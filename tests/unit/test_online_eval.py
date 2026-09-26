"""Unit tests for online per-turn evaluation (REC-72)."""

import random
from unittest.mock import MagicMock, patch

from contracts.metrics import QueryTelemetry, RetrievalEvalScores
from contracts.retrieval import Candidate, Citation
from services.evaluation.online import (
    groundedness,
    maybe_schedule_llm_judge,
    parse_judge_score,
    score_turn,
)

CONTEXT = (
    "The RTX 3050 laptop GPU has 6 GB of VRAM. Qdrant serves dense vectors with HNSW indexing, "
    "while BM25s provides sparse lexical retrieval fused by reciprocal rank fusion."
)


def _cand(text: str = CONTEXT, score: float = 0.8) -> Candidate:
    return Candidate(id="c1", doc_id="spec_12345678", page=1, bbox=(10.0, 10.0, 200.0, 60.0),
                     text=text, rrf_score=0.5, rerank_score=score)


def _cit(bbox=(10.0, 10.0, 200.0, 60.0), page: int = 1) -> Citation:
    return Citation(doc_id="spec_12345678", page=page, bbox=bbox, snippet="x", formatted_badge="[x]")


def test_grounded_answer_scores_higher_than_ungrounded():
    grounded, n = groundedness("The RTX 3050 laptop GPU has 6 GB of VRAM.", [CONTEXT])
    ungrounded, _ = groundedness("Pinecone hosts serverless embeddings on managed Kubernetes clusters.", [CONTEXT])
    assert n == 1
    assert grounded == 1.0
    assert ungrounded == 0.0


def test_short_fragments_are_not_scored():
    score, n = groundedness("Sure! Sources:", [CONTEXT])
    assert n == 0 and score == 0.0


def test_score_turn_combines_signals_and_flags_bad_citations():
    scores = score_turn(
        "Qdrant serves dense vectors with HNSW indexing.",
        [_cand(score=0.9), _cand(score=0.5)],
        [_cit(), _cit(bbox=(0.0, 0.0, 0.0, 0.0))],
        crag_status="CONFIDENT",
    )
    assert scores.context_relevance == 0.7
    assert scores.groundedness == 1.0
    assert scores.citation_validity == 0.5
    assert scores.passages_used == 2
    assert scores.crag_status == "CONFIDENT"


def test_old_telemetry_records_without_eval_still_parse():
    old = '{"query_id": "q1", "query_text": "hi", "total_ms": 5.0, "timestamp": 1.0}'
    assert QueryTelemetry.model_validate_json(old).eval is None


def test_parse_judge_score():
    assert parse_judge_score("0.85") == 0.85
    assert parse_judge_score("Score: 1") == 1.0
    assert parse_judge_score("I think 7/10") is None


def test_llm_judge_sampling_and_update():
    tel = QueryTelemetry(query_text="q", session_id="sess_1", eval=RetrievalEvalScores())
    # sample_rate 0 never schedules
    assert maybe_schedule_llm_judge(tel, "answer", [_cand()], model="m", ollama_url="http://x",
                                    sample_rate=0.0) is None
    resp = MagicMock(ok=True)
    resp.json.return_value = {"response": "0.9"}
    with patch("services.evaluation.online.requests.post", return_value=resp):
        t = maybe_schedule_llm_judge(tel, "answer", [_cand()], model="m", ollama_url="http://x",
                                     sample_rate=1.0, rng=random.Random(0))
        assert t is not None
        t.join(timeout=5)
    assert tel.eval.llm_judge_groundedness == 0.9


def test_inline_citations_and_meta_words_do_not_sink_groundedness():
    """REC-75 follow-up: a correctly cited answer must not score as ungrounded because of the
    copied `[doc_id: Page n]` provenance tokens or words like 'excerpts'/'mentions'."""
    ctx = ["Marcus Aurelius wrote that all things die. Not just people but kingdoms and ideas eventually."]
    cited = (
        "Marcus Aurelius mentions this in several excerpts. He notes that all things die "
        "(Source [the_daily_stoic_5cfc645e: Page 12]). Not just people but kingdoms die eventually."
    )
    score, n = groundedness(cited, ctx)
    # The pure meta sentence ("mentions this in several excerpts") has no checkable claim and is skipped.
    assert n == 2 and score == 1.0
    fabricated, _ = groundedness("Pinecone hosts serverless embeddings on Kubernetes [doc_x: Page 1].", ctx)
    assert fabricated == 0.0
