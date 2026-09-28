"""Shared unit-test fixtures."""

import pytest

from contracts.identity import OwnedDocument, User
from services.identity.store import InMemoryIdentityStore

# Every gateway test runs signed in as this admin unless it signs in as someone else (IRA-33).
TEST_USER = User(id="usr_test", email="test@example.com", display_name="Test", is_admin=True)


@pytest.fixture(autouse=True)
def identity(monkeypatch):
    """A fresh in-memory identity store per test, the gateway signed in as TEST_USER, and the CSRF
    header check off. Tests of auth itself remove the overrides (see `real_auth`)."""
    from services.gateway import api

    store = InMemoryIdentityStore()
    store.users[TEST_USER.id] = TEST_USER
    store.password_hashes[TEST_USER.id] = ""
    monkeypatch.setattr(api, "_identity_store", store)
    monkeypatch.setattr(api, "_public_doc_ids", lambda: set())
    api.app.dependency_overrides[api.optional_user] = lambda: TEST_USER
    api.app.dependency_overrides[api.csrf_guard] = lambda: None
    yield store
    api.app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _in_memory_projects(monkeypatch):
    """Keep projects and messages out of the live Redis (IRA-37). The gateway's SessionManager is a
    module-level singleton connected to 127.0.0.1:6379 whenever Redis runs, so without this every
    suite run left dozens of junk projects in the real store. Patching the shared instance (not the
    module attribute) also covers tests that imported `session_manager` directly."""
    from services.gateway import api

    monkeypatch.setattr(api.session_manager, "redis_client", None)
    monkeypatch.setattr(api.session_manager, "_in_memory_sessions", {})
    monkeypatch.setattr(api.session_manager, "_in_memory_messages", {})


@pytest.fixture
def real_auth():
    """Drops the signed-in override so requests authenticate through the real cookie path."""
    from services.gateway import api

    api.app.dependency_overrides.pop(api.optional_user, None)
    api.app.dependency_overrides.pop(api.csrf_guard, None)


@pytest.fixture
def make_project(identity):
    """Creates a TEST_USER project with `doc_ids` uploaded by TEST_USER and attached. A project with
    no readable documents refuses every turn (IRA-34), so chat tests need one of these."""
    from services.gateway import api

    def _make(*doc_ids: str, **kwargs):
        own_documents(identity, *doc_ids)
        return api.session_manager.create_session(files=list(doc_ids), owner_id=TEST_USER.id, **kwargs)

    return _make


def own_documents(store: InMemoryIdentityStore, *doc_ids: str, user: User = TEST_USER) -> None:
    """Registers `doc_ids` as uploaded by `user`, as /api/v1/ingest would."""
    for doc_id in doc_ids:
        store.add_document(OwnedDocument(user_id=user.id, doc_id=doc_id, filename=f"{doc_id}.pdf", path=""))


@pytest.fixture(autouse=True)
def _no_sampled_llm_judge(monkeypatch):
    """Disable the sampled background LLM judge (IRA-14) for every unit test.

    It fires on a random ~10% of answered turns and calls `requests.post` from a thread, so tests
    that patch `requests.post` and inspect `call_args` would otherwise flakily see the judge's call
    instead of the generation call. Tests that exercise the judge pass `sample_rate` explicitly."""
    from services.gateway import api

    monkeypatch.setattr(api.settings.evaluation, "llm_judge_sample_rate", 0.0)


@pytest.fixture(autouse=True)
def _offline_model_catalog(monkeypatch):
    """Keep the chat-model check (IRA-31) off the network: the gateway's catalog would otherwise
    query a real Ollama on every chat test. Tests of the check patch `rejects` themselves."""
    from services.gateway import api

    monkeypatch.setattr(api.model_catalog, "rejects", lambda name: False)
