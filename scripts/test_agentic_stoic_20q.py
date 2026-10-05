"""20-Query Agentic RAG Evaluation Benchmark on 'The Daily Stoic' Corpus.

Evaluates the multi-hop coordinator, query decomposition, CRAG reflection,
GraphRAG traversal, FlashRank reranking, and contextual compaction on the live gateway.
"""

import json
import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

BASE_URL = "http://127.0.0.1:8010"
DOC_ID = "the_daily_stoic__366_meditations_on_wisdom,_perseverance,_and_the_art_of_living_(_pdfdrive_)_5cfc645e"
USER_ID = "usr_cbfa2228ea6f4958"
MODEL = "llama3.2:3b"

BENCHMARK_QUERIES = [
    # Archetype 1: Direct Quote & Excerpt Recall
    {
        "id": "Q01",
        "category": "Direct Quote & Excerpt Recall",
        "query": "What does Epictetus say about what is within our control and what is outside of our control in the opening of the Enchiridion?",
    },
    {
        "id": "Q02",
        "category": "Direct Quote & Excerpt Recall",
        "query": "What advice does Marcus Aurelius give himself about waking up early and getting out of bed when feeling lazy?",
    },
    {
        "id": "Q03",
        "category": "Direct Quote & Excerpt Recall",
        "query": "What does Seneca say in On the Shortness of Life about how people waste time complaining that life is too brief?",
    },
    {
        "id": "Q04",
        "category": "Direct Quote & Excerpt Recall",
        "query": "What is the metaphor of the dog leashed to a moving cart mentioned in Stoic philosophy regarding fate?",
    },

    # Archetype 2: Core Stoic Principles & Concepts
    {
        "id": "Q05",
        "category": "Core Stoic Principles",
        "query": "Explain the Stoic concept of 'Amor Fati' and how one should practice loving whatever happens.",
    },
    {
        "id": "Q06",
        "category": "Core Stoic Principles",
        "query": "What is 'Memento Mori' and why do the Stoics emphasize contemplating mortality as a daily exercise?",
    },
    {
        "id": "Q07",
        "category": "Core Stoic Principles",
        "query": "What does 'Sympatheia' mean in Stoicism and how does it view the interconnectedness of all human beings?",
    },
    {
        "id": "Q08",
        "category": "Core Stoic Principles",
        "query": "What is the 'inner citadel' and how does a Stoic protect the ruling center (hegemonikon) from external disturbances?",
    },

    # Archetype 3: Multi-Hop Comparative Philosophy
    {
        "id": "Q09",
        "category": "Multi-Hop Comparative Philosophy",
        "query": "Compare how Seneca and Epictetus view wealth, poverty, and material possessions.",
    },
    {
        "id": "Q10",
        "category": "Multi-Hop Comparative Philosophy",
        "query": "How do Marcus Aurelius and Seneca differ in their perspective on seeking solitude versus fulfilling public and social duties?",
    },
    {
        "id": "Q11",
        "category": "Multi-Hop Comparative Philosophy",
        "query": "Compare the Stoic analysis of anger and emotional outbursts between Seneca and Marcus Aurelius.",
    },
    {
        "id": "Q12",
        "category": "Multi-Hop Comparative Philosophy",
        "query": "How does Epictetus's background as an enslaved person contrast with Marcus Aurelius as a Roman Emperor in their philosophical teachings?",
    },

    # Archetype 4: Practical Applied Life Scenarios
    {
        "id": "Q13",
        "category": "Practical Applied Scenarios",
        "query": "How does Stoicism advise someone to respond when receiving harsh criticism, insults, or public slander?",
    },
    {
        "id": "Q14",
        "category": "Practical Applied Scenarios",
        "query": "What practical exercises does the book prescribe when someone is feeling paralyzed by anxiety about future catastrophes?",
    },
    {
        "id": "Q15",
        "category": "Practical Applied Scenarios",
        "query": "What is the Stoic perspective on grief and mourning the loss of a close friend or family member?",
    },
    {
        "id": "Q16",
        "category": "Practical Applied Scenarios",
        "query": "What does Seneca recommend regarding practicing voluntary poverty and temporary hardship to build resilience?",
    },

    # Archetype 5: Edge Cases, Structural & Refusal Guardrails
    {
        "id": "Q17",
        "category": "Out-of-Scope / CRAG Refusal Guardrail",
        "query": "What are the latest benchmarks comparing quantum computing qubits and artificial neural networks in 2026?",
    },
    {
        "id": "Q18",
        "category": "Cross-Philosophical Comparison",
        "query": "How does the book contrast Epicurean views on pleasure with Stoic views on virtue and duty?",
    },
    {
        "id": "Q19",
        "category": "Structural Philosophical Framework",
        "query": "Explain the three Stoic disciplines outlined by Epictetus: the discipline of Desire, the discipline of Action, and the discipline of Assent.",
    },
    {
        "id": "Q20",
        "category": "Book Architecture & Meta Analysis",
        "query": "What does Ryan Holiday explain in the introduction about the structure of the book divided into Perception, Action, and Will?",
    },
]


def setup_auth_and_session() -> tuple[dict, str]:
    """Generates an auth token for USER_ID and ensures a clean session exists."""
    from services.gateway.api import get_identity_store
    from services.identity.auth import hash_token, new_token
    from services.session.manager import SessionManager

    store = get_identity_store()
    token = new_token()
    store.create_auth_session(USER_ID, hash_token(token), time.time() + 86400)
    headers = {"Cookie": f"ri_auth={token}", "X-RI-Client": "web"}

    # Create dedicated evaluation session
    sm = SessionManager()
    session = sm.create_session(
        title="Stoic Agentic RAG Evaluation (20 Queries)",
        owner_id=USER_ID,
        workspace_id="ws_c90fcba7f5e047b3",
        files=[DOC_ID],
    )
    return headers, session.id


