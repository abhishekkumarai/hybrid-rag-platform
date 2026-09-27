"""Unit tests for the /api/v1/models endpoint."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from services.gateway.api import app

SHOW = {
    "llama3.1:8b": {"capabilities": ["completion", "tools"], "model_info": {"general.architecture": "llama"}},
    "qwen2.5:7b": {"capabilities": ["completion"], "model_info": {"general.architecture": "qwen2"}},
    "bge-m3:latest": {"capabilities": ["embedding"], "model_info": {"general.architecture": "bert"}},
}


def test_list_models_with_mocked_ollama():
    client = TestClient(app)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "models": [
            {"name": "llama3.1:8b", "size": 4920731648, "modified_at": "2024-08-01T12:00:00Z"},
            {"name": "qwen2.5:7b", "size": 4700000000, "modified_at": "2024-08-02T12:00:00Z"},
            {"name": "bge-m3:latest", "size": 1200000000, "modified_at": "2024-08-03T12:00:00Z"},
        ]
    }

    def show(url, json=None, timeout=None):
        return MagicMock(status_code=200, json=MagicMock(return_value=SHOW[json["model"]]))

    with patch("requests.get", return_value=mock_response), patch("requests.post", side_effect=show):
        res = client.get("/api/v1/models")
        assert res.status_code == 200
        data = res.json()
        assert data["ollama_alive"] is True
        # The embedding model is installed but not offered for chat (IRA-31).
        assert [m["name"] for m in data["models"]] == ["llama3.1:8b", "qwen2.5:7b"]
        assert data["models"][0]["is_default"] is True


def test_list_models_fallback_when_ollama_unreachable():
    client = TestClient(app)
    with patch("requests.get", side_effect=Exception("Connection refused")):
        res = client.get("/api/v1/models")
        assert res.status_code == 200
        data = res.json()
        assert data["ollama_alive"] is False
        assert len(data["models"]) >= 1
        names = [m["name"] for m in data["models"]]
        assert data["default_model"] in names
        assert any(m["is_default"] for m in data["models"])
