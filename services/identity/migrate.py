"""Applies `migrations/*.sql` to the auth database and, optionally, hands pre-accounts data to an
admin (IRA-33).

    python -m services.identity.migrate                           # apply pending migrations
    python -m services.identity.migrate --adopt-legacy admin@x.io # + give unowned data to that admin

The target is `auth.database` on the storage Postgres host (default `rag_db`, override with
RAG_AUTH_DB) — never the ambient DATABASE_URL / POSTGRES_DB, which point elsewhere on this machine.
Both steps are idempotent, so re-run `--adopt-legacy` after dropping files straight into
data/documents/ for the reconciler to index: those have no uploader and would otherwise be unreadable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from contracts.identity import OwnedDocument
from services.common.config import load_config
from services.common.logger import get_logger

logger = get_logger("identity.migrate")

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"


def apply_migrations(conninfo: str) -> list[str]:
    import psycopg

    applied: list[str] = []
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT now())"
        )
        done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.stem in done:
                continue
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.stem,))
            applied.append(path.stem)
            logger.info(f"Applied migration {path.stem}")
    return applied


def backfill_personal_workspaces(conninfo: str, *, redis_host: str, redis_port: int) -> dict[str, int]:
    """Gives every pre-IRA-46 user a personal workspace and stamps their existing Redis projects with
    it. Idempotent: a user who already owns a workspace (from signup, demo, or a prior run of this)
    is skipped, and `stamp_workspace_for_owner` only touches sessions still missing a `workspace_id`."""
    from services.identity.store import PostgresIdentityStore
    from services.session.manager import SessionManager

    store = PostgresIdentityStore(conninfo)
    sessions = SessionManager(host=redis_host, port=redis_port)

    created = 0
    stamped = 0
    for user in store.list_users():
        workspaces = [w for w in store.list_workspaces_for_user(user.id) if w.owner_id == user.id]
        if workspaces:
            workspace = workspaces[0]
        else:
            workspace = store.create_workspace(name=f"{user.display_name or user.email}'s Workspace", owner_id=user.id)
            created += 1
        if sessions.redis_client is not None:
            stamped += sessions.stamp_workspace_for_owner(user.id, workspace.id)
    return {"workspaces_created": created, "sessions_stamped": stamped}


def adopt_legacy(admin_email: str, *, redis_host: str, redis_port: int, conninfo: str) -> dict[str, int]:
    """Stamps unowned Redis projects with the admin and registers every legacy document as theirs."""
    from services.identity.store import PostgresIdentityStore
    from services.indexing.bm25_store import BM25Store
    from services.ingestion.visualizer import resolve_document_path
    from services.session.manager import SessionManager

    store = PostgresIdentityStore(conninfo)
    admin = store.get_user_by_email(admin_email)
    if not admin or not admin.is_admin:
        raise SystemExit(f"No admin account '{admin_email}'. Create it first: python -m services.identity.cli create-admin")

    sessions = SessionManager(host=redis_host, port=redis_port)
    if sessions.redis_client is None:
        raise SystemExit("Redis is unreachable; legacy projects live there. Start it and retry.")
    adopted = sessions.adopt_unowned(admin.id)

    # Every indexed doc_id, mapped to its source file where one exists. The lookup is the legacy
    # fuzzy resolver on purpose: this runs once, by an operator, over files that predate ownership.
    doc_ids = {c.get("doc_id") for c in BM25Store().corpus_chunks if c.get("doc_id")}
    registered = 0
    for doc_id in sorted(doc_ids):
        if doc_id.startswith(("web_", "wiki_index")):
            continue  # the public web corpus is readable by everyone and owned by no one
        path = resolve_document_path(doc_id)
        store.add_document(OwnedDocument(
            user_id=admin.id, doc_id=doc_id,
            filename=path.name if path else doc_id, path=str(path) if path else "",
        ))
        registered += 1
    return {"projects": adopted, "documents": registered}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--adopt-legacy", metavar="ADMIN_EMAIL")
    args = parser.parse_args(argv)

    settings = load_config()
    print(f"Target database: {settings.auth.database} on {settings.storage.postgres_host}:{settings.storage.postgres_port}")
    applied = apply_migrations(settings.auth_postgres_url)
    print(f"Applied: {', '.join(applied) if applied else 'nothing (up to date)'}")
    backfill = backfill_personal_workspaces(
        settings.auth_postgres_url, redis_host=settings.storage.redis_host, redis_port=settings.storage.redis_port
    )
    print(
        f"Workspaces: created {backfill['workspaces_created']} personal workspace(s), "
        f"stamped {backfill['sessions_stamped']} project(s)"
    )
    if args.adopt_legacy:
        result = adopt_legacy(
            args.adopt_legacy, redis_host=settings.storage.redis_host,
            redis_port=settings.storage.redis_port, conninfo=settings.auth_postgres_url,
        )
        print(f"Adopted {result['projects']} projects and {result['documents']} documents for {args.adopt_legacy}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
