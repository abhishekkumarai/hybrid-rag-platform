"""Durable identity and access-control state: users, login sessions, document ownership, shares
and the read-only document grants that forks of a share receive (IRA-33).

Two implementations of one interface, the same split `SessionManager` uses for Redis: Postgres
(`rag_db`) in every real deployment, and an in-memory store for unit tests and for a gateway started
without Postgres (accounts then last only as long as the process, which is logged loudly)."""

from __future__ import annotations

import threading
import time
from typing import Protocol

from contracts.identity import OwnedDocument, User
from contracts.share import Share, ShareSnapshot
from services.common.logger import get_logger

logger = get_logger("identity.store")


class DuplicateEmailError(ValueError):
    pass


class IdentityStore(Protocol):
    # users
    def create_user(self, email: str, password_hash: str, display_name: str = "", is_admin: bool = False) -> User: ...
    def get_user(self, user_id: str) -> User | None: ...
    def get_credentials(self, email: str) -> tuple[User, str] | None: ...
    def get_user_by_email(self, email: str) -> User | None: ...

    # login sessions
    def create_auth_session(self, user_id: str, token_hash: str, expires_at: float) -> None: ...
    def user_for_token(self, token_hash: str) -> User | None: ...
    def delete_auth_session(self, token_hash: str) -> None: ...

    # documents
    def add_document(self, doc: OwnedDocument) -> None: ...
    def owned_doc_ids(self, user_id: str) -> set[str]: ...
    def get_document(self, doc_id: str, user_id: str | None = None) -> OwnedDocument | None: ...
    def document_owner_count(self, doc_id: str) -> int: ...
    def first_owner(self, doc_id: str) -> str | None: ...

    # grants
    def add_grants(self, user_id: str, doc_ids: list[str], share_id: str) -> None: ...
    def granted_doc_ids(self, user_id: str) -> set[str]: ...

    # shares
    def create_share(self, share: Share) -> None: ...
    def get_share(self, share_id: str) -> Share | None: ...
    def get_share_by_token_hash(self, token_hash: str) -> Share | None: ...
    def list_shares(self, session_id: str) -> list[Share]: ...
    def revoke_share(self, share_id: str) -> None: ...
    def record_share_view(self, share_id: str) -> None: ...


def normalize_email(email: str) -> str:
    return email.strip().lower()


class InMemoryIdentityStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.users: dict[str, User] = {}
        self.password_hashes: dict[str, str] = {}
        self.auth_sessions: dict[str, tuple[str, float]] = {}
        self.documents: dict[tuple[str, str], OwnedDocument] = {}
        self.grants: set[tuple[str, str, str]] = set()
        self.shares: dict[str, Share] = {}

    def create_user(self, email: str, password_hash: str, display_name: str = "", is_admin: bool = False) -> User:
        email = normalize_email(email)
        with self._lock:
            if any(u.email == email for u in self.users.values()):
                raise DuplicateEmailError(email)
            user = User(email=email, display_name=display_name, is_admin=is_admin)
            self.users[user.id] = user
            self.password_hashes[user.id] = password_hash
        return user

    def get_user(self, user_id: str) -> User | None:
        return self.users.get(user_id)

    def get_user_by_email(self, email: str) -> User | None:
        email = normalize_email(email)
        return next((u for u in self.users.values() if u.email == email), None)

    def get_credentials(self, email: str) -> tuple[User, str] | None:
        user = self.get_user_by_email(email)
        return (user, self.password_hashes[user.id]) if user else None

    def create_auth_session(self, user_id: str, token_hash: str, expires_at: float) -> None:
        self.auth_sessions[token_hash] = (user_id, expires_at)

    def user_for_token(self, token_hash: str) -> User | None:
        entry = self.auth_sessions.get(token_hash)
        if not entry or entry[1] < time.time():
            return None
        return self.users.get(entry[0])

    def delete_auth_session(self, token_hash: str) -> None:
        self.auth_sessions.pop(token_hash, None)

    def add_document(self, doc: OwnedDocument) -> None:
        self.documents.setdefault((doc.user_id, doc.doc_id), doc)

    def owned_doc_ids(self, user_id: str) -> set[str]:
        return {d for (u, d) in self.documents if u == user_id}

    def get_document(self, doc_id: str, user_id: str | None = None) -> OwnedDocument | None:
        if user_id is not None:
            return self.documents.get((user_id, doc_id))
        matches = sorted((d for (_, i), d in self.documents.items() if i == doc_id), key=lambda d: d.created_at)
        return matches[0] if matches else None

    def document_owner_count(self, doc_id: str) -> int:
        return sum(1 for (_, d) in self.documents if d == doc_id)

    def first_owner(self, doc_id: str) -> str | None:
        doc = self.get_document(doc_id)
        return doc.user_id if doc else None

    def add_grants(self, user_id: str, doc_ids: list[str], share_id: str) -> None:
        for d in doc_ids:
            self.grants.add((user_id, d, share_id))

    def granted_doc_ids(self, user_id: str) -> set[str]:
        live = {s.id for s in self.shares.values() if s.revoked_at is None}
        return {d for (u, d, s) in self.grants if u == user_id and s in live}

    def create_share(self, share: Share) -> None:
        self.shares[share.id] = share

    def get_share(self, share_id: str) -> Share | None:
        return self.shares.get(share_id)

    def get_share_by_token_hash(self, token_hash: str) -> Share | None:
        return next((s for s in self.shares.values() if s.token_hash == token_hash), None)

    def list_shares(self, session_id: str) -> list[Share]:
        return sorted(
            (s for s in self.shares.values() if s.session_id == session_id), key=lambda s: s.created_at, reverse=True
        )

    def revoke_share(self, share_id: str) -> None:
        share = self.shares.get(share_id)
        if share and share.revoked_at is None:
            share.revoked_at = time.time()
        self.grants = {g for g in self.grants if g[2] != share_id}

    def record_share_view(self, share_id: str) -> None:
        share = self.shares.get(share_id)
        if share:
            share.view_count += 1


