import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

SUPPORTED_SUFFIXES = {".csv", ".xlsx", ".xls"}


@dataclass
class ParsedTable:
    headers: list[str]
    rows: list[dict[str, Any]]
    encoding: str | None = None
    sheet_name: str | None = None


def _cell_to_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return str(value).strip() if isinstance(value, str) else value


def _is_empty_row(values: list[Any] | tuple[Any, ...]) -> bool:
    return all(value is None or str(value).strip() == "" for value in values)


def _normalize_headers(raw_headers: list[Any]) -> list[str]:
    headers: list[str] = []
    counts: dict[str, int] = {}
    for index, raw in enumerate(raw_headers, start=1):
        base = str(raw).strip() if raw is not None and str(raw).strip() else f"column_{index}"
        count = counts.get(base, 0) + 1
        counts[base] = count
        headers.append(base if count == 1 else f"{base}_{count}")
    if not headers:
        raise ValueError("文件中未识别到表头")
    return headers


def _rows_from_matrix(
    headers: list[str],
    matrix: list[list[Any]],
    max_rows: int | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_values in matrix:
        if _is_empty_row(raw_values):
            continue
        padded = list(raw_values) + [None] * max(0, len(headers) - len(raw_values))
        row = {
            header: _cell_to_value(padded[index]) if index < len(padded) else ""
            for index, header in enumerate(headers)
        }
        rows.append(row)
        if max_rows is not None and len(rows) >= max_rows:
            break
    return rows


def _parse_csv(path: Path, max_rows: int | None) -> ParsedTable:
    raw = path.read_bytes()
    encoding = "utf-8-sig"
    for candidate in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            text = raw.decode(candidate)
            encoding = candidate
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("CSV 编码无法识别，请转换为 UTF-8 或 GB18030")

    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    reader = csv.reader(io.StringIO(text), dialect)
    try:
        raw_headers = next(reader)
    except StopIteration as exc:
        raise ValueError("CSV 文件为空") from exc

    headers = _normalize_headers(raw_headers)
    matrix: list[list[Any]] = []
    for row in reader:
        if _is_empty_row(row):
            continue
        matrix.append(row)
        if max_rows is not None and len(matrix) >= max_rows:
            break

    return ParsedTable(
        headers=headers,
        rows=_rows_from_matrix(headers, matrix, max_rows=max_rows),
        encoding=encoding,
    )


def _parse_xlsx(path: Path, max_rows: int | None) -> ParsedTable:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise ValueError("服务器未安装 openpyxl，无法解析 xlsx 文件") from exc

    workbook = load_workbook(filename=path, read_only=True, data_only=True)
    try:
        sheet = workbook.active
        rows = sheet.iter_rows(values_only=True)
        try:
            raw_headers = list(next(rows))
        except StopIteration as exc:
            raise ValueError("Excel 文件为空") from exc

        headers = _normalize_headers(raw_headers)
        matrix: list[list[Any]] = []
        for row in rows:
            values = list(row)
            if _is_empty_row(values):
                continue
            matrix.append(values)
            if max_rows is not None and len(matrix) >= max_rows:
                break

        return ParsedTable(
            headers=headers,
            rows=_rows_from_matrix(headers, matrix, max_rows=max_rows),
            sheet_name=sheet.title,
        )
    finally:
        workbook.close()


def _parse_xls(path: Path, max_rows: int | None) -> ParsedTable:
    try:
        import xlrd
    except ImportError as exc:
        raise ValueError("服务器未安装 xlrd，无法解析 xls 文件") from exc

    workbook = xlrd.open_workbook(str(path), on_demand=True)
    try:
        sheet = workbook.sheet_by_index(0)
        if sheet.nrows == 0:
            raise ValueError("Excel 文件为空")
        raw_headers = [sheet.cell_value(0, col) for col in range(sheet.ncols)]
        headers = _normalize_headers(raw_headers)
        matrix: list[list[Any]] = []
        for row_index in range(1, sheet.nrows):
            values = [sheet.cell_value(row_index, col) for col in range(sheet.ncols)]
            if _is_empty_row(values):
                continue
            matrix.append(values)
            if max_rows is not None and len(matrix) >= max_rows:
                break
        return ParsedTable(
            headers=headers,
            rows=_rows_from_matrix(headers, matrix, max_rows=max_rows),
            sheet_name=sheet.name,
        )
    finally:
        workbook.release_resources()


def parse_table(path: Path, max_rows: int | None = None) -> ParsedTable:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _parse_csv(path, max_rows=max_rows)
    if suffix == ".xlsx":
        return _parse_xlsx(path, max_rows=max_rows)
    if suffix == ".xls":
        return _parse_xls(path, max_rows=max_rows)
    raise ValueError("仅支持 csv、xlsx、xls 文件")
