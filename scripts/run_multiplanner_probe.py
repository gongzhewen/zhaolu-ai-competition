from __future__ import annotations

import asyncio
import json
from pathlib import Path
from time import perf_counter

from agent_core.contracts import AgentContext
from agent_core.router import RuleRouter
from agent_core.runtime import AgentRuntime
from app.core.config import settings
from app.core.text import text
from app.modules.agent.providers import CompositePlanner
from app.modules.agent.tools.registry import NATIVE_TOOL_EXECUTORS


CASES = (
    ("预测2026年土木工程招生计划和录取情况，并分析历史趋势", "forecast"),
    ("结合历史趋势预测2027年人工智能专业招生规模", "forecast"),
    ("分析2026年临床医学专业计划完成风险并预测明年计划", "forecast"),
    ("为什么2026年计算机科学与技术专业招生计划可能需要调整", "forecast"),
    ("如果土木工程增加20个计划，结合历史完成率和志愿热度分析风险", "plan_simulation"),
    ("计算机科学与技术减少10个计划会怎样，结合志愿热度评估风险", "plan_simulation"),
    ("比较2025和2026年软件工程录取趋势并解释原因", "trend_analysis"),
    ("综合分析2026年招生计划和生源情况，给出优化建议", "cross_metric"),
)


async def main() -> None:
    root = Path(__file__).resolve().parents[1]
    original_vector = settings.rag_vector_enabled
    settings.rag_vector_enabled = False
    from app.core.database import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as db:
            provinces = tuple((await db.execute(text("SELECT province_name FROM dim.province ORDER BY id"))).scalars().all())
            majors = tuple((await db.execute(text("SELECT major_name FROM dim.major WHERE is_active IS TRUE ORDER BY id"))).scalars().all())
            latest_year = int(await db.scalar(text("SELECT MAX(year_no) FROM dim.year")))

            async def execute(call, context):
                return await NATIVE_TOOL_EXECUTORS[call.name](db, {**call.params, "school_id": context.school_id, "can_lookup_students": True})

            runtime = AgentRuntime(
                tool_executor=execute,
                router=RuleRouter(),
                llm_planner=CompositePlanner(db),
                multi_planning_enabled=True,
                plan_consistency_threshold=settings.agent_plan_consistency_threshold,
                risk_threshold=settings.agent_risk_threshold,
            )
            context = AgentContext(school_id=1, values={"can_lookup_students": True})
            rows = []
            for index, (question, category) in enumerate(CASES, 1):
                started = perf_counter()
                result = await runtime.chat(
                    question,
                    context=context,
                    known_provinces=provinces,
                    known_majors=majors,
                    latest_year=latest_year,
                )
                consistency = result.get("plan_consistency") or {}
                rows.append({
                    "case_id": f"MULTI-{index:03d}",
                    "category": category,
                    "question": question,
                    "intent": result.get("intent"),
                    "plan_summary": result.get("plan_summary"),
                    "tools": [item["name"] for item in result.get("tool_calls", [])],
                    "triggered": bool(consistency.get("triggered")),
                    "consistent": bool(consistency.get("consistent")),
                    "similarity": consistency.get("score"),
                    "strategy": (result.get("risk_decision") or {}).get("strategy"),
                    "can_answer": ((result.get("verification_summary") or {}).get("answer_conditions") or {}).get("can_answer"),
                    "answer": result.get("answer"),
                    "latency_ms": round((perf_counter() - started) * 1000, 2),
                })
    finally:
        settings.rag_vector_enabled = original_vector

    summary = {
        "evaluation_kind": "multiplanner_high_risk_probe",
        "model": settings.minimind_model,
        "cases": len(rows),
        "local_model_plans": sum(1 for row in rows if "本地模型" in str(row.get("plan_summary") or "")),
        "dual_planning_triggered": sum(1 for row in rows if row["triggered"]),
        "dual_planning_consistent": sum(1 for row in rows if row["triggered"] and row["consistent"]),
        "answered": sum(1 for row in rows if row["strategy"] == "answer"),
        "blocked": sum(1 for row in rows if row["strategy"] != "answer"),
        "latency_ms": {
            "p50": sorted(row["latency_ms"] for row in rows)[len(rows)//2],
            "max": max(row["latency_ms"] for row in rows),
        },
        "cases_detail": rows,
        "boundary": "高风险探针用于验证双计划触发与一致性门控，不是准确率金标准。",
    }
    output = root / "artifacts/G7/multiplanner_probe.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
