"""Default grounding persona and prompt fitting (IRA-18)."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from contracts.chat import ChatTurnRequest
from services.gateway.api import app, settings
from services.gateway.chat_pipeline import ChatPipeline, fit_prompt
from tests.unit.test_chat_pipeline_contract import _coordinator, _ollama, _retrieval

client = TestClient(app)
DEFAULT = settings.generation.default_system_prompt


def _prompt_sent(mode: str, system_prompt: str | None) -> str:
    pipeline = ChatPipeline(
        retrieval=_retrieval(refused=False, with_graph=mode == "graph"), coordinator=_coordinator(refused=False),
        session_manager=MagicMock(), telemetry=MagicMock(), settings=settings,
    )
    pipeline.sessions.build_conversation_context.return_value = ""
    pipeline.sessions.reformulate_query.side_effect = lambda q, _sid: q
    req = ChatTurnRequest(query="What GPU does it use?", session_id="s1", model="llama3.2:3b", mode=mode,
                          system_prompt=system_prompt)
    with patch("services.gateway.chat_pipeline.requests.post", return_value=_ollama()) as post:
        list(pipeline.run(req, stream_llm=False))
    return post.call_args.kwargs["json"]["prompt"]


def test_default_persona_is_configured_and_strict():
    assert "ONLY source of truth" in DEFAULT
    assert "NEVER invent" in DEFAULT
    assert len(DEFAULT) / 3.5 < 400  # stays a small slice of the 8K window


@pytest.mark.parametrize("mode", ["direct", "graph", "agentic"])
def test_project_without_persona_gets_default(mode):
    prompt = _prompt_sent(mode, None)
    assert prompt.startswith(f"System Persona & Directives:\n{DEFAULT}")


@pytest.mark.parametrize("mode", ["direct", "graph", "agentic"])
def test_custom_persona_replaces_default(mode):
    prompt = _prompt_sent(mode, "You are a strict SEC auditor.")
    assert "You are a strict SEC auditor." in prompt
    assert DEFAULT not in prompt


def test_default_prompt_endpoint():
    assert client.get("/api/v1/prompts/default").json() == {"system_prompt": DEFAULT}


def test_fit_prompt_keeps_persona_and_question():
    prompt = "PERSONA\n\n" + "evidence " * 2000 + "\n\nCurrent question: what?\nAnswer:"
    fitted = fit_prompt(prompt, 1000)
    assert len(fitted) <= 1000
    assert fitted.startswith("PERSONA")
    assert fitted.endswith("Current question: what?\nAnswer:")
    assert "[Context truncated" in fitted


def test_fit_prompt_is_noop_when_it_fits():
    assert fit_prompt("short", 100) == "short"
