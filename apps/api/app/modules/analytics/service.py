from typing import Any

from app.core.text import text
from app.modules.analytics.materialized import refresh_admissions_rollup
from sqlalchemy.ext.asyncio import AsyncSession


def _where_clause(
    *,
    year: int | None = None,
    province: str | None = None,
    major: str | None = None,
) -> tuple[str, dict]:
    clauses: list[str] = []
    params: dict[str, object] = {}
    if year is not None:
        clauses.append("y.year_no = :year")
        params["year"] = year
    if province:
        clauses.append("pr.province_name = :province")
        params["province"] = province
    if major:
        clauses.append("resolved_major.major_name = :major")
        params["major"] = major
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


MAJOR_RESOLVE_JOIN = """
LEFT JOIN LATERAL (
    SELECT ma.canonical_major_id
    FROM dim.major_alias ma
    WHERE ma.is_active
      AND ma.source_name_key = lower(
          replace(replace(replace(m.major_name, '（', '('), '）', ')'), ' ', '')
      )
      AND (ma.province_id IS NULL OR ma.province_id = p.province_id)
    ORDER BY (ma.province_id IS NOT NULL) DESC, ma.id DESC
    LIMIT 1
) major_alias ON TRUE
JOIN dim.major resolved_major
  ON resolved_major.id = COALESCE(major_alias.canonical_major_id, m.id)
"""

MAJOR_RESOLVE_JOIN_AR = """
LEFT JOIN LATERAL (
    SELECT ma.canonical_major_id
    FROM dim.major_alias ma
    WHERE ma.is_active
      AND ma.source_name_key = lower(
          replace(replace(replace(m.major_name, '（', '('), '）', ')'), ' ', '')
      )
      AND (ma.province_id IS NULL OR ma.province_id = ar.province_id)
    ORDER BY (ma.province_id IS NOT NULL) DESC, ma.id DESC
    LIMIT 1
) major_alias ON TRUE
JOIN dim.major resolved_major
  ON resolved_major.id = COALESCE(major_alias.canonical_major_id, m.id)
"""

ADMISSION_FROM = f"""
FROM fact.plan p
JOIN dim.year y ON y.id = p.year_id
JOIN dim.province pr ON pr.id = p.province_id
JOIN dim.major m ON m.id = p.major_id
JOIN dim.subject sub ON sub.id = p.subject_id
JOIN dim.plan_type pt ON pt.id = p.plan_type_id
{MAJOR_RESOLVE_JOIN}
LEFT JOIN fact.admission_summary s ON s.plan_id = p.id
"""

COMPARABLE_CULTURE_SCORE = """
    pt.type_code = 'REG'
    AND COALESCE(sub.subject_name, '') NOT LIKE '%体育%'
    AND COALESCE(sub.subject_name, '') NOT LIKE '%艺术%'
    AND m.major_name !~ '美术|音乐|舞蹈|视觉传达设计|环境设计|产品设计|服装与服饰设计|工艺美术|艺术|体育'
"""

MV_COMPARABLE_CULTURE_SCORE = """
    mv.plan_type_code = 'REG'
    AND COALESCE(mv.subject_name, '') NOT LIKE '%体育%'
    AND COALESCE(mv.subject_name, '') NOT LIKE '%艺术%'
    AND mv.source_major_name !~ '美术|音乐|舞蹈|视觉传达设计|环境设计|产品设计|服装与服饰设计|工艺美术|艺术|体育'
"""


def _mv_where_clause(
    *,
    year: int | None = None,
    province: str | None = None,
    major: str | None = None,
) -> tuple[str, dict]:
    clauses: list[str] = []
    params: dict[str, object] = {}
    if year is not None:
        clauses.append("mv.year_no = :year")
        params["year"] = year
    if province:
        clauses.append("mv.province_name = :province")
        params["province"] = province
    if major:
        clauses.append("mv.canonical_major_name = :major")
        params["major"] = major
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


