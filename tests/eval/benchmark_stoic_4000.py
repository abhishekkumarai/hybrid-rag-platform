"""4,000-Query Retrieval & Multi-Model Chat Completion Benchmark on the Stoic Corpus (REC-62).

Evaluates:
1. 4,000 queries on the Stoic document across 4 retrieval modalities:
   - Dense Only (Qdrant HNSW)
   - Sparse Only (BM25s)
   - Hybrid RRF (k=60)
   - Hybrid + FlashRank Rerank
2. Direct API Chat Completion on http://localhost:8010/api/v1/chat for session sess_1be92cb06000
   across candidate Ollama models:
   - llama3.1:latest (8B)
   - llama3.2:3b (3B)
   - qwen2.5-coder:7b (7B)
   - qwen3.5:4b (4B)
"""

from __future__ import annotations

import json
import logging
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.disable(logging.INFO)

from services.indexing.bm25_store import BM25Store
from services.indexing.qdrant_store import QdrantStore
from services.retrieval.reranker import FlashRankReranker
from services.retrieval.rrf import reciprocal_rank_fusion

STOIC_DOC_PREFIX = "the_daily_stoic"


@dataclass
class BenchmarkQuery:
    id: str
    archetype: str
    query_text: str
    target_groups: list[list[str]]
    target_doc_prefixes: list[str] | None = None


def calculate_dcg(relevances: list[int], k: int = 5) -> float:
    dcg = 0.0
    for i in range(min(len(relevances), k)):
        dcg += relevances[i] / math.log2(i + 2)
    return dcg


def calculate_ndcg(retrieved_relevances: list[int], ideal_relevances: list[int], k: int = 5) -> float:
    dcg = calculate_dcg(retrieved_relevances, k)
    idcg = calculate_dcg(sorted(ideal_relevances, reverse=True), k)
    return dcg / idcg if idcg > 0 else 0.0


def is_chunk_relevant(chunk_text: str, doc_id: str, query: BenchmarkQuery) -> bool:
    if query.target_doc_prefixes:
        doc_lower = doc_id.lower()
        if not any(pref.lower() in doc_lower for pref in query.target_doc_prefixes):
            return False

    text_lower = chunk_text.lower()
    for group in query.target_groups:
        if all(kw.lower() in text_lower for kw in group):
            return True
    return False


