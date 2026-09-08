"""End-to-End Evaluation Script for Phase 12 (Agentic Multi-Hop & CRAG) and Phase 15 (RAGOps)."""

import sys
import time

import requests

sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8000"


def main():
    print("\n" + "=" * 75)
    print("🚀 EVALUATING PHASE 12 (AGENTIC RAG & CRAG) AND PHASE 15 (RAGOPS ACTIVE LEARNING)")
    print("=" * 75 + "\n")

    # 1. Health & Service Check
    res = requests.get(f"{BASE_URL}/api/v1/health", timeout=5)
    assert res.status_code == 200, f"Gateway unhealthy: {res.text}"
    print("✅ System Health Check: All microservices (Qdrant, Redis, Ollama) active.\n")

    # 2. Test Phase 12: Multi-Hop Agentic Query Decomposition & Synthesis
    multi_hop_query = (
        "Compare Abhishek Kumar's role and key responsibilities at Syngene "
        "with the dense retrieval latency of the RTX 3050 in the hardware benchmark."
    )
    print("--- [TEST 1] Executing Agentic Multi-Hop Query ---")
    print(f"Query: \"{multi_hop_query}\"\n")

    t0 = time.perf_counter()
    chat_payload = {
        "query": multi_hop_query,
        "mode": "agentic",
        "stream": False,
        "model": "llama3.2:3b",
    }
    chat_resp = requests.post(f"{BASE_URL}/api/v1/chat", json=chat_payload, timeout=120)
    elapsed = time.perf_counter() - t0

    assert chat_resp.status_code == 200, f"Chat error: {chat_resp.text}"
    chat_data = chat_resp.json()

    print(f"Latency: {elapsed:.2f}s | Agentic Mode: {chat_data.get('is_agentic')}")
    print(f"Top Rerank Score: {chat_data.get('top_score'):.4f}")
    print(f"Sub-Queries Decomposed ({len(chat_data.get('sub_queries', []))}):")
    for sq in chat_data.get("sub_queries", []):
        print(f"  • {sq}")

    print(f"\nAgent Execution Steps ({len(chat_data.get('agent_steps', []))} steps):")
    for step in chat_data.get("agent_steps", []):
        icon = "🔍" if step.get("step_type") == "decomposition" else (
            "🌐" if step.get("step_type") == "sub_retrieval" else (
                "🛡️" if step.get("step_type") == "crag_reflection" else "⚖️"
            )
        )
        print(f"  {icon} [{step.get('title')}]: {step.get('detail')}")

    print("\n--- Synthesized Answer Excerpt ---")
    raw_answer = chat_data.get("raw_answer", "")
    print(raw_answer[:450] + ("..." if len(raw_answer) > 450 else ""))

    citations = chat_data.get("citations", [])
    print(f"\nCitations Attached ({len(citations)}):")
    for c in citations[:4]:
        badge = c.get("formatted_badge", "")
        is_tbl = " [Table]" if c.get("is_table") else ""
        is_fig = " [Figure]" if c.get("is_figure") else ""
        print(f"  📌 {badge}{is_tbl}{is_fig}: \"{c.get('snippet', '')[:80]}...\"")

    assert chat_data.get("is_agentic") is True, "Expected is_agentic to be True"
    assert len(chat_data.get("sub_queries", [])) >= 2, "Expected at least 2 decomposed sub-queries"
    assert len(citations) >= 1, "Expected at least 1 citation attached"
    print("\n✅ Test 1 (Agentic Multi-Hop & Synthesis) PASSED!\n")

    # 3. Test Phase 15: RAGOps Feedback & Active Learning Hard-Negative Mining
    print("--- [TEST 2] Submitting User Feedback (Thumbs Up) ---")
    fb_up_payload = {
        "session_id": "eval_session_12_15",
        "query_text": multi_hop_query,
        "response_text": raw_answer,
        "citations": citations,
        "rating": "thumbs_up",
        "comment": "Accurate cross-document comparison and grounded citations.",
    }
    fb_up_res = requests.post(f"{BASE_URL}/api/v1/feedback", json=fb_up_payload, timeout=5)
    assert fb_up_res.status_code == 200
    print(f"Recorded Thumbs Up: ID = {fb_up_res.json().get('id')}\n")

    print("--- [TEST 3] Submitting Feedback (Thumbs Down) with Hard-Negative Mining ---")
    fb_down_payload = {
        "session_id": "eval_session_12_15",
        "query_text": "What was the VRAM consumption on CPU mode?",
        "response_text": "CPU mode does not consume GPU VRAM.",
        "citations": [
            {
                "doc_id": "hardware_benchmark",
                "page": 1,
                "text": "RTX 3050 Laptop GPU achieves 18.5 ms dense latency with 2.2 GB VRAM.",
                "score": 0.41,
            }
        ],
        "rating": "thumbs_down",
        "comment": "Passage discussed GPU VRAM rather than CPU execution.",
    }
    fb_down_res = requests.post(f"{BASE_URL}/api/v1/feedback", json=fb_down_payload, timeout=5)
    assert fb_down_res.status_code == 200
    print(f"Recorded Thumbs Down & Mined Hard Negative: ID = {fb_down_res.json().get('id')}\n")

    # 4. Verify RAGOps Summary & Continuous Evaluation Metrics
    print("--- [TEST 4] Inspecting Continuous Evaluation & RAGOps Summary ---")
    summary_res = requests.get(f"{BASE_URL}/api/v1/feedback/summary", timeout=5)
    assert summary_res.status_code == 200
    summary = summary_res.json()
    print(f"Total Feedback Count : {summary.get('total_feedback')}")
    print(f"Thumbs Up            : {summary.get('thumbs_up')}")
    print(f"Thumbs Down          : {summary.get('thumbs_down')}")
    print(f"User Satisfaction    : {summary.get('satisfaction_rate_pct')}%")
    print(f"Hard Negatives Mined : {summary.get('hard_negatives_count')}\n")

    assert summary.get("total_feedback") >= 2
    assert summary.get("thumbs_up") >= 1
    assert summary.get("thumbs_down") >= 1
    assert summary.get("hard_negatives_count") >= 1
    print("✅ Test 3 & 4 (RAGOps Feedback & Mining) PASSED!\n")

    # 5. Verify Active Learning Dataset Export
    print("--- [TEST 5] Exporting Contrastive Fine-Tuning Dataset ---")
    dataset_res = requests.get(f"{BASE_URL}/api/v1/ragops/dataset", timeout=5)
    assert dataset_res.status_code == 200
    dataset = dataset_res.json()
    print(f"Dataset samples exported: {len(dataset)}")
    if dataset:
        sample = dataset[0]
        print(f"Sample 1:\n  Query    : {sample.get('query')}\n  Negative : {sample.get('negative')[:80]}...\n  Source   : {sample.get('source')}")

    assert len(dataset) >= 1, "Expected at least 1 mined hard negative in export"
    print("\n✅ Test 5 (Active Learning Dataset Export) PASSED!\n")

    print("=" * 75)
    print("🎉 ALL PHASE 12 & PHASE 15 EVALUATION CRITERIA 100% SATISFIED!")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    main()
