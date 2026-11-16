from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.text import text
from app.modules.agent.tools.common import bar_chart as _bar_chart, pie_chart as _pie_chart
from sqlalchemy.ext.asyncio import AsyncSession
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

async def student_statistics(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
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


async def student_lookup(db: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
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