async def get_dashboard_overview(db: AsyncSession, *, year: int | None = None) -> dict:
    target_year = year or await db.scalar(text("SELECT MAX(year_no) FROM dim.year"))
    plan_count = await db.scalar(
        text(
            """
            SELECT COALESCE(SUM(p.plan_count), 0)
            FROM fact.plan p
            JOIN dim.year y ON y.id = p.year_id
            WHERE y.year_no = :year
            """
        ),
        {"year": target_year},
    )
    admitted_count = await db.scalar(
        text(
            """
            SELECT COUNT(*)
            FROM fact.admission_record ar
            JOIN dim.year y ON y.id = ar.year_id
            WHERE y.year_no = :year
            """
        ),
        {"year": target_year},
    )
    min_rank_no = await db.scalar(
        text(
            """
            SELECT MIN(ar.rank_no)
            FROM fact.admission_record ar
            JOIN dim.year y ON y.id = ar.year_id
            WHERE y.year_no = :year
              AND ar.rank_no IS NOT NULL
            """
        ),
        {"year": target_year},
    )
    completion_rate = 0
    if plan_count:
        completion_rate = round(float(admitted_count) / float(plan_count), 4)
    return {
        "year_no": target_year,
        "plan_count": int(plan_count or 0),
        "admitted_count": int(admitted_count or 0),
        "completion_rate": completion_rate,
        "min_rank_no": min_rank_no,
        "source_quality_index": None,
        "pending_alerts": 0,
        "empty_reason": None if plan_count else "等待导入真实招录数据",
    }


async def _rollup_matches_base(db: AsyncSession, year: int | None) -> bool:
    row = (
        await db.execute(
            text(
                """
                SELECT
                    (
                        SELECT COALESCE(SUM(p.plan_count), 0)
                        FROM fact.plan p
                        JOIN dim.year y ON y.id = p.year_id
                        WHERE (CAST(:year AS integer) IS NULL OR y.year_no = :year)
                    ) AS base_plan_count,
                    (
                        SELECT COALESCE(SUM(mv.plan_count), 0)
                        FROM analytics.mv_admissions_rollup mv
                        WHERE (CAST(:year AS integer) IS NULL OR mv.year_no = :year)
                    ) AS rollup_plan_count,
                    (
                        SELECT COUNT(*)
                        FROM fact.admission_record ar
                        JOIN dim.year y ON y.id = ar.year_id
                        WHERE (CAST(:year AS integer) IS NULL OR y.year_no = :year)
                    ) AS base_admitted_count,
                    (
                        SELECT COALESCE(SUM(mv.admitted_count), 0)
                        FROM analytics.mv_admissions_rollup mv
                        WHERE (CAST(:year AS integer) IS NULL OR mv.year_no = :year)
                    ) AS rollup_admitted_count
                """
            ),
            {"year": year},
        )
    ).mappings().one()
    return (
        int(row["base_plan_count"] or 0) == int(row["rollup_plan_count"] or 0)
        and int(row["base_admitted_count"] or 0) == int(row["rollup_admitted_count"] or 0)
    )


