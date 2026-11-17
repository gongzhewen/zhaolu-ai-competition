from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .schemas import ResultExportRequest

_MEDIA_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "md": "text/markdown; charset=utf-8",
    "json": "application/json; charset=utf-8",
}

_SENSITIVE_MARKERS = (
    "手机号",
    "身份证",
    "联系方式",
    "家庭住址",
    "考生号",
    "准考证号",
    "姓名",
    "联系电话",
)


class ExportDataError(ValueError):
    pass


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _safe_filename(request: ResultExportRequest) -> str:
    raw = request.filename or request.title or "分析结果"
    stem = re.sub(r'[\\/:*?"<>|\\r\\n]+', "_", raw).strip(" ._")
    if not stem:
        stem = "分析结果"
    return f"{stem[:80]}_{datetime.now():%Y%m%d_%H%M%S}.{request.format}"


def _rows_for_csv(request: ResultExportRequest) -> tuple[list[str], list[list[Any]]]:
    if request.table:
        return request.table.columns, request.table.rows
    if request.metrics:
        return ["指标", "数值"], [[key, value] for key, value in request.metrics.items()]
    return ["项目", "内容"], [
        ["标题", request.title],
        ["问题", request.question or ""],
        ["回答", request.answer or ""],
    ]


def _validate_content(request: ResultExportRequest) -> None:
    columns = request.table.columns if request.table else []
    if any(marker in column for marker in _SENSITIVE_MARKERS for column in columns):
        raise ExportDataError("聚合结果导出不允许包含学生敏感个人字段")

    for row in request.table.rows if request.table else []:
        for value in row:
            text_value = _text(value)
            if re.search(r"(?<!\\d)1[3-9]\\d{9}(?!\\d)", text_value):
                raise ExportDataError("导出结果疑似包含手机号")
            if re.search(r"\\b\\d{17}[\\dXx]\\b", text_value):
                raise ExportDataError("导出结果疑似包含身份证号")


def _build_json(request: ResultExportRequest) -> bytes:
    payload = request.model_dump(mode="json")
    payload["generated_at"] = datetime.now().isoformat(timespec="seconds")
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _build_csv(request: ResultExportRequest) -> bytes:
    columns, rows = _rows_for_csv(request)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    writer.writerows(rows)
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


