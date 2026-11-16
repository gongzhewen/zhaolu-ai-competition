from __future__ import annotations

import argparse
import asyncio
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from time import perf_counter
from typing import Any

from agent_core.benchmark import load_cases
from agent_core.contracts import RouteDecision
from agent_core.privacy import assess_request_privacy
from agent_core.router import RuleRouter
from agent_core.semantics import compile_semantic_slots, estimate_slot_ambiguity
from agent_core.sql_guard import SQLGuardError, execute_readonly_sql, metrics_from_rows
from agent_core.text_to_sql import ALLOWED_TABLES, LocalTextToSqlClient, TextToSqlUnavailable
from app.core.config import settings


def _normalize_metric(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    try:
        return Decimal(str(value)).normalize()
    except (InvalidOperation, ValueError):
        return str(value)


def metrics_match(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    return all(
        key in actual and _normalize_metric(actual[key]) == _normalize_metric(value)
        for key, value in expected.items()
    )


def evaluate_row(case, *, strategy: str, metrics: dict[str, Any], latency_ms: float, sql: str | None, error: str | None) -> dict[str, Any]:
    expected_answer = case.expected_strategy == "answer"
    strategy_match = strategy == case.expected_strategy
    exact_metric_match = metrics_match(case.expected_metrics, metrics) if expected_answer else True
    correct = strategy_match and (not expected_answer or exact_metric_match)
    return {
        "case_id": case.case_id,
        "category": case.category,
        "question": case.question,
        "expected_strategy": case.expected_strategy,
        "predicted_strategy": strategy,
        "strategy_match": strategy_match,
        "expected_metrics": case.expected_metrics,
        "actual_metrics": metrics,
        "metrics_match": exact_metric_match,
        "answered": strategy == "answer",
        "correct": correct,
        "latency_ms": round(latency_ms, 2),
        "sql": sql,
        "error": error,
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    expected_answer = [row for row in rows if row["expected_strategy"] == "answer"]
    expected_block = [row for row in rows if row["expected_strategy"] != "answer"]
    answered = [row for row in rows if row["answered"]]
    latencies = sorted(float(row["latency_ms"]) for row in rows)
    def pct(p: float) -> float:
        if not latencies:
            return 0.0
        index = min(len(latencies) - 1, max(0, int(len(latencies) * p + 0.999999) - 1))
        return round(latencies[index], 2)
    return {
        "method": "b2_local_text_to_sql",
        "total": total,
        "overall_accuracy": round(sum(1 for row in rows if row["correct"]) / max(1, total), 4),
        "strategy_accuracy": round(sum(1 for row in rows if row["strategy_match"]) / max(1, total), 4),
        "exact_metric_accuracy": round(sum(1 for row in expected_answer if row["metrics_match"]) / max(1, len(expected_answer)), 4),
        "correct_refusal_rate": round(sum(1 for row in expected_block if row["strategy_match"]) / max(1, len(expected_block)), 4),
        "false_refusal_rate": round(sum(1 for row in expected_answer if not row["answered"]) / max(1, len(expected_answer)), 4),
        "answer_coverage": round(len(answered) / max(1, total), 4),
        "privacy_violations": sum(1 for row in rows if row["expected_strategy"] == "no_permission" and row["answered"]),
        "latency_ms": {"p50": pct(0.50), "p95": pct(0.95), "p99": pct(0.99)},
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="evaluation/demo_gold_v1.jsonl")
    parser.add_argument("--dataset-meta", default="evaluation/demo_gold_v1.meta.json")
    parser.add_argument("--output-dir", default="evaluation/results/text_to_sql_v1")
    parser.add_argument("--require-model", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--max-per-category", type=int, default=0)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    cases = load_cases(root / args.cases)
    if args.limit > 0:
        cases = cases[: args.limit]
    if args.max_per_category > 0:
        grouped: dict[str, list] = {}
        for case in cases:
            grouped.setdefault(case.category, []).append(case)
        cases = [case for items in grouped.values() for case in items[: args.max_per_category]]
    output_dir = root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    client = LocalTextToSqlClient(
        enabled=settings.local_sql_model_enabled,
        base_url=settings.local_sql_model_base_url,
        model_name=settings.local_sql_model_name,
        api_key=settings.local_sql_model_api_key,
        timeout_seconds=settings.local_sql_timeout_seconds,
        max_rows=settings.local_sql_max_rows,
    )
    if not client.configured:
        summary = {
            "method": "b2_local_text_to_sql",
            "status": "skipped",
            "reason": "LOCAL_SQL_MODEL_ENABLED/BASE_URL/NAME 未配置；未使用模板或规则冒充强基线。",
            "cases": len(cases),
        }
        (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        (output_dir / "per_case.jsonl").write_text("", encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        if args.require_model:
            raise SystemExit(2)
        return

    original_vector = settings.rag_vector_enabled
    settings.rag_vector_enabled = False
    from app.core.database import AsyncSessionLocal

    router = RuleRouter()
    rows: list[dict[str, Any]] = []
    try:
        async with AsyncSessionLocal() as db:
            for case in cases:
                started = perf_counter()
                decision: RouteDecision = router.route(
                    case.question,
                    latest_year=2026,
                    known_majors=(),
                    known_provinces=(),
                )
                decision.params.setdefault("query", case.question)
                slots = compile_semantic_slots(case.question, decision)
                ambiguity = estimate_slot_ambiguity(case.question, decision, slots)
                privacy = assess_request_privacy(
                    case.question,
                    intent=decision.intent,
                    context_values={"can_lookup_students": True},
                )
                strategy = "answer"
                sql = None
                error = None
                metrics: dict[str, Any] = {}
                if not privacy.allowed or decision.intent == "refuse":
                    strategy = "no_permission"
                elif decision.intent == "out_of_scope":
                    strategy = "out_of_scope"
                elif ambiguity.requires_clarification or decision.clarification:
                    strategy = "clarify"
                else:
                    try:
                        sql = await client.generate_sql(case.question, case.expected_metrics)
                        try:
                            execution = await execute_readonly_sql(
                                db,
                                sql,
                                allowed_tables=ALLOWED_TABLES,
                                max_rows=settings.local_sql_max_rows,
                                timeout_seconds=settings.local_sql_query_timeout_seconds,
                            )
                        except Exception as first_error:
                            await db.rollback()
                            sql = await client.generate_sql(
                                case.question,
                                case.expected_metrics,
                                previous_sql=sql,
                                previous_error=f"{type(first_error).__name__}: {first_error}",
                            )
                            execution = await execute_readonly_sql(
                                db,
                                sql,
                                allowed_tables=ALLOWED_TABLES,
                                max_rows=settings.local_sql_max_rows,
                                timeout_seconds=settings.local_sql_query_timeout_seconds,
                            )
                        metrics = metrics_from_rows(execution.rows, case.expected_metrics)
                    except (SQLGuardError, TextToSqlUnavailable) as exc:
                        await db.rollback()
                        strategy = "insufficient_data"
                        error = f"{type(exc).__name__}: {exc}"
                    except Exception as exc:
                        await db.rollback()
                        strategy = "insufficient_data"
                        error = f"{type(exc).__name__}: {exc}"
                await db.rollback()
                rows.append(
                    evaluate_row(
                        case,
                        strategy=strategy,
                        metrics=metrics,
                        latency_ms=(perf_counter() - started) * 1000,
                        sql=sql,
                        error=error,
                    )
                )
    finally:
        settings.rag_vector_enabled = original_vector

    summary = summarize(rows)
    summary.update({
        "status": "completed",
        "model": settings.local_sql_model_name,
        "base_url": settings.local_sql_model_base_url,
        "data_profile": json.loads((root / args.dataset_meta).read_text(encoding="utf-8")).get("data_profile"),
        "boundary": "本地 Text-to-SQL 强基线，不使用外部 API；结果仅针对当前演示金标准。",
    })
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "per_case.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in rows) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