async def get_admissions_overview(
    db: AsyncSession,
    *,
    year: int | None = None,
    province: str | None = None,
    major: str | None = None,
) -> dict:
    where, params = _mv_where_clause(year=year, province=province, major=major)
    if not await _rollup_matches_base(db, year):
        await refresh_admissions_rollup(db)
        await db.commit()

    metric_sql = f"""
        SELECT
            COALESCE(SUM(mv.plan_count), 0) AS plan_count,
            COALESCE(SUM(mv.admitted_count), 0) AS admitted_count,
            MIN(CASE WHEN {MV_COMPARABLE_CULTURE_SCORE} THEN mv.min_score END) AS min_score,
            MAX(CASE WHEN {MV_COMPARABLE_CULTURE_SCORE} THEN mv.max_score END) AS max_score,
            MIN(CASE WHEN {MV_COMPARABLE_CULTURE_SCORE} THEN mv.min_rank_no END) AS min_rank_no
        FROM analytics.mv_admissions_rollup mv
        {where}
    """
    metrics = await db.execute(text(metric_sql), params)
    metric_row = metrics.mappings().one()
    plan_count = int(metric_row["plan_count"] or 0)
    admitted_count = int(metric_row["admitted_count"] or 0)
    completion_rate = round(admitted_count / plan_count * 100, 2) if plan_count else 0

    by_province_result = await db.execute(
        text(
            f"""
            SELECT
                mv.province_name,
                SUM(mv.plan_count) AS plan_count,
                SUM(mv.admitted_count) AS admitted_count,
                CASE WHEN SUM(mv.plan_count) > 0
                    THEN ROUND(SUM(mv.admitted_count) * 100.0 / SUM(mv.plan_count), 2)
                    ELSE 0
                END AS completion_rate,
                MIN(CASE WHEN {MV_COMPARABLE_CULTURE_SCORE} THEN mv.min_score END) AS min_score,
                MAX(CASE WHEN {MV_COMPARABLE_CULTURE_SCORE} THEN mv.max_score END) AS max_score,
                MIN(CASE WHEN {MV_COMPARABLE_CULTURE_SCORE} THEN mv.min_rank_no END) AS min_rank_no
            FROM analytics.mv_admissions_rollup mv
            {where}
            GROUP BY mv.province_name
            ORDER BY plan_count DESC
            """
        ),
        params,
    )

    by_major_result = await db.execute(
        text(
            f"""
            SELECT
                mv.canonical_major_name AS major_name,
                SUM(mv.plan_count) AS plan_count,
                SUM(mv.admitted_count) AS admitted_count,
                CASE WHEN SUM(mv.plan_count) > 0
                    THEN ROUND(SUM(mv.admitted_count) * 100.0 / SUM(mv.plan_count), 2)
                    ELSE 0
                END AS completion_rate,
                MIN(CASE WHEN {MV_COMPARABLE_CULTURE_SCORE} THEN mv.min_score END) AS min_score,
                MAX(CASE WHEN {MV_COMPARABLE_CULTURE_SCORE} THEN mv.max_score END) AS max_score,
                MIN(CASE WHEN {MV_COMPARABLE_CULTURE_SCORE} THEN mv.min_rank_no END) AS min_rank_no
            FROM analytics.mv_admissions_rollup mv
            {where}
            GROUP BY mv.canonical_major_name
            ORDER BY plan_count DESC
            """
        ),
        params,
    )

    trend_where, trend_params = _mv_where_clause(year=None, province=province, major=major)
    trend_result = await db.execute(
        text(
            f"""
            SELECT
                mv.year_no,
                SUM(mv.plan_count) AS plan_count,
                SUM(mv.admitted_count) AS admitted_count,
                CASE WHEN SUM(mv.plan_count) > 0
                    THEN ROUND(SUM(mv.admitted_count) * 100.0 / SUM(mv.plan_count), 2)
                    ELSE 0
                END AS completion_rate
            FROM analytics.mv_admissions_rollup mv
            {trend_where}
            GROUP BY mv.year_no
            ORDER BY mv.year_no
            """
        ),
        trend_params,
    )

    return {
        "filters": {"year": year, "province": province, "major": major},
        "metrics": {
            "plan_count": plan_count,
            "admitted_count": admitted_count,
            "completion_rate": completion_rate,
            "min_score": metric_row["min_score"],
            "max_score": metric_row["max_score"],
            "min_rank_no": metric_row["min_rank_no"],
            "score_scope": "普通类文化总分，排除专升本、体育、艺术及特殊计分专业",
        },
        "by_province": [dict(row) for row in by_province_result.mappings().all()],
        "by_major": [dict(row) for row in by_major_result.mappings().all()],
        "year_trend": [dict(row) for row in trend_result.mappings().all()],
    }


async def get_plans(
    db: AsyncSession,
    *,
    year: int | None = None,
    province: str | None = None,
    major: str | None = None,
    limit: int = 200,
) -> list[dict]:
    where, params = _where_clause(year=year, province=province, major=major)
    params["limit"] = limit
    result = await db.execute(
        text(
            f"""
            SELECT
                y.year_no,
                pr.province_name,
                b.batch_name,
                sub.subject_name,
                resolved_major.major_name,
                m.major_name AS source_major_name,
                p.plan_count,
                COALESCE(s.admitted_count, 0) AS admitted_count,
                s.min_score,
                s.min_rank_no,
                p.data_version
            {ADMISSION_FROM}
            JOIN dim.batch b ON b.id = p.batch_id
            {where}
            ORDER BY y.year_no DESC, pr.province_name, resolved_major.major_name
            LIMIT :limit
            """
        ),
        params,
    )
    return [dict(row) for row in result.mappings().all()]


