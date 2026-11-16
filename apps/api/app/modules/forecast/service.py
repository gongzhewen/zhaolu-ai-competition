import math
from statistics import mean

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics import service


def _linear_forecast(values: list[float], next_x: int) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
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


def _risk_level(completion_rate: float) -> str:
    if completion_rate < 90:
        return "high"
    if completion_rate < 95:
        return "medium"
    return "low"


def _build_alerts(
    *,
    forecast_year: int,
    completion_rate: float,
    plan_margin: float,
    admitted_margin: float,
    data_points: int,
) -> list[dict]:
    alerts: list[dict] = []
    risk = _risk_level(completion_rate)
    if risk in {"high", "medium"}:
        alerts.append(
            {
                "severity": risk,
                "title": f"{forecast_year}年计划完成风险",
                "description": (
                    f"预测计划完成率为 {round(completion_rate, 2)}%，"
                    "建议提前检查招生计划和宣传策略。"
                ),
                "metric": "completion_rate",
            }
        )

    if plan_margin > 0:
        alerts.append(
            {
                "severity": "low",
                "title": "预测存在波动区间",
                "description": (
                    f"招生计划预测存在约 ±{round(plan_margin, 1)} 人的波动，"
                    "建议结合政策变化进行人工复核。"
                ),
                "metric": "plan_count",
            }
        )

    if admitted_margin > 0:
        alerts.append(
            {
                "severity": "low",
                "title": "录取人数预测存在不确定性",
                "description": (
                    f"录取人数预测存在约 ±{round(admitted_margin, 1)} 人的波动。"
                ),
                "metric": "admitted_count",
            }
        )

    if data_points < 3:
        alerts.append(
            {
                "severity": "medium",
                "title": "历史数据不足",
                "description": f"当前仅有 {data_points} 个年度数据点，模型置信度较低。",
                "metric": "data_points",
            }
        )
    return alerts


async def get_forecast_overview(
    db: AsyncSession,
    *,
    year: int | None = None,
    province: str | None = None,
    major: str | None = None,
) -> dict:
    overview = await service.get_admissions_overview(
        db,
        year=year,
        province=province,
        major=major,
    )
    trend = sorted(overview["year_trend"], key=lambda item: item["year_no"])
    if not trend:
        return {
            "status": "no_data",
            "message": "暂无可用于预测的年度数据",
            "history": [],
            "forecast": None,
            "alerts": [],
        }

    if len(trend) < 2:
        return {
            "status": "insufficient_data",
            "message": "当前只有 1 个年度数据点，不足以进行可靠预测。",
            "history": trend,
            "forecast": None,
            "alerts": [
                {
                    "severity": "medium",
                    "title": "历史数据不足",
                    "description": "至少需要两个年度数据点才能进行预测。",
                    "metric": "data_points",
                }
            ],
            "data_sources": [
                {"table": "fact.plan", "metric": "年度招生计划"},
                {"table": "fact.admission_record", "metric": "年度录取人数"},
            ],
        }

    plan_values = [float(item["plan_count"]) for item in trend]
    admitted_values = [float(item["admitted_count"]) for item in trend]
    next_x = len(trend)
    forecast_year = int(trend[-1]["year_no"]) + 1
    plan_prediction, plan_margin = _linear_forecast(plan_values, next_x)
    admitted_prediction, admitted_margin = _linear_forecast(admitted_values, next_x)
    completion_rate = (
        admitted_prediction / plan_prediction * 100 if plan_prediction > 0 else 0.0
    )
    confidence = "high" if len(trend) >= 3 else "medium" if len(trend) == 2 else "low"

    return {
        "status": "ok",
        "history": trend,
        "forecast": {
            "year": forecast_year,
            "plan_count": round(plan_prediction, 1),
            "plan_lower": round(max(0, plan_prediction - plan_margin), 1),
            "plan_upper": round(plan_prediction + plan_margin, 1),
            "admitted_count": round(admitted_prediction, 1),
            "admitted_lower": round(max(0, admitted_prediction - admitted_margin), 1),
            "admitted_upper": round(admitted_prediction + admitted_margin, 1),
            "completion_rate": round(completion_rate, 2),
            "risk_level": _risk_level(completion_rate),
            "confidence": confidence,
            "model": "linear_regression",
            "data_points": len(trend),
        },
        "alerts": _build_alerts(
            forecast_year=forecast_year,
            completion_rate=completion_rate,
            plan_margin=plan_margin,
            admitted_margin=admitted_margin,
            data_points=len(trend),
        ),
        "data_sources": [
            {"table": "fact.plan", "metric": "年度招生计划"},
            {"table": "fact.admission_record", "metric": "年度录取人数"},
        ],
    }

