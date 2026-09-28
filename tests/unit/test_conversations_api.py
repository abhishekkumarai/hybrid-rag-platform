"""API tests for chat threads within a project (IRA-24)."""

from fastapi.testclient import TestClient

from services.gateway.api import app, session_manager  # noqa: F401 (app drives the TestClient)
from tests.unit.conftest import TEST_USER

client = TestClient(app)


def _create_owned(**kwargs):
    return session_manager.create_session(owner_id=TEST_USER.id, **kwargs)


def test_conversation_lifecycle_over_the_api():
    project = _create_owned(title="Project with threads")

    # A brand-new project reports one (lazily-created) default conversation.
    listed = client.get(f"/api/v1/sessions/{project.id}/conversations").json()["conversations"]
    assert len(listed) == 1
    default_id = listed[0]["id"]

    created = client.post(
        f"/api/v1/sessions/{project.id}/conversations", json={"title": "Second thread"}
    )
    assert created.status_code == 200
    second = created.json()
    assert second["title"] == "Second thread"
    assert second["id"] != default_id

    listed_again = client.get(f"/api/v1/sessions/{project.id}/conversations").json()["conversations"]
    assert {c["id"] for c in listed_again} == {default_id, second["id"]}

    renamed = client.patch(
        f"/api/v1/sessions/{project.id}/conversations/{second['id']}", json={"title": "Renamed"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Renamed"

    detail = client.get(f"/api/v1/sessions/{project.id}/conversations/{second['id']}")
    assert detail.status_code == 200
    assert detail.json()["messages"] == []

    # A project can't be left with zero threads.
    delete_default = client.delete(f"/api/v1/sessions/{project.id}/conversations/{default_id}")
    assert delete_default.json()["deleted"] is True
    delete_last = client.delete(f"/api/v1/sessions/{project.id}/conversations/{second['id']}")
    assert delete_last.json()["deleted"] is False


def test_conversation_routes_404_for_another_users_project(identity):
    from contracts.identity import User

    other = User(id="usr_other", email="other@example.com", display_name="Other")
    identity.users[other.id] = other
    project = session_manager.create_session(owner_id=other.id)

    assert client.get(f"/api/v1/sessions/{project.id}/conversations").status_code == 404
    assert client.post(f"/api/v1/sessions/{project.id}/conversations").status_code == 404


def test_chat_can_target_a_specific_conversation(identity):
    """/api/v1/chat threads messages into whichever conversation_id it's given, not always the default."""
    from unittest.mock import patch

    from tests.unit.conftest import own_documents
    from tests.unit.test_chat_pipeline_contract import _coordinator, _ollama, _retrieval

    own_documents(identity, "doc_a")
    project = _create_owned(files=["doc_a"])
    second = client.post(f"/api/v1/sessions/{project.id}/conversations").json()

    with patch("services.gateway.api.get_services") as gs, \
         patch("services.gateway.api.get_agentic_coordinator") as gc, \
         patch("services.gateway.api.requests.post", return_value=_ollama()):
        gs.return_value = (None, None, _retrieval(refused=False))
        gc.return_value = _coordinator(refused=False)
        r = client.post(
            "/api/v1/chat",
            json={
                "session_id": project.id,
                "conversation_id": second["id"],
                "query": "What GPU?",
                "stream": False,
                "mode": "direct",
            },
        )
    assert r.status_code == 200
    assert r.json()["conversation_id"] == second["id"]

    default_id = client.get(f"/api/v1/sessions/{project.id}/conversations").json()["conversations"][0]["id"]
    assert default_id != second["id"]

    _, default_msgs = session_manager.get_conversation_messages(project.id, default_id)
    assert default_msgs == []
    _, second_msgs = session_manager.get_conversation_messages(project.id, second["id"])
    assert len(second_msgs) == 2
