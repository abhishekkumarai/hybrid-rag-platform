"""Per-project evaluation: online score aggregation and offline golden-set runs.

A project is a backend `ChatSession`: its `files` scope retrieval and its `parameters` are the settings
under test. Golden sets are generated from the project's *own* indexed chunks, so the numbers describe
this project's documents and configuration — unlike `tests/eval/eval_harness.py`, which scores the
pipeline code against a fixed synthetic corpus and stays the CI regression gate.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import requests

from contracts.metrics import (
    ChatLatencyStats,
    ConversationStats,
    GoldenQueryResult,
    GoldenQuestion,
    ProjectEvalRun,
    ProjectEvalSummary,
    ProjectObservability,
    QueryTelemetry,
    TurnEvalPoint,
)
from contracts.retrieval import SearchQuery
from contracts.session import ChatSession, Conversation
from services.common.doc_scope import matches_doc_scope
from services.common.logger import get_logger
from services.common.ollama_options import no_think

logger = get_logger("evaluation.project")

# Resolved from this file (not CWD), matching bm25_store.py.
EVAL_DIR = Path(__file__).resolve().parents[2] / "data" / "eval"
MIN_CHUNK_WORDS = 25


# --------------------------------------------------------------------------- online summary


def load_session_telemetry(
    session_id: str,
    in_memory: Sequence[QueryTelemetry],
    redis_host: str | None = None,
    redis_port: int | None = None,
) -> tuple[list[QueryTelemetry], dict[str, float]]:
    """Returns (records oldest-first, {query_id: llm_judge_score}). Redis wins when reachable."""
    records: list[QueryTelemetry] = []
    judge: dict[str, float] = {}
    if redis_host and redis_port:
        try:
            import redis

            r_client = redis.Redis(host=redis_host, port=redis_port, socket_timeout=1.0, decode_responses=True)
            for raw in reversed(r_client.lrange(f"rag:telemetry:session:{session_id}", 0, -1)):
                try:
                    records.append(QueryTelemetry.model_validate_json(raw))
                except Exception:
                    continue
            judge = {k: float(v) for k, v in r_client.hgetall(f"rag:eval:judge:{session_id}").items()}
        except Exception as exc:
            logger.warning(f"Redis unavailable for project eval summary, using in-memory history: {exc}")
            records = []
    if not records:
        records = [t for t in in_memory if t.session_id == session_id]
        records.sort(key=lambda t: t.timestamp)
    return records, judge


def in_conversation(
    records: Sequence[QueryTelemetry], conversation_id: str, default_conversation_id: str | None
) -> list[QueryTelemetry]:
    """A chat's records. Records from before IRA-56 carry no thread; they belong to the project's first
    (default) thread, which held all of a project's history before multi-thread chats (IRA-24)."""
    return [t for t in records if (t.conversation_id or default_conversation_id) == conversation_id]


def _latency_stats(records: Sequence[QueryTelemetry]) -> ChatLatencyStats:
    if not records:
        return ChatLatencyStats()

    def avg(values: list[float]) -> float:
        return round(sum(values) / len(values), 2) if values else 0.0

    answered = [t for t in records if not t.refused]
    return ChatLatencyStats(
        queries=len(records),
        refusals=len(records) - len(answered),
        avg_total_ms=avg([t.total_ms for t in records]),
        avg_retrieval_ms=avg([t.dense_ms + t.sparse_ms + t.fusion_ms + t.rerank_ms for t in records]),
        avg_ttft_ms=avg([t.llm_ttft_ms for t in answered if t.llm_ttft_ms > 0]),
        avg_generation_ms=avg([t.llm_gen_ms for t in answered if t.llm_gen_ms > 0]),
        avg_tokens_per_sec=avg([t.tokens_per_sec for t in answered if t.tokens_per_sec > 0]),
        avg_top_score=round(sum(t.top_score for t in records) / len(records), 4),
        last_query_at=max(t.timestamp for t in records),
    )


def summarize_observability(
    session_id: str,
    records: Sequence[QueryTelemetry],
    conversations: Sequence[Conversation],
    conversation_id: str | None = None,
    recent_n: int = 20,
) -> ProjectObservability:
    """Per-chat latency/volume rows for every thread, plus totals and recent queries for the scope
    (one chat when `conversation_id` is given, else the whole project)."""
    default_id = conversations[0].id if conversations else None
    rows = []
    for conv in conversations:
        stats = _latency_stats(in_conversation(records, conv.id, default_id))
        rows.append(ConversationStats(conversation_id=conv.id, title=conv.title, **stats.model_dump()))
    rows.sort(key=lambda r: (r.queries, r.last_query_at or 0), reverse=True)
    scoped = in_conversation(records, conversation_id, default_id) if conversation_id else list(records)
    return ProjectObservability(
        session_id=session_id,
        conversation_id=conversation_id,
        totals=_latency_stats(scoped),
        conversations=rows,
        recent=sorted(scoped, key=lambda t: t.timestamp, reverse=True)[:recent_n],
    )


