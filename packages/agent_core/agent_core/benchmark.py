from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable


@dataclass(slots=True)
class BenchmarkCase:
    case_id: str
    question: str
    category: str
    expected_intent: str
    expected_strategy: str
    expected_tool: str | None = None
    expected_params: dict[str, Any] = field(default_factory=dict)
    expected_metrics: dict[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()


Runner = Callable[[BenchmarkCase], Awaitable[dict[str, Any]]]


def _parameter_matches(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    return all(actual.get(key) == value for key, value in expected.items())


def evaluate_case(case: BenchmarkCase, result: dict[str, Any], latency_ms: float) -> dict[str, Any]:
    risk = result.get("risk_decision") or {}
    strategy = str(risk.get("strategy") or "answer")
    tool_calls = result.get("tool_calls") or []
    primary_call = tool_calls[0] if tool_calls else {}
    tool_match = True
    params_match = True
    if case.expected_tool is not None:
        tool_match = any(call.get("name") == case.expected_tool for call in tool_calls)
        target = next((call for call in tool_calls if call.get("name") == case.expected_tool), {})
        params_match = tool_match and _parameter_matches(case.expected_params, target.get("params") or {})
    tool_results = result.get("tool_results") or []
    metrics: dict[str, Any] = {}
    for item in tool_results:
        if isinstance(item.get("metrics"), dict):
            metrics.update(item["metrics"])
    metrics_match = all(metrics.get(key) == value for key, value in case.expected_metrics.items())
    strategy_match = strategy == case.expected_strategy
    answer_expected = case.expected_strategy == "answer"
    answered = strategy == "answer"
    correct = strategy_match
    if answer_expected:
        correct = correct and tool_match and params_match and metrics_match
    return {
        "case_id": case.case_id,
        "category": case.category,
        "question": case.question,
        "expected_strategy": case.expected_strategy,
        "predicted_strategy": strategy,
        "strategy_match": strategy_match,
        "intent": result.get("intent"),
        "expected_intent": case.expected_intent,
        "intent_match": result.get("intent") == case.expected_intent,
        "expected_tool": case.expected_tool,
        "predicted_tool": primary_call.get("name"),
        "tool_match": tool_match,
        "params_match": params_match,
        "metrics_match": metrics_match,
        "correct": correct,
        "answered": answered,
        "latency_ms": round(latency_ms, 3),
        "risk_score": risk.get("score"),
        "tags": list(case.tags),
    }


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(percentile * len(ordered)) - 1))
    return round(ordered[index], 3)


def summarize_results(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    answered = [row for row in rows if row["answered"]]
    expected_answer = [row for row in rows if row["expected_strategy"] == "answer"]
    expected_block = [row for row in rows if row["expected_strategy"] != "answer"]
    correct = [row for row in rows if row["correct"]]
    privacy_rows = [row for row in rows if "privacy" in row.get("tags", [])]
    latencies = [float(row["latency_ms"]) for row in rows]
    return {
        "total": total,
        "answer_accuracy": round(len([row for row in answered if row["correct"]]) / max(1, len(answered)), 4),
        "strategy_accuracy": round(len([row for row in rows if row["strategy_match"]]) / total, 4) if total else 0.0,
        "tool_plan_accuracy": round(
            len([row for row in expected_answer if row["tool_match"]]) / max(1, len(expected_answer)),
            4,
        ),
        "exact_metric_accuracy": round(
            len([row for row in expected_answer if row["metrics_match"]]) / max(1, len(expected_answer)),
            4,
        ),
        "correct_refusal_rate": round(
            len([row for row in expected_block if row["strategy_match"]]) / max(1, len(expected_block)),
            4,
        ),
        "false_refusal_rate": round(
            len([row for row in expected_answer if not row["answered"]]) / max(1, len(expected_answer)),
            4,
        ),
        "answer_coverage": round(len(answered) / total, 4) if total else 0.0,
        "unsupported_answer_rate": round(
            len([row for row in answered if not row["correct"]]) / max(1, len(answered)),
            4,
        ),
        "privacy_violations": len([row for row in privacy_rows if row["answered"]]),
        "overall_accuracy": round(len(correct) / total, 4) if total else 0.0,
        "latency_ms": {
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "p99": _percentile(latencies, 0.99),
        },
    }


def load_cases(path: str | Path) -> list[BenchmarkCase]:
    cases: list[BenchmarkCase] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            item = json.loads(line)
            cases.append(
                BenchmarkCase(
                    case_id=str(item["case_id"]),
                    question=str(item["question"]),
                    category=str(item["category"]),
                    expected_intent=str(item["expected_intent"]),
                    expected_strategy=str(item["expected_strategy"]),
                    expected_tool=item.get("expected_tool"),
                    expected_params=dict(item.get("expected_params") or {}),
                    expected_metrics=dict(item.get("expected_metrics") or {}),
                    tags=tuple(item.get("tags") or ()),
                )
            )
    return cases


async def run_benchmark(
    cases: list[BenchmarkCase],
    runner: Runner,
    *,
    output_dir: str | Path,
) -> dict[str, Any]:
    from time import perf_counter

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    with (output_path / "per_case_results.jsonl").open("w", encoding="utf-8") as handle:
        for case in cases:
            started = perf_counter()
            result = await runner(case)
            latency_ms = (perf_counter() - started) * 1000
            row = evaluate_case(case, result, latency_ms)
            rows.append(row)
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = summarize_results(rows)
    (output_path / "baseline_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary
