from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

import agent_core.runtime as runtime_module
from agent_core.contracts import AgentContext
from agent_core.privacy import PrivacyAssessment
from agent_core.router import RuleRouter
from agent_core.runtime import AgentRuntime
from app.core.database import AsyncSessionLocal
from app.core.text import text
from app.modules.agent.tools.registry import NATIVE_TOOL_EXECUTORS
from scripts.run_real_frozen_evaluation import category_summary, evaluate_row, load_gold, summarize, to_case


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="local_private/gold/real_frozen_test_gold_v2.jsonl")
    parser.add_argument("--output-dir", default="local_private/results/real_frozen_v2_ablation")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    cases_path = Path(args.cases)
    if not cases_path.is_absolute():
        cases_path = root / cases_path
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = load_gold(cases_path)

    async with AsyncSessionLocal() as db:
        provinces = tuple((await db.execute(text("SELECT province_name FROM dim.province ORDER BY id"))).scalars().all())
        majors = tuple((await db.execute(text("SELECT major_name FROM dim.major WHERE is_active IS TRUE ORDER BY id"))).scalars().all())
        latest_year = int(await db.scalar(text("SELECT MAX(year_no) FROM dim.year")))
        context = AgentContext(school_id=1, values={"can_lookup_students": True})
        common = {"known_provinces": provinces, "known_majors": majors, "latest_year": latest_year}

        async def full_execute(call, agent_context):
            return await NATIVE_TOOL_EXECUTORS[call.name](db, {**call.params, "school_id": agent_context.school_id, "can_lookup_students": True})

        async def alias_disabled_execute(call, agent_context):
            if call.name == "major_alias_lookup":
                return {
                    "answer": "未启用专业别名标准化。",
                    "charts": [],
                    "table": None,
                    "data_sources": [],
                    "metrics": {"matched": 0, "alias_normalization": "disabled"},
                }
            return await full_execute(call, agent_context)

        async def run_variant(name: str, runtime: AgentRuntime) -> dict[str, Any]:
            if cases:
                await runtime.chat(cases[0]["question"], context=context, **common)
            rows = []
            started = perf_counter()
            for case in cases:
                case_started = perf_counter()
                result = await runtime.chat(case["question"], context=context, **common)
                row = evaluate_row(case, result, (perf_counter() - case_started) * 1000, None)
                row["variant"] = name
                rows.append(row)
            summary = summarize(rows, name, perf_counter() - started)
            (output_dir / f"{name}_per_case.jsonl").write_text(
                "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in rows) + "\n",
                encoding="utf-8",
            )
            return {"summary": summary, "categories": category_summary(rows, name), "rows": rows}

        alias_runtime = AgentRuntime(tool_executor=alias_disabled_execute, router=RuleRouter(), llm_planner=None)
        alias_result = await run_variant("no_alias_normalization", alias_runtime)

        original_request_privacy = runtime_module.assess_request_privacy
        original_result_privacy = runtime_module.assess_result_privacy
        original_sensitive = RuleRouter.__dict__["_is_sensitive_request"]
        runtime_module.assess_request_privacy = lambda *args, **kwargs: PrivacyAssessment(allowed=True, risk=0.0, reasons=[])
        runtime_module.assess_result_privacy = lambda *args, **kwargs: PrivacyAssessment(allowed=True, risk=0.0, reasons=[])
        RuleRouter._is_sensitive_request = staticmethod(lambda text: False)
        try:
            privacy_runtime = AgentRuntime(tool_executor=full_execute, router=RuleRouter(), llm_planner=None)
            privacy_result = await run_variant("no_privacy_hard_constraint", privacy_runtime)
        finally:
            runtime_module.assess_request_privacy = original_request_privacy
            runtime_module.assess_result_privacy = original_result_privacy
            RuleRouter._is_sensitive_request = original_sensitive

    full_summary = load_json(root / "local_private/results/real_frozen_v2/summary.json")
    full_method = next(item for item in full_summary["summaries"] if item["method"] == "g1_full")
    alias_cases = [case for case in cases if case["category"] == "专业别名和口语表达"]
    privacy_cases = [case for case in cases if case["category"] == "隐私小样本与超范围"]
    result = {
        "evaluation_kind": "real_frozen_v2_ablation",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset": "m1-real-frozen-v2",
        "full_reference": full_method,
        "variants": [alias_result["summary"], privacy_result["summary"]],
        "effects": {
            "alias_normalization": {
                "cases": len(alias_cases),
                "full_answer_accuracy": full_method["answer_accuracy"],
                "without_alias_answer_accuracy": alias_result["summary"]["answer_accuracy"],
                "accuracy_delta": round(full_method["answer_accuracy"] - alias_result["summary"]["answer_accuracy"], 4),
            },
            "privacy_hard_constraint": {
                "cases": len(privacy_cases),
                "full_correct_refusal_rate": full_method["correct_refusal_rate"],
                "without_privacy_correct_refusal_rate": privacy_result["summary"]["correct_refusal_rate"],
                "full_privacy_violations": full_method["privacy_violations"],
                "without_privacy_privacy_violations": privacy_result["summary"]["privacy_violations"],
            },
        },
        "boundary": "Privacy-off variant is an isolated local aggregate evaluation only; no PII was exported and no production switch was added.",
    }
    (output_dir / "ablation_summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())


