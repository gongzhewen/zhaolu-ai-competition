from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

ERROR_LABELS = {
    "user_reported": "用户指出的错误",
    "missing_evidence": "缺少工具证据",
    "possible_false_refusal": "可能存在误拒答",
    "condition_preservation": "年份或筛选条件可能丢失",
    "metric_omission": "用户要求的指标可能未完整覆盖",
    "numeric_mismatch": "数字或口径可能不一致",
    "intent_mismatch": "问题意图可能识别错误",
    "data_error": "数据结果可能有误",
    "answer_quality": "回答未满足用户预期",
}

ERROR_RULES = {
    "missing_evidence": "数据类结论必须绑定至少一个受控工具证据。",
    "possible_false_refusal": "拒绝前确认筛选条件下是否确实没有数据。",
    "condition_preservation": "复核年份、省份、专业和批次等条件是否保留。",
    "metric_omission": "答案必须覆盖用户明确要求的全部核心指标。",
    "numeric_mismatch": "回答数字必须与工具结果和统一口径一致。",
    "intent_mismatch": "先确认问题意图，再选择对应工具。",
    "data_error": "关键结论需要通过工具结果再次核对。",
    "answer_quality": "结论应直接回应问题，避免无关信息。",
}


def _clean_text(value: str | None, limit: int = 240) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    text = re.sub(r"(?i)ignore\s+(all\s+)?previous\s+instructions?", "", text)
    text = text.replace("忽略之前所有指令", "").replace("忽略先前指令", "")
    return text[:limit]