async def get_source_overview(db: AsyncSession, *, year: int | None = None) -> dict:
    target_year = year or await db.scalar(text("SELECT MAX(year_no) FROM dim.year"))
    province_result = await db.execute(
        text(
            """
            SELECT
                pr.province_name,
                COUNT(*) AS candidate_count,
                COUNT(*) FILTER (WHERE ar.is_enrolled IS TRUE) AS enrolled_count,
                ROUND(AVG(ar.score), 2) AS avg_score
            FROM fact.admission_record ar
            JOIN dim.province pr ON pr.id = ar.province_id
            JOIN dim.year y ON y.id = ar.year_id
            WHERE y.year_no = :year
            GROUP BY pr.province_name
            ORDER BY candidate_count DESC
            """
        ),
        {"year": target_year},
    )
    channel_result = await db.execute(
        text(
            """
            SELECT
                COALESCE(c.channel_name, '未标注') AS channel_name,
                COUNT(*) AS candidate_count,
                COUNT(*) FILTER (WHERE ar.is_enrolled IS TRUE) AS enrolled_count,
                ROUND(AVG(ar.score), 2) AS avg_score
            FROM fact.admission_record ar
            JOIN dim.year y ON y.id = ar.year_id
            LEFT JOIN dim.channel c ON c.id = ar.channel_id
            WHERE y.year_no = :year
            GROUP BY COALESCE(c.channel_name, '未标注')
            ORDER BY candidate_count DESC
            """
        ),
        {"year": target_year},
    )
    total_candidates = await db.scalar(
        text(
            """
            SELECT COUNT(*)
            FROM fact.admission_record ar
            JOIN dim.year y ON y.id = ar.year_id
            WHERE y.year_no = :year
            """
        ),
        {"year": target_year},
    )
    official_total = await db.scalar(
        text(
            """
            SELECT COALESCE(SUM(total_admitted_count), 0)
            FROM fact.authoritative_admission_stat
            WHERE year_no = :year
              AND data_version LIKE 'official-%'
            """
        ),
        {"year": target_year},
    )
    enrolled_count = await db.scalar(
        text(
            """
            SELECT COUNT(*)
            FROM fact.admission_record ar
            JOIN dim.year y ON y.id = ar.year_id
            WHERE y.year_no = :year AND ar.is_enrolled IS TRUE
            """
        ),
        {"year": target_year},
    )
    enrollment_record_count = await db.scalar(
        text(
            """
            SELECT COUNT(*)
            FROM fact.enrollment_status
            WHERE year_no = :year
            """
        ),
        {"year": target_year},
    )
    dedicated_enrolled_count = await db.scalar(
        text(
            """
            SELECT COUNT(*)
            FROM fact.enrollment_status
            WHERE year_no = :year AND is_enrolled IS TRUE
            """
        ),
        {"year": target_year},
    )
    detail_count = int(total_candidates or 0)
    official_count = int(official_total or 0)
    total_count = official_count or detail_count
    coverage_rate = round(detail_count / official_count * 100, 2) if official_count else 0.0
    enrollment_records = int(enrollment_record_count or 0)
    enrollment_data_available = enrollment_records > 0
    enrolled_total = int(dedicated_enrolled_count or 0) if enrollment_data_available else int(enrolled_count or 0)
    return {
        "year_no": target_year,
        "metrics": {
            "official_total_count": official_count,
            "baseline_total_count": total_count,
            "candidate_count": detail_count,
            "detail_count": detail_count,
            "detail_gap_count": max(official_count - detail_count, 0),
            "coverage_rate": coverage_rate,
            "coverage_basis": "official" if official_count else "unverified",
            "detail_complete": bool(official_count > 0 and detail_count >= official_count),
            "enrollment_record_count": enrollment_records,
            "enrollment_data_available": enrollment_data_available,
            "enrolled_count": enrolled_total,
            "enrollment_rate": round(enrolled_total / detail_count * 100, 2)
            if detail_count
            else 0,
            "data_quality_status": (
                "complete"
                if official_count > 0 and detail_count >= official_count
                else "partial"
                if official_count > 0 and detail_count > 0
                else "unverified"
                if detail_count > 0
                else "missing"
            ),
        },
        "by_province": [dict(row) for row in province_result.mappings().all()],
        "by_channel": [dict(row) for row in channel_result.mappings().all()],
    }


async def get_candidate_profile_overview(
    db: AsyncSession,
    *,
    year: int | None = None,
    province: str | None = None,
    major: str | None = None,
) -> dict:
    joins = []
    clauses = []
    params: dict[str, object] = {}
    if year or province or major:
        joins.append("JOIN fact.admission_record ar ON ar.candidate_key = cp.candidate_key")
        joins.append("JOIN dim.year y ON y.id = ar.year_id")
    if province:
        joins.append("JOIN dim.province pr ON pr.id = ar.province_id")
        clauses.append("pr.province_name = :province")
        params["province"] = province
    if major:
        joins.append("JOIN dim.major m ON m.id = ar.major_id")
        joins.append(MAJOR_RESOLVE_JOIN_AR)
        clauses.append("resolved_major.major_name = :major")
        params["major"] = major
    if year:
        clauses.append("y.year_no = :year")
        params["year"] = year
    from_sql = "FROM fact.candidate_profile cp " + " ".join(joins)
    where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""

    total = await db.scalar(text(f"SELECT COUNT(DISTINCT cp.candidate_key) {from_sql} {where_sql}"), params)
    by_gender = await db.execute(
        text(
            f"""
            SELECT COALESCE(cp.gender_name, '未知') AS name,
                   COUNT(DISTINCT cp.candidate_key) AS count
            {from_sql}
            {where_sql}
            GROUP BY COALESCE(cp.gender_name, '未知')
            ORDER BY count DESC
            """
        ),
        params,
    )
    by_region = await db.execute(
        text(
            f"""
            SELECT COALESCE(cp.region_name, '未知') AS name,
                   COUNT(DISTINCT cp.candidate_key) AS count
            {from_sql}
            {where_sql}
            GROUP BY COALESCE(cp.region_name, '未知')
            ORDER BY count DESC
            LIMIT 30
            """
        ),
        params,
    )
    by_exam_type = await db.execute(
        text(
            f"""
            SELECT COALESCE(cp.exam_type_name, cp.exam_type_code, '未知') AS name,
                   COUNT(DISTINCT cp.candidate_key) AS count
            {from_sql}
            {where_sql}
            GROUP BY COALESCE(cp.exam_type_name, cp.exam_type_code, '未知')
            ORDER BY count DESC
            """
        ),
        params,
    )
    by_subject = await db.execute(
        text(
            f"""
            SELECT
                CASE cp.subject_category_code
                    WHEN 'W' THEN '物理类'
                    WHEN 'L' THEN '历史类'
                    WHEN 'Z' THEN '职高对口类'
                    ELSE COALESCE(cp.subject_category_code, '未知')
                END AS name,
                COUNT(DISTINCT cp.candidate_key) AS count
            {from_sql}
            {where_sql}
            GROUP BY cp.subject_category_code
            ORDER BY count DESC
            """
        ),
        params,
    )
    return {
        "metrics": {"candidate_count": int(total or 0)},
        "by_gender": [dict(row) for row in by_gender.mappings().all()],
        "by_region": [dict(row) for row in by_region.mappings().all()],
        "by_exam_type": [dict(row) for row in by_exam_type.mappings().all()],
        "by_subject": [dict(row) for row in by_subject.mappings().all()],
    }


