import unicodedata
from typing import Any

from app.core.text import text
from app.core.db_compat import execute_returning_id
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.data_change import notify_data_changed
from app.modules.major_aliases.schemas import MajorAliasUpsert, MajorRenameRequest


def normalize_major_name(value: str) -> str:
    text_value = unicodedata.normalize("NFKC", value or "").strip().lower()
    text_value = text_value.replace("（", "(").replace("）", ")")
    return "".join(text_value.split())


async def list_aliases(db: AsyncSession) -> dict[str, Any]:
    result = await db.execute(
        text("""
            SELECT
                ma.id,
                ma.source_name,
                ma.source_name_key,
                ma.province_id,
                p.province_name,
                ma.canonical_major_id,
                cm.major_name AS canonical_major_name,
                ma.note,
                ma.is_active,
                ma.created_at,
                ma.updated_at,
                COALESCE(source_majors.source_major_count, 0) AS source_major_count,
                COALESCE(plan_usage.plan_count, 0) AS affected_plan_count,
                COALESCE(record_usage.record_count, 0) AS affected_record_count
            FROM dim.major_alias ma
            LEFT JOIN dim.province p ON p.id = ma.province_id
            JOIN dim.major cm ON cm.id = ma.canonical_major_id
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS source_major_count
                FROM dim.major m
                WHERE m.major_name = ma.source_name
            ) source_majors ON TRUE
            LEFT JOIN LATERAL (
                SELECT SUM(fp.plan_count) AS plan_count
                FROM fact.plan fp
                JOIN dim.major m ON m.id = fp.major_id
                WHERE m.major_name = ma.source_name
                  AND (ma.province_id IS NULL OR fp.province_id = ma.province_id)
            ) plan_usage ON TRUE
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS record_count
                FROM fact.admission_record ar
                JOIN dim.major m ON m.id = ar.major_id
                WHERE m.major_name = ma.source_name
                  AND (ma.province_id IS NULL OR ar.province_id = ma.province_id)
            ) record_usage ON TRUE
            ORDER BY ma.is_active DESC, COALESCE(p.province_name, '全局'), ma.source_name
            """
        )
    )
    return {"items": [dict(row) for row in result.mappings().all()]}


async def get_alias_options(db: AsyncSession) -> dict[str, Any]:
    provinces = await db.execute(text("SELECT id, province_code, province_name FROM dim.province ORDER BY province_name"))
    majors = await db.execute(
        text(
            """
            SELECT
                m.id,
                m.major_code,
                m.major_name,
                COUNT(p.id) AS plan_record_count,
                COALESCE(SUM(p.plan_count), 0) AS plan_count
            FROM dim.major m
            LEFT JOIN fact.plan p ON p.major_id = m.id
            WHERE m.is_active IS TRUE
            GROUP BY m.id, m.major_code, m.major_name
            ORDER BY m.major_name, m.major_code
            """
        )
    )
    return {
        "provinces": [dict(row) for row in provinces.mappings().all()],
        "majors": [dict(row) for row in majors.mappings().all()],
    }


async def _duplicate_exists(
    db: AsyncSession,
    *,
    source_name_key: str,
    province_id: int | None,
    exclude_id: int | None = None,
) -> bool:
    value = await db.scalar(
        text(
            """
            SELECT id
            FROM dim.major_alias
            WHERE source_name_key = :source_name_key
              AND COALESCE(province_id, 0) = COALESCE(CAST(:province_id AS bigint), 0)
              AND (CAST(:exclude_id AS bigint) IS NULL OR id <> :exclude_id)
            LIMIT 1
            """
        ),
        {
            "source_name_key": source_name_key,
            "province_id": province_id,
            "exclude_id": exclude_id,
        },
    )
    return value is not None


async def _validate(db: AsyncSession, payload: MajorAliasUpsert) -> tuple[str, int | None]:
    source_name = payload.source_name.strip()
    source_key = normalize_major_name(source_name)
    if not source_key:
        raise ValueError("来源专业名称不能为空")
    canonical = await db.scalar(
        text("SELECT id FROM dim.major WHERE id = :id AND is_active IS TRUE"),
        {"id": payload.canonical_major_id},
    )
    if canonical is None:
        raise ValueError("标准专业不存在或已停用")
    if payload.province_id is not None:
        province = await db.scalar(text("SELECT id FROM dim.province WHERE id = :id"), {"id": payload.province_id})
        if province is None:
            raise ValueError("省份不存在")
    canonical_name = await db.scalar(text("SELECT major_name FROM dim.major WHERE id = :id"), {"id": payload.canonical_major_id})
    if normalize_major_name(str(canonical_name)) == source_key:
        raise ValueError("来源名称与标准专业名称相同，无需建立别名")
    return source_name, source_key


