from __future__ import annotations

from statistics import mean
from typing import Any


def as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def completion_rate(plan_count: int | float, admitted_count: int | float) -> float:
    plan = float(plan_count or 0)
    admitted = float(admitted_count or 0)
    return round(admitted / plan * 100, 2) if plan else 0.0


def source_coverage_rate(detail_count: int | float, official_count: int | float) -> float:
    official = float(official_count or 0)
    detail = float(detail_count or 0)
    return round(detail / official * 100, 2) if official else 0.0


def linear_forecast(values: list[float], next_x: int | None = None) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    if next_x is None:
        next_x = len(values)
    if len(values) == 1:
        value = values[0]
        return value, max(value * 0.1, 1.0)

    x_values = list(range(len(values)))
    x_mean = mean(x_values)
    y_mean = mean(values)
    denominator = sum((x - x_mean) ** 2 for x in x_values)
    slope = (
        sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, values)) / denominator
        if denominator
        else 0.0
    )
    intercept = y_mean - slope * x_mean
    prediction = intercept + slope * next_x
    residuals = [y - (intercept + slope * x) for x, y in zip(x_values, values)]
    residual_margin = max((abs(item) for item in residuals), default=0.0) * 1.5
    scale_margin = abs(prediction) * 0.05
    margin = max(residual_margin, scale_margin, 1.0)
    return max(0.0, prediction), margin


def risk_level(completion: float) -> str:
    if completion < 90:
        return "high"
    if completion < 95:
        return "medium"
    return "low"


def simulate_plan_change(
    *,
    major_name: str,
    plan_count: int,
    admitted_count: int,
    choice_count: int,
    plan_delta: int,
) -> dict[str, Any]:
    new_plan = max(0, plan_count + plan_delta)
    demand_factor = min(1.2, max(0.5, (choice_count / plan_count / 3) if plan_count else 0.5))
    projected_admitted = (
        min(new_plan, max(0, round(admitted_count + plan_delta * demand_factor)))
        if new_plan
        else 0
    )
    projected_completion = round(projected_admitted / new_plan * 100, 2) if new_plan else 0
    projected_score_change = round(-plan_delta * 0.08, 2)
    level = risk_level(projected_completion)
    if choice_count >= plan_count * 3 and new_plan <= plan_count:
        level = "high" if level == "low" else level
    return {
        "major_name": major_name,
        "plan_delta": plan_delta,
        "baseline_plan": plan_count,
        "baseline_admitted": admitted_count,
        "baseline_completion_rate": completion_rate(plan_count, admitted_count),
        "projected_plan": new_plan,
        "projected_admitted": projected_admitted,
        "projected_completion_rate": projected_completion,
        "projected_score_change": projected_score_change,
        "risk_level": level,
        "choice_count": choice_count,
    }


def _format_decision_number(value: Any, digits: int = 2) -> str:
    number = as_float(value)
    if number is None:
        return "暂无"
    return f"{number:.{digits}f}".rstrip("0").rstrip(".")


