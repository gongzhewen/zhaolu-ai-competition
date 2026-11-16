from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from agent_core.contracts import AgentContext
from agent_core.router import RuleRouter
from agent_core.runtime import AgentRuntime
from app.core.database import AsyncSessionLocal
from app.core.text import text
from app.modules.agent.tools.registry import NATIVE_TOOL_EXECUTORS
from scripts.run_real_frozen_evaluation import evaluate_row, load_gold, summarize


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--cases', default='local_private/gold/real_calibration_gold_v2.jsonl')
    parser.add_argument('--output-dir', default='local_private/results/real_calibration_v2')
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
    if any(case.get('split') != 'calibration' for case in cases):
        raise ValueError('calibration runner accepts calibration split only')
    async with AsyncSessionLocal() as db:
        provinces = tuple((await db.execute(text('SELECT province_name FROM dim.province ORDER BY id'))).scalars().all())
        majors = tuple((await db.execute(text('SELECT major_name FROM dim.major WHERE is_active IS TRUE ORDER BY id'))).scalars().all())
        latest_year = 2023

        async def execute(call, context):
            return await NATIVE_TOOL_EXECUTORS[call.name](db, {**call.params, 'school_id': context.school_id, 'can_lookup_students': True})

        runtime = AgentRuntime(tool_executor=execute, router=RuleRouter(), llm_planner=None, multi_planning_enabled=False)
        context = AgentContext(school_id=1, values={'can_lookup_students': True})
        common = {'known_provinces': provinces, 'known_majors': majors, 'latest_year': latest_year}
        rows = []
        started = perf_counter()
        for case in cases:
            case_started = perf_counter()
            result = await runtime.chat(case['question'], context=context, **common)
            row = evaluate_row(case, result, (perf_counter() - case_started) * 1000, None)
            row['plan_consistency'] = result.get('plan_consistency')
            rows.append(row)
    summary = summarize(rows, 'g1_full', perf_counter() - started)
    summary.update({
        'status': 'completed',
        'split': 'calibration',
        'dataset': 'm1-real-calibration-v2',
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'boundary': 'Calibration-only run; used to fit thresholds, never for final test scoring.',
    })
    (output_dir / 'g1_full_per_case.jsonl').write_text(
        '\n'.join(json.dumps(row, ensure_ascii=False, default=str) for row in rows) + '\n', encoding='utf-8'
    )
    (output_dir / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
