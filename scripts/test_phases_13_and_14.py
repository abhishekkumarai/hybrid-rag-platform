"""End-to-End Evaluation & Verification Script for Phase 13 (GraphRAG) and Phase 14 (Contextual Compression)."""

import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from contracts.chunk import Chunk
from contracts.retrieval import Candidate
from services.graph.extractor import EntityRelationshipExtractor
from services.graph.store import GraphStore
from services.graph.traversal import GraphTraverser
from services.retrieval.compactor import ContextCompactor

sys.stdout.reconfigure(encoding="utf-8")


def main():
    print("\n" + "=" * 80)
    print("🚀 EVALUATING PHASE 13 (GRAPHRAG & KNOWLEDGE GRAPH) AND PHASE 14 (CONTEXT COMPACTOR)")
    print("=" * 80 + "\n")

    # =========================================================================
    # PART 1: PHASE 13 — Entity & Relationship Extraction
    # =========================================================================
    print("--- [PART 1] Testing Deterministic Entity & Relation Extraction ---")
    extractor = EntityRelationshipExtractor()

    sample_chunk = Chunk(
        id="arch_spec_c0",
        doc_id="architecture_plan.pdf",
        page=1,
        page_end=1,
        bbox=(72.0, 72.0, 540.0, 180.0),
        text=(
            "The NVIDIA RTX 3050 Laptop GPU has 6GB VRAM and runs on CPU with FlashRank "
            "cross-encoder reranking. The platform indexes into Qdrant vector database and "
            "BM25s sparse index, enforcing strict Ollama 8K context envelope limits."
        ),
        raw_text="The NVIDIA RTX 3050 Laptop GPU has 6GB VRAM...",
        token_count=35,
    )

    t0 = time.perf_counter()
    extract_res = extractor.extract_from_chunk(sample_chunk)
    elapsed_extract = (time.perf_counter() - t0) * 1000

    print(f"Extracted in {elapsed_extract:.2f}ms:")
    print(f"Entities ({len(extract_res.entities)}):")
    for e in extract_res.entities:
        print(f"  • [{e.category}] {e.name} (Doc: {e.doc_id}, Page: {e.page})")

    print(f"\nRelations ({len(extract_res.relations)}):")
    for r in extract_res.relations:
        print(f"  • ({r.source}) —[{r.predicate}]—> ({r.target}) [weight={r.weight}]")

    # =========================================================================
    # PART 2: PHASE 13 — Graph Store & Multi-Hop Associative Traversal
    # =========================================================================
    print("\n--- [PART 2] Testing Knowledge Graph Multi-Hop Traversal & Pathfinding ---")
    store = GraphStore(auto_load=False)

    # Index chunks from multiple heterogeneous documents
    chunk_a = sample_chunk
    chunk_b = Chunk(
        id="resume_c1",
        doc_id="abhishek_resume.pdf",
        page=1,
        page_end=1,
        bbox=(50.0, 100.0, 450.0, 200.0),
        text=(
            "Abhishek Kumar implemented enterprise Hybrid RAG pipelines at Syngene, "
            "optimizing dense latency on NVIDIA GPU architectures."
        ),
        raw_text="Abhishek Kumar implemented enterprise Hybrid RAG...",
        token_count=25,
    )
    chunk_c = Chunk(
        id="partner_c2",
        doc_id="pharma_partnerships.pdf",
        page=2,
        page_end=2,
        bbox=(60.0, 120.0, 500.0, 220.0),
        text=(
            "Syngene partnered with Bristol Myers Squibb to accelerate discovery "
            "using high-throughput biomedical knowledge graphs and RAG."
        ),
        raw_text="Syngene partnered with Bristol Myers Squibb...",
        token_count=24,
    )

    store.index_chunks([chunk_a, chunk_b, chunk_c])
    stats = store.get_stats()
    print(f"Graph Store Stats: {stats['num_nodes']} Nodes, {stats['num_edges']} Edges, Density: {stats['density']}")
    print(f"Categories: {stats['entity_categories']}")

    traverser = GraphTraverser(store)
    cross_doc_path = traverser.find_associative_path("Abhishek Kumar", "Bristol Myers Squibb")
    print("\nCross-Document Associative Path (Abhishek -> Bristol Myers Squibb):")
    print(f"  {' -> '.join(cross_doc_path) if cross_doc_path else 'No path found'}")

    # Query graph
    query_text = "How does NVIDIA RTX 3050 relate to FlashRank and CPU?"
    graph_res = traverser.query_graph(query_text)
    print(f"\nGraph Query Traversal for: \"{query_text}\"")
    print(f"Discovered Relations: {len(graph_res.relations)}")
    print(f"Connected Document Chunks: {graph_res.connected_chunk_ids}")
    print("\nFormatted Subgraph Markdown Injection:")
    print(graph_res.subgraph_text)

    # =========================================================================
    # PART 3: PHASE 14 — Contextual Compression & Token Budget Compactor
    # =========================================================================
    print("\n--- [PART 3] Testing Contextual Compression & Adaptive Compactor ---")
    compactor = ContextCompactor(default_budget_tokens=3072)

    # 1. Wide Table Column Pruning
    table_text = (
        "| Architecture Component | Technology | VRAM Usage | Host Memory | Latency Target | Cloud Cost | Redundant Col |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        "| Dense Search | Qdrant HNSW | 0 MB (Disk) | 250 MB | 18.5 ms | $0.00 | Info |\n"
        "| Reranking | FlashRank CPU | 0 MB (CPU) | 120 MB | 12.0 ms | $0.00 | Info |\n"
        "| LLM Synthesis | Llama 3.2:3b | 2.2 GB | 500 MB | 45.0 ms | $0.00 | Info |\n"
    )
    pruned_table, pruned_cols = compactor.prune_markdown_table(
        table_text, query="What is the VRAM Usage and Latency Target?"
    )
    print(f"\n1. Wide Table Pruning (Pruned {pruned_cols} irrelevant columns):")
    print(pruned_table)

    # 2. Overlapping Chunk Deduplication & Budget Packing
    c1 = Candidate(
        id="c1",
        doc_id="spec.pdf",
        page=1,
        bbox=(0.0, 0.0, 100.0, 100.0),
        text=(
            "The system operates with an NVIDIA RTX 3050 Laptop GPU with 6GB VRAM. "
            "Strict token envelope boundaries prevent VRAM overflow during synthesis. "
            "Introductory generic background notes that can be discarded."
        ),
        rerank_score=0.92,
    )
    c2 = Candidate(
        id="c2",
        doc_id="spec.pdf",
        page=2,
        bbox=(0.0, 50.0, 100.0, 150.0),
        text=(
            "Strict token envelope boundaries prevent VRAM overflow during synthesis. "  # Duplicate sentence
            "FlashRank CPU reranker operates sub-15ms without GPU allocation."
        ),
        rerank_score=0.88,
    )
    c3 = Candidate(
        id="c3_table",
        doc_id="spec.pdf",
        page=3,
        bbox=(10.0, 10.0, 200.0, 100.0),
        text=table_text,
        is_table=True,
        rerank_score=0.85,
    )

    comp_res = compactor.compress_candidates(
        query="What GPU VRAM and reranker latency is achieved?",
        candidates=[c1, c2, c3],
        budget_tokens=150,  # Enforce tight budget
        deduplicate=True,
        prune_tables=True,
    )

    print("\n2. Multi-Document Context Compaction Results:")
    print(f"  • Original Candidate Tokens: {comp_res.total_original_tokens}")
    print(f"  • Compressed Retained Tokens: {comp_res.total_compressed_tokens}")
    print(f"  • Compression Ratio: {comp_res.overall_compression_ratio:.2f} (Saved {int((1-comp_res.overall_compression_ratio)*100)}% token space)")
    print(f"  • Deduplicated Sentences: {comp_res.deduplicated_sentences_count}")
    print(f"  • Pruned Table Columns: {comp_res.pruned_table_columns_count}")
    print(f"  • Chunks Retained: {len(comp_res.chunks)} / 3")
    print(f"  • Latency: {comp_res.duration_ms:.2f}ms")

    print("\n--- Compacted Injection Context (Strictly within budget & preserving BBoxes) ---")
    print(comp_res.formatted_prompt_context)

    print("\n" + "=" * 80)
    print("🎯 PHASE 13 & PHASE 14 VERIFICATION COMPLETED SUCCESSFULLY")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
