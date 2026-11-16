from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.core.config import settings
from app.modules.analytics import service
from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


async def build_report_context(
    db,
    *,
    report_type: str,
    year: int | None,
    province: str | None,
    major: str | None,
) -> dict:
    admissions = None
    source = None
    trend = None
    candidate_profile = None
    subject_scores = None
    major_choices = None
    medical = None
    anomalies = None
    if report_type in {"admissions", "comprehensive"}:
        admissions = await service.get_admissions_overview(
            db,
            year=year,
            province=province,
            major=major,
        )
        trend = await service.get_admissions_overview(db)
        candidate_profile = await service.get_candidate_profile_overview(
            db, year=year, province=province, major=major
        )
        subject_scores = await service.get_subject_score_overview(
            db, year=year, province=province, major=major
        )
        major_choices = await service.get_major_choice_overview(
            db, year=year, major=major
        )
        medical = await service.get_medical_overview(
            db, year=year, province=province, major=major
        )
        anomalies = await service.get_anomalies(db, year=year)
    if report_type in {"source", "comprehensive"}:
        source = await service.get_source_overview(db, year=year)

    filters = {
        "year": year,
        "province": province,
        "major": major,
    }
    summary = _build_summary(admissions, source)
    insights = _build_insights(
        admissions=admissions,
        trend=trend,
        candidate_profile=candidate_profile,
        subject_scores=subject_scores,
        major_choices=major_choices,
        medical=medical,
        anomalies=anomalies,
        source=source,
    )
    context = {
        "title": _report_title(report_type),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "filters": filters,
        "admissions": admissions,
        "source": source,
        "trend": trend,
        "candidate_profile": candidate_profile,
        "subject_scores": subject_scores,
        "major_choices": major_choices,
        "medical": medical,
        "anomalies": anomalies,
        "summary": summary,
        "insights": insights,
        "ai_commentary": None,
    }
    context["ai_commentary"] = _build_local_commentary(context)
    return context


def _rank(items: list[dict], key: str = "plan_count", *, limit: int = 5) -> list[str]:
    rows = [item for item in items if item.get(key) is not None]
    rows = sorted(rows, key=lambda item: item[key], reverse=True)[:limit]
    return [str(item.get("major_name") or item.get("province_name") or item.get("name")) for item in rows]


