from __future__ import annotations

from typing import Any

from .contracts import EvidenceCertificate, PlanConsistency, RiskDecision, RiskFeatures, RouteDecision, SemanticSlots, SlotAmbiguity
from .formal import evaluate_answer_conditions
from .privacy import PrivacyAssessment
from .registry import DATA_INTENTS


_MESSAGES = {
    "clarify": "请补充必要的时间、范围或指标口径后重新提问。",
    "no_data": "未查询到符合条件的数据，请确认年度、范围或数据是否已导入。",
    "no_permission": "当前请求超出账号的数据访问权限，不能提供。",
    "out_of_scope": "该问题超出招生业务范围。",
    "insufficient_data": "数据支撑不足，为保证严谨性，暂不回答",
}


def _average_completeness(certificates: list[EvidenceCertificate]) -> float:
    if not certificates:
        return 0.0
    return sum(item.completeness for item in certificates) / len(certificates)


def build_risk_features(
    *,
    decision: RouteDecision,
    ambiguity: SlotAmbiguity,
    evidence: list[EvidenceCertificate],
    numeric_verification: dict[str, Any],
    plan_consistency: PlanConsistency,
    data_support: dict[str, Any],
    privacy: PrivacyAssessment,
    tool_results: list[dict[str, Any]],
    slots: SemanticSlots | None = None,
    enforce_evidence_gate: bool = True,
) -> RiskFeatures:
    evidence_score = _average_completeness(evidence)
    numeric_score = float(numeric_verification.get("coverage") or 0.0)
    has_metrics = any(bool(result.get("metrics")) for result in tool_results)
    required_slot_gap = 0.0
    if slots is not None and slots.missing_required:
        required_slot_gap = 1.0
    alias_risk = 0.0
    message = decision.normalized_message
    if decision.intent == "major_alias_lookup" or "别名" in message or "是什么专业" in message:
        has_alias_scope = bool(decision.params.get("source_name") or decision.params.get("major"))
        alias_risk = 0.2 if has_alias_scope else 0.8
    return RiskFeatures(
        ambiguity=max(ambiguity.score, required_slot_gap, alias_risk * 0.5),
        required_slot_gap=required_slot_gap,
        alias_risk=alias_risk,
        confidence_gap={"high": 0.0, "normal": 0.2, "medium": 0.35, "low": 0.8}.get(
            decision.confidence,
            0.5,
        ),
        evidence_gap=(1.0 - evidence_score) if enforce_evidence_gate else 0.0,
        numeric_gap=(1.0 - numeric_score) if enforce_evidence_gate else 0.0,
        plan_consistency_gap=(
            1.0 - plan_consistency.score
            if plan_consistency.triggered and not plan_consistency.consistent
            else 0.0
        ),
        permission_risk=0.0 if privacy.allowed else 1.0,
        privacy_risk=float(privacy.risk),
        missing_data_risk=1.0 if decision.intent in DATA_INTENTS and not has_metrics else 0.0,
        data_support_gap=1.0 - float(data_support.get("score") or 0.0),
    )