async def get_subject_score_overview(
    db: AsyncSession,
    *,
    year: int | None = None,
    province: str | None = None,
    major: str | None = None,
) -> dict:
    joins = []
    clauses = []
    params: dict[str, object] = {}
    if year or province or major:
        joins.append("JOIN fact.admission_record ar ON ar.candidate_key = es.candidate_key")
        joins.append("JOIN dim.year y ON y.id = ar.year_id")
    if province:
        joins.append("JOIN dim.province pr ON pr.id = ar.province_id")
        clauses.append("pr.province_name = :province")
        params["province"] = province
    if major:
        joins.append("JOIN dim.major m ON m.id = ar.major_id")
        joins.append(MAJOR_RESOLVE_JOIN_AR)
        clauses.append("resolved_major.major_name = :major")
        params["major"] = major
    if year:
        clauses.append("y.year_no = :year")
        params["year"] = year
    where_sql = "WHERE es.score IS NOT NULL" + (" AND " + " AND ".join(clauses) if clauses else "")
    result = await db.execute(
        text(
            f"""
            SELECT
                es.subject_code,
                COALESCE(es.subject_name, es.subject_code) AS subject_name,
                COUNT(*) AS record_count,
                COUNT(DISTINCT es.candidate_key) AS candidate_count,
                ROUND(AVG(es.score), 2) AS avg_score,
                MIN(es.score) AS min_score,
                MAX(es.score) AS max_score,
                ROUND(STDDEV_POP(es.score), 2) AS score_stddev
            FROM fact.exam_subject_score es
            {' '.join(joins)}
            {where_sql}
            GROUP BY es.subject_code, COALESCE(es.subject_name, es.subject_code)
            ORDER BY es.subject_code
            """
        ),
        params,
    )
    return {"subjects": [dict(row) for row in result.mappings().all()]}


async def get_major_choice_overview(
    db: AsyncSession,
    *,
    year: int | None = None,
    major: str | None = None,
) -> dict:
    alias_count = int(
        await db.scalar(text("SELECT COUNT(*) FROM dim.major_alias WHERE is_active IS TRUE")) or 0
    )
    if alias_count:
        major_expr = "COALESCE(resolved_major.major_name, mc.major_name, mc.major_code)"
        from_sql = """
            FROM fact.major_choice mc
            LEFT JOIN LATERAL (
                SELECT ma.canonical_major_id
                FROM dim.major_alias ma
                WHERE ma.is_active
                  AND ma.province_id IS NULL
                  AND ma.source_name_key = lower(
                      replace(replace(replace(mc.major_name, '（', '('), '）', ')'), ' ', '')
                  )
                ORDER BY ma.id DESC
                LIMIT 1
            ) major_alias ON TRUE
            LEFT JOIN dim.major resolved_major ON resolved_major.id = major_alias.canonical_major_id
        """
    else:
        major_expr = "COALESCE(mc.major_name, mc.major_code)"
        from_sql = "FROM fact.major_choice mc"

    clauses = []
    params: dict[str, object] = {}
    if year:
        clauses.append("mc.year_no = :year")
        params["year"] = year
    if major:
        clauses.append(f"{major_expr} = :major")
        params["major"] = major
    where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""

    metrics = await db.execute(
        text(
            f"""
            SELECT COUNT(*) AS choice_count,
                   COUNT(DISTINCT mc.candidate_key) AS candidate_count
            {from_sql}
            {where_sql}
            """
        ),
        params,
    )
    metric_row = metrics.mappings().one()

    result = await db.execute(
        text(
            f"""
            SELECT
                {major_expr} AS major_name,
                COUNT(*) AS choice_count,
                COUNT(DISTINCT mc.candidate_key) AS candidate_count
            {from_sql}
            {where_sql}
            GROUP BY {major_expr}
            ORDER BY choice_count DESC
            """
        ),
        params,
    )
    return {
        "metrics": {
            "choice_count": int(metric_row["choice_count"] or 0),
            "candidate_count": int(metric_row["candidate_count"] or 0),
        },
        "majors": [dict(row) for row in result.mappings().all()],
    }