def build_expansion_decision(
    *,
    major_name: str,
    year_no: int | None,
    metric: dict[str, Any] | None,
    forecast: dict[str, Any] | None,
    scenario: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plan_count = int((metric or {}).get("plan_count") or 0)
    admitted_count = int((metric or {}).get("admitted_count") or 0)
    choice_count = int((metric or {}).get("choice_count") or 0)
    demand_ratio = choice_count / plan_count if plan_count else 0.0
    forecast_completion = as_float((forecast or {}).get("completion_rate"))
    forecast_risk = str((forecast or {}).get("risk_level") or "unknown")
    projected_completion = as_float((scenario or {}).get("projected_completion_rate"))
    score_change = as_float((scenario or {}).get("projected_score_change"))

    blockers: list[str] = []
    cautions: list[str] = []
    supports: list[str] = []

    if demand_ratio >= 1.2:
        supports.append(f"志愿热度比为 {demand_ratio:.2f}，专业需求明显高于现有计划")
    elif demand_ratio < 0.8:
        blockers.append(f"志愿热度比仅 {demand_ratio:.2f}，现有计划的志愿支撑不足")
    elif demand_ratio < 1.0:
        cautions.append(f"志愿热度比为 {demand_ratio:.2f}，需求仅接近现有计划")

    if forecast_completion is not None:
        if forecast_risk == "high" or forecast_completion < 90:
            blockers.append(f"下一年完成率预测为 {forecast_completion:.2f}%，存在较高完成风险")
        elif forecast_risk == "medium" or forecast_completion < 95:
            cautions.append(f"下一年完成率预测为 {forecast_completion:.2f}%，需要保留安全余量")
        else:
            supports.append(f"下一年完成率预测为 {forecast_completion:.2f}%，总体可控")

    if scenario:
        if projected_completion is not None:
            if projected_completion < 90:
                blockers.append(f"模拟完成率降至 {projected_completion:.2f}%，扩招后缺口风险较高")
            elif projected_completion < 95:
                cautions.append(f"模拟完成率降至 {projected_completion:.2f}%，安全余量偏低")
        if score_change is not None and score_change < -3:
            cautions.append(f"模拟分数变化为 {score_change:+.2f} 分，新增计划可能明显拉低录取竞争度")

    if blockers:
        decision = "不建议直接扩招"
        decision_level = "不建议"
    elif cautions:
        decision = "可以小幅审慎扩招"
        decision_level = "审慎"
    else:
        decision = "具备扩招条件，建议分步实施"
        decision_level = "支持"

    if plan_count:
        if decision_level == "支持":
            recommended_min = max(5, round(plan_count * 0.05))
            recommended_max = max(recommended_min, round(plan_count * 0.10))
        elif decision_level == "审慎":
            recommended_min = max(3, round(plan_count * 0.02))
            recommended_max = max(recommended_min, round(plan_count * 0.05))
        else:
            recommended_min = 0
            recommended_max = max(3, round(plan_count * 0.02))
    else:
        recommended_min = recommended_max = 0

    reasons = blockers or cautions or supports
    if not reasons:
        reasons = ["当前缺少足够的计划、志愿或预测数据，无法形成可靠结论"]
        decision = "暂不建议扩招"
        decision_level = "数据不足"

    answer_parts = [
        f"明确结论：{decision}。",
        f"判断对象：{year_no or '最新年度'}年{major_name}专业，"
        f"计划 {plan_count} 人、录取 {admitted_count} 人、志愿次数 {choice_count} 次，"
        f"志愿热度比 {demand_ratio:.2f}。",
        "主要依据：" + "；".join(reasons) + "。",
    ]
    if scenario:
        answer_parts.append(
            f"模拟结果：计划调整为 {scenario.get('projected_plan')} 人，"
            f"预计录取 {scenario.get('projected_admitted')} 人，"
            f"完成率 {_format_decision_number(scenario.get('projected_completion_rate'))}%，"
            f"分数变化 {_format_decision_number(scenario.get('projected_score_change'))} 分，"
            f"风险等级 {scenario.get('risk_level')}。"
        )
    if decision_level == "不建议":
        answer_parts.append(
            f"执行建议：不建议按当前幅度扩招；如确有政策或培养任务，建议增量暂控制在 {recommended_min}-{recommended_max} 人，"
            "并先补充生源宣传、优化专业分流和设置分阶段评估指标。"
        )
    elif decision_level == "审慎":
        answer_parts.append(
            f"执行建议：可考虑分步扩招 {recommended_min}-{recommended_max} 人，按月或分批次监测志愿热度、报到率和培养容量，"
            "达到阈值后再决定是否追加。"
        )
    elif decision_level == "支持":
        answer_parts.append(
            f"执行建议：可考虑扩招 {recommended_min}-{recommended_max} 人，优先保障师资、宿舍、实验条件和就业服务，"
            "同时持续监测完成率和最低位次。"
        )
    else:
        answer_parts.append("执行建议：先补充连续年度计划和志愿数据后再决策，不建议仅凭单一指标扩招。")

    return {
        "decision": decision,
        "decision_level": decision_level,
        "recommended_min": recommended_min,
        "recommended_max": recommended_max,
        "demand_ratio": round(demand_ratio, 2),
        "plan_count": plan_count,
        "admitted_count": admitted_count,
        "choice_count": choice_count,
        "forecast_completion_rate": forecast_completion,
        "forecast_risk_level": forecast_risk,
        "answer": " ".join(answer_parts),
    }
