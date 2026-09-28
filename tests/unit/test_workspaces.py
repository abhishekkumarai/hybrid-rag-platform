"""Unit tests for shared workspaces (IRA-46): store CRUD, doc-scope union, and the
member/non-member/removed-member access matrix on projects, chats, and documents."""

from fastapi.testclient import TestClient

from contracts.identity import User
from services.gateway.api import app, session_manager
from services.identity.access import accessible_doc_ids
from services.identity.store import InMemoryIdentityStore
from tests.unit.conftest import TEST_USER, own_documents

client = TestClient(app)


# --- Store-level CRUD -------------------------------------------------------------------------


def test_in_memory_store_workspace_crud():
    store = InMemoryIdentityStore()
    owner = User(email="owner@example.com")
    other = User(email="other@example.com")
    store.users[owner.id] = owner
    store.users[other.id] = other

    ws = store.create_workspace(name="Team", owner_id=owner.id)
    assert store.get_member(ws.id, owner.id).role == "owner"
    assert store.workspace_ids_for_user(owner.id) == {ws.id}

    member = store.add_member(ws.id, other.id, "member")
    assert member.role == "member"
    assert {m.user_id for m in store.list_members(ws.id)} == {owner.id, other.id}
    assert store.workspace_ids_for_user(other.id) == {ws.id}

    updated = store.update_member_role(ws.id, other.id, "admin")
    assert updated.role == "admin"

    renamed = store.update_workspace(ws.id, "Renamed Team")
    assert renamed.name == "Renamed Team"

    assert store.remove_member(ws.id, other.id) is True
    assert store.get_member(ws.id, other.id) is None
    assert store.remove_member(ws.id, other.id) is False

    assert store.delete_workspace(ws.id) is True
    assert store.get_workspace(ws.id) is None
    assert store.get_member(ws.id, owner.id) is None


def test_workspace_doc_ids_feed_accessible_doc_ids():
    store = InMemoryIdentityStore()
    owner = User(email="owner2@example.com")
    member = User(email="member2@example.com")
    outsider = User(email="outsider2@example.com")
    for u in (owner, member, outsider):
        store.users[u.id] = u

    ws = store.create_workspace(name="Docs Team", owner_id=owner.id)
    store.add_member(ws.id, member.id, "member")
    store.attach_workspace_document(ws.id, "doc_shared", added_by=owner.id)

    assert "doc_shared" in accessible_doc_ids(store, owner.id)
    assert "doc_shared" in accessible_doc_ids(store, member.id)
    assert "doc_shared" not in accessible_doc_ids(store, outsider.id)


# --- API access matrix -------------------------------------------------------------------------


def _other_user(identity, email="colleague@example.com") -> User:
    user = User(id=f"usr_{email.split('@')[0]}", email=email, display_name="Colleague")
    identity.users[user.id] = user
    identity.password_hashes[user.id] = ""
    return user


def test_project_visible_to_workspace_members_and_not_outsiders(identity):
    other = _other_user(identity)
    ws = identity.create_workspace(name="Shared", owner_id=TEST_USER.id)
    identity.add_member(ws.id, other.id, "member")
    outsider = _other_user(identity, "outsider@example.com")

    project = session_manager.create_session(owner_id=TEST_USER.id, workspace_id=ws.id)

    # The workspace's own owner (creator) can read it.
    assert client.get(f"/api/v1/sessions/{project.id}").status_code == 200

    # A member (not the owner) can read it too, via workspace_session's membership path.
    from services.gateway.api import current_user

    app.dependency_overrides[current_user] = lambda: other
    try:
        assert client.get(f"/api/v1/sessions/{project.id}").status_code == 200
    finally:
        app.dependency_overrides[current_user] = lambda: TEST_USER

    # An outsider gets a 404, not a 403 (can't probe existence).
    app.dependency_overrides[current_user] = lambda: outsider
    try:
        assert client.get(f"/api/v1/sessions/{project.id}").status_code == 404
    finally:
        app.dependency_overrides[current_user] = lambda: TEST_USER

    # Removing the member revokes access.
    identity.remove_member(ws.id, other.id)
    app.dependency_overrides[current_user] = lambda: other
    try:
        assert client.get(f"/api/v1/sessions/{project.id}").status_code == 404
    finally:
        app.dependency_overrides[current_user] = lambda: TEST_USER


def test_workspace_document_readable_by_members_not_outsiders(identity):
    other = _other_user(identity)
    outsider = _other_user(identity, "outsider2@example.com")
    ws = identity.create_workspace(name="Shared Docs", owner_id=TEST_USER.id)
    identity.add_member(ws.id, other.id, "member")
    own_documents(identity, "shared_doc")

    project = session_manager.create_session(owner_id=TEST_USER.id, workspace_id=ws.id)
    attach = client.post(f"/api/v1/sessions/{project.id}/files", json={"files": ["shared_doc"]})
    assert attach.status_code == 200

    from services.gateway.api import _accessible

    assert "shared_doc" in _accessible(TEST_USER)
    assert "shared_doc" in _accessible(other)
    assert "shared_doc" not in _accessible(outsider)

    identity.remove_member(ws.id, other.id)
    assert "shared_doc" not in _accessible(other)


