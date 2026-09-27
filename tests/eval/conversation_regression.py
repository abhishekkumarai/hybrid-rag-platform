"""Multi-turn answer-quality regression suite against a live gateway (IRA-19).

Each case opens a fresh project scoped to one document, plays a conversation, and checks only the last
answer. Small models are sampled, so every case runs several trials and must reach a pass rate; a single
run proves nothing either way. The cases pin the failures this area has actually had:

- IRA-19: a superlative over a table ("which device has the highest throughput?") was answered from
  the first plausible row -- 0/24 on llama3.2:3b before tables carried computed column extremes.
- IRA-17: a follow-up about a new person re-answered the previous turn's subject.
- IRA-18: an off-corpus question must get the persona's exact refusal, not a guess.

Needs the gateway (default http://127.0.0.1:8010), Qdrant and Ollama with both documents indexed.
Usage: python tests/eval/conversation_regression.py [--base URL] [--model M] [--trials N]
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

import requests

BENCHMARK_DOC = "multimodal_hardware_benchmark.pdf"
STOIC_DOC = "The Daily Stoic_ 366 Meditations on Wisdom, Perseverance, and the Art of Living ( PDFDrive ).pdf"
REFUSAL = "do not contain"


@dataclass
class Case:
    name: str
    doc: str
    turns: list[str]
    must_contain: list[str] = field(default_factory=list)
    must_not_contain: list[str] = field(default_factory=list)
    min_pass_rate: float = 0.8

    def check(self, answer: str) -> bool:
        a = answer.lower()
        return all(m in a for m in self.must_contain) and not any(m in a for m in self.must_not_contain)


CASES = [
    Case("IRA-19 highest throughput after a comparison turn", BENCHMARK_DOC,
         ["Compare the RTX 3050 and RTX 4060 laptops.", "Which device has the highest throughput?"],
         must_contain=["a100", "110"]),
    Case("IRA-19 lowest dense latency", BENCHMARK_DOC,
         ["Which device has the lowest dense latency?"], must_contain=["a100", "4.2"]),
    Case("IRA-19 most VRAM", BENCHMARK_DOC,
         ["Which device uses the most VRAM?"], must_contain=["a100", "40"]),
    Case("IRA-17 follow-up switches person", STOIC_DOC,
         ["What does Seneca say about anger?", "What does Epictetus say about what is within our control?"],
         must_contain=["epictetus"], must_not_contain=["anger"]),
    Case("IRA-18 off-corpus refusal", BENCHMARK_DOC,
         ["What is the retail price of the RTX 4060 laptop?"], must_contain=[REFUSAL]),
]


def run_case(base: str, model: str, case: Case) -> tuple[bool, str]:
    session = requests.post(f"{base}/sessions", json={
        "title": f"[eval] {case.name}",
        "parameters": {"model": model, "retrieval_mode": "auto", "temperature": 0.2},
    }, timeout=30).json()
    sid = session["id"]
    try:
        requests.post(f"{base}/sessions/{sid}/files", json={"files": [case.doc]}, timeout=30)
        answer = ""
        for query in case.turns:
            resp = requests.post(f"{base}/chat", json={
                "query": query, "session_id": sid, "stream": False, "model": model, "mode": "auto",
            }, timeout=300).json()
            answer = (resp.get("raw_answer") or resp.get("answer") or "").strip()
        return case.check(answer), answer
    finally:
        requests.delete(f"{base}/sessions/{sid}", timeout=30)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="http://127.0.0.1:8010/api/v1")
    parser.add_argument("--model", default="llama3.2:3b")
    parser.add_argument("--trials", type=int, default=5)
    args = parser.parse_args()

    failed = []
    for case in CASES:
        passes, sample_fail = 0, ""
        for _ in range(args.trials):
            ok, answer = run_case(args.base, args.model, case)
            passes += ok
            if not ok and not sample_fail:
                sample_fail = answer[:160].replace("\n", " ")
        rate = passes / args.trials
        verdict = "PASS" if rate >= case.min_pass_rate else "FAIL"
        print(f"[{verdict}] {case.name}: {passes}/{args.trials} (need {case.min_pass_rate:.0%})")
        if sample_fail:
            print(f"        e.g. {sample_fail}")
        if verdict == "FAIL":
            failed.append(case.name)

    print(f"\n{len(CASES) - len(failed)}/{len(CASES)} cases passed on {args.model}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
