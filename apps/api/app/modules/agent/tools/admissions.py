from __future__ import annotations

import re
from typing import Any

from app.core.text import text
from sqlalchemy.ext.asyncio import AsyncSession

from agent_core.analytics import build_expansion_decision
from agent_core.extractors import is_multi_year_question
from app.modules.agent.tools.common import bar_chart, trend_chart
from app.modules.analytics import service
from app.modules.forecast import service as forecast_service


async def admissions_overview(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    overview = await service.get_admissions_overview(
        db,
        year=params.get("year"),
        province=params.get("province"),
        major=params.get("major"),
    )
    metrics = overview["metrics"]
    if int(metrics.get("plan_count") or 0) == 0:
        year_no = params.get("year")
        return {
            "answer": f"{year_no or '当前年度'}未找到招生计划数据，请确认该年度数据是否已导入。",
            "charts": [],
            "table": None,
            "data_sources": [{"table": "fact.plan", "metric": "年度招生计划"}],
            "metrics": {"year_no": year_no, "has_data": False, "plan_count": 0},
        }
    query = str(params.get("query") or "")
    trend = sorted(overview.get("year_trend", []), key=lambda item: item["year_no"])
    if is_multi_year_question(query) and len(trend) > 1:
        details = "；".join(
            (
                f"{item['year_no']} 年计划 {item['plan_count']} 人、"
                f"录取 {item['admitted_count']} 人、完成率 {item['completion_rate']}%"
            )
            for item in trend
        )
        scope = f"{params['major']}专业" if params.get("major") else "招生"
        result_metrics = {
            "data_points": len(trend),
            "start_year": trend[0]["year_no"],
            "end_year": trend[-1]["year_no"],
        }
        query_years = sorted({int(item) for item in re.findall(r"20\d{2}", query)})
        metric_name = None
        metric_label = None
        if "计划数" in query:
            metric_name, metric_label = "plan_count", "计划数"
        elif "录取数" in query:
            metric_name, metric_label = "admitted_count", "录取数"
        elif "报到数" in query:
            metric_name, metric_label = "enrolled_count", "报到数"
        elif "完成率" in query:
            metric_name, metric_label = "completion_rate", "计划完成率"
        if len(query_years) >= 2 and metric_name:
            start_year, end_year = query_years[0], query_years[-1]
            result_metrics.update({"start_year": start_year, "end_year": end_year})
            values: dict[int, Any] = {}
            if metric_name in {"plan_count", "admitted_count", "completion_rate"}:
                for item in trend:
                    if int(item["year_no"]) in {start_year, end_year}:
                        values[int(item["year_no"])] = item[metric_name]
            else:
                clauses = ["y.year_no IN (:start_year, :end_year)"]
                binds: dict[str, Any] = {"start_year": start_year, "end_year": end_year}
                if params.get("province"):
                    clauses.append("pr.province_name=:province")
                    binds["province"] = params["province"]
                if params.get("major"):
                    clauses.append("m.major_name=:major")
                    binds["major"] = params["major"]
                enrolled_rows = await db.execute(
                    text(
                        f"""
                        SELECT y.year_no,
                               COALESCE(SUM(CASE WHEN ar.is_enrolled=1 THEN 1 ELSE 0 END),0) AS enrolled_count
                        FROM fact.admission_record ar
                        JOIN dim.year y ON y.id=ar.year_id
                        JOIN dim.province pr ON pr.id=ar.province_id
                        JOIN dim.major m ON m.id=ar.major_id
                        WHERE {' AND '.join(clauses)}
                        GROUP BY y.year_no
                        """
                    ),
                    binds,
                )
                values = {int(row["year_no"]): int(row["enrolled_count"] or 0) for row in enrolled_rows.mappings().all()}
            if start_year in values and end_year in values:
                start_value = values[start_year]
                end_value = values[end_year]
                delta = end_value - start_value
                result_metrics.update({
                    "start_value": start_value,
                    "end_value": end_value,
                    "delta": delta,
                    "delta_rate": round(delta / start_value * 100, 2) if start_value else 0.0,
                })
                details += (
                    f" 其中{metric_label}由 {start_value} 变为 {end_value}，"
                    f"变化 {delta}，变化率 {result_metrics['delta_rate']}%。"
                )
        return {
            "answer": f"{scope}跨年度趋势为：{details}。",
            "charts": [
                trend_chart(
                    "招生计划与录取趋势",
                    [str(item["year_no"]) for item in trend],
                    [item["plan_count"] for item in trend],
                    [item["admitted_count"] for item in trend],
                )
            ],
            "table": {
                "columns": ["年度", "计划数", "录取数", "完成率"],
                "rows": [
                    [item["year_no"], item["plan_count"], item["admitted_count"], item["completion_rate"]]
                    for item in trend
                ],
            },
            "data_sources": [
                {"table": "fact.plan", "metric": "年度招生计划"},
                {"table": "fact.admission_record", "metric": "年度录取汇总"},
            ],
            "metrics": result_metrics,
        }
    wants_major_breakdown = (
        not params.get("major")
        and any(keyword in query for keyword in ("各专业", "每个专业", "每专业", "分专业", "专业完成率"))
    )
    if wants_major_breakdown:
        rows = overview.get("by_major", [])
        year_label = f"{params['year']}年" if params.get("year") else "当前年度"
        details = "；".join(
            f"{row['major_name']}计划 {row['plan_count']} 人、录取 {row['admitted_count']} 人、完成率 {row['completion_rate']}%"
            for row in rows[:12]
        )
        answer = f"{year_label}各专业计划完成率：{details}。" if details else f"{year_label}未找到专业计划数据。"
        return {
            "answer": answer,
            "charts": [
                bar_chart(
                    "各专业计划完成率",
                    [row["major_name"] for row in rows[:20]],
                    [row["completion_rate"] for row in rows[:20]],
                )
            ],
            "table": {
                "columns": ["专业", "计划数", "录取数", "完成率", "最低分"],
                "rows": [
                    [row["major_name"], row["plan_count"], row["admitted_count"], row["completion_rate"], row["min_score"]]
                    for row in rows
                ],
            },
            "data_sources": [
                {"table": "fact.plan", "metric": "分专业招生计划"},
                {"table": "fact.admission_record", "metric": "分专业录取汇总"},
            ],
            "metrics": {
                "plan_count": metrics["plan_count"],
                "admitted_count": metrics["admitted_count"],
                "completion_rate": metrics["completion_rate"],
                "major_count": len(rows),
            },
        }
    if params.get("group_by") == "province_name":
        rows = overview.get("by_province", [])
        year_label = f"{params['year']}年" if params.get("year") else "最新年度"
        details = "；".join(
            f"{row['province_name']}计划 {row['plan_count']} 人、录取 {row['admitted_count']} 人、完成率 {row['completion_rate']}%"
            for row in rows[:12]
        )
        answer = f"{year_label}各省招生计划情况：{details}。" if details else f"{year_label}未找到各省招生计划数据。"
        return {
            "answer": answer,
            "charts": [
                bar_chart(
                    "各省招生计划",
                    [row["province_name"] for row in rows[:20]],
                    [row["plan_count"] for row in rows[:20]],
                )
            ],
            "table": {
                "columns": ["省份", "计划数", "录取数", "完成率", "最低分"],
                "rows": [
                    [row["province_name"], row["plan_count"], row["admitted_count"], row["completion_rate"], row["min_score"]]
                    for row in rows[:30]
                ],
            },
            "data_sources": [
                {"table": "fact.plan", "metric": "分省招生计划"},
                {"table": "fact.admission_record", "metric": "分省录取汇总"},
            ],
            "metrics": {
                "plan_count": metrics["plan_count"],
                "admitted_count": metrics["admitted_count"],
                "completion_rate": metrics["completion_rate"],
                "province_count": len(rows),
            },
        }
    answer = (
        f"当前招生计划 {metrics['plan_count']} 人，实际录取 {metrics['admitted_count']} 人，"
        f"计划完成率 {metrics['completion_rate']}%。"
    )
    if metrics.get("min_score") is not None:
        answer += f" 最低录取分 {metrics['min_score']}。"
    if not params.get("major") and overview["by_major"]:
        top = overview["by_major"][0]
        answer += (
            f" 计划规模最大的专业是{top['major_name']}，计划 {top['plan_count']} 人，"
            f"完成率 {top['completion_rate']}%。"
        )
    chart = bar_chart(
        "专业招生计划",
        [row["major_name"] for row in overview["by_major"][:20]],
        [row["plan_count"] for row in overview["by_major"][:20]],
    )
    table = {
        "columns": ["专业", "计划数", "录取数", "完成率", "最低分"],
        "rows": [
            [
                row["major_name"],
                row["plan_count"],
                row["admitted_count"],
                row["completion_rate"],
                row["min_score"],
            ]
            for row in overview["by_major"][:30]
        ],
    }
    return {
        "answer": answer,
        "charts": [chart],
        "table": table,
        "data_sources": [
            {"table": "fact.plan", "metric": "招生计划"},
            {"table": "fact.admission_record", "metric": "录取汇总"},
        ],
        "metrics": metrics,
    }


async def forecast(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    overview = await forecast_service.get_forecast_overview(
        db,
        year=params.get("year"),
        province=params.get("province"),
        major=params.get("major"),
    )
    result = overview.get("forecast")
    if not result:
        return {
            "answer": "当前缺少足够的年份数据，暂时无法完成预测。",
            "charts": [],
            "table": None,
            "data_sources": [{"table": "fact.plan", "metric": "预测输入"}],
            "metrics": {"data_points": 0},
        }
    answer = (
        f"预测 {result['year']} 年招生计划 {result['plan_count']} 人，"
        f"录取人数 {result['admitted_count']} 人，计划完成率 {result['completion_rate']}%，"
        f"风险等级为 {result['risk_level']}。"
    )
    return {
        "answer": answer,
        "charts": [],
        "table": None,
        "data_sources": [{"table": "fact.plan", "metric": "趋势预测"}],
        "metrics": result,
    }


async def anomaly_detection(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    overview = await service.get_anomalies(db, year=params.get("year"))
    items = overview.get("items", [])
    summary = overview.get("summary", {})
    year_no = overview.get("year_no")
    if not year_no:
        answer = overview.get("message", "暂无可用于异常检测的数据。")
    elif not items:
        answer = f"{year_no} 年未检测到达到规则阈值的专业异常。"
    else:
        leading = "；".join(
            f"{item['major_name']}：{item['message']}，建议{item['suggestion']}"
            for item in items[:5]
        )
        answer = (
            f"{year_no} 年共检测到 {summary.get('total_anomalies', 0)} 项专业异常，"
            f"其中高风险 {summary.get('high', 0)} 项、中风险 {summary.get('medium', 0)} 项。"
            f"重点异常：{leading}。"
        )
    chart = bar_chart(
        "专业异常热度",
        [item["major_name"] for item in items[:20]],
        [item["demand_ratio"] for item in items[:20]],
    )
    table = {
        "columns": ["专业", "等级", "异常原因", "完成率", "志愿热度比", "建议"],
        "rows": [
            [
                item["major_name"],
                item["severity"],
                item["message"],
                item["completion_rate"],
                item["demand_ratio"],
                item["suggestion"],
            ]
            for item in items[:30]
        ],
    }
    return {
        "answer": answer,
        "charts": [chart] if items else [],
        "table": table if items else None,
        "data_sources": overview.get("data_sources", []),
        "metrics": {"year_no": year_no, **summary},
    }


async def official_admission_stats(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    year = params.get("year")
    rows_result = await db.execute(
        text(
            """
            SELECT
                year_no,
                COALESCE(SUM(plan_count), 0) AS regular_plan,
                COALESCE(SUM(regular_admitted_count), 0) AS regular_admitted,
                COALESCE(SUM(zhuan_admitted_count), 0) AS zhuan_admitted,
                COALESCE(SUM(total_admitted_count), 0) AS total_admitted
            FROM fact.authoritative_admission_stat
            WHERE (data_version LIKE 'official-%' OR data_version LIKE 'source-%')
              AND (CAST(:year AS integer) IS NULL OR year_no = :year)
            GROUP BY year_no
            ORDER BY year_no
            """
        ),
        {"year": year},
    )
    rows = [dict(row) for row in rows_result.mappings().all()]
    if not rows:
        return {
            "answer": "当前没有对应年度的官方招生统计。",
            "charts": [],
            "table": None,
            "data_sources": [{"table": "fact.authoritative_admission_stat", "metric": "官方招生统计"}],
            "metrics": {"data_points": 0},
        }
    if len(rows) == 1:
        item = rows[0]
        answer = (
            f"{item['year_no']} 年普通招生计划 {item['regular_plan']} 人，"
            f"普通录取 {item['regular_admitted']} 人，专升本 {item['zhuan_admitted']} 人，"
            f"总录取 {item['total_admitted']} 人。"
        )
    else:
        details = "；".join(
            (
                f"{item['year_no']} 年普通计划 {item['regular_plan']} 人、"
                f"普通录取 {item['regular_admitted']} 人、专升本 {item['zhuan_admitted']} 人、"
                f"总录取 {item['total_admitted']} 人"
            )
            for item in rows
        )
        answer = f"2024—2026 年官方招生统计为：{details}。"
    chart = bar_chart(
        "年度官方录取人数",
        [str(item["year_no"]) for item in rows],
        [int(item["total_admitted"]) for item in rows],
    )
    table = {
        "columns": ["年度", "普通计划", "普通录取", "专升本", "总录取"],
        "rows": [
            [
                item["year_no"],
                item["regular_plan"],
                item["regular_admitted"],
                item["zhuan_admitted"],
                item["total_admitted"],
            ]
            for item in rows
        ],
    }
    metrics = {"data_points": len(rows), "years": [item["year_no"] for item in rows]}
    if len(rows) == 1:
        item = rows[0]
        metrics.update({
            "official_plan_count": int(item["regular_plan"]),
            "official_regular_admitted": int(item["regular_admitted"]),
            "official_zhuan_admitted": int(item["zhuan_admitted"]),
            "official_total_admitted": int(item["total_admitted"]),
        })
    return {
        "answer": answer,
        "charts": [chart],
        "table": table,
        "data_sources": [{"table": "fact.authoritative_admission_stat", "metric": "官方招生统计"}],
        "metrics": metrics,
    }


async def _expansion_decision_context(
    db: AsyncSession,
    *,
    major_name: str,
    year: int | None,
) -> tuple[int | None, dict[str, Any] | None, dict[str, Any] | None]:
    year_no = await service._resolve_data_year(db, year)
    metric = None
    if year_no is not None:
        metrics = await service._get_major_year_metrics(db, year_no)
        metric = metrics.get(major_name)
    forecast_overview = await forecast_service.get_forecast_overview(
        db,
        year=year,
        major=major_name,
    )
    return year_no, metric, forecast_overview.get("forecast")


async def plan_simulation(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    raw_adjustments = params.get("adjustments")
    adjustments: list[dict[str, Any]] = []
    if isinstance(raw_adjustments, list):
        for item in raw_adjustments:
            if not isinstance(item, dict) or not item.get("major_name"):
                continue
            try:
                adjustments.append(
                    {
                        "major_name": str(item["major_name"]),
                        "plan_delta": int(item.get("plan_delta") or 0),
                    }
                )
            except (TypeError, ValueError):
                continue
    elif params.get("major") and params.get("plan_delta") is not None:
        try:
            adjustments.append(
                {
                    "major_name": str(params["major"]),
                    "plan_delta": int(params["plan_delta"]),
                }
            )
        except (TypeError, ValueError):
            pass

    if not adjustments and params.get("major"):
        major_name = str(params["major"])
        year_no, metric, forecast = await _expansion_decision_context(
            db,
            major_name=major_name,
            year=params.get("year"),
        )
        decision = build_expansion_decision(
            major_name=major_name,
            year_no=year_no,
            metric=metric,
            forecast=forecast,
        )
        return {
            "answer": decision["answer"],
            "charts": [],
            "table": {
                "columns": ["专业", "计划数", "录取数", "志愿次数", "志愿热度比", "决策"],
                "rows": [[
                    major_name,
                    decision["plan_count"],
                    decision["admitted_count"],
                    decision["choice_count"],
                    decision["demand_ratio"],
                    decision["decision"],
                ]],
            },
            "data_sources": [
                {"table": "fact.plan", "metric": "专业计划"},
                {"table": "fact.admission_record", "metric": "专业录取"},
                {"table": "fact.major_choice", "metric": "专业志愿热度"},
                {"table": "fact.plan", "metric": "下一年趋势预测"},
            ],
            "metrics": decision,
        }
    if not adjustments:
        return {
            "answer": "请明确要模拟的专业以及计划增减人数，例如：如果土木工程增加 20 个计划，录取和风险会怎样变化？",
            "charts": [],
            "table": None,
            "data_sources": [],
            "metrics": {"applied": 0},
        }

    simulation = await service.simulate_plan(
        db,
        year=params.get("year"),
        adjustments=adjustments,
    )
    results = simulation.get("results", [])
    baseline = simulation.get("baseline", {})
    projected = simulation.get("projected", {})
    unmatched = simulation.get("unmatched_adjustments", [])
    decision_note = ""
    decision_metrics: dict[str, Any] = {}
    if results:
        first_result = results[0]
        year_no, metric, forecast = await _expansion_decision_context(
            db,
            major_name=first_result["major_name"],
            year=params.get("year"),
        )
        decision = build_expansion_decision(
            major_name=first_result["major_name"],
            year_no=year_no,
            metric=metric,
            forecast=forecast,
            scenario=first_result,
        )
        decision_note = decision["answer"] + " "
        decision_metrics = decision

    if not results and unmatched:
        answer = f"未找到专业：{'、'.join(unmatched)}。请检查专业名称后重新模拟。"
    elif not results:
        answer = simulation.get("message", "当前没有可执行的计划调整。")
    else:
        detail = "；".join(
            (
                f"{item['major_name']}计划由 {item['baseline_plan']} 调整为 {item['projected_plan']}，"
                f"预计录取 {item['projected_admitted']} 人，完成率 {item['projected_completion_rate']}%，"
                f"风险等级 {item['risk_level']}"
            )
            for item in results
        )
        answer = (
            decision_note
            + f"模拟后总计划为 {projected.get('plan_count', 0)} 人，预计录取 "
            f"{projected.get('admitted_count', 0)} 人，整体完成率 "
            f"{projected.get('completion_rate', 0)}%。{detail}。"
            f"{simulation.get('disclaimer', '')}"
        )
        if unmatched:
            answer += f" 未匹配专业：{'、'.join(unmatched)}。"
    labels: list[str] = []
    values: list[int] = []
    for item in results:
        labels.extend([f"{item['major_name']}·基准", f"{item['major_name']}·模拟"])
        values.extend([item["baseline_plan"], item["projected_plan"]])
    return {
        "answer": answer,
        "charts": [bar_chart("招生计划模拟对比", labels, values)] if values else [],
        "table": {
            "columns": ["专业", "计划变化", "模拟计划", "模拟录取", "完成率", "分数变化", "风险"],
            "rows": [
                [
                    item["major_name"],
                    item["plan_delta"],
                    item["projected_plan"],
                    item["projected_admitted"],
                    item["projected_completion_rate"],
                    item["projected_score_change"],
                    item["risk_level"],
                ]
                for item in results
            ],
        }
        if results
        else None,
        "data_sources": simulation.get("data_sources", []),
        "metrics": {
            "baseline": baseline,
            "projected": projected,
            "applied_adjustments": len(results),
            "expansion_decision": decision_metrics,
        },
        "citations": [],
    }





