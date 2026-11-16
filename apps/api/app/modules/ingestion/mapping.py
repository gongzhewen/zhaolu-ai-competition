from dataclasses import dataclass, field
from typing import Any

TARGET_FIELDS = [
    "year",
    "province",
    "batch",
    "subject",
    "major_code",
    "major_name",
    "plan_type",
    "plan_count",
    "admitted_count",
    "min_score",
    "avg_score",
    "max_score",
    "min_rank_no",
    "candidate_key",
    "student_name",
    "score",
    "rank_no",
    "volunteer_order",
    "channel",
    "consultation_type",
    "status",
    "contacted_at",
    "converted",
    "admit_type",
    "is_enrolled",
    "enrolled_at",
    "remark",
    "tuition",
    "source_type",
    "data_version",
]

FIELD_ALIASES: dict[str, list[str]] = {
    "year": ["year", "year_no", "年份", "招生年份", "录取年份", "年度"],
    "province": ["province", "province_name", "省份", "生源地", "生源省份", "录取省份"],
    "batch": ["batch", "batch_name", "批次", "录取批次"],
    "subject": ["subject", "subject_name", "科类", "选科", "选考科目", "招生科类"],
    "major_code": ["major_code", "专业代码", "院校专业代码", "招生专业代码"],
    "major_name": ["major", "major_name", "major-name", "major name", "专业", "专业名", "专业名称", "录取专业", "录取专业名", "录取专业名称", "招生专业"],
    "plan_type": ["plan_type", "计划类型", "招生类型", "计划性质"],
    "plan_count": ["plan_count", "计划数", "招生计划", "招生计划数", "计划人数"],
    "admitted_count": ["admitted_count", "录取数", "录取人数", "实际录取数"],
    "min_score": ["min_score", "最低分", "最低录取分", "录取最低分"],
    "avg_score": ["avg_score", "平均分", "录取平均分"],
    "max_score": ["max_score", "最高分", "录取最高分"],
    "min_rank_no": ["min_rank_no", "最低位次", "最低录取位次", "最低排位", "录取最低位次"],
    "candidate_key": ["candidate_key", "考生编号", "考生号", "报名号", "考生ID", "candidate_id"],
    "student_name": ["student_name", "姓名", "考生姓名", "学生姓名"],
    "score": ["score", "成绩", "高考成绩", "总分", "投档分"],
    "rank_no": ["rank_no", "位次", "排位", "全省位次"],
    "volunteer_order": ["volunteer_order", "志愿顺序", "专业志愿", "志愿号"],
    "channel": ["channel", "channel_name", "渠道", "招生渠道", "来源渠道"],
    "consultation_type": ["consultation_type", "咨询类型", "咨询方式"],
    "status": ["status", "状态", "咨询状态"],
    "contacted_at": ["contacted_at", "咨询时间", "联系时间"],
    "converted": ["converted", "是否转化", "是否报名", "转化结果"],
    "admit_type": ["admit_type", "录取类型", "录取方式"],
    "is_enrolled": ["is_enrolled", "是否报到", "报到状态", "是否入学"],
    "enrolled_at": ["enrolled_at", "报到日期", "报到时间", "入学日期", "入学时间"],
    "remark": ["remark", "备注", "说明", "报到说明"],
    "tuition": ["tuition", "学费", "收费标准"],
    "source_type": ["source_type", "数据来源", "来源类型"],
    "data_version": ["data_version", "数据版本", "版本号"],
}

REQUIRED_FIELDS: dict[str, set[str]] = {
    "plan": {"year", "province", "major_name", "plan_count"},
    "admission": {"year", "province", "major_name"},
    "score_line": {"year", "province"},
    "consultation": {"year", "province"},
    "enrollment": {"year"},
}

def infer_data_type(selected_data_type: str, mapping: dict[str, str | None]) -> str:
    targets = {
        normalize_target_field(target)
        for target in mapping.values()
        if normalize_target_field(target)
    }
    has_major = "major_name" in targets
    has_plan = "plan_count" in targets
    has_candidate = bool({"candidate_key", "student_name"} & targets)
    has_admission_value = bool({"score", "rank_no"} & targets)
    has_score_line_value = bool({"min_score", "min_rank_no"} & targets)
    has_enrollment = bool({"is_enrolled", "enrolled_at"} & targets)
    has_consultation = bool({"consultation_type", "status", "converted"} & targets)

    if selected_data_type in {"plan", "admission"} and has_score_line_value and not has_major and not has_admission_value:
        return "score_line"
    if selected_data_type in {"plan", "admission"} and has_enrollment and has_candidate and not has_admission_value and not has_plan:
        return "enrollment"
    if selected_data_type in {"plan", "admission"} and has_consultation and not has_major and not has_plan:
        return "consultation"
    if selected_data_type in {"score_line", "consultation"} and has_major and has_plan:
        return "plan"
    if selected_data_type == "score_line" and has_major and has_admission_value:
        return "admission"
    return selected_data_type


