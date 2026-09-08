"""End-to-end live demonstration of the RAG pipeline."""

import sys
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fitz
import requests

from components.citation_formatter import CitationFormatterComponent
from contracts.document import IngestRequest
from contracts.retrieval import SearchQuery
from services.common.logger import get_logger
from services.indexing.service import IndexingService
from services.ingestion.service import IngestionService
from services.retrieval.service import RetrievalService

logger = get_logger("demo")

def main():
    # 1. Create sample PDF
    doc_dir = Path("data/documents")
    doc_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = doc_dir / "system_architecture_spec.pdf"

    doc = fitz.open()
    # Page 1
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((72, 72), "Enterprise System Architecture", fontsize=18)
    p1.insert_text(
        (72, 110),
        "The distributed platform relies on an NVIDIA GeForce RTX 3050 Laptop GPU with 6GB VRAM. "
        "PostgreSQL operates as the primary relational database on port 5432, while Qdrant serves vector queries on port 6333. "
        "The system memory is 16GB RAM and runs strictly local open-source models.",
        fontsize=11,
    )

    # Page 2
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((72, 72), "Hybrid Retrieval Performance Benchmarks", fontsize=16)
    p2.insert_text(
        (72, 110),
        "Reciprocal Rank Fusion fuses dense and sparse result sets using constant k=60 to eliminate ranking bias. "
        "FlashRank cross-encoder reranks top-20 candidates down to top-6 with a minimum refusal threshold of 0.15. "
        "BM25s provides microsecond lexical keyword lookup.",
        fontsize=11,
    )
    doc.save(str(pdf_path))
    doc.close()
    print(f"[1/5] Created sample PDF at: {pdf_path}")

    # 2. Ingest
    ingestion = IngestionService()
    ingest_res = ingestion.parse(IngestRequest(file_path=str(pdf_path)))
    print(f"[2/5] Ingested {len(ingest_res.blocks)} blocks. Probed route: {ingest_res.profile.route}")

    # 3. Index to real Qdrant & BM25s
    indexing = IndexingService(in_memory=False)
    index_res = indexing.chunk_and_index(doc_id=ingest_res.doc_id, blocks=ingest_res.blocks)
    print(f"[3/5] Indexed {index_res.indexed_count} chunks into Qdrant & BM25s.")

    # 4. Retrieve
    retrieval = RetrievalService(qdrant_store=indexing.qdrant, bm25_store=indexing.bm25)
    query_text = "What GPU and VRAM are used in the platform?"
    print(f"[4/5] Searching query: '{query_text}'")
    ret_res = retrieval.retrieve(SearchQuery(query_text=query_text, top_k=5, top_rerank=2))
    print(f"      Found {len(ret_res.candidates)} candidates, refused: {ret_res.refused}")
    for idx, c in enumerate(ret_res.candidates):
        print(f"      Candidate {idx+1}: [rerank_score={c.rerank_score:.4f}] {c.text[:80]}...")

    # 5. Generate with Ollama
    context = "\n\n".join([f"[{c.id}] {c.text}" for c in ret_res.candidates])
    prompt = (
        f"Context:\n{context}\n\n"
        f"Question: {query_text}\n"
        f"Answer truthfully based only on the context provided:"
    )
    print("[5/5] Requesting answer from Ollama (llama3.2:3b)...")
    try:
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": "llama3.2:3b", "prompt": prompt, "stream": False},
            timeout=60,
        )
        llm_answer = resp.json().get("response", "No response received")
    except Exception as e:
        llm_answer = f"Error querying Ollama: {e}"

    formatter = CitationFormatterComponent()
    final_output = formatter.format_response(llm_answer, [c.model_dump() for c in ret_res.citations])

    print("\n" + "="*50)
    print("LIVE RAG PIPELINE RESULT:")
    print("="*50)
    print(final_output)
    print("="*50)

if __name__ == "__main__":
    main()
