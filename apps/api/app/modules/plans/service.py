from __future__ import annotations

from typing import Any

from app.core.text import text
from app.core.config import settings
from app.core.db_compat import execute_returning_id, is_mysql
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.data_change import notify_data_changed
from app.modules.plans.schemas import PlanUpsert


def _manual_version(year_no: int) -> str:
    return f"manual-{year_no}-v1"


async def _school_id(db: AsyncSession) -> int:
    value = await db.scalar(text("SELECT id FROM dim.school ORDER BY id LIMIT 1"))
    if value is None:
        raise ValueError("学校基础资料尚未初始化")
    return int(value)


async def _validate_dimensions(db: AsyncSession, payload: PlanUpsert) -> tuple[int, int]:
    school_id = await _school_id(db)
    year_id = await db.scalar(text("SELECT id FROM dim.year WHERE year_no = :year"), {"year": payload.year_no})
    if year_id is None:
        raise ValueError("招生年度不存在")
    checks = (
        ("province", "SELECT id FROM dim.province WHERE id = :id", payload.province_id),
        ("major", "SELECT id FROM dim.major WHERE id = :id AND is_active IS TRUE", payload.major_id),
        ("subject", "SELECT id FROM dim.subject WHERE id = :id", payload.subject_id),
    )
    for label, sql, identifier in checks:
        if await db.scalar(text(sql), {"id": identifier}) is None:
            raise ValueError(f"{label} 维度不存在或不可用")
    batch_row = (
        await db.execute(
            text("SELECT id, year_id FROM dim.batch WHERE id = :id"),
            {"id": payload.batch_id},
        )
    ).mappings().one_or_none()
    if batch_row is None:
        raise ValueError("批次不存在")
    if batch_row["year_id"] is not None and int(batch_row["year_id"]) != int(year_id):
        raise ValueError("所选批次不属于当前招生年度")
    if payload.plan_type_id is not None:
        if await db.scalar(text("SELECT id FROM dim.plan_type WHERE id = :id"), {"id": payload.plan_type_id}) is None:
            raise ValueError("计划类型不存在")
    return school_id, int(year_id)


async def _duplicate_exists(
    db: AsyncSession,
    *,
    payload: PlanUpsert,
    school_id: int,
    year_id: int,
    exclude_id: int | None = None,
) -> bool:
    result = await db.scalar(
        text("""
            SELECT id
            FROM fact.plan
            WHERE year_id = :year_id
              AND school_id = :school_id
              AND province_id = :province_id
              AND batch_id = :batch_id
              AND subject_id = :subject_id
              AND major_id = :major_id
              AND COALESCE(plan_type_id, 0) = COALESCE(CAST(:plan_type_id AS bigint), 0)
              AND data_version = :data_version
              AND (CAST(:exclude_id AS bigint) IS NULL OR id <> :exclude_id)
            LIMIT 1
            """
        ),
        {
            "year_id": year_id,
            "school_id": school_id,
            "province_id": payload.province_id,
            "batch_id": payload.batch_id,
            "subject_id": payload.subject_id,
            "major_id": payload.major_id,
            "plan_type_id": payload.plan_type_id,
            "data_version": _manual_version(payload.year_no),
            "exclude_id": exclude_id,
        },
    )
    return result is not None


async def _get_plan(db: AsyncSession, plan_id: int) -> dict[str, Any] | None:
    row = (
        await db.execute(
            text(
                """
                SELECT
                    p.id,
                    y.year_no,
                    s.school_name,
                    pr.province_name,
                    b.batch_name,
                    sub.subject_name,
                    m.major_name,
                    pt.type_name AS plan_type_name,
                    p.plan_count,
                    p.tuition,
                    p.data_version,
                    p.created_at,
                    (p.data_version LIKE 'manual-%') AS is_editable
                FROM fact.plan p
                JOIN dim.year y ON y.id = p.year_id
                JOIN dim.school s ON s.id = p.school_id
                JOIN dim.province pr ON pr.id = p.province_id
                JOIN dim.batch b ON b.id = p.batch_id
                JOIN dim.subject sub ON sub.id = p.subject_id
                JOIN dim.major m ON m.id = p.major_id
                LEFT JOIN dim.plan_type pt ON pt.id = p.plan_type_id
                WHERE p.id = :plan_id
                """
            ),
            {"plan_id": plan_id},
        )
    ).mappings().one_or_none()
    return dict(row) if row else None