async def get_medical_overview(
    db: AsyncSession,
    *,
    year: int | None = None,
    province: str | None = None,
    major: str | None = None,
) -> dict:
    joins = []
    clauses = []
    params: dict[str, object] = {}
    if year or province or major:
        joins.append("JOIN fact.admission_record ar ON ar.candidate_key = ms.candidate_key")
        joins.append("JOIN dim.year y ON y.id = ar.year_id")
    if province:
        joins.append("JOIN dim.province pr ON pr.id = ar.province_id")
        clauses.append("pr.province_name = :province")
        params["province"] = province
    if major:
        joins.append("JOIN dim.major m ON m.id = ar.major_id")
        joins.append(MAJOR_RESOLVE_JOIN_AR)
        clauses.append("resolved_major.major_name = :major")
        params["major"] = major
    if year:
        clauses.append("y.year_no = :year")
        params["year"] = year
    where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""
    result = await db.execute(
        text(
            f"""
            SELECT
                COALESCE(ms.medical_result_name, ms.medical_result_code, '未知') AS result_name,
                COUNT(*) AS count
            FROM fact.medical_summary ms
            {' '.join(joins)}
            {where_sql}
            GROUP BY COALESCE(ms.medical_result_name, ms.medical_result_code, '未知')
            ORDER BY count DESC
            """
        ),
        params,
    )
    return {"medical_results": [dict(row) for row in result.mappings().all()]}


async def _get_major_year_metrics(db: AsyncSession, year_no: int) -> dict[str, dict[str, Any]]:
    result = await db.execute(
        text(
            f"""
            SELECT
                resolved_major.major_name,
                COALESCE(SUM(p.plan_count), 0) AS plan_count,
                COALESCE(SUM(ar.admitted_count), 0) AS admitted_count,
                MIN(ar.min_score) AS min_score,
                MAX(ar.max_score) AS max_score
            FROM fact.plan p
            JOIN dim.year y ON y.id = p.year_id
            JOIN dim.major m ON m.id = p.major_id
            {MAJOR_RESOLVE_JOIN}
            LEFT JOIN (
                SELECT year_id, province_id, major_id, subject_id, batch_id,
                       COUNT(*) AS admitted_count,
                       MIN(NULLIF(score, 0)) AS min_score,
                       MAX(NULLIF(score, 0)) AS max_score
                FROM fact.admission_record
                GROUP BY year_id, province_id, major_id, subject_id, batch_id
            ) ar
              ON ar.year_id = p.year_id
             AND ar.province_id = p.province_id
             AND ar.major_id = p.major_id
             AND ar.subject_id = p.subject_id
             AND ar.batch_id = p.batch_id
            WHERE y.year_no = :year
            GROUP BY resolved_major.major_name
            """
        ),
        {"year": year_no},
    )
    metrics = {row["major_name"]: dict(row) for row in result.mappings().all()}
    alias_count = int(
        await db.scalar(text("SELECT COUNT(*) FROM dim.major_alias WHERE is_active IS TRUE")) or 0
    )
    if alias_count:
        demand_sql = """
            SELECT
                COALESCE(resolved_major.major_name, mc.major_name, mc.major_code) AS major_name,
                COUNT(*) AS choice_count
            FROM fact.major_choice mc
            LEFT JOIN fact.admission_record ar ON ar.candidate_key = mc.candidate_key
            LEFT JOIN LATERAL (
                SELECT ma.canonical_major_id
                FROM dim.major_alias ma
                WHERE ma.is_active
                  AND ma.source_name_key = lower(
                      replace(replace(replace(mc.major_name, '（', '('), '）', ')'), ' ', '')
                  )
                  AND (ma.province_id IS NULL OR ma.province_id = ar.province_id)
                ORDER BY (ma.province_id IS NOT NULL) DESC, ma.id DESC
                LIMIT 1
            ) major_alias ON TRUE
            LEFT JOIN dim.major resolved_major ON resolved_major.id = major_alias.canonical_major_id
            WHERE mc.year_no = :year
            GROUP BY COALESCE(resolved_major.major_name, mc.major_name, mc.major_code)
        """
    else:
        demand_sql = """
            SELECT
                COALESCE(mc.major_name, mc.major_code) AS major_name,
                COUNT(*) AS choice_count
            FROM fact.major_choice mc
            WHERE mc.year_no = :year
            GROUP BY COALESCE(mc.major_name, mc.major_code)
        """
    demand_result = await db.execute(text(demand_sql), {"year": year_no})
    for row in demand_result.mappings().all():
        if row["major_name"] in metrics:
            metrics[row["major_name"]]["choice_count"] = int(row["choice_count"] or 0)
    for metric in metrics.values():
        metric.setdefault("choice_count", 0)
    return metrics

