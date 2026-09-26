"""Online (per-turn, reference-free) evaluation of retrieval and answer quality.

Every answered chat turn gets cheap heuristic scores inline; a configurable sample is additionally
graded by an LLM judge in a background thread so it never delays the answer or fights generation
for VRAM on the request path.
"""

from __future__ import annotations

import random
import re
import threading
from collections.abc import Sequence

import requests

from contracts.metrics import QueryTelemetry, RetrievalEvalScores
from contracts.retrieval import Candidate, Citation
from services.common.logger import get_logger

logger = get_logger("evaluation.online")

_STOPWORDS = frozenset(
    """a an and are as at be been but by can could did do does for from had has have he her his how
    i if in into is it its may might more most no not of on or our she should so such than that the
    their them then there these they this those to was we were what when where which while who why
    will with would you your also based according provided context document documents answer
    excerpt excerpts passage passages source sources section sections text quote quotes quoted
    mention mentions mentioned note notes noted state states stated say says said several""".split()
)
# Inline citations the model copies from the prompt ("[doc_id: Page 12]", "(Source [...])") are
# provenance, not claims; their long id tokens never occur in passage text and would sink the score.
_INLINE_CITATION = re.compile(r"\(\s*(?:source|sources|see)?[^()]*\[[^\]]*\][^()]*\)|\[[^\]]*\]", re.IGNORECASE)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_TOKEN = re.compile(r"[a-z0-9][a-z0-9_.%-]*")
# A sentence counts as supported when this share of its content words appears in the context.
SUPPORT_THRESHOLD = 0.6
MIN_CONTENT_WORDS = 3


def _content_words(text: str) -> list[str]:
    tokens = (t.strip(".") for t in _TOKEN.findall(text.lower()))
    return [t for t in tokens if len(t) > 2 and t not in _STOPWORDS]


def groundedness(answer: str, context_texts: Sequence[str]) -> tuple[float, int]:
    """Returns (share of substantive answer sentences supported by the context, sentences scored)."""
    context_vocab = set()
    for text in context_texts:
        context_vocab.update(_content_words(text))
    scored = supported = 0
    for sentence in _SENTENCE_SPLIT.split(_INLINE_CITATION.sub(" ", answer or "")):
        words = _content_words(sentence)
        if len(words) < MIN_CONTENT_WORDS:
            continue  # greetings, headings, "Sources:" lines carry no checkable claim
        scored += 1
        if sum(w in context_vocab for w in words) / len(words) >= SUPPORT_THRESHOLD:
            supported += 1
    return (supported / scored if scored else 0.0), scored


def citation_validity(citations: Sequence[Citation]) -> float:
    """Share of citations that can actually be rendered as visual provenance."""
    if not citations:
        return 0.0
    valid = 0
    for c in citations:
        x0, y0, x1, y1 = c.bbox
        if c.doc_id and c.page >= 1 and x1 > x0 and y1 > y0:
            valid += 1
    return valid / len(citations)


def score_turn(
    answer: str,
    candidates: Sequence[Candidate],
    citations: Sequence[Citation],
    crag_status: str | None = None,
) -> RetrievalEvalScores:
    """Heuristic, reference-free scores for one answered turn. Pure and fast (no model calls)."""
    rerank_scores = [min(max(c.rerank_score, 0.0), 1.0) for c in candidates]
    grounded, n_sentences = groundedness(answer, [c.text for c in candidates])
    return RetrievalEvalScores(
        context_relevance=round(sum(rerank_scores) / len(rerank_scores), 4) if rerank_scores else 0.0,
        groundedness=round(grounded, 4),
        citation_validity=round(citation_validity(citations), 4),
        answer_sentences=n_sentences,
        passages_used=len(candidates),
        crag_status=crag_status,
    )


_JUDGE_PROMPT = (
    "You are grading a retrieval-augmented answer. Using ONLY the context, rate how fully the "
    "answer's claims are supported by it, from 0.0 (unsupported / contradicted) to 1.0 (every claim "
    "supported). Reply with the number only.\n\nContext:\n{context}\n\nAnswer:\n{answer}\n\nScore:"
)
_FLOAT = re.compile(r"(?<![\d.])(0(?:\.\d+)?|1(?:\.0+)?)(?![\d.])")


def parse_judge_score(text: str) -> float | None:
    m = _FLOAT.search(text or "")
    return float(m.group(1)) if m else None


def maybe_schedule_llm_judge(
    telemetry: QueryTelemetry,
    answer: str,
    candidates: Sequence[Candidate],
    *,
    model: str,
    ollama_url: str,
    sample_rate: float,
    timeout_s: float = 60.0,
    redis_host: str | None = None,
    redis_port: int | None = None,
    rng: random.Random | None = None,
) -> threading.Thread | None:
    """With probability `sample_rate`, grades the turn with an LLM judge in a daemon thread.

    The score is written onto `telemetry.eval` (the same object the in-memory tracker holds) and
    to Redis hash `rag:eval:judge:{session_id}` keyed by query_id, which the per-project summary
    merges in. Failures are logged and dropped — the judge is best-effort by design."""
    if telemetry.eval is None or sample_rate <= 0 or not answer.strip() or not candidates:
        return None
    if (rng or random).random() >= sample_rate:
        return None

    context = "\n\n".join(c.text for c in candidates)[:6000]
    prompt = _JUDGE_PROMPT.format(context=context, answer=answer[:2000])

    def _run() -> None:
        try:
            resp = requests.post(
                f"{ollama_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": 8, "temperature": 0.0},
                },
                timeout=timeout_s,
            )
            score = parse_judge_score(resp.json().get("response", "")) if resp.ok else None
            if score is None:
                logger.info(f"LLM judge gave no parseable score for query {telemetry.query_id[:8]}")
                return
            telemetry.eval.llm_judge_groundedness = score
            logger.info(f"LLM judge: query {telemetry.query_id[:8]} groundedness={score:.2f}")
            if redis_host and redis_port and telemetry.session_id:
                import redis

                r_client = redis.Redis(host=redis_host, port=redis_port, socket_timeout=1.0)
                r_client.hset(f"rag:eval:judge:{telemetry.session_id}", telemetry.query_id, score)
        except Exception as exc:
            logger.warning(f"LLM judge failed for query {telemetry.query_id[:8]}: {exc}")

    thread = threading.Thread(target=_run, name="llm-judge", daemon=True)
    thread.start()
    return thread
