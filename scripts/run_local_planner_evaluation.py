from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter
from typing import Any

from agent_core.benchmark import evaluate_case, load_cases, summarize_results
from agent_core.contracts import AgentContext
from agent_core.router import RuleRouter
from agent_core.runtime import AgentRuntime
from app.core.config import settings
from app.core.text import text
from app.modules.agent.providers import CompositePlanner
from app.modules.agent.tools.registry import NATIVE_TOOL_EXECUTORS
from scripts.run_demo_gold_evaluation import run_g1


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="evaluation/demo_gold_v1.jsonl")
    parser.add_argument("--output-dir", default="evaluation/results/local_planner_v1")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    cases = load_cases(root / args.cases)
    output_dir = root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    original_vector = settings.rag_vector_enabled
    settings.rag_vector_enabled = False
    from app.core.database import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as db:
            provinces = tuple((await db.execute(text("SELECT province_name FROM dim.province ORDER BY id"))).scalars().all())
            majors = tuple((await db.execute(text("SELECT major_name FROM dim.major WHERE is_active IS TRUE ORDER BY id"))).scalars().all())
            latest_year = int(await db.scalar(text("SELECT MAX(year_no) FROM dim.year")))

            async def execute(call, context):
                params = {**call.params, "school_id": context.school_id, "can_lookup_students": True}
                return await NATIVE_TOOL_EXECUTORS[call.name](db, params)

            runtime = AgentRuntime(
                tool_executor=execute,
                router=RuleRouter(),
                llm_planner=CompositePlanner(db),
                multi_planning_enabled=True,
                plan_consistency_threshold=settings.agent_plan_consistency_threshold,
                risk_threshold=settings.agent_risk_threshold,
                semantic_entropy_enabled=True,
                enforce_evidence_gate=True,
            )
            context = AgentContext(school_id=1, values={"can_lookup_students": True})
            common = {"known_provinces": provinces, "known_majors": majors, "latest_year": latest_year}
            rows: list[dict[str, Any]] = []
            for case in cases:
                case_started = perf_counter()
                result = await run_g1(case, runtime, context, **common)
                row = evaluate_case(case, result, (perf_counter() - case_started) * 1000)
                row["plan_summary"] = result.get("plan_summary")
                row["plan_consistency"] = result.get("plan_consistency")
                row["risk_strategy"] = (result.get("risk_decision") or {}).get("strategy")
                row["answer_conditions"] = (result.get("verification_summary") or {}).get("answer_conditions")
                rows.append(row)
    finally:
        settings.rag_vector_enabled = original_vector

    summary = summarize_results(rows)
    summary.update({
        "method": "g1_2_local_planner",
        "status": "completed",
        "model": settings.minimind_model,
        "model_enabled": settings.minimind_enabled,
        "dual_planning_triggered": sum(1 for row in rows if (row.get("plan_consistency") or {}).get("triggered")),
        "dual_planning_consistent": sum(
            1
            for row in rows
            if (row.get("plan_consistency") or {}).get("triggered")
            and (row.get("plan_consistency") or {}).get("consistent")
        ),
        "local_model_plans": sum(1 for row in rows if "本地模型" in str(row.get("plan_summary") or "")),
        "boundary": "本地 3B 规划器，演示数据库；不是真实授权冻结集实验。",
    })
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "per_case.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in rows) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