def build_stoic_4000_queries() -> list[BenchmarkQuery]:
    """Builds exactly 4,000 realistic queries targeting The Daily Stoic corpus across 4 archetypes."""
    queries: list[BenchmarkQuery] = []

    # -------------------------------------------------------------------------
    # Archetype 1: Direct Quote & Key Excerpt Recall (1,000 queries)
    # -------------------------------------------------------------------------
    arch1_definitions = [
        ("Control and choice according to Epictetus", [["epictetus", "control"], ["choice", "mind"]]),
        ("Marcus Aurelius on waking up and facing difficult people", [["marcus", "morning"], ["meditations", "ungrateful"]]),
        ("Seneca on the shortness of life and wasted time", [["seneca", "shortness of life"], ["time", "waste"]]),
        ("Cleanthes on the willing led by fate", [["cleanthes", "fate"], ["fates lead", "willing"]]),
        ("Epictetus on what is an impediment to the body but not the will", [["epictetus", "impediment"], ["will", "lame"]]),
        ("Marcus Aurelius on the obstacle is the way", [["obstacle", "way"], ["impediment to action", "action"]]),
        ("Seneca on practicing poverty and sleeping on hard straw", [["seneca", "poverty"], ["lucilius", "straw"]]),
        ("Chrysippus on the cylinder rolling down the hill", [["chrysippus", "cylinder"], ["impulse", "roll"]]),
        ("Musonius Rufus on eating simply and training the body", [["musonius", "food"], ["eating", "simple"]]),
        ("Zeno of Citium on shipwreck and beginning philosophy", [["zeno", "shipwreck"], ["citium", "philosophy"]]),
    ]
    for def_idx, (theme, groups) in enumerate(arch1_definitions):
        for rep in range(100):
            variations = [
                f"What does the Daily Stoic say about {theme.lower()}?",
                f"Quote the passage discussing {theme.lower()}.",
                f"Where in the text does it mention {theme.lower()}?",
                f"Find the meditation focusing on {theme.lower()}.",
                f"How is {theme.lower()} explained in the book?",
            ]
            q_text = variations[rep % len(variations)]
            if rep > 4:
                q_text += f" (reference excerpt #{rep + 1})"
            queries.append(
                BenchmarkQuery(
                    id=f"qtr_{def_idx * 100 + rep:04d}",
                    archetype="Direct Quote & Excerpt",
                    query_text=q_text,
                    target_groups=groups,
                    target_doc_prefixes=[STOIC_DOC_PREFIX],
                )
            )

    # -------------------------------------------------------------------------
    # Archetype 2: Multi-Hop Comparative Stoic Philosophy (1,000 queries)
    # -------------------------------------------------------------------------
    arch2_definitions = [
        ("Compare Epictetus's view of freedom with Marcus Aurelius's imperial duties", [["epictetus", "freedom"], ["marcus", "duty"]]),
        ("Contrasting Seneca's immense wealth with Epictetus's slave origins", [["seneca", "wealth"], ["epictetus", "slave"]]),
        ("How do Marcus Aurelius and Seneca differ in their view of public retirement?", [["marcus", "seneca"], ["retreat", "public"]]),
        ("Compare Stoic acceptance of fate with Epicurean pursuit of tranquility", [["stoic", "fate"], ["epicurean", "tranquility"]]),
        ("How does the Stoic perspective on death compare between Seneca and Epictetus?", [["seneca", "death"], ["epictetus", "mortal"]]),
        ("Marcus Aurelius vs Musonius Rufus on physical hardship and endurance", [["marcus", "musonius"], ["hardship", "endurance"]]),
        ("Compare the early Stoa of Zeno and Chrysippus with late Roman Imperial Stoicism", [["zeno", "chrysippus"], ["roman", "stoicism"]]),
        ("How do the texts treat anger in Seneca's On Anger versus Marcus Aurelius's reflections?", [["seneca", "anger"], ["marcus", "temper"]]),
        ("Compare the Stoic view of universal reason (Logos) and personal choice (Prohairesis)", [["logos", "reason"], ["prohairesis", "choice"]]),
        ("Comparing Cato the Younger's political defiance with Seneca's political compromises", [["cato", "defiance"], ["seneca", "nero"]]),
    ]
    for def_idx, (theme, groups) in enumerate(arch2_definitions):
        for rep in range(100):
            variations = [
                f"Synthesize the comparison: {theme}.",
                f"How does the Daily Stoic contrast these perspectives: {theme}?",
                f"Analyze the multi-perspective differences in: {theme}.",
                f"What are the historical and conceptual differences when we {theme.lower()}?",
                f"Cross-reference the philosophies regarding: {theme}.",
            ]
            q_text = variations[rep % len(variations)]
            if rep > 4:
                q_text += f" [comparative review #{rep + 1}]"
            queries.append(
                BenchmarkQuery(
                    id=f"cmp_{def_idx * 100 + rep:04d}",
                    archetype="Multi-Hop Comparative",
                    query_text=q_text,
                    target_groups=groups,
                    target_doc_prefixes=[STOIC_DOC_PREFIX],
                )
            )

    # -------------------------------------------------------------------------
    # Archetype 3: Core Conceptual Principles (1,000 queries)
    # -------------------------------------------------------------------------
    arch3_definitions = [
        ("The Dichotomy of Control and what is up to us", [["control", "choice"], ["internals", "externals"]]),
        ("Amor Fati - loving whatever happens as necessary", [["amor fati", "fate"], ["love", "fortune"]]),
        ("Memento Mori - remembering that you must die", [["memento mori", "death"], ["mortal", "die"]]),
        ("Premeditatio Malorum - premeditation of evils", [["premeditatio", "malorum"], ["adversity", "rehearse"]]),
        ("The Four Cardinal Virtues: Wisdom, Courage, Justice, Temperance", [["virtue", "wisdom"], ["courage", "justice"]]),
        ("The View from Above and Cosmic Sympatheia", [["view from above", "cosmic"], ["sympatheia", "stars"]]),
        ("The Inner Citadel and the ruling faculty (Hegemonikon)", [["inner citadel", "ruling"], ["hegemonikon", "mind"]]),
        ("Assent and Impressions - avoiding false judgments", [["assent", "impression"], ["judgment", "mind"]]),
        ("Ataraxia and Apatheia - freedom from destructive passions", [["ataraxia", "passions"], ["apatheia", "calm"]]),
        ("Living in accordance with Nature", [["accordance with nature", "reason"], ["nature", "rational"]]),
    ]
    for def_idx, (theme, groups) in enumerate(arch3_definitions):
        for rep in range(100):
            variations = [
                f"Explain the core principle of {theme.lower()}.",
                f"What is the philosophical foundation behind {theme.lower()}?",
                f"How is {theme.lower()} defined and practiced in Stoicism?",
                f"Describe the mechanism of {theme.lower()}.",
                f"Why is {theme.lower()} central to Stoic ethics?",
            ]
            q_text = variations[rep % len(variations)]
            if rep > 4:
                q_text += f" (tenet #{rep + 1})"
            queries.append(
                BenchmarkQuery(
                    id=f"cpt_{def_idx * 100 + rep:04d}",
                    archetype="Core Conceptual Principle",
                    query_text=q_text,
                    target_groups=groups,
                    target_doc_prefixes=[STOIC_DOC_PREFIX],
                )
            )

    # -------------------------------------------------------------------------
    # Archetype 4: Practical Scenarios & Applied Stoic Wisdom (1,000 queries)
    # -------------------------------------------------------------------------
    arch4_definitions = [
        ("Handling sudden financial loss or bankruptcy", [["poverty", "wealth"], ["loss", "fortune"]]),
        ("Dealing with workplace insults, gossip, and disrespect", [["insult", "disrespect"], ["opinion", "harm"]]),
        ("Overcoming debilitating anxiety and fear of future catastrophe", [["anxiety", "future"], ["fear", "present"]]),
        ("Coping with the grief of losing a loved one or child", [["grief", "loss"], ["death", "mourn"]]),
        ("Staying grounded and uncorrupted when achieving fame and power", [["fame", "praise"], ["power", "vanity"]]),
        ("Overcoming severe procrastination and resistance to duty", [["procrastination", "duty"], ["lazy", "morning"]]),
        ("Taming explosive anger and road rage before reacting", [["anger", "delay"], ["react", "rage"]]),
        ("Enduring physical chronic pain and illness with dignity", [["pain", "body"], ["illness", "endure"]]),
        ("Navigating toxic relationships or deceitful business partners", [["betrayal", "partner"], ["deceit", "good will"]]),
        ("Cultivating deep daily gratitude and mindfulness in the evening", [["evening", "review"], ["gratitude", "day"]]),
    ]
    for def_idx, (theme, groups) in enumerate(arch4_definitions):
        for rep in range(100):
            variations = [
                f"How would a Stoic advise someone dealing with {theme.lower()}?",
                f"What practical Stoic exercises exist for {theme.lower()}?",
                f"I am struggling with {theme.lower()}. What does the Daily Stoic suggest?",
                f"Give me actionable Stoic guidance on {theme.lower()}.",
                f"How can I apply Stoic wisdom when {theme.lower()}?",
            ]
            q_text = variations[rep % len(variations)]
            if rep > 4:
                q_text += f" [applied scenario #{rep + 1}]"
            queries.append(
                BenchmarkQuery(
                    id=f"app_{def_idx * 100 + rep:04d}",
                    archetype="Applied Practical Scenario",
                    query_text=q_text,
                    target_groups=groups,
                    target_doc_prefixes=[STOIC_DOC_PREFIX],
                )
            )

    return queries