async def get_plan_options(db: AsyncSession) -> dict[str, Any]:
    years = await db.execute(text("SELECT id, year_no FROM dim.year ORDER BY year_no DESC"))
    provinces = await db.execute(
        text("SELECT id, province_code, province_name FROM dim.province ORDER BY province_name")
    )
    batches = await db.execute(
        text(
            """
            SELECT b.id, b.batch_code, b.batch_name, y.year_no
            FROM dim.batch b
            LEFT JOIN dim.year y ON y.id = b.year_id
            ORDER BY COALESCE(y.year_no, 0) DESC, b.batch_name
            """
        )
    )
    subjects = await db.execute(text("SELECT id, subject_code, subject_name FROM dim.subject ORDER BY id"))
    majors = await db.execute(
        text("SELECT id, major_code, major_name FROM dim.major WHERE is_active IS TRUE ORDER BY major_name")
    )
    plan_types = await db.execute(text("SELECT id, type_code, type_name FROM dim.plan_type ORDER BY id"))
    schools = await db.execute(text("SELECT id, school_name FROM dim.school ORDER BY id"))
    return {
        "years": [dict(row) for row in years.mappings().all()],
        "provinces": [dict(row) for row in provinces.mappings().all()],
        "batches": [dict(row) for row in batches.mappings().all()],
        "subjects": [dict(row) for row in subjects.mappings().all()],
        "majors": [dict(row) for row in majors.mappings().all()],
        "plan_types": [dict(row) for row in plan_types.mappings().all()],
        "schools": [dict(row) for row in schools.mappings().all()],
    }