def infer_feedback_error_points(
    *,
    question: str,
    answer: str,
    reason: str | None,
    intent: str,
    tool_names: list[str],
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    clean_reason = _clean_text(reason)
    clean_answer = _clean_text(answer, 1000)
    tools = set(tool_names)

    def add(code: str, detail: str) -> None:
        if code not in {item["code"] for item in findings}:
            findings.append(
                {
                    "code": code,
                    "label": ERROR_LABELS.get(code, code),
                    "detail": _clean_text(detail),
                }
            )

    if clean_reason:
        add("user_reported", clean_reason)
        if re.search(r"年份|年度|20\d{2}", clean_reason):
            add("condition_preservation", "用户反馈涉及年份或时间条件")
        if re.search(r"专业|省份|地区|批次|筛选", clean_reason):
            add("condition_preservation", "用户反馈涉及筛选条件")
        if re.search(r"指标|口径|率|人数|数量|漏|少", clean_reason):
            add("metric_omission", "用户反馈涉及指标缺失或口径差异")
        if re.search(r"答非所问|意图|理解错", clean_reason):
            add("intent_mismatch", "用户反馈认为问题被理解错误")
        if re.search(r"数字|错误|不对|不一致", clean_reason):
            add("numeric_mismatch", "用户反馈认为数字或结论不正确")

    if not tools:
        add("missing_evidence", f"意图 {intent} 的此前回答没有受控工具调用")
    if "数据支撑不足" in clean_answer:
        add("possible_false_refusal", "此前回答以数据支撑不足结束")

    years = re.findall(r"20\d{2}", question)
    if years and not all(year in clean_answer for year in years):
        add("condition_preservation", "问题中的年份未全部出现在回答中")

    if any(marker in question for marker in ("分别", "同时", "以及", "、")) and len(
        re.findall(r"(?:率|数|人数|分数|位次)", question)
    ) >= 2:
        metric_terms = ("率", "数", "人数", "分数", "位次")
        if not all(term in clean_answer for term in metric_terms if term in question):
            add("metric_omission", "组合问题中的部分指标可能未覆盖")

    if not findings:
        add("answer_quality", "用户否定但未提供具体原因，需复核相关性、条件和证据")
    return findings[:5]


def build_reflection_summary(findings: list[dict[str, str]]) -> str:
    labels = [item["label"] for item in findings]
    return "可能问题：" + "、".join(labels)


def compress_reflection_memories(
    memories: list[dict[str, Any]],
) -> dict[str, Any]:
    code_counts: Counter[str] = Counter()
    for item in memories:
        value = item.get("memory_value") or {}
        if isinstance(value, str):
            continue
        for finding in value.get("error_points") or []:
            code = str(finding.get("code") or "")
            if code:
                code_counts[code] += 1
    ordered = [code for code, _count in code_counts.most_common(6)]
    rules = [ERROR_RULES[code] for code in ordered if code in ERROR_RULES]
    labels = [ERROR_LABELS.get(code, code) for code in ordered]
    summary = (
        f"历史反馈修正（{len(memories)} 条）：重点检查"
        + "、".join(labels[:4])
        + "。"
    )
    return {
        "summary": summary,
        "error_codes": ordered,
        "rules": rules,
        "source_count": len(memories),
    }


def compile_reflection_guidance(memories: list[dict[str, Any]]) -> dict[str, Any]:
    codes: Counter[str] = Counter()
    rules: list[str] = []
    summaries: list[str] = []
    confidence = 0.0
    for item in memories:
        memory_type = str(item.get("memory_type") or "")
        value = item.get("memory_value") or {}
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                value = {}
        if memory_type == "reflection_summary" and isinstance(value, dict):
            codes.update(str(code) for code in value.get("error_codes") or [])
            rules.extend(str(rule) for rule in value.get("rules") or [])
            summaries.append(str(item.get("summary") or ""))
            confidence = max(confidence, float(item.get("confidence") or 0.0))
        elif memory_type == "reflection" and isinstance(value, dict):
            for finding in value.get("error_points") or []:
                code = str(finding.get("code") or "")
                if code:
                    codes[code] += 1
            confidence = max(confidence, float(item.get("confidence") or 0.0))
    return {
        "active": bool(codes or rules),
        "error_codes": [code for code, _count in codes.most_common()],
        "rules": list(dict.fromkeys(rules))[:8],
        "summary": summaries[0] if summaries else None,
        "confidence": round(confidence, 4),
    }


def validate_answer_with_reflection_guidance(
    *,
    guidance: dict[str, Any],
    decision: Any,
    answer: str,
    tool_results: list[dict[str, Any]],
    evidence: list[Any],
    numeric_verification: dict[str, Any],
) -> dict[str, Any]:
    if not guidance.get("active"):
        return {"applied": False, "critical": False, "warnings": [], "rules": []}
    if getattr(decision, "intent", "") in {
        "policy_faq",
        "major_alias_lookup",
        "clarify",
        "memory_command",
    }:
        return {
            "applied": False,
            "critical": False,
            "warnings": [],
            "rules": list(guidance.get("rules") or []),
        }

    warnings: list[str] = []
    codes = set(guidance.get("error_codes") or [])
    if "missing_evidence" in codes and not tool_results:
        warnings.append("历史反馈要求数据结论必须包含工具证据")
    if "condition_preservation" in codes:
        params = decision.params
        filters = {
            key: value
            for item in evidence
            for key, value in (getattr(item, "filters", {}) or {}).items()
        }
        for key in ("year", "province", "major"):
            if params.get(key) is not None and filters.get(key) != params.get(key):
                warnings.append(f"历史反馈要求复核条件 {key} 是否被正确应用")
    if "metric_omission" in codes and tool_results and not numeric_verification.get(
        "answer_number_count"
    ):
        warnings.append("历史反馈要求回答覆盖可核验指标")
    if "numeric_mismatch" in codes and not numeric_verification.get("supported", True):
        warnings.append("历史反馈要求复核数字与工具结果一致性")
    if "possible_false_refusal" in codes and "数据支撑不足" in answer:
        warnings.append("历史反馈曾出现疑似误拒答，本次需确认是否存在可用数据")

    critical = bool(guidance.get("confidence", 0.0) >= 0.8 and warnings)
    return {
        "applied": True,
        "critical": critical,
        "warnings": list(dict.fromkeys(warnings)),
        "rules": list(guidance.get("rules") or []),
    }


def select_reflection_answer(
    *,
    original_answer: str,
    second_result: dict[str, Any],
) -> dict[str, Any]:
    risk = second_result.get("risk_decision") or {}
    support = second_result.get("data_support") or {}
    numeric = second_result.get("numeric_verification") or {}
    second_answer = str(second_result.get("answer") or "").strip()
    answered = risk.get("strategy") == "answer"
    supported = support.get("status") == "sufficient"
    numeric_supported = numeric.get("supported", True)

    if second_answer and answered and supported and numeric_supported:
        normalized_original = re.sub(r"\s+", "", original_answer)
        normalized_second = re.sub(r"\s+", "", second_answer)
        return {
            "mode": "maintained" if normalized_original == normalized_second else "refined",
            "answer": second_answer,
            "reason": (
                "二次复核维持原结论"
                if normalized_original == normalized_second
                else "二次复核重新执行受控工具并形成新结论"
            ),
        }
    return {
        "mode": "insufficient",
        "answer": "二次复核后仍缺少可替代原回答的充分证据，建议人工核对相关条件和指标口径。",
        "reason": "二次复核未同时满足工具证据、数据支撑和数字一致性要求",
    }