def summarize_project(
    session_id: str,
    records: Sequence[QueryTelemetry],
    judge: dict[str, float],
    weakest_n: int = 5,
    conversation_id: str | None = None,
) -> ProjectEvalSummary:
    points: list[TurnEvalPoint] = []
    for t in records:
        if t.eval is None:
            continue
        ev = t.eval.model_copy()
        if ev.llm_judge_groundedness is None and t.query_id in judge:
            ev.llm_judge_groundedness = judge[t.query_id]
        points.append(TurnEvalPoint(query_id=t.query_id, query_text=t.query_text, timestamp=t.timestamp, eval=ev))

    def mean(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 4) if values else None

    grounded_points = [p for p in points if p.eval.answer_sentences > 0]
    judged = [p.eval.llm_judge_groundedness for p in points if p.eval.llm_judge_groundedness is not None]
    refusals = sum(1 for t in records if t.refused)
    return ProjectEvalSummary(
        session_id=session_id,
        conversation_id=conversation_id,
        turns=len(records),
        answered=len(points),
        refusal_rate=round(refusals / len(records), 4) if records else 0.0,
        mean_groundedness=mean([p.eval.groundedness for p in grounded_points]),
        mean_context_relevance=mean([p.eval.context_relevance for p in points]),
        mean_citation_validity=mean([p.eval.citation_validity for p in points]),
        mean_llm_judge=mean(judged),
        judged_turns=len(judged),
        trend=points,
        weakest=sorted(grounded_points, key=lambda p: p.eval.groundedness)[:weakest_n],
    )


# --------------------------------------------------------------------------- golden set


def project_chunks(corpus_chunks: Sequence[dict[str, Any]], files: Sequence[str]) -> list[dict[str, Any]]:
    """The project's indexed chunks that carry enough text to ask a question about."""
    scope = set(files)
    return [
        c for c in corpus_chunks
        if matches_doc_scope(c.get("doc_id"), scope) and len(str(c.get("text", "")).split()) >= MIN_CHUNK_WORDS
    ]


def _files_fingerprint(files: Sequence[str]) -> str:
    return hashlib.sha256("\n".join(sorted(files)).encode("utf-8")).hexdigest()[:12]


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip().rstrip(":.,;")


def heuristic_question(chunk: dict[str, Any]) -> str:
    """Fallback when no LLM is reachable: ask about the chunk's heading plus its lead phrase.

    Headings alone are often shared by several chunks (or are bare numerals like "I"), which makes
    the target ambiguous, so the chunk's own opening words are always appended."""
    headings = [_clean(h) for h in (chunk.get("headings") or [])]
    headings = [h for h in headings if len(re.sub(r"[^A-Za-z]", "", h)) >= 3]
    raw = str(chunk.get("text", ""))
    # The chunker prefixes "Section: <breadcrumb>\n\n" (services/indexing/chunker.py); drop it.
    if raw.startswith("Section: ") and "\n\n" in raw:
        raw = raw.split("\n\n", 1)[1]
    body = _clean(raw)
    # Skip a leading repeat of the heading so the lead phrase adds new terms.
    if headings and body.lower().startswith(headings[-1].lower()):
        body = body[len(headings[-1]):].lstrip(" :.-")
    lead = " ".join(re.split(r"(?<=[.!?])\s", body, maxsplit=1)[0].split()[:10]).rstrip(":.,;")
    if headings:
        topic = " ".join(headings[-1].split()[:10])
        return f'In "{topic}", what does the document say about {lead}?' if lead else (
            f"What does the document say about {topic}?"
        )
    return f"What does the document say about {lead}?"


_QUESTION_PROMPT = (
    "Write ONE specific question that is answered by the passage below and could not be answered "
    "without it. Use the passage's own key terms. Reply with the question only.\n\nPassage:\n{text}\n\nQuestion:"
)


def llm_question(chunk: dict[str, Any], model: str, ollama_url: str, timeout_s: float) -> str | None:
    try:
        resp = requests.post(
            f"{ollama_url}/api/generate",
            json={
                "model": model,
                "prompt": _QUESTION_PROMPT.format(text=str(chunk.get("text", ""))[:2000]),
                "stream": False,
                **no_think(ollama_url, model),
                "options": {"num_predict": 64, "temperature": 0.2},
            },
            timeout=timeout_s,
        )
        if not resp.ok:
            return None
        text = (resp.json().get("response") or "").strip()
        q = text.splitlines()[0].strip().strip('"') if text else ""
        return q if len(q.split()) >= 4 else None
    except Exception:
        return None


