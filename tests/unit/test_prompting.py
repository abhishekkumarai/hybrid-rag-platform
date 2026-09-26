"""Unit tests for grounded prompt assembly and compact conversation history (REC-75)."""

from contracts.session import ChatMessage
from services.retrieval.prompting import build_grounded_prompt
from services.session.manager import SessionManager


def test_history_precedes_evidence_and_question_is_last():
    prompt = build_grounded_prompt(
        "What does Epictetus say about control?",
        "[c1] Some things are within our control.",
        history="User: What does Seneca say about anger?\nAssistant: Anger is madness.",
        system_prompt="You are a classics tutor.",
    )
    i_sys = prompt.index("You are a classics tutor.")
    i_hist = prompt.index("What does Seneca say about anger?")
    i_evid = prompt.index("[c1] Some things are within our control.")
    i_q = prompt.index("Current question: What does Epictetus say about control?")
    assert i_sys < i_hist < i_evid < i_q
    assert "do not answer it again" in prompt
    assert prompt.rstrip().endswith("Answer:")


def test_prompt_without_history_has_no_history_section():
    prompt = build_grounded_prompt("q?", "[c1] text")
    assert "Earlier conversation" not in prompt


def test_conversation_context_drops_provenance_and_truncates(monkeypatch):
    mgr = SessionManager.__new__(SessionManager)
    long_answer = ("Seneca calls anger a brief madness that harms the angry most. " * 20).strip()
    messages = [
        ChatMessage(role="user", content="What does Seneca say about anger?"),
        ChatMessage(
            role="assistant",
            content=long_answer + "\n\n---\n### Verified Sources & Provenance:\n1. [doc: Page 3] > long quote",
        ),
    ]
    monkeypatch.setattr(mgr, "get_session", lambda sid: (None, messages), raising=False)
    ctx = mgr.build_conversation_context("sess", max_turns=3, max_answer_chars=120)
    assert ctx.startswith("User: What does Seneca say about anger?")
    assert "Verified Sources" not in ctx and "long quote" not in ctx
    assistant_line = ctx.splitlines()[1]
    assert assistant_line.endswith("...") and len(assistant_line) <= len("Assistant: ") + 125
