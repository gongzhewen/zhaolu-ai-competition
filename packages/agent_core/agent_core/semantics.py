from __future__ import annotations

import re
from typing import Any

from .contracts import RouteDecision, SemanticSlots, SlotAmbiguity
from .formal import estimate_semantic_uncertainty


_METRIC_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("completion_rate", ("计划完成率", "完成率", "完成情况", "计划完成")),
    ("enrollment_rate", ("报到率", "到校率", "到校比例", "报到比例")),
    ("enrolled_count", ("报到人数", "已报到", "到校人数", "未报到人数")),
    ("candidate_count", ("生源人数", "考生人数", "生源数量")),
    ("plan_count", ("招生计划", "计划数", "计划人数", "招生名额", "计划招生", "名额")),
    ("admitted_count", ("录取人数", "录取数", "实际录取", "录取多少")),
    ("student_count", ("学生人数", "有多少人", "多少人", "人数统计", "统计人数")),
    ("choice_count", ("志愿次数", "志愿热度", "报考热度", "专业热度", "志愿率")),
    ("subject_score", ("平均分", "最低分", "最高分", "成绩", "分数")),
    ("score_distribution", ("分数段", "一分一段", "成绩分段", "分数区间")),
    ("consultation_count", ("咨询人数", "咨询数量", "咨询量")),
    ("conversion_rate", ("转化率", "咨询转化")),
    ("anomaly_count", ("异常项", "异常专业", "风险专业")),
    ("medical_count", ("体检结论", "专业受限")),
    ("major_alias", ("专业别名", "标准专业", "名称映射", "专业改名")),
    ("student_profile", ("学生档案", "考生档案")),
)

_DEFINITION_MARKERS = ("怎么理解", "是什么意思", "含义", "怎么解释", "数据口径", "怎么计算", "如何计算")

_INTENT_METRICS: dict[str, tuple[str, ...]] = {
    "admissions_overview": ("plan_count", "admitted_count", "completion_rate"),
    "source_overview": ("candidate_count", "enrolled_count", "enrollment_rate"),
    "candidate_profile": ("student_count",),
    "subject_scores": ("subject_score",),
    "major_choices": ("choice_count",),
    "medical_summary": ("medical_count",),
    "forecast": ("plan_count", "admitted_count", "completion_rate"),
    "official_admission_stats": ("plan_count", "admitted_count", "student_count"),
    "major_alias_lookup": ("major_alias",),
    "student_lookup": ("student_profile",),
    "student_statistics": ("student_count",),
    "anomaly_detection": ("anomaly_count",),
    "plan_simulation": ("plan_count", "admitted_count", "completion_rate"),
    "consultation_overview": ("consultation_count", "conversion_rate"),
    "enrollment_funnel": ("plan_count", "admitted_count", "enrolled_count", "enrollment_rate"),
    "score_band_statistics": ("score_distribution", "subject_score"),
}

_INTENT_AGGREGATION: dict[str, str] = {
    "student_lookup": "detail",
    "student_statistics": "count",
    "score_band_statistics": "distribution",
    "subject_scores": "average_range",
    "major_choices": "rank",
    "anomaly_detection": "risk_scan",
    "plan_simulation": "scenario",
    "forecast": "forecast",
    "admissions_overview": "sum_ratio",
    "source_overview": "sum_ratio",
    "enrollment_funnel": "funnel",
    "consultation_overview": "sum_ratio",
}


def _explicit_metrics(message: str) -> tuple[str, ...]:
    compact = re.sub(r"\s+", "", message)
    metrics: list[str] = []
    for metric, patterns in _METRIC_PATTERNS:
        if any(pattern in compact for pattern in patterns):
            metrics.append(metric)
    if "招生多少人" in compact and not any(token in compact for token in ("计划", "录取")):
        metrics.extend(["plan_count", "admitted_count"])
    if "招生人数" in compact and "计划" not in compact:
        metrics.extend(["plan_count", "admitted_count"])
    return tuple(dict.fromkeys(metrics))


def compile_semantic_slots(
    message: str,
    decision: RouteDecision,
    *,
    context_values: dict[str, Any] | None = None,
) -> SemanticSlots:
    context_values = context_values or {}
    explicit_metrics = _explicit_metrics(message)
    fallback_metrics = _INTENT_METRICS.get(decision.intent, ())
    metrics = explicit_metrics or fallback_metrics
    missing: list[str] = []
    if decision.intent == "plan_simulation":
        if not decision.params.get("major"):
            missing.append("major")
        if decision.params.get("plan_delta") is None:
            missing.append("plan_delta")
    if decision.intent == "student_lookup":
        if not decision.params.get("student_name"):
            missing.append("student_name")
        if decision.params.get("year") is None:
            missing.append("year")
    filters = {
        key: value
        for key, value in decision.params.items()
        if key
        not in {
            "year",
            "province",
            "major",
            "query",
            "history",
            "can_lookup_students",
            "plan_delta",
        }
        and value is not None
    }
    output_mode = "detail"
    if decision.intent == "student_statistics":
        output_mode = "grouped" if decision.params.get("group_by") else "scalar"
    elif decision.intent in {"subject_scores", "major_choices", "anomaly_detection", "score_band_statistics"}:
        output_mode = "table"
    elif decision.intent in {"admissions_overview", "source_overview", "enrollment_funnel"}:
        output_mode = "summary"
    sources: list[str] = ["rule"]
    if context_values:
        sources.append("context")
    if any(str(reason).startswith("ml_intent=") for reason in decision.reasons):
        sources.append("onnx")
    return SemanticSlots(
        intent=decision.intent,
        metrics=metrics,
        year=decision.params.get("year"),
        province=decision.params.get("province"),
        major=decision.params.get("major"),
        subject=decision.params.get("exam_subject_name") or decision.params.get("subject_name"),
        filters=filters,
        aggregation=_INTENT_AGGREGATION.get(decision.intent),
        output_mode=output_mode,
        missing_required=tuple(missing),
        sources=tuple(dict.fromkeys(sources)),
    )