def _build_markdown(request: ResultExportRequest) -> bytes:
    lines = [
        f"# {request.title}",
        "",
        f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 结果类型：{request.kind}",
    ]
    if request.question:
        lines.extend(["", "## 用户问题", "", request.question])
    if request.answer:
        lines.extend(["", "## 分析结论", "", request.answer])
    if request.metrics:
        lines.extend(["", "## 关键指标", "", "| 指标 | 数值 |", "| --- | --- |"])
        lines.extend(f"| {key} | {_text(value)} |" for key, value in request.metrics.items())
    for section in request.sections:
        lines.extend(["", f"## {section.title}", "", section.text])
    if request.table:
        lines.extend(
            [
                "",
                "## 数据明细",
                "",
                "| " + " | ".join(request.table.columns) + " |",
                "| " + " | ".join("---" for _ in request.table.columns) + " |",
            ]
        )
        lines.extend(
            "| " + " | ".join(_text(value).replace("|", "\\|") for value in row) + " |"
            for row in request.table.rows
        )
    if request.metadata:
        lines.extend(
            [
                "",
                "## 导出元数据",
                "",
                "```json",
                json.dumps(request.metadata, ensure_ascii=False, indent=2, default=str),
                "```",
            ]
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def _build_xlsx(request: ResultExportRequest) -> bytes:
    workbook = Workbook()
    summary = workbook.active
    summary.title = "概览"
    summary["A1"] = request.title
    summary["A1"].font = Font(size=18, bold=True, color="123A63")
    summary["A2"] = "生成时间"
    summary["B2"] = datetime.now().isoformat(timespec="seconds")
    summary["A3"] = "结果类型"
    summary["B3"] = request.kind
    if request.question:
        summary["A4"] = "用户问题"
        summary["B4"] = request.question
    if request.answer:
        summary["A5"] = "分析结论"
        summary["B5"] = request.answer
    row_index = 7
    if request.metrics:
        summary.cell(row=row_index, column=1, value="关键指标").font = Font(bold=True)
        row_index += 1
        for key, value in request.metrics.items():
            summary.cell(row=row_index, column=1, value=str(key))
            summary.cell(row=row_index, column=2, value=_text(value))
            row_index += 1
    for column, width in (("A", 24), ("B", 90)):
        summary.column_dimensions[column].width = width
    for row in summary.iter_rows():
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    if request.table:
        sheet = workbook.create_sheet("数据明细")
        sheet.append(request.table.columns)
        for cell in sheet[1]:
            cell.fill = PatternFill("solid", fgColor="DCE9F7")
            cell.font = Font(bold=True)
        for row in request.table.rows:
            sheet.append([_text(value) for value in row])
        sheet.freeze_panes = "A2"
        for column in sheet.columns:
            max_len = max(len(_text(cell.value)) for cell in column)
            sheet.column_dimensions[column[0].column_letter].width = min(max(12, max_len + 2), 40)

    if request.sections:
        detail = workbook.create_sheet("分析明细")
        detail.append(["章节", "内容"])
        for cell in detail[1]:
            cell.fill = PatternFill("solid", fgColor="DCE9F7")
            cell.font = Font(bold=True)
        for section in request.sections:
            detail.append([section.title, section.text])
        detail.column_dimensions["A"].width = 24
        detail.column_dimensions["B"].width = 100
        for row in detail.iter_rows():
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)

    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def _build_docx(request: ResultExportRequest) -> bytes:
    document = Document()
    title = document.add_heading(request.title, level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    document.add_paragraph(f"生成时间：{datetime.now().isoformat(timespec='seconds')}")
    document.add_paragraph(f"结果类型：{request.kind}")
    if request.question:
        document.add_heading("用户问题", level=1)
        document.add_paragraph(request.question)
    if request.answer:
        document.add_heading("分析结论", level=1)
        document.add_paragraph(request.answer)
    if request.metrics:
        document.add_heading("关键指标", level=1)
        table = document.add_table(rows=1, cols=2)
        table.style = "Table Grid"
        table.rows[0].cells[0].text = "指标"
        table.rows[0].cells[1].text = "数值"
        for key, value in request.metrics.items():
            cells = table.add_row().cells
            cells[0].text = str(key)
            cells[1].text = _text(value)
    for section in request.sections:
        document.add_heading(section.title, level=1)
        document.add_paragraph(section.text)
    if request.table:
        document.add_heading("数据明细", level=1)
        table = document.add_table(rows=1, cols=len(request.table.columns))
        table.style = "Table Grid"
        for index, column in enumerate(request.table.columns):
            table.rows[0].cells[index].text = column
        for row in request.table.rows:
            cells = table.add_row().cells
            for index, value in enumerate(row):
                cells[index].text = _text(value)
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def _build_pdf(request: ResultExportRequest) -> bytes:
    font_name = "STSong-Light"
    pdfmetrics.registerFont(UnicodeCIDFont(font_name))
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ExportTitle",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=20,
        leading=28,
        textColor=colors.HexColor("#123A63"),
    )
    heading_style = ParagraphStyle(
        "ExportHeading",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=14,
        leading=20,
        spaceBefore=10,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "ExportBody",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=10,
        leading=16,
    )
    story = [
        Paragraph(_escape_pdf(request.title), title_style),
        Spacer(1, 4 * mm),
        Paragraph(f"生成时间：{datetime.now().isoformat(timespec='seconds')}", body_style),
        Paragraph(f"结果类型：{request.kind}", body_style),
    ]
    if request.question:
        story.extend([Paragraph("用户问题", heading_style), Paragraph(_escape_pdf(request.question), body_style)])
    if request.answer:
        story.extend([Paragraph("分析结论", heading_style), Paragraph(_escape_pdf(request.answer), body_style)])
    if request.metrics:
        story.append(Paragraph("关键指标", heading_style))
        story.append(_pdf_table(["指标", "数值"], [[key, value] for key, value in request.metrics.items()], font_name))
    for section in request.sections:
        story.extend([Paragraph(_escape_pdf(section.title), heading_style), Paragraph(_escape_pdf(section.text), body_style)])
    if request.table:
        story.extend(
            [
                Paragraph("数据明细", heading_style),
                _pdf_table(request.table.columns, request.table.rows, font_name),
            ]
        )
    story.extend(
        [
            Spacer(1, 4 * mm),
            Paragraph("说明", heading_style),
            Paragraph("本文件由招录智策系统根据当前分析结果生成，业务数字以系统数据为准。", body_style),
        ]
    )
    output = io.BytesIO()
    SimpleDocTemplate(output, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm).build(story)
    return output.getvalue()


def _escape_pdf(value: str) -> str:
    return _text(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")


def _pdf_table(headers: list[str], rows: list[list[Any]], font_name: str) -> Table:
    data = [[_escape_pdf(header) for header in headers]]
    data.extend([[_escape_pdf(value) for value in row] for row in rows])
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCE9F7")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#AAB7C6")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("PADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def build_export_file(request: ResultExportRequest) -> tuple[bytes, str, str]:
    _validate_content(request)
    builders = {
        "csv": _build_csv,
        "xlsx": _build_xlsx,
        "docx": _build_docx,
        "pdf": _build_pdf,
        "md": _build_markdown,
        "json": _build_json,
    }
    content = builders[request.format](request)
    filename = _safe_filename(request)
    disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
    return content, _MEDIA_TYPES[request.format], disposition

