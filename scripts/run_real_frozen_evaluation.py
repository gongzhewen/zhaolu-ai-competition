from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import random
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from time import perf_counter
from typing import Any

from agent_core.benchmark import BenchmarkCase
from agent_core.contracts import AgentContext, RouteDecision
from agent_core.privacy import assess_request_privacy
from agent_core.router import RuleRouter
from agent_core.runtime import AgentRuntime
from agent_core.semantics import compile_semantic_slots, estimate_slot_ambiguity
from agent_core.sql_guard import SQLGuardError, execute_readonly_sql, metrics_from_rows
from agent_core.text_to_sql import ALLOWED_TABLES, LocalTextToSqlClient, TextToSqlUnavailable
from app.core.config import settings
from app.core.text import text
from app.modules.agent.providers import SQLAlchemyKnowledgeProvider
from app.modules.agent.tools.registry import NATIVE_TOOL_EXECUTORS
from scripts.run_demo_gold_evaluation import run_g0, run_g1, run_rag_only

METRIC_LABEL_TO_KEY = {
    "计划数": "plan_count",
    "录取数": "admitted_count",
    "男生数": "male_count",
    "女生数": "female_count",
    "计划完成率": "completion_rate",
    "报到数": "enrolled_count",
    "报到率": "enrollment_rate",
    "最高分": "max_score",
    "最低分": "min_score",
    "平均分": "avg_score",
    "中位分": "median_score",
    "下四分位分": "lower_quartile_score",
    "最高分位次": "min_rank_no",
    "最低分位次": "max_rank_no",
    "平均分位次": "avg_rank_no",
    "志愿数": "choice_count",
    "志愿率": "choice_rate",
    "报考数": "applicant_count",
    "报考率": "application_rate",
    "一志愿录取数": "first_admitted_count",
    "一志愿录取率": "first_admission_rate",
    "一志愿报考数": "first_applicant_count",
    "一志愿报考率": "first_application_rate",
    "区间志愿录取数": "range_admitted_count",
    "区间志愿录取率": "range_admission_rate",
    "区间志愿报考数": "range_applicant_count",
    "区间志愿报考率": "range_application_rate",
    "调剂数": "adjusted_count",
    "调剂率": "adjusted_rate",
    "普通计划": "official_plan_count",
    "普通录取": "official_regular_admitted",
    "专升本": "official_zhuan_admitted",
    "总录取": "official_total_admitted",
    "人数": "student_count",
}
METRIC_ALIASES = {"enroll_rate": "enrollment_rate", "admit_rate": "completion_rate"}
B2_OUTPUT_ALIASES = {
    "plan_count": ("plan_count", "plan", "计划数"),
    "admitted_count": ("admitted_count", "admit_count", "录取数"),
    "enrolled_count": ("enrolled_count", "enroll_count", "报到数"),
    "completion_rate": ("completion_rate", "admit_rate", "计划完成率"),
    "enrollment_rate": ("enrollment_rate", "enroll_rate", "报到率"),
    "max_score": ("max_score", "最高分"),
    "min_score": ("min_score", "最低分"),
    "avg_score": ("avg_score", "average_score", "平均分"),
    "male_count": ("male_count", "男生数"),
    "female_count": ("female_count", "女生数"),
    "choice_count": ("choice_count", "志愿数"),
    "applicant_count": ("applicant_count", "applicants", "报考数"),
    "official_plan_count": ("official_plan_count", "regular_plan", "plan_count"),
    "official_regular_admitted": ("official_regular_admitted", "regular_admitted", "regular_admitted_count"),
    "official_zhuan_admitted": ("official_zhuan_admitted", "zhuan_admitted", "zhuan_admitted_count"),
    "official_total_admitted": ("official_total_admitted", "total_admitted", "total_admitted_count"),
    "student_count": ("student_count", "count", "人数"),
    "band_start": ("band_start", "band"),
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_gold(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def to_case(item: dict[str, Any]) -> BenchmarkCase:
    return BenchmarkCase(
        case_id=item["case_id"],
        question=item["question"],
        category=item["category"],
        expected_intent=item["expected_intent"],
        expected_strategy=item["expected_strategy"],
        expected_tool=item.get("expected_tool"),
        expected_params=dict(item.get("expected_params") or {}),
        expected_metrics=dict(item.get("expected_metrics") or {}),
        tags=tuple(item.get("tags") or ()),
    )


def infer_b2_metrics(rows: list[dict[str, Any]], expected_keys: dict[str, Any]) -> dict[str, Any]:
    if not rows:
        return {}
    lowered = {str(key).lower(): value for key, value in rows[0].items()}
    metrics: dict[str, Any] = {}
    for key in expected_keys:
        for alias in B2_OUTPUT_ALIASES.get(key, (key,)):
            if alias.lower() in lowered:
                metrics[key] = lowered[alias.lower()]
                break
    return metrics


def normalize_metric(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    try:
        return Decimal(str(value)).normalize()
    except (InvalidOperation, ValueError):
        return str(value).strip()


def metric_equal(expected: Any, actual: Any, tolerance: float) -> bool:
    if actual is None:
        return False
    if tolerance > 0:
        try:
            return abs(float(actual) - float(expected)) <= tolerance + 1e-9
        except (TypeError, ValueError):
            return False
    return normalize_metric(expected) == normalize_metric(actual)


def normalize_key(key: str) -> str:
    return METRIC_ALIASES.get(key, key)

def table_rows(payload: dict[str, Any], expected: dict[str, Any], group_value: str | None) -> list[dict[str, Any]]:
    table = payload.get("table")
    if not isinstance(table, dict):
        return []
    columns = [str(item) for item in table.get("columns") or []]
    rows = table.get("rows") or []
    result = []
    for row in rows:
        if not isinstance(row, (list, tuple)):
            continue
        mapped = {columns[index]: value for index, value in enumerate(row) if index < len(columns)}
        result.append(mapped)
    if group_value is not None and len(result) > 1:
        exact = [row for row in result if str(row.get(columns[0]) if columns else "") == str(group_value)]
        if exact:
            return exact
    return result


def extract_observations(result: dict[str, Any], expected: dict[str, Any], case: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    metrics: dict[str, Any] = {}
    values: dict[str, Any] = {}
    payloads = []
    for item in result.get("tool_results") or []:
        if not isinstance(item, dict):
            continue
        payloads.append(item)
        for key, value in (item.get("metrics") or {}).items():
            metrics[normalize_key(str(key))] = value
        table = item.get("table")
        if not isinstance(table, dict):
            continue
        columns = [str(value) for value in table.get("columns") or []]
        rows = table.get("rows") or []
        if not columns:
            continue
        if "分数段" in columns and "人数" in columns and "band_start" in expected:
            band_index = columns.index("分数段")
            count_index = columns.index("人数")
            target = int(expected["band_start"])
            for row in rows:
                try:
                    start = int(str(row[band_index]).split("-")[0])
                except (ValueError, IndexError, TypeError):
                    continue
                if start == target:
                    metrics["student_count"] = row[count_index]
                    metrics["band_start"] = target
                    metrics["band_end"] = target + 9
                    break
        if "来源专业" in columns and "标准专业" in columns and case.get("expected_values"):
            canonical_index = columns.index("标准专业")
            source_index = columns.index("来源专业")
            expected_source = case.get("expected_params", {}).get("source_name")
            for row in rows:
                if expected_source is None or str(row[source_index]) == str(expected_source):
                    values["canonical_major"] = row[canonical_index]
                    break
        group_value = None
        for candidate in ("province", "major", "subject_name", "source_name"):
            if candidate in case.get("expected_params", {}):
                group_value = str(case["expected_params"][candidate])
                break
        for row in table_rows(item, expected, group_value):
            for column, value in row.items():
                key = METRIC_LABEL_TO_KEY.get(column)
                if key:
                    metrics.setdefault(key, value)
    return metrics, values


def parameter_match(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    equivalent = {
        "year": ("year", "end_year"),
        "start_year": ("start_year", "compare_year"),
        "end_year": ("end_year", "year"),
    }
    for key, value in expected.items():
        candidates = equivalent.get(key, (key,))
        if not any(actual.get(candidate) == value for candidate in candidates):
            return False
    return True


def strategy_equivalent(expected: str, actual: str) -> bool:
    if expected == actual:
        return True
    return expected in {"refuse", "no_permission"} and actual in {"refuse", "no_permission"}


def evaluate_row(case: dict[str, Any], result: dict[str, Any], latency_ms: float, error: str | None) -> dict[str, Any]:
    risk = result.get("risk_decision") or {}
    strategy = str(risk.get("strategy") or "answer")
    tool_calls = result.get("tool_calls") or []
    expected_tool = case.get("expected_tool")
    tool_match = expected_tool is None or any(call.get("name") == expected_tool for call in tool_calls)
    target_call = next((call for call in tool_calls if call.get("name") == expected_tool), {}) if expected_tool else {}
    params_match = True if expected_tool is None else tool_match and parameter_match(case.get("expected_params") or {}, target_call.get("params") or {})
    observed_metrics, observed_values = extract_observations(result, case.get("expected_metrics") or {}, case)
    metric_results = {}
    for key, expected in (case.get("expected_metrics") or {}).items():
        tolerance = float((case.get("allowed_error") or {}).get(key, 0) or 0)
        metric_results[key] = metric_equal(expected, observed_metrics.get(key), tolerance)
    value_results = {
        key: normalize_metric(observed_values.get(key)) == normalize_metric(expected)
        for key, expected in (case.get("expected_values") or {}).items()
    }
    metrics_match = all(metric_results.values())
    values_match = all(value_results.values())
    strategy_exact = strategy == case["expected_strategy"]
    strategy_match = strategy_equivalent(case["expected_strategy"], strategy)
    answer_expected = case["expected_strategy"] == "answer"
    answered = strategy == "answer"
    data_match = metrics_match and values_match
    correct = strategy_match and (not answer_expected or data_match)
    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "question": case["question"],
        "expected_strategy": case["expected_strategy"],
        "predicted_strategy": strategy,
        "strategy_match": strategy_match,
        "strategy_exact": strategy_exact,
        "expected_intent": case.get("expected_intent"),
        "predicted_intent": result.get("intent"),
        "intent_match": result.get("intent") == case.get("expected_intent"),
        "expected_tool": expected_tool,
        "predicted_tool": (tool_calls[0].get("name") if tool_calls else None),
        "tool_match": tool_match,
        "params_match": params_match,
        "expected_metrics": case.get("expected_metrics") or {},
        "observed_metrics": observed_metrics,
        "metric_results": metric_results,
        "metrics_match": metrics_match,
        "expected_values": case.get("expected_values") or {},
        "observed_values": observed_values,
        "value_results": value_results,
        "values_match": values_match,
        "answered": answered,
        "correct": correct,
        "latency_ms": round(latency_ms, 3),
        "risk_score": risk.get("score"),
        "tags": case.get("tags") or [],
        "error": error,
    }


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return round(ordered[index], 3)


def bootstrap_ci(flags: list[int], *, seed: int = 20261108, rounds: int = 2000) -> list[float]:
    if not flags:
        return [0.0, 0.0]
    rng = random.Random(seed)
    values = []
    for _ in range(rounds):
        sample = [flags[rng.randrange(len(flags))] for _ in flags]
        values.append(sum(sample) / len(sample))
    values.sort()
    return [round(values[int(0.025 * rounds)], 4), round(values[int(0.975 * rounds) - 1], 4)]

def summarize(rows: list[dict[str, Any]], method: str, elapsed_seconds: float) -> dict[str, Any]:
    total = len(rows)
    expected_answer = [row for row in rows if row["expected_strategy"] == "answer"]
    expected_block = [row for row in rows if row["expected_strategy"] != "answer"]
    answered = [row for row in rows if row["answered"]]
    privacy_rows = [row for row in rows if "privacy" in row.get("tags", [])]
    latencies = [float(row["latency_ms"]) for row in rows]
    overall_flags = [1 if row["correct"] else 0 for row in rows]
    answer_flags = [1 if row["correct"] else 0 for row in expected_answer]
    return {
        "method": method,
        "total": total,
        "overall_accuracy": round(sum(overall_flags) / total, 4) if total else 0.0,
        "overall_accuracy_ci95": bootstrap_ci(overall_flags),
        "answer_accuracy": round(sum(answer_flags) / len(expected_answer), 4) if expected_answer else 0.0,
        "answer_accuracy_ci95": bootstrap_ci(answer_flags),
        "strategy_accuracy": round(sum(1 for row in rows if row["strategy_match"]) / total, 4) if total else 0.0,
        "strategy_exact_accuracy": round(sum(1 for row in rows if row["strategy_exact"]) / total, 4) if total else 0.0,
        "tool_plan_accuracy": round(sum(1 for row in expected_answer if row["tool_match"]) / len(expected_answer), 4) if expected_answer else 0.0,
        "parameter_accuracy": round(sum(1 for row in expected_answer if row["params_match"]) / len(expected_answer), 4) if expected_answer else 0.0,
        "exact_metric_accuracy": round(sum(1 for row in expected_answer if row["metrics_match"]) / len(expected_answer), 4) if expected_answer else 0.0,
        "correct_refusal_rate": round(sum(1 for row in expected_block if row["strategy_match"]) / len(expected_block), 4) if expected_block else 0.0,
        "false_refusal_rate": round(sum(1 for row in expected_answer if not row["answered"]) / len(expected_answer), 4) if expected_answer else 0.0,
        "answer_coverage": round(len(answered) / total, 4) if total else 0.0,
        "unsupported_answer_rate": round(sum(1 for row in answered if row["expected_strategy"] == "answer" and not row["correct"]) / len(answered), 4) if answered else 0.0,
        "privacy_violations": sum(1 for row in privacy_rows if row["expected_strategy"] == "no_permission" and row["answered"]),
        "latency_ms": {"p50": percentile(latencies, 0.50), "p95": percentile(latencies, 0.95), "p99": percentile(latencies, 0.99)},
        "elapsed_seconds": round(elapsed_seconds, 3),
        "dual_planning_triggered": sum(1 for row in rows if isinstance(row.get("plan_consistency"), dict) and row["plan_consistency"].get("triggered")),
    }


def category_summary(rows: list[dict[str, Any]], method: str | None = None) -> list[dict[str, Any]]:
    output = []
    for category in sorted({row["category"] for row in rows}):
        items = [row for row in rows if row["category"] == category]
        expected_answer = [row for row in items if row["expected_strategy"] == "answer"]
        expected_block = [row for row in items if row["expected_strategy"] != "answer"]
        output.append({
            "method": method,
            "category": category,
            "total": len(items),
            "overall_accuracy": round(sum(1 for row in items if row["correct"]) / len(items), 4),
            "answer_accuracy": round(sum(1 for row in expected_answer if row["correct"]) / len(expected_answer), 4) if expected_answer else None,
            "strategy_accuracy": round(sum(1 for row in items if row["strategy_match"]) / len(items), 4),
            "tool_plan_accuracy": round(sum(1 for row in expected_answer if row["tool_match"]) / len(expected_answer), 4) if expected_answer else None,
            "metric_accuracy": round(sum(1 for row in expected_answer if row["metrics_match"]) / len(expected_answer), 4) if expected_answer else None,
            "correct_refusal_rate": round(sum(1 for row in expected_block if row["strategy_match"]) / len(expected_block), 4) if expected_block else None,
            "false_refusal_rate": round(sum(1 for row in expected_answer if not row["answered"]) / len(expected_answer), 4) if expected_answer else None,
            "privacy_violations": sum(1 for row in items if row["expected_strategy"] == "no_permission" and row["answered"]),
        })
    return output


async def run_b2_case(db, case: dict[str, Any], client: LocalTextToSqlClient, router: RuleRouter) -> tuple[dict[str, Any], str | None]:
    started = perf_counter()
    decision: RouteDecision = router.route(case["question"], latest_year=2026, known_majors=(), known_provinces=())
    decision.params.setdefault("query", case["question"])
    slots = compile_semantic_slots(case["question"], decision)
    ambiguity = estimate_slot_ambiguity(case["question"], decision, slots)
    privacy = assess_request_privacy(case["question"], intent=decision.intent, context_values={"can_lookup_students": True})
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
            sql = await client.generate_sql(case["question"], {})
            try:
                execution = await execute_readonly_sql(db, sql, allowed_tables=ALLOWED_TABLES, max_rows=settings.local_sql_max_rows, timeout_seconds=settings.local_sql_query_timeout_seconds)
            except Exception as first_error:
                await db.rollback()
                sql = await client.generate_sql(case["question"], {}, previous_sql=sql, previous_error=f"{type(first_error).__name__}: {first_error}")
                execution = await execute_readonly_sql(db, sql, allowed_tables=ALLOWED_TABLES, max_rows=settings.local_sql_max_rows, timeout_seconds=settings.local_sql_query_timeout_seconds)
            metrics = infer_b2_metrics(execution.rows, case.get("expected_metrics") or {})
        except (SQLGuardError, TextToSqlUnavailable) as exc:
            await db.rollback()
            strategy = "insufficient_data"
            error = f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            await db.rollback()
            strategy = "insufficient_data"
            error = f"{type(exc).__name__}: {exc}"
    await db.rollback()
    result = {
        "intent": decision.intent,
        "answer": "",
        "tool_calls": [],
        "tool_results": [{"metrics": metrics}],
        "risk_decision": {"strategy": strategy, "score": 0.0 if strategy == "answer" else 1.0},
        "b2_sql": sql,
        "b2_elapsed_ms": round((perf_counter() - started) * 1000, 3),
    }
    return result, error

async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="local_private/gold/real_frozen_test_gold_v2.jsonl")
    parser.add_argument("--dataset-manifest", default="local_private/gold/m1_gold_manifest_v2.json")
    parser.add_argument("--freeze-record", default="local_private/results/M1_final_freeze_v2.json")
    parser.add_argument("--output-dir", default="local_private/results/real_frozen_v2")
    parser.add_argument("--methods", default="g0,g1,b1,b2")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--max-per-category", type=int, default=0)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    cases_path = Path(args.cases)
    if not cases_path.is_absolute():
        cases_path = root / cases_path
    manifest_path = Path(args.dataset_manifest)
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path
    freeze_path = Path(args.freeze_record)
    if not freeze_path.is_absolute():
        freeze_path = root / freeze_path
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_cases = load_gold(cases_path)
    if any(item.get("split") != "test" for item in raw_cases):
        raise ValueError("formal evaluation accepts only the frozen test split")
    if args.limit > 0:
        raw_cases = raw_cases[: args.limit]
    if args.max_per_category > 0:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in raw_cases:
            grouped[item["category"]].append(item)
        raw_cases = [item for items in grouped.values() for item in items[: args.max_per_category]]
    manifest = load_json(manifest_path)
    freeze = load_json(freeze_path)
    if manifest.get("version") != "m1-real-frozen-v2" or freeze.get("dataset_version") != "m1-real-frozen-v2":
        raise ValueError("dataset is not the authoritative M1 v2 freeze")
    caseload = [to_case(item) for item in raw_cases]
    method_codes = {item.strip() for item in args.methods.split(",") if item.strip()}
    method_names = {
        "g0": "g0_rule_tool",
        "g1": "g1_full",
        "b1": "b1_local_rag_only",
        "b2": "b2_local_text_to_sql",
    }
    unknown = method_codes - set(method_names)
    if unknown:
        raise ValueError(f"unknown methods: {sorted(unknown)}")

    original_vector = settings.rag_vector_enabled
    settings.rag_vector_enabled = False
    from app.core.database import AsyncSessionLocal

    summaries: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    try:
        async with AsyncSessionLocal() as db:
            provinces = tuple((await db.execute(text("SELECT province_name FROM dim.province ORDER BY id"))).scalars().all())
            majors = tuple((await db.execute(text("SELECT major_name FROM dim.major WHERE is_active IS TRUE ORDER BY id"))).scalars().all())
            latest_year = int(await db.scalar(text("SELECT MAX(year_no) FROM dim.year")))
            context = AgentContext(school_id=1, values={"can_lookup_students": True})
            common = {"known_provinces": provinces, "known_majors": majors, "latest_year": latest_year}

            async def execute(call, agent_context):
                params = {**call.params, "school_id": agent_context.school_id, "can_lookup_students": True}
                return await NATIVE_TOOL_EXECUTORS[call.name](db, params)

            runtime = AgentRuntime(
                tool_executor=execute,
                router=RuleRouter(),
                llm_planner=None,
                multi_planning_enabled=settings.agent_multi_planning_enabled,
            )
            router = RuleRouter()
            rag = SQLAlchemyKnowledgeProvider(db)
            b2_client = LocalTextToSqlClient(
                enabled=settings.local_sql_model_enabled,
                base_url=settings.local_sql_model_base_url,
                model_name=settings.local_sql_model_name,
                api_key=settings.local_sql_model_api_key,
                timeout_seconds=settings.local_sql_timeout_seconds,
                max_rows=settings.local_sql_max_rows,
            )

            async def run_method(case: dict[str, Any], code: str) -> tuple[dict[str, Any], str | None]:
                benchmark_case = to_case(case)
                try:
                    if code == "g0":
                        return await run_g0(benchmark_case, router=router, db=db, context=context, **common), None
                    if code == "g1":
                        return await run_g1(benchmark_case, runtime, context, **common), None
                    if code == "b1":
                        return await run_rag_only(benchmark_case, provider=rag), None
                    if code == "b2":
                        return await run_b2_case(db, case, b2_client, router)
                except Exception as exc:
                    return {"intent": "runtime_error", "tool_calls": [], "tool_results": [], "risk_decision": {"strategy": "insufficient_data", "score": 1.0}}, f"{type(exc).__name__}: {exc}"
                raise ValueError(f"unknown method {code}")

            for code in [item for item in ("g0", "g1", "b1", "b2") if item in method_codes]:
                if code == "b2" and not b2_client.configured:
                    summaries.append({"method": "b2_local_text_to_sql", "status": "skipped", "total": len(raw_cases), "reason": "LOCAL_SQL_MODEL_ENABLED/BASE_URL/NAME 未配置"})
                    continue
                if raw_cases:
                    await run_method(raw_cases[0], code)
                rows = []
                started = perf_counter()
                for case in raw_cases:
                    case_started = perf_counter()
                    result, error = await run_method(case, code)
                    row = evaluate_row(case, result, (perf_counter() - case_started) * 1000, error)
                    row["method"] = method_names[code]
                    row["plan_consistency"] = result.get("plan_consistency")
                    row["verification_summary"] = result.get("verification_summary")
                    row["b2_sql"] = result.get("b2_sql")
                    rows.append(row)
                    all_rows.append(row)
                summary = summarize(rows, method_names[code], perf_counter() - started)
                summaries.append(summary)
                (output_dir / f"{method_names[code]}_per_case.jsonl").write_text(
                    "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in rows) + "\n",
                    encoding="utf-8",
                )
    finally:
        settings.rag_vector_enabled = original_vector

    fieldnames = [
        "method", "total", "overall_accuracy", "answer_accuracy", "strategy_accuracy", "strategy_exact_accuracy",
        "tool_plan_accuracy", "parameter_accuracy", "exact_metric_accuracy", "correct_refusal_rate",
        "false_refusal_rate", "answer_coverage", "unsupported_answer_rate", "privacy_violations",
    ]
    with (output_dir / "baseline_summary.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for summary in summaries:
            writer.writerow({key: summary.get(key) for key in fieldnames})
    categories = []
    for summary in summaries:
        categories.extend(category_summary([row for row in all_rows if row["method"] == summary["method"]], summary["method"]))
    (output_dir / "category_summary.json").write_text(json.dumps(categories, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (output_dir / "category_summary.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(categories[0]) if categories else ["method", "category"])
        writer.writeheader()
        writer.writerows(categories)
    (output_dir / "per_case_results.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in all_rows) + "\n",
        encoding="utf-8",
    )

    taxonomy = ["# Real Frozen v2 Error Taxonomy", ""]
    for summary in summaries:
        method = summary["method"]
        rows = [row for row in all_rows if row["method"] == method]
        false_refusals = [row for row in rows if row["expected_strategy"] == "answer" and not row["answered"]]
        wrong_strategy = [row for row in rows if not row["strategy_match"]]
        metric_errors = [row for row in rows if row["expected_strategy"] == "answer" and not row["metrics_match"]]
        privacy = [row for row in rows if row["expected_strategy"] == "no_permission" and row["answered"]]
        taxonomy.extend([
            f"## {method}", "",
            f"- 错误拒答：{len(false_refusals)}",
            f"- 策略错误：{len(wrong_strategy)}",
            f"- 指标错误：{len(metric_errors)}",
            f"- 隐私违规：{len(privacy)}", "",
        ])
        for label, items in (("错误拒答", false_refusals), ("策略错误", wrong_strategy), ("指标错误", metric_errors), ("隐私违规", privacy)):
            for row in items[:20]:
                taxonomy.append(f"- {label}：{row['case_id']} {row['question']}")
        taxonomy.append("")
    (output_dir / "error_taxonomy.md").write_text("\n".join(taxonomy) + "\n", encoding="utf-8")

    meta = {
        "evaluation_kind": "real_frozen_v2_end_to_end",
        "dataset_version": manifest["version"],
        "data_snapshot_id": manifest["data_snapshot_id"],
        "case_set_sha256": freeze["case_set_sha256"],
        "data_scope": "local authorized real-source anonymized snapshot; 2024-2025 frozen test only",
        "authorization_status": "declared_by_user_pending_signed_document",
        "post_hoc_freeze": True,
        "cases": len(raw_cases),
        "methods": [summary["method"] for summary in summaries],
        "external_api_calls": 0,
        "local_sql_model": {
            "enabled": settings.local_sql_model_enabled,
            "base_url": settings.local_sql_model_base_url,
            "model": settings.local_sql_model_name,
        },
        "agent_config": {
            "agent_fast_mode": settings.agent_fast_mode,
            "agent_risk_threshold": settings.agent_risk_threshold,
            "agent_privacy_min_cohort_size": settings.agent_privacy_min_cohort_size,
            "agent_multi_planning_enabled": settings.agent_multi_planning_enabled,
            "agent_plan_consistency_threshold": settings.agent_plan_consistency_threshold,
            "agent_min_data_support": settings.agent_min_data_support,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (output_dir / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "summary.json").write_text(json.dumps({"meta": meta, "summaries": summaries, "categories": categories}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"meta": meta, "summaries": summaries}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())






