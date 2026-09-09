"""Unit tests for the /api/v1/models endpoint."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from services.gateway.api import app


def test_list_models_with_mocked_ollama():
    client = TestClient(app)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "models": [
            {"name": "llama3.1:8b", "size": 4920731648, "modified_at": "2024-08-01T12:00:00Z"},
            {"name": "qwen2.5:7b", "size": 4700000000, "modified_at": "2024-08-02T12:00:00Z"},
        ]
    }

    with patch("requests.get", return_value=mock_response):
        res = client.get("/api/v1/models")
        assert res.status_code == 200
        data = res.json()
        assert data["ollama_alive"] is True
        assert len(data["models"]) == 2
        assert data["models"][0]["name"] == "llama3.1:8b"
        assert data["models"][0]["is_default"] is True


def test_list_models_fallback_when_ollama_unreachable():
    client = TestClient(app)
    with patch("requests.get", side_effect=Exception("Connection refused")):
        res = client.get("/api/v1/models")
        assert res.status_code == 200
        data = res.json()
        assert data["ollama_alive"] is False
        assert len(data["models"]) >= 2
        names = [m["name"] for m in data["models"]]
        assert "llama3.1:8b" in names or "llama3.2:3b" in names
        assert any(m["is_default"] for m in data["models"])
