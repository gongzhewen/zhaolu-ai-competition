from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any


def extract_year(message: str, context: dict[str, Any] | None = None, current_year: int = 2026) -> int | None:
    context = context or {}
    if context.get("year"):
        return int(context["year"])
    matches = re.findall(r"(20\d{2})", message)
    if len(matches) >= 2 and any(keyword in message for keyword in ("到", "至", "趋势", "历年", "近三年")):
        return None
    if matches:
        return int(matches[0])
    if any(keyword in message for keyword in ("今年", "本年", "当前年度")):
        return current_year
    if any(keyword in message for keyword in ("去年", "上一年")):
        return current_year - 1
    if "前年" in message:
        return current_year - 2
    return None


def uses_all_year_scope(message: str) -> bool:
    return any(
        keyword in message
        for keyword in (
            "历年", "逐年", "每年", "趋势", "近三年", "三年", "各年度", "全部年度", "年度对比", "明年", "下一年", "预测"
        )
    )


def is_multi_year_question(message: str) -> bool:
    year_matches = re.findall(r"(20\d{2})", message)
    return any(keyword in message for keyword in ("历年", "逐年", "每年", "趋势", "近三年", "三年", "各年度", "全部年度", "年度对比", "相比")) or (
        len(year_matches) >= 2 and any(keyword in message for keyword in ("到", "至"))
    )


def clean_student_name(value: str) -> str | None:
    cleaned = re.sub(r"[\s“”\'‘’《》【】\[\]（）()]+", "", value)
    if not re.fullmatch(r"[\u4e00-\u9fff·]{2,10}", cleaned):
        return None
    if cleaned in {"学生", "考生", "同学", "姓名", "情况", "录取", "成绩", "志愿"}:
        return None
    if any(keyword in cleaned for keyword in ("多少", "人数", "是多少", "招生", "计划")):
        return None
    return cleaned


def extract_student_name(message: str, context: dict[str, Any] | None = None) -> str | None:
    context = context or {}
    if context.get("student_name"):
        return clean_student_name(str(context["student_name"])) or None
    patterns = (
        r"([\u4e00-\u9fff·]{2,4})的(?:档案|成绩|志愿|录取|情况)",
        r"(?:名为|名叫|姓名为|姓名叫)\s*[“”\"'‘’]?([\u4e00-\u9fff·]{2,10}?)[“”\"'‘’]?(?=\s*(?:的|学生|同学|考生|录取|情况|成绩|志愿|[，,、。]|$))",
        r"姓名\s*[:：]?\s*(?:是|为|叫)?\s*[“”\"'‘’]?([\u4e00-\u9fff·]{2,10}?)[“”\"'‘’]?(?=\s*(?:的|学生|同学|考生|录取|情况|成绩|志愿|[，,、。]|$))",
        r"(?:录取|考入|考上|招收)\s*的?\s*[“”\"'‘’]?([\u4e00-\u9fff·]{2,10}?)[“”\"'‘’]?(?=\s*(?:同学|学生|考生|的|情况|录取|成绩|志愿|[，,、。]|$))",
        r"(?:学生|考生|同学)\s*[“”\"'’]?([\u4e00-\u9fff·]{2,10}?)[“”\"'’]?(?=\s*(?:的|情况|录取|成绩|志愿))",
        r"[“”\"'‘’]([\u4e00-\u9fff·]{2,10}?)[“”\"'‘’](?=\s*(?:同学|学生|考生|的|录取|情况|成绩|志愿|[，,、。]|$))",
    )
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            candidate = clean_student_name(match.group(1))
            if candidate and not candidate.startswith("姓"):
                return candidate
    return None


