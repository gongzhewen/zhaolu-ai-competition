from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any


class SQLGuardError(ValueError):
    pass


_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|replace|drop|alter|truncate|create|grant|revoke|call|"
    r"load|outfile|infile|lock|unlock|set|use|transaction|commit|rollback|do|handler|"
    r"prepare|execute|deallocate)\b",
    re.IGNORECASE,
)
_DANGEROUS_FUNCTIONS = re.compile(
    r"\b(sleep|benchmark|get_lock|release_lock|load_file)\s*\(",
    re.IGNORECASE,
)
_SENSITIVE_COLUMNS = re.compile(
    r"\b(student_name|candidate_name|phone|mobile|id_card|id_number|address|contact|"
    r"candidate_no|student_no|email)\b",
    re.IGNORECASE,
)
_TABLE_PATTERN = re.compile(
    r"\b(?:FROM|JOIN)\s+((?:`?[A-Za-z_][A-Za-z0-9_]*`?\.)?`?[A-Za-z_][A-Za-z0-9_]*`?)",
    re.IGNORECASE,
)
_CTE_PATTERN = re.compile(r"\b(?:WITH|,)\s*`?([A-Za-z_][A-Za-z0-9_]*)`?\s+AS\s*\(", re.IGNORECASE)
_LIMIT_PATTERN = re.compile(r"\bLIMIT\s+(\d+)\b", re.IGNORECASE)


@dataclass(slots=True, frozen=True)
class SQLExecutionResult:
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    truncated: bool


def extract_sql(content: str) -> str:
    text_value = content.strip()
    fenced = re.search(r"```(?:sql|json)?\s*(.*?)```", text_value, re.IGNORECASE | re.DOTALL)
    if fenced:
        text_value = fenced.group(1).strip()
    if text_value.startswith("{"):
        try:
            payload = json.loads(text_value)
            if isinstance(payload, dict) and isinstance(payload.get("sql"), str):
                text_value = payload["sql"].strip()
        except json.JSONDecodeError:
            pass
    text_value = re.sub(r"^SQL\s*[:：]\s*", "", text_value, flags=re.IGNORECASE)
    return text_value.strip()


def _normalize_table_name(name: str) -> str:
    return ".".join(part.strip("`").lower() for part in name.split("."))


def validate_readonly_sql(
    sql: str,
    *,
    allowed_tables: set[str],
    max_rows: int = 200,
) -> str:
    text_value = extract_sql(sql).strip()
    if not text_value:
        raise SQLGuardError("SQL 为空")
    if "--" in text_value or "/*" in text_value or text_value.lstrip().startswith("#"):
        raise SQLGuardError("禁止使用 SQL 注释")
    if text_value.endswith(";"):
        text_value = text_value[:-1].rstrip()
    if ";" in text_value:
        raise SQLGuardError("禁止多语句 SQL")
    if not re.match(r"^(SELECT|WITH)\b", text_value, re.IGNORECASE):
        raise SQLGuardError("只允许 SELECT 或 WITH 查询")
    if _FORBIDDEN.search(text_value):
        raise SQLGuardError("SQL 含写操作或危险语句")
    if _DANGEROUS_FUNCTIONS.search(text_value):
        raise SQLGuardError("SQL 含危险函数")
    if _SENSITIVE_COLUMNS.search(text_value):
        raise SQLGuardError("SQL 引用敏感个人字段")
    if re.search(r"\bSELECT\s+\*", text_value, re.IGNORECASE):
        raise SQLGuardError("禁止 SELECT *，必须显式列出字段")

    cte_names = {match.group(1).lower() for match in _CTE_PATTERN.finditer(text_value)}
    referenced_tables = {
        _normalize_table_name(match.group(1))
        for match in _TABLE_PATTERN.finditer(text_value)
    }
    external_tables = {name for name in referenced_tables if name not in cte_names}
    if not external_tables:
        raise SQLGuardError("SQL 未引用允许的数据表")
    allowed = {_normalize_table_name(name) for name in allowed_tables}
    unauthorized = external_tables - allowed
    if unauthorized:
        raise SQLGuardError(f"SQL 引用非白名单表：{sorted(unauthorized)}")

    limit_match = _LIMIT_PATTERN.search(text_value)
    if limit_match:
        requested = int(limit_match.group(1))
        if requested > max_rows:
            text_value = (
                text_value[: limit_match.start(1)]
                + str(max_rows)
                + text_value[limit_match.end(1) :]
            )
    else:
        text_value = f"{text_value}\nLIMIT {max_rows}"
    return text_value


async def execute_readonly_sql(
    db,
    sql: str,
    *,
    allowed_tables: set[str],
    max_rows: int = 200,
    timeout_seconds: float = 10.0,
) -> SQLExecutionResult:
    guarded_sql = validate_readonly_sql(sql, allowed_tables=allowed_tables, max_rows=max_rows)
    try:
        result = await asyncio.wait_for(db.execute(_text(guarded_sql)), timeout=timeout_seconds)
    except asyncio.TimeoutError as exc:
        raise SQLGuardError("SQL 执行超时") from exc
    mappings = result.mappings().all()
    rows = [dict(row) for row in mappings[: max_rows + 1]]
    truncated = len(rows) > max_rows
    rows = rows[:max_rows]
    columns = list(rows[0].keys()) if rows else list(result.keys())
    return SQLExecutionResult(sql=guarded_sql, columns=columns, rows=rows, truncated=truncated)


def _text(sql: str):
    from app.core.text import text

    return text(sql)


_METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "plan_count": ("plan_count", "plan_total", "total_plan", "planned_count", "plans"),
    "admitted_count": ("admitted_count", "admission_count", "total_admitted", "admitted"),
    "completion_rate": ("completion_rate", "plan_completion_rate", "rate"),
    "candidate_count": ("candidate_count", "candidates", "student_count"),
    "enrolled_count": ("enrolled_count", "reported_count", "registered_count"),
    "enrollment_rate": ("enrollment_rate", "reporting_rate", "arrival_rate"),
    "consultation_count": ("consultation_count", "consultations"),
    "converted_count": ("converted_count", "conversions"),
    "conversion_rate": ("conversion_rate", "conversion"),
    "lost_after_admission": ("lost_after_admission", "lost_count", "melted_count"),
    "choice_count": ("choice_count", "major_choice_count", "choices"),
    "record_count": ("record_count", "score_record_count"),
    "total_students": ("total_students", "student_count", "count"),
    "data_points": ("data_points", "record_count", "count"),
    "matched": ("matched", "match_count", "count"),
}


def metrics_from_rows(rows: list[dict[str, Any]], expected_metrics: dict[str, Any]) -> dict[str, Any]:
    if not rows:
        return {}
    row = rows[0]
    lowered = {str(key).lower(): value for key, value in row.items()}
    metrics: dict[str, Any] = {}
    for metric_name in expected_metrics:
        value = None
        for alias in (metric_name, *_METRIC_ALIASES.get(metric_name, ())):
            if alias.lower() in lowered:
                value = lowered[alias.lower()]
                break
        if value is not None:
            metrics[metric_name] = value
    return metrics
