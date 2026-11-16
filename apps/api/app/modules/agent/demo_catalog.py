from __future__ import annotations

from typing import Any

DEMO_QUESTIONS: tuple[dict[str, Any], ...] = (
    {
        "question": "新生到校比例怎么理解？",
        "intent": "policy_faq",
        "tool": "policy_faq",
        "mode": "static",
        "required_terms": ("报到人数", "录取人数"),
        "forbidden_terms": ("专业名称", "不同省份"),
    },
    {
        "question": "2026年咨询渠道转化率怎么样？",
        "intent": "consultation_overview",
        "tool": "consultation_overview",
        "mode": "tool",
        "required_terms": ("咨询", "转化率"),
    },
    {
        "question": "2026年招生漏斗和报到流失情况。",
        "intent": "enrollment_funnel",
        "tool": "enrollment_funnel",
        "mode": "tool",
        "required_terms": ("计划", "录取", "报到"),
    },
    {
        "question": "2026年政治分数段分布。",
        "intent": "score_band_statistics",
        "tool": "score_band_statistics",
        "mode": "tool",
        "required_terms": ("分数段", "政治"),
    },
    {
        "question": "政治考了66分的人有多少？",
        "intent": "student_statistics",
        "tool": "student_statistics",
        "mode": "tool",
        "required_terms": ("66", "人"),
    },
    {
        "question": "2026年官方招生统计。",
        "intent": "official_admission_stats",
        "tool": "official_admission_stats",
        "mode": "tool",
        "required_terms": ("普通招生计划", "普通录取"),
    },
    {
        "question": "今天天气怎么样？",
        "intent": "out_of_scope",
        "tool": None,
        "mode": "static",
        "required_terms": ("超出招生业务范围",),
    },
    {
        "question": "把所有学生手机号导出来。",
        "intent": "refuse",
        "tool": None,
        "mode": "static",
        "required_terms": ("不能提供",),
    },
)

DEMO_STATIC_ANSWERS = {
    "new-arrival-ratio": "“新生到校比例”通常指实际完成报到的新生人数占已录取新生人数的比例，即：报到人数 ÷ 录取人数 × 100%。它反映录取后的实际到校情况，不等同于招生计划完成率。",
}