from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterable

from .contracts import EvidenceCertificate, PlanCandidate, PlanConsistency, SemanticSlots, ToolCall


_NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")


def _walk_scalars(value: Any) -> Iterable[Any]:
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk_scalars(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _walk_scalars(item)
    else:
        yield value


def _number_tokens(value: Any) -> set[Decimal]:
    text_value = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    tokens: set[Decimal] = set()
    for raw in _NUMBER_PATTERN.findall(text_value):
        try:
            tokens.add(Decimal(raw).normalize())
        except InvalidOperation:
            continue
    return tokens


def _decimal_places(raw: str) -> int:
    return len(raw.split(".", 1)[1]) if "." in raw else 0


def _answer_tokens(answer: str) -> list[tuple[Decimal, int]]:
    tokens: list[tuple[Decimal, int]] = []
    for raw in _NUMBER_PATTERN.findall(answer):
        try:
            tokens.append((Decimal(raw).normalize(), _decimal_places(raw)))
        except InvalidOperation:
            continue
    return tokens


def _token_matches(answer_number: Decimal, answer_places: int, evidence_numbers: set[Decimal]) -> bool:
    if answer_number in evidence_numbers:
        return True
    if answer_places > 12:
        return False
    quantum = Decimal("1").scaleb(-answer_places)
    for evidence_number in evidence_numbers:
        try:
            rounded = evidence_number.quantize(quantum, rounding=ROUND_HALF_UP)
        except InvalidOperation:
            continue
        if rounded == answer_number:
            return True
    return False


def verify_numeric_claims(answer: str, evidence_payload: Any) -> dict[str, Any]:
    answer_numbers = _answer_tokens(answer)
    evidence_numbers = _number_tokens(evidence_payload)
    unsupported = [
        str(number)
        for number, places in answer_numbers
        if not _token_matches(number, places, evidence_numbers)
    ]
    coverage = 1.0 if not answer_numbers else round(1.0 - len(unsupported) / len(answer_numbers), 4)
    return {
        "coverage": max(0.0, coverage),
        "answer_number_count": len(answer_numbers),
        "unsupported_numbers": list(dict.fromkeys(unsupported)),
        "supported": not unsupported,
    }


def _count_missing(value: Any) -> int:
    if isinstance(value, dict):
        return sum(_count_missing(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return sum(_count_missing(item) for item in value)
    return 1 if value is None else 0


def _row_count(result: dict[str, Any]) -> int | None:
    table = result.get("table")
    if isinstance(table, dict) and isinstance(table.get("rows"), list):
        return len(table["rows"])
    metrics = result.get("metrics")
    if isinstance(metrics, dict):
        for key in ("row_count", "data_points", "student_count", "province_count", "major_count", "matched"):
            value = metrics.get(key)
            if isinstance(value, (int, float)):
                return int(value)
        if metrics:
            return 1
    return None


def _year_range(result: dict[str, Any], params: dict[str, Any]) -> tuple[int | None, int | None]:
    year = params.get("year")
    if isinstance(year, int):
        return year, year
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    years = metrics.get("years")
    if isinstance(years, list) and years:
        numeric_years = [int(item) for item in years if isinstance(item, (int, float))]
        if numeric_years:
            return min(numeric_years), max(numeric_years)
    start = metrics.get("start_year")
    end = metrics.get("end_year")
    if isinstance(start, (int, float)) and isinstance(end, (int, float)):
        return int(start), int(end)
    metric_year = metrics.get("year") or metrics.get("year_no")
    if isinstance(metric_year, (int, float)):
        return int(metric_year), int(metric_year)
    return None, None


def _result_value(result: dict[str, Any]) -> dict[str, Any]:
    metrics = result.get("metrics")
    if isinstance(metrics, dict) and metrics:
        return {key: value for key, value in metrics.items() if not isinstance(value, (list, dict))}
    table = result.get("table")
    if isinstance(table, dict) and isinstance(table.get("rows"), list):
        return {"row_count": len(table["rows"])}
    return {}


def _data_sources(result: dict[str, Any]) -> tuple[str, ...]:
    sources = result.get("data_sources") or []
    values: list[str] = []
    for item in sources:
        if isinstance(item, dict):
            table = str(item.get("table") or "").strip()
            metric = str(item.get("metric") or "").strip()
            if table and metric:
                values.append(f"{table}:{metric}")
            elif table:
                values.append(table)
        elif item:
            values.append(str(item))
    return tuple(dict.fromkeys(values))


def build_evidence_certificates(
    calls: list[ToolCall],
    results: list[dict[str, Any]],
    *,
    slots: SemanticSlots | None = None,
    permission_scope: str = "school_scope",
) -> list[EvidenceCertificate]:
    remaining = list(enumerate(results))
    certificates: list[EvidenceCertificate] = []
    for call_index, call in enumerate(calls):
        match_position = next(
            (index for index, (_, result) in enumerate(remaining) if result.get("tool") == call.name),
            None,
        )
        if match_position is None and call_index < len(results):
            match_position = 0
        result = remaining.pop(match_position)[1] if match_position is not None else {}
        sources = _data_sources(result)
        row_count = _row_count(result)
        result_value = _result_value(result)
        year_start, year_end = _year_range(result, call.params)
        scope = "super_admin" if call.name == "student_lookup" else permission_scope
        completeness = 0.0
        if sources:
            completeness += 0.35
        if result_value:
            completeness += 0.30
        if row_count is not None:
            completeness += 0.15
        if year_start is not None or slots is None:
            completeness += 0.10
        if scope:
            completeness += 0.10
        filters = {
            key: value
            for key, value in call.params.items()
            if key not in {"query", "user", "school_id", "can_lookup_students"} and value is not None
        }
        certificates.append(
            EvidenceCertificate(
                tool_name=call.name,
                data_source=sources,
                year_range=(year_start, year_end),
                filters=filters,
                canonical_major=str(call.params.get("major") or (slots.major if slots else "") or "") or None,
                aggregation=slots.aggregation if slots else None,
                row_count=row_count,
                result_value=result_value,
                missing_value_count=_count_missing(result_value),
                permission_scope=scope,
                completeness=round(min(1.0, completeness), 4),
            )
        )
    return certificates


def certificate_dict(certificate: EvidenceCertificate) -> dict[str, Any]:
    return {
        "tool_name": certificate.tool_name,
        "data_source": list(certificate.data_source),
        "year_range": list(certificate.year_range),
        "filters": certificate.filters,
        "canonical_major": certificate.canonical_major,
        "aggregation": certificate.aggregation,
        "row_count": certificate.row_count,
        "result_value": certificate.result_value,
        "missing_value_count": certificate.missing_value_count,
        "permission_scope": certificate.permission_scope,
        "completeness": certificate.completeness,
    }


def _canonical_value(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float, Decimal)):
        try:
            return format(Decimal(str(value)).normalize(), "f")
        except InvalidOperation:
            return str(value)
    if isinstance(value, dict):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple, set)):
        normalized = [_canonical_value(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, default=str),
        )
    if isinstance(value, str):
        return value.strip()
    return value


