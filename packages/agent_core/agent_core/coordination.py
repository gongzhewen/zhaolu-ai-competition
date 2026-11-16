from __future__ import annotations

import re
from typing import Iterable

from .contracts import RouteDecision, ToolCall
from .registry import TOOL_BY_NAME


def _call(name: str, decision: RouteDecision, reason: str) -> ToolCall | None:
    if name not in TOOL_BY_NAME:
        return None
    params = {**decision.params, "query": decision.normalized_message}
    return ToolCall(name=name, params=params, reason=reason)


def _unique(calls: Iterable[ToolCall | None]) -> list[ToolCall]:
    result: list[ToolCall] = []
    seen: set[str] = set()
    for call in calls:
        if call is None or call.name in seen:
            continue
        seen.add(call.name)
        result.append(call)
    return result


def coordinate_tool_calls(message: str, decision: RouteDecision) -> list[ToolCall]:
    """Build a small deterministic plan for compound questions.

    This is intentionally rule-based: it only handles combinations whose
    domains can be identified without another model call. Multi-tool plans
    are preferred over a slow or unstable local planner for these shapes.
    """
    text = message.replace(" ", "")
    if decision.intent in {"refuse", "out_of_scope", "clarify", "memory_command"}:
        return []

    has_plan = any(token in text for token in ("招生计划", "计划数", "计划完成率", "招生人数"))
    has_admit = any(token in text for token in ("录取人数", "录取数", "录取情况", "录取"))
    has_enroll = any(token in text for token in ("报到人数", "报到数", "报到率", "未报到", "报到"))
    has_source = any(token in text for token in ("生源", "渠道"))
    has_profile = any(token in text for token in ("性别", "男女", "考生画像", "科类", "民族", "户籍"))
    has_score = any(token in text for token in ("成绩", "分数", "平均分", "中位分", "科目"))
    has_score_band = bool(any(token in text for token in ("分数段", "十分段", "分数区间")) or re.search(r"\d{2,3}\s*(?:到|至|-)\s*\d{2,3}\s*分", text))
    has_choice = any(token in text for token in ("志愿", "报考"))
    has_official = any(token in text for token in ("官方统计", "专升本"))
    has_forecast = "预测" in text or "明年" in text
    has_anomaly = any(token in text for token in ("异常", "风险", "计划缺口"))
    has_simulation = any(token in text for token in ("增加", "减少", "扩招", "缩招", "模拟")) and (
        "计划" in text or "名额" in text
    )
    has_policy = any(token in text for token in ("政策", "怎么理解", "是什么意思", "口径", "平行志愿", "投档规则", "招生章程", "调剂", "退档"))

    calls: list[ToolCall | None] = []

    # High-risk decision intents take precedence over generic metric combinations.
    if has_simulation:
        calls.append(_call("plan_simulation", decision, "规则协调：计划模拟"))
        if has_source:
            calls.append(_call("source_overview", decision, "规则协调：生源结构"))
        elif has_profile:
            calls.append(_call("candidate_profile", decision, "规则协调：考生画像"))
        return _unique(calls)
    if has_forecast and has_anomaly:
        return _unique([
            _call("anomaly_detection", decision, "规则协调：异常检测"),
            _call("forecast", decision, "规则协调：预测"),
        ])
    if has_forecast:
        calls.append(_call("forecast", decision, "规则协调：预测"))
        if has_source:
            calls.append(_call("source_overview", decision, "规则协调：生源结构"))
        return _unique(calls)
    if has_anomaly:
        calls.append(_call("anomaly_detection", decision, "规则协调：异常检测"))
        if has_source:
            calls.append(_call("source_overview", decision, "规则协调：生源结构"))
        return _unique(calls)

    # These metrics can be handled by the coordinated statistics tool in one call.
    if has_plan and has_admit and has_enroll:
        calls.append(_call("admissions_statistics", decision, "规则协调：计划、录取、报到组合指标"))
    elif has_plan and has_source:
        calls.extend([
            _call("admissions_overview", decision, "规则协调：招生计划"),
            _call("source_overview", decision, "规则协调：生源结构"),
        ])
    elif has_plan and has_profile:
        calls.extend([
            _call("admissions_overview", decision, "规则协调：招生计划"),
            _call("candidate_profile", decision, "规则协调：考生画像"),
        ])
    elif has_source and has_enroll:
        calls.extend([
            _call("source_overview", decision, "规则协调：生源与报到"),
            _call("admissions_overview", decision, "规则协调：招生趋势"),
        ])
    elif has_score and has_choice:
        calls.extend([
            _call("score_band_statistics" if has_score_band else "subject_scores", decision, "规则协调：成绩"),
            _call("admissions_statistics", decision, "规则协调：志愿"),
        ])
    elif has_policy and (has_plan or has_admit or has_enroll or has_choice):
        calls.extend([
            _call("policy_faq", decision, "规则协调：政策口径"),
            _call("admissions_statistics", decision, "规则协调：业务数据"),
        ])
    elif has_plan and has_admit:
        calls.append(_call("admissions_statistics", decision, "规则协调：计划与录取"))
    elif has_admit and has_enroll:
        calls.append(_call("admissions_statistics", decision, "规则协调：录取与报到"))
    elif has_official:
        calls.append(_call("official_admission_stats", decision, "规则协调：官方统计"))
    elif has_simulation:
        calls.append(_call("plan_simulation", decision, "规则协调：计划模拟"))
    elif has_forecast:
        calls.append(_call("forecast", decision, "规则协调：预测"))
    elif has_anomaly:
        calls.append(_call("anomaly_detection", decision, "规则协调：异常检测"))

    result = _unique(calls)
    return result if result else []