def test_workspace_crud_and_member_routes(identity):
    other = _other_user(identity)

    created = client.post("/api/v1/workspaces", json={"name": "New Team"})
    assert created.status_code == 200
    ws = created.json()

    listed = client.get("/api/v1/workspaces").json()["workspaces"]
    assert any(w["id"] == ws["id"] for w in listed)

    added = client.post(f"/api/v1/workspaces/{ws['id']}/members", json={"email": other.email, "role": "member"})
    assert added.status_code == 200
    assert added.json()["member"]["role"] == "member"

    members = client.get(f"/api/v1/workspaces/{ws['id']}/members").json()["members"]
    assert {m["user"]["id"] for m in members} == {TEST_USER.id, other.id}

    promoted = client.patch(f"/api/v1/workspaces/{ws['id']}/members/{other.id}", json={"role": "admin"})
    assert promoted.status_code == 200
    assert promoted.json()["member"]["role"] == "admin"

    removed = client.delete(f"/api/v1/workspaces/{ws['id']}/members/{other.id}")
    assert removed.json()["removed"] is True

    renamed = client.patch(f"/api/v1/workspaces/{ws['id']}", json={"name": "Renamed"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Renamed"

    # A non-member can't manage the workspace, and the route reports it as missing.
    from services.gateway.api import current_user

    outsider = _other_user(identity, "outsider3@example.com")
    app.dependency_overrides[current_user] = lambda: outsider
    try:
        assert client.get(f"/api/v1/workspaces/{ws['id']}").status_code == 404
        assert client.patch(f"/api/v1/workspaces/{ws['id']}", json={"name": "Hijacked"}).status_code == 404
    finally:
        app.dependency_overrides[current_user] = lambda: TEST_USER

    deleted = client.delete(f"/api/v1/workspaces/{ws['id']}")
    assert deleted.json()["deleted"] is True


def test_admin_cannot_self_escalate_to_owner_and_delete_workspace(identity):
    """An admin (not the true owner) must not be able to grant themselves the owner role and use it
    to pass the owner-only delete check — a role stored on the member table is caller-settable data,
    so authorization must key off `workspace.owner_id`, not that column."""
    from services.gateway.api import current_user

    admin = _other_user(identity, "admin-not-owner@example.com")
    ws = identity.create_workspace(name="Target", owner_id=TEST_USER.id)
    identity.add_member(ws.id, admin.id, "admin")

    app.dependency_overrides[current_user] = lambda: admin
    try:
        # Can't be granted the owner role via either mutation route.
        escalate = client.patch(f"/api/v1/workspaces/{ws.id}/members/{admin.id}", json={"role": "owner"})
        assert escalate.status_code == 400
        assert identity.get_member(ws.id, admin.id).role == "admin"

        accomplice = _other_user(identity, "accomplice@example.com")
        add_as_owner = client.post(
            f"/api/v1/workspaces/{ws.id}/members", json={"email": accomplice.email, "role": "owner"}
        )
        assert add_as_owner.status_code == 400
        assert identity.get_member(ws.id, accomplice.id) is None

        # Even if a role row somehow says "owner", delete is keyed off workspace.owner_id, not it.
        identity.members[(ws.id, admin.id)].role = "owner"
        forced_delete = client.delete(f"/api/v1/workspaces/{ws.id}")
        assert forced_delete.status_code == 403
        assert identity.get_workspace(ws.id) is not None
    finally:
        app.dependency_overrides[current_user] = lambda: TEST_USER

    # The real owner can still delete it.
    assert client.delete(f"/api/v1/workspaces/{ws.id}").json()["deleted"] is True


def test_signup_and_demo_each_get_a_personal_workspace(identity, monkeypatch):
    from services.gateway import api

    monkeypatch.setattr(api.settings.auth, "allow_signup", True)
    resp = client.post(
        "/api/v1/auth/signup", json={"email": "fresh@example.com", "password": "password123"}
    )
    assert resp.status_code == 200
    new_user = identity.get_user_by_email("fresh@example.com")
    assert len(identity.list_workspaces_for_user(new_user.id)) == 1

    monkeypatch.setattr(api.settings.auth, "allow_demo", True)
    demo_resp = client.post("/api/v1/auth/demo")
    assert demo_resp.status_code == 200
    demo_user_id = demo_resp.json()["user"]["id"]
    assert len(identity.list_workspaces_for_user(demo_user_id)) == 1