class PostgresIdentityStore:
    """One short-lived autocommit connection per call: traffic is a handful of lookups per request
    on a local server, which doesn't justify a pool dependency."""

    def __init__(self, conninfo: str) -> None:
        self.conninfo = conninfo

    def _conn(self):
        import psycopg

        return psycopg.connect(self.conninfo, autocommit=True, connect_timeout=3)

    def ping(self) -> None:
        with self._conn() as conn:
            conn.execute("SELECT 1 FROM users LIMIT 1")

    @staticmethod
    def _user(row) -> User:
        return User(id=row[0], email=row[1], display_name=row[2], is_admin=row[3], created_at=row[4])

    _USER_COLS = "id, email, display_name, is_admin, created_at"

    def create_user(self, email: str, password_hash: str, display_name: str = "", is_admin: bool = False) -> User:
        import psycopg

        user = User(email=normalize_email(email), display_name=display_name, is_admin=is_admin)
        try:
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO users (id, email, display_name, password_hash, is_admin, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (user.id, user.email, user.display_name, password_hash, user.is_admin, user.created_at),
                )
        except psycopg.errors.UniqueViolation as exc:
            raise DuplicateEmailError(user.email) from exc
        return user

    def get_user(self, user_id: str) -> User | None:
        with self._conn() as conn:
            row = conn.execute(f"SELECT {self._USER_COLS} FROM users WHERE id = %s", (user_id,)).fetchone()
        return self._user(row) if row else None

    def get_user_by_email(self, email: str) -> User | None:
        with self._conn() as conn:
            row = conn.execute(
                f"SELECT {self._USER_COLS} FROM users WHERE email = %s", (normalize_email(email),)
            ).fetchone()
        return self._user(row) if row else None

    def get_credentials(self, email: str) -> tuple[User, str] | None:
        with self._conn() as conn:
            row = conn.execute(
                f"SELECT {self._USER_COLS}, password_hash FROM users WHERE email = %s", (normalize_email(email),)
            ).fetchone()
        return (self._user(row), row[5]) if row else None

    def create_auth_session(self, user_id: str, token_hash: str, expires_at: float) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO auth_sessions (token_hash, user_id, created_at, expires_at) VALUES (%s, %s, %s, %s)",
                (token_hash, user_id, time.time(), expires_at),
            )

    def user_for_token(self, token_hash: str) -> User | None:
        cols = ", ".join(f"u.{c.strip()}" for c in self._USER_COLS.split(","))
        with self._conn() as conn:
            row = conn.execute(
                f"SELECT {cols} FROM auth_sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.token_hash = %s AND s.expires_at > %s",
                (token_hash, time.time()),
            ).fetchone()
        return self._user(row) if row else None

    def delete_auth_session(self, token_hash: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM auth_sessions WHERE token_hash = %s", (token_hash,))

    @staticmethod
    def _doc(row) -> OwnedDocument:
        return OwnedDocument(user_id=row[0], doc_id=row[1], filename=row[2], path=row[3], created_at=row[4])

    def add_document(self, doc: OwnedDocument) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO user_documents (user_id, doc_id, filename, path, created_at) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (user_id, doc_id) DO NOTHING",
                (doc.user_id, doc.doc_id, doc.filename, doc.path, doc.created_at),
            )

    def owned_doc_ids(self, user_id: str) -> set[str]:
        with self._conn() as conn:
            rows = conn.execute("SELECT doc_id FROM user_documents WHERE user_id = %s", (user_id,)).fetchall()
        return {r[0] for r in rows}

    def get_document(self, doc_id: str, user_id: str | None = None) -> OwnedDocument | None:
        sql = "SELECT user_id, doc_id, filename, path, created_at FROM user_documents WHERE doc_id = %s"
        params: tuple = (doc_id,)
        if user_id is not None:
            sql += " AND user_id = %s"
            params = (doc_id, user_id)
        with self._conn() as conn:
            row = conn.execute(sql + " ORDER BY created_at LIMIT 1", params).fetchone()
        return self._doc(row) if row else None

    def document_owner_count(self, doc_id: str) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT count(*) FROM user_documents WHERE doc_id = %s", (doc_id,)).fetchone()[0]

    def first_owner(self, doc_id: str) -> str | None:
        doc = self.get_document(doc_id)
        return doc.user_id if doc else None

    def add_grants(self, user_id: str, doc_ids: list[str], share_id: str) -> None:
        now = time.time()
        with self._conn() as conn:
            for d in doc_ids:
                conn.execute(
                    "INSERT INTO doc_grants (user_id, doc_id, share_id, created_at) VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT DO NOTHING",
                    (user_id, d, share_id, now),
                )

    def granted_doc_ids(self, user_id: str) -> set[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT g.doc_id FROM doc_grants g JOIN shares s ON s.id = g.share_id "
                "WHERE g.user_id = %s AND s.revoked_at IS NULL",
                (user_id,),
            ).fetchall()
        return {r[0] for r in rows}

    _SHARE_COLS = "id, token_hash, session_id, owner_id, snapshot, created_at, revoked_at, view_count"

    @staticmethod
    def _share(row) -> Share:
        return Share(
            id=row[0], token_hash=row[1], session_id=row[2], owner_id=row[3],
            snapshot=ShareSnapshot.model_validate(row[4]), created_at=row[5], revoked_at=row[6], view_count=row[7],
        )

    def create_share(self, share: Share) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO shares (id, token_hash, session_id, owner_id, snapshot, created_at) "
                "VALUES (%s, %s, %s, %s, %s::jsonb, %s)",
                (share.id, share.token_hash, share.session_id, share.owner_id,
                 share.snapshot.model_dump_json(), share.created_at),
            )

    def _one_share(self, where: str, value: str) -> Share | None:
        with self._conn() as conn:
            row = conn.execute(f"SELECT {self._SHARE_COLS} FROM shares WHERE {where} = %s", (value,)).fetchone()
        return self._share(row) if row else None

    def get_share(self, share_id: str) -> Share | None:
        return self._one_share("id", share_id)

    def get_share_by_token_hash(self, token_hash: str) -> Share | None:
        return self._one_share("token_hash", token_hash)

    def list_shares(self, session_id: str) -> list[Share]:
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT {self._SHARE_COLS} FROM shares WHERE session_id = %s ORDER BY created_at DESC",
                (session_id,),
            ).fetchall()
        return [self._share(r) for r in rows]

    def revoke_share(self, share_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE shares SET revoked_at = %s WHERE id = %s AND revoked_at IS NULL", (time.time(), share_id)
            )
            conn.execute("DELETE FROM doc_grants WHERE share_id = %s", (share_id,))

    def record_share_view(self, share_id: str) -> None:
        with self._conn() as conn:
            conn.execute("UPDATE shares SET view_count = view_count + 1 WHERE id = %s", (share_id,))


def build_identity_store(conninfo: str) -> IdentityStore:
    """Postgres when reachable and migrated, else the in-memory store with a loud warning."""
    store = PostgresIdentityStore(conninfo)
    try:
        store.ping()
        logger.info("IdentityStore: using Postgres")
        return store
    except Exception as exc:
        logger.warning(
            f"IdentityStore: Postgres unavailable or not migrated ({exc}); using an IN-MEMORY store — "
            "accounts, shares and document ownership will be lost on restart. "
            "Run `python -m services.identity.migrate`."
        )
        return InMemoryIdentityStore()
