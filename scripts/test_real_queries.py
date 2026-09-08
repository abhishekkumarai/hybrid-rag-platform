"""Real-world multi-query evaluation script testing real documents."""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Ensure UTF-8 output on Windows consoles
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import requests

from components.citation_formatter import CitationFormatterComponent
from contracts.document import IngestRequest
from contracts.retrieval import SearchQuery
from services.common.config import load_config
from services.indexing.service import IndexingService
from services.ingestion.service import IngestionService
from services.retrieval.service import RetrievalService

config = load_config()


def index_documents(ingestion: IngestionService, indexing: IndexingService):
    docs_dir = Path("data/documents")
    pdf_files = list(docs_dir.glob("*.pdf"))
    print(f"Found {len(pdf_files)} documents in {docs_dir}:")
    for f in pdf_files:
        print(f" - {f.name} ({f.stat().st_size / 1024:.1f} KB)")

    for pdf_path in pdf_files:
        print(f"\nIngesting & Indexing '{pdf_path.name}'...")
        ingest_res = ingestion.parse(IngestRequest(file_path=str(pdf_path)))
        print(f"  Probed Route: {ingest_res.profile.route} (pages: {ingest_res.profile.page_count}, blocks: {len(ingest_res.blocks)})")
        index_res = indexing.chunk_and_index(doc_id=ingest_res.doc_id, blocks=ingest_res.blocks)
        print(f"  Indexed {index_res.indexed_count} chunks into Qdrant & BM25s in {index_res.duration_ms:.1f}ms")


def run_query(retrieval: RetrievalService, formatter: CitationFormatterComponent, query_text: str, test_num: int):
    print("\n" + "=" * 70)
    print(f"REAL QUERY {test_num}: \"{query_text}\"")
    print("=" * 70)

    t0 = time.perf_counter()
    search_query = SearchQuery(query_text=query_text, top_k=20, top_rerank=4, min_rerank_score=0.15)
    ret_res = retrieval.retrieve(search_query)
    retrieval_ms = (time.perf_counter() - t0) * 1000

    print(f"Retrieval & Rerank Latency: {retrieval_ms:.1f}ms")
    print(f"Top Rerank Score:           {ret_res.top_score:.4f}")
    print(f"Refusal Triggered:          {ret_res.refused}")
    print(f"Candidates Retrieved:       {len(ret_res.candidates)}")

    if ret_res.refused or not ret_res.candidates:
        print("\n>>> RESULT: System issued confident refusal due to relevance cutoff < 0.15.")
        print("    No hallucination was passed to Ollama.")
        return

    print("\nTop Retrieved Context Passages:")
    for i, c in enumerate(ret_res.candidates[:3]):
        print(f"  [{i+1}] (Score: {c.rerank_score:.4f}, Doc: {c.doc_id}, Page: {c.page})")
        snippet = c.text.replace("\n", " ")[:140]
        print(f"      \"{snippet}...\"")

    # Generate answer via local Ollama
    context = "\n\n".join([f"[{c.id}] {c.text}" for c in ret_res.candidates])
    prompt = (
        f"You are a factual assistant. Answer the question truthfully based ONLY on the context provided below. "
        f"If the context does not contain the answer, say you do not know.\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {query_text}\n"
        f"Answer:"
    )

    print("\nRequesting LLM generation from Ollama (llama3.2:3b)...")
    t1 = time.perf_counter()
    try:
        resp = requests.post(
            f"{config.hardware.ollama_base_url}/api/generate",
            json={"model": "llama3.2:3b", "prompt": prompt, "stream": False},
            timeout=60,
        )
        llm_raw = resp.json().get("response", "Error: No response")
    except Exception as e:
        llm_raw = f"Error querying Ollama: {e}"
    gen_ms = (time.perf_counter() - t1) * 1000

    formatted = formatter.format_response(llm_raw, [c.model_dump() for c in ret_res.citations])
    print(f"LLM Generation Latency:     {gen_ms:.1f}ms\n")
    print("---------------------------- ANSWER ----------------------------")
    print(formatted)
    print("----------------------------------------------------------------")


def test_visual_preview(citations: list[dict]):
    """Verifies that visual page bounding box snapshot preview endpoint works."""
    if not citations:
        return
    c = citations[0]
    doc_id = c.get("doc_id", "")
    page = c.get("page", 1)
    bbox = c.get("bbox", [72, 72, 200, 200])
    bbox_str = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
    url = f"http://127.0.0.1:8000/api/v1/preview?doc_id={doc_id}&page={page}&bbox={bbox_str}"
    print("\n" + "=" * 70)
    print("VISUAL PROVENANCE HIGHLIGHT VERIFICATION")
    print("=" * 70)
    print(f"Requesting preview from FastAPI Gateway: {url}")
    try:
        r = requests.get(url, timeout=10)
        print(f"Preview Response Status:  {r.status_code}")
        print(f"Content-Type:             {r.headers.get('content-type')}")
        print(f"Image Size:               {len(r.content)} bytes")
        if r.status_code == 200 and "image" in r.headers.get("content-type", ""):
            print(">>> SUCCESS: Visual bounding box snapshot rendered and verified!")
    except Exception as e:
        print(f"Visual preview check skipped (Gateway offline or {e})")


def main():
    import shutil
    print("Initializing Services for Real Queries Testing...")

    # 1. Reset BM25 index on disk
    bm25_dir = Path("data/indices/bm25")
    if bm25_dir.exists():
        shutil.rmtree(bm25_dir, ignore_errors=True)

    ingestion = IngestionService()
    indexing = IndexingService(in_memory=False, qdrant_host="127.0.0.1")

    # 2. Reset Qdrant collection
    indexing.qdrant.reset_collection()

    retrieval = RetrievalService(
        qdrant_store=indexing.qdrant,
        bm25_store=indexing.bm25,
        ollama_url="http://127.0.0.1:11434",
    )
    formatter = CitationFormatterComponent()

    # Step 1: Ingest and index available documents
    index_documents(ingestion, indexing)

    # Step 2: Test diverse real-world queries
    queries = [
        "What are Abhishek Kumar's key skills, generative AI frameworks, and core technical expertise?",
        "Where has Abhishek Kumar worked and what were his key roles or project achievements?",
        "What GPU, how much VRAM, and which database ports are specified in the platform architecture?",
        "What is the capital of France and what is the best recipe for baking croissants?",
    ]

    for idx, q in enumerate(queries, 1):
        run_query(retrieval, formatter, q, idx)

    # Step 3: Test Visual Preview on the indexed document
    test_visual_preview([{"doc_id": "abhishek_kumar_genai_2026_10yoe_detailed_96b0495d", "page": 1, "bbox": [72.0, 74.4, 520.0, 160.0]}])


if __name__ == "__main__":
    main()
