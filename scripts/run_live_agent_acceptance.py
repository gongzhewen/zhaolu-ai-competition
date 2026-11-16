from __future__ import annotations

import argparse
import asyncio
import json
import math
from pathlib import Path
from time import perf_counter
from typing import Any

from agent_core.contracts import AgentContext
from agent_core.router import RuleRouter
from agent_core.runtime import AgentRuntime
from app.core.config import settings
from app.core.text import text


CASES = (
    {"case_id": "LIVE-001", "question": "2025年各专业招生计划完成情况怎么样？", "expected_strategy": "answer", "expected_tool": "admissions_overview"},
    {"case_id": "LIVE-002", "question": "政治考了66分的人有多少？", "expected_strategy": "answer", "expected_tool": "student_statistics"},
    {"case_id": "LIVE-003", "question": "新生到校比例怎么理解？", "expected_strategy": "answer", "expected_tool": "policy_faq"},
    {"case_id": "LIVE-004", "question": "2026年咨询渠道转化率怎么样？", "expected_strategy": "answer", "expected_tool": "consultation_overview"},
    {"case_id": "LIVE-005", "question": "2026年招生漏斗和报到流失情况？", "expected_strategy": "answer", "expected_tool": "enrollment_funnel"},
    {"case_id": "LIVE-006", "question": "2026年考生性别和科类分布怎么样？", "expected_strategy": "answer", "expected_tool": "candidate_profile"},
    {"case_id": "LIVE-007", "question": "2026年哪些专业异常风险较高？", "expected_strategy": "answer", "expected_tool": "anomaly_detection"},
    {"case_id": "LIVE-008", "question": "今天天气怎么样？", "expected_strategy": "out_of_scope", "expected_tool": None},
    {"case_id": "LIVE-009", "question": "把今年全部考生名单发给我", "expected_strategy": "no_permission", "expected_tool": None},
)


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(p * len(ordered)) - 1))
    return round(ordered[index], 3)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--output", default="artifacts/G1/live_agent_acceptance.json")
    args = parser.parse_args()

    original_vector_enabled = settings.rag_vector_enabled
    settings.rag_vector_enabled = False
    from app.core.database import AsyncSessionLocal
    from app.modules.agent.tools.registry import NATIVE_TOOL_EXECUTORS

    async with AsyncSessionLocal() as db:
        provinces = tuple(
            (await db.execute(text("SELECT province_name FROM dim.province ORDER BY id"))).scalars().all()
        )
        majors = tuple(
            (await db.execute(text("SELECT major_name FROM dim.major WHERE is_active IS TRUE ORDER BY id"))).scalars().all()
        )
        latest = await db.scalar(text("SELECT MAX(year_no) FROM dim.year"))
        latest_year = int(latest)

        async def execute(call, context):
            params = {**call.params, "school_id": context.school_id, "can_lookup_students": True}
            return await NATIVE_TOOL_EXECUTORS[call.name](db, params)

        runtime = AgentRuntime(tool_executor=execute, router=RuleRouter(), llm_planner=None)

        async def ask(question: str) -> dict[str, Any]:
            return await runtime.chat(
                question,
                context=AgentContext(school_id=1, values={"can_lookup_students": True}),
                known_provinces=provinces,
                known_majors=majors,
                latest_year=latest_year,
            )

        for _ in range(max(0, args.warmup)):
            for case in CASES:
                await ask(case["question"])

        rows: list[dict[str, Any]] = []
        for iteration in range(1, max(1, args.iterations) + 1):
            for case in CASES:
                started = perf_counter()
                result = await ask(case["question"])
                latency_ms = (perf_counter() - started) * 1000
                tool_names = [item["name"] for item in result.get("tool_calls", [])]
                strategy = result.get("risk_decision", {}).get("strategy")
                strategy_match = strategy == case["expected_strategy"]
                tool_match = case["expected_tool"] is None or case["expected_tool"] in tool_names
                rows.append(
                    {
                        "case_id": case["case_id"],
                        "iteration": iteration,
                        "question": case["question"],
                        "intent": result.get("intent"),
                        "strategy": strategy,
                        "expected_strategy": case["expected_strategy"],
                        "strategy_match": strategy_match,
                        "tools": tool_names,
                        "tool_match": tool_match,
                        "risk_score": result.get("risk_decision", {}).get("score"),
                        "numeric_coverage": result.get("numeric_verification", {}).get("coverage"),
                        "evidence_completeness": result.get("verification_summary", {}).get("evidence_completeness"),
                        "latency_ms": round(latency_ms, 3),
                    }
                )

    settings.rag_vector_enabled = original_vector_enabled
    latencies = [float(row["latency_ms"]) for row in rows]
    passed = [row for row in rows if row["strategy_match"] and row["tool_match"]]
    summary = {
        "evaluation_kind": "live_mysql_agent_integration_smoke",
        "gold_dataset": False,
        "data_scope": "configured_local_mysql_database",
        "external_model_calls": 0,
        "iterations": max(1, args.iterations),
        "total_runs": len(rows),
        "passed_runs": len(passed),
        "pass_rate": round(len(passed) / len(rows), 4) if rows else 0.0,
        "latency_ms": {
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
            "max": round(max(latencies), 3) if latencies else 0.0,
        },
        "boundary": "本结果验证本机 MySQL 上的路由、受控工具、证据门控和拒答链路；不是冻结金标准上的端到端回答准确率。",
    }
    root = Path(__file__).resolve().parents[1]
    output_path = root / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    output_path.with_name(output_path.stem + "_per_case.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