def run_benchmark():
    print("=" * 80)
    print("🚀 RUNNING 20-QUERY AGENTIC RAG BENCHMARK ON THE DAILY STOIC CORPUS")
    print(f"Target Gateway: {BASE_URL} | Model: {MODEL} | Doc ID: {DOC_ID}")
    print("=" * 80 + "\n")

    # 1. Health check
    h_resp = requests.get(f"{BASE_URL}/api/v1/health", timeout=5)
    if h_resp.status_code != 200:
        print(f"❌ Gateway unhealthy: {h_resp.text}")
        return
    print("✅ Gateway health verified: Qdrant, Redis, Ollama active.\n")

    # 2. Setup auth
    headers, session_id = setup_auth_and_session()
    print(f"✅ Authenticated as user: {USER_ID} | Session ID: {session_id}\n")

    results = []
    total_start = time.perf_counter()

    for idx, item in enumerate(BENCHMARK_QUERIES, start=1):
        q_id = item["id"]
        category = item["category"]
        query = item["query"]

        print(f"\n[{idx}/20] ({q_id}) [{category}]")
        print(f"Query: \"{query}\"")

        payload = {
            "query": query,
            "session_id": session_id,
            "mode": "agentic",
            "model": MODEL,
            "stream": False,
            "top_k": 20,
            "top_rerank": 6,
        }

        t0 = time.perf_counter()
        try:
            resp = requests.post(
                f"{BASE_URL}/api/v1/chat",
                headers=headers,
                json=payload,
                timeout=180,
            )
            elapsed = time.perf_counter() - t0
        except Exception as exc:
            print(f"  ❌ Request failed with error: {exc}")
            results.append({
                "id": q_id,
                "category": category,
                "query": query,
                "status": "ERROR",
                "error": str(exc),
                "duration_s": round(time.perf_counter() - t0, 2),
            })
            continue

        if resp.status_code != 200:
            print(f"  ❌ HTTP {resp.status_code}: {resp.text}")
            results.append({
                "id": q_id,
                "category": category,
                "query": query,
                "status": "HTTP_ERROR",
                "error": resp.text,
                "duration_s": round(elapsed, 2),
            })
            continue

        data = resp.json()
        refused = data.get("refused", False)
        top_score = data.get("top_score", 0.0)
        sub_queries = data.get("sub_queries", [])
        agent_steps = data.get("agent_steps", [])
        citations = data.get("citations", [])
        answer = data.get("answer", "")
        raw_answer = data.get("raw_answer", "")

        # Extract step details
        step_summary = []
        crag_status = "UNKNOWN"
        crag_reason = ""
        crag_reformulated = None
        for step in agent_steps:
            stype = step.get("step_type")
            title = step.get("title")
            detail = step.get("detail")
            sdata = step.get("data", {})
            step_summary.append({"step_index": step.get("step_index"), "type": stype, "title": title, "detail": detail})
            if stype == "crag_reflection":
                crag_status = sdata.get("status", crag_status)
                if "reformulated_query" in sdata:
                    crag_reformulated = sdata.get("reformulated_query")

        print(f"  ⏱️ Latency: {elapsed:.2f}s | Refused: {refused} | CRAG: {crag_status} | Top Score: {top_score:.4f}")
        print(f"  🔀 Sub-queries ({len(sub_queries)}): {sub_queries}")
        print(f"  📋 Steps ({len(agent_steps)}): {[s['type'] for s in step_summary]}")
        print(f"  📚 Citations ({len(citations)}): pages {[c.get('page') for c in citations[:5]]}")
        snippet = (raw_answer or answer or "").strip().replace("\n", " ")[:150]
        print(f"  💬 Answer: \"{snippet}...\"")

        results.append({
            "id": q_id,
            "category": category,
            "query": query,
            "status": "SUCCESS",
            "duration_s": round(elapsed, 2),
            "refused": refused,
            "top_score": round(top_score, 4),
            "crag_status": crag_status,
            "crag_reformulated": crag_reformulated,
            "sub_queries": sub_queries,
            "agent_steps_count": len(agent_steps),
            "agent_steps": step_summary,
            "citations_count": len(citations),
            "citations": [
                {
                    "page": c.get("page"),
                    "score": round(c.get("score", 0.0), 4),
                    "bbox": c.get("bbox"),
                    "snippet": c.get("snippet", "")[:120],
                }
                for c in citations
            ],
            "answer_preview": (raw_answer or answer or "")[:350],
            "full_answer": raw_answer or answer,
        })

    total_elapsed = time.perf_counter() - total_start
    print("\n" + "=" * 80)
    print(f"🏁 BENCHMARK COMPLETED: 20 queries evaluated in {total_elapsed:.2f}s (avg {total_elapsed/20:.2f}s/query)")
    print("=" * 80 + "\n")

    # Save structured results
    out_dir = Path("data")
    out_dir.mkdir(exist_ok=True)
    json_path = out_dir / "stoic_agentic_20q_results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"total_duration_s": round(total_elapsed, 2), "model": MODEL, "doc_id": DOC_ID, "results": results}, f, indent=2)

    print(f"💾 Structured results saved to: {json_path}")


if __name__ == "__main__":
    run_benchmark()