def extract_plan_delta(message: str, context: dict[str, Any] | None = None) -> int | None:
    context = context or {}
    if context.get("plan_delta") is not None:
        try:
            return int(context["plan_delta"])
        except (TypeError, ValueError):
            return None
    patterns = (
        r"(?:增加|上调|扩招|新增)(\d+)(?:个)?(?:招生计划|计划|名额)",
        r"(?:减少|下调|缩减|削减)(\d+)(?:个)?(?:招生计划|计划|名额)",
        r"(?:增加|上调|扩招|新增)(?:专项计划|招生计划|计划|名额)\s*(\d+)",
        r"(?:减少|下调|缩减|削减)(?:专项计划|招生计划|计划|名额)\s*(\d+)",
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


def extract_surname(message: str, context: dict[str, Any] | None = None) -> str | None:
    context = context or {}
    if context.get("surname"):
        return str(context["surname"]).strip() or None
    match = re.search(r"姓([\u4e00-\u9fff]{1,2}?)(?:的)?(?:学生|考生|同学)", message)
    if match:
        return match.group(1).removesuffix("的")
    match = re.search(r"([\u4e00-\u9fff]{1,2})姓(?:学生|考生|同学)", message)
    return match.group(1).removesuffix("的") if match else None


def extract_name_contains(message: str, context: dict[str, Any] | None = None) -> str | None:
    context = context or {}
    if context.get("name_contains"):
        return str(context["name_contains"]).strip() or None
    match = re.search(r"(?:姓名|名字)(?:包含|含|中有)([\u4e00-\u9fff]{1,4})", message)
    return match.group(1) if match else None


def extract_gender_name(message: str, context: dict[str, Any] | None = None) -> str | None:
    context = context or {}
    if context.get("gender_name"):
        return str(context["gender_name"]).strip() or None
    if any(keyword in message for keyword in ("男生", "男性", "男学生")):
        return "男"
    if any(keyword in message for keyword in ("女生", "女性", "女学生")):
        return "女"
    return None


def extract_subject_name(message: str) -> str | None:
    for name in ("物理类", "历史类", "理科", "文科", "艺术类", "体育类", "专升本"):
        if name in message:
            return name
    return None


def extract_academic_subject_name(message: str) -> str | None:
    for name in ("语文", "数学", "外语", "英语", "物理", "化学", "生物", "政治", "历史", "地理", "技术", "综合"):
        if name in message:
            return "外语" if name == "英语" else name
    return None


def extract_alias_source_name(message: str) -> str | None:
    patterns = (
        r"^(.{2,20}?)(?:是什么专业|是哪个专业|属于什么专业|属于哪个标准专业|属于哪个校内标准专业)[？?]?$",
        r"^(.{2,20}?)(?:的专业别名|对应的标准专业)[？?]?$",
        r"^用户所说的[“\"]?(.{2,20}?)[”\"]?[，,]?对应哪个(?:校内)?标准专业[？?]?$",
    )
    generic = {"这个专业", "那个专业", "该专业", "专业名称", "标准专业"}
    for pattern in patterns:
        match = re.search(pattern, message)
        if not match:
            continue
        value = match.group(1).strip().removesuffix("专业").strip()
        if value and value not in generic:
            return value
    return None


def extract_exam_score_condition(message: str, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    context = context or {}
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


def extract_student_status(message: str) -> str | None:
    mapping = {"新学生": "NEW", "已联系": "CONTACTED", "有意向": "INTERESTED", "已录取": "ADMITTED", "已报到": "ENROLLED", "已放弃": "ABANDONED"}
    for label, code in mapping.items():
        if label in message:
            return code
    return None


def extract_enrollment_filter(message: str) -> bool | None:
    if any(keyword in message for keyword in ("未报到", "没有报到", "尚未报到")):
        return False
    if "已报到" in message:
        return True
    return None


def extract_group_by(message: str) -> str | None:
    mapping = {"按专业": "major_name", "各专业": "major_name", "按省份": "province_name", "各省": "province_name", "按学院": "major_group", "各学院": "major_group", "按性别": "gender_name", "按科类": "subject_name", "按状态": "student_status", "按渠道": "channel_name", "按层次": "level_name", "各层次": "level_name", "按招生类型": "plan_type", "各招生类型": "plan_type", "按生源高中": "source_school_name", "各生源高中": "source_school_name"}
    for label, field in mapping.items():
        if label in message:
            return field
    return None


_PROVINCE_ALIASES = {
    "湘": "湖南", "粤": "广东", "鄂": "湖北", "苏": "江苏", "浙": "浙江",
    "鲁": "山东", "豫": "河南", "川": "四川", "渝": "重庆", "陕": "陕西",
    "皖": "安徽", "闽": "福建", "赣": "江西", "桂": "广西", "冀": "河北",
    "晋": "山西", "辽": "辽宁", "吉": "吉林", "黑": "黑龙江", "滇": "云南",
    "黔": "贵州", "甘": "甘肃", "琼": "海南",
}


def extract_province(message: str, known_provinces: list[str] | tuple[str, ...]) -> str | None:
    known = set(known_provinces)
    for name in known_provinces:
        if name == "专升本":
            continue
        if name in message:
            return name
    for alias, full in _PROVINCE_ALIASES.items():
        if alias in message and full in known:
            return full
    return None


def extract_major(message: str, known_majors: list[str] | tuple[str, ...]) -> str | None:
    matches = [
        name
        for name in known_majors
        if name != "专升本" and name in message
    ]
    return max(matches, key=len) if matches else None



