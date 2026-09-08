"""Automated CI/CD evaluation regression gate for Hybrid RAG quality assurance."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tests.eval.eval_harness import run_evaluation

# Strict production regression thresholds
THRESHOLDS = {
    "hit_rate_at_1": 0.85,
    "hit_rate_at_3": 0.90,
    "mrr": 0.90,
    "citation_validity_rate": 1.00,
    "avg_faithfulness": 0.85,
}


def run_regression_gate() -> bool:
    print("=" * 65)
    print("EXECUTING CI/CD RAG EVALUATION REGRESSION GATE")
    print("=" * 65)

    results = run_evaluation()

    actual_hit1 = results["hit_rate_at_1"]["reranked"]
    actual_hit3 = results["hit_rate_at_3"]["reranked"]
    actual_mrr = results["mrr"]["reranked"]
    actual_cites = results["citation_validity_rate"]
    actual_faith = results["avg_faithfulness"]

    checks = [
        ("HitRate@1 (>= 85%)", actual_hit1 >= THRESHOLDS["hit_rate_at_1"], f"{actual_hit1 * 100:.1f}%"),
        ("HitRate@3 (>= 90%)", actual_hit3 >= THRESHOLDS["hit_rate_at_3"], f"{actual_hit3 * 100:.1f}%"),
        ("MRR (>= 0.90)", actual_mrr >= THRESHOLDS["mrr"], f"{actual_mrr:.4f}"),
        ("Citation Validity (== 100%)", actual_cites >= THRESHOLDS["citation_validity_rate"], f"{actual_cites * 100:.1f}%"),
        ("Faithfulness (>= 85%)", actual_faith >= THRESHOLDS["avg_faithfulness"], f"{actual_faith * 100:.1f}%"),
    ]

    all_passed = True
    print(f"{'Metric':<30} | {'Status':<8} | {'Score'}")
    print("-" * 65)
    for name, passed, score in checks:
        status_str = "PASS" if passed else "FAIL"
        print(f"{name:<30} | {status_str:<8} | {score}")
        if not passed:
            all_passed = False

    print("=" * 65)
    if all_passed:
        print(">>> SUCCESS: ALL RAG RETRIEVAL & QUALITY REGRESSION GATES PASSED! <<<")
    else:
        print(">>> FAILURE: RAG REGRESSION DETECTED. GATES FAILED! <<<")
    print("=" * 65)

    return all_passed


if __name__ == "__main__":
    passed = run_regression_gate()
    sys.exit(0 if passed else 1)