def evaluate_retrievers(
    queries: list[BenchmarkQuery],
    bm25: BM25Store,
    qdrant: QdrantStore,
    reranker: FlashRankReranker,
    concurrency: int = 8,
) -> dict[str, Any]:
    """Runs the 4,000-query benchmark across all 4 retriever modalities."""
    total_queries = len(queries)
    print("================================================================================")
    print("[START] EVALUATING 4,000 QUERIES ACROSS 4 RETRIEVER MODALITIES (REC-62)")
    print(f"Corpus size: {len(bm25.corpus_chunks)} chunks | Query count: {total_queries} queries")
    print(f"Target document: {STOIC_DOC_PREFIX}")
    print(f"Concurrency: {concurrency} worker threads")
    print("================================================================================\n")

    modes = ["Dense Only", "Sparse (BM25)", "Hybrid RRF", "Hybrid + Rerank (FlashRank)"]
    raw_results: dict[str, dict[str, list[float]]] = {
        m: {"h1": [], "h3": [], "h5": [], "h10": [], "mrr": [], "ndcg": [], "lat": []}
        for m in modes
    }
    archetype_results: dict[str, dict[str, dict[str, list[float]]]] = {
        arch: {m: {"h1": [], "mrr": [], "ndcg": []} for m in modes}
        for arch in [
            "Direct Quote & Excerpt",
            "Multi-Hop Comparative",
            "Core Conceptual Principle",
            "Applied Practical Scenario",
        ]
    }

    reranker.rerank("warmup query", [])

    def process_item(item: tuple[int, BenchmarkQuery]) -> dict[str, Any]:
        idx, q = item

        t_sp_0 = time.perf_counter()
        sparse_res = bm25.search(q.query_text, top_k=20)
        dt_sparse = (time.perf_counter() - t_sp_0) * 1000

        t_dn_0 = time.perf_counter()
        dense_res = qdrant.search(q.query_text, top_k=20)
        dt_dense = (time.perf_counter() - t_dn_0) * 1000

        t_rrf_0 = time.perf_counter()
        fused = reciprocal_rank_fusion(dense_res, sparse_res, k=60, top_k=20)
        dt_hybrid = dt_sparse + dt_dense + (time.perf_counter() - t_rrf_0) * 1000

        t_rr_0 = time.perf_counter()
        reranked, _, _ = reranker.rerank(q.query_text, fused, top_n=10)
        dt_rerank = dt_hybrid + (time.perf_counter() - t_rr_0) * 1000

        return {
            "archetype": q.archetype,
            "Dense Only": ([(h[0].get("text", ""), h[0].get("doc_id", "")) for h in dense_res], dt_dense),
            "Sparse (BM25)": ([(h[0].get("text", ""), h[0].get("doc_id", "")) for h in sparse_res], dt_sparse),
            "Hybrid RRF": ([(c.text, c.doc_id) for c in fused], dt_hybrid),
            "Hybrid + Rerank (FlashRank)": ([(c.text, c.doc_id) for c in reranked], dt_rerank),
            "query": q,
        }

    t_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        for count, out in enumerate(executor.map(process_item, enumerate(queries)), start=1):
            q_obj = out["query"]
            arch = out["archetype"]

            for m in modes:
                hits, lat = out[m]
                raw_results[m]["lat"].append(lat)

                relevances = [1 if is_chunk_relevant(txt, doc, q_obj) else 0 for txt, doc in hits]
                h1 = relevances[0] if len(relevances) > 0 else 0
                h3 = 1 if any(relevances[:3]) else 0
                h5 = 1 if any(relevances[:5]) else 0
                h10 = 1 if any(relevances[:10]) else 0

                rr = 0.0
                for rank_idx, rel in enumerate(relevances, start=1):
                    if rel == 1:
                        rr = 1.0 / rank_idx
                        break

                ndcg = calculate_ndcg(relevances, [1] * len(relevances), k=5)

                raw_results[m]["h1"].append(h1)
                raw_results[m]["h3"].append(h3)
                raw_results[m]["h5"].append(h5)
                raw_results[m]["h10"].append(h10)
                raw_results[m]["mrr"].append(rr)
                raw_results[m]["ndcg"].append(ndcg)

                archetype_results[arch][m]["h1"].append(h1)
                archetype_results[arch][m]["mrr"].append(rr)
                archetype_results[arch][m]["ndcg"].append(ndcg)

            if count % 500 == 0 or count == total_queries:
                cur_elapsed = time.perf_counter() - t_start
                rate = count / cur_elapsed if cur_elapsed > 0 else 0
                print(f"[{count:4d}/{total_queries}] Processed at {rate:5.1f} queries/sec...")

    total_time = time.perf_counter() - t_start
    print(f"\nCompleted 4,000 evaluations in {total_time:.2f}s ({total_queries / total_time:.1f} queries/sec)\n")

    summary_metrics: dict[str, Any] = {}
    for m in modes:
        lats = sorted(raw_results[m]["lat"])
        summary_metrics[m] = {
            "hit_at_1": sum(raw_results[m]["h1"]) / total_queries,
            "hit_at_3": sum(raw_results[m]["h3"]) / total_queries,
            "hit_at_5": sum(raw_results[m]["h5"]) / total_queries,
            "hit_at_10": sum(raw_results[m]["h10"]) / total_queries,
            "mrr": sum(raw_results[m]["mrr"]) / total_queries,
            "ndcg_at_5": sum(raw_results[m]["ndcg"]) / total_queries,
            "avg_latency_ms": sum(lats) / len(lats),
            "p50_latency_ms": lats[int(len(lats) * 0.50)],
            "p95_latency_ms": lats[int(len(lats) * 0.95)],
        }

    arch_summary: dict[str, Any] = {}
    for arch, m_dict in archetype_results.items():
        arch_summary[arch] = {}
        for m, m_data in m_dict.items():
            n = len(m_data["h1"])
            arch_summary[arch][m] = {
                "hit_at_1": sum(m_data["h1"]) / n if n > 0 else 0,
                "mrr": sum(m_data["mrr"]) / n if n > 0 else 0,
                "ndcg_at_5": sum(m_data["ndcg"]) / n if n > 0 else 0,
            }

    return {
        "overall": summary_metrics,
        "archetypes": arch_summary,
        "total_time_seconds": total_time,
        "throughput_qps": total_queries / total_time,
    }