async def _resolve_data_year(db: AsyncSession, year: int | None) -> int | None:
    resolved = year if year is not None else await db.scalar(text("SELECT MAX(year_no) FROM dim.year"))
    return int(resolved) if resolved is not None else None


async def get_anomalies(db: AsyncSession, *, year: int | None = None) -> dict:
    latest_year = await _resolve_data_year(db, year)
    if latest_year is None:
        return {
            "year_no": None,
            "previous_year": None,
            "contains_synthetic": False,
            "summary": {"total_anomalies": 0, "high": 0, "medium": 0},
            "items": [],
            "message": "暂无可用于异常检测的年度数据。",
            "data_sources": [],
        }

    previous_year = latest_year - 1
    current = await _get_major_year_metrics(db, latest_year)
    previous = await _get_major_year_metrics(db, previous_year)

    items = []
    for major_name, current_metric in current.items():
        previous_metric = previous.get(major_name, {})
        plan_count = int(current_metric.get("plan_count") or 0)
        admitted_count = int(current_metric.get("admitted_count") or 0)
        prior_plan = int(previous_metric.get("plan_count") or 0)
        prior_admitted = int(previous_metric.get("admitted_count") or 0)
        choice_count = int(current_metric.get("choice_count") or 0)
        completion_rate = round(admitted_count / plan_count * 100, 2) if plan_count else 0
        demand_ratio = round(choice_count / plan_count, 2) if plan_count else 0
        plan_change = round((plan_count - prior_plan) / prior_plan * 100, 2) if prior_plan else 0
        admitted_change = (
            round((admitted_count - prior_admitted) / prior_admitted * 100, 2)
            if prior_admitted
            else 0
        )
        severity = "low"
        message = "指标波动处于正常范围"
        suggestion = "保持常规监测"

        if plan_count == 0 or admitted_count == 0:
            severity = "high"
            message = "该专业当前计划或录取数据为 0"
            suggestion = "核对招生计划和录取数据是否缺失"
        elif completion_rate < 95:
            severity = "high" if completion_rate < 90 else "medium"
            message = f"计划完成率仅 {completion_rate}%"
            suggestion = "核查缺额原因，评估宣传、选科要求或计划投放"
        elif demand_ratio >= 3:
            severity = "high"
            message = f"志愿热度为计划数的 {demand_ratio} 倍"
            suggestion = "评估增加计划或优化专业分流；需结合政策和培养能力决策"
        elif demand_ratio and demand_ratio < 0.5:
            severity = "medium"
            message = f"志愿热度仅为计划数的 {demand_ratio} 倍"
            suggestion = "加强专业宣传或评估减少计划"
        elif abs(plan_change) >= 15:
            severity = "medium"
            message = f"招生计划同比变化 {plan_change}%"
            suggestion = "核对计划调整依据和政策变化"
        elif abs(admitted_change) >= 15:
            severity = "medium"
            message = f"录取人数同比变化 {admitted_change}%"
            suggestion = "分析生源和志愿变化原因"

        if severity != "low":
            items.append(
                {
                    "major_name": major_name,
                    "severity": severity,
                    "message": message,
                    "suggestion": suggestion,
                    "plan_count": plan_count,
                    "admitted_count": admitted_count,
                    "completion_rate": completion_rate,
                    "demand_ratio": demand_ratio,
                    "plan_change_pct": plan_change,
                    "admitted_change_pct": admitted_change,
                }
            )

    severity_order = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda item: (severity_order[item["severity"]], -item["demand_ratio"]))
    contains_synthetic = latest_year <= 2025
    return {
        "year_no": latest_year,
        "previous_year": previous_year,
        "contains_synthetic": contains_synthetic,
        "summary": {
            "total_anomalies": len(items),
            "high": sum(1 for item in items if item["severity"] == "high"),
            "medium": sum(1 for item in items if item["severity"] == "medium"),
        },
        "items": items[:100],
        "data_sources": [
            {"table": "fact.plan", "metric": "招生计划"},
            {"table": "fact.admission_record", "metric": "录取完成率"},
            {"table": "fact.major_choice", "metric": "志愿热度"},
        ],
    }


