from __future__ import annotations

import argparse
import asyncio
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from agent_core.contracts import AgentContext
from agent_core.router import RuleRouter
from agent_core.runtime import AgentRuntime
from app.core.database import AsyncSessionLocal
from app.core.text import text
from app.modules.agent.providers import CompositePlanner
from app.modules.agent.tools.registry import NATIVE_TOOL_EXECUTORS
from scripts.run_real_frozen_evaluation import category_summary, evaluate_row, load_gold, summarize


def select_calibration_cases(cases: list[dict[str, Any]], per_category: int) -> list[dict[str, Any]]:
    if any(case.get("split") != "calibration" for case in cases):
        raise ValueError("dual-planning calibration runner accepts calibration split only")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        grouped[case["category"]].append(case)
    selected: list[dict[str, Any]] = []
    for category in sorted(grouped):
        selected.extend(grouped[category][:per_category])
    return selected


async def run_variant(
    *,
    name: str,
    cases: list[dict[str, Any]],
    db,
    context: AgentContext,
    common: dict[str, Any],
    multi_planning_enabled: bool,
) -> dict[str, Any]:
    async def execute(call, agent_context):
        params = {**call.params, "school_id": agent_context.school_id, "can_lookup_students": True}
        return await NATIVE_TOOL_EXECUTORS[call.name](db, params)

    runtime = AgentRuntime(
        tool_executor=execute,
        router=RuleRouter(),
        llm_planner=CompositePlanner(db),
        multi_planning_enabled=multi_planning_enabled,
        plan_consistency_threshold=0.95,
        risk_threshold=0.32,
        semantic_entropy_enabled=True,
        enforce_evidence_gate=True,
    )
    rows: list[dict[str, Any]] = []
    started = perf_counter()
    for case in cases:
        case_started = perf_counter()
        result = await runtime.chat(case["question"], context=context, **common)
        row = evaluate_row(case, result, (perf_counter() - case_started) * 1000, None)
        row["variant"] = name
        row["plan_summary"] = result.get("plan_summary")
        row["plan_consistency"] = result.get("plan_consistency")
        rows.append(row)
    summary = summarize(rows, name, perf_counter() - started)
    summary["dual_planning_triggered"] = sum(1 for row in rows if (row.get("plan_consistency") or {}).get("triggered"))
    summary["dual_planning_consistent"] = sum(
        1 for row in rows if (row.get("plan_consistency") or {}).get("triggered") and (row.get("plan_consistency") or {}).get("consistent")
    )
    summary["local_model_plans"] = sum(1 for row in rows if "本地模型" in str(row.get("plan_summary") or ""))
    return {"summary": summary, "categories": category_summary(rows, name), "rows": rows}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="local_private/gold/real_calibration_gold_v2.jsonl")
    parser.add_argument("--output-dir", default="local_private/results/dual_planning_calibration_v1")
    parser.add_argument("--per-category", type=int, default=3)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    cases_path = Path(args.cases)
    if not cases_path.is_absolute():
        cases_path = root / cases_path
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = select_calibration_cases(load_gold(cases_path), args.per_category)

    async with AsyncSessionLocal() as db:
        provinces = tuple((await db.execute(text("SELECT province_name FROM dim.province ORDER BY id"))).scalars().all())
        majors = tuple((await db.execute(text("SELECT major_name FROM dim.major WHERE is_active IS TRUE ORDER BY id"))).scalars().all())
        latest_year = int(await db.scalar(text("SELECT MAX(year_no) FROM dim.year")))
        context = AgentContext(school_id=1, values={"can_lookup_students": True})
        common = {"known_provinces": provinces, "known_majors": majors, "latest_year": latest_year}
        on = await run_variant(name="dual_planning_on", cases=cases, db=db, context=context, common=common, multi_planning_enabled=True)
        off = await run_variant(name="dual_planning_off", cases=cases, db=db, context=context, common=common, multi_planning_enabled=False)

    on_summary = on["summary"]
    off_summary = off["summary"]
    result = {
        "evaluation_kind": "dual_planning_calibration_comparison",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset": "m1-real-calibration-v2",
        "sample_cases": len(cases),
        "sample_policy": f"first {args.per_category} cases per category from calibration only",
        "on": on_summary,
        "off": off_summary,
        "effect": {
            "accuracy_delta": round(on_summary["overall_accuracy"] - off_summary["overall_accuracy"], 4),
            "answer_accuracy_delta": round(on_summary["answer_accuracy"] - off_summary["answer_accuracy"], 4),
            "false_refusal_delta": round(off_summary["false_refusal_rate"] - on_summary["false_refusal_rate"], 4),
            "latency_p95_delta_ms": round(on_summary["latency_ms"]["p95"] - off_summary["latency_ms"]["p95"], 3),
            "triggered": on_summary["dual_planning_triggered"],
            "consistent": on_summary["dual_planning_consistent"],
        },
        "categories_on": on["categories"],
        "categories_off": off["categories"],
        "boundary": "Calibration-only comparison; no frozen test case is used for tuning. The local 3B planner is a slow optional path.",
    }
    (output_dir / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name, data in (("dual_planning_on", on), ("dual_planning_off", off)):
        (output_dir / f"{name}_per_case.jsonl").write_text(
            "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in data["rows"]) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
