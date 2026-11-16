from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from .registry import DATA_INTENTS, DECISION_INTENTS


def _numbers(value: Any) -> set[Decimal]:
    text_value = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
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
    evidence_completeness: float | None = None,
    numeric_verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del question
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

    if numeric_verification is not None:
        numeric_consistency = float(numeric_verification.get("coverage") or 0.0)
        unsupported = numeric_verification.get("unsupported_numbers") or []
        if unsupported:
            issues.append("回答中存在工具结果未覆盖的年份或数据数字")
    else:
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
    dimensions["numeric_consistency"] = max(0.0, numeric_consistency)

    if evidence_completeness is not None:
        dimensions["evidence_completeness"] = max(0.0, min(1.0, evidence_completeness))
        if evidence_completeness < 0.6:
            issues.append("数字证据证书不完整")

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
    answer_number_count = (
        int(numeric_verification.get("answer_number_count") or 0)
        if numeric_verification is not None
        else len(_numbers(answer))
    )
    return {
        "score": round(score, 4),
        "loss": round(1.0 - score, 4),
        "action": action,
        "dimensions": dimensions,
        "issues": issues,
        "answer_number_count": answer_number_count,
    }


def assess_data_support(
    *,
    result: dict[str, Any],
    self_check: dict[str, Any],
    canonical_intent: str,
    knowledge_items: list[dict[str, Any]] | None = None,
    threshold: float = 0.65,
    evidence_completeness: float | None = None,
    numeric_coverage: float | None = None,
) -> dict[str, Any]:
    knowledge_items = knowledge_items or []
    confidence_score = {
        "high": 1.0,
        "medium": 0.75,
        "normal": 0.75,
        "low": 0.4,
    }.get(str(result.get("confidence") or "low").lower(), 0.5)
    self_check_score = float(self_check.get("score") or 0.0)
    base_score = 0.7 * self_check_score + 0.3 * confidence_score

    tool_results = result.get("tool_results") or []
    data_sources = result.get("data_sources") or []
    citations = result.get("citations") or []
    caps: list[float] = []
    reasons: list[str] = []

    if canonical_intent in DATA_INTENTS:
        if str(result.get("confidence") or "low").lower() == "low":
            caps.append(0.60)
            reasons.append("模型置信度低")
        if not tool_results:
            caps.append(0.35)
            reasons.append("未调用确定性数据工具")
        if not data_sources:
            caps.append(0.55)
            reasons.append("缺少可追溯数据来源")
        if tool_results and not any(item.get("metrics") for item in tool_results):
            caps.append(0.60)
            reasons.append("工具未返回可验证指标")
        if evidence_completeness is not None and evidence_completeness < 0.6:
            caps.append(0.55)
            reasons.append("数字证据证书不完整")
        if numeric_coverage is not None and numeric_coverage < 1.0:
            caps.append(0.50)
            reasons.append("回答数字未被工具证据完全覆盖")
    if canonical_intent == "policy_faq" and not citations and not knowledge_items:
        caps.append(0.50)
        reasons.append("政策结论缺少依据")

    score = min([base_score, *caps]) if caps else base_score
    score = round(max(0.0, min(1.0, score)), 4)
    return {
        "score": score,
        "threshold": threshold,
        "status": "sufficient" if score >= threshold else "insufficient",
        "confidence_score": confidence_score,
        "self_check_score": self_check_score,
        "reasons": reasons,
    }
