import asyncio
import copy
import json
import re
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.db_compat import execute_returning_id
from app.core.permissions import is_super_admin
from app.core.redis_cache import shared_get_json, shared_set_json
from app.core.runtime_metrics import record_chat_metric
from app.core.text import text
from app.models.dimension import Major, Province
from app.models.system import User
from app.modules.agent.tools.diagnostics import (
    consultation_overview,
    enrollment_funnel,
    score_band_statistics,
)
from app.modules.agent_intelligence.memory import (
    load_relevant_memories,
    remember_turn,
)
from app.modules.agent_intelligence.optimizer import (
    record_response_evaluation,
    select_prompt_template,
    task_type_for_intent,
)
from app.modules.agent_intelligence.school_context import resolve_school_context
from app.modules.agent_intelligence.self_check import DATA_INTENTS, evaluate_answer
from app.modules.ai_gateway.faq import search_faq
from app.modules.ai_gateway.language_normalizer import normalize_colloquial
from app.modules.ai_gateway.minimind_router import minimind_router
from app.modules.analytics import service
from app.modules.forecast import service as forecast_service
from app.modules.rag.service import search_knowledge
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

TOOL_DEFINITIONS = {
    "admissions_overview": {
        "description": "查询招生计划、录取人数、计划完成率、专业和省份招生情况",
        "params": ["year", "province", "major", "group_by"],
    },
    "source_overview": {
        "description": "查询录取概况、省份和渠道分布",
        "params": [],
    },
    "candidate_profile": {
        "description": "查询考生性别、地区、考试类型和科类结构",
        "params": [],
    },
    "subject_scores": {
        "description": "查询各科平均分、最低分和最高分",
        "params": [],
    },
    "major_choices": {
        "description": "查询专业志愿热度和志愿次数",
        "params": [],
    },
    "medical_summary": {
        "description": "查询体检结论和专业受限汇总，不返回个人体检数据",
        "params": [],
    },
    "forecast": {
        "description": "查询下一年招生计划、录取人数和计划完成率预测",
        "params": [],
    },
    "official_admission_stats": {
        "description": "查询官方统计的年度普通计划、普通录取、专升本和总招生人数",
        "params": ["year"],
    },
    "major_alias_lookup": {
        "description": "查询不同省份专业名称、别名与标准专业之间的映射规则",
        "params": ["source_name"],
    },
    "student_lookup": {
        "description": "按姓名和年度查询单个学生档案、录取、成绩、志愿和跟进状态，仅超级管理员可用",
        "params": ["student_name", "year"],
    },
    "student_statistics": {
        "description": "按姓氏、姓名包含、性别、科类、专业、省份、报到状态等条件统计学生人数和分组分布，只返回聚合结果",
        "params": [
            "year", "surname", "name_contains", "gender_name", "subject_name",
            "province", "major", "is_enrolled", "group_by", "exam_subject_name",
            "exam_score_operator", "exam_score_value",
        ],
    },
    "anomaly_detection": {
        "description": "检测专业招生计划、录取完成率和志愿热度的异常波动与风险",
        "params": ["year"],
    },
    "plan_simulation": {
        "description": "模拟某个专业招生计划增减后的录取人数、完成率和风险变化",
        "params": ["year", "major", "plan_delta"],
    },
    "policy_faq": {
        "description": "回答高考志愿、投档、退档、调剂、选科、体检、录取流程等政策规则问题",
        "params": ["query"],
    },
    "consultation_overview": {
        "description": "查询招生咨询渠道、咨询类型、咨询数量与转化率",
        "params": ["year", "province"],
    },
    "enrollment_funnel": {
        "description": "查询招生计划、实际录取、已报到三个阶段的数量与流失率",
        "params": ["year"],
    },
    "score_band_statistics": {
        "description": "查询指定科目的分数段人数分布和平均分",
        "params": ["year", "subject_name"],
    },
}


def _extract_year(message: str, context: dict[str, Any]) -> int | None:
    if context.get("year"):
        return int(context["year"])
    matches = re.findall(r"(20\d{2})", message)
    if len(matches) >= 2 and any(keyword in message for keyword in ("到", "至", "趋势", "历年", "近三年")):
        return None
    if matches:
        return int(matches[0])
    current_year = datetime.now().year
    if any(keyword in message for keyword in ("今年", "本年", "当前年度")):
        return current_year
    if any(keyword in message for keyword in ("去年", "上一年")):
        return current_year - 1
    if "前年" in message:
        return current_year - 2
    return None


def _uses_all_year_scope(message: str) -> bool:
    return any(
        keyword in message
        for keyword in ("历年", "逐年", "每年", "趋势", "近三年", "三年", "各年度", "全部年度", "年度对比", "明年", "下一年", "预测")
    )


def _is_multi_year_question(message: str) -> bool:
    year_matches = re.findall(r"(20\d{2})", message)
    return any(keyword in message for keyword in ("历年", "逐年", "每年", "趋势", "近三年", "三年", "各年度", "全部年度", "年度对比")) or (
        len(year_matches) >= 2 and any(keyword in message for keyword in ("到", "至"))
    )


def _clean_student_name(value: str) -> str | None:
    cleaned = re.sub(r"[\s“”\"'‘’《》【】\[\]（）()]+", "", value)
    if not re.fullmatch(r"[\u4e00-\u9fff·]{2,10}", cleaned):
        return None
    if cleaned in {"学生", "考生", "同学", "姓名", "情况", "录取", "成绩", "志愿"}:
        return None
    if any(keyword in cleaned for keyword in ("多少", "人数", "是多少", "招生", "计划")):
        return None
    return cleaned


def _extract_student_name(message: str, context: dict[str, Any]) -> str | None:
    if context.get("student_name"):
        return _clean_student_name(str(context["student_name"])) or None
    patterns = (
        r"(?:名为|名叫|姓名为|姓名叫)\s*[“”\"'‘’]?([\u4e00-\u9fff·]{2,10}?)[“”\"'‘’]?(?=\s*(?:的|学生|同学|考生|录取|情况|成绩|志愿|[，,、。]|$))",
        r"姓名\s*[:：]?\s*(?:是|为|叫)?\s*[“”\"'‘’]?([\u4e00-\u9fff·]{2,10}?)[“”\"'‘’]?(?=\s*(?:的|学生|同学|考生|录取|情况|成绩|志愿|[，,、。]|$))",
        r"(?:录取|考入|考上|招收)\s*的?\s*[“”\"'‘’]?([\u4e00-\u9fff·]{2,10}?)[“”\"'‘’]?(?=\s*(?:同学|学生|考生|的|情况|录取|成绩|志愿|[，,、。]|$))",
        r"(?:学生|考生|同学)\s*[“”\"'’]?([\u4e00-\u9fff·]{2,10}?)[“”\"'’]?(?=\s*(?:的|情况|录取|成绩|志愿))",
        r"[“”\"'‘’]([\u4e00-\u9fff·]{2,10}?)[“”\"'‘’](?=\s*(?:同学|学生|考生|的|录取|情况|成绩|志愿|[，,、。]|$))",
    )
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            candidate = _clean_student_name(match.group(1))
            if candidate and not candidate.startswith("姓"):
                return candidate
    return None


def _extract_plan_delta(message: str, context: dict[str, Any]) -> int | None:
    if context.get("plan_delta") is not None:
        try:
            return int(context["plan_delta"])
        except (TypeError, ValueError):
            return None
    patterns = (
        r"(?:增加|上调|扩招|新增)(\d+)(?:个)?(?:招生计划|计划|名额)",
        r"(?:减少|下调|缩减|削减)(\d+)(?:个)?(?:招生计划|计划|名额)",
        r"(?:增加|上调|扩招|新增)(?:招生计划|计划|名额)?\s*(\d+)",
        r"(?:减少|下调|缩减|削减)(?:招生计划|计划|名额)?\s*(\d+)",
        r"(?:招生计划|计划|名额)\s*(?:增加|上调|扩招|新增)\s*(\d+)",
        r"(?:招生计划|计划|名额)\s*(?:减少|下调|缩减|削减)\s*(\d+)",
    )
    for pattern in patterns:
        match = re.search(pattern, message)
        if not match:
            continue
        value = int(match.group(1))
        if any(keyword in match.group(0) for keyword in ("减少", "下调", "缩减", "削减")):
            return -value
        return value
    return None


def _extract_surname(message: str, context: dict[str, Any]) -> str | None:
    if context.get("surname"):
        return str(context["surname"]).strip() or None
    match = re.search(r"姓([\u4e00-\u9fff]{1,2}?)(?:的)?(?:学生|考生|同学)", message)
    if match:
        return match.group(1).removesuffix("的")
    match = re.search(r"([\u4e00-\u9fff]{1,2})姓(?:学生|考生|同学)", message)
    return match.group(1).removesuffix("的") if match else None


def _extract_name_contains(message: str, context: dict[str, Any]) -> str | None:
    if context.get("name_contains"):
        return str(context["name_contains"]).strip() or None
    match = re.search(r"(?:姓名|名字)(?:包含|含|中有)([\u4e00-\u9fff]{1,4})", message)
    return match.group(1) if match else None


def _extract_gender_name(message: str, context: dict[str, Any]) -> str | None:
    if context.get("gender_name"):
        return str(context["gender_name"]).strip() or None
    if any(keyword in message for keyword in ("男生", "男性", "男学生")):
        return "男"
    if any(keyword in message for keyword in ("女生", "女性", "女学生")):
        return "女"
    return None


def _extract_subject_name(message: str) -> str | None:
    for name in ("物理类", "历史类", "理科", "文科", "艺术类", "体育类", "专升本"):
        if name in message:
            return name
    return None


def _extract_exam_score_condition(
    message: str,
    context: dict[str, Any],
) -> dict[str, Any] | None:
    subject = str(context.get("exam_subject_name") or "").strip()
    value = context.get("exam_score_value")
    operator = str(context.get("exam_score_operator") or "=").strip()
    if subject and value is not None:
        try:
            return {
                "exam_subject_name": "外语" if subject == "英语" else subject,
                "exam_score_operator": operator,
                "exam_score_value": Decimal(str(value)),
            }
        except InvalidOperation:
            return None

    subjects = "语文|数学|外语|英语|物理|化学|生物|政治|历史|地理|技术|综合"
    comparison_match = re.search(
        rf"({subjects}).*?(不低于|至少|大于等于|>=|≥|超过|高于|大于|不超过|至多|小于等于|<=|≤|低于|少于|小于)\s*(\d+(?:\.\d+)?)\s*分?",
        message,
    )
    operator_map = {
        "不低于": ">=",
        "至少": ">=",
        "大于等于": ">=",
        ">=": ">=",
        "≥": ">=",
        "超过": ">",
        "高于": ">",
        "大于": ">",
        "不超过": "<=",
        "至多": "<=",
        "小于等于": "<=",
        "<=": "<=",
        "≤": "<=",
        "低于": "<",
        "少于": "<",
        "小于": "<",
    }
    if comparison_match:
        subject_value = "外语" if comparison_match.group(1) == "英语" else comparison_match.group(1)
        return {
            "exam_subject_name": subject_value,
            "exam_score_operator": operator_map.get(comparison_match.group(2), "="),
            "exam_score_value": Decimal(comparison_match.group(3)),
        }

    exact_match = re.search(
        rf"({subjects})(?:考了|考得|考|得了|得|是|为|成绩为|分数为|达到)?\s*(\d+(?:\.\d+)?)\s*分",
        message,
    )
    if exact_match is None:
        return None
    subject_value = "外语" if exact_match.group(1) == "英语" else exact_match.group(1)
    return {
        "exam_subject_name": subject_value,
        "exam_score_operator": "=",
        "exam_score_value": Decimal(exact_match.group(2)),
    }