def build_golden_set(
    session: ChatSession,
    corpus_chunks: Sequence[dict[str, Any]],
    size: int,
    ollama_url: str,
    timeout_s: float = 30.0,
    use_llm: bool = True,
) -> list[GoldenQuestion]:
    """Samples `size` of the project's chunks (deterministic per project) and writes one question each."""
    chunks = project_chunks(corpus_chunks, session.files)
    rng = random.Random(session.id)
    sample = rng.sample(chunks, min(size, len(chunks)))
    golden: list[GoldenQuestion] = []
    llm_ok = use_llm
    for ch in sample:
        question = llm_question(ch, session.parameters.model, ollama_url, timeout_s) if llm_ok else None
        if question is None and llm_ok and not golden:
            # First call failed outright — assume the LLM is down rather than paying a timeout per chunk.
            llm_ok = False
        golden.append(
            GoldenQuestion(
                question=question or heuristic_question(ch),
                target_chunk_id=str(ch["id"]),
                doc_id=str(ch.get("doc_id", "")),
                page=int(ch.get("page", 1) or 1),
                source="llm" if question else "heuristic",
            )
        )
    logger.info(
        f"Golden set for {session.id}: {len(golden)} questions from {len(chunks)} eligible chunks "
        f"({sum(g.source == 'llm' for g in golden)} LLM-written)"
    )
    return golden


def _golden_path(session_id: str) -> Path:
    return EVAL_DIR / f"{session_id}_golden.json"


def _run_path(session_id: str) -> Path:
    return EVAL_DIR / f"{session_id}_last_run.json"


def load_or_build_golden_set(
    session: ChatSession,
    corpus_chunks: Sequence[dict[str, Any]],
    size: int,
    ollama_url: str,
    rebuild: bool = False,
    timeout_s: float = 30.0,
) -> list[GoldenQuestion]:
    """Cached per project; rebuilt when the project's files change so runs stay comparable otherwise."""
    path = _golden_path(session.id)
    fingerprint = _files_fingerprint(session.files)
    if path.exists() and not rebuild:
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            if cached.get("files_fingerprint") == fingerprint and cached.get("questions"):
                return [GoldenQuestion.model_validate(q) for q in cached["questions"]]
        except Exception as exc:
            logger.warning(f"Ignoring unreadable golden set {path}: {exc}")
    golden = build_golden_set(session, corpus_chunks, size, ollama_url, timeout_s=timeout_s)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"files_fingerprint": fingerprint, "questions": [g.model_dump() for g in golden]}, indent=2),
        encoding="utf-8",
    )
    return golden


# --------------------------------------------------------------------------- offline run


def _ndcg_at_k(rank: int | None, k: int) -> float:
    # Single relevant item: ideal DCG is 1, so nDCG is just the discounted gain at its rank.
    return 1.0 / math.log2(rank + 1) if rank is not None and rank <= k else 0.0


def run_golden_set(session: ChatSession, golden: Sequence[GoldenQuestion], retrieval: Any) -> ProjectEvalRun:
    """Runs every golden question through the real retrieval path with the project's own settings."""
    start = time.perf_counter()
    params = session.parameters
    results: list[GoldenQueryResult] = []
    for g in golden:
        res = retrieval.retrieve(
            SearchQuery(
                query_text=g.question,
                top_k=params.top_k,
                top_rerank=params.top_rerank,
                min_rerank_score=params.min_score_threshold,
                doc_ids=session.files or None,
                ef_search=params.hnsw_ef_search,
            )
        )
        ranked = [c.id for c in res.candidates]
        rank = ranked.index(g.target_chunk_id) + 1 if g.target_chunk_id in ranked else None
        results.append(
            GoldenQueryResult(
                question=g.question, target_chunk_id=g.target_chunk_id, rank=rank,
                top_score=res.top_score, refused=res.refused,
            )
        )

    n = len(results) or 1
    run = ProjectEvalRun(
        session_id=session.id,
        duration_ms=round((time.perf_counter() - start) * 1000, 2),
        num_questions=len(results),
        llm_generated=sum(g.source == "llm" for g in golden),
        hit_rate_at_1=round(sum(r.rank == 1 for r in results) / n, 4),
        hit_rate_at_3=round(sum(r.rank is not None and r.rank <= 3 for r in results) / n, 4),
        mrr=round(sum(1.0 / r.rank for r in results if r.rank) / n, 4),
        ndcg_at_3=round(sum(_ndcg_at_k(r.rank, 3) for r in results) / n, 4),
        refusal_rate=round(sum(r.refused for r in results) / n, 4),
        parameters=params.model_dump(),
        results=results,
    )
    logger.info(
        f"Project eval {session.id}: {run.num_questions} questions, hit@1={run.hit_rate_at_1:.2f} "
        f"hit@3={run.hit_rate_at_3:.2f} mrr={run.mrr:.3f} in {run.duration_ms:.0f}ms"
    )
    return run


def save_run(run: ProjectEvalRun) -> None:
    path = _run_path(run.session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(run.model_dump_json(indent=2), encoding="utf-8")


def load_last_run(session_id: str) -> ProjectEvalRun | None:
    path = _run_path(session_id)
    if not path.exists():
        return None
    try:
        return ProjectEvalRun.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:
        return None
