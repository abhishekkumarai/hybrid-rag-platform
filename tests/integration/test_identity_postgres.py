"""PostgresIdentityStore against the real auth database (IRA-33). Skipped when Postgres is down or
unmigrated (`python -m services.identity.migrate`). Every row it writes is deleted afterwards."""

import time
import uuid

import pytest

from contracts.identity import OwnedDocument
from contracts.share import Share, SharedMessage, ShareSnapshot
from services.common.config import load_config
from services.identity.store import DuplicateEmailError, PostgresIdentityStore


@pytest.fixture
def store():
    s = PostgresIdentityStore(load_config().auth_postgres_url)
    try:
        s.ping()
    except Exception as exc:
        pytest.skip(f"auth database unavailable: {exc}")
    created: list[str] = []
    s.created = created  # type: ignore[attr-defined]
    yield s
    with s._conn() as conn:
        for uid in created:
            conn.execute("DELETE FROM users WHERE id = %s", (uid,))  # cascades to everything else


def _user(store, admin=False):
    user = store.create_user(f"it-{uuid.uuid4().hex[:8]}@example.com", "hash", is_admin=admin)
    store.created.append(user.id)
    return user


def test_users_and_login_sessions(store):
    user = _user(store)
    assert store.get_user(user.id).email == user.email
    assert store.get_credentials(user.email.upper()) == (store.get_user(user.id), "hash")
    with pytest.raises(DuplicateEmailError):
        store.create_user(user.email, "x")

    store.create_auth_session(user.id, "tok-live-" + user.id, time.time() + 60)
    store.create_auth_session(user.id, "tok-dead-" + user.id, time.time() - 1)
    assert store.user_for_token("tok-live-" + user.id).id == user.id
    assert store.user_for_token("tok-dead-" + user.id) is None
    store.delete_auth_session("tok-live-" + user.id)
    assert store.user_for_token("tok-live-" + user.id) is None


def test_documents_shares_and_grants(store):
    ana, ben = _user(store), _user(store)
    doc_id = f"doc_{uuid.uuid4().hex[:8]}"
    store.add_document(OwnedDocument(user_id=ana.id, doc_id=doc_id, filename="a.pdf", path="/tmp/a.pdf"))
    store.add_document(OwnedDocument(user_id=ana.id, doc_id=doc_id, filename="a.pdf", path="/tmp/a.pdf"))
    store.add_document(OwnedDocument(user_id=ben.id, doc_id=doc_id, filename="b.pdf", path="/tmp/b.pdf"))
    assert store.owned_doc_ids(ana.id) == {doc_id}
    assert store.document_owner_count(doc_id) == 2
    assert store.first_owner(doc_id) == ana.id
    assert store.get_document(doc_id, ben.id).filename == "b.pdf"

    share = Share(
        token_hash=f"h-{uuid.uuid4().hex}", session_id="sess_it", owner_id=ana.id,
        snapshot=ShareSnapshot(title="T", doc_ids=[doc_id], messages=[SharedMessage(role="user", content="q", timestamp=1.0)]),
    )
    store.create_share(share)
    fetched = store.get_share_by_token_hash(share.token_hash)
    assert fetched.snapshot.messages[0].content == "q" and fetched.revoked_at is None
    store.record_share_view(share.id)
    assert store.get_share(share.id).view_count == 1
    assert [s.id for s in store.list_shares("sess_it") if s.owner_id == ana.id] == [share.id]

    reader = _user(store)
    store.add_grants(reader.id, [doc_id], share.id)
    assert store.granted_doc_ids(reader.id) == {doc_id}
    store.revoke_share(share.id)
    assert store.get_share(share.id).revoked_at is not None
    assert store.granted_doc_ids(reader.id) == set()
