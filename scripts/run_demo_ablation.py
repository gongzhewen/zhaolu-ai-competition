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
from app.modules.agent.tools.registry import NATIVE_TOOL_EXECUTORS
from scripts.run_demo_gold_evaluation import run_g0, run_g1


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="evaluation/demo_gold_v1.jsonl")
    parser.add_argument("--output-dir", default="evaluation/results/ablation_v1")
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

            context = AgentContext(school_id=1, values={"can_lookup_students": True})
            common = {"known_provinces": provinces, "known_majors": majors, "latest_year": latest_year}
            variants: dict[str, Any] = {
                "g1_2_full": AgentRuntime(tool_executor=execute, router=RuleRouter(), llm_planner=None),
                "no_entropy": AgentRuntime(tool_executor=execute, router=RuleRouter(), llm_planner=None, semantic_entropy_enabled=False),
                "no_evidence_gate": AgentRuntime(tool_executor=execute, router=RuleRouter(), llm_planner=None, enforce_evidence_gate=False),
                "no_multi_planning": AgentRuntime(tool_executor=execute, router=RuleRouter(), llm_planner=None, multi_planning_enabled=False),
                "threshold_0_37535": AgentRuntime(tool_executor=execute, router=RuleRouter(), llm_planner=None, risk_threshold=0.37535),
            }
            summaries: list[dict[str, Any]] = []
            all_rows: list[dict[str, Any]] = []
            for name, runtime in variants.items():
                started = perf_counter()
                rows: list[dict[str, Any]] = []
                for case in cases:
                    case_started = perf_counter()
                    result = await run_g1(case, runtime, context, **common)
                    row = evaluate_case(case, result, (perf_counter() - case_started) * 1000)
                    row["method"] = name
                    rows.append(row)
                    all_rows.append(row)
                summary = summarize_results(rows)
                summary["method"] = name
                summary["elapsed_seconds"] = round(perf_counter() - started, 3)
                summaries.append(summary)

            g0_rows: list[dict[str, Any]] = []
            for case in cases:
                case_started = perf_counter()
                result = await run_g0(case, router=RuleRouter(), db=db, context=context, **common)
                row = evaluate_case(case, result, (perf_counter() - case_started) * 1000)
                row["method"] = "g0_rule_tool"
                g0_rows.append(row)
                all_rows.append(row)
            g0_summary = summarize_results(g0_rows)
            g0_summary["method"] = "g0_rule_tool"
            summaries.append(g0_summary)
    finally:
        settings.rag_vector_enabled = original_vector

    (output_dir / "summary.json").write_text(json.dumps({"variants": summaries}, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "per_case.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in all_rows) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"variants": summaries}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