async def simulate_plan(
    db: AsyncSession,
    *,
    year: int | None = None,
    adjustments: list[dict],
) -> dict:
    latest_year = await _resolve_data_year(db, year)
    if latest_year is None:
        return {
            "year_no": None,
            "contains_synthetic": False,
            "baseline": {"plan_count": 0, "admitted_count": 0, "completion_rate": 0},
            "projected": {"plan_count": 0, "admitted_count": 0, "completion_rate": 0},
            "results": [],
            "unmatched_adjustments": [],
            "message": "暂无可用于计划模拟的年度数据。",
            "disclaimer": "模拟未执行。",
            "data_sources": [],
        }

    metrics = await _get_major_year_metrics(db, latest_year)
    adjustment_map: dict[str, int] = {}
    for item in adjustments:
        major_name = str(item.get("major_name") or "").strip()
        if not major_name:
            continue
        adjustment_map[major_name] = adjustment_map.get(major_name, 0) + int(item.get("plan_delta") or 0)

    unmatched_adjustments = sorted(name for name in adjustment_map if name not in metrics)
    baseline_total_plan = 0
    baseline_total_admitted = 0
    projected_total_plan = 0
    projected_total_admitted = 0
    results = []

    for major_name, metric in metrics.items():
        plan_count = int(metric.get("plan_count") or 0)
        admitted_count = int(metric.get("admitted_count") or 0)
        choice_count = int(metric.get("choice_count") or 0)
        delta = adjustment_map.get(major_name, 0)
        new_plan = max(0, plan_count + delta)
        demand_factor = min(1.2, max(0.5, (choice_count / plan_count / 3) if plan_count else 0.5))
        projected_admitted = (
            min(new_plan, max(0, round(admitted_count + delta * demand_factor)))
            if new_plan
            else 0
        )
        projected_completion = round(projected_admitted / new_plan * 100, 2) if new_plan else 0
        projected_score_change = round(-delta * 0.08, 2)
        risk_level = "low"
        if projected_completion < 90:
            risk_level = "high"
        elif projected_completion < 95:
            risk_level = "medium"
        if choice_count >= plan_count * 3 and new_plan <= plan_count:
            risk_level = "high" if risk_level == "low" else risk_level

        baseline_total_plan += plan_count
        baseline_total_admitted += admitted_count
        projected_total_plan += new_plan
        projected_total_admitted += projected_admitted

        if delta:
            results.append(
                {
                    "major_name": major_name,
                    "plan_delta": delta,
                    "baseline_plan": plan_count,
                    "baseline_admitted": admitted_count,
                    "baseline_completion_rate": round(admitted_count / plan_count * 100, 2)
                    if plan_count
                    else 0,
                    "projected_plan": new_plan,
                    "projected_admitted": projected_admitted,
                    "projected_completion_rate": projected_completion,
                    "projected_score_change": projected_score_change,
                    "risk_level": risk_level,
                    "choice_count": choice_count,
                }
            )

    severity_order = {"high": 0, "medium": 1, "low": 2}
    results.sort(key=lambda item: (severity_order[item["risk_level"]], -abs(item["plan_delta"])))
    return {
        "year_no": latest_year,
        "contains_synthetic": latest_year <= 2025,
        "baseline": {
            "plan_count": baseline_total_plan,
            "admitted_count": baseline_total_admitted,
            "completion_rate": round(baseline_total_admitted / baseline_total_plan * 100, 2)
            if baseline_total_plan
            else 0,
        },
        "projected": {
            "plan_count": projected_total_plan,
            "admitted_count": projected_total_admitted,
            "completion_rate": round(projected_total_admitted / projected_total_plan * 100, 2)
            if projected_total_plan
            else 0,
        },
        "results": results,
        "unmatched_adjustments": unmatched_adjustments,
        "disclaimer": "本结果为基于历史计划、录取和志愿热度的启发式模拟，不代表因果结论，最终仍需结合政策和培养能力判断。",
        "data_sources": [
            {"table": "fact.plan", "metric": "基准招生计划"},
            {"table": "fact.admission_record", "metric": "基准录取"},
            {"table": "fact.major_choice", "metric": "需求弹性启发式参数"},
        ],
    }