def _canonical_table(table: Any) -> Any:
    if not isinstance(table, dict):
        return _canonical_value(table)
    columns = [str(item).strip() for item in (table.get("columns") or [])]
    rows = table.get("rows")
    if columns and isinstance(rows, list) and all(
        isinstance(row, (list, tuple)) and len(row) == len(columns) for row in rows
    ):
        normalized_rows = [
            {
                column: _canonical_value(value)
                for column, value in zip(columns, row, strict=True)
            }
            for row in rows
        ]
        return {
            "columns": sorted(columns),
            "rows": sorted(
                normalized_rows,
                key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, default=str),
            ),
        }
    return _canonical_value(table)


def _canonical_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "metrics": _canonical_value(result.get("metrics") or {}),
        "table": _canonical_table(result.get("table")),
        "data_sources": _canonical_value(result.get("data_sources") or []),
    }


def _decimal_or_none(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _flatten_mapping(value: Any, prefix: str = "") -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(_flatten_mapping(item, child))
    else:
        flattened[prefix or "value"] = value
    return flattened


def _metrics_similarity(primary: dict[str, Any], secondary: dict[str, Any]) -> float:
    left = _flatten_mapping(primary.get("metrics") or {})
    right = _flatten_mapping(secondary.get("metrics") or {})
    if not left and not right:
        return 1.0
    keys = sorted(set(left) | set(right))
    scores: list[float] = []
    for key in keys:
        if key not in left or key not in right:
            scores.append(0.0)
            continue
        left_number = _decimal_or_none(left[key])
        right_number = _decimal_or_none(right[key])
        if left_number is not None and right_number is not None:
            denominator = max(abs(left_number), abs(right_number), Decimal("1e-12"))
            difference = abs(left_number - right_number) / denominator
            scores.append(max(0.0, 1.0 - float(difference)))
        else:
            scores.append(1.0 if _canonical_value(left[key]) == _canonical_value(right[key]) else 0.0)
    return sum(scores) / max(1, len(scores))


def _row_set(table: dict[str, Any]) -> set[str]:
    rows = table.get("rows")
    if not isinstance(rows, list):
        return set()
    return {
        json.dumps(_canonical_value(row), ensure_ascii=False, sort_keys=True, default=str)
        for row in rows
    }


def _table_similarity(primary: dict[str, Any], secondary: dict[str, Any]) -> float:
    left = primary.get("table")
    right = secondary.get("table")
    if left is None and right is None:
        return 1.0
    if not isinstance(left, dict) or not isinstance(right, dict):
        return 0.0
    if _canonical_table(left) == _canonical_table(right):
        return 1.0
    left_columns = {str(item).strip() for item in (left.get("columns") or [])}
    right_columns = {str(item).strip() for item in (right.get("columns") or [])}
    column_score = (
        len(left_columns & right_columns) / len(left_columns | right_columns)
        if left_columns or right_columns
        else 1.0
    )
    left_rows = _row_set(left)
    right_rows = _row_set(right)
    row_score = (
        len(left_rows & right_rows) / len(left_rows | right_rows)
        if left_rows or right_rows
        else 1.0
    )
    return 0.3 * column_score + 0.7 * row_score


def _source_similarity(primary: dict[str, Any], secondary: dict[str, Any]) -> float:
    left = {json.dumps(_canonical_value(item), ensure_ascii=False, sort_keys=True, default=str) for item in (primary.get("data_sources") or [])}
    right = {json.dumps(_canonical_value(item), ensure_ascii=False, sort_keys=True, default=str) for item in (secondary.get("data_sources") or [])}
    if not left and not right:
        return 1.0
    return len(left & right) / max(1, len(left | right))


def _single_result_similarity(primary: dict[str, Any], secondary: dict[str, Any]) -> float:
    components: list[float] = []
    if primary.get("metrics") or secondary.get("metrics"):
        components.append(_metrics_similarity(primary, secondary))
    if primary.get("table") is not None or secondary.get("table") is not None:
        components.append(_table_similarity(primary, secondary))
    if primary.get("data_sources") or secondary.get("data_sources"):
        components.append(_source_similarity(primary, secondary))
    if not components:
        return 1.0 if _canonical_result(primary) == _canonical_result(secondary) else 0.0
    return sum(components) / len(components)


def result_similarity(
    primary_results: list[dict[str, Any]],
    secondary_results: list[dict[str, Any]],
) -> float:
    if not primary_results or not secondary_results:
        return 0.0
    remaining = list(secondary_results)
    scores: list[float] = []
    for primary in primary_results:
        tool_name = str(primary.get("tool") or "")
        match_index = next(
            (index for index, item in enumerate(remaining) if str(item.get("tool") or "") == tool_name),
            None,
        )
        if match_index is None:
            scores.append(0.0)
            continue
        secondary = remaining.pop(match_index)
        scores.append(_single_result_similarity(primary, secondary))
    tool_coverage = len(primary_results) / max(len(primary_results), len(secondary_results))
    result_coverage = 1.0 - len(remaining) / max(1, len(secondary_results))
    coverage = tool_coverage * result_coverage
    return round(max(0.0, min(1.0, (sum(scores) / len(scores)) * coverage)), 6)


def compare_plan_results(
    primary_results: list[dict[str, Any]],
    secondary_results: list[dict[str, Any]],
    *,
    threshold: float = 1.0,
) -> tuple[bool, float, list[str]]:
    if not primary_results or not secondary_results:
        return False, 0.0, ["至少一个计划没有返回结果"]
    similarity = result_similarity(primary_results, secondary_results)
    if similarity >= threshold:
        return True, similarity, [f"两个计划的规范化结果相似度 {similarity:.4f} >= {threshold:.4f}"]
    return False, similarity, [f"两个计划的规范化结果相似度 {similarity:.4f} < {threshold:.4f}"]


def _call_signature(call: ToolCall) -> str:
    return json.dumps(
        {"name": call.name, "params": call.params},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def build_plan_consistency(
    primary: PlanCandidate,
    secondary: PlanCandidate | None,
    *,
    primary_results: list[dict[str, Any]],
    secondary_results: list[dict[str, Any]],
    triggered: bool,
    threshold: float = 1.0,
) -> PlanConsistency:
    if not triggered:
        return PlanConsistency(
            triggered=False,
            primary=primary.name,
            secondary=None,
            consistent=True,
            score=1.0,
            reasons=["简单问题采用单计划快速路径"],
        )
    if secondary is None:
        return PlanConsistency(
            triggered=True,
            primary=primary.name,
            secondary=None,
            consistent=False,
            score=0.5,
            reasons=["高风险问题没有生成第二计划"],
        )
    primary_signature = [_call_signature(call) for call in primary.tool_calls]
    secondary_signature = [_call_signature(call) for call in secondary.tool_calls]
    if primary_signature == secondary_signature:
        return PlanConsistency(
            triggered=True,
            primary=primary.name,
            secondary=secondary.name,
            consistent=True,
            score=1.0,
            reasons=["两个候选计划在工具与参数层面一致"],
        )
    if secondary_results:
        consistent, score, reasons = compare_plan_results(
            primary_results,
            secondary_results,
            threshold=threshold,
        )
    else:
        consistent, score, reasons = False, 0.0, ["第二计划未执行"]
    return PlanConsistency(
        triggered=True,
        primary=primary.name,
        secondary=secondary.name,
        consistent=consistent,
        score=score,
        reasons=reasons,
    )