def _extract_student_status(message: str) -> str | None:
    mapping = {"新学生": "NEW", "已联系": "CONTACTED", "有意向": "INTERESTED", "已录取": "ADMITTED", "已报到": "ENROLLED", "已放弃": "ABANDONED"}
    for label, code in mapping.items():
        if label in message:
            return code
    return None


def _extract_enrollment_filter(message: str) -> bool | None:
    if any(keyword in message for keyword in ("未报到", "没有报到", "尚未报到")):
        return False
    if "已报到" in message:
        return True
    return None


def _extract_group_by(message: str) -> str | None:
    mapping = {"按专业": "major_name", "各专业": "major_name", "按省份": "province_name", "各省": "province_name", "按性别": "gender_name", "按科类": "subject_name", "按状态": "student_status", "按渠道": "channel_name"}
    for label, field in mapping.items():
        if label in message:
            return field
    return None


async def _extract_province(
    db: AsyncSession,
    message: str,
    context: dict[str, Any],
) -> str | None:
    if context.get("province"):
        return str(context["province"])
    result = await db.execute(select(Province.province_name))
    for name in result.scalars().all():
        if name == "专升本":
            continue
        if name in message:
            return name
    return None


async def _extract_major(
    db: AsyncSession,
    message: str,
    context: dict[str, Any],
) -> str | None:
    if context.get("major"):
        return str(context["major"])
    result = await db.execute(select(Major.major_name))
    for name in result.scalars().all():
        if name == "专升本":
            continue
        if name in message:
            return name
    return None


def _classify(message: str) -> str:
    message = normalize_colloquial(message)
    if re.match(r"^(?:请)?记住[：:，,\s]?", message) or re.match(r"^以后(?:都|默认|优先)?", message):
        return "memory_command"
    if _extract_plan_delta(message, {}) is not None and any(
        keyword in message for keyword in ("计划", "名额", "多招", "少招", "增加", "减少", "扩招", "缩招", "模拟", "风险")
    ):
        return "plan_simulation"
    policy_keywords = (
        "平行志愿", "投档", "退档", "滑档", "调剂", "院校专业组", "招生章程",
        "招生简章", "征集志愿", "强基计划", "综合评价", "专项计划", "提前批",
        "冲稳保", "选科要求", "大类招生", "转专业", "体检受限", "专业级差",
        "投档比例", "录取结果", "分数线", "位次", "填报资料", "录取后不去",
    )
    if any(keyword in message for keyword in policy_keywords):
        return "policy_faq"
    if (
        _extract_surname(message, {})
        or _extract_name_contains(message, {})
    ) and any(keyword in message for keyword in ("多少", "人数", "统计", "分布", "学生", "考生", "录取")):
        return "student_statistics"
    if any(keyword in message for keyword in ("男生", "女生", "男性", "女性", "男学生", "女学生")) and any(
        keyword in message for keyword in ("多少", "人数", "统计", "录取", "学生", "考生")
    ):
        return "student_statistics"
    if any(keyword in message for keyword in ("按专业", "按省份", "按性别", "按科类", "各专业", "各省")) and any(
        keyword in message for keyword in ("多少", "人数", "统计", "学生", "考生", "录取", "报到")
    ):
        return "student_statistics"
    if any(keyword in message for keyword in ("多少名学生", "多少考生", "学生人数", "考生人数", "人数统计")) and any(
        keyword in message for keyword in ("专业", "省份", "性别", "科类", "报到", "录取")
    ):
        return "student_statistics"
    if _extract_exam_score_condition(message, {}) and any(
        keyword in message for keyword in ("多少", "人数", "几人", "几个", "学生", "考生", "人")
    ):
        return "student_statistics"
    if _extract_student_name(message, {}) and any(
        keyword in message for keyword in ("学生", "录取", "情况", "成绩", "志愿", "分析")
    ):
        return "student_lookup"
    if any(
        keyword in message
        for keyword in ("专业别名", "名称不同", "名称修正", "标准专业", "改名", "专业名称")
    ):
        return "major_alias_lookup"
    if any(
        keyword in message
        for keyword in ("专升本", "普通计划", "总招生", "招生总人数", "官方统计", "数据口径", "人数对比")
    ):
        return "official_admission_stats"
    plan_change_patterns = (
        r"(?:增加|上调|扩招|新增|减少|下调|缩减|削减)\s*\d*\s*个?\s*(?:招生计划|计划|名额)",
        r"(?:招生计划|计划|名额)\s*(?:增加|上调|扩招|新增|减少|下调|缩减|削减)\s*\d*",
    )
    if any(
        keyword in message
        for keyword in (
            "沙盘", "模拟", "假如", "增加计划", "减少计划", "调整计划", "扩招",
            "缩招", "上调计划", "下调计划", "名额增减",
        )
    ) or any(re.search(pattern, message) for pattern in plan_change_patterns):
        return "plan_simulation"
    if any(
        keyword in message
        for keyword in ("异常", "波动异常", "风险", "不正常", "预警", "偏离", "计划缺口")
    ):
        return "anomaly_detection"
    if any(keyword in message for keyword in ("预测", "明年", "下一年", "未来")):
        return "forecast"
    if any(keyword in message for keyword in ("体检", "专业受限", "健康")):
        return "medical_summary"
    if any(keyword in message for keyword in ("志愿", "报考热度", "专业热度")):
        return "major_choices"
    if any(
        keyword in message
        for keyword in (
            "成绩",
            "科目",
            "平均分",
            "语文",
            "数学",
            "外语",
            "物理",
            "化学",
            "生物",
            "政治",
            "历史",
            "地理",
        )
    ):
        return "subject_scores"
    if any(
        keyword in message
        for keyword in ("性别", "男女", "考生构成", "民族", "户籍", "地区分布", "考生画像")
    ):
        return "candidate_profile"
    if any(keyword in message for keyword in ("生源", "报到", "渠道")):
        return "source_overview"
    if any(keyword in message for keyword in ("专业", "热门专业", "专业录取")):
        return "admissions_overview"
    if any(keyword in message for keyword in ("省份", "各省", "分省", "省际", "地区", "生源地分布")):
        return "admissions_overview"
    if any(keyword in message for keyword in ("计划", "录取", "招生", "完成率")):
        return "admissions_overview"
    return "admissions_overview"


def _synthetic_note(params: dict[str, Any], tool_names: set[str] | None = None) -> str:
    return ""


def _trend_chart(
    title: str,
    categories: list[str],
    plan_values: list[int | float],
    admitted_values: list[int | float],
) -> dict[str, Any]:
    return {
        "title": {"text": title},
        "tooltip": {"trigger": "axis"},
        "legend": {"data": ["招生计划", "实际录取"]},
        "xAxis": {"type": "category", "data": categories},
        "yAxis": {"type": "value"},
        "series": [
            {"name": "招生计划", "type": "line", "data": plan_values, "smooth": True},
            {"name": "实际录取", "type": "line", "data": admitted_values, "smooth": True},
        ],
    }


def _bar_chart(title: str, categories: list[str], values: list[int | float]) -> dict[str, Any]:
    return {
        "title": {"text": title},
        "tooltip": {"trigger": "axis"},
        "xAxis": {"type": "category", "data": categories},
        "yAxis": {"type": "value"},
        "series": [{"type": "bar", "data": values}],
    }


def _pie_chart(title: str, data: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "title": {"text": title},
        "tooltip": {"trigger": "item"},
        "series": [{"type": "pie", "radius": ["35%", "68%"], "data": data}],
    }


async def _tool_admissions_overview(
    db: AsyncSession,
    params: dict[str, Any],
) -> dict[str, Any]:
    overview = await service.get_admissions_overview(
        db,
        year=params.get("year"),
        province=params.get("province"),
        major=params.get("major"),
    )
    metrics = overview["metrics"]
    query = str(params.get("query") or "")
    trend = sorted(overview.get("year_trend", []), key=lambda item: item["year_no"])
    if _is_multi_year_question(query) and len(trend) > 1:
        details = "；".join(
            (
                f"{item['year_no']} 年计划 {item['plan_count']} 人、"
                f"录取 {item['admitted_count']} 人、完成率 {item['completion_rate']}%"
            )
            for item in trend
        )
        scope = f"{params['major']}专业" if params.get("major") else "招生"
        return {
            "answer": f"{scope}跨年度趋势为：{details}。",
            "charts": [
                _trend_chart(
                    "招生计划与录取趋势",
                    [str(item["year_no"]) for item in trend],
                    [item["plan_count"] for item in trend],
                    [item["admitted_count"] for item in trend],
                )
            ],
            "table": {
                "columns": ["年度", "计划数", "录取数", "完成率"],
                "rows": [
                    [item["year_no"], item["plan_count"], item["admitted_count"], item["completion_rate"]]
                    for item in trend
                ],
            },
            "data_sources": [
                {"table": "fact.plan", "metric": "年度招生计划"},
                {"table": "fact.admission_summary", "metric": "年度录取汇总"},
            ],
            "metrics": {"data_points": len(trend), "start_year": trend[0]["year_no"], "end_year": trend[-1]["year_no"]},
        }
    answer = (
        f"当前招生计划 {metrics['plan_count']} 人，实际录取 {metrics['admitted_count']} 人，"
        f"计划完成率 {metrics['completion_rate']}%。"
    )
    if metrics.get("min_score") is not None:
        answer += f" 最低录取分 {metrics['min_score']}。"
    if not params.get("major") and overview["by_major"]:
        top = overview["by_major"][0]
        answer += (
            f" 计划规模最大的专业是{top['major_name']}，计划 {top['plan_count']} 人，"
            f"完成率 {top['completion_rate']}%。"
        )
    chart = _bar_chart(
        "专业招生计划",
        [row["major_name"] for row in overview["by_major"][:20]],
        [row["plan_count"] for row in overview["by_major"][:20]],
    )
    table = {
        "columns": ["专业", "计划数", "录取数", "完成率", "最低分"],
        "rows": [
            [
                row["major_name"],
                row["plan_count"],
                row["admitted_count"],
                row["completion_rate"],
                row["min_score"],
            ]
            for row in overview["by_major"][:30]
        ],
    }
    return {
        "answer": answer,
        "charts": [chart],
        "table": table,
        "data_sources": [
            {"table": "fact.plan", "metric": "招生计划"},
            {"table": "fact.admission_summary", "metric": "录取汇总"},
        ],
        "metrics": metrics,
    }


