"""Characterization tests for /api/v1/chat (IRA-16).

Pins the observable contract of every chat path -- SSE event order and payload keys when streaming,
JSON keys when not -- across direct / graph / agentic modes, answered and refused. Written against
the pre-refactor code so the streaming/sync de-duplication can be checked for behavior drift.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from contracts.agent import AgenticRunResult, AgentStep, CRAGAssessment, DecompositionPlan, SubQuery
from contracts.graph import Entity, GraphRAGResponse, Relation
from contracts.retrieval import Candidate, Citation, RetrieveResponse
from services.gateway.api import app

client = TestClient(app)

ANSWER = "The system uses an RTX 3050 GPU with 6GB VRAM."
CAND = Candidate(
    id="chunk_1", doc_id="arch_doc", page=1, bbox=(50.0, 50.0, 200.0, 100.0), text=ANSWER, rerank_score=0.95
)
CIT = Citation(doc_id="arch_doc", page=1, bbox=(50.0, 50.0, 200.0, 100.0), snippet=ANSWER, formatted_badge="[arch_doc: 1]")


def _retrieval(refused: bool, with_graph: bool = False):
    r = MagicMock()
    res = RetrieveResponse(
        query="q", candidates=[] if refused else [CAND], citations=[] if refused else [CIT],
        refused=refused, top_score=0.05 if refused else 0.95, duration_ms=1.0,
    )
    r.retrieve.return_value = res
    graph = GraphRAGResponse(
        query="q",
        matched_entities=[Entity(name="RTX 3050")] if with_graph else [],
        relations=[Relation(source="RTX 3050", predicate="has", target="6GB VRAM", doc_id="arch_doc")] if with_graph else [],
        subgraph_text="- RTX 3050 has 6GB VRAM" if with_graph else "",
        connected_chunk_ids=["chunk_1"] if with_graph else [],
        communities=[],
        duration_ms=1.0,
    )
    r.retrieve_with_graph.return_value = (res, graph)
    comp = MagicMock(formatted_prompt_context="", dropped_chunks_count=0, deduplicated_sentences_count=0)
    r.compact_results.return_value = comp
    return r


def _coordinator(refused: bool):
    c = MagicMock()
    c.decomposer.is_multi_hop_candidate.return_value = True
    plan = DecompositionPlan(
        original_query="Compare X and Y", is_multi_hop=True,
        sub_queries=[SubQuery(query_text="X?", rationale="a", hop_index=0), SubQuery(query_text="Y?", rationale="b", hop_index=1)],
    )
    step = AgentStep(step_type="decomposition", step_index=1, title="Query Decomposition", detail="2 sub-queries")
    c.run_plan_full.return_value = AgenticRunResult(
        candidates=[] if refused else [CAND], citations=[] if refused else [CIT], steps=[step], plan=plan,
        crag=CRAGAssessment(status="REFUSE" if refused else "CONFIDENT", top_score=0.05 if refused else 0.95),
        refused=refused,
    )
    c.build_agentic_prompt.return_value = "agentic prompt"
    return c


def _ollama(answer: str = ANSWER):
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"response": answer}
    resp.iter_lines.return_value = [
        json.dumps({"response": answer, "done": False}).encode(),
        json.dumps({"response": "", "done": True}).encode(),
    ]
    return resp


def _events(body: str) -> list[tuple[str, dict]]:
    out, cur = [], None
    for line in body.splitlines():
        if line.startswith("event: "):
            cur = line[7:]
        elif line.startswith("data: "):
            out.append((cur, json.loads(line[6:])))
    return out


def _collapse(names: list[str]) -> list[str]:
    """Consecutive duplicate event names (token, agent_step) collapse to one entry."""
    return [n for i, n in enumerate(names) if i == 0 or names[i - 1] != n]


CASES = {
    # mode, refused, with_graph -> expected collapsed SSE event sequence
    "direct-answered": ("direct", False, False, ["session", "token", "eval", "telemetry", "done"]),
    "direct-refused": ("direct", True, False, ["session", "token", "telemetry", "done"]),
    "graph-answered": ("graph", False, True, ["session", "mode", "agent_step", "token", "eval", "telemetry", "done"]),
    "graph-refused": ("graph", True, False, ["session", "mode", "token", "telemetry", "done"]),
    "agentic-answered": ("agentic", False, False, ["session", "mode", "agent_step", "token", "eval", "telemetry", "done"]),
    "agentic-refused": ("agentic", True, False, ["session", "mode", "agent_step", "token", "telemetry", "done"]),
}

SYNC_ANSWERED_KEYS = {
    "answer", "raw_answer", "citations", "top_score", "refused", "duration_ms", "telemetry", "eval",
    "is_agentic", "agent_steps", "sub_queries", "session_id",
}
SYNC_REFUSED_KEYS = {"answer", "citations", "refused", "telemetry", "is_agentic", "session_id"}


def _run(case: str, stream: bool):
    mode, refused, with_graph, _ = CASES[case]
    with patch("services.gateway.api.get_services") as gs, \
         patch("services.gateway.api.get_agentic_coordinator") as gc, \
         patch("services.gateway.api.requests.post") as post:
        gs.return_value = (MagicMock(), MagicMock(), _retrieval(refused, with_graph))
        gc.return_value = _coordinator(refused)
        post.return_value = _ollama()
        r = client.post("/api/v1/chat", json={"query": "Compare X and Y", "stream": stream, "mode": mode})
    assert r.status_code == 200
    return r


@pytest.mark.parametrize("case", list(CASES))
def test_stream_event_sequence(case):
    events = _events(_run(case, stream=True).text)
    assert _collapse([n for n, _ in events]) == CASES[case][3]
    done = events[-1][1]
    refused = CASES[case][1]
    assert done["refused"] is True if refused else "answer" in done and ANSWER in done["answer"]
    assert done["is_agentic"] is (CASES[case][0] == "agentic")


@pytest.mark.parametrize("case", list(CASES))
def test_sync_response_keys(case):
    data = _run(case, stream=False).json()
    refused = CASES[case][1]
    assert (SYNC_REFUSED_KEYS if refused else SYNC_ANSWERED_KEYS) <= set(data)
    assert data["refused"] is refused
    assert data["is_agentic"] is (CASES[case][0] == "agentic")
    if not refused:
        assert ANSWER in data["answer"] and data["raw_answer"] == ANSWER
        assert data["eval"]["groundedness"] == 1.0


# --- Drift fixed by the single pipeline (IRA-16) -------------------------------------------------


@pytest.mark.parametrize("mode", ["direct", "graph", "agentic"])
def test_stream_and_sync_refusals_are_identical(mode):
    case = f"{mode}-refused"
    stream_done = _events(_run(case, stream=True).text)[-1][1]
    sync = _run(case, stream=False).json()
    assert stream_done["answer"] == sync["answer"]
    assert stream_done["agent_steps"] == sync["agent_steps"]


def test_sync_generation_failure_is_reported_not_scored():
    """The old sync path stored and scored "Error generating answer: ..." as if it were an answer."""
    with patch("services.gateway.api.get_services") as gs, \
         patch("services.gateway.api.get_agentic_coordinator") as gc, \
         patch("services.gateway.api.requests.post", side_effect=ConnectionError("ollama down")):
        gs.return_value = (MagicMock(), MagicMock(), _retrieval(refused=False))
        gc.return_value = _coordinator(refused=False)
        data = client.post("/api/v1/chat", json={"query": "What GPU?", "stream": False, "mode": "direct"}).json()
    assert data["error"] == "ollama down"
    assert data["answer"].startswith("Error generating answer")
    assert data["raw_answer"] == ""
    assert data["eval"] is None


@pytest.mark.parametrize("stream", [True, False])
def test_history_stores_answer_without_provenance_block(stream):
    """Reloaded chats render stored content plus citation chips; a stored provenance block showed
    every source twice and tripled the page height."""
    with patch("services.gateway.api.get_services") as gs, \
         patch("services.gateway.api.get_agentic_coordinator") as gc, \
         patch("services.gateway.api.requests.post", return_value=_ollama()), \
         patch("services.gateway.api.session_manager.append_message") as append:
        gs.return_value = (MagicMock(), MagicMock(), _retrieval(refused=False))
        gc.return_value = _coordinator(refused=False)
        client.post("/api/v1/chat", json={"query": "What GPU?", "stream": stream, "mode": "direct"})
    stored = append.call_args_list[-1].args[1]
    assert stored.role == "assistant"
    assert stored.content == ANSWER
    assert stored.citations == [CIT]


@pytest.mark.parametrize("stream", [True, False])
def test_non_chat_model_is_rejected_before_retrieval(stream):
    """IRA-31: an embedding/reranker model fails fast with a clear error and is never sent to Ollama."""
    retrieval = _retrieval(refused=False)
    with patch("services.gateway.api.get_services") as gs, \
         patch("services.gateway.api.get_agentic_coordinator") as gc, \
         patch("services.gateway.api.requests.post") as post, \
         patch("services.gateway.api.model_catalog.rejects", return_value=True), \
         patch("services.gateway.api.session_manager.append_message") as append:
        gs.return_value = (MagicMock(), MagicMock(), retrieval)
        gc.return_value = _coordinator(refused=False)
        r = client.post("/api/v1/chat", json={"query": "What GPU?", "stream": stream,
                                              "mode": "direct", "model": "bge-m3:latest"})
    post.assert_not_called()
    retrieval.retrieve.assert_not_called()
    append.assert_not_called()
    if stream:
        events = _events(r.text)
        assert [n for n, _ in events] == ["session", "error", "telemetry", "done"]
        assert "cannot generate answers" in events[-1][1]["error"]
    else:
        data = r.json()
        assert "cannot generate answers" in data["error"]
        assert data["answer"].startswith("Error generating answer")


@pytest.mark.parametrize("stream", [True, False])
def test_ollama_error_body_is_reported_not_blank(stream):
    """IRA-31: Ollama's `error` body used to become a silent empty answer."""
    resp = MagicMock(status_code=500)
    resp.json.return_value = {"error": '"bge-m3:latest" does not support generate'}
    with patch("services.gateway.api.get_services") as gs, \
         patch("services.gateway.api.get_agentic_coordinator") as gc, \
         patch("services.gateway.api.requests.post", return_value=resp), \
         patch("services.gateway.api.model_catalog.rejects", return_value=False):
        gs.return_value = (MagicMock(), MagicMock(), _retrieval(refused=False))
        gc.return_value = _coordinator(refused=False)
        r = client.post("/api/v1/chat", json={"query": "What GPU?", "stream": stream, "mode": "direct"})
    if stream:
        errors = [p for n, p in _events(r.text) if n == "error"]
        assert errors and "does not support generate" in errors[0]["error"]
    else:
        assert "does not support generate" in r.json()["error"]


def test_sync_token_count_uses_ollama_eval_count():
    resp = _ollama()
    resp.json.return_value = {"response": ANSWER, "eval_count": 42}
    with patch("services.gateway.api.get_services") as gs, \
         patch("services.gateway.api.get_agentic_coordinator") as gc, \
         patch("services.gateway.api.requests.post", return_value=resp):
        gs.return_value = (MagicMock(), MagicMock(), _retrieval(refused=False))
        gc.return_value = _coordinator(refused=False)
        data = client.post("/api/v1/chat", json={"query": "What GPU?", "stream": False, "mode": "direct"}).json()
    assert data["telemetry"]["tokens_generated"] == 42
