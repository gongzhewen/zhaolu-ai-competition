from __future__ import annotations

import argparse
import asyncio
import csv
import json
from pathlib import Path
from time import perf_counter
from typing import Any

from agent_core.benchmark import BenchmarkCase, evaluate_case, load_cases, summarize_results
from agent_core.contracts import AgentContext, ToolCall
from agent_core.planner import single_tool_plan
from agent_core.router import RuleRouter
from agent_core.runtime import AgentRuntime
from app.core.config import settings
from app.core.text import text
from app.modules.agent.providers import SQLAlchemyKnowledgeProvider
from app.modules.agent.tools.registry import NATIVE_TOOL_EXECUTORS
from agent_core.composer import deterministic_answer


def _result(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"tool": tool_name, **payload}


async def run_g1(case: BenchmarkCase, runtime: AgentRuntime, context: AgentContext, **kwargs) -> dict[str, Any]:
    return await runtime.chat(case.question, context=context, **kwargs)


async def run_g0(case: BenchmarkCase, *, router: RuleRouter, db, context: AgentContext, **kwargs) -> dict[str, Any]:
    decision = router.route(case.question, latest_year=kwargs.get("latest_year"), known_majors=kwargs.get("known_majors", ()), known_provinces=kwargs.get("known_provinces", ()))
    decision.params.setdefault("query", case.question)
    intent = decision.intent
    if intent == "out_of_scope":
        return {"intent": intent, "tool_calls": [], "tool_results": [], "risk_decision": {"strategy": "out_of_scope", "score": 1.0}, "answer": "超出招生业务范围"}
    if intent == "refuse":
        return {"intent": intent, "tool_calls": [], "tool_results": [], "risk_decision": {"strategy": "no_permission", "score": 1.0}, "answer": "不能提供"}
    if decision.clarification:
        return {"intent": intent, "tool_calls": [], "tool_results": [], "risk_decision": {"strategy": "clarify", "score": 1.0}, "answer": decision.clarification}
    call = single_tool_plan(intent)
    if call is None:
        return {"intent": intent, "tool_calls": [], "tool_results": [], "risk_decision": {"strategy": "insufficient_data", "score": 1.0}, "answer": "数据支撑不足"}
    call = AgentRuntime._materialize_calls([call], decision)[0]
    payload = await NATIVE_TOOL_EXECUTORS[call.name](db, {**call.params, "school_id": context.school_id, "can_lookup_students": True})
    result = _result(call.name, payload)
    strategy = "answer" if payload.get("metrics") else "insufficient_data"
    answer = deterministic_answer(decision, [result])
    return {
        "intent": intent,
        "answer": answer,
        "tool_calls": [{"name": call.name, "params": call.params}],
        "tool_results": [result],
        "risk_decision": {"strategy": strategy, "score": 0.0 if strategy == "answer" else 1.0},
    }


