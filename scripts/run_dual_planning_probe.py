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
from app.modules.agent.providers import CompositePlanner
from app.modules.agent.tools.registry import NATIVE_TOOL_EXECUTORS

CASES = (
    ('预测2023年土木工程招生计划和录取情况，并分析历史趋势', 'forecast'),
    ('结合历史趋势预测2024年人工智能专业招生规模', 'forecast'),
    ('分析2023年临床医学专业计划完成风险并预测明年计划', 'forecast'),
    ('为什么2023年计算机科学与技术专业招生计划可能需要调整', 'cross_metric'),
    ('如果土木工程增加20个计划，结合历史完成率和志愿热度分析风险', 'plan_simulation'),
    ('计算机科学与技术减少10个计划会怎样，结合志愿热度评估风险', 'plan_simulation'),
    ('比较2022和2023年软件工程录取趋势并解释原因', 'trend_analysis'),
    ('综合分析2023年招生计划和生源情况，给出优化建议', 'cross_metric'),
    ('预测2023年各省招生计划变化并说明风险', 'forecast'),
    ('结合2022到2023年历史数据预测2024年招生计划', 'forecast'),
    ('分析2023年专业计划完成率和志愿热度之间的风险', 'anomaly_detection'),
    ('如果人工智能扩招15个计划，计划完成率和报到率会如何变化', 'plan_simulation'),
    ('比较2022年和2023年不同省份的录取规模和完成率', 'trend_analysis'),
    ('为什么2023年招生计划与录取人数出现差异，给出调整建议', 'cross_metric'),
    ('分析2023年临床医学专业异常波动和计划缺口', 'anomaly_detection'),
    ('预测2024年计算机科学与技术专业招生规模，考虑志愿热度', 'forecast'),
    ('如果软件工程减少10个计划，报到率和风险如何变化', 'plan_simulation'),
    ('综合分析2023年招生计划、录取和报到情况，给出决策建议', 'cross_metric'),
    ('预测2023年各学院计划完成率并识别高风险专业', 'forecast'),
    ('比较2022和2023年各省生源和报到趋势', 'trend_analysis'),
    ('分析2023年计划调整对录取和报到的影响', 'cross_metric'),
    ('如果增加专项计划20个，结合历史计划完成率评估风险', 'plan_simulation'),
    ('预测2024年招生计划时，哪些专业需要优先调整', 'forecast'),
    ('综合分析2022到2023年招生、成绩和志愿数据，给出专业优化建议', 'cross_metric'),
)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', default='artifacts/G7')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    async with AsyncSessionLocal() as db:
        provinces = tuple((await db.execute(text('SELECT province_name FROM dim.province ORDER BY id'))).scalars().all())
        majors = tuple((await db.execute(text('SELECT major_name FROM dim.major WHERE is_active IS TRUE ORDER BY id'))).scalars().all())
        latest_year = 2023
        context = AgentContext(school_id=1, values={'can_lookup_students': True})

        async def execute(call, agent_context):
            return await NATIVE_TOOL_EXECUTORS[call.name](db, {**call.params, 'school_id': agent_context.school_id, 'can_lookup_students': True})

        async def run(name: str, enabled: bool) -> dict[str, Any]:
            runtime = AgentRuntime(
                tool_executor=execute,
                router=RuleRouter(),
                llm_planner=CompositePlanner(db),
                multi_planning_enabled=enabled,
                plan_consistency_threshold=0.95,
                risk_threshold=0.32,
                semantic_entropy_enabled=True,
                enforce_evidence_gate=True,
            )
            rows = []
            started = perf_counter()
            for index, (question, category) in enumerate(CASES, 1):
                case_started = perf_counter()
                result = await runtime.chat(question, context=context, known_provinces=provinces, known_majors=majors, latest_year=latest_year)
                consistency = result.get('plan_consistency') or {}
                rows.append({
                    'case_id': f'DUAL-{index:03d}',
                    'category': category,
                    'question': question,
                    'intent': result.get('intent'),
                    'plan_summary': result.get('plan_summary'),
                    'tools': [item['name'] for item in result.get('tool_calls', [])],
                    'triggered': bool(consistency.get('triggered')),
                    'consistent': bool(consistency.get('consistent')),
                    'similarity': consistency.get('score'),
                    'strategy': (result.get('risk_decision') or {}).get('strategy'),
                    'can_answer': ((result.get('verification_summary') or {}).get('answer_conditions') or {}).get('can_answer'),
                    'latency_ms': round((perf_counter() - case_started) * 1000, 2),
                })
            latencies = sorted(row['latency_ms'] for row in rows)
            return {
                'variant': name,
                'cases': len(rows),
                'local_model_plans': sum(1 for row in rows if '本地模型' in str(row.get('plan_summary') or '')),
                'dual_planning_triggered': sum(1 for row in rows if row['triggered']),
                'dual_planning_consistent': sum(1 for row in rows if row['triggered'] and row['consistent']),
                'answered': sum(1 for row in rows if row['strategy'] == 'answer'),
                'blocked': sum(1 for row in rows if row['strategy'] != 'answer'),
                'latency_ms': {'p50': latencies[len(latencies)//2], 'p95': latencies[min(len(latencies)-1, int(len(latencies)*0.95))], 'max': max(latencies)},
                'elapsed_seconds': round(perf_counter() - started, 3),
                'cases_detail': rows,
            }

        on = await run('dual_planning_on', True)
        off = await run('dual_planning_off', False)

    result = {
        'evaluation_kind': 'dual_planning_calibration_probe',
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'dataset_years': [2022, 2023],
        'sample_policy': '24 high-risk probe questions using calibration years only',
        'on': on,
        'off': off,
        'effect': {
            'triggered_delta': on['dual_planning_triggered'] - off['dual_planning_triggered'],
            'consistent_delta': on['dual_planning_consistent'] - off['dual_planning_consistent'],
            'answered_delta': on['answered'] - off['answered'],
            'blocked_delta': on['blocked'] - off['blocked'],
            'p95_latency_delta_ms': round(on['latency_ms']['p95'] - off['latency_ms']['p95'], 2),
        },
        'boundary': 'No gold answer scoring in this probe; it measures trigger behavior and gating, not answer accuracy.',
    }
    (output_dir / 'dual_planning_probe_20261109.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
