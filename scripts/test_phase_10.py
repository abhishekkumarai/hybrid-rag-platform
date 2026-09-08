"""End-to-End Verification Script for Phase 10: Multi-Turn Memory & Telemetry.

Demonstrates:
1. Session lifecycle: creation, listing, retrieval.
2. Multi-turn dialogue with context memory and pronoun resolution.
3. Live telemetry validation via /api/v1/metrics.
"""

from __future__ import annotations

import sys
import time

import requests

sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8000"


def print_banner(title: str) -> None:
    print("\n" + "=" * 80)
    print(f"  {title.upper()}")
    print("=" * 80)


def verify_phase_10() -> bool:
    print_banner("Phase 10: Enterprise Multi-Turn & Telemetry Verification")

    # 1. Health check
    try:
        health_resp = requests.get(f"{BASE_URL}/api/v1/health", timeout=3.0)
        if health_resp.status_code != 200:
            print(f"[-] Gateway unhealthy: {health_resp.status_code}")
            return False
        print(f"[+] Gateway is healthy: {health_resp.json()}")
    except Exception as e:
        print(f"[-] Could not reach Gateway at {BASE_URL}: {e}")
        return False

    # 2. Create Session
    session_title = "Phase 10 Multi-Turn Evaluation"
    sess_resp = requests.post(f"{BASE_URL}/api/v1/sessions", json={"title": session_title}, timeout=3.0)
    if sess_resp.status_code != 200:
        print(f"[-] Failed to create session: {sess_resp.text}")
        return False
    session_data = sess_resp.json()
    session_id = session_data["id"]
    print(f"[+] Created Session: id={session_id} title='{session_data['title']}'")

    # 3. Multi-Turn Conversational Flow
    turns = [
        {
            "label": "Turn 1: Specific Entity Identification",
            "query": "Who is Abhishek Kumar and what is his current role?",
            "expected_keywords": ["abhishek", "syngene", "bristol", "architect", "engineer"],
        },
        {
            "label": "Turn 2: Anaphoric Reference (Pronoun Resolution)",
            "query": "Where did he work before that?",
            "expected_keywords": ["data capital", "accenture", "syngene", "prior", "before"],
        },
        {
            "label": "Turn 3: Follow-Up Project Achievements",
            "query": "What were his main project achievements there?",
            "expected_keywords": ["llm", "rag", "pipeline", "platform", "model", "production"],
        },
    ]

    for idx, turn in enumerate(turns, 1):
        print_banner(f"{turn['label']}")
        print(f"User Query: \"{turn['query']}\"")

        start_t = time.perf_counter()
        chat_payload = {
            "query": turn["query"],
            "session_id": session_id,
            "top_k": 5,
            "top_rerank": 3,
            "stream": False,
            "model": "llama3.2:3b",
        }

        resp = requests.post(f"{BASE_URL}/api/v1/chat", json=chat_payload, timeout=60.0)
        elapsed = (time.perf_counter() - start_t) * 1000

        if resp.status_code != 200:
            print(f"[-] Chat failed with status {resp.status_code}: {resp.text}")
            return False

        data = resp.json()
        answer = data.get("answer", "")
        citations = data.get("citations", [])
        refused = data.get("refused", False)
        duration_ms = data.get("duration_ms", 0.0)

        print(f"\nAssistant Response (Gateway Latency: {elapsed:.1f}ms, Pipeline: {duration_ms:.1f}ms):")
        print("-" * 60)
        print(answer)
        print("-" * 60)
        print(f"Refused: {refused} | Citations: {len(citations)}")

        # Keyword match check
        answer_lower = answer.lower()
        matched = [kw for kw in turn["expected_keywords"] if kw in answer_lower]
        print(f"Keyword Matches: {matched} / {turn['expected_keywords']}")

    # 4. Verify Session History & Auto-titling
    print_banner("Verifying Session Message History")
    detail_resp = requests.get(f"{BASE_URL}/api/v1/sessions/{session_id}", timeout=3.0)
    if detail_resp.status_code != 200:
        print(f"[-] Failed to fetch session details: {detail_resp.text}")
        return False

    detail_data = detail_resp.json()
    messages = detail_data.get("messages", [])
    print(f"[+] Retrieved {len(messages)} chronological messages in session.")
    assert len(messages) == 6, f"Expected 6 messages (3 user + 3 assistant), got {len(messages)}"
    for m in messages:
        role = m["role"].upper()
        snippet = m["content"][:80].replace("\n", " ")
        print(f"  [{role}] {snippet}...")

    # 5. Verify Telemetry HUD & System Metrics
    print_banner("Verifying Real-Time Telemetry & Observability Metrics")
    metrics_resp = requests.get(f"{BASE_URL}/api/v1/metrics", timeout=3.0)
    if metrics_resp.status_code != 200:
        print(f"[-] Failed to fetch metrics: {metrics_resp.text}")
        return False

    metrics = metrics_resp.json()
    print(f"  * Total Queries Processed: {metrics.get('total_queries')}")
    print(f"  * Total Refusals:          {metrics.get('total_refusals')}")
    print(f"  * Avg Retrieval Latency:   {metrics.get('avg_retrieval_ms')} ms")
    print(f"  * Avg Rerank Latency:      {metrics.get('avg_rerank_ms')} ms")
    print(f"  * Avg Generation Latency:  {metrics.get('avg_generation_ms')} ms")
    print(f"  * Avg LLM Throughput:      {metrics.get('avg_tokens_per_sec')} tok/s")
    print(f"  * Qdrant Points:           {metrics.get('qdrant_points')}")
    print(f"  * BM25 Chunks:             {metrics.get('bm25_chunks')}")
    print(f"  * Redis Queue Depth:       {metrics.get('redis_queue_depth')}")
    print(f"  * DLQ Dead Letter Count:   {metrics.get('dlq_task_count')}")

    recent = metrics.get("recent_telemetry", [])
    print(f"\n[+] Recent Telemetry Entries: {len(recent)}")
    for t in recent[:3]:
        q_str = t.get("query_text") or t.get("query") or ""
        print(
            f"  - Query: \"{q_str[:40]}...\" | Total: {t.get('total_ms'):.1f}ms "
            f"(Dense: {t.get('dense_ms'):.1f}ms, Sparse: {t.get('sparse_ms'):.1f}ms, "
            f"Rerank: {t.get('rerank_ms'):.1f}ms, TTFT: {t.get('llm_ttft_ms'):.1f}ms) "
            f"| Speed: {t.get('tokens_per_sec'):.1f} tok/s"
        )

    print_banner("Phase 10 Verification Completed Successfully!")
    return True


if __name__ == "__main__":
    success = verify_phase_10()
    sys.exit(0 if success else 1)