def decide_risk(
    *,
    decision: RouteDecision,
    ambiguity: SlotAmbiguity,
    evidence: list[EvidenceCertificate],
    numeric_verification: dict[str, Any],
    plan_consistency: PlanConsistency,
    data_support: dict[str, Any],
    privacy: PrivacyAssessment,
    tool_results: list[dict[str, Any]],
    threshold: float = 0.32,
    slots: SemanticSlots | None = None,
    enforce_evidence_gate: bool = True,
) -> RiskDecision:
    evidence_score = _average_completeness(evidence)
    numeric_score = float(numeric_verification.get("coverage") or 0.0)
    has_metrics = any(bool(result.get("metrics")) for result in tool_results)
    explicit_no_data = any(
        isinstance(result.get("metrics"), dict)
        and (
            result["metrics"].get("has_data") is False
            or result["metrics"].get("row_count") == 0
        )
        for result in tool_results
    )
    features = build_risk_features(
        decision=decision,
        ambiguity=ambiguity,
        evidence=evidence,
        numeric_verification=numeric_verification,
        plan_consistency=plan_consistency,
        data_support=data_support,
        privacy=privacy,
        tool_results=tool_results,
        slots=slots,
        enforce_evidence_gate=enforce_evidence_gate,
    )
    score = (
        0.24 * features.ambiguity
        + 0.22 * features.evidence_gap
        + 0.20 * features.numeric_gap
        + 0.12 * features.plan_consistency_gap
        + 0.08 * features.confidence_gap
        + 0.10 * features.data_support_gap
        + 0.04 * features.privacy_risk
    )
    if features.missing_data_risk:
        score = max(score, 0.82)
    score = round(max(0.0, min(1.0, score)), 4)
    reasons: list[str] = []
    reasons.extend(ambiguity.reasons)
    reasons.extend(plan_consistency.reasons)
    reasons.extend(privacy.reasons)
    if evidence_score < 0.6:
        reasons.append("证据证书不完整")
    if numeric_verification.get("unsupported_numbers"):
        reasons.append(
            "回答数字缺少证据：" + ", ".join(str(item) for item in numeric_verification["unsupported_numbers"])
        )
    if features.missing_data_risk:
        reasons.append("工具未返回可验证指标")
    if features.alias_risk >= 0.8:
        reasons.append("专业别名缺少可执行的来源专业或标准专业")
    if data_support.get("status") == "insufficient":
        reasons.extend(data_support.get("reasons") or ["数据支撑度不足"])

    conditions = evaluate_answer_conditions(
        constraints_complete=(
            not ambiguity.requires_clarification
            and not decision.clarification
            and features.required_slot_gap == 0.0
            and features.alias_risk < 0.8
        ),
        evidence_sufficient=(
            not enforce_evidence_gate
            or (
                evidence_score >= 0.6
                and numeric_score >= 1.0
                and not explicit_no_data
                and data_support.get("status") != "insufficient"
            )
        ),
        result_consistent=plan_consistency.consistent,
        permission_allowed=privacy.allowed,
        risk_below_threshold=score <= threshold,
    )

    strategy = "answer"
    response: str | None = None
    if not privacy.allowed:
        strategy = "no_permission"
        response = privacy.response or _MESSAGES["no_permission"]
    elif ambiguity.requires_clarification and decision.intent in DATA_INTENTS:
        strategy = "clarify"
        response = ambiguity.clarification or _MESSAGES["clarify"]
    elif decision.intent in DATA_INTENTS and not has_metrics:
        strategy = "insufficient_data"
        response = _MESSAGES["insufficient_data"]
    elif decision.intent in DATA_INTENTS and explicit_no_data:
        strategy = "no_data"
        response = _MESSAGES["no_data"]
    elif decision.intent in DATA_INTENTS and (
        (enforce_evidence_gate and (evidence_score < 0.6 or numeric_score < 1.0))
        or features.plan_consistency_gap > 0.0
        or (enforce_evidence_gate and data_support.get("status") == "insufficient")
        or score > threshold
    ):
        strategy = "insufficient_data"
        response = _MESSAGES["insufficient_data"]
    elif decision.intent == "policy_faq" and data_support.get("status") == "insufficient":
        strategy = "insufficient_data"
        response = "暂未检索到足够的政策依据，请补充具体年份、省份或问题范围。"
    elif score > threshold:
        strategy = "clarify"
        response = ambiguity.clarification or _MESSAGES["clarify"]

    return RiskDecision(
        score=score,
        strategy=strategy,  # type: ignore[arg-type]
        threshold=threshold,
        reasons=list(dict.fromkeys(reasons)),
        response=response,
        features=features,
        answer_conditions=conditions.as_dict(),
    )
