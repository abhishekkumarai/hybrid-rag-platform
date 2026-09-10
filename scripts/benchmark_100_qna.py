"""
benchmark_100_qna.py - 100-query RAG benchmark.
Run: docker exec rag_gateway python scripts/benchmark_100_qna.py
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from contracts.retrieval import SearchQuery
from services.common.config import load_config
from services.indexing.service import IndexingService
from services.retrieval.service import RetrievalService

config = load_config()

QUERIES: list[tuple[str, str, str]] = [
    ("What are Abhishek Kumar core GenAI skills and frameworks?", "abhishek_kumar", "scoped"),
    ("List all companies where Abhishek has worked.", "abhishek_kumar", "scoped"),
    ("What LLM platforms and vector databases does Abhishek know?", "abhishek_kumar", "scoped"),
    ("What is Abhishek total years of experience in AI and ML?", "abhishek_kumar", "scoped"),
    ("What are the highlights of Abhishek most recent role?", "abhishek_kumar", "scoped"),
    ("Does Abhishek have experience with RAG or retrieval systems?", "abhishek_kumar", "scoped"),
    ("What certifications or education does Abhishek hold?", "abhishek_kumar", "scoped"),
    ("Summarize this resume.", "abhishek_kumar", "scoped"),
    ("What cloud platforms is Abhishek experienced with?", "abhishek_kumar", "scoped"),
    ("Tell me about the document.", "abhishek_kumar", "scoped"),
    ("What programming languages does Abhishek use?", "abhishek_kumar", "scoped"),
    ("What is the most recent job title on this resume?", "abhishek_kumar", "scoped"),
    ("What is the account number shown in the bank statement?", "acct_statement", "scoped"),
    ("What transactions are listed in November 2024?", "acct_statement", "scoped"),
    ("What is the closing balance in the statement?", "acct_statement", "scoped"),
    ("Are there any debit transactions above 10000?", "acct_statement", "scoped"),
    ("What bank issued this account statement?", "acct_statement", "scoped"),
    ("List any credit entries in the statement.", "acct_statement", "scoped"),
    ("What is the account holder name?", "acct_statement", "scoped"),
    ("What is the opening balance in this statement?", "acct_statement", "scoped"),
    ("Summarize the bank statement.", "acct_statement", "scoped"),
    ("Tell me about this document.", "acct_statement", "scoped"),
    ("What is the total number of transactions in the statement?", "acct_statement", "scoped"),
    ("What is the statement period or date range?", "acct_statement", "scoped"),
    ("What is the total EPF contribution shown in the 2025 passbook?", "bgbng13885620000013678_2025", "scoped"),
    ("What is the employee UAN number in the passbook?", "bgbng13885620000013678_2025", "scoped"),
    ("What employer contributions are listed?", "bgbng13885620000013678_2025", "scoped"),
    ("What is the closing balance in the EPF passbook?", "bgbng13885620000013678_2025", "scoped"),
    ("What establishment name is on this EPF passbook?", "bgbng13885620000013678_2025", "scoped"),
    ("Summarize this EPF passbook.", "bgbng13885620000013678_2025", "scoped"),
    ("What is the opening EPF balance in 2025?", "bgbng13885620000013678_2025", "scoped"),
    ("What interest was credited in the 2025 EPF passbook?", "bgbng13885620000013678_2025", "scoped"),
    ("Tell me about this EPF 2025 document.", "bgbng13885620000013678_2025", "scoped"),
    ("What is the EPF balance as of 2021?", "bgbng20125150000010074_2021", "scoped"),
    ("What contributions were made in the 2021 EPF passbook?", "bgbng20125150000010074_2021", "scoped"),
    ("Tell me about this EPF document.", "bgbng20125150000010074_2021", "scoped"),
    ("What is the member ID in this passbook?", "bgbng20125150000010074_2021", "scoped"),
    ("What employer share is recorded in 2021?", "bgbng20125150000010074_2021", "scoped"),
    ("Summarize the 2021 EPF passbook.", "bgbng20125150000010074_2021", "scoped"),
    ("What is the EPF balance as of 2022?", "bgbng20125150000010074_2022", "scoped"),
    ("What contributions were made in the 2022 EPF passbook?", "bgbng20125150000010074_2022", "scoped"),
    ("Summarize the 2022 EPF passbook.", "bgbng20125150000010074_2022", "scoped"),
    ("Tell me about this document.", "bgbng20125150000010074_2022", "scoped"),
    ("What interest was earned in the 2022 EPF passbook?", "bgbng20125150000010074_2022", "scoped"),
    ("What is the closing balance for 2022?", "bgbng20125150000010074_2022", "scoped"),
    ("What income is reported in the IT certificate?", "it_certificate_687818458", "scoped"),
    ("What tax was deducted as per this IT certificate?", "it_certificate_687818458", "scoped"),
    ("What is the PAN number shown?", "it_certificate_687818458", "scoped"),
    ("What assessment year does this certificate cover?", "it_certificate_687818458", "scoped"),
    ("Who issued this IT certificate?", "it_certificate_687818458", "scoped"),
    ("Summarize this IT certificate.", "it_certificate_687818458", "scoped"),
    ("What income is reported in the second IT certificate?", "it_certificate_687818458_2", "scoped"),
    ("What TDS was deducted in the second certificate?", "it_certificate_687818458_2", "scoped"),
    ("What financial year does the second certificate cover?", "it_certificate_687818458_2", "scoped"),
    ("Tell me about this tax document.", "it_certificate_687818458_2", "scoped"),
    ("What columns are present in the spreadsheet?", "file_example_xls", "scoped"),
    ("How many rows of data are in this CSV file?", "file_example_xls", "scoped"),
    ("What numeric values are in the data?", "file_example_xls", "scoped"),
    ("Summarize the data in this document.", "file_example_xls", "scoped"),
    ("Tell me about this file.", "file_example_xls", "scoped"),
    ("What GPU models are benchmarked in the document?", "multimodal_hardware_benchmark", "scoped"),
    ("What is the VRAM capacity of the RTX 3050 laptop GPU?", "multimodal_hardware_benchmark", "scoped"),
    ("Which model achieved the highest throughput in the benchmark?", "multimodal_hardware_benchmark", "scoped"),
    ("What inference frameworks are used in the benchmark?", "multimodal_hardware_benchmark", "scoped"),
    ("What LLM models were tested in the hardware benchmark?", "multimodal_hardware_benchmark", "scoped"),
    ("Summarize the hardware benchmark results.", "multimodal_hardware_benchmark", "scoped"),
    ("What is the tokens per second for llama3 on RTX 3050?", "multimodal_hardware_benchmark", "scoped"),
    ("What are the memory usage numbers in the benchmark?", "multimodal_hardware_benchmark", "scoped"),
    ("Tell me about this document.", "multimodal_hardware_benchmark", "scoped"),
    ("What services make up the RAG platform architecture?", "system_architecture_spec", "scoped"),
    ("What database ports are listed in the architecture spec?", "system_architecture_spec", "scoped"),
    ("What is the role of the Redis queue in the system?", "system_architecture_spec", "scoped"),
    ("How does the ingestion pipeline work?", "system_architecture_spec", "scoped"),
    ("What retrieval modes does the system support?", "system_architecture_spec", "scoped"),
    ("What is the purpose of the CRAG evaluator?", "system_architecture_spec", "scoped"),
    ("What vector database is used and why?", "system_architecture_spec", "scoped"),
    ("Describe the Langflow integration.", "system_architecture_spec", "scoped"),
    ("What hardware is this system designed for?", "system_architecture_spec", "scoped"),
    ("Summarize the system architecture.", "system_architecture_spec", "scoped"),
    ("What is the BM25 index used for?", "system_architecture_spec", "scoped"),
    ("How are documents chunked in the pipeline?", "system_architecture_spec", "scoped"),
    ("What is the role of the scheduler service?", "system_architecture_spec", "scoped"),
    ("How does session scoping work in the platform?", "system_architecture_spec", "scoped"),
    ("What is the knowledge graph used for?", "system_architecture_spec", "scoped"),
    ("Tell me about this architecture document.", "system_architecture_spec", "scoped"),
    ("Who is Abhishek Kumar and what documents are in this knowledge base?", "", "global"),
    ("What EPF accounts are indexed?", "", "global"),
    ("What tax documents exist in this knowledge base?", "", "global"),
    ("What financial documents are available?", "", "global"),
    ("Summarize all indexed documents.", "", "global"),
    ("What GPU hardware is being used?", "", "global"),
    ("What platform architecture is described?", "", "global"),
    ("What are the latest AI skills mentioned across all documents?", "", "global"),
    ("Are there any spreadsheet or tabular documents?", "", "global"),
    ("List all documents in the knowledge base.", "", "global"),
    ("What is the capital of France?", "", "global"),
    ("Give me a recipe for chocolate cake.", "", "global"),
    ("Who won the FIFA World Cup 2022?", "", "global"),
    ("Explain quantum entanglement.", "", "global"),
    ("What is the stock price of Apple today?", "", "global"),
]

assert len(QUERIES) == 100, f"Expected 100 queries, got {len(QUERIES)}"
MODES = ["direct", "agentic", "graph"]


def _resolve_doc_ids(bm25, stem: str) -> list[str] | None:
    if not stem:
        return None
    matched = bm25.resolve_matching_doc_ids([stem])
    if matched:
        return matched
    matched_chunks = {c["doc_id"] for c in getattr(bm25, "corpus_chunks", []) if stem in c.get("doc_id", "")}
    return list(matched_chunks) if matched_chunks else None


def _run_one(retrieval, query_text: str, doc_ids, mode: str, q_idx: int) -> dict:
    t0 = time.perf_counter()
    sq = SearchQuery(
        query_text=query_text, top_k=20, top_rerank=6,
        min_rerank_score=0.15, doc_ids=doc_ids, retrieval_mode=mode,
    )
    try:
        result = retrieval.retrieve(sq)
        ms = (time.perf_counter() - t0) * 1000
        return {"q_idx": q_idx, "query": query_text, "mode": mode,
                "scope": "scoped" if doc_ids else "global",
                "target_doc_stem": (doc_ids[0][:30] if doc_ids else ""),
                "latency_ms": round(ms, 1), "top_score": round(result.top_score, 4),
                "refused": result.refused, "candidates": len(result.candidates),
                "citations": len(result.citations), "error": None}
    except Exception as exc:
        ms = (time.perf_counter() - t0) * 1000
        return {"q_idx": q_idx, "query": query_text, "mode": mode,
                "scope": "scoped" if doc_ids else "global",
                "target_doc_stem": (doc_ids[0][:30] if doc_ids else ""),
                "latency_ms": round(ms, 1), "top_score": 0.0,
                "refused": True, "candidates": 0, "citations": 0,
                "error": str(exc)[:120]}


def _pct(data: list[float], p: float) -> float:
    if not data:
        return 0.0
    ds = sorted(data)
    idx = (len(ds) - 1) * p / 100
    lo = int(idx)
    hi = min(lo + 1, len(ds) - 1)
    return ds[lo] + (ds[hi] - ds[lo]) * (idx - lo)


def stats_for(rows: list[dict]) -> dict:
    n = len(rows)
    refused = sum(1 for r in rows if r["refused"])
    passed = n - refused
    lats = [r["latency_ms"] for r in rows]
    cits = [r["citations"] for r in rows if not r["refused"]]
    return {"n": n, "passed": passed, "refused": refused,
            "pass_rate": 100 * passed / n if n else 0,
            "avg_ms": statistics.mean(lats) if lats else 0,
            "p50_ms": _pct(lats, 50), "p95_ms": _pct(lats, 95),
            "avg_cit": statistics.mean(cits) if cits else 0}


def main() -> None:
    print("=" * 72)
    print("  RAG Platform -- 100-Query Benchmark  (direct | agentic | graph)")
    print("=" * 72)

    indexing = IndexingService(
        in_memory=False,
        qdrant_host=config.storage.qdrant_host,
        qdrant_port=config.storage.qdrant_port,
    )
    retrieval = RetrievalService(
        qdrant_store=indexing.qdrant, bm25_store=indexing.bm25,
        ollama_url=config.hardware.ollama_base_url)
    bm25 = indexing.bm25
    total_runs = len(QUERIES) * len(MODES)
    all_results: list[dict] = []
    run_no = 0

    for q_idx, (qt, stem, _scope) in enumerate(QUERIES, start=1):
        doc_ids = _resolve_doc_ids(bm25, stem) if stem else None
        for mode in MODES:
            run_no += 1
            scope = "scoped" if doc_ids else "global"
            print(f"[{run_no:>3}/{total_runs}] {mode:7s}|{scope:6s} Q{q_idx:>3}: {qt[:50]!r}", flush=True)
            row = _run_one(retrieval, qt, doc_ids, mode, q_idx)
            all_results.append(row)
            st = "REFUSED" if row["refused"] else f"OK score={row['top_score']:.3f} cit={row['citations']}"
            print(f"         -> {st}  {row['latency_ms']:.0f}ms", flush=True)

    out = Path("data/ragops/benchmark_100_results.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResults -> {out}\n")
    print("=" * 72)
    print("  AGGREGATE STATISTICS")
    print("=" * 72)

    ov = stats_for(all_results)
    print(f"\n  Total   : {ov['n']}  ({len(QUERIES)} q x {len(MODES)} modes)")
    print(f"  Passed  : {ov['passed']}  ({ov['pass_rate']:.1f}%)")
    print(f"  Refused : {ov['refused']}  ({100 - ov['pass_rate']:.1f}%)")
    print(f"  Avg lat : {ov['avg_ms']:.0f} ms   p50={ov['p50_ms']:.0f}ms   p95={ov['p95_ms']:.0f}ms")
    print(f"  Avg cit : {ov['avg_cit']:.2f}  (passing only)")

    fmt = "{:<10} {:>5} {:>7} {:>8} {:>8} {:>8} {:>8}"
    print(f"\n{'-'*60}\n  PER-MODE\n{'-'*60}")
    print(fmt.format("MODE","N","PASSED","REFUSED","PASS%","AVG_ms","P95_ms"))
    print("-" * 60)
    for m in MODES:
        s = stats_for([r for r in all_results if r["mode"] == m])
        print(fmt.format(m, s["n"], s["passed"], s["refused"],
                         f"{s['pass_rate']:.1f}%", f"{s['avg_ms']:.0f}", f"{s['p95_ms']:.0f}"))

    print(f"\n{'-'*60}\n  PER-SCOPE\n{'-'*60}")
    for sc in ("scoped", "global"):
        s = stats_for([r for r in all_results if r["scope"] == sc])
        print(f"  {sc.upper():<8} n={s['n']} passed={s['passed']} "
              f"refused={s['refused']} {s['pass_rate']:.1f}% avg={s['avg_ms']:.0f}ms")

    oos = set(range(96, 101))
    oos_rows = [r for r in all_results if r["q_idx"] in oos]
    n_ref = sum(1 for r in oos_rows if r["refused"])
    guard = "PASS" if n_ref == len(oos_rows) else "PARTIAL"
    print(f"\n  OOS GUARD: {n_ref}/{len(oos_rows)} refused [{guard}]")

    bad = [r for r in all_results
           if r["refused"] and r["scope"] == "scoped" and r["q_idx"] not in oos and not r.get("error")]
    if bad:
        print(f"\n  UNEXPECTED REFUSALS ({len(bad)}):")
        for r in bad[:15]:
            print(f"    Q{r['q_idx']:>3} [{r['mode']:7s}] score={r['top_score']:.3f} {r['query'][:60]!r}")

    errs = [r for r in all_results if r.get("error")]
    if errs:
        print(f"\n  ERRORS ({len(errs)}):")
        for r in errs[:10]:
            print(f"    Q{r['q_idx']:>3} [{r['mode']:7s}] {r['error']}")

    print(f"\n{'='*72}\n  Benchmark complete.\n{'='*72}\n")


if __name__ == "__main__":
    main()
