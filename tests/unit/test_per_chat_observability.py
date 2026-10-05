"""Per-chat observability and evaluation inside a project (IRA-56)."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from contracts.metrics import QueryTelemetry, RetrievalEvalScores
from contracts.session import Conversation
from services.evaluation import project as project_eval
from services.gateway import api

client = TestClient(api.app)


def _tel(qid, conv, *, grounded=0.9, refused=False, total=100.0, ts=1.0, sid="sess_a"):
    ev = None if refused else RetrievalEvalScores(
        groundedness=grounded, context_relevance=0.8, citation_validity=1.0, answer_sentences=2
    )
    return QueryTelemetry(
        query_id=qid, session_id=sid, conversation_id=conv, query_text=qid, refused=refused, eval=ev,
        total_ms=total, rerank_ms=10.0, llm_gen_ms=0.0 if refused else 50.0, tokens_per_sec=0.0 if refused else 20.0,
        timestamp=ts,
    )


CONVS = [
    Conversation(id="conv_first", session_id="sess_a", title="First", created_at=1),
    Conversation(id="conv_second", session_id="sess_a", title="Second", created_at=2),
]


def test_legacy_records_without_a_thread_belong_to_the_first_chat():
    records = [_tel("old", None, ts=1), _tel("a", "conv_first", ts=2), _tel("b", "conv_second", ts=3)]
    assert [t.query_id for t in project_eval.in_conversation(records, "conv_first", "conv_first")] == ["old", "a"]
    assert [t.query_id for t in project_eval.in_conversation(records, "conv_second", "conv_first")] == ["b"]


def test_observability_rows_per_chat_and_scoped_totals():
    records = [
        _tel("a1", "conv_first", total=100, ts=1),
        _tel("a2", "conv_first", total=300, ts=2),
        _tel("b1", "conv_second", refused=True, total=40, ts=3),
    ]
    obs = project_eval.summarize_observability("sess_a", records, CONVS)
    assert obs.totals.queries == 3 and obs.totals.refusals == 1
    first = next(r for r in obs.conversations if r.conversation_id == "conv_first")
    assert first.title == "First" and first.queries == 2 and first.avg_total_ms == 200.0
    assert first.avg_tokens_per_sec == 20.0 and first.last_query_at == 2
    assert [t.query_id for t in obs.recent] == ["b1", "a2", "a1"]

    scoped = project_eval.summarize_observability("sess_a", records, CONVS, "conv_second")
    assert scoped.conversation_id == "conv_second"
    assert scoped.totals.queries == 1 and scoped.totals.refusals == 1
    assert [t.query_id for t in scoped.recent] == ["b1"]
    assert len(scoped.conversations) == 2  # the table always lists every chat


def _project_with_two_chats():
    sid = client.post("/api/v1/sessions", json={"title": "p"}).json()["id"]
    first = client.get(f"/api/v1/sessions/{sid}/conversations").json()["conversations"][0]["id"]
    second = client.post(f"/api/v1/sessions/{sid}/conversations").json()["id"]
    return sid, first, second


def test_endpoints_scope_eval_and_observability_to_one_chat():
    sid, first, second = _project_with_two_chats()
    records = [
        _tel("a", first, grounded=0.9, ts=1, sid=sid),
        _tel("b", second, grounded=0.3, ts=2, sid=sid),
        _tel("legacy", None, grounded=0.5, ts=0.5, sid=sid),
    ]
    with patch.object(api.project_eval, "load_session_telemetry", return_value=(records, {})):
        whole = client.get(f"/api/v1/sessions/{sid}/eval/summary").json()
        one = client.get(f"/api/v1/sessions/{sid}/eval/summary", params={"conversation_id": second}).json()
        default_chat = client.get(f"/api/v1/sessions/{sid}/eval/summary", params={"conversation_id": first}).json()
        obs = client.get(f"/api/v1/sessions/{sid}/observability", params={"conversation_id": second}).json()
    assert whole["turns"] == 3 and whole["conversation_id"] is None
    assert one["turns"] == 1 and one["conversation_id"] == second and one["mean_groundedness"] == 0.3
    assert default_chat["turns"] == 2  # includes the pre-IRA-56 record
    assert obs["totals"]["queries"] == 1 and [r["query_id"] for r in obs["recent"]] == ["b"]
    assert {c["conversation_id"] for c in obs["conversations"]} == {first, second}


def test_unknown_chat_is_404():
    sid, _, _ = _project_with_two_chats()
    assert client.get(f"/api/v1/sessions/{sid}/eval/summary", params={"conversation_id": "conv_nope"}).status_code == 404
    assert client.get(f"/api/v1/sessions/{sid}/observability", params={"conversation_id": "conv_nope"}).status_code == 404


def test_a_project_with_no_data_gets_empty_results_not_invented_ones(tmp_path, monkeypatch):
    monkeypatch.setattr(api.project_eval, "EVAL_DIR", tmp_path)
    sid, _, _ = _project_with_two_chats()
    with patch.object(api.project_eval, "load_session_telemetry", return_value=([], {})):
        summary = client.get(f"/api/v1/sessions/{sid}/eval/summary").json()
        obs = client.get(f"/api/v1/sessions/{sid}/observability").json()
    assert summary["turns"] == 0 and summary["trend"] == [] and summary["weakest"] == []
    assert obs["totals"]["queries"] == 0 and obs["recent"] == []
    assert client.get(f"/api/v1/sessions/{sid}/eval/run").json() is None
    run = client.post(f"/api/v1/sessions/{sid}/eval/run")
    assert run.status_code == 422 and "golden set" in run.json()["detail"]
    assert client.get(f"/api/v1/sessions/{sid}/eval/run").json() is None  # nothing fake was saved
