from __future__ import annotations

import re
from typing import Any

from app.core.text import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics import service
from app.modules.agent.tools.common import bar_chart


async def consultation_overview(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    year = params.get("year")
    province = params.get("province")
    clauses: list[str] = []
    binds: dict[str, Any] = {}

    if year is not None:
        clauses.append("y.year_no = :year")
        binds["year"] = int(year)
    if province:
        clauses.append("pr.province_name = :province")
        binds["province"] = str(province)

    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    total = int(await db.scalar(
        text(f"SELECT COUNT(*) FROM fact.consultation c JOIN dim.year y ON y.id=c.year_id {where_sql}"),
        binds,
    ) or 0)
    converted = int(await db.scalar(
        text(f"SELECT COUNT(*) FROM fact.consultation c JOIN dim.year y ON y.id=c.year_id {where_sql} AND c.converted IS TRUE"),
        binds,
    ) or 0)
    channel_rows = (await db.execute(
        text(f"""
            SELECT COALESCE(ch.channel_name, '未标注') AS channel_name,
                   COUNT(*) AS consultation_count,
                   SUM(CASE WHEN c.converted IS TRUE THEN 1 ELSE 0 END) AS converted_count
            FROM fact.consultation c
            JOIN dim.year y ON y.id=c.year_id
            LEFT JOIN dim.province pr ON pr.id=c.province_id
            LEFT JOIN dim.channel ch ON ch.id=c.channel_id
            {where_sql}
            GROUP BY COALESCE(ch.channel_name, '未标注')
            ORDER BY consultation_count DESC
        """),
        binds,
    )).mappings().all()
    type_rows = (await db.execute(
        text(f"""
            SELECT COALESCE(c.consultation_type, '未标注') AS consultation_type,
                   COUNT(*) AS consultation_count
            FROM fact.consultation c
            JOIN dim.year y ON y.id=c.year_id
            LEFT JOIN dim.province pr ON pr.id=c.province_id
            {where_sql}
            GROUP BY COALESCE(c.consultation_type, '未标注')
            ORDER BY consultation_count DESC
        """),
        binds,
    )).mappings().all()

    conversion_rate = round(converted / total * 100, 2) if total else 0.0
    channel_details = "；".join(
        f"{row['channel_name']}咨询 {row['consultation_count']} 次、转化 {row['converted_count'] or 0} 次"
        for row in channel_rows[:8]
    )
    type_details = "；".join(
        f"{row['consultation_type']} {row['consultation_count']} 次"
        for row in type_rows[:8]
    )
    answer = (
        f"当前共 {total} 条咨询，已转化 {converted} 条，转化率 {conversion_rate}%。"
        + (f" 渠道情况：{channel_details}。" if channel_details else "")
        + (f" 咨询类型：{type_details}。" if type_details else "")
    )
    return {
        "answer": answer,
        "charts": [
            bar_chart(
                "各渠道咨询转化",
                [row["channel_name"] for row in channel_rows],
                [row["converted_count"] or 0 for row in channel_rows],
            )
        ] if channel_rows else [],
        "table": {
            "columns": ["渠道", "咨询数", "转化数", "转化率"],
            "rows": [
                [
                    row["channel_name"],
                    row["consultation_count"],
                    row["converted_count"] or 0,
                    round((row["converted_count"] or 0) / row["consultation_count"] * 100, 2) if row["consultation_count"] else 0,
                ]
                for row in channel_rows
            ],
        },
        "data_sources": [{"table": "fact.consultation", "metric": "咨询转化"}],
        "metrics": {
            "consultation_count": total,
            "converted_count": converted,
            "conversion_rate": conversion_rate,
            "channel_count": len(channel_rows),
            "type_count": len(type_rows),
            "by_channel": {
                str(row["channel_name"]): {
                    "consultation_count": row["consultation_count"],
                    "converted_count": row["converted_count"] or 0,
                }
                for row in channel_rows
            },
            "by_type": {
                str(row["consultation_type"]): row["consultation_count"]
                for row in type_rows
            },
        },
    }


async def enrollment_funnel(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    year = params.get("year")
    admissions = await service.get_admissions_overview(db, year=year)
    source = await service.get_source_overview(db, year=year)

    plan_count = int((admissions.get("metrics") or {}).get("plan_count") or 0)
    admitted_count = int((admissions.get("metrics") or {}).get("admitted_count") or 0)
    enrolled_count = int((source.get("metrics") or {}).get("enrolled_count") or 0)

    admit_rate = round(admitted_count / plan_count * 100, 2) if plan_count else 0.0
    enroll_rate = round(enrolled_count / admitted_count * 100, 2) if admitted_count else 0.0
    lost_after_admission = max(admitted_count - enrolled_count, 0)

    year_label = f"{year}年" if year else "当前年度"
    answer = (
        f"{year_label}招生漏斗：计划 {plan_count} 人 → 录取 {admitted_count} 人 → 已报到 {enrolled_count} 人；"
        f"录取完成率 {admit_rate}%，报到率 {enroll_rate}%，录取后流失 {lost_after_admission} 人。"
    )
    return {
        "answer": answer,
        "charts": [],
        "table": {
            "columns": ["阶段", "人数"],
            "rows": [
                ["招生计划", plan_count],
                ["实际录取", admitted_count],
                ["已报到", enrolled_count],
                ["录取后流失", lost_after_admission],
            ],
        },
        "data_sources": [
            {"table": "fact.plan", "metric": "招生计划"},
            {"table": "fact.admission_summary", "metric": "录取汇总"},
            {"table": "fact.enrollment_status", "metric": "报到状态"},
        ],
        "metrics": {
            "plan_count": plan_count,
            "admitted_count": admitted_count,
            "enrolled_count": enrolled_count,
            "admit_rate": admit_rate,
            "enroll_rate": enroll_rate,
            "lost_after_admission": lost_after_admission,
        },
    }


async def score_band_statistics(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    year = params.get("year")
    subject_name = str(params.get("subject_name") or "").strip()
    query_text = str(params.get("query") or "")
    if not subject_name:
        query_text = str(params.get("query") or "")
        for candidate in ("语文", "数学", "外语", "英语", "物理", "化学", "生物", "政治", "历史", "地理", "综合"):
            if candidate in query_text:
                subject_name = candidate
                break
    if not subject_name:
        year_label = f"{year}年" if year else "当前年度"
        return {
            "answer": f"{year_label}请指定要统计的科目，例如：语文、数学、外语、物理、化学、生物、政治、历史、地理、综合。",
            "charts": [],
            "table": None,
            "data_sources": [{"table": "fact.exam_subject_score", "metric": "学科成绩"}],
            "metrics": {"subject_required": True},
        }

    subject_name = "外语" if subject_name == "英语" else subject_name
    clauses = ["es.subject_name = :subject_name"]
    binds: dict[str, Any] = {"subject_name": subject_name}
    if year is not None:
        clauses.append("es.year_no = :year")
        binds["year"] = int(year)

    where_sql = "WHERE " + " AND ".join(clauses)
    rows = (await db.execute(
        text(f"""
            SELECT FLOOR(es.score / 10) * 10 AS band,
                   COUNT(*) AS student_count,
                   ROUND(AVG(es.score), 2) AS avg_score
            FROM fact.exam_subject_score es
            {where_sql}
            GROUP BY FLOOR(es.score / 10) * 10
            ORDER BY band
        """),
        binds,
    )).mappings().all()

    if not rows:
        return {
            "answer": f"没有找到 {subject_name} 的成绩数据。",
            "charts": [],
            "table": None,
            "data_sources": [{"table": "fact.exam_subject_score", "metric": "学科成绩"}],
            "metrics": {"subject_name": subject_name, "band_count": 0},
        }

    details = "；".join(
        f"{int(row['band'])}-{int(row['band']) + 9} 分 {row['student_count']} 人"
        for row in rows
    )
    year_label = f"{year}年" if year else "当前年度"
    answer = f"{year_label}{subject_name}分数段：{details}。"
    metrics = {
        "subject_name": subject_name,
        "band_count": len(rows),
        "total_students": sum(int(row["student_count"]) for row in rows),
        "by_band": {
            f"{int(row['band'])}-{int(row['band']) + 9}": int(row["student_count"])
            for row in rows
        },
    }
    band_match = re.search(r"(\d{2,3})\s*(?:到|至|-)\s*(\d{2,3})\s*分", query_text)
    if band_match:
        target = int(band_match.group(1))
        for row in rows:
            if int(row["band"]) == target:
                metrics.update({
                    "student_count": int(row["student_count"]),
                    "band_start": target,
                    "band_end": target + 9,
                })
                break
    return {
        "answer": answer,
        "charts": [
            bar_chart(
                f"{subject_name}分数段",
                [f"{int(row['band'])}-{int(row['band']) + 9}" for row in rows],
                [row["student_count"] for row in rows],
            )
        ],
        "table": {
            "columns": ["分数段", "人数", "平均分"],
            "rows": [
                [f"{int(row['band'])}-{int(row['band']) + 9}", row["student_count"], row["avg_score"]]
                for row in rows
            ],
        },
        "data_sources": [{"table": "fact.exam_subject_score", "metric": "学科成绩"}],
        "metrics": metrics,
    }