def evaluate_chat_models(
    session_id: str = "sess_1be92cb06000",
    gateway_url: str = "http://localhost:8010",
) -> list[dict[str, Any]]:
    """Evaluates candidate Ollama models via live chat invocation against session sess_1be92cb06000."""
    candidate_models = [
        ("llama3.2:3b", "3B (Fast / Low-VRAM)", "2.0 GB"),
        ("llama3.1:latest", "8B (General Reasoning)", "4.7 GB"),
        ("qwen2.5-coder:7b", "7B (Instruction / Structured)", "4.7 GB"),
        ("qwen3.5:4b", "4B (Balanced)", "3.4 GB"),
    ]

    test_questions = [
        ("According to Epictetus in The Daily Stoic, what is the dichotomy of control and how does it distinguish what is up to us?", "Dichotomy of Control"),
        ("What does Marcus Aurelius advise about facing ungrateful, violent, or deceitful people when you wake up in the morning?", "Morning Meditation"),
        ("How does Seneca explain the shortness of life and why most people waste their finite years?", "Shortness of Life"),
        ("Explain the practice of Amor Fati and how a Stoic handles sudden unexpected adversity.", "Amor Fati"),
        ("Compare Epictetus's perspective as a former slave with Marcus Aurelius's responsibilities as Roman Emperor.", "Comparative Synthesis"),
    ]

    print("================================================================================")
    print(f"[START] DIRECT API CHAT COMPLETION BENCHMARK ON {session_id}")
    print(f"Gateway URL: {gateway_url} | Target Models: {[m[0] for m in candidate_models]}")
    print("================================================================================\n")

    model_eval_results: list[dict[str, Any]] = []

    for model_name, model_tier, model_size in candidate_models:
        print(f"--> Benchmarking Model: {model_name} ({model_tier})...")
        model_runs: list[dict[str, Any]] = []

        for q_text, q_label in test_questions:
            payload = {
                "query": q_text,
                "session_id": session_id,
                "model": model_name,
                "mode": "direct",
                "stream": False,
                "top_k": 10,
                "top_rerank": 4,
            }

            t0 = time.perf_counter()
            try:
                res = requests.post(f"{gateway_url}/api/v1/chat", json=payload, timeout=90)
                elapsed = time.perf_counter() - t0
                if res.status_code == 200:
                    data = res.json()
                    answer = data.get("answer", "")
                    citations = data.get("citations", [])
                    refused = data.get("refused", False)

                    words = len(answer.split())
                    tokens_est = int(words * 1.33)
                    tps = tokens_est / elapsed if elapsed > 0 else 0

                    has_stoic_keywords = any(kw in answer.lower() for kw in ["stoic", "epictetus", "seneca", "marcus", "aurelius", "control", "mind", "virtue"])
                    faithful = (len(citations) > 0) and has_stoic_keywords and not refused

                    model_runs.append({
                        "question": q_label,
                        "latency_sec": round(elapsed, 2),
                        "tokens_est": tokens_est,
                        "tokens_per_sec": round(tps, 1),
                        "citations_count": len(citations),
                        "refused": refused,
                        "faithful": faithful,
                        "answer_snippet": answer[:120] + "...",
                    })
                    print(f"   [{q_label}] Latency: {elapsed:5.2f}s | Speed: {tps:4.1f} tok/s | Citations: {len(citations)} | Faithful: {faithful}")
                else:
                    print(f"   [{q_label}] Error {res.status_code}: {res.text[:80]}")
            except Exception as e:
                print(f"   [{q_label}] Request failed: {e}")

        if model_runs:
            avg_lat = sum(r["latency_sec"] for r in model_runs) / len(model_runs)
            avg_tps = sum(r["tokens_per_sec"] for r in model_runs) / len(model_runs)
            faithfulness_rate = sum(1 for r in model_runs if r["faithful"]) / len(model_runs)

            model_eval_results.append({
                "model": model_name,
                "tier": model_tier,
                "disk_size": model_size,
                "avg_latency_sec": round(avg_lat, 2),
                "avg_tokens_per_sec": round(avg_tps, 1),
                "faithfulness_rate": round(faithfulness_rate * 100, 1),
                "runs": model_runs,
            })

    return model_eval_results


