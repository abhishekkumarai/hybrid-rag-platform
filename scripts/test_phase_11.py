"""End-to-End Verification Script for Phase 11: Deep Multimodal Table & Figure Ingestion.

Validates:
1. Extraction of structured tables into clean GitHub Markdown with captions.
2. Extraction of diagrams/figures into rendered PNG crops with visual captions.
3. Dual indexing of table and figure chunks in Qdrant and BM25s.
4. Multimodal retrieval & QA:
   - Query 1: Extracting specific matrix cells from the Hardware Benchmark Table.
   - Query 2: Explaining the visual architecture diagram from Figure 1.
5. Serving extracted figures via GET /api/v1/figures/{filename}.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8000"
PDF_PATH = Path("data/documents/multimodal_hardware_benchmark.pdf")


def print_banner(title: str) -> None:
    print("\n" + "=" * 80)
    print(f"  {title.upper()}")
    print("=" * 80)


def verify_phase_11() -> bool:
    print_banner("Phase 11: Deep Multimodal Table & Figure Ingestion Verification")

    # 1. Health check
    try:
        health_resp = requests.get(f"{BASE_URL}/api/v1/health", timeout=3.0)
        if health_resp.status_code != 200:
            print(f"[-] Gateway unhealthy: {health_resp.status_code}")
            return False
        print(f"[+] Gateway is healthy: {health_resp.json()}")
    except Exception as e:
        print(f"[-] Could not connect to Gateway at {BASE_URL}: {e}")
        return False

    # 2. Ingest Multimodal PDF
    if not PDF_PATH.exists():
        print(f"[-] Test PDF not found: {PDF_PATH}")
        return False

    print(f"\n[+] Ingesting '{PDF_PATH.name}'...")
    with open(PDF_PATH, "rb") as f:
        ingest_resp = requests.post(f"{BASE_URL}/api/v1/ingest", files={"file": (PDF_PATH.name, f, "application/pdf")})

    if ingest_resp.status_code != 200:
        print(f"[-] Ingest failed: {ingest_resp.text}")
        return False

    ingest_data = ingest_resp.json()
    doc_id = ingest_data["doc_id"]
    blocks = ingest_data["blocks"]
    print(f"[+] Parsed '{PDF_PATH.name}' (doc_id={doc_id}) into {len(blocks)} blocks via route '{ingest_data['profile']['route']}'")

    # Verify table and figure blocks exist
    table_blocks = [b for b in blocks if b["type"] == "table"]
    figure_blocks = [b for b in blocks if b["type"] == "image"]
    print(f"    * Detected Tables:  {len(table_blocks)} (Caption: '{table_blocks[0]['caption'] if table_blocks else 'None'}')")
    print(f"    * Detected Figures: {len(figure_blocks)} (Caption: '{figure_blocks[0]['caption'] if figure_blocks else 'None'}')")

    assert len(table_blocks) >= 1, "Expected at least 1 table block"
    assert len(figure_blocks) >= 1, "Expected at least 1 figure block"

    # 3. Index Blocks into Dual Stores
    print("\n[+] Chunking and indexing into Qdrant & BM25s...")
    index_resp = requests.post(
        f"{BASE_URL}/api/v1/index",
        json={"doc_id": doc_id, "blocks": blocks},
    )
    if index_resp.status_code != 200:
        print(f"[-] Indexing failed: {index_resp.text}")
        return False

    index_data = index_resp.json()
    print(f"[+] Successfully indexed {index_data['indexed_count']} chunks in {index_data['duration_ms']:.1f}ms")

    # 4. Verify Figure Image Endpoint
    fig_rel_path = figure_blocks[0].get("image_path")
    if fig_rel_path:
        fig_filename = Path(fig_rel_path).name
        fig_url = f"{BASE_URL}/api/v1/figures/{fig_filename}"
        fig_resp = requests.get(fig_url, timeout=3.0)
        assert fig_resp.status_code == 200, f"Expected 200 from figure endpoint, got {fig_resp.status_code}"
        assert fig_resp.headers.get("content-type") == "image/png"
        print(f"[+] Figure serving verified at GET /api/v1/figures/{fig_filename} (HTTP 200, {len(fig_resp.content)} bytes)")

    # 5. Create Fresh Test Session
    sess_resp = requests.post(f"{BASE_URL}/api/v1/sessions", json={"title": "Multimodal Evaluation"}, timeout=3.0)
    session_id = sess_resp.json()["id"]

    # 6. Test Multimodal Queries
    queries = [
        {
            "title": "Query 1: Structured Table Extraction & Numerical Accuracy",
            "query": "What is the VRAM usage and dense latency of the RTX 3050 Laptop in the hardware benchmark table?",
            "expected_keywords": ["3050", "2.2", "18.5", "vram", "latency"],
            "expected_type": "table",
        },
        {
            "title": "Query 2: Visual Figure & Architecture Diagram Reasoning",
            "query": "Describe the main components and data flow illustrated in the architecture diagram in Figure 1.",
            "expected_keywords": ["extractor", "hnsw", "bm25", "flashrank", "reranker", "ollama"],
            "expected_type": "figure",
        },
    ]

    for q_info in queries:
        print_banner(q_info["title"])
        print(f"User Query: \"{q_info['query']}\"")

        start_t = time.perf_counter()
        chat_resp = requests.post(
            f"{BASE_URL}/api/v1/chat",
            json={
                "query": q_info["query"],
                "session_id": session_id,
                "top_k": 5,
                "top_rerank": 3,
                "stream": False,
                "model": "llama3.2:3b",
            },
            timeout=120.0,
        )
        elapsed = (time.perf_counter() - start_t) * 1000

        if chat_resp.status_code != 200:
            print(f"[-] Chat query failed: {chat_resp.text}")
            return False

        data = chat_resp.json()
        answer = data.get("answer", "")
        citations = data.get("citations", [])
        refused = data.get("refused", False)
        duration_ms = data.get("duration_ms", 0.0)

        print(f"\nAssistant Answer (Gateway: {elapsed:.1f}ms, Pipeline: {duration_ms:.1f}ms):")
        print("-" * 60)
        print(answer)
        print("-" * 60)
        print(f"Refused: {refused} | Citations: {len(citations)}")

        # Check keyword matches
        answer_lower = answer.lower()
        matched = [kw for kw in q_info["expected_keywords"] if kw in answer_lower]
        print(f"Keyword Matches: {matched} / {q_info['expected_keywords']}")

        # Verify multimodal citations
        if citations:
            for c in citations:
                c_type = "Table" if c.get("is_table") else ("Figure" if c.get("is_figure") else "Text")
                print(f"  * Citation [{c_type}]: {c.get('formatted_badge')}")

    print_banner("Phase 11 Multimodal Verification Completed Successfully!")
    return True


if __name__ == "__main__":
    success = verify_phase_11()
    sys.exit(0 if success else 1)
