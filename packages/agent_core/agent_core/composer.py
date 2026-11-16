from __future__ import annotations

from typing import Any

from .contracts import RouteDecision


INSUFFICIENT_DATA_ANSWER = "数据支撑不足，为保证严谨性，暂不回答"


def deterministic_answer(
    decision: RouteDecision,
    tool_results: list[dict[str, Any]],
    *,
    insufficient_data: bool = False,
) -> str:
    if insufficient_data:
        return INSUFFICIENT_DATA_ANSWER
    answers = [
        str(item.get("answer") or "").strip()
        for item in tool_results
        if str(item.get("answer") or "").strip()
    ]
    if answers:
        return "\n".join(dict.fromkeys(answers))
    if decision.intent == "policy_faq":
        return "暂未检索到足够的政策依据，请补充具体年份、省份或问题范围。"
    return "未查询到符合条件的数据，请补充年度、省份、专业或学生条件。"