async def list_plans(
    db: AsyncSession,
    *,
    year: int | None = None,
    province_id: int | None = None,
    batch_id: int | None = None,
    subject_id: int | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    clauses = ["1 = 1"]
    params: dict[str, Any] = {"limit": page_size, "offset": (page - 1) * page_size}
    if year is not None:
        clauses.append("y.year_no = :year")
        params["year"] = year
    if province_id is not None:
        clauses.append("p.province_id = :province_id")
        params["province_id"] = province_id
    if batch_id is not None:
        clauses.append("p.batch_id = :batch_id")
        params["batch_id"] = batch_id
    if subject_id is not None:
        clauses.append("p.subject_id = :subject_id")
        params["subject_id"] = subject_id
    if keyword:
        clauses.append("(m.major_name ILIKE :keyword OR m.major_code ILIKE :keyword OR pr.province_name ILIKE :keyword)")
        params["keyword"] = f"%{keyword.strip()}%"
    where_sql = " AND ".join(clauses)
    base_from = """
        FROM fact.plan p
        JOIN dim.year y ON y.id = p.year_id
        JOIN dim.school s ON s.id = p.school_id
        JOIN dim.province pr ON pr.id = p.province_id
        JOIN dim.batch b ON b.id = p.batch_id
        JOIN dim.subject sub ON sub.id = p.subject_id
        JOIN dim.major m ON m.id = p.major_id
        LEFT JOIN dim.plan_type pt ON pt.id = p.plan_type_id
    """
    filter_params = {key: value for key, value in params.items() if key not in {"limit", "offset"}}
    count = await db.scalar(text(f"SELECT COUNT(*) {base_from} WHERE {where_sql}"), filter_params)
    metrics = await db.execute(
        text(
            f"""
            SELECT
                COALESCE(SUM(p.plan_count), 0) AS total_plan_count,
                COUNT(DISTINCT p.province_id) AS province_count,
                COUNT(DISTINCT p.major_id) AS major_count,
                COUNT(*) FILTER (WHERE p.data_version LIKE 'manual-%') AS manual_count
            {base_from}
            WHERE {where_sql}
            """
        ),
        filter_params,
    )
    rows = await db.execute(
        text(
            f"""
            SELECT
                p.id,
                y.year_no,
                s.school_name,
                p.province_id,
                pr.province_name,
                p.batch_id,
                b.batch_name,
                p.subject_id,
                sub.subject_name,
                p.major_id,
                m.major_name,
                p.plan_type_id,
                pt.type_name AS plan_type_name,
                p.plan_count,
                p.tuition,
                p.data_version,
                p.created_at,
                (p.data_version LIKE 'manual-%') AS is_editable
            {base_from}
            WHERE {where_sql}
            ORDER BY y.year_no DESC, pr.province_name, m.major_name, p.id
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    )
    metric_row = metrics.mappings().one()
    return {
        "items": [dict(row) for row in rows.mappings().all()],
        "total": int(count or 0),
        "page": page,
        "page_size": page_size,
        "summary": {
            "total_plan_count": int(metric_row["total_plan_count"] or 0),
            "province_count": int(metric_row["province_count"] or 0),
            "major_count": int(metric_row["major_count"] or 0),
            "manual_count": int(metric_row["manual_count"] or 0),
        },
    }


async def create_plan(db: AsyncSession, payload: PlanUpsert) -> dict[str, Any]:
    school_id, year_id = await _validate_dimensions(db, payload)
    if await _duplicate_exists(db, payload=payload, school_id=school_id, year_id=year_id):
        raise ValueError("相同年度、省份、批次、科类、专业和计划类型的手工计划已存在")
    plan_id = await execute_returning_id(
        db,
        """
        INSERT INTO fact.plan (
                school_id, year_id, province_id, batch_id, subject_id, major_id,
                plan_type_id, plan_count, tuition, policy_id, data_version
            )
            VALUES (
                :school_id, :year_id, :province_id, :batch_id, :subject_id, :major_id,
                :plan_type_id, :plan_count, :tuition, NULL, :data_version
            )
        RETURNING id
        """,
        {
            "school_id": school_id,
            "year_id": year_id,
            "province_id": payload.province_id,
            "batch_id": payload.batch_id,
            "subject_id": payload.subject_id,
            "major_id": payload.major_id,
            "plan_type_id": payload.plan_type_id,
            "plan_count": payload.plan_count,
            "tuition": payload.tuition,
            "data_version": _manual_version(payload.year_no),
        },
    )
    await db.commit()
    await notify_data_changed(school_id)
    created = await _get_plan(db, int(plan_id))
    return created or {}


async def update_plan(db: AsyncSession, plan_id: int, payload: PlanUpsert) -> dict[str, Any]:
    existing = await _get_plan(db, plan_id)
    if existing is None:
        raise ValueError("招生计划不存在")
    if not existing["is_editable"]:
        raise ValueError("导入的招生计划为只读数据，请在数据导入模块中修订")
    school_id, year_id = await _validate_dimensions(db, payload)
    if await _duplicate_exists(
        db,
        payload=payload,
        school_id=school_id,
        year_id=year_id,
        exclude_id=plan_id,
    ):
        raise ValueError("修改后与已有手工计划重复")
    await db.execute(
        text("""
            UPDATE fact.plan
            SET school_id = :school_id,
                year_id = :year_id,
                province_id = :province_id,
                batch_id = :batch_id,
                subject_id = :subject_id,
                major_id = :major_id,
                plan_type_id = :plan_type_id,
                plan_count = :plan_count,
                tuition = :tuition,
                data_version = :data_version
            WHERE id = :plan_id
            """
        ),
        {
            "plan_id": plan_id,
            "school_id": school_id,
            "year_id": year_id,
            "province_id": payload.province_id,
            "batch_id": payload.batch_id,
            "subject_id": payload.subject_id,
            "major_id": payload.major_id,
            "plan_type_id": payload.plan_type_id,
            "plan_count": payload.plan_count,
            "tuition": payload.tuition,
            "data_version": _manual_version(payload.year_no),
        },
    )
    await db.commit()
    await notify_data_changed(school_id)
    updated = await _get_plan(db, plan_id)
    return updated or {}


async def delete_plan(db: AsyncSession, plan_id: int) -> dict[str, Any]:
    existing = await _get_plan(db, plan_id)
    if existing is None:
        raise ValueError("招生计划不存在")
    if not existing["is_editable"]:
        raise ValueError("导入的招生计划为只读数据，不能删除")
    await db.execute(text("DELETE FROM fact.admission_summary WHERE plan_id = :plan_id"), {"plan_id": plan_id})
    await db.execute(text("DELETE FROM fact.plan WHERE id = :plan_id"), {"plan_id": plan_id})
    await db.commit()
    await notify_data_changed()
    return {"id": plan_id, "deleted": True}


async def copy_plans(db: AsyncSession, *, source_year: int, target_year: int) -> dict[str, Any]:
    if source_year == target_year:
        raise ValueError("来源年度和目标年度不能相同")
    target_year_id = await db.scalar(text("SELECT id FROM dim.year WHERE year_no = :year"), {"year": target_year})
    if target_year_id is None:
        raise ValueError("目标年度不存在，请先初始化年度")
    source_count = await db.scalar(
        text(
            """
            SELECT COUNT(*)
            FROM fact.plan p
            JOIN dim.year y ON y.id = p.year_id
            WHERE y.year_no = :year
            """
        ),
        {"year": source_year},
    )
    if not source_count:
        raise ValueError("来源年度没有可复制的招生计划")
    params = {
        "source_year": source_year,
        "target_year_id": target_year_id,
        "data_version": _manual_version(target_year),
    }
    if is_mysql():
        result = await db.execute(
            text(
                """
                INSERT IGNORE INTO fact.plan (
                    school_id, year_id, province_id, batch_id, subject_id, major_id,
                    plan_type_id, plan_count, tuition, policy_id, data_version
                )
                WITH source_plans AS (
                    SELECT
                        p.school_id, p.province_id, target_batch.id AS batch_id,
                        p.subject_id, p.major_id, p.plan_type_id,
                        p.plan_count, p.tuition,
                        ROW_NUMBER() OVER (
                            PARTITION BY
                                p.school_id, p.province_id, target_batch.id,
                                p.subject_id, p.major_id, COALESCE(p.plan_type_id, 0)
                            ORDER BY p.created_at DESC, p.id DESC
                        ) AS row_no
                    FROM fact.plan p
                    JOIN dim.year y ON y.id = p.year_id
                    JOIN dim.batch source_batch ON source_batch.id = p.batch_id
                    JOIN dim.batch target_batch
                      ON target_batch.year_id = :target_year_id
                     AND target_batch.batch_code = source_batch.batch_code
                    WHERE y.year_no = :source_year
                )
                SELECT
                    sp.school_id, :target_year_id, sp.province_id, sp.batch_id,
                    sp.subject_id, sp.major_id, sp.plan_type_id,
                    sp.plan_count, sp.tuition, NULL, :data_version
                FROM source_plans sp
                WHERE sp.row_no = 1
                  AND NOT EXISTS (
                    SELECT 1
                    FROM fact.plan existing
                    WHERE existing.year_id = :target_year_id
                      AND existing.school_id = sp.school_id
                      AND existing.province_id = sp.province_id
                      AND existing.batch_id = sp.batch_id
                      AND existing.subject_id = sp.subject_id
                      AND existing.major_id = sp.major_id
                      AND COALESCE(existing.plan_type_id, 0) = COALESCE(sp.plan_type_id, 0)
                      AND existing.data_version = :data_version
                  )
                """
            ),
            params,
        )
        created_count = max(int(result.rowcount or 0), 0)
    else:
        result = await db.execute(
            text(
                """
                WITH source_plans AS (
                    SELECT DISTINCT ON (
                        p.school_id, p.province_id, target_batch.id,
                        p.subject_id, p.major_id, COALESCE(p.plan_type_id, 0)
                    )
                        p.school_id, p.province_id, target_batch.id AS batch_id,
                        p.subject_id, p.major_id, p.plan_type_id,
                        p.plan_count, p.tuition
                    FROM fact.plan p
                    JOIN dim.year y ON y.id = p.year_id
                    JOIN dim.batch source_batch ON source_batch.id = p.batch_id
                    JOIN dim.batch target_batch
                      ON target_batch.year_id = :target_year_id
                     AND target_batch.batch_code = source_batch.batch_code
                    WHERE y.year_no = :source_year
                    ORDER BY
                        p.school_id, p.province_id, target_batch.id,
                        p.subject_id, p.major_id, COALESCE(p.plan_type_id, 0),
                        p.created_at DESC, p.id DESC
                )
                INSERT INTO fact.plan (
                    school_id, year_id, province_id, batch_id, subject_id, major_id,
                    plan_type_id, plan_count, tuition, policy_id, data_version
                )
                SELECT
                    sp.school_id, :target_year_id, sp.province_id, sp.batch_id,
                    sp.subject_id, sp.major_id, sp.plan_type_id,
                    sp.plan_count, sp.tuition, NULL, :data_version
                FROM source_plans sp
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM fact.plan existing
                    WHERE existing.year_id = :target_year_id
                      AND existing.school_id = sp.school_id
                      AND existing.province_id = sp.province_id
                      AND existing.batch_id = sp.batch_id
                      AND existing.subject_id = sp.subject_id
                      AND existing.major_id = sp.major_id
                      AND COALESCE(existing.plan_type_id, 0) = COALESCE(sp.plan_type_id, 0)
                      AND existing.data_version = :data_version
                )
                RETURNING id
                """
            ),
            params,
        )
        created_count = len(result.fetchall())
    await db.commit()
    await notify_data_changed()
    return {
        "source_year": source_year,
        "target_year": target_year,
        "created_count": created_count,
        "skipped_count": int(source_count) - created_count,
        "data_version": _manual_version(target_year),
    }




async def create_year(db: AsyncSession, year_no: int) -> dict[str, Any]:
    year_id = await execute_returning_id(
        db,
        """
        INSERT INTO dim.year (year_no)
        VALUES (:year_no)
        ON CONFLICT (year_no) DO NOTHING
        RETURNING id
        """,
        {"year_no": year_no},
        mysql_select="SELECT id FROM dim.year WHERE year_no=:year_no LIMIT 1",
    )
    if year_id is None:
        year_id = await db.scalar(text("SELECT id FROM dim.year WHERE year_no = :year_no"), {"year_no": year_no})
    await db.execute(
        text(
            """
            INSERT INTO dim.batch (year_id, batch_code, batch_name)
            SELECT
                :year_id,
                source.batch_code,
                source.batch_name
            FROM dim.batch source
            JOIN dim.year source_year ON source_year.id = source.year_id
            WHERE source_year.year_no = (
                SELECT MAX(year_no)
                FROM dim.year
                WHERE year_no < :year_no
            )
              AND NOT EXISTS (
                SELECT 1
                FROM dim.batch existing
                WHERE existing.year_id = :year_id
                  AND existing.batch_code = source.batch_code
              )
            """
        ),
        {"year_id": year_id, "year_no": year_no},
    )
    await db.commit()
    return {"id": int(year_id), "year_no": year_no}