TARGET_TABLES = {
    "plan": "fact.plan",
    "admission": "fact.admission_record",
    "score_line": "fact.score_line",
    "consultation": "fact.consultation",
    "enrollment": "fact.enrollment_status",
}


@dataclass
class ValidatedRow:
    row_no: int
    raw_data: dict[str, Any]
    normalized_data: dict[str, Any]
    errors: list[str] = field(default_factory=list)


def normalize_header(value: str) -> str:
    return (
        str(value)
        .strip()
        .lower()
        .replace(" ", "")
        .replace("_", "")
        .replace("-", "")
        .replace("（", "")
        .replace("）", "")
        .replace("(", "")
        .replace(")", "")
    )


def normalize_target_field(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    return normalized or None


def auto_map_headers(headers: list[str]) -> tuple[dict[str, str | None], dict[str, float]]:
    mapping: dict[str, str | None] = {}
    confidence: dict[str, float] = {}
    normalized_aliases: dict[str, str] = {}

    for target, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            normalized_aliases[normalize_header(alias)] = target

    unresolved: list[str] = []
    for header in headers:
        normalized = normalize_header(header)
        target = normalized_aliases.get(normalized)
        if target:
            mapping[header] = target
            confidence[header] = 1.0
        else:
            mapping[header] = None
            confidence[header] = 0.0
            unresolved.append(header)

    for header in unresolved:
        normalized = normalize_header(header)
        best_target: str | None = None
        best_score = 0.0
        for alias, target in normalized_aliases.items():
            if len(alias) >= 2 and (alias in normalized or normalized in alias):
                score = min(len(alias), len(normalized)) / max(len(alias), len(normalized))
                if score > best_score:
                    best_target = target
                    best_score = score
        if best_target and best_score >= 0.5:
            mapping[header] = best_target
            confidence[header] = round(best_score, 2)

    return mapping, confidence


def validate_mapping(data_type: str, mapping: dict[str, str | None]) -> None:
    if data_type not in REQUIRED_FIELDS:
        raise ValueError(f"不支持的数据类型：{data_type}")

    targets = [normalize_target_field(target) for target in mapping.values() if target]
    duplicate_targets = {target for target in targets if target and targets.count(target) > 1}
    if duplicate_targets:
        raise ValueError(f"字段映射重复：{', '.join(sorted(duplicate_targets))}")



def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _to_int(value: Any) -> int | None:
    text = _clean_text(value)
    if text is None:
        return None
    try:
        return int(float(text.replace(",", "")))
    except ValueError:
        raise ValueError(f"无法转换为整数：{text}") from None


def _to_float(value: Any) -> float | None:
    text = _clean_text(value)
    if text is None:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        raise ValueError(f"无法转换为数字：{text}") from None


def _to_bool(value: Any) -> bool | None:
    text = _clean_text(value)
    if text is None:
        return None
    normalized = text.lower()
    if normalized in {"true", "1", "是", "已报到", "已报名", "已转化", "成功"}:
        return True
    if normalized in {"false", "0", "否", "未报到", "未报名", "未转化", "失败"}:
        return False
    raise ValueError(f"无法转换为布尔值：{text}")


def normalize_row(raw: dict[str, Any], mapping: dict[str, str | None]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for source_field, target_field in mapping.items():
        normalized_target = normalize_target_field(target_field)
        if not normalized_target:
            continue
        result[normalized_target] = raw.get(source_field)
    return result


def _validate_common(row: dict[str, Any], errors: list[str]) -> None:
    year = _to_int(row.get("year"))
    if year is None:
        errors.append("year 不能为空")
    elif year < 2000 or year > 2100:
        errors.append("year 超出合理范围")

    if row.get("min_score") is not None:
        score = _to_float(row.get("min_score"))
        if score is not None and not 0 <= score <= 1000:
            errors.append("min_score 超出合理范围")


def validate_rows(
    data_type: str,
    raw_rows: list[dict[str, Any]],
    mapping: dict[str, str | None],
) -> list[ValidatedRow]:
    validate_mapping(data_type, mapping)
    validated: list[ValidatedRow] = []

    for index, raw in enumerate(raw_rows, start=2):
        errors: list[str] = []
        row = normalize_row(raw, mapping)

        try:
            _validate_common(row, errors)

            if data_type == "plan":
                row["year"] = _to_int(row.get("year"))
                row["plan_count"] = _to_int(row.get("plan_count"))
                row["admitted_count"] = _to_int(row.get("admitted_count"))
                row["tuition"] = _to_float(row.get("tuition"))
                if row.get("plan_count") is None:
                    errors.append("plan_count 不能为空")
                elif row["plan_count"] < 0:
                    errors.append("plan_count 不能为负数")
                for field in ("province", "major_name"):
                    if not _clean_text(row.get(field)):
                        errors.append(f"{field} 不能为空")

            elif data_type == "admission":
                row["year"] = _to_int(row.get("year"))
                row["score"] = _to_float(row.get("score"))
                row["rank_no"] = _to_int(row.get("rank_no"))
                row["volunteer_order"] = _to_int(row.get("volunteer_order"))
                row["is_enrolled"] = _to_bool(row.get("is_enrolled"))
                if row.get("score") is None and row.get("rank_no") is None:
                    errors.append("score 和 rank_no 至少填写一个")
                if row.get("score") is not None and not 0 <= row["score"] <= 1000:
                    errors.append("score 超出合理范围")
                if row.get("rank_no") is not None and row["rank_no"] <= 0:
                    errors.append("rank_no 必须大于 0")
                for field in ("province", "major_name"):
                    if not _clean_text(row.get(field)):
                        errors.append(f"{field} 不能为空")

            elif data_type == "score_line":
                row["year"] = _to_int(row.get("year"))
                row["min_score"] = _to_float(row.get("min_score"))
                row["min_rank_no"] = _to_int(row.get("min_rank_no"))
                if row.get("min_score") is None and row.get("min_rank_no") is None:
                    errors.append("min_score 和 min_rank_no 至少填写一个")
                if row.get("min_score") is not None and not 0 <= row["min_score"] <= 1000:
                    errors.append("min_score 超出合理范围")
                if row.get("min_rank_no") is not None and row["min_rank_no"] <= 0:
                    errors.append("min_rank_no 必须大于 0")
                if not _clean_text(row.get("province")):
                    errors.append("province 不能为空")

            elif data_type == "consultation":
                row["year"] = _to_int(row.get("year"))
                row["converted"] = _to_bool(row.get("converted"))
                if not _clean_text(row.get("province")):
                    errors.append("province 不能为空")

            elif data_type == "enrollment":
                row["year"] = _to_int(row.get("year"))
                row["is_enrolled"] = _to_bool(row.get("is_enrolled"))
                if row.get("year") is None:
                    errors.append("year 不能为空")
                if row.get("is_enrolled") is None:
                    errors.append("是否报到不能为空，支持 是/否、已报到/未报到、1/0")
                if not _clean_text(row.get("candidate_key")) and not _clean_text(row.get("student_name")):
                    errors.append("考生号和姓名至少填写一个")

            for key, value in list(row.items()):
                if isinstance(value, str):
                    row[key] = _clean_text(value)

        except ValueError as exc:
            errors.append(str(exc))

        validated.append(ValidatedRow(row_no=index, raw_data=raw, normalized_data=row, errors=errors))

    _mark_duplicates(data_type, validated)
    return validated


def _duplicate_key(data_type: str, row: dict[str, Any]) -> tuple[Any, ...] | None:
    if data_type == "plan":
        return (
            row.get("year"),
            row.get("province"),
            row.get("batch"),
            row.get("subject"),
            row.get("major_name"),
            row.get("plan_type"),
        )
    if data_type == "admission":
        if row.get("candidate_key"):
            return (row.get("candidate_key"),)
        return (
            row.get("year"),
            row.get("province"),
            row.get("major_name"),
            row.get("score"),
            row.get("rank_no"),
            row.get("volunteer_order"),
        )
    if data_type == "score_line":
        return (
            row.get("year"),
            row.get("province"),
            row.get("batch"),
            row.get("subject"),
            row.get("major_name"),
        )
    if data_type == "enrollment":
        if row.get("candidate_key"):
            return (row.get("year"), row.get("candidate_key"))
        return (row.get("year"), row.get("student_name"))
    return None


def _mark_duplicates(data_type: str, rows: list[ValidatedRow]) -> None:
    seen: dict[tuple[Any, ...], int] = {}
    for row in rows:
        if row.errors:
            continue
        key = _duplicate_key(data_type, row.normalized_data)
        if key is None or all(value is None for value in key):
            continue
        first_row = seen.get(key)
        if first_row is None:
            seen[key] = row.row_no
        else:
            row.errors.append(f"与第 {first_row} 行重复")