def _build_insights(
    *,
    admissions: dict | None,
    trend: dict | None,
    candidate_profile: dict | None,
    subject_scores: dict | None,
    major_choices: dict | None,
    medical: dict | None,
    anomalies: dict | None,
    source: dict | None,
) -> list[dict]:
    insights: list[dict] = []

    if admissions:
        metrics = admissions["metrics"]
        insights.append({
            "title": "招生执行度",
            "finding": (
                f"计划 {metrics['plan_count']} 人，录取 {metrics['admitted_count']} 人，"
                f"完成率 {metrics['completion_rate']}%。"
            ),
            "analysis": (
                "完成率接近或超过 100% 说明计划与生源需求基本匹配；"
                "低于 95% 则需要按省份、专业和批次定位缺口。"
            ),
            "suggestion": "优先排查完成率低于 90% 的专业，并核对招生计划与志愿热度是否脱节。",
            "evidence": ["fact.plan", "fact.admission_record"],
        })

        if admissions.get("by_province"):
            low_provinces = sorted(
                admissions["by_province"],
                key=lambda row: row.get("completion_rate") or 100,
            )[:3]
            names = "、".join(row["province_name"] for row in low_provinces)
            insights.append({
                "title": "省份结构差异",
                "finding": f"完成率较低的省份为：{names}。",
                "analysis": "省份间完成率差异通常反映宣传触达、专业投放和生源结构差异。",
                "suggestion": "对低完成率省份做专业、科类和渠道下钻，避免只按总量判断。",
                "evidence": ["fact.plan", "fact.admission_record"],
            })

        if admissions.get("by_major"):
            hot = admissions["by_major"][0]
            insights.append({
                "title": "专业热度集中",
                "finding": f"计划规模最大的专业为 {hot['major_name']}，计划 {hot['plan_count']} 人。",
                "analysis": "专业集中会放大单一专业波动对整体完成率的影响。",
                "suggestion": "热门专业扩展前先核验志愿热度、分数位次和培养容量。",
                "evidence": ["fact.plan", "fact.admission_record"],
            })

    if trend and len(trend.get("year_trend", [])) >= 2:
        years = trend["year_trend"]
        current = years[-1]
        previous = years[-2]
        plan_growth = (
            round((current["plan_count"] - previous["plan_count"]) / previous["plan_count"] * 100, 2)
            if previous["plan_count"]
            else 0
        )
        insights.append({
            "title": "年度趋势",
            "finding": (
                f"招生计划从 {previous['year_no']} 年 {previous['plan_count']} 人"
                f"变化到 {current['year_no']} 年 {current['plan_count']} 人，同比 {plan_growth}%。"
            ),
            "analysis": "年度变化需要结合政策、批次和专业结构调整，不能简单归因。",
            "suggestion": "把年度变化拆成计划增量和结构变化两部分，分别评估风险。",
            "evidence": ["analytics.mv_admissions_rollup"],
        })

    if candidate_profile:
        by_gender = candidate_profile.get("by_gender") or []
        if by_gender:
            top = by_gender[0]
            insights.append({
                "title": "考生结构",
                "finding": f"考生性别分布中 {top['name']} 占 {top['count']} 人。",
                "analysis": "结构数据只说明样本构成，不能直接解释录取质量。",
                "suggestion": "结合专业志愿和录取分数，判断结构差异是否带来培养与宣传偏差。",
                "evidence": ["fact.candidate_profile"],
            })

    if subject_scores and subject_scores.get("subjects"):
        subjects = subject_scores["subjects"]
        max_avg = max(subjects, key=lambda row: row.get("avg_score") or 0)
        min_avg = min(subjects, key=lambda row: row.get("avg_score") or 0)
        insights.append({
            "title": "学科成绩分化",
            "finding": (
                f"平均分最高为 {max_avg['subject_name']}（{max_avg['avg_score']}），"
                f"最低为 {min_avg['subject_name']}（{min_avg['avg_score']}）。"
            ),
            "analysis": "学科均分差异受满分制、选考人群和样本结构影响。",
            "suggestion": "对低均分学科按科类、专业志愿和地区下钻，识别基础薄弱群体。",
            "evidence": ["fact.exam_subject_score"],
        })

    if major_choices and major_choices.get("majors"):
        choices = major_choices["majors"]
        top_three = choices[:3]
        names = "、".join(row["major_name"] for row in top_three)
        insights.append({
            "title": "志愿集中度",
            "finding": f"志愿热度最高的专业为：{names}。",
            "analysis": "志愿集中会加剧热门专业竞争和调剂压力。",
            "suggestion": "对高热度专业测算扩招后的位次变化，并加强低热度专业的招生宣传。",
            "evidence": ["fact.major_choice"],
        })

    if medical and medical.get("medical_results"):
        total = sum(int(row.get("count") or 0) for row in medical["medical_results"])
        top = medical["medical_results"][0]
        insights.append({
            "title": "体检受限",
            "finding": f"体检摘要共 {total} 条，主要结论为 {top['result_name']}。",
            "analysis": "受限人数不等于退档人数，需与志愿专业和录取结果关联。",
            "suggestion": "对受限高发专业增加填报前提示和录取后复核。",
            "evidence": ["fact.medical_summary"],
        })

    if anomalies:
        summary = anomalies.get("summary") or {}
        items = anomalies.get("items") or []
        insights.append({
            "title": "异常与风险",
            "finding": (
                f"检测出 {summary.get('total_anomalies', 0)} 项异常，"
                f"其中高风险 {summary.get('high', 0)} 项，中风险 {summary.get('medium', 0)} 项。"
            ),
            "analysis": "异常检测是启发式规则，必须结合业务核查确认。",
            "suggestion": "优先处理高风险专业，核对计划、录取、志愿热度和同比变化。",
            "evidence": ["fact.plan", "fact.admission_record", "fact.major_choice"],
        })
        for item in items[:3]:
            insights.append({
                "title": f"风险专业：{item.get('major_name')}",
                "finding": item.get("message") or "",
                "analysis": f"计划 {item.get('plan_count')}，录取 {item.get('admitted_count')}，完成率 {item.get('completion_rate')}%。",
                "suggestion": item.get("suggestion") or "按业务口径复核。",
                "evidence": ["fact.plan", "fact.admission_record", "fact.major_choice"],
            })

    if source:
        metrics = source["metrics"]
        insights.append({
            "title": "生源与报到",
            "finding": (
                f"生源 {metrics['candidate_count']} 人，报到 {metrics['enrolled_count']} 人，"
                f"报到率 {metrics['enrollment_rate']}%。"
            ),
            "analysis": "报到率低会直接抵消录取规模，需结合渠道和省份分析。",
            "suggestion": "对报到率低的渠道和省份做回访，核对录取通知与缴费确认流程。",
            "evidence": ["fact.admission_record", "fact.enrollment_status"],
        })

    return insights