def estimate_slot_ambiguity(
    message: str,
    decision: RouteDecision,
    slots: SemanticSlots,
    *,
    entropy_enabled: bool = True,
) -> SlotAmbiguity:
    compact = re.sub(r"\s+", "", message)
    candidates: dict[str, tuple[Any, ...]] = {}
    reasons: list[str] = []
    score = 0.0
    clarification: str | None = None
    definition_question = any(marker in compact for marker in _DEFINITION_MARKERS)

    if decision.intent == "out_of_scope":
        return SlotAmbiguity(score=0.0)

    ambiguous_arrival = any(term in compact for term in ("到校比例", "报到比例")) or (
        any(term in compact for term in ("到校情况", "报到情况"))
        and not any(term in compact for term in ("生源", "渠道", "计划", "录取"))
    )
    if not definition_question and ambiguous_arrival:
        candidates["metric"] = ("报到率", "未报到率", "计划完成率")
        score = max(score, 0.78)
        reasons.append("到校或报到表述可能对应多个招生指标口径")
        clarification = "请明确要统计的是报到率、未报到率，还是招生计划完成率？"

    if "招生人数" in compact and "计划" not in compact:
        candidates["metric"] = ("plan_count", "admitted_count")
        score = max(score, 0.68)
        reasons.append("招生人数可能指计划人数或实际录取人数")
        clarification = "请明确要统计的是招生计划人数、实际录取人数，还是两者都需要？"

    if "招生规模" in compact:
        candidates["metric"] = ("plan_count", "admitted_count")
        score = max(score, 0.70)
        reasons.append("招生规模未明确采用计划口径还是录取口径")
        clarification = "请明确“招生规模”是指招生计划规模、实际录取规模，还是两者对比？"

    generic_major_question = any(
        term in compact
        for term in ("这个专业怎么样", "那个专业怎么样", "专业怎么样", "专业情况如何", "专业就业好不好")
    ) or ("就业" in compact and not decision.params.get("major"))
    if generic_major_question:
        candidates["major"] = ("需要指定标准专业名称",)
        score = max(score, 0.74)
        reasons.append("问题没有给出可执行的标准专业或招生指标")
        clarification = "请提供标准专业名称、招生年度和需要分析的指标，例如招生计划、录取人数或计划完成率。"

    typo_name = re.search(r"([\u4e00-\u9fff])性同学", compact)
    if typo_name:
        candidates["student_identity"] = (f"{typo_name.group(1)}姓学生", f"姓名中包含{typo_name.group(0)}")
        score = max(score, 0.82)
        reasons.append("姓氏或姓名写法存在歧义")
        clarification = f"请确认“{typo_name.group(0)}”是指{typo_name.group(1)}姓学生，还是姓名中包含“{typo_name.group(0)}”的学生？"

    placeholder_student = decision.intent == "student_lookup" and any(
        marker in compact
        for marker in ("同名", "某位", "某名", "某学生", "某同学", "这位学生", "那位学生")
    )
    if placeholder_student:
        candidates["student_identity"] = ("需要提供可唯一识别学生的姓名和年度",)
        score = max(score, 0.82)
        reasons.append("学生档案请求使用了无法唯一识别的占位姓名")
        clarification = "请提供学生完整姓名和招生年度；如果存在同名情况，还需要补充专业、省份或考生号等可核验条件。"

    missing = set(slots.missing_required)
    if missing:
        score = max(score, min(0.95, 0.55 + 0.1 * len(missing)))
        reasons.append(f"缺少必填槽位：{', '.join(sorted(missing))}")
        if "plan_delta" in missing:
            clarification = "请补充拟增加或减少的计划数，例如“土木工程增加 20 个计划”。"
        elif {"student_name", "year"} & missing:
            clarification = "请提供学生姓名和招生年度；学生个体档案仅授权管理员可查。"

    if decision.intent in {"admissions_overview", "forecast", "source_overview"} and slots.metrics and len(slots.metrics) >= 4:
        score = max(score, 0.5)
        reasons.append("问题同时涉及多个招生指标，口径需要约束")

    uncertainty = estimate_semantic_uncertainty(candidates) if entropy_enabled else None
    if uncertainty is not None:
        score = max(score, min(0.65, uncertainty.weighted_uncertainty * 0.5))
    return SlotAmbiguity(
        score=round(score, 4),
        candidates=candidates,
        reasons=reasons,
        clarification=clarification,
        slot_entropy=uncertainty.normalized_entropy if uncertainty is not None else {},
        semantic_uncertainty=uncertainty.weighted_uncertainty if uncertainty is not None else 0.0,
    )
