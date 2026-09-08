"""Agentic Multi-Hop Retrieval Coordinator with CRAG Reflection."""

import time

from contracts.agent import (
    AgentStep,
    CRAGAssessment,
    DecompositionPlan,
)
from contracts.compactor import CompactedContext
from contracts.graph import GraphRAGResponse
from contracts.retrieval import Candidate, Citation, SearchQuery
from services.common.logger import get_logger
from services.graph.traversal import GraphTraverser
from services.retrieval.compactor import ContextCompactor
from services.retrieval.crag import CRAGEvaluator
from services.retrieval.decomposer import QueryDecomposer
from services.retrieval.reranker import FlashRankReranker
from services.retrieval.service import RetrievalService

logger = get_logger("agentic_coordinator")


class AgenticCoordinator:
    """Coordinates autonomous multi-hop query decomposition, retrieval, CRAG reflection, and synthesis."""

    def __init__(
        self,
        retrieval_service: RetrievalService,
        decomposer: QueryDecomposer | None = None,
        crag_evaluator: CRAGEvaluator | None = None,
        reranker: FlashRankReranker | None = None,
        graph_traverser: GraphTraverser | None = None,
        compactor: ContextCompactor | None = None,
    ) -> None:
        self.retrieval = retrieval_service
        ollama_url = getattr(retrieval_service, "ollama_url", "http://127.0.0.1:11434")
        self.decomposer = decomposer or QueryDecomposer(ollama_url=ollama_url)
        self.crag = crag_evaluator or CRAGEvaluator()
        self.reranker = reranker or getattr(retrieval_service, "reranker", None)

        ret_traverser = getattr(retrieval_service, "traverser", None)
        self.traverser = (
            graph_traverser
            if graph_traverser is not None
            else (ret_traverser if isinstance(ret_traverser, GraphTraverser) else None)
        )

        ret_compactor = getattr(retrieval_service, "compactor", None)
        self.compactor = (
            compactor
            if compactor is not None
            else (
                ret_compactor
                if isinstance(ret_compactor, ContextCompactor)
                else ContextCompactor()
            )
        )
        self.last_graph_response: GraphRAGResponse | None = None
        self.last_compacted_context: CompactedContext | None = None

    def run_plan(
        self,
        query: str,
        top_k: int = 20,
        top_rerank: int = 6,
        force_multi_hop: bool = False,
        enable_graph: bool = True,
        enable_compression: bool = True,
        context_budget: int = 3072,
        doc_ids: list[str] | None = None,
    ) -> tuple[list[Candidate], list[Citation], list[AgentStep], DecompositionPlan, CRAGAssessment, bool]:
        """Executes full agentic loop: decompose -> sub-retrievals -> CRAG reflection -> cross-rerank.

        Returns:
            (candidates, citations, steps, decomposition_plan, crag_assessment, is_refused)
        """
        start_time = time.perf_counter()
        steps: list[AgentStep] = []

        # 1. Query Decomposition
        decomp_plan = self.decomposer.decompose(query, force_multi_hop=force_multi_hop)
        sub_queries = [sq.query_text for sq in decomp_plan.sub_queries]
        steps.append(
            AgentStep(
                step_type="decomposition",
                step_index=1,
                title="Query Decomposition",
                detail=(
                    f"Decomposed query into {len(sub_queries)} sub-queries"
                    if decomp_plan.is_multi_hop
                    else "Identified single-hop targeted query"
                ),
                data={"sub_queries": sub_queries, "is_multi_hop": decomp_plan.is_multi_hop},
            )
        )

        # 2. Multi-Hop Sub-Retrievals
        all_candidates_map: dict[str, Candidate] = {}
        for idx, sq in enumerate(decomp_plan.sub_queries):
            hop_num = idx + 1
            logger.info(f"Executing Hop {hop_num}/{len(decomp_plan.sub_queries)}: '{sq.query_text}'")
            sub_res = self.retrieval.retrieve(
                SearchQuery(query_text=sq.query_text, top_k=top_k, top_rerank=top_rerank, doc_ids=doc_ids)
            )

            for cand in sub_res.candidates:
                score = cand.rerank_score if cand.rerank_score > 0 else cand.rrf_score
                if cand.id not in all_candidates_map or score > (all_candidates_map[cand.id].rerank_score or all_candidates_map[cand.id].rrf_score):
                    all_candidates_map[cand.id] = cand

            steps.append(
                AgentStep(
                    step_type="sub_retrieval",
                    step_index=len(steps) + 1,
                    title=f"Sub-Query Retrieval (Hop {hop_num})",
                    detail=f"Target: '{sq.query_text}' -> Found {len(sub_res.candidates)} candidates (top score: {sub_res.top_score:.4f})",
                    data={
                        "hop": hop_num,
                        "query": sq.query_text,
                        "candidates_count": len(sub_res.candidates),
                        "top_score": sub_res.top_score,
                    },
                )
            )

        merged_candidates = list(all_candidates_map.values())

        # 3. CRAG Reflection & Evaluation
        crag_assessment = self.crag.evaluate(query, merged_candidates)

        if crag_assessment.status == "AMBIGUOUS" and crag_assessment.reformulated_query:
            logger.info(f"CRAG triggered corrective secondary hop: '{crag_assessment.reformulated_query}'")
            steps.append(
                AgentStep(
                    step_type="crag_reflection",
                    step_index=len(steps) + 1,
                    title="Corrective RAG (CRAG) Reflection",
                    detail=f"Initial retrieval ambiguous (score: {crag_assessment.top_score:.4f}). Reformulated to: '{crag_assessment.reformulated_query}'",
                    data={
                        "status": crag_assessment.status,
                        "top_score": crag_assessment.top_score,
                        "reformulated_query": crag_assessment.reformulated_query,
                    },
                )
            )

            # Execute corrective retrieval hop
            corr_res = self.retrieval.retrieve(
                SearchQuery(query_text=crag_assessment.reformulated_query, top_k=top_k, top_rerank=top_rerank, doc_ids=doc_ids)
            )
            for cand in corr_res.candidates:
                score = cand.rerank_score if cand.rerank_score > 0 else cand.rrf_score
                if cand.id not in all_candidates_map or score > (all_candidates_map[cand.id].rerank_score or all_candidates_map[cand.id].rrf_score):
                    all_candidates_map[cand.id] = cand
            merged_candidates = list(all_candidates_map.values())

        elif crag_assessment.status == "REFUSE":
            steps.append(
                AgentStep(
                    step_type="crag_reflection",
                    step_index=len(steps) + 1,
                    title="Corrective RAG (CRAG) Reflection",
                    detail=f"Retrieval confidence ({crag_assessment.top_score:.4f}) below refusal cutoff. Refusing to hallucinate.",
                    data={"status": "REFUSE", "top_score": crag_assessment.top_score},
                )
            )
            return [], [], steps, decomp_plan, crag_assessment, True
        else:
            steps.append(
                AgentStep(
                    step_type="crag_reflection",
                    step_index=len(steps) + 1,
                    title="Corrective RAG (CRAG) Reflection",
                    detail=f"Candidates verified CONFIDENT (score: {crag_assessment.top_score:.4f}). Proceeding to synthesis.",
                    data={"status": "CONFIDENT", "top_score": crag_assessment.top_score},
                )
            )

        # 3.5 GraphRAG Relational Traversal (Phase 13)
        if enable_graph and self.traverser:
            graph_res = self.traverser.query_graph(query)
            self.last_graph_response = graph_res
            if graph_res.relations:
                steps.append(
                    AgentStep(
                        step_type="graph_traversal",
                        step_index=len(steps) + 1,
                        title="GraphRAG Relational Traversal",
                        detail=(
                            f"Discovered {len(graph_res.relations)} relational facts and "
                            f"{len(graph_res.connected_chunk_ids)} connected chunks across documents"
                        ),
                        data={
                            "entities": [e.name for e in graph_res.matched_entities],
                            "relations_count": len(graph_res.relations),
                            "subgraph_text": graph_res.subgraph_text,
                        },
                    )
                )

        # 4. Global FlashRank Cross-Encoder Re-ranking
        final_candidates, citations, refused = self.reranker.rerank(
            query=query,
            candidates=merged_candidates,
            top_n=top_rerank,
        )

        top_score = final_candidates[0].rerank_score if final_candidates else 0.0
        steps.append(
            AgentStep(
                step_type="rerank",
                step_index=len(steps) + 1,
                title="Unified Cross-Encoder Reranking",
                detail=f"Reranked {len(merged_candidates)} merged candidates down to top {len(final_candidates)} (top score: {top_score:.4f})",
                data={"merged_count": len(merged_candidates), "final_count": len(final_candidates), "top_score": top_score},
            )
        )

        # 5. Contextual Token Budget Compactor (Phase 14)
        if enable_compression and self.compactor and final_candidates:
            comp_res = self.compactor.compress_candidates(
                query=query,
                candidates=final_candidates,
                budget_tokens=context_budget,
            )
            self.last_compacted_context = comp_res
            steps.append(
                AgentStep(
                    step_type="compaction",
                    step_index=len(steps) + 1,
                    title="Contextual Token Budget Compaction",
                    detail=(
                        f"Compacted {comp_res.total_original_tokens} tokens down to {comp_res.total_compressed_tokens} "
                        f"tokens (ratio {comp_res.overall_compression_ratio:.2f}, "
                        f"pruned {comp_res.pruned_table_columns_count} table cols, "
                        f"deduped {comp_res.deduplicated_sentences_count} sents)"
                    ),
                    data={
                        "original_tokens": comp_res.total_original_tokens,
                        "compressed_tokens": comp_res.total_compressed_tokens,
                        "ratio": comp_res.overall_compression_ratio,
                        "dropped": comp_res.dropped_chunks_count,
                    },
                )
            )

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.info(f"Agentic plan completed in {elapsed_ms:.1f}ms with {len(steps)} steps")

        return final_candidates, citations, steps, decomp_plan, crag_assessment, refused

    def build_agentic_prompt(
        self,
        query: str,
        candidates: list[Candidate],
        decomp_plan: DecompositionPlan,
        history_context: str = "",
        graph_context: str = "",
        compacted_context: CompactedContext | None = None,
    ) -> str:
        """Constructs an expert multi-hop comparative prompt with GraphRAG and compaction support."""
        if compacted_context and compacted_context.formatted_prompt_context:
            context_blocks = compacted_context.formatted_prompt_context
        else:
            context_blocks = "\n\n".join([f"[{c.id}] {c.text}" for c in candidates])

        evidence_section = ""
        if graph_context:
            evidence_section += f"{graph_context}\n\n"
        evidence_section += f"Retrieved Document Evidence:\n{context_blocks}"

        if decomp_plan.is_multi_hop:
            sub_q_list = "\n".join([f"- {sq.query_text}" for sq in decomp_plan.sub_queries])
            prompt = (
                f"You are an expert analytical research assistant synthesizing information across multiple documents.\n\n"
                f"The user's question was decomposed into these core sub-goals:\n{sub_q_list}\n\n"
                f"{evidence_section}\n\n"
                f"{f'Previous Conversation:\n{history_context}\n\n' if history_context else ''}"
                f"User Question: {query}\n\n"
                f"Instructions:\n"
                f"1. Address each sub-question clearly using the retrieved evidence.\n"
                f"2. Provide a structured comparative synthesis across the topics/documents.\n"
                f"3. Strictly base your response on the provided excerpts.\n"
                f"Comparative Synthesis:"
            )
        else:
            prompt = (
                f"{evidence_section}\n\n"
                f"{f'Previous Conversation:\n{history_context}\n\n' if history_context else ''}"
                f"Question: {query}\n"
                f"Answer truthfully based strictly on the provided context:"
            )

        return prompt