def _build_local_commentary(context: dict) -> str | None:
    lines: list[str] = []
    for item in (context.get("insights") or [])[:5]:
        title = str(item.get("title") or "分析结论").strip()
        action = str(
            item.get("suggestion")
            or item.get("analysis")
            or item.get("finding")
            or ""
        ).strip()
        if action:
            lines.append(f"{title}：{action}")
    return "\n".join(lines) or None


def _report_title(report_type: str) -> str:
    return {
        "admissions": "高校招生分析报告",
        "source": "高校生源分析报告",
        "comprehensive": "高校招录综合分析报告",
    }.get(report_type, "高校招录分析报告")


def _build_summary(admissions: dict | None, source: dict | None) -> list[str]:
    summary: list[str] = []
    if admissions:
        metrics = admissions["metrics"]
        summary.append(
            f"招生计划共 {metrics['plan_count']} 人，实际录取 {metrics['admitted_count']} 人，"
            f"计划完成率为 {metrics['completion_rate']}%。"
        )
        if admissions["by_province"]:
            top_province = admissions["by_province"][0]
            summary.append(
                f"计划规模最大的省份为 {top_province['province_name']}，"
                f"计划 {top_province['plan_count']} 人，完成率 {top_province['completion_rate']}%。"
            )
        if admissions["by_major"]:
            top_major = admissions["by_major"][0]
            summary.append(
                f"计划规模最大的专业为 {top_major['major_name']}，"
                f"计划 {top_major['plan_count']} 人，完成率 {top_major['completion_rate']}%。"
            )
    if source:
        metrics = source["metrics"]
        summary.append(
            f"生源统计共 {metrics['candidate_count']} 人，报到 {metrics['enrolled_count']} 人，"
            f"报到率为 {metrics['enrollment_rate']}%。"
        )
        if source["by_channel"]:
            top_channel = source["by_channel"][0]
            summary.append(
                f"生源人数最多的渠道为 {top_channel['channel_name']}，"
                f"生源人数 {top_channel['candidate_count']} 人。"
            )
    return summary


def generate_report_file(context: dict, file_format: str) -> Path:
    report_dir = Path(settings.storage_root) / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    suffix = "docx" if file_format == "docx" else "pdf"
    path = report_dir / f"{uuid4().hex}.{suffix}"
    if suffix == "docx":
        _write_docx(context, path)
    else:
        _write_pdf(context, path)
    return path