async def _tool_source_overview(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    overview = await service.get_source_overview(db, year=params.get("year"))
    metrics = overview["metrics"]
    answer = (
        f"当前生源 {metrics['candidate_count']} 人，报到 {metrics['enrolled_count']} 人，"
        f"报到率 {metrics['enrollment_rate']}%。"
    )
    chart = _pie_chart(
        "渠道生源分布",
        [{"name": row["channel_name"], "value": row["candidate_count"]} for row in overview["by_channel"]],
    )
    table = {
        "columns": ["渠道", "生源人数", "报到人数", "平均分"],
        "rows": [
            [row["channel_name"], row["candidate_count"], row["enrolled_count"], row["avg_score"]]
            for row in overview["by_channel"]
        ],
    }
    return {
        "answer": answer,
        "charts": [chart],
        "table": table,
        "data_sources": [{"table": "fact.admission_record", "metric": "生源与报到"}],
        "metrics": metrics,
    }


async def _tool_candidate_profile(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    overview = await service.get_candidate_profile_overview(
        db,
        year=params.get("year"),
        province=params.get("province"),
        major=params.get("major"),
    )
    metrics = overview["metrics"]
    scope = f"{params['major']}专业录取考生" if params.get("major") else "当前考生画像"
    answer = f"{scope}覆盖 {metrics['candidate_count']} 名考生。"
    if overview["by_gender"]:
        answer += " 性别分布为：" + "，".join(
            f"{row['name']} {row['count']} 人" for row in overview["by_gender"]
        ) + "。"
    if overview["by_subject"]:
        answer += " 科类分布为：" + "，".join(
            f"{row['name']} {row['count']} 人" for row in overview["by_subject"]
        ) + "。"
    chart = _pie_chart(
        "考生性别分布",
        [{"name": row["name"], "value": row["count"]} for row in overview["by_gender"]],
    )
    table = {
        "columns": ["地区", "人数"],
        "rows": [[row["name"], row["count"]] for row in overview["by_region"][:20]],
    }
    return {
        "answer": answer,
        "charts": [chart],
        "table": table,
        "data_sources": [{"table": "fact.candidate_profile", "metric": "考生画像"}],
        "metrics": metrics,
    }


async def _tool_subject_scores(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    overview = await service.get_subject_score_overview(
        db,
        year=params.get("year"),
        province=params.get("province"),
        major=params.get("major"),
    )
    subjects = overview["subjects"]
    record_count = sum(int(row["record_count"] or 0) for row in subjects)
    scope = f"{params['major']}专业录取考生的" if params.get("major") else "当前"
    answer = f"{scope}学科成绩共有 {record_count} 条记录。"
    if subjects:
        high = max(subjects, key=lambda row: float(row["avg_score"] or 0))
        low = min(subjects, key=lambda row: float(row["avg_score"] or 0))
        answer += (
            f" 平均分最高的是{high['subject_name']}，平均 {high['avg_score']} 分；"
            f"平均分最低的是{low['subject_name']}，平均 {low['avg_score']} 分。"
        )
    chart = _bar_chart(
        "各科平均分",
        [row["subject_name"] for row in subjects],
        [float(row["avg_score"] or 0) for row in subjects],
    )
    table = {
        "columns": ["科目", "记录数", "平均分", "最低分", "最高分"],
        "rows": [
            [row["subject_name"], row["record_count"], row["avg_score"], row["min_score"], row["max_score"]]
            for row in subjects
        ],
    }
    return {
        "answer": answer,
        "charts": [chart],
        "table": table,
        "data_sources": [{"table": "fact.exam_subject_score", "metric": "学科成绩"}],
        "metrics": {"record_count": record_count},
    }


async def _tool_major_choices(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    overview = await service.get_major_choice_overview(
        db,
        year=params.get("year"),
        major=params.get("major"),
    )
    metrics = overview["metrics"]
    top = overview["majors"][0] if overview["majors"] else None
    if params.get("major"):
        answer = (
            f"在专业志愿数据中，{params['major']}共出现 {metrics['choice_count']} 次，"
            f"涉及 {metrics['candidate_count']} 名考生。"
        )
    else:
        answer = (
            f"当前共有 {metrics['choice_count']} 条专业志愿，覆盖 {metrics['candidate_count']} 名考生。"
        )
        if top:
            answer += (
                f" 热度最高的专业是{top['major_name']}，共出现 {top['choice_count']} 次，"
                f"涉及 {top['candidate_count']} 名考生。"
            )
    chart = _bar_chart(
        "专业志愿热度",
        [row["major_name"] for row in overview["majors"][:20]],
        [row["choice_count"] for row in overview["majors"][:20]],
    )
    table = {
        "columns": ["专业", "志愿次数", "涉及考生"],
        "rows": [
            [row["major_name"], row["choice_count"], row["candidate_count"]]
            for row in overview["majors"][:30]
        ],
    }
    return {
        "answer": answer,
        "charts": [chart],
        "table": table,
        "data_sources": [{"table": "fact.major_choice", "metric": "专业志愿"}],
        "metrics": metrics,
    }


async def _tool_medical_summary(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    overview = await service.get_medical_overview(
        db,
        year=params.get("year"),
        province=params.get("province"),
        major=params.get("major"),
    )
    total = sum(int(row["count"] or 0) for row in overview["medical_results"])
    scope = f"{params['major']}专业录取考生的" if params.get("major") else "当前"
    answer = scope + "体检结论汇总为：" + "，".join(
        f"{row['result_name']} {row['count']} 人" for row in overview["medical_results"]
    ) + "。 不展示个人体检测量信息。"
    chart = _pie_chart(
        "体检结论分布",
        [{"name": row["result_name"], "value": row["count"]} for row in overview["medical_results"]],
    )
    table = {
        "columns": ["体检结论", "人数"],
        "rows": [[row["result_name"], row["count"]] for row in overview["medical_results"]],
    }
    return {
        "answer": answer,
        "charts": [chart],
        "table": table,
        "data_sources": [{"table": "fact.medical_summary", "metric": "体检结论摘要"}],
        "metrics": {"candidate_count": total},
    }


async def _tool_policy_faq(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    query = str(params.get("query") or params.get("message") or "").strip()
    item = search_faq(query)
    knowledge_items = await search_knowledge(
        db,
        query=query,
        school_id=params.get("school_id"),
        limit=4,
    )
    citations = list(item.sources) if item else []
    if item is None and knowledge_items:
        return {
            "answer": "\n\n".join(str(row.get("content") or "") for row in knowledge_items[:3]),
            "charts": [],
            "table": None,
            "data_sources": [{"table": "ai.knowledge_chunk", "metric": "招生知识库"}],
            "metrics": {"matched": len(knowledge_items)},
            "citations": citations,
        }
    if item is None:
        return {
            "answer": "当前政策知识库中没有找到对应依据，建议咨询省考试院或学校招生办。",
            "charts": [],
            "table": None,
            "data_sources": [{"table": "policy_faq", "metric": "高招政策常见问答"}],
            "metrics": {"matched": 0},
            "citations": [],
        }
    return {
        "answer": f"{item.question}\n{item.answer}",
        "charts": [],
        "table": None,
        "data_sources": [{"table": "policy_faq", "metric": "高招政策常见问答"}],
        "metrics": {"matched": 1, "knowledge_matches": len(knowledge_items)},
        "citations": citations,
    }


async def _tool_forecast(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    overview = await forecast_service.get_forecast_overview(
        db,
        year=params.get("year"),
        province=params.get("province"),
        major=params.get("major"),
    )
    forecast = overview.get("forecast")
    if not forecast:
        return {
            "answer": "当前缺少足够的年份数据，暂时无法完成预测。",
            "charts": [],
            "table": None,
            "data_sources": [{"table": "fact.plan", "metric": "预测输入"}],
            "metrics": {"data_points": 0},
        }
    answer = (
        f"预测 {forecast['year']} 年招生计划 {forecast['plan_count']} 人，"
        f"录取人数 {forecast['admitted_count']} 人，计划完成率 {forecast['completion_rate']}%，"
        f"风险等级为 {forecast['risk_level']}。"
    )
    return {
        "answer": answer,
        "charts": [],
        "table": None,
        "data_sources": [{"table": "fact.plan", "metric": "趋势预测"}],
        "metrics": forecast,
    }


async def _tool_anomaly_detection(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    overview = await service.get_anomalies(db, year=params.get("year"))
    items = overview.get("items", [])
    summary = overview.get("summary", {})
    year_no = overview.get("year_no")
    if not year_no:
        answer = overview.get("message", "暂无可用于异常检测的数据。")
    elif not items:
        answer = f"{year_no} 年未检测到达到规则阈值的专业异常。"
    else:
        leading = "；".join(
            f"{item['major_name']}：{item['message']}，建议{item['suggestion']}"
            for item in items[:5]
        )
        answer = (
            f"{year_no} 年共检测到 {summary.get('total_anomalies', 0)} 项专业异常，"
            f"其中高风险 {summary.get('high', 0)} 项、中风险 {summary.get('medium', 0)} 项。"
            f"重点异常：{leading}。"
        )
    chart = _bar_chart(
        "专业异常热度",
        [item["major_name"] for item in items[:20]],
        [item["demand_ratio"] for item in items[:20]],
    )
    table = {
        "columns": ["专业", "等级", "异常原因", "完成率", "志愿热度比", "建议"],
        "rows": [
            [
                item["major_name"],
                item["severity"],
                item["message"],
                item["completion_rate"],
                item["demand_ratio"],
                item["suggestion"],
            ]
            for item in items[:30]
        ],
    }
    return {
        "answer": answer,
        "charts": [chart] if items else [],
        "table": table if items else None,
        "data_sources": overview.get("data_sources", []),
        "metrics": {"year_no": year_no, **summary},
    }


def _format_decision_number(value: Any, digits: int = 2) -> str:
    number = _as_float(value)
    if number is None:
        return "暂无"
    return f"{number:.{digits}f}".rstrip("0").rstrip(".")


def _build_expansion_decision(
    *,
    major_name: str,
    year_no: int | None,
    metric: dict[str, Any] | None,
    forecast: dict[str, Any] | None,
    scenario: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plan_count = int((metric or {}).get("plan_count") or 0)
    admitted_count = int((metric or {}).get("admitted_count") or 0)
    choice_count = int((metric or {}).get("choice_count") or 0)
    demand_ratio = choice_count / plan_count if plan_count else 0.0
    forecast_completion = _as_float((forecast or {}).get("completion_rate"))
    forecast_risk = str((forecast or {}).get("risk_level") or "unknown")
    projected_completion = _as_float((scenario or {}).get("projected_completion_rate"))
    score_change = _as_float((scenario or {}).get("projected_score_change"))

    blockers: list[str] = []
    cautions: list[str] = []
    supports: list[str] = []

    if demand_ratio >= 1.2:
        supports.append(f"志愿热度比为 {demand_ratio:.2f}，专业需求明显高于现有计划")
    elif demand_ratio < 0.8:
        blockers.append(f"志愿热度比仅 {demand_ratio:.2f}，现有计划的志愿支撑不足")
    elif demand_ratio < 1.0:
        cautions.append(f"志愿热度比为 {demand_ratio:.2f}，需求仅接近现有计划")

    if forecast_completion is not None:
        if forecast_risk == "high" or forecast_completion < 90:
            blockers.append(f"下一年完成率预测为 {forecast_completion:.2f}%，存在较高完成风险")
        elif forecast_risk == "medium" or forecast_completion < 95:
            cautions.append(f"下一年完成率预测为 {forecast_completion:.2f}%，需要保留安全余量")
        else:
            supports.append(f"下一年完成率预测为 {forecast_completion:.2f}%，总体可控")

    if scenario:
        if projected_completion is not None:
            if projected_completion < 90:
                blockers.append(f"模拟完成率降至 {projected_completion:.2f}%，扩招后缺口风险较高")
            elif projected_completion < 95:
                cautions.append(f"模拟完成率降至 {projected_completion:.2f}%，安全余量偏低")
        if score_change is not None and score_change < -3:
            cautions.append(f"模拟分数变化为 {score_change:+.2f} 分，新增计划可能明显拉低录取竞争度")

    if blockers:
        decision = "不建议直接扩招"
        decision_level = "不建议"
    elif cautions:
        decision = "可以小幅审慎扩招"
        decision_level = "审慎"
    else:
        decision = "具备扩招条件，建议分步实施"
        decision_level = "支持"

    if plan_count:
        if decision_level == "支持":
            recommended_min = max(5, round(plan_count * 0.05))
            recommended_max = max(recommended_min, round(plan_count * 0.10))
        elif decision_level == "审慎":
            recommended_min = max(3, round(plan_count * 0.02))
            recommended_max = max(recommended_min, round(plan_count * 0.05))
        else:
            recommended_min = 0
            recommended_max = max(3, round(plan_count * 0.02))
    else:
        recommended_min = recommended_max = 0

    reasons = blockers or cautions or supports
    if not reasons:
        reasons = ["当前缺少足够的计划、志愿或预测数据，无法形成可靠结论"]
        decision = "暂不建议扩招"
        decision_level = "数据不足"

    answer_parts = [
        f"明确结论：{decision}。",
        f"判断对象：{year_no or '最新年度'}年{major_name}专业，"
        f"计划 {plan_count} 人、录取 {admitted_count} 人、志愿次数 {choice_count} 次，"
        f"志愿热度比 {demand_ratio:.2f}。",
        "主要依据：" + "；".join(reasons) + "。",
    ]
    if scenario:
        answer_parts.append(
            f"模拟结果：计划调整为 {scenario.get('projected_plan')} 人，"
            f"预计录取 {scenario.get('projected_admitted')} 人，"
            f"完成率 {_format_decision_number(scenario.get('projected_completion_rate'))}%，"
            f"分数变化 {_format_decision_number(scenario.get('projected_score_change'))} 分，"
            f"风险等级 {scenario.get('risk_level')}。"
        )
    if decision_level == "不建议":
        answer_parts.append(
            f"执行建议：不建议按当前幅度扩招；如确有政策或培养任务，建议增量暂控制在 {recommended_min}-{recommended_max} 人，"
            "并先补充生源宣传、优化专业分流和设置分阶段评估指标。"
        )
    elif decision_level == "审慎":
        answer_parts.append(
            f"执行建议：可考虑分步扩招 {recommended_min}-{recommended_max} 人，按月或分批次监测志愿热度、报到率和培养容量，"
            "达到阈值后再决定是否追加。"
        )
    elif decision_level == "支持":
        answer_parts.append(
            f"执行建议：可考虑扩招 {recommended_min}-{recommended_max} 人，优先保障师资、宿舍、实验条件和就业服务，"
            "同时持续监测完成率和最低位次。"
        )
    else:
        answer_parts.append("执行建议：先补充连续年度计划和志愿数据后再决策，不建议仅凭单一指标扩招。")

    return {
        "decision": decision,
        "decision_level": decision_level,
        "recommended_min": recommended_min,
        "recommended_max": recommended_max,
        "demand_ratio": round(demand_ratio, 2),
        "plan_count": plan_count,
        "admitted_count": admitted_count,
        "choice_count": choice_count,
        "forecast_completion_rate": forecast_completion,
        "forecast_risk_level": forecast_risk,
        "answer": " ".join(answer_parts),
    }


async def _expansion_decision_context(
    db: AsyncSession,
    *,
    major_name: str,
    year: int | None,
) -> tuple[int | None, dict[str, Any] | None, dict[str, Any] | None]:
    year_no = await service._resolve_data_year(db, year)
    metric = None
    if year_no is not None:
        metrics = await service._get_major_year_metrics(db, year_no)
        metric = metrics.get(major_name)
    forecast_overview = await forecast_service.get_forecast_overview(
        db,
        year=year,
        major=major_name,
    )
    return year_no, metric, forecast_overview.get("forecast")


async def _tool_plan_simulation(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    raw_adjustments = params.get("adjustments")
    adjustments: list[dict[str, Any]] = []
    if isinstance(raw_adjustments, list):
        for item in raw_adjustments:
            if not isinstance(item, dict) or not item.get("major_name"):
                continue
            try:
                adjustments.append(
                    {
                        "major_name": str(item["major_name"]),
                        "plan_delta": int(item.get("plan_delta") or 0),
                    }
                )
            except (TypeError, ValueError):
                continue
    elif params.get("major") and params.get("plan_delta") is not None:
        try:
            adjustments.append(
                {
                    "major_name": str(params["major"]),
                    "plan_delta": int(params["plan_delta"]),
                }
            )
        except (TypeError, ValueError):
            pass

    if not adjustments and params.get("major"):
        major_name = str(params["major"])
        year_no, metric, forecast = await _expansion_decision_context(
            db,
            major_name=major_name,
            year=params.get("year"),
        )
        decision = _build_expansion_decision(
            major_name=major_name,
            year_no=year_no,
            metric=metric,
            forecast=forecast,
        )
        return {
            "answer": decision["answer"],
            "charts": [],
            "table": {
                "columns": ["专业", "计划数", "录取数", "志愿次数", "志愿热度比", "决策"],
                "rows": [[
                    major_name,
                    decision["plan_count"],
                    decision["admitted_count"],
                    decision["choice_count"],
                    decision["demand_ratio"],
                    decision["decision"],
                ]],
            },
            "data_sources": [
                {"table": "fact.plan", "metric": "专业计划"},
                {"table": "fact.admission_summary", "metric": "专业录取"},
                {"table": "fact.major_choice", "metric": "专业志愿热度"},
                {"table": "fact.plan", "metric": "下一年趋势预测"},
            ],
            "metrics": decision,
        }
    if not adjustments:
        return {
            "answer": "请明确要模拟的专业以及计划增减人数，例如：如果土木工程增加 20 个计划，录取和风险会怎样变化？",
            "charts": [],
            "table": None,
            "data_sources": [],
            "metrics": {"applied": 0},
        }

    simulation = await service.simulate_plan(
        db,
        year=params.get("year"),
        adjustments=adjustments,
    )
    results = simulation.get("results", [])
    baseline = simulation.get("baseline", {})
    projected = simulation.get("projected", {})
    unmatched = simulation.get("unmatched_adjustments", [])
    decision_note = ""
    decision_metrics: dict[str, Any] = {}
    if results:
        first_result = results[0]
        year_no, metric, forecast = await _expansion_decision_context(
            db,
            major_name=first_result["major_name"],
            year=params.get("year"),
        )
        decision = _build_expansion_decision(
            major_name=first_result["major_name"],
            year_no=year_no,
            metric=metric,
            forecast=forecast,
            scenario=first_result,
        )
        decision_note = decision["answer"] + " "
        decision_metrics = decision

    if not results and unmatched:
        answer = f"未找到专业：{'、'.join(unmatched)}。请检查专业名称后重新模拟。"
    elif not results:
        answer = simulation.get("message", "当前没有可执行的计划调整。")
    else:
        detail = "；".join(
            (
                f"{item['major_name']}计划由 {item['baseline_plan']} 调整为 {item['projected_plan']}，"
                f"预计录取 {item['projected_admitted']} 人，完成率 {item['projected_completion_rate']}%，"
                f"风险等级 {item['risk_level']}"
            )
            for item in results
        )
        answer = (
            decision_note
            + f"模拟后总计划为 {projected.get('plan_count', 0)} 人，预计录取 "
            f"{projected.get('admitted_count', 0)} 人，整体完成率 "
            f"{projected.get('completion_rate', 0)}%。{detail}。"
            f"{simulation.get('disclaimer', '')}"
        )
        if unmatched:
            answer += f" 未匹配专业：{'、'.join(unmatched)}。"

    labels: list[str] = []
    values: list[int] = []
    for item in results:
        labels.extend([f"{item['major_name']}·基准", f"{item['major_name']}·模拟"])
        values.extend([item["baseline_plan"], item["projected_plan"]])
    return {
        "answer": answer,
        "charts": [_bar_chart("招生计划模拟对比", labels, values)] if values else [],
        "table": {
            "columns": ["专业", "计划变化", "模拟计划", "模拟录取", "完成率", "分数变化", "风险"],
            "rows": [
                [
                    item["major_name"],
                    item["plan_delta"],
                    item["projected_plan"],
                    item["projected_admitted"],
                    item["projected_completion_rate"],
                    item["projected_score_change"],
                    item["risk_level"],
                ]
                for item in results
            ],
        }
        if results
        else None,
        "data_sources": simulation.get("data_sources", []),
        "metrics": {
            "baseline": baseline,
            "projected": projected,
            "applied_adjustments": len(results),
            "expansion_decision": decision_metrics,
        },
        "citations": [],
    }

async def _tool_official_admission_stats(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    year = params.get("year")
    rows_result = await db.execute(
        text("""
            SELECT
                year_no,
                COALESCE(SUM(plan_count), 0) AS regular_plan,
                COALESCE(SUM(regular_admitted_count), 0) AS regular_admitted,
                COALESCE(SUM(zhuan_admitted_count), 0) AS zhuan_admitted,
                COALESCE(SUM(total_admitted_count), 0) AS total_admitted
            FROM fact.authoritative_admission_stat
            WHERE data_version LIKE 'official-%'
              AND (CAST(:year AS integer) IS NULL OR year_no = :year)
            GROUP BY year_no
            ORDER BY year_no
            """
        ),
        {"year": year},
    )
    rows = [dict(row) for row in rows_result.mappings().all()]
    if not rows:
        return {
            "answer": "当前没有对应年度的官方招生统计。",
            "charts": [],
            "table": None,
            "data_sources": [{"table": "fact.authoritative_admission_stat", "metric": "官方招生统计"}],
            "metrics": {"data_points": 0},
        }
    if len(rows) == 1:
        item = rows[0]
        answer = (
            f"{item['year_no']} 年普通招生计划 {item['regular_plan']} 人，"
            f"普通录取 {item['regular_admitted']} 人，专升本 {item['zhuan_admitted']} 人，"
            f"总录取 {item['total_admitted']} 人。"
        )
    else:
        details = "；".join(
            (
                f"{item['year_no']} 年普通计划 {item['regular_plan']} 人、"
                f"普通录取 {item['regular_admitted']} 人、专升本 {item['zhuan_admitted']} 人、"
                f"总录取 {item['total_admitted']} 人"
            )
            for item in rows
        )
        answer = f"2024—2026 年官方招生统计为：{details}。"
    chart = _bar_chart(
        "年度官方录取人数",
        [str(item["year_no"]) for item in rows],
        [int(item["total_admitted"]) for item in rows],
    )
    table = {
        "columns": ["年度", "普通计划", "普通录取", "专升本", "总录取"],
        "rows": [
            [
                item["year_no"],
                item["regular_plan"],
                item["regular_admitted"],
                item["zhuan_admitted"],
                item["total_admitted"],
            ]
            for item in rows
        ],
    }
    return {
        "answer": answer,
        "charts": [chart],
        "table": table,
        "data_sources": [{"table": "fact.authoritative_admission_stat", "metric": "官方招生统计"}],
        "metrics": {"data_points": len(rows), "years": [item["year_no"] for item in rows]},
    }


async def _tool_major_alias_lookup(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    query = str(params.get("source_name") or params.get("major") or params.get("query") or "").strip()
    result = await db.execute(
        text(
            """
            SELECT
                ma.source_name,
                COALESCE(pr.province_name, '全局') AS province_name,
                cm.major_name AS canonical_major_name,
                ma.note,
                ma.is_active
            FROM dim.major_alias ma
            LEFT JOIN dim.province pr ON pr.id = ma.province_id
            JOIN dim.major cm ON cm.id = ma.canonical_major_id
            WHERE ma.is_active IS TRUE
              AND (
                  CAST(:query AS text) = ''
                  OR ma.source_name ILIKE :keyword
                  OR cm.major_name ILIKE :keyword
              )
            ORDER BY province_name, ma.source_name
            LIMIT 50
            """
        ),
        {"query": query, "keyword": f"%{query}%" if query else "%"},
    )
    rows = [dict(row) for row in result.mappings().all()]
    if not rows:
        answer = (
            f"当前没有找到与“{query}”相关的启用的专业名称映射规则。"
            if query
            else "当前没有启用的专业名称映射规则。"
        )
        table = None
    else:
        details = "；".join(
            f"{item['source_name']}（{item['province_name']}）→ {item['canonical_major_name']}"
            for item in rows[:12]
        )
        answer = f"当前专业名称映射规则：{details}。"
        table = {
            "columns": ["来源专业", "生效范围", "标准专业", "备注"],
            "rows": [
                [item["source_name"], item["province_name"], item["canonical_major_name"], item["note"]]
                for item in rows
            ],
        }
    return {
        "answer": answer,
        "charts": [],
        "table": table,
        "data_sources": [{"table": "dim.major_alias", "metric": "专业名称标准化映射"}],
        "metrics": {"matched": len(rows)},
    }

def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_score(value: Any) -> str:
    number = _as_float(value)
    if number is None:
        return "暂无"
    return f"{number:.1f}".rstrip("0").rstrip(".")

async def _tool_student_statistics(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    year = params.get("year")
    if year is None:
        year = await db.scalar(text("SELECT MAX(year_no) FROM dim.year"))
    clauses = ["si.year_no = :year", "ar.id IS NOT NULL"]
    binds: dict[str, Any] = {"year": int(year)}
    score_join = ""
    exam_subject_name = str(params.get("exam_subject_name") or "").strip()
    exam_score_value = params.get("exam_score_value")
    exam_score_operator = str(params.get("exam_score_operator") or "=").strip()
    try:
        exam_score_decimal = Decimal(str(exam_score_value)) if exam_score_value is not None else None
    except InvalidOperation:
        exam_score_decimal = None
    if exam_subject_name and exam_score_decimal is not None:
        allowed_operators = {"=": "=", ">": ">", ">=": ">=", "<": "<", "<=": "<="}
        exam_score_operator = allowed_operators.get(exam_score_operator, "=")
        score_join = (
            "JOIN fact.exam_subject_score ess "
            "ON ess.candidate_key=si.candidate_key AND ess.year_no=si.year_no"
        )
        clauses.append("ess.subject_name = :exam_subject_name")
        clauses.append(f"ess.score {exam_score_operator} :exam_score_value")
        binds["exam_subject_name"] = exam_subject_name
        binds["exam_score_value"] = exam_score_decimal
        exam_score_value = exam_score_decimal
    if params.get("surname"):
        clauses.append("si.student_name LIKE :surname_prefix")
        binds["surname_prefix"] = f"{str(params['surname']).strip()}%"
    if params.get("name_contains"):
        clauses.append("POSITION(:name_contains IN si.student_name) > 0")
        binds["name_contains"] = str(params["name_contains"]).strip()
    if params.get("gender_name"):
        clauses.append("cp.gender_name = :gender_name")
        binds["gender_name"] = str(params["gender_name"]).strip()
    if params.get("subject_name"):
        clauses.append("sub.subject_name = :subject_name")
        binds["subject_name"] = str(params["subject_name"]).strip()
    if params.get("province"):
        clauses.append("pr.province_name = :province_name")
        binds["province_name"] = str(params["province"]).strip()
    if params.get("major"):
        clauses.append("m.major_name = :major_name")
        binds["major_name"] = str(params["major"]).strip()
    if params.get("is_enrolled") is not None:
        clauses.append("COALESCE(es.is_enrolled, ar.is_enrolled) = :is_enrolled")
        binds["is_enrolled"] = bool(params["is_enrolled"])
    if params.get("student_status"):
        clauses.append("sm.student_status = :student_status")
        binds["student_status"] = str(params["student_status"]).strip()

    group_fields = {
        "major_name": ("m.major_name", "专业"),
        "province_name": ("pr.province_name", "省份"),
        "gender_name": ("cp.gender_name", "性别"),
        "subject_name": ("sub.subject_name", "科类"),
        "student_status": ("sm.student_status", "学生状态"),
        "channel_name": ("ch.channel_name", "渠道"),
    }
    group_by = str(params.get("group_by") or "")
    where_sql = " AND ".join(clauses)
    if group_by in group_fields:
        expression, label = group_fields[group_by]
        rows = (await db.execute(text(f"""
            SELECT COALESCE({expression}, '未标注') AS group_name,
                   COUNT(DISTINCT si.candidate_key) AS student_count
            FROM fact.student_identity si
            JOIN fact.admission_record ar ON ar.candidate_key=si.candidate_key AND ar.year_id=(SELECT id FROM dim.year WHERE year_no=si.year_no LIMIT 1)
            LEFT JOIN fact.candidate_profile cp ON cp.candidate_key=si.candidate_key AND cp.year_no=si.year_no
            LEFT JOIN fact.student_management sm ON sm.candidate_key=si.candidate_key AND sm.year_no=si.year_no
            LEFT JOIN fact.enrollment_status es ON es.candidate_key=si.candidate_key AND es.year_no=si.year_no
            {score_join}
            LEFT JOIN dim.province pr ON pr.id=ar.province_id
            LEFT JOIN dim.subject sub ON sub.id=ar.subject_id
            LEFT JOIN dim.major m ON m.id=ar.major_id
            LEFT JOIN dim.channel ch ON ch.id=ar.channel_id
            WHERE {where_sql}
            GROUP BY COALESCE({expression}, '未标注')
            ORDER BY student_count DESC, group_name
            LIMIT 30
        """), binds)).mappings().all()
        total = sum(int(row["student_count"] or 0) for row in rows)
        detail = "；".join(f"{row['group_name']} {row['student_count']} 人" for row in rows[:12])
        if rows:
            condition_text = (
                f"{exam_subject_name}成绩{exam_score_operator}{_format_score(exam_score_value)}分"
                if exam_subject_name and exam_score_value is not None
                else "符合条件"
            )
            answer = f"{condition_text}的学生共有 {total} 人。按{label}分组：{detail}。"
        else:
            answer = "没有找到符合条件的学生。"
        table = {"columns": [label, "人数"], "rows": [[row["group_name"], row["student_count"]] for row in rows]}
        chart = _bar_chart(f"按{label}统计", [str(row["group_name"]) for row in rows], [int(row["student_count"]) for row in rows])
    else:
        total = int((await db.scalar(text(f"""
            SELECT COUNT(DISTINCT si.candidate_key)
            FROM fact.student_identity si
            JOIN fact.admission_record ar ON ar.candidate_key=si.candidate_key AND ar.year_id=(SELECT id FROM dim.year WHERE year_no=si.year_no LIMIT 1)
            LEFT JOIN fact.candidate_profile cp ON cp.candidate_key=si.candidate_key AND cp.year_no=si.year_no
            LEFT JOIN fact.student_management sm ON sm.candidate_key=si.candidate_key AND sm.year_no=si.year_no
            LEFT JOIN fact.enrollment_status es ON es.candidate_key=si.candidate_key AND es.year_no=si.year_no
            {score_join}
            LEFT JOIN dim.province pr ON pr.id=ar.province_id
            LEFT JOIN dim.subject sub ON sub.id=ar.subject_id
            LEFT JOIN dim.major m ON m.id=ar.major_id
            LEFT JOIN dim.channel ch ON ch.id=ar.channel_id
            WHERE {where_sql}
        """), binds)) or 0)
        if exam_subject_name and exam_score_value is not None:
            operator_label = {"=": "为", ">": "高于", ">=": "不低于", "<": "低于", "<=": "不高于"}.get(
                exam_score_operator,
                "为",
            )
            condition_text = (
                f"{exam_subject_name}成绩{operator_label}{_format_score(exam_score_value)}分"
            )
            answer = f"{int(year)}年录取的学生中，{condition_text}的共有 {total} 人。"
        else:
            subject = f"姓{params['surname']}的" if params.get("surname") else "符合条件"
            answer = f"{int(year)}年录取的{subject}学生共有 {total} 人。"
        table = None
        chart = None
    data_sources = [{"table": "fact.student_identity", "metric": "学生人数统计"}]
    if exam_subject_name and exam_score_value is not None:
        data_sources.append({"table": "fact.exam_subject_score", "metric": "单科成绩筛选"})
    return {
        "answer": answer,
        "charts": [chart] if chart else [],
        "table": table,
        "data_sources": data_sources,
        "metrics": {
            "student_count": total,
            "year": int(year),
            "exam_subject_name": exam_subject_name or None,
            "exam_score_operator": exam_score_operator if exam_subject_name else None,
            "exam_score_value": float(exam_score_value) if exam_score_value is not None else None,
        },
    }


async def _tool_student_lookup(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    if not params.get("can_lookup_students"):
        return {
            "answer": "当前账号无权查看单个学生档案。请联系超级管理员。",
            "charts": [],
            "table": None,
            "data_sources": [],
            "metrics": {"matched": 0, "permission": "denied"},
        }
    name = str(params.get("student_name") or "").strip()
    year = params.get("year")
    if not name or not year:
        return {
            "answer": "请明确学生姓名和招生年度，例如：分析2024年录取的演示考生的情况。",
            "charts": [],
            "table": None,
            "data_sources": [],
            "metrics": {"matched": 0},
        }
    rows = await db.execute(
        text(
            """
            SELECT si.candidate_key, si.year_no, si.candidate_no, si.student_name,
                   ar.exam_score, ar.score AS filing_score, ar.rank_no,
                   ar.admit_type, ar.is_enrolled,
                   pr.province_name, m.major_name, b.batch_name, sub.subject_name,
                   cp.gender_name, cp.ethnicity_name, cp.region_name,
                   cp.source_school_name,
                   sm.student_status, sm.follow_up_status, sm.owner_name, sm.tags, sm.notes
            FROM fact.student_identity si
            LEFT JOIN fact.admission_record ar ON ar.candidate_key=si.candidate_key
            LEFT JOIN dim.year y ON y.id=ar.year_id AND y.year_no=si.year_no
            LEFT JOIN dim.province pr ON pr.id=ar.province_id
            LEFT JOIN dim.major m ON m.id=ar.major_id
            LEFT JOIN dim.batch b ON b.id=ar.batch_id
            LEFT JOIN dim.subject sub ON sub.id=ar.subject_id
            LEFT JOIN fact.candidate_profile cp ON cp.candidate_key=si.candidate_key AND cp.year_no=si.year_no
            LEFT JOIN fact.student_management sm ON sm.candidate_key=si.candidate_key AND sm.year_no=si.year_no
            WHERE si.year_no=:year AND si.student_name=:name
            ORDER BY si.candidate_key
            LIMIT 10
            """
        ),
        {"year": year, "name": name},
    )
    matches = [dict(row) for row in rows.mappings().all()]
    if not matches:
        return {
            "answer": f"未找到 {year} 年名为“{name}”的学生记录。",
            "charts": [],
            "table": None,
            "data_sources": [{"table": "fact.student_identity", "metric": "学生身份"}],
            "metrics": {"matched": 0, "year": year, "student_name": name},
        }
    if len(matches) > 1:
        return {
            "answer": f"{year} 年找到 {len(matches)} 名同名学生，请根据考生号和录取专业进一步确认。",
            "charts": [],
            "table": {
                "columns": ["姓名", "考生号", "录取专业", "省份"],
                "rows": [[item["student_name"], item["candidate_no"], item["major_name"], item["province_name"]] for item in matches],
            },
            "data_sources": [{"table": "fact.student_identity", "metric": "学生身份"}],
            "metrics": {"matched": len(matches), "year": year, "student_name": name},
        }

    item = matches[0]
    candidate_key = item["candidate_key"]
    score_rows = await db.execute(
        text(
            """
            SELECT subject_name, score
            FROM fact.exam_subject_score
            WHERE candidate_key=:candidate_key AND year_no=:year
            ORDER BY id
            """
        ),
        {"candidate_key": candidate_key, "year": year},
    )
    scores = [dict(row) for row in score_rows.mappings().all()]
    choice_rows = await db.execute(
        text(
            """
            SELECT choice_order, major_name
            FROM fact.major_choice
            WHERE candidate_key=:candidate_key AND year_no=:year
            ORDER BY choice_order
            """
        ),
        {"candidate_key": candidate_key, "year": year},
    )
    choices = [dict(row) for row in choice_rows.mappings().all()]
    status = item.get("student_status") or "NEW"
    follow_status = item.get("follow_up_status") or "PENDING"

    analysis_parts: list[str] = []
    analysis_metrics: dict[str, Any] = {}
    exam_score = _as_float(item.get("exam_score"))

    if exam_score is not None and item.get("subject_name"):
        cohort_row = (
            await db.execute(
                text(
                    """
                    SELECT COUNT(*) AS scored_count,
                           COUNT(*) FILTER (WHERE ar.exam_score <= :exam_score) AS at_or_below
                    FROM fact.admission_record ar
                    JOIN dim.year y ON y.id=ar.year_id
                    JOIN dim.subject sub ON sub.id=ar.subject_id
                    WHERE y.year_no=:year
                      AND sub.subject_name=:subject_name
                      AND ar.exam_score IS NOT NULL
                    """
                ),
                {
                    "year": year,
                    "subject_name": item.get("subject_name"),
                    "exam_score": item.get("exam_score"),
                },
            )
        ).mappings().first()
        scored_count = int(cohort_row["scored_count"] or 0) if cohort_row else 0
        at_or_below = int(cohort_row["at_or_below"] or 0) if cohort_row else 0
        if scored_count >= 20:
            percentile = at_or_below / scored_count * 100
            top_percent = max(0.0, 100 - percentile)
            analysis_metrics["cohort_scored_count"] = scored_count
            analysis_metrics["cohort_percentile"] = round(percentile, 1)
            analysis_parts.append(
                f"成绩位置：高考成绩 {_format_score(item.get('exam_score'))} 分，"
                f"在同年度、同科类 {scored_count} 条可比记录中约处于前 {top_percent:.1f}%。"
            )

    if exam_score is not None and item.get("major_name"):
        benchmark = (
            await db.execute(
                text(
                    """
                    SELECT COUNT(*) AS sample_count,
                           MIN(ar.exam_score) AS min_score,
                           MAX(ar.exam_score) AS max_score,
                           AVG(ar.exam_score) AS avg_score
                    FROM fact.admission_record ar
                    JOIN dim.year y ON y.id=ar.year_id
                    JOIN dim.major m ON m.id=ar.major_id
                    JOIN dim.province pr ON pr.id=ar.province_id
                    JOIN dim.subject sub ON sub.id=ar.subject_id
                    WHERE y.year_no=:year
                      AND m.major_name=:major_name
                      AND (
                          CAST(:province_name AS text) IS NULL
                          OR pr.province_name=CAST(:province_name AS text)
                      )
                      AND (
                          CAST(:subject_name AS text) IS NULL
                          OR sub.subject_name=CAST(:subject_name AS text)
                      )
                      AND ar.exam_score IS NOT NULL
                    """
                ),
                {
                    "year": year,
                    "major_name": item.get("major_name"),
                    "province_name": item.get("province_name"),
                    "subject_name": item.get("subject_name"),
                },
            )
        ).mappings().first()
        sample_count = int(benchmark["sample_count"] or 0) if benchmark else 0
        average_score = _as_float(benchmark["avg_score"]) if benchmark else None
        if sample_count >= 5 and average_score is not None:
            delta = exam_score - average_score
            relation = "高于" if delta >= 0 else "低于"
            analysis_metrics["major_sample_count"] = sample_count
            analysis_metrics["major_average_score"] = round(average_score, 1)
            analysis_parts.append(
                f"录取竞争力：{item.get('province_name') or '来源省份'}"
                f"{item.get('subject_name') or ''}{item.get('major_name')}可比录取记录 {sample_count} 条，"
                f"高考成绩区间 {_format_score(benchmark['min_score'])}-{_format_score(benchmark['max_score'])} 分，"
                f"均值 {_format_score(average_score)} 分；该生{relation}均值 {abs(delta):.1f} 分。"
            )

    if scores:
        average_rows = await db.execute(
            text(
                """
                SELECT subject_name, AVG(score) AS avg_score
                FROM fact.exam_subject_score
                WHERE year_no=:year
                GROUP BY subject_name
                """
            ),
            {"year": year},
        )
        subject_averages = {
            str(row["subject_name"]): _as_float(row["avg_score"])
            for row in average_rows.mappings().all()
        }
        subject_deltas = []
        for row in scores:
            score_value = _as_float(row.get("score"))
            average_value = subject_averages.get(str(row.get("subject_name")))
            if score_value is not None and average_value is not None:
                subject_deltas.append((str(row["subject_name"]), score_value - average_value))
        strengths = sorted(
            (item for item in subject_deltas if item[1] >= 2),
            key=lambda value: value[1],
            reverse=True,
        )[:3]
        weaknesses = sorted(
            (item for item in subject_deltas if item[1] <= -2),
            key=lambda value: value[1],
        )[:2]
        subject_notes = []
        if strengths:
            subject_notes.append(
                "优势科目：" + "、".join(f"{name}高于同年度整体均分 {delta:.1f} 分" for name, delta in strengths)
            )
        if weaknesses:
            subject_notes.append(
                "需关注科目：" + "、".join(f"{name}低于同年度整体均分 {abs(delta):.1f} 分" for name, delta in weaknesses)
            )
        if subject_notes:
            analysis_parts.append("学科画像：" + "；".join(subject_notes) + "。")

    if choices and item.get("major_name"):
        matched_choice = next(
            (row for row in choices if row.get("major_name") == item.get("major_name")),
            None,
        )
        if matched_choice:
            choice_order = int(matched_choice["choice_order"])
            match_text = "第一志愿" if choice_order == 1 else f"第 {choice_order} 志愿"
            analysis_parts.append(f"专业匹配：录取专业为{match_text}，志愿一致性明确。")

    if follow_status in {"NEW", "PENDING"}:
        analysis_parts.append("管理侧重点：该生仍处于待跟进阶段，建议优先核实报到意向、联系方式更新和专业适应情况。")
    elif follow_status:
        analysis_parts.append(f"管理侧重点：当前跟进状态为 {follow_status}，建议按现有流程持续更新记录。")

    answer = (
        f"{year} 年录取学生“{item['student_name']}”，考生号 {item['candidate_no']}，"
        f"{item.get('gender_name') or '性别未知'}，来源学校 {item.get('source_school_name') or '未知'}。"
        f"录取信息：{item.get('province_name') or '未知省份'}、{item.get('batch_name') or '未知批次'}、"
        f"{item.get('subject_name') or '未知科类'}、{item.get('major_name') or '未知专业'}。"
        f"高考成绩 {item.get('exam_score') if item.get('exam_score') is not None else '暂无'}，"
        f"投档成绩 {item.get('filing_score') if item.get('filing_score') is not None else '暂无'}，"
        f"最低位次 {item.get('rank_no') if item.get('rank_no') is not None else '暂无'}。"
        f"管理状态：{status}，跟进状态：{follow_status}。"
    )
    if choices:
        answer += " 专业志愿顺序：" + "、".join(f"{row['choice_order']}. {row['major_name']}" for row in choices) + "。"
    if analysis_parts:
        answer += " 综合分析：" + " ".join(analysis_parts)
    table = {
        "columns": ["科目", "成绩"],
        "rows": [[row["subject_name"], row["score"]] for row in scores],
    }
    return {
        "answer": answer,
        "charts": [],
        "table": table if scores else None,
        "data_sources": [
            {"table": "fact.student_identity", "metric": "学生身份"},
            {"table": "fact.admission_record", "metric": "录取信息"},
            {"table": "fact.exam_subject_score", "metric": "学科成绩"},
            {"table": "fact.major_choice", "metric": "专业志愿"},
            {"table": "fact.student_management", "metric": "跟进状态"},
        ],
        "metrics": {
            "matched": 1,
            "year": year,
            "candidate_no": item["candidate_no"],
            "exam_score": item.get("exam_score"),
            "filing_score": item.get("filing_score"),
            **analysis_metrics,
        },
    }

_TOOL_RESULT_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _tool_cache_key(name: str, params: dict[str, Any], school_id: Any) -> str:
    return json.dumps({"tool": name, "params": params, "school_id": school_id}, ensure_ascii=False, sort_keys=True, default=str)


def _tool_cache_get(key: str) -> dict[str, Any] | None:
    item = _TOOL_RESULT_CACHE.get(key)
    if item is None:
        return None
    expires_at, value = item
    if expires_at < time.monotonic():
        _TOOL_RESULT_CACHE.pop(key, None)
        return None
    return copy.deepcopy(value)


def _tool_cache_set(key: str, value: dict[str, Any]) -> None:
    _TOOL_RESULT_CACHE[key] = (time.monotonic() + max(1, settings.agent_cache_ttl_seconds), copy.deepcopy(value))


def clear_agent_tool_cache() -> None:
    _TOOL_RESULT_CACHE.clear()


async def _tool_cache_lookup(
    key: str,
    *,
    school_id: int | None,
) -> tuple[dict[str, Any] | None, str]:
    local_value = _tool_cache_get(key)
    if local_value is not None:
        return local_value, "L1"
    if settings.agent_shared_cache_enabled:
        shared_value = await shared_get_json("agent:tool", key, school_id)
        if isinstance(shared_value, dict):
            _tool_cache_set(key, shared_value)
            return copy.deepcopy(shared_value), "L2"
    return None, "MISS"


async def _tool_cache_store(
    key: str,
    value: dict[str, Any],
    *,
    school_id: int | None,
) -> None:
    _tool_cache_set(key, value)
    if settings.agent_shared_cache_enabled:
        await shared_set_json(
            "agent:tool",
            key,
            value,
            school_id=school_id,
            ttl_seconds=settings.agent_cache_ttl_seconds,
        )


TOOL_EXECUTORS: dict[str, Callable[[AsyncSession, dict[str, Any]], Awaitable[dict[str, Any]]]] = {
    "admissions_overview": _tool_admissions_overview,
    "source_overview": _tool_source_overview,
    "candidate_profile": _tool_candidate_profile,
    "subject_scores": _tool_subject_scores,
    "major_choices": _tool_major_choices,
    "medical_summary": _tool_medical_summary,
    "forecast": _tool_forecast,
    "official_admission_stats": _tool_official_admission_stats,
    "major_alias_lookup": _tool_major_alias_lookup,
    "student_lookup": _tool_student_lookup,
    "student_statistics": _tool_student_statistics,
    "anomaly_detection": _tool_anomaly_detection,
    "plan_simulation": _tool_plan_simulation,
    "policy_faq": _tool_policy_faq,
    "consultation_overview": consultation_overview,
    "enrollment_funnel": enrollment_funnel,
    "score_band_statistics": score_band_statistics,
}


def _normalize_params(params: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue
        if key in {"year", "plan_delta"}:
            try:
                value = int(value)
            except (TypeError, ValueError):
                continue
        normalized[key] = value
    return normalized


async def _load_memory_and_knowledge_parallel(
    *,
    user_id: int,
    school_id: int | None,
    message: str,
    normalized_message: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    async with AsyncSessionLocal() as memory_db, AsyncSessionLocal() as knowledge_db:
        return await asyncio.gather(
            load_relevant_memories(
                memory_db,
                user_id=user_id,
                school_id=school_id,
                query=message,
            ),
            search_knowledge(
                knowledge_db,
                query=normalized_message,
                school_id=school_id,
                limit=4,
            ),
        )


def _should_use_local_plan(
    message: str,
    intent: str,
    params: dict[str, Any],
) -> bool:
    if not minimind_router.configured:
        return False
    if not settings.agent_fast_mode:
        return True
    if intent in {"student_lookup", "student_statistics"}:
        return False
    if intent == "plan_simulation":
        return True

    complex_cues = (
        "综合分析", "结合", "联合", "关联", "关系", "规律", "对比", "同时分析",
        "共同", "为什么", "原因", "如何", "怎么", "建议", "影响", "方案", "优化",
        "决策", "权衡", "优先", "利弊",
    )
    if any(cue in message for cue in complex_cues):
        return True
    if intent == "forecast" and any(
        cue in message
        for cue in ("扩招", "缩招", "必要", "应该", "建议", "可以", "风险", "调整")
    ):
        return True
    follow_up_cues = ("那", "这个专业呢", "它", "其", "上述", "前面", "继续分析")
    return len(message) <= 12 and any(cue in message for cue in follow_up_cues)


def _should_retrieve_knowledge(intent: str, use_local_plan: bool) -> bool:
    if use_local_plan:
        return True
    return intent in {"policy_faq", "major_alias_lookup"}


def _single_tool_plan(intent: str) -> dict[str, Any] | None:
    if intent not in TOOL_EXECUTORS:
        return None
    return {
        "intent": intent,
        "tools": [{"name": intent, "params": {}}],
        "reason": "规则工具路由",
        "suggestions": _default_suggestions(intent),
    }


async def _execute_plan(
    db: AsyncSession,
    plan: dict[str, Any],
    fallback_params: dict[str, Any],
) -> dict[str, Any]:
    tool_results = []
    tool_calls = []
    for tool in plan["tools"]:
        name = tool["name"]
        params = _normalize_params({**(tool.get("params") or {}), **fallback_params})
        if _is_multi_year_question(str(fallback_params.get("query") or "")):
            params.pop("year", None)
        cache_key = None
        cache_layer = "MISS"
        result = None
        if settings.agent_fast_mode and name != "student_lookup":
            cache_key = _tool_cache_key(name, params, fallback_params.get("school_id"))
            result, cache_layer = await _tool_cache_lookup(
                cache_key,
                school_id=fallback_params.get("school_id"),
            )
        cache_hit = cache_layer != "MISS"
        if result is None:
            result = await TOOL_EXECUTORS[name](db, params)
            if cache_key is not None:
                await _tool_cache_store(
                    cache_key,
                    result,
                    school_id=fallback_params.get("school_id"),
                )
        tool_results.append(
            {
                "tool": name,
                "cache_hit": cache_hit,
                "cache_layer": cache_layer,
                "params": params,
                "answer": result["answer"],
                "metrics": result.get("metrics"),
                "data_sources": result.get("data_sources", []),
                "charts": result.get("charts", []),
                "table": result.get("table"),
                "citations": result.get("citations", []),
            }
        )
        tool_calls.append({"tool": name, "params": params})

    answer_parts = [result["answer"] for result in tool_results]
    combined_answer = "\n".join(answer_parts)
    first_tool_params = plan["tools"][0].get("params", {}) if plan.get("tools") else {}
    combined_answer += _synthetic_note(
        {**fallback_params, **first_tool_params},
        {tool["name"] for tool in plan.get("tools", [])},
    )
    charts = [chart for result in tool_results for chart in result.get("charts", [])][:2]
    table = next((result.get("table") for result in tool_results if result.get("table")), None)
    citations = []
    seen_citations = set()
    for result in tool_results:
        for citation in result.get("citations", []):
            key = (citation.get("title"), citation.get("url"))
            if key not in seen_citations:
                citations.append(citation)
                seen_citations.add(key)

    data_sources = []
    seen_sources = set()
    for result in tool_results:
        for source in result.get("data_sources", []):
            key = (source.get("table"), source.get("metric"))
            if key not in seen_sources:
                data_sources.append(source)
                seen_sources.add(key)

    return {
        "intent": plan.get("intent") or "smart_analysis",
        "answer": combined_answer,
        "charts": charts,
        "table": table,
        "data_sources": data_sources,
        "tool_calls": tool_calls,
        "tool_results": tool_results,
        "confidence": "high" if tool_results else "low",
        "suggestions": plan.get("suggestions", []),
        "plan_summary": plan.get("reason"),
        "citations": citations,
    }


def _fallback_plan(message: str, intent: str, major: str | None) -> dict[str, Any] | None:
    if intent == "forecast" and major and any(
        keyword in message for keyword in ("增加名额", "增加招生", "有必要", "必要性", "是否增加")
    ):
        return {
            "intent": "forecast_professional_analysis",
            "tools": [
                {"name": "forecast", "params": {"major": major}},
                {"name": "admissions_overview", "params": {"major": major}},
                {"name": "major_choices", "params": {"major": major}},
            ],
            "reason": "预测、计划完成率和志愿热度联合分析",
            "suggestions": ["模拟增加计划后的影响", "查看历年计划趋势", "分析该专业志愿热度"],
        }
    return None


async def _execute_rule_based(
    db: AsyncSession,
    intent: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    params = _normalize_params(params)
    result = await TOOL_EXECUTORS[intent](db, params)
    result["answer"] += _synthetic_note(params, {intent})
    return {
        "intent": intent,
        **(result),
        "tool_calls": [{"tool": intent, "params": params}],
        "tool_results": [
            {
                "tool": intent,
                "params": params,
                "answer": result["answer"],
                "metrics": result.get("metrics"),
                "data_sources": result.get("data_sources", []),
            }
        ],
        "confidence": "high" if result.get("metrics") else "low",
        "suggestions": _default_suggestions(intent),
        "plan_summary": "规则工具路由",
        "citations": result.get("citations", []),
    }


def _default_suggestions(intent: str) -> list[str]:
    suggestions = {
        "admissions_overview": ["查看各专业计划完成率", "哪些专业计划数最多？", "各省招生计划是多少？"],
        "candidate_profile": ["考生性别结构如何？", "生源主要来自哪些地区？", "物理类和历史类人数是多少？"],
        "subject_scores": ["各科平均分是多少？", "哪一科平均分最高？", "哪些科目成绩差异较大？"],
        "major_choices": ["哪些专业志愿热度最高？", "志愿热度和计划数是否匹配？", "热门专业有哪些？"],
        "medical_summary": ["体检专业受限情况如何？", "体检结论分布是什么？", "哪些考生需要重点关注？"],
        "source_overview": ["生源渠道分布如何？", "报到率是多少？", "哪些地区生源最多？"],
        "forecast": ["明年计划完成率预测是多少？", "预测风险等级如何？", "预测区间是多少？"],
        "official_admission_stats": ["2026年专升本有多少人？", "三年总招生人数对比", "2024年普通计划是多少？"],
        "major_alias_lookup": ["当前有哪些专业名称映射？", "某专业在不同省份叫什么？", "这些名称是否会合并统计？"],
        "student_lookup": ["分析该生录取情况", "查看该生各科成绩", "该生专业志愿顺序是什么？"],
        "student_statistics": ["2025年录取的姓王的学生有多少？", "按专业统计男生人数", "统计各省份未报到人数"],
        "anomaly_detection": ["哪些专业存在高风险？", "计划完成率异常的专业有哪些？", "志愿热度和计划是否匹配？"],
        "plan_simulation": ["土木工程增加 20 个计划会怎样？", "某专业减少计划的风险如何？", "如何调整计划更稳妥？"],
    }
    return suggestions.get(intent, ["还可以从哪些角度分析？", "生成一份综合分析报告", "有哪些异常需要关注？"])


def _assess_data_support(
    *,
    result: dict[str, Any],
    self_check: dict[str, Any],
    canonical_intent: str,
    knowledge_items: list[dict[str, Any]],
) -> dict[str, Any]:
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
    if canonical_intent == "policy_faq" and not citations and not knowledge_items:
        caps.append(0.50)
        reasons.append("政策结论缺少依据")

    score = min([base_score, *caps]) if caps else base_score
    score = round(max(0.0, min(1.0, score)), 4)
    return {
        "score": score,
        "threshold": settings.agent_min_data_support,
        "status": "sufficient" if score >= settings.agent_min_data_support else "insufficient",
        "confidence_score": confidence_score,
        "self_check_score": self_check_score,
        "reasons": reasons,
    }


async def answer_question(
    db: AsyncSession,
    *,
    user: User,
    message: str,
    conversation_id: int | None,
    context: dict[str, Any],
) -> dict[str, Any]:
    request_started = time.perf_counter()
    normalized_message = normalize_colloquial(message)
    fallback_intent = _classify(normalized_message)
    school_context = await resolve_school_context(db, user_id=user.id, context=context)

    year = _extract_year(normalized_message, context)
    if year is None and not _uses_all_year_scope(normalized_message):
        latest_year = await db.scalar(text("SELECT MAX(year_no) FROM dim.year"))
        year = int(latest_year) if latest_year is not None else None
    province = await _extract_province(db, normalized_message, context)
    major = await _extract_major(db, normalized_message, context)
    exam_score_condition = _extract_exam_score_condition(normalized_message, context) or {}
    params = {
        "year": year,
        "province": province,
        "major": major,
        "student_name": _extract_student_name(normalized_message, context),
        "surname": _extract_surname(normalized_message, context),
        "name_contains": _extract_name_contains(normalized_message, context),
        "gender_name": _extract_gender_name(normalized_message, context),
        "subject_name": _extract_subject_name(normalized_message),
        "student_status": _extract_student_status(normalized_message),
        "is_enrolled": _extract_enrollment_filter(normalized_message),
        "group_by": _extract_group_by(normalized_message),
        "exam_subject_name": exam_score_condition.get("exam_subject_name"),
        "exam_score_operator": exam_score_condition.get("exam_score_operator"),
        "exam_score_value": exam_score_condition.get("exam_score_value"),
        "can_lookup_students": is_super_admin(user),
        "plan_delta": _extract_plan_delta(normalized_message, context),
        "school_id": school_context.get("school_id"),
        "school_name": school_context.get("school_name"),
        "query": normalized_message,
    }
    use_local_plan = _should_use_local_plan(normalized_message, fallback_intent, params)
    retrieve_knowledge = _should_retrieve_knowledge(fallback_intent, use_local_plan)
    if fallback_intent in {"student_lookup", "student_statistics"}:
        memory_items: list[dict[str, Any]] = []
        knowledge_items: list[dict[str, Any]] = []
    elif retrieve_knowledge:
        memory_items, knowledge_items = await _load_memory_and_knowledge_parallel(
            user_id=user.id,
            school_id=school_context.get("school_id"),
            message=message,
            normalized_message=normalized_message,
        )
    else:
        memory_items = await load_relevant_memories(
            db,
            user_id=user.id,
            school_id=school_context.get("school_id"),
            query=message,
        )
        knowledge_items = []

    if conversation_id is None:
        conversation_id = await execute_returning_id(
            db,
            """
            INSERT INTO ai.conversation (user_id, title, mode)
            VALUES (:user_id, :title, 'AUTO')
            RETURNING id
            """,
            {"user_id": user.id, "title": message[:80]},
        )

    await db.execute(
        text("""
            INSERT INTO ai.message (conversation_id, role, content, intent)
            VALUES (:conversation_id, 'user', :content, :intent)
            """
        ),
        {"conversation_id": conversation_id, "content": message, "intent": fallback_intent},
    )

    used_local_router = False
    if fallback_intent == "memory_command":
        result = {
            "intent": "memory_command",
            "answer": "已记录这条长期偏好，后续回答会优先参考它。",
            "charts": [],
            "table": None,
            "data_sources": [],
            "tool_calls": [],
            "tool_results": [],
            "confidence": "high",
            "suggestions": [],
            "plan_summary": "长期记忆写入",
            "citations": [],
        }
    else:
        plan = None
        if use_local_plan:
            plan = await minimind_router.route(
                message=normalized_message,
                fallback_intent=fallback_intent,
                params=params,
            )
            used_local_router = plan is not None
        if plan is None:
            plan = _fallback_plan(normalized_message, fallback_intent, major)
        if plan is None:
            plan = _single_tool_plan(fallback_intent)
        if plan:
            result = await _execute_plan(db, plan, params)
        else:
            result = await _execute_rule_based(db, fallback_intent, params)
    routing_finished = time.perf_counter()

    knowledge_citations = []
    for item in knowledge_items:
        metadata = item.get("metadata") or {}
        source_url = item.get("source_url")
        if isinstance(metadata, dict) and metadata.get("sources"):
            source_url = metadata["sources"][0].get("url") or source_url
        knowledge_citations.append(
            {
                "title": item.get("title"),
                "url": source_url,
                "snippet": str(item.get("content") or "")[:240],
                "score": item.get("score"),
                "document_type": item.get("document_type"),
            }
        )
    combined_citations = list(result.get("citations", []))
    seen_citations = {(item.get("title"), item.get("url")) for item in combined_citations}
    for citation in knowledge_citations:
        key = (citation.get("title"), citation.get("url"))
        if key not in seen_citations:
            combined_citations.append(citation)
            seen_citations.add(key)

    deterministic_answer = result["answer"]
    tool_names = [call["tool"] for call in result.get("tool_calls", [])]
    canonical_intent = tool_names[0] if tool_names else fallback_intent
    template = await select_prompt_template(
        db,
        task_type=task_type_for_intent(canonical_intent),
        school_id=school_context.get("school_id"),
    )
    answer = deterministic_answer
    mandatory_note = _synthetic_note(
        params,
        {call["tool"] for call in result.get("tool_calls", [])},
    )
    if mandatory_note and "模拟数据" not in answer:
        answer += mandatory_note
    answer_finished = time.perf_counter()

    self_check = evaluate_answer(
        question=message,
        intent=canonical_intent,
        answer=answer,
        tool_calls=result.get("tool_calls", []),
        tool_results=result.get("tool_results", []),
        knowledge_results=knowledge_items,
        citations=combined_citations,
    )
    if self_check["action"] == "fallback_required" and answer != deterministic_answer:
        answer = deterministic_answer
        self_check = evaluate_answer(
            question=message,
            intent=canonical_intent,
            answer=answer,
            tool_calls=result.get("tool_calls", []),
            tool_results=result.get("tool_results", []),
            knowledge_results=knowledge_items,
            citations=combined_citations,
        )
    data_support = _assess_data_support(
        result=result,
        self_check=self_check,
        canonical_intent=canonical_intent,
        knowledge_items=knowledge_items,
    )
    insufficient_data = data_support["status"] == "insufficient"
    self_check["data_support"] = data_support
    if insufficient_data:
        answer = "数据支撑不足，为保证严谨性，暂不回答"
        self_check["action"] = "insufficient_data"
        self_check["issues"] = [*self_check.get("issues", []), "数据支撑度低于阈值"]
    response_confidence = "low" if insufficient_data else result.get("confidence", "low")
    reasoning_trace = [
        f"学校上下文：{school_context.get('school_name') or '默认学校'}",
        f"意图识别：{result['intent']}",
        "工具计划：" + ("、".join(call["tool"] for call in result.get("tool_calls", [])) or "无需数据工具"),
        "链路模式：" + (
            "MiniMind 本地规划" if used_local_router else "规则直达"
        ),
        f"工具缓存：命中 {sum(1 for item in result.get('tool_results', []) if item.get('cache_hit'))} 项",
        f"知识库检索：命中 {len(knowledge_items)} 条",
        f"长期记忆：使用 {len(memory_items)} 条",
        f"回答自查：{self_check['score']:.2f} 分，动作 {self_check['action']}",
        f"数据支撑度：{data_support['score']:.2f}，阈值 {data_support['threshold']:.2f}，状态 {data_support['status']}",
        f"规划与取数耗时：{(routing_finished - request_started) * 1000:.0f} ms",
        f"回答生成耗时：{(answer_finished - routing_finished) * 1000:.0f} ms",
    ]
    assistant_message_id = await execute_returning_id(
        db,
        """
        INSERT INTO ai.message (
            conversation_id, role, content, intent, citations, tool_result, confidence
        )
        VALUES (
            :conversation_id, 'assistant', :content, :intent,
            CAST(:citations AS jsonb), CAST(:tool_result AS jsonb), :confidence
        )
        RETURNING id
        """,
        {
            "conversation_id": conversation_id,
            "content": answer,
            "intent": result["intent"],
            "citations": json.dumps(combined_citations, ensure_ascii=False),
            "tool_result": json.dumps(
                {
                    "data_sources": result.get("data_sources", []),
                    "table": result.get("table"),
                    "tool_results": result.get("tool_results", []),
                    "knowledge_results": knowledge_items,
                    "memories_used": memory_items,
                    "reasoning_trace": reasoning_trace,
                    "self_check": self_check,
                    "school": {
                        "school_id": school_context.get("school_id"),
                        "school_code": school_context.get("school_code"),
                        "school_name": school_context.get("school_name"),
                    },
                },
                default=str,
                ensure_ascii=False,
            ),
            "confidence": response_confidence,
        },
    )

    for tool_call in result.get("tool_calls", []):
        await db.execute(
            text(
                """
                INSERT INTO ai.tool_call (
                    conversation_id, tool_name, input_params, output_summary, status, duration_ms
                )
                VALUES (
                    :conversation_id, :tool_name,
                    CAST(:input_params AS jsonb), CAST(:output_summary AS jsonb),
                    'SUCCESS', 0
                )
                """
            ),
            {
                "conversation_id": conversation_id,
                "tool_name": tool_call["tool"],
                "input_params": json.dumps(tool_call.get("params", {}), default=str, ensure_ascii=False),
                "output_summary": json.dumps({"message_id": assistant_message_id}, ensure_ascii=False),
            },
        )

    await record_response_evaluation(
        db,
        message_id=assistant_message_id,
        school_id=school_context.get("school_id"),
        intent=canonical_intent,
        template_id=(template or {}).get("id"),
        tool_names=tool_names,
        evaluation=self_check,
    )
    if canonical_intent not in {"student_lookup", "student_statistics"}:
        await remember_turn(
            db,
            user_id=user.id,
            school_id=school_context.get("school_id"),
            conversation_id=conversation_id,
            question=message,
            intent=result["intent"],
            answer=answer,
        )
    await db.commit()
    await record_chat_metric(
        duration_ms=(time.perf_counter() - request_started) * 1000,
        route_mode="local" if used_local_router else "fast",
        cache_layers=[
            str(item.get("cache_layer") or "MISS")
            for item in result.get("tool_results", [])
            if item.get("cache_layer") is not None
        ],
        tool_count=len(result.get("tool_results", [])),
    )
    return {
        "conversation_id": conversation_id,
        "message_id": assistant_message_id,
        "intent": result["intent"],
        "answer": answer,
        "confidence": response_confidence,
        "need_human": (
            response_confidence == "low"
            or self_check["action"] in {"fallback_required", "insufficient_data"}
        ),
        "data_sources": result.get("data_sources", []),
        "charts": result.get("charts", []),
        "table": result.get("table"),
        "tool_calls": result.get("tool_calls", []),
        "suggestions": result.get("suggestions", []),
        "plan_summary": result.get("plan_summary"),
        "citations": combined_citations,
        "reasoning_trace": reasoning_trace,
        "self_check": self_check,
        "memory_used": memory_items,
        "knowledge_sources": knowledge_items,
        "school_context": {
            "school_id": school_context.get("school_id"),
            "school_code": school_context.get("school_code"),
            "school_name": school_context.get("school_name"),
            "dbf_schema_version": (school_context.get("dbf_profile") or {}).get("schema_version"),
        },
    }








































