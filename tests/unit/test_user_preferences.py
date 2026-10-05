"""Per-user default chat model (IRA-56)."""

import pytest
from fastapi.testclient import TestClient

from services.gateway import api
from services.session.preferences import PreferencesStore

client = TestClient(api.app)
INSTALLED = [{"name": "llama3.2:3b", "size": 1}, {"name": "qwen3.5:4b", "size": 2}]


@pytest.fixture(autouse=True)
def _catalog(monkeypatch):
    monkeypatch.setattr(api, "prefs_store", PreferencesStore(lambda: None))
    monkeypatch.setattr(api.model_catalog, "installed", lambda: INSTALLED)
    monkeypatch.setattr(api.model_catalog, "chat_models", lambda installed=None: INSTALLED)
    monkeypatch.setattr(api.settings.hardware, "llm_model", "llama3.2:3b")


def test_default_is_the_server_model_until_the_user_picks_one():
    body = client.get("/api/v1/models").json()
    assert body["default_model"] == "llama3.2:3b" == body["system_default_model"]
    assert client.get("/api/v1/me/preferences").json() == {"default_model": None}


def test_picking_a_model_changes_the_default_and_new_projects_use_it():
    assert client.put("/api/v1/me/preferences", json={"default_model": "qwen3.5:4b"}).json()["default_model"] == "qwen3.5:4b"
    models = client.get("/api/v1/models").json()
    assert models["default_model"] == "qwen3.5:4b" and models["system_default_model"] == "llama3.2:3b"
    assert [m["name"] for m in models["models"] if m["is_default"]] == ["qwen3.5:4b"]

    project = client.post("/api/v1/sessions", json={"title": "p"}).json()
    assert project["parameters"]["model"] == "qwen3.5:4b"
    explicit = client.post("/api/v1/sessions", json={"title": "p", "parameters": {"model": "llama3.2:3b"}}).json()
    assert explicit["parameters"]["model"] == "llama3.2:3b"
    partial = client.post("/api/v1/sessions", json={"title": "p", "parameters": {"retrieval_mode": "graph"}}).json()
    assert partial["parameters"]["model"] == "qwen3.5:4b" and partial["parameters"]["retrieval_mode"] == "graph"


def test_only_installed_chat_models_are_accepted_and_null_clears():
    assert client.put("/api/v1/me/preferences", json={"default_model": "bge-m3:latest"}).status_code == 422
    client.put("/api/v1/me/preferences", json={"default_model": "qwen3.5:4b"})
    assert client.put("/api/v1/me/preferences", json={"default_model": None}).json()["default_model"] is None
    assert client.get("/api/v1/models").json()["default_model"] == "llama3.2:3b"


def test_an_uninstalled_preference_falls_back_to_the_server_default(monkeypatch):
    client.put("/api/v1/me/preferences", json={"default_model": "qwen3.5:4b"})
    remaining = [INSTALLED[0]]
    monkeypatch.setattr(api.model_catalog, "installed", lambda: remaining)
    monkeypatch.setattr(api.model_catalog, "chat_models", lambda installed=None: remaining)
    assert client.get("/api/v1/models").json()["default_model"] == "llama3.2:3b"