def _write_docx(context: dict, path: Path) -> None:
    document = Document()
    style = document.styles["Normal"]
    style.font.name = "Microsoft YaHei"
    style._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
    style.font.size = Pt(10.5)

    document.add_heading(context["title"], level=0)
    document.add_paragraph(f"生成时间：{context['generated_at']}")
    document.add_paragraph(f"筛选条件：{_filters_text(context['filters'])}")

    document.add_heading("一、核心结论", level=1)
    for item in context["summary"]:
        document.add_paragraph(item, style="List Bullet")

    if context.get("insights"):
        document.add_heading("二、深层分析", level=1)
        for item in context["insights"]:
            document.add_paragraph(f"{item['title']}：{item['finding']}", style="List Bullet")
            if item.get("analysis"):
                document.add_paragraph(item["analysis"])
            if item.get("suggestion"):
                document.add_paragraph(f"建议：{item['suggestion']}")

    if context.get("ai_commentary"):
        document.add_heading("三、AI 管理建议", level=1)
        document.add_paragraph(context["ai_commentary"])

    admissions = context.get("admissions")
    if admissions:
        document.add_heading("四、招生指标", level=1)
        _add_docx_table(
            document,
            ["指标", "数值"],
            [
                ["招生计划数", admissions["metrics"]["plan_count"]],
                ["实际录取数", admissions["metrics"]["admitted_count"]],
                ["计划完成率", f"{admissions['metrics']['completion_rate']}%"],
                ["最低录取分", admissions["metrics"]["min_score"]],
                ["最低录取位次", admissions["metrics"]["min_rank_no"]],
            ],
        )
        document.add_heading("五、分省招生情况", level=1)
        _add_docx_table(
            document,
            ["省份", "计划数", "录取数", "完成率", "最低分", "最低位次"],
            [
                [
                    row["province_name"],
                    row["plan_count"],
                    row["admitted_count"],
                    row["completion_rate"],
                    row["min_score"],
                    row["min_rank_no"],
                ]
                for row in admissions["by_province"]
            ],
        )
        document.add_heading("六、专业招生情况", level=1)
        _add_docx_table(
            document,
            ["专业", "计划数", "录取数", "完成率", "最低分", "最低位次"],
            [
                [
                    row["major_name"],
                    row["plan_count"],
                    row["admitted_count"],
                    row["completion_rate"],
                    row["min_score"],
                    row["min_rank_no"],
                ]
                for row in admissions["by_major"]
            ],
        )

    source = context.get("source")
    if source:
        document.add_heading("七、生源与渠道分析", level=1)
        _add_docx_table(
            document,
            ["指标", "数值"],
            [
                ["生源人数", source["metrics"]["candidate_count"]],
                ["报到人数", source["metrics"]["enrolled_count"]],
                ["报到率", f"{source['metrics']['enrollment_rate']}%"],
            ],
        )
        _add_docx_table(
            document,
            ["渠道", "生源人数", "报到人数", "平均分"],
            [
                [
                    row["channel_name"],
                    row["candidate_count"],
                    row["enrolled_count"],
                    row["avg_score"],
                ]
                for row in source["by_channel"]
            ],
        )

    document.add_heading("七、说明", level=1)
    document.add_paragraph(
        "本报告由招录智策系统根据已导入数据自动生成。所有统计数字来自数据库计算，"
        "预测和解释内容不构成录取承诺，最终结果以官方发布为准。"
    )
    document.save(path)


def _add_docx_table(document: Document, headers: list[str], rows: list[list]) -> None:
    table = document.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    for index, header in enumerate(headers):
        table.rows[0].cells[index].text = str(header)
    for row in rows:
        cells = table.add_row().cells
        for index, value in enumerate(row):
            cells[index].text = "" if value is None else str(value)


