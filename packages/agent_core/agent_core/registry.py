from __future__ import annotations

from .contracts import ToolSpec

TOOL_CATALOG: tuple[ToolSpec, ...] = (
    ToolSpec(
        "admissions_overview",
        "查询招生计划、录取人数、计划完成率、专业和省份招生情况",
        ("year", "province", "major", "group_by"),
    ),
    ToolSpec("source_overview", "查询录取概况、省份和渠道分布"),
    ToolSpec("candidate_profile", "查询考生性别、地区、考试类型和科类结构"),
    ToolSpec("subject_scores", "查询各科平均分、最低分和最高分"),
    ToolSpec("major_choices", "查询专业志愿热度和志愿次数"),
    ToolSpec("medical_summary", "查询体检结论和专业受限汇总，不返回个人体检数据"),
    ToolSpec("forecast", "查询下一年招生计划、录取人数和计划完成率预测"),
    ToolSpec(
        "official_admission_stats",
        "查询官方统计的年度普通计划、普通录取、专升本和总招生人数",
        ("year",),
    ),
    ToolSpec(
        "major_alias_lookup",
        "查询不同省份专业名称、别名与标准专业之间的映射规则",
        ("source_name",),
    ),
    ToolSpec(
        "student_lookup",
        "按姓名和年度查询单个学生档案、录取、成绩、志愿和跟进状态，仅超级管理员可用",
        ("student_name", "year"),
    ),
    ToolSpec(
        "student_statistics",
        "按姓氏、姓名包含、性别、科类、专业、省份、报到状态等条件统计学生人数和分组分布",
        (
            "year",
            "surname",
            "name_contains",
            "gender_name",
            "subject_name",
            "province",
            "major",
            "is_enrolled",
            "group_by",
            "exam_subject_name",
            "exam_score_operator",
            "exam_score_value",
        ),
    ),
    ToolSpec(
        "anomaly_detection",
        "检测专业招生计划、录取完成率和志愿热度的异常波动与风险",
        ("year",),
    ),
    ToolSpec(
        "plan_simulation",
        "模拟某个专业招生计划增减后的录取人数、完成率和风险变化",
        ("year", "major", "plan_delta"),
    ),
    ToolSpec("policy_faq", "回答高考志愿、投档、退档、调剂、选科、体检、录取流程等政策规则问题", ("query",)),
    ToolSpec(
        "consultation_overview",
        "查询招生咨询渠道、咨询类型、咨询数量与转化率",
        ("year", "province"),
    ),
    ToolSpec(
        "enrollment_funnel",
        "查询招生计划、实际录取、已报到三个阶段的数量与流失率",
        ("year",),
    ),
    ToolSpec(
        "score_band_statistics",
        "查询指定科目的分数段人数分布和平均分",
        ("year", "subject_name"),
    ),
    ToolSpec(
        "admissions_statistics",
        "协调计划、录取、报到、成绩、位次和志愿数据，按受控指标与维度生成统计分析",
        (
            "year", "province", "major", "subject_name", "batch_name", "plan_type_code",
            "gender_name", "source_school_name", "group_by", "metric", "choice_order_min",
            "choice_order_max", "top_n",
        ),
    ),
)

TOOL_NAMES = tuple(spec.name for spec in TOOL_CATALOG)
TOOL_BY_NAME = {spec.name: spec for spec in TOOL_CATALOG}
SAFE_TOOLS = frozenset(spec.name for spec in TOOL_CATALOG if spec.name not in {"student_lookup", "student_statistics"})
DATA_INTENTS = frozenset(
    {
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
        "student_statistics",
        "anomaly_detection",
        "plan_simulation",
        "consultation_overview",
        "enrollment_funnel",
        "score_band_statistics",
        "admissions_statistics",
    }
)
DECISION_INTENTS = frozenset({"plan_simulation", "forecast_professional_analysis"})


def get_tool_spec(name: str) -> ToolSpec:
    try:
        return TOOL_BY_NAME[name]
    except KeyError as exc:
        raise ValueError(f"unknown tool: {name}") from exc


def validate_tool_call(name: str, params: dict) -> tuple[bool, str | None]:
    spec = TOOL_BY_NAME.get(name)
    if spec is None:
        return False, f"unknown tool: {name}"
    allowed = set(spec.params)
    if not allowed:
        return True, None
    unknown = set(params) - allowed
    if unknown:
        return False, f"unsupported params for {name}: {sorted(unknown)}"
    return True, None