async def run_rag_only(case: BenchmarkCase, *, provider: SQLAlchemyKnowledgeProvider) -> dict[str, Any]:
    items = await provider.search(case.question, school_id=1, limit=4)
    answer = "\n".join(str(item.get("content") or "") for item in items[:2])
    return {
        "intent": "rag_only",
        "answer": answer,
        "tool_calls": [],
        "tool_results": [],
        "risk_decision": {"strategy": "answer" if items else "insufficient_data", "score": 0.2 if items else 1.0},
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="evaluation/demo_gold_v1.jsonl")
    parser.add_argument("--dataset-meta", default="evaluation/demo_gold_v1.meta.json")
    parser.add_argument("--output", default="evaluation/results/demo_v1")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    cases = load_cases(root / args.cases)
    output_dir = root / args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    original_vector = settings.rag_vector_enabled
    settings.rag_vector_enabled = False
    from app.core.database import AsyncSessionLocal

    dataset_meta = {}
    meta_path = root / args.dataset_meta
    if meta_path.exists():
        dataset_meta = json.loads(meta_path.read_text(encoding="utf-8"))

    async with AsyncSessionLocal() as db:
        current_profile = {
            "dim_major": int(await db.scalar(text("SELECT COUNT(*) FROM dim.major")) or 0),
            "dim_province": int(await db.scalar(text("SELECT COUNT(*) FROM dim.province")) or 0),
            "fact_plan": int(await db.scalar(text("SELECT COUNT(*) FROM fact.plan")) or 0),
            "fact_admission_record": int(await db.scalar(text("SELECT COUNT(*) FROM fact.admission_record")) or 0),
            "fact_student_identity": int(await db.scalar(text("SELECT COUNT(*) FROM fact.student_identity")) or 0),
            "fact_enrollment_status": int(await db.scalar(text("SELECT COUNT(*) FROM fact.enrollment_status")) or 0),
        }
        expected_profile = dataset_meta.get("data_profile")
        if expected_profile and expected_profile != current_profile:
            raise ValueError(
                "演示金标准与当前数据库画像不一致，请先在同一数据库上重新生成金标准。"
                f" expected={expected_profile} actual={current_profile}"
            )
        provinces = tuple((await db.execute(text("SELECT province_name FROM dim.province ORDER BY id"))).scalars().all())
        majors = tuple((await db.execute(text("SELECT major_name FROM dim.major WHERE is_active IS TRUE ORDER BY id"))).scalars().all())
        latest = await db.scalar(text("SELECT MAX(year_no) FROM dim.year"))
        latest_year = int(latest)

        async def execute(call, context):
            params = {**call.params, "school_id": context.school_id, "can_lookup_students": True}
            return await NATIVE_TOOL_EXECUTORS[call.name](db, params)

        runtime = AgentRuntime(tool_executor=execute, router=RuleRouter(), llm_planner=None)
        router = RuleRouter()
        rag = SQLAlchemyKnowledgeProvider(db)
        context = AgentContext(school_id=1, values={"can_lookup_students": True})
        common = {"known_provinces": provinces, "known_majors": majors, "latest_year": latest_year}

        methods = {
            "g1_full": lambda case: run_g1(case, runtime, context, **common),
            "g0_rule_tool": lambda case: run_g0(case, router=router, db=db, context=context, **common),
            "b1_local_rag_only": lambda case: run_rag_only(case, provider=rag),
        }
        all_per_case: list[dict[str, Any]] = []
        summaries: list[dict[str, Any]] = []
        for method, runner in methods.items():
            # Warm the process without including the warmup in measured latency.
            if cases:
                await runner(cases[0])
            rows: list[dict[str, Any]] = []
            started = perf_counter()
            for case in cases:
                case_started = perf_counter()
                try:
                    result = await runner(case)
                    error = None
                except Exception as exc:
                    result = {"intent": "runtime_error", "tool_calls": [], "tool_results": [], "risk_decision": {"strategy": "insufficient_data", "score": 1.0}}
                    error = f"{type(exc).__name__}: {exc}"
                latency_ms = (perf_counter() - case_started) * 1000
                row = evaluate_case(case, result, latency_ms)
                row["method"] = method
                row["error"] = error
                row["risk_score"] = result.get("risk_decision", {}).get("score")
                row["risk_features"] = result.get("risk_decision", {}).get("features")
                row["verification_summary"] = result.get("verification_summary")
                row["plan_consistency"] = result.get("plan_consistency")
                rows.append(row)
                all_per_case.append(row)
            summary = summarize_results(rows)
            summary["method"] = method
            summary["elapsed_seconds"] = round(perf_counter() - started, 3)
            summary["dual_planning_triggered"] = sum(
                1 for row in rows if (row.get("plan_consistency") or {}).get("triggered")
            )
            summaries.append(summary)
            with (output_dir / f"{method}_per_case.jsonl").open("w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    settings.rag_vector_enabled = original_vector

    fieldnames = ["method", "total", "overall_accuracy", "answer_accuracy", "strategy_accuracy", "tool_plan_accuracy", "exact_metric_accuracy", "correct_refusal_rate", "false_refusal_rate", "answer_coverage", "unsupported_answer_rate", "privacy_violations"]
    with (output_dir / "baseline_summary.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for summary in summaries:
            writer.writerow({key: summary.get(key) for key in fieldnames})
    performance_rows = [{"method": summary["method"], **summary["latency_ms"]} for summary in summaries]
    with (output_dir / "performance.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["method", "p50", "p95", "p99"])
        writer.writeheader()
        writer.writerows(performance_rows)
    with (output_dir / "per_case_results.jsonl").open("w", encoding="utf-8") as handle:
        for row in all_per_case:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    taxonomy = ["# Demo Gold Error Taxonomy", "", "数据范围：本机演示库，不是真实授权冻结集。", ""]
    for method in ("g1_full", "g0_rule_tool", "b1_local_rag_only"):
        method_rows = [row for row in all_per_case if row["method"] == method]
        false_refusals = [row for row in method_rows if row["expected_strategy"] == "answer" and not row["answered"]]
        unsupported = [row for row in method_rows if row["answered"] and not row["correct"]]
        metric_errors = [row for row in method_rows if row["expected_strategy"] == "answer" and not row["metrics_match"]]
        taxonomy.extend([
            f"## {method}", "",
            f"- 错误拒答：{len(false_refusals)}",
            f"- 无依据或错误回答：{len(unsupported)}",
            f"- 指标不一致：{len(metric_errors)}", "",
        ])
        for label, items in (("错误拒答", false_refusals), ("无依据或错误回答", unsupported), ("指标不一致", metric_errors)):
            for row in items[:8]:
                taxonomy.append(f"- {label}：{row['case_id']} {row['question']}")
        taxonomy.append("")
    (output_dir / "error_taxonomy.md").write_text("\n".join(taxonomy) + "\n", encoding="utf-8")

    meta = {
        "evaluation_kind": "demo_gold_end_to_end",
        "gold_dataset": True,
        "real_authorized_frozen_set": False,
        "data_scope": "local demonstration database zhaolu_v2",
        "data_profile": current_profile,
        "dataset_meta": dataset_meta,
        "cases": len(cases),
        "methods": [summary["method"] for summary in summaries],
        "external_model_calls": 0,
        "g1_dual_planning_triggered": next(
            (summary.get("dual_planning_triggered", 0) for summary in summaries if summary["method"] == "g1_full"),
            0,
        ),
        "b2_local_text_to_sql": {
            "status": "not_run",
            "reason": "未配置可审计的本地 Text-to-SQL 模型服务；不使用外部 API 替代。",
        },
    }
    (output_dir / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"meta": meta, "summaries": summaries}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
