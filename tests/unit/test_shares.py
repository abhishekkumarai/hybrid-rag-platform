"""Public share links and forking a shared chat into one's own project (IRA-35)."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from contracts.identity import User
from contracts.retrieval import Citation, RetrieveResponse
from contracts.session import ChatMessage
from services.gateway import api
from tests.unit.conftest import own_documents

client = TestClient(api.app)

ANA = User(id="usr_ana", email="ana@example.com")
BEN = User(id="usr_ben", email="ben@example.com")
ANA_DOC = "falcon_1a2b3c4d"
CIT = Citation(doc_id=ANA_DOC, page=2, bbox=(1.0, 2.0, 3.0, 4.0), snippet="Falcon ships in May.", formatted_badge="[falcon]")


def as_user(user: User | None) -> None:
    api.app.dependency_overrides[api.optional_user] = lambda: user


@pytest.fixture(autouse=True)
def _users(identity):
    identity.users[ANA.id] = ANA
    identity.users[BEN.id] = BEN
    identity.create_workspace(name="Ana's", owner_id=ANA.id)
    identity.create_workspace(name="Ben's", owner_id=BEN.id)
    own_documents(identity, ANA_DOC, user=ANA)


@pytest.fixture
def ana_chat():
    """Ana's project with one answered turn."""
    as_user(ANA)
    sid = client.post("/api/v1/sessions", json={"title": "Falcon plan", "files": [ANA_DOC]}).json()["id"]
    api.session_manager.append_message(sid, ChatMessage(role="user", content="When does Falcon ship?"))
    api.session_manager.append_message(sid, ChatMessage(
        role="assistant", content="Falcon ships in May.", citations=[CIT], metadata={"eval": {"groundedness": 1.0}},
    ))
    return sid


def _share(sid):
    as_user(ANA)
    r = client.post(f"/api/v1/sessions/{sid}/shares")
    assert r.status_code == 200
    return r.json()


def test_share_is_a_public_snapshot_without_internal_metadata(ana_chat, identity):
    created = _share(ana_chat)
    token = created["token"]
    assert created["url"].endswith(f"/s/{token}")
    assert all(s.token_hash != token for s in identity.shares.values())

    api.session_manager.append_message(ana_chat, ChatMessage(role="user", content="Private follow-up"))

    as_user(None)
    snap = client.get(f"/api/v1/public/shares/{token}")
    assert snap.status_code == 200
    body = snap.json()
    assert body["title"] == "Falcon plan" and body["doc_ids"] == [ANA_DOC]
    assert [m["content"] for m in body["messages"]] == ["When does Falcon ship?", "Falcon ships in May."]
    assert "metadata" not in body["messages"][1]
    assert body["messages"][1]["citations"][0]["doc_id"] == ANA_DOC


def test_public_preview_is_limited_to_the_snapshot_documents(ana_chat, identity):
    own_documents(identity, "unrelated_99999999", user=ANA)
    token = _share(ana_chat)["token"]
    as_user(None)
    assert client.get(f"/api/v1/public/shares/{token}/preview?doc_id=unrelated_99999999").status_code == 404
    with patch("services.gateway.api._render_preview", return_value=api.Response(content=b"png")) as render:
        assert client.get(f"/api/v1/public/shares/{token}/preview?doc_id={ANA_DOC}&page=2").status_code == 200
    assert render.call_args[0][1] == {ANA_DOC}


def test_revoke_kills_the_url_and_only_the_owner_can_do_it(ana_chat):
    created = _share(ana_chat)
    share_id, token = created["share"]["id"], created["token"]

    as_user(BEN)
    assert client.delete(f"/api/v1/shares/{share_id}").status_code == 404
    as_user(ANA)
    assert client.delete(f"/api/v1/shares/{share_id}").status_code == 200
    assert client.get(f"/api/v1/sessions/{ana_chat}/shares").json()["shares"][0]["revoked"] is True

    as_user(None)
    assert client.get(f"/api/v1/public/shares/{token}").status_code == 404


def test_fork_needs_sign_in(ana_chat):
    token = _share(ana_chat)["token"]
    as_user(None)
    assert client.post(f"/api/v1/public/shares/{token}/fork").status_code == 401


@patch("services.gateway.api.requests.post")
@patch("services.gateway.api.get_services")
def test_fork_continues_the_conversation_grounded_in_the_shared_documents(mock_services, mock_post, ana_chat):
    token = _share(ana_chat)["token"]

    as_user(BEN)
    fork = client.post(f"/api/v1/public/shares/{token}/fork")
    assert fork.status_code == 200
    fid = fork.json()["session_id"]

    detail = client.get(f"/api/v1/sessions/{fid}").json()
    assert detail["session"]["owner_id"] == BEN.id and detail["session"]["forked_from"]
    assert detail["session"]["files"] == [ANA_DOC]
    assert [m["content"] for m in detail["messages"]] == ["When does Falcon ship?", "Falcon ships in May."]
    # The copied history is the context for Ben's next turn
    assert "When does Falcon ship?" in api.session_manager.build_conversation_context(fid)

    # Ben can now read the shared document, read-only
    docs = client.get("/api/v1/documents").json()["documents"]
    assert {"doc_id": ANA_DOC, "read_only": True}.items() <= next(d for d in docs if d["doc_id"] == ANA_DOC).items()

    retrieval = MagicMock()
    retrieval.retrieve.return_value = RetrieveResponse(
        query="q", candidates=[], citations=[], refused=True, top_score=0.0, duration_ms=1.0
    )
    mock_services.return_value = (MagicMock(), MagicMock(), retrieval)
    client.post("/api/v1/chat", json={"query": "And the budget?", "session_id": fid, "stream": False, "mode": "direct"})
    assert retrieval.retrieve.call_args[0][0].doc_ids == [ANA_DOC]

    # Ana's project is untouched
    as_user(ANA)
    assert len(client.get(f"/api/v1/sessions/{ana_chat}").json()["messages"]) == 2


def test_revoking_removes_forks_document_access_but_keeps_their_history(ana_chat):
    created = _share(ana_chat)
    as_user(BEN)
    fid = client.post(f"/api/v1/public/shares/{created['token']}/fork").json()["session_id"]

    as_user(ANA)
    client.delete(f"/api/v1/shares/{created['share']['id']}")

    as_user(BEN)
    assert client.get(f"/api/v1/preview?doc_id={ANA_DOC}").status_code == 404
    assert len(client.get(f"/api/v1/sessions/{fid}").json()["messages"]) == 2
    data = client.post("/api/v1/chat", json={"query": "And the budget?", "session_id": fid, "stream": False}).json()
    assert data["refused"] is True


def test_resharing_a_fork_does_not_republish_granted_documents(ana_chat):
    token = _share(ana_chat)["token"]
    as_user(BEN)
    fid = client.post(f"/api/v1/public/shares/{token}/fork").json()["session_id"]
    reshared = client.post(f"/api/v1/sessions/{fid}/shares").json()

    as_user(None)
    snap = client.get(f"/api/v1/public/shares/{reshared['token']}").json()
    assert snap["doc_ids"] == []
    assert all(not m["citations"] for m in snap["messages"])