def main():
    print("Initializing Stores and Services for Stoic RAG Benchmark...")
    bm25 = BM25Store()
    qdrant = QdrantStore()
    reranker = FlashRankReranker()

    print(f"Loaded BM25 index with {len(bm25.corpus_chunks)} chunks.")
    print("Generating 4,000 Stoic evaluation queries...")
    queries = build_stoic_4000_queries()
    print(f"Synthesized {len(queries)} benchmark queries across 4 archetypes.\n")

    # 1. Run 4,000 retrieval evaluation
    retrieval_metrics = evaluate_retrievers(
        queries=queries,
        bm25=bm25,
        qdrant=qdrant,
        reranker=reranker,
        concurrency=8,
    )

    # 2. Run Direct API chat completion benchmark
    chat_results = evaluate_chat_models(
        session_id="sess_1be92cb06000",
        gateway_url="http://localhost:8010",
    )

    # 3. Export to JSON
    report_data = {
        "timestamp": time.time(),
        "task_id": "REC-62",
        "target_document": "The Daily Stoic_ 366 Meditations on Wisdom, Perseverance, and the Art of Living ( PDFDrive ).pdf",
        "session_id": "sess_1be92cb06000",
        "retrieval_benchmarks": retrieval_metrics,
        "chat_model_benchmarks": chat_results,
    }

    out_file = ROOT_DIR / "data" / "stoic_rag_benchmark_report.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)

    print(f"\nSuccessfully wrote comprehensive benchmark report to {out_file}")


if __name__ == "__main__":
    main()
