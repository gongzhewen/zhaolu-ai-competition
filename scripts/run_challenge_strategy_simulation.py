from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from time import perf_counter
from typing import Any

from agent_core.privacy import assess_request_privacy
from agent_core.registry import DATA_INTENTS
from agent_core.router import RuleRouter
from agent_core.semantics import compile_semantic_slots, estimate_slot_ambiguity


def predict_strategy(
    question: str,
    *,
    latest_year: int = 2026,
    router: RuleRouter | None = None,
    enable_ambiguity: bool = True,
    enable_privacy: bool = True,
) -> dict[str, Any]:
    router = router or RuleRouter()
    decision = router.route(question, latest_year=latest_year)
    decision.params.setdefault("query", question)
    slots = compile_semantic_slots(question, decision)
    ambiguity = estimate_slot_ambiguity(question, decision, slots)
    privacy = assess_request_privacy(
        question,
        intent=decision.intent,
        context_values={"can_lookup_students": True},
    )
    strategy = "answer"
    if (enable_privacy and not privacy.allowed) or decision.intent == "refuse":
        strategy = "no_permission"
    elif decision.intent == "out_of_scope":
        strategy = "out_of_scope"
    elif enable_ambiguity and ambiguity.requires_clarification and decision.intent in DATA_INTENTS:
        strategy = "clarify"
    elif decision.clarification:
        strategy = "clarify"
    return {
        "intent": decision.intent,
        "strategy": strategy,
        "ambiguity_score": ambiguity.score,
        "clarification": ambiguity.clarification or decision.clarification,
        "metrics": list(slots.metrics),
    }


def evaluate_cases(
    cases: list[dict[str, Any]],
    *,
    latest_year: int = 2026,
    enable_ambiguity: bool = True,
    enable_privacy: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    router = RuleRouter()
    rows: list[dict[str, Any]] = []
    for case in cases:
        started = perf_counter()
        prediction = predict_strategy(
            case["question"],
            latest_year=latest_year,
            router=router,
            enable_ambiguity=enable_ambiguity,
            enable_privacy=enable_privacy,
        )
        latency_ms = (perf_counter() - started) * 1000
        rows.append(
            {
                "case_id": case["case_id"],
                "category": case["category"],
                "question": case["question"],
                "expected_intent": case["expected_intent"],
                "predicted_intent": prediction["intent"],
                "intent_match": prediction["intent"] == case["expected_intent"],
                "expected_strategy": case["expected_strategy"],
                "predicted_strategy": prediction["strategy"],
                "strategy_match": prediction["strategy"] == case["expected_strategy"],
                "ambiguity_score": prediction["ambiguity_score"],
                "clarification": prediction["clarification"],
                "latency_ms": round(latency_ms, 3),
                "tags": list(case.get("tags") or []),
            }
        )
    total = len(rows)
    matched = sum(1 for row in rows if row["strategy_match"])
    categories = Counter(row["category"] for row in rows)
    category_matches = Counter(row["category"] for row in rows if row["strategy_match"])
    latencies = sorted(float(row["latency_ms"]) for row in rows)
    def percentile(value: float) -> float:
        if not latencies:
            return 0.0
        index = min(len(latencies) - 1, max(0, math.ceil(value * len(latencies)) - 1))
        return round(latencies[index], 3)
    summary = {
        "evaluation_kind": "route_semantics_privacy_simulation",
        "end_to_end": False,
        "gold_dataset": False,
        "database_connected": False,
        "expected_metrics_present": any(bool(case.get("expected_metrics")) for case in cases),
        "total": total,
        "strategy_matches": matched,
        "strategy_match_rate": round(matched / total, 4) if total else 0.0,
        "intent_matches": sum(1 for row in rows if row["intent_match"]),
        "by_category": {
            category: {
                "total": count,
                "strategy_matches": category_matches[category],
                "strategy_match_rate": round(category_matches[category] / count, 4),
            }
            for category, count in sorted(categories.items())
        },
        "latency_ms": {
            "p50": percentile(0.50),
            "p95": percentile(0.95),
            "p99": percentile(0.99),
        },
        "boundary": "本结果仅验证规则路由、槽位歧义和隐私拒答策略，不代表真实 MySQL 端到端回答准确率。",
    }
    return rows, summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--challenge", default="evaluation/challenge_set_v1.jsonl")
    parser.add_argument("--output", default="artifacts/G1/challenge_strategy_simulation.json")
    parser.add_argument("--latest-year", type=int, default=2026)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    challenge_path = root / args.challenge
    output_path = root / args.output
    cases = [
        json.loads(line)
        for line in challenge_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows, summary = evaluate_cases(cases, latest_year=args.latest_year)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    per_case_path = output_path.with_name(output_path.stem + "_per_case.jsonl")
    per_case_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