def _write_pdf(context: dict, path: Path) -> None:
    font_name = "STSong-Light"
    pdfmetrics.registerFont(UnicodeCIDFont(font_name))
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ChineseTitle",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=20,
        leading=28,
        textColor=colors.HexColor("#123A63"),
    )
    heading_style = ParagraphStyle(
        "ChineseHeading",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=14,
        leading=20,
        spaceBefore=10,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "ChineseBody",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=10,
        leading=16,
    )

    story = [
        Paragraph(context["title"], title_style),
        Spacer(1, 6 * mm),
        Paragraph(f"生成时间：{context['generated_at']}", body_style),
        Paragraph(f"筛选条件：{_filters_text(context['filters'])}", body_style),
        Spacer(1, 4 * mm),
        Paragraph("一、核心结论", heading_style),
    ]
    if context.get("insights"):
        story.append(Paragraph("二、深层分析", heading_style))
        for item in context["insights"]:
            story.append(Paragraph(
                f"{item['title']}：{_pdf_text(item['finding'])}",
                body_style,
            ))
            if item.get("analysis"):
                story.append(Paragraph(_pdf_text(item["analysis"]), body_style))
            if item.get("suggestion"):
                story.append(Paragraph(f"建议：{_pdf_text(item['suggestion'])}", body_style))
        story.append(Spacer(1, 4 * mm))
    for item in context["summary"]:
        story.append(Paragraph(f"• {_pdf_text(item)}", body_style))
        story.append(Spacer(1, 2 * mm))

    if context.get("ai_commentary"):
        story.extend(
            [
                Paragraph("三、AI 管理建议", heading_style),
                Paragraph(_pdf_text(context["ai_commentary"]).replace("\n", "<br/>"), body_style),
                Spacer(1, 4 * mm),
            ]
        )

    admissions = context.get("admissions")
    if admissions:
        story.extend(
            [
                Paragraph("四、招生指标", heading_style),
                _pdf_table(
                    ["指标", "数值"],
                    [
                        ["招生计划数", admissions["metrics"]["plan_count"]],
                        ["实际录取数", admissions["metrics"]["admitted_count"]],
                        ["计划完成率", f"{admissions['metrics']['completion_rate']}%"],
                        ["最低录取分", admissions["metrics"]["min_score"]],
                        ["最低录取位次", admissions["metrics"]["min_rank_no"]],
                    ],
                    font_name,
                ),
                Spacer(1, 4 * mm),
                Paragraph("五、分省招生情况", heading_style),
                _pdf_table(
                    ["省份", "计划数", "录取数", "完成率", "最低分", "最低位次"],
                    [
                        [
                            row["province_name"],
                            row["plan_count"],
                            row["admitted_count"],
                            row["completion_rate"],
                            row["min_score"],
                            row["min_rank_no"],
                        ]
                        for row in admissions["by_province"]
                    ],
                    font_name,
                ),
                Spacer(1, 4 * mm),
                Paragraph("六、专业招生情况", heading_style),
                _pdf_table(
                    ["专业", "计划数", "录取数", "完成率", "最低分", "最低位次"],
                    [
                        [
                            row["major_name"],
                            row["plan_count"],
                            row["admitted_count"],
                            row["completion_rate"],
                            row["min_score"],
                            row["min_rank_no"],
                        ]
                        for row in admissions["by_major"]
                    ],
                    font_name,
                ),
            ]
        )

    source = context.get("source")
    if source:
        story.extend(
            [
                Spacer(1, 4 * mm),
                Paragraph("七、生源与渠道分析", heading_style),
                _pdf_table(
                    ["渠道", "生源人数", "报到人数", "平均分"],
                    [
                        [
                            row["channel_name"],
                            row["candidate_count"],
                            row["enrolled_count"],
                            row["avg_score"],
                        ]
                        for row in source["by_channel"]
                    ],
                    font_name,
                ),
            ]
        )

    story.extend(
        [
            Spacer(1, 5 * mm),
            Paragraph("八、说明", heading_style),
            Paragraph(
                "本报告由招录智策系统自动生成，所有数字来自数据库。"
                "最终结果以官方发布为准。",
                body_style,
            ),
        ]
    )
    SimpleDocTemplate(str(path), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm).build(story)


def _pdf_table(headers: list[str], rows: list[list], font_name: str) -> Table:
    data = [[_pdf_text(header) for header in headers]]
    data.extend([[_pdf_text(value) for value in row] for row in rows])
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCE9F7")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#AAB7C6")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("PADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _filters_text(filters: dict) -> str:
    parts = []
    if filters.get("year"):
        parts.append(f"年度：{filters['year']}")
    if filters.get("province"):
        parts.append(f"省份：{filters['province']}")
    if filters.get("major"):
        parts.append(f"专业：{filters['major']}")
    return "；".join(parts) if parts else "全部数据"


def _pdf_text(value) -> str:
    return "" if value is None else str(value)

