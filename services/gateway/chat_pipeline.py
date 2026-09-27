"""Single implementation of a /api/v1/chat turn (IRA-16).

Before this module the gateway carried two ~350-line copies of the same pipeline (streaming and
non-streaming) that had drifted: different refusal texts and payloads, and the non-streaming copy
stored "Error generating answer: ..." as if it were an answer. `ChatPipeline.run()` is now the only
place a turn is executed; it yields typed `contracts.chat` events that the endpoint either
serializes as SSE (`to_sse`) or folds into one JSON response (`fold_to_response`).
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any

import requests

from components.citation_formatter import CitationFormatterComponent
from contracts.agent import AgentStep
from contracts.chat import (
    AgentStepEvent,
    ChatEvent,
    ChatTurnRequest,
    DoneEvent,
    ErrorEvent,
    EvalEvent,
    ModeEvent,
    SessionEvent,
    TelemetryEvent,
    TokenEvent,
)
from contracts.metrics import QueryTelemetry, RetrievalEvalScores
from contracts.retrieval import Candidate, Citation, SearchQuery
from contracts.session import ChatMessage
from services.common.logger import get_logger
from services.evaluation.online import maybe_schedule_llm_judge, score_turn
from services.retrieval.prompting import build_grounded_prompt

logger = get_logger("gateway.chat_pipeline")

# Hard caps from the 6 GB VRAM target (CLAUDE.md, "Token budget").
_LARGE_MODEL_TAGS = ("8b", "7b", "14b", "13b", "70b")
NUM_PREDICT = 256
_CHARS_PER_TOKEN = 3.5
_TRUNCATION_NOTE = "\n\n[Context truncated to fit model context window]\n\n"


def fit_prompt(prompt: str, max_chars: int) -> str:
    """Shrinks an over-long prompt by cutting the *middle* (the evidence), never the ends.

    The head holds the persona and the tail holds the current question and the answer instruction
    (`build_grounded_prompt` puts them last). Cutting the tail, as the old code did, sent the model
    evidence with no question at all (IRA-18)."""
    if len(prompt) <= max_chars:
        return prompt
    q = prompt.rfind("Current question:")
    tail_len = len(prompt) - q if q != -1 else max_chars // 4
    tail_len = min(tail_len, max_chars // 2)
    head_len = max(max_chars - tail_len - len(_TRUNCATION_NOTE), 0)
    return prompt[:head_len] + _TRUNCATION_NOTE + prompt[len(prompt) - tail_len:]


class _Prepared:
    """Everything the generation stage needs once retrieval has produced an answerable context."""

    def __init__(self, prompt: str, candidates: list[Candidate], citations: list[Citation],
                 top_score: float, crag_status: str | None) -> None:
        self.prompt = prompt
        self.candidates = candidates
        self.citations = citations
        self.top_score = top_score
        self.crag_status = crag_status


class ChatPipeline:
    """Executes one chat turn. Collaborators are injected so the gateway keeps owning the singletons."""

    def __init__(self, *, retrieval: Any, coordinator: Any, session_manager: Any, telemetry: Any,
                 settings: Any, models: Any = None) -> None:
        self.retrieval = retrieval
        self.coordinator = coordinator
        self.sessions = session_manager
        self.telemetry = telemetry
        self.settings = settings
        self.models = models

    # ------------------------------------------------------------------ orchestration

    def run(self, req: ChatTurnRequest, *, stream_llm: bool = True) -> Iterator[ChatEvent]:
        """Yields the turn's events: session, [mode], [agent_step...], token..., [error], [eval],
        telemetry, done. `stream_llm` only changes how Ollama is called, never the event contract."""
        t_start = time.perf_counter()
        yield SessionEvent(session_id=req.session_id)

        if self.models is not None and self.models.rejects(req.model):
            yield from self._reject_model(req, t_start)
            return

        retrieval_query = self.sessions.reformulate_query(req.query, req.session_id)
        history = self.sessions.build_conversation_context(req.session_id, max_turns=3)
        self.sessions.append_message(req.session_id, ChatMessage(role="user", content=req.query))

        is_agentic = req.mode == "agentic" or (
            req.mode == "auto" and self.coordinator.decomposer.is_multi_hop_candidate(retrieval_query)
        )
        steps: list[AgentStep] = []
        sub_queries: list[str] = []
        mode_label: str | None = None
        # A project without its own persona gets the configured grounding persona (IRA-18).
        persona = req.system_prompt or self.settings.generation.default_system_prompt or None
        t_ret = time.perf_counter()

        if is_agentic:
            yield ModeEvent(mode="agentic")
            res = self.coordinator.run_plan_full(
                query=retrieval_query, top_k=req.top_k, top_rerank=req.top_rerank,
                force_multi_hop=(req.mode == "agentic"), context_budget=req.compactor_budget,
                doc_ids=req.doc_ids, ef_search=req.ef_search, min_rerank_score=req.min_score_threshold,
            )
            retrieval_ms = (time.perf_counter() - t_ret) * 1000
            steps = list(res.steps)
            sub_queries = [sq.query_text for sq in res.plan.sub_queries]
            for step in steps:
                yield AgentStepEvent(step=step)
            if res.refused:
                yield from self._refuse(
                    req, t_start, retrieval_ms, res.crag.top_score, self._threshold_refusal(req),
                    is_agentic=True, steps=steps, sub_queries=sub_queries,
                )
                return
            prompt = self.coordinator.build_agentic_prompt(
                query=req.query, candidates=res.candidates, decomp_plan=res.plan, history_context=history,
                graph_context=res.graph_response.subgraph_text if res.graph_response else "",
                compacted_context=res.compacted_context,
            )
            if persona:
                prompt = f"System Persona & Directives:\n{persona}\n\n{prompt}"
            prepared = _Prepared(
                prompt, res.candidates, res.citations,
                res.candidates[0].rerank_score if res.candidates else 0.0, res.crag.status,
            )

        elif req.mode == "graph":
            mode_label = "graph"
            yield ModeEvent(mode="graph")
            search_res, graph_res = self.retrieval.retrieve_with_graph(self._search_query(req, retrieval_query))
            retrieval_ms = (time.perf_counter() - t_ret) * 1000
            has_relations = bool(graph_res and graph_res.relations)
            if has_relations:
                step = AgentStep(
                    step_type="graph_traversal", step_index=1, title="GraphRAG Relational Traversal",
                    detail=(
                        f"Discovered {len(graph_res.relations)} relational facts and "
                        f"{len(graph_res.connected_chunk_ids)} connected chunks"
                    ),
                    data={
                        "entities": [e.name for e in graph_res.matched_entities],
                        "relations_count": len(graph_res.relations),
                        "subgraph_text": graph_res.subgraph_text,
                    },
                )
                steps.append(step)
                yield AgentStepEvent(step=step)
            if search_res.refused and not has_relations:
                yield from self._refuse(
                    req, t_start, retrieval_ms, search_res.top_score,
                    "I could not locate sufficiently relevant information in the indexed documents "
                    "or knowledge graph to answer your question with confidence.",
                    is_agentic=False, steps=steps, sub_queries=sub_queries, mode=mode_label,
                )
                return
            evidence, step = self._compact(req, retrieval_query, search_res.candidates, len(steps), trace=True)
            if step:
                steps.append(step)
                yield AgentStepEvent(step=step)
            graph_md = graph_res.subgraph_text if graph_res else ""
            prompt = build_grounded_prompt(
                req.query, f"{graph_md}\n\n{evidence}" if graph_md else evidence,
                history=history, system_prompt=persona,
                evidence_label="Relational & document context",
                task_instructions="Synthesize an accurate answer using the verified graph relations and retrieved passages.",
            )
            prepared = _Prepared(prompt, search_res.candidates, search_res.citations, search_res.top_score, None)

        else:
            search_res = self.retrieval.retrieve(self._search_query(req, retrieval_query))
            retrieval_ms = (time.perf_counter() - t_ret) * 1000
            if search_res.refused:
                yield from self._refuse(
                    req, t_start, retrieval_ms, search_res.top_score, self._threshold_refusal(req),
                    is_agentic=False, steps=steps, sub_queries=sub_queries,
                )
                return
            evidence, _ = self._compact(req, retrieval_query, search_res.candidates, 0)
            prompt = build_grounded_prompt(req.query, evidence, history=history, system_prompt=persona)
            prepared = _Prepared(prompt, search_res.candidates, search_res.citations, search_res.top_score, None)

        yield from self._generate(
            req, prepared, t_start, retrieval_ms, stream_llm=stream_llm, is_agentic=is_agentic,
            steps=steps, sub_queries=sub_queries, mode=mode_label,
        )

    # ------------------------------------------------------------------ stages

    @staticmethod
    def _search_query(req: ChatTurnRequest, retrieval_query: str) -> SearchQuery:
        return SearchQuery(
            query_text=retrieval_query, top_k=req.top_k, top_rerank=req.top_rerank,
            min_rerank_score=req.min_score_threshold, doc_ids=req.doc_ids, ef_search=req.ef_search,
        )

    @staticmethod
    def _threshold_refusal(req: ChatTurnRequest) -> str:
        return (
            "I could not locate sufficiently relevant information in the indexed documents "
            f"to answer your question with confidence (relevance cutoff threshold: {req.min_score_threshold:.2f})."
        )

    def _compact(self, req: ChatTurnRequest, retrieval_query: str, candidates: list[Candidate],
                 step_count: int, *, trace: bool = False) -> tuple[str, AgentStep | None]:
        """Packs candidates into the token budget. With `trace`, also returns a compaction AgentStep
        when anything was dropped or deduplicated (graph mode surfaces it; direct mode never has)."""
        comp = self.retrieval.compact_results(
            query=retrieval_query, candidates=candidates, budget_tokens=req.compactor_budget
        )
        evidence = comp.formatted_prompt_context or "\n\n".join(f"[{c.id}] {c.text}" for c in candidates)
        step = None
        if trace and (comp.dropped_chunks_count > 0 or comp.deduplicated_sentences_count > 0):
            step = AgentStep(
                step_type="compaction", step_index=step_count + 1, title="Contextual Token Budget Compaction",
                detail=(
                    f"Compacted {comp.total_original_tokens} -> {comp.total_compressed_tokens} "
                    f"tokens (ratio {comp.overall_compression_ratio:.2f})"
                ),
                data={"original_tokens": comp.total_original_tokens, "compressed_tokens": comp.total_compressed_tokens},
            )
        return evidence, step

    def _reject_model(self, req: ChatTurnRequest, t_start: float) -> Iterator[ChatEvent]:
        """The project's model is an embedding or reranker model (IRA-31). Fail before retrieval, and
        keep the turn out of history and telemetry: nothing was asked of a model that can answer."""
        error = (
            f"'{req.model}' is an embedding or reranker model and cannot generate answers. "
            "Choose a chat model in Project Settings."
        )
        logger.warning(f"Rejected non-chat model {req.model!r} for session {req.session_id}")
        yield ErrorEvent(error=error)
        yield TelemetryEvent(telemetry=QueryTelemetry(
            session_id=req.session_id, query_text=req.query,
            total_ms=round((time.perf_counter() - t_start) * 1000, 2),
        ))
        yield DoneEvent(error=error)

    def _refuse(self, req: ChatTurnRequest, t_start: float, retrieval_ms: float, top_score: float, message: str,
                *, is_agentic: bool, steps: list[AgentStep], sub_queries: list[str],
                mode: str | None = None) -> Iterator[ChatEvent]:
        total_ms = (time.perf_counter() - t_start) * 1000
        telemetry = QueryTelemetry(
            session_id=req.session_id, query_text=req.query, rerank_ms=round(retrieval_ms, 2),
            total_ms=round(total_ms, 2), refused=True, top_score=top_score, citations_count=0,
        )
        self.telemetry.record_query(telemetry)
        self.sessions.append_message(
            req.session_id, ChatMessage(role="assistant", content=message, latency_ms=round(total_ms, 2))
        )
        yield TokenEvent(token=message)
        yield TelemetryEvent(telemetry=telemetry)
        yield DoneEvent(
            refused=True, answer=message, top_score=top_score, is_agentic=is_agentic, mode=mode,
            agent_steps=steps, sub_queries=sub_queries,
        )

    def _num_ctx(self, req: ChatTurnRequest, prompt: str = "") -> int:
        # On the RTX 3050 6 GB target, 7B+ models get a 4K window to stay VRAM-resident.
        max_ctx = 4096 if any(tag in req.model.lower() for tag in _LARGE_MODEL_TAGS) else 8192
        # Size for the actual prompt (persona + history + evidence + question) plus the answer, not
        # just the passage budget -- the default persona alone is ~250 tokens (IRA-18).
        needed = max(req.compactor_budget + 512, int(len(prompt) / _CHARS_PER_TOKEN) + NUM_PREDICT + 64)
        return min(max(needed, 2048), max_ctx)

    def _ollama(self, req: ChatTurnRequest, prompt: str, num_ctx: int, stream: bool) -> requests.Response:
        url = f"{self.settings.hardware.ollama_base_url}/api/generate"

        def call(p: str, ctx: int) -> requests.Response:
            return requests.post(
                url,
                json={
                    "model": req.model, "prompt": p, "stream": stream,
                    "options": {"num_predict": NUM_PREDICT, "temperature": req.temperature, "num_ctx": ctx},
                },
                stream=stream,
                timeout=120,
            )

        resp = call(prompt, num_ctx)
        if resp.status_code != 200:
            logger.warning(f"Ollama returned {resp.status_code}, retrying with safe num_ctx=2048: {resp.text}")
            resp = call(fit_prompt(prompt, 4000), 2048)
        return resp

    def _generate(self, req: ChatTurnRequest, prep: _Prepared, t_start: float, retrieval_ms: float, *,
                  stream_llm: bool, is_agentic: bool, steps: list[AgentStep], sub_queries: list[str],
                  mode: str | None) -> Iterator[ChatEvent]:
        num_ctx = self._num_ctx(req, prep.prompt)
        prompt = fit_prompt(prep.prompt, int((num_ctx - 350) * _CHARS_PER_TOKEN))

        parts: list[str] = []
        token_count = 0
        ttft_ms = 0.0
        error: str | None = None
        t_llm = time.perf_counter()
        try:
            resp = self._ollama(req, prompt, num_ctx, stream_llm)
            # Ollama reports failures ("does not support generate", a crashed runner) as an `error`
            # body; reading only `response` turned them into a silent empty answer (IRA-31).
            if resp.status_code != 200:
                raise RuntimeError(_ollama_error(resp))
            if stream_llm:
                for line in resp.iter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    if chunk.get("error"):
                        raise RuntimeError(chunk["error"])
                    tok = chunk.get("response", "")
                    if tok:
                        if token_count == 0:
                            ttft_ms = (time.perf_counter() - t_llm) * 1000
                        token_count += 1
                        parts.append(tok)
                        yield TokenEvent(token=tok)
                    if chunk.get("done", False):
                        break
            else:
                body = resp.json()
                if body.get("error"):
                    raise RuntimeError(body["error"])
                text = body.get("response", "")
                if text:
                    parts.append(text)
                    yield TokenEvent(token=text)
                # Ollama reports the real generated-token count; estimate only if it is absent.
                token_count = int(body.get("eval_count") or round(len(text.split()) * 1.3))
        except Exception as exc:
            error = str(exc)
            logger.warning(f"Generation failed for session {req.session_id}: {error}")
            yield ErrorEvent(error=error)

        llm_ms = (time.perf_counter() - t_llm) * 1000
        total_ms = (time.perf_counter() - t_start) * 1000
        raw_answer = "".join(parts)
        telemetry = QueryTelemetry(
            session_id=req.session_id, query_text=req.query, rerank_ms=round(retrieval_ms, 2),
            llm_ttft_ms=round(ttft_ms, 2), llm_gen_ms=round(llm_ms, 2), total_ms=round(total_ms, 2),
            tokens_generated=token_count,
            tokens_per_sec=round(token_count / (llm_ms / 1000), 1) if llm_ms > 0 else 0.0,
            refused=False, top_score=prep.top_score, citations_count=len(prep.citations),
        )
        turn_eval = self._evaluate(telemetry, raw_answer, prep, req.model)
        self.telemetry.record_query(
            telemetry,
            redis_host=self.settings.storage.redis_host,
            redis_port=self.settings.storage.redis_port,
        )

        formatted = CitationFormatterComponent().format_response(
            raw_answer, [c.model_dump() for c in prep.citations]
        )
        # History stores the answer as streamed; the provenance lives in `citations`, which the UI
        # renders as chips. Persisting `formatted` made reloaded answers show every source twice.
        self.sessions.append_message(
            req.session_id,
            ChatMessage(
                role="assistant", content=raw_answer, citations=prep.citations, latency_ms=round(total_ms, 2),
                metadata={"eval": turn_eval.model_dump() if turn_eval else None, "query_id": telemetry.query_id},
            ),
        )

        if turn_eval:
            yield EvalEvent(scores=turn_eval)
        yield TelemetryEvent(telemetry=telemetry)
        yield DoneEvent(
            answer=formatted, raw_answer=raw_answer, citations=prep.citations, top_score=prep.top_score,
            is_agentic=is_agentic, mode=mode, agent_steps=steps, sub_queries=sub_queries, error=error,
        )

    def _evaluate(self, telemetry: QueryTelemetry, answer: str, prep: _Prepared,
                  model: str) -> RetrievalEvalScores | None:
        """Online per-turn scores (IRA-14). Runs before telemetry is recorded so the scores persist
        with it. A failed/empty generation was never answered and is not scored."""
        if not answer.strip():
            return None
        telemetry.eval = score_turn(answer, prep.candidates, prep.citations, crag_status=prep.crag_status)
        ev = self.settings.evaluation
        maybe_schedule_llm_judge(
            telemetry, answer, prep.candidates, model=model,
            ollama_url=self.settings.hardware.ollama_base_url,
            sample_rate=ev.llm_judge_sample_rate, timeout_s=ev.llm_judge_timeout_s,
            redis_host=self.settings.storage.redis_host, redis_port=self.settings.storage.redis_port,
        )
        return telemetry.eval


# ---------------------------------------------------------------------- transports


def _ollama_error(resp: requests.Response) -> str:
    try:
        return resp.json().get("error") or f"Ollama returned HTTP {resp.status_code}"
    except ValueError:
        return f"Ollama returned HTTP {resp.status_code}: {resp.text[:200]}"


def to_sse(event: ChatEvent) -> str:
    """One SSE frame, byte-compatible with the pre-IRA-16 wire format."""
    if isinstance(event, AgentStepEvent):
        data = event.step.model_dump_json()
    elif isinstance(event, EvalEvent):
        data = event.scores.model_dump_json()
    elif isinstance(event, TelemetryEvent):
        data = event.telemetry.model_dump_json()
    elif isinstance(event, DoneEvent):
        data = event.model_dump_json(exclude={"kind"}, exclude_none=True)
    else:
        data = event.model_dump_json(exclude={"kind"})
    return f"event: {event.kind}\ndata: {data}\n\n"


def fold_to_response(events: Iterator[ChatEvent]) -> dict[str, Any]:
    """Collapses a turn's events into the non-streaming /api/v1/chat JSON body."""
    session_id: str | None = None
    telemetry: QueryTelemetry | None = None
    scores: RetrievalEvalScores | None = None
    done: DoneEvent | None = None
    for ev in events:
        if isinstance(ev, SessionEvent):
            session_id = ev.session_id
        elif isinstance(ev, TelemetryEvent):
            telemetry = ev.telemetry
        elif isinstance(ev, EvalEvent):
            scores = ev.scores
        elif isinstance(ev, DoneEvent):
            done = ev
    assert done is not None and telemetry is not None, "chat pipeline ended without done/telemetry"

    body = done.model_dump(exclude={"kind"}, exclude_none=True)
    body.update(
        session_id=session_id,
        telemetry=telemetry.model_dump(),
        duration_ms=telemetry.total_ms,
        eval=scores.model_dump() if scores else None,
    )
    if done.error and not done.raw_answer:
        # Keep a human-readable answer for display, but it was never stored or scored as one.
        body["answer"] = f"Error generating answer: {done.error}"
    return body
