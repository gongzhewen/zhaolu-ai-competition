from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

DATA_INTENTS = {
    "admissions_overview",
    "source_overview",
    "candidate_profile",
    "subject_scores",
    "major_choices",
    "medical_summary",
    "forecast",
    "official_admission_stats",
    "major_alias_lookup",
    "student_lookup",
    "anomaly_detection",
    "plan_simulation",
    "forecast_professional_analysis",
}
DECISION_INTENTS = {"plan_simulation", "forecast_professional_analysis"}


def _numbers(value: Any) -> set[Decimal]:
    text_value = json.dumps(value, ensure_ascii=False, default=str) if not isinstance(value, str) else value
    numbers: set[Decimal] = set()
    for token in re.findall(r"-?\d+(?:\.\d+)?", text_value):
        try:
            numbers.add(Decimal(token).normalize())
        except InvalidOperation:
            continue
    return numbers


def evaluate_answer(
    *,
    question: str,
    intent: str,
    answer: str,
    tool_calls: list[dict[str, Any]],
    tool_results: list[dict[str, Any]],
    knowledge_results: list[dict[str, Any]] | None = None,
    citations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    knowledge_results = knowledge_results or []
    citations = citations or []
    issues: list[str] = []
    dimensions: dict[str, float] = {}

    grounding = 1.0
    if intent in DATA_INTENTS:
        if not tool_calls:
            grounding = 0.0
            issues.append("数据类问题未调用确定性工具")
        elif not tool_results or not any(str(item.get("answer") or "").strip() for item in tool_results):
            grounding = 0.2
            issues.append("工具未返回有效结果")
    dimensions["data_grounding"] = grounding

    numeric_consistency = 1.0
    answer_numbers = _numbers(answer)
    allowed_numbers = _numbers(tool_results)
    formatting_numbers = {Decimal(value) for value in range(1, 6)}
    unsupported = {
        number
        for number in answer_numbers
        if number not in allowed_numbers and number not in formatting_numbers
    }
    if unsupported:
        numeric_consistency = max(0.0, 1.0 - 0.2 * len(unsupported))
        issues.append("回答中存在工具结果未覆盖的年份或数据数字")
    dimensions["numeric_consistency"] = numeric_consistency

    completeness = 1.0
    if intent in DECISION_INTENTS:
        required_markers = ("结论", "建议")
        missing = [marker for marker in required_markers if marker not in answer]
        if missing:
            completeness -= 0.4
            issues.append("决策回答缺少明确结论或执行建议")
        if "2026" in answer and not any(term in answer for term in ("计划", "录取", "完成率", "风险")):
            completeness -= 0.2
            issues.append("决策回答缺少关键数据依据")
    elif not answer.strip():
        completeness = 0.0
        issues.append("回答为空")
    dimensions["task_completeness"] = max(0.0, completeness)

    safety = 1.0
    if re.search(r"(?<!\d)1[3-9]\d{9}(?!\d)", answer) or re.search(r"\b\d{17}[\dXx]\b", answer):
        safety = 0.0
        issues.append("回答疑似包含手机号或身份证号")
    dimensions["safety"] = safety

    citation_quality = 1.0
    if intent == "policy_faq" and not citations and not knowledge_results:
        citation_quality = 0.4
        issues.append("政策回答缺少知识库来源")
    dimensions["citation_quality"] = citation_quality

    score = sum(dimensions.values()) / len(dimensions)
    if score >= 0.8:
        action = "accepted"
    elif score >= 0.6:
        action = "revised"
    else:
        action = "fallback_required"
    return {
        "score": round(score, 4),
        "loss": round(1.0 - score, 4),
        "action": action,
        "dimensions": dimensions,
        "issues": issues,
        "answer_number_count": len(answer_numbers),
    }
