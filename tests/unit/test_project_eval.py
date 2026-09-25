"""Unit tests for per-project evaluation (REC-73)."""

from unittest.mock import MagicMock

from contracts.metrics import GoldenQuestion, QueryTelemetry, RetrievalEvalScores
from contracts.retrieval import Candidate, RetrieveResponse
from contracts.session import ChatSession
from services.evaluation import project as project_eval

LONG = " ".join(f"word{i}" for i in range(40))


def _tel(qid, grounded, refused=False, sentences=2, ts=1.0):
    ev = None if refused else RetrievalEvalScores(
        groundedness=grounded, context_relevance=0.8, citation_validity=1.0, answer_sentences=sentences
    )
    return QueryTelemetry(query_id=qid, session_id="sess_a", query_text=qid, refused=refused, eval=ev, timestamp=ts)


def test_summarize_project_aggregates_and_merges_judge_scores():
    records = [_tel("q1", 0.9, ts=1), _tel("q2", 0.3, ts=2), _tel("q3", 0.0, refused=True, ts=3)]
    summary = project_eval.summarize_project("sess_a", records, judge={"q2": 0.25})
    assert summary.turns == 3 and summary.answered == 2
    assert summary.refusal_rate == round(1 / 3, 4)
    assert summary.mean_groundedness == 0.6
    assert summary.mean_llm_judge == 0.25 and summary.judged_turns == 1
    assert [p.query_id for p in summary.weakest] == ["q2", "q1"]
    assert [p.query_id for p in summary.trend] == ["q1", "q2"]


def test_in_memory_fallback_filters_by_project():
    mem = [_tel("q1", 0.9), QueryTelemetry(query_id="x", session_id="other", query_text="x")]
    records, judge = project_eval.load_session_telemetry("sess_a", mem)
    assert [r.query_id for r in records] == ["q1"] and judge == {}


def test_project_chunks_respect_scope_and_min_length():
    corpus = [
        {"id": "a1", "doc_id": "alpha_12345678", "text": LONG},
        {"id": "a2", "doc_id": "alpha_12345678", "text": "too short"},
        {"id": "b1", "doc_id": "alpha_final_87654321", "text": LONG},
    ]
    assert [c["id"] for c in project_eval.project_chunks(corpus, ["alpha.pdf"])] == ["a1"]


def test_heuristic_question_uses_heading_and_lead_and_skips_junk_headings():
    q = project_eval.heuristic_question({"headings": ["Intro", "VRAM\nBudget"], "text": "The GPU has 6 GB. More."})
    assert q == 'In "VRAM Budget", what does the document say about The GPU has 6 GB?'
    q2 = project_eval.heuristic_question({"headings": ["I"], "text": "Stoicism teaches control. Rest."})
    assert q2 == "What does the document say about Stoicism teaches control?"


def test_golden_set_cached_until_files_change(tmp_path, monkeypatch):
    monkeypatch.setattr(project_eval, "EVAL_DIR", tmp_path)
    corpus = [{"id": f"c{i}", "doc_id": "alpha_12345678", "text": LONG, "headings": [f"H{i}"]} for i in range(5)]
    sess = ChatSession(id="sess_a", files=["alpha.pdf"])
    monkeypatch.setattr(project_eval, "llm_question", lambda *a, **k: None)

    g1 = project_eval.load_or_build_golden_set(sess, corpus, size=3, ollama_url="http://x")
    assert len(g1) == 3 and all(g.source == "heuristic" for g in g1)
    monkeypatch.setattr(project_eval, "build_golden_set", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    assert project_eval.load_or_build_golden_set(sess, corpus, size=3, ollama_url="http://x") == g1


def test_run_golden_set_uses_project_settings_and_scores_ranks():
    sess = ChatSession(id="sess_a", files=["alpha.pdf"])
    sess.parameters.min_score_threshold = 0.3
    golden = [
        GoldenQuestion(question="q1", target_chunk_id="c1", doc_id="alpha"),
        GoldenQuestion(question="q2", target_chunk_id="c9", doc_id="alpha"),
    ]

    def cand(cid):
        return Candidate(id=cid, doc_id="alpha_12345678", page=1, bbox=(0, 0, 1, 1), text="t", rrf_score=0.1)

    retrieval = MagicMock()
    retrieval.retrieve.side_effect = [
        RetrieveResponse(query="q1", candidates=[cand("c1"), cand("c2")], citations=[], top_score=0.9, duration_ms=1),
        RetrieveResponse(query="q2", candidates=[cand("c2"), cand("c3"), cand("c9")], citations=[], top_score=0.5,
                         duration_ms=1),
    ]
    run = project_eval.run_golden_set(sess, golden, retrieval)
    assert [r.rank for r in run.results] == [1, 3]
    assert run.hit_rate_at_1 == 0.5 and run.hit_rate_at_3 == 1.0
    assert run.mrr == round((1 + 1 / 3) / 2, 4)
    sq = retrieval.retrieve.call_args_list[0].args[0]
    assert sq.doc_ids == ["alpha.pdf"] and sq.min_rerank_score == 0.3