async def create_alias(db: AsyncSession, payload: MajorAliasUpsert) -> dict[str, Any]:
    source_name, source_key = await _validate(db, payload)
    if await _duplicate_exists(db, source_name_key=source_key, province_id=payload.province_id):
        raise ValueError("该来源名称在相同省份范围内已存在映射")
    alias_id = await execute_returning_id(
        db,
        """
        INSERT INTO dim.major_alias (
                source_name, source_name_key, province_id, canonical_major_id,
                note, is_active, updated_at
            )
            VALUES (
                :source_name, :source_name_key, :province_id, :canonical_major_id,
                :note, :is_active, now()
            )
        RETURNING id
        """,
        {
            "source_name": source_name,
            "source_name_key": source_key,
            "province_id": payload.province_id,
            "canonical_major_id": payload.canonical_major_id,
            "note": payload.note,
            "is_active": payload.is_active,
        },
    )
    await db.commit()
    await notify_data_changed()
    return {"id": int(alias_id)}


async def update_alias(db: AsyncSession, alias_id: int, payload: MajorAliasUpsert) -> dict[str, Any]:
    source_name, source_key = await _validate(db, payload)
    if await _duplicate_exists(db, source_name_key=source_key, province_id=payload.province_id, exclude_id=alias_id):
        raise ValueError("该来源名称在相同省份范围内已存在映射")
    result = await db.execute(
        text(
            """
            UPDATE dim.major_alias
            SET source_name = :source_name,
                source_name_key = :source_name_key,
                province_id = :province_id,
                canonical_major_id = :canonical_major_id,
                note = :note,
                is_active = :is_active,
                updated_at = now()
            WHERE id = :alias_id
            """
        ),
        {
            "alias_id": alias_id,
            "source_name": source_name,
            "source_name_key": source_key,
            "province_id": payload.province_id,
            "canonical_major_id": payload.canonical_major_id,
            "note": payload.note,
            "is_active": payload.is_active,
        },
    )
    if result.rowcount == 0:
        raise ValueError("专业别名不存在")
    await db.commit()
    await notify_data_changed()
    return {"id": alias_id}


async def delete_alias(db: AsyncSession, alias_id: int) -> dict[str, Any]:
    result = await db.execute(text("DELETE FROM dim.major_alias WHERE id = :alias_id"), {"alias_id": alias_id})
    if result.rowcount == 0:
        raise ValueError("专业别名不存在")
    await db.commit()
    await notify_data_changed()
    return {"id": alias_id, "deleted": True}


async def rename_major(db: AsyncSession, major_id: int, payload: MajorRenameRequest) -> dict[str, Any]:
    row = (
        await db.execute(
            text(
                """
                SELECT id, school_id, major_code, major_name
                FROM dim.major
                WHERE id = :major_id
                """
            ),
            {"major_id": major_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise ValueError("标准专业不存在")
    new_name = payload.major_name.strip()
    new_key = normalize_major_name(new_name)
    if not new_key:
        raise ValueError("专业名称不能为空")
    if new_name != row["major_name"]:
        duplicate = await db.scalar(
            text(
                """
                SELECT id
                FROM dim.major
                WHERE school_id = :school_id
                  AND major_name = :major_name
                  AND id <> :major_id
                LIMIT 1
                """
            ),
            {
                "school_id": row["school_id"],
                "major_name": new_name,
                "major_id": major_id,
            },
        )
        if duplicate is not None:
            plan_count = await db.scalar(
                text("SELECT COUNT(*) FROM fact.plan WHERE major_id = :major_id"),
                {"major_id": major_id},
            )
            if int(plan_count or 0) > 0:
                raise ValueError("同名专业已存在且当前专业已有计划数据；如需合并统计，请使用专业别名映射")

    await db.execute(
        text("UPDATE dim.major SET major_name = :major_name WHERE id = :major_id"),
        {"major_name": new_name, "major_id": major_id},
    )
    choice_result = await db.execute(
        text(
            """
            UPDATE fact.major_choice
            SET major_name = :new_name
            WHERE major_code = :major_code
              AND major_name = :old_name
            """
        ),
        {
            "new_name": new_name,
            "major_code": row["major_code"],
            "old_name": row["major_name"],
        },
    )
    alias_result = await db.execute(
        text(
            """
            UPDATE dim.major_alias
            SET source_name = :new_name,
                source_name_key = :new_key,
                updated_at = now()
            WHERE source_name = :old_name
            """
        ),
        {
            "new_name": new_name,
            "new_key": new_key,
            "old_name": row["major_name"],
        },
    )
    await db.commit()
    await notify_data_changed(row["school_id"])
    return {
        "id": major_id,
        "old_name": row["major_name"],
        "new_name": new_name,
        "major_code": row["major_code"],
        "updated_choices": choice_result.rowcount,
        "updated_aliases": alias_result.rowcount,
    }




