from __future__ import annotations

import hashlib
import json
from typing import Any

from app.core.text import text
from app.core.db_compat import execute_returning_row
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ingestion.dbf_catalog import DBF_TABLE_CATALOG


def _catalog_checksum() -> str:
    payload = json.dumps(DBF_TABLE_CATALOG, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def get_or_create_dbf_profile(db: AsyncSession, school_id: int) -> dict[str, Any]:
    result = await db.execute(
        text("""
            SELECT id, school_id, profile_code, profile_name, schema_version,
                   table_catalog, field_semantics, canonical_mapping,
                   validation_rules, checksum, is_active
            FROM gov.dbf_interface_profile
            WHERE school_id=:school_id AND is_active IS TRUE
            ORDER BY id
            LIMIT 1
            """),
        {"school_id": school_id},
    )
    row = result.mappings().first()
    if row is not None:
        return dict(row)

    checksum = _catalog_checksum()
    profile = await execute_returning_row(
        db,
        """
        INSERT INTO gov.dbf_interface_profile (
                school_id, profile_code, profile_name, schema_version,
                table_catalog, field_semantics, canonical_mapping,
                validation_rules, checksum, is_active
            )
            VALUES (
                :school_id, 'default-dbf-v1', '学校 DBF 标准接口',
                'dbf-catalog-v1', CAST(:catalog AS jsonb), CAST(:field_semantics AS jsonb),
                CAST(:canonical_mapping AS jsonb), CAST(:validation_rules AS jsonb),
                :checksum, TRUE
            )
            ON CONFLICT (school_id, profile_code)
            DO UPDATE SET
                table_catalog=EXCLUDED.table_catalog,
                checksum=EXCLUDED.checksum,
                updated_at=now()
            RETURNING id, school_id, profile_code, profile_name, schema_version,
                      table_catalog, field_semantics, canonical_mapping,
                      validation_rules, checksum, is_active
            """
        ,
        {
            "school_id": school_id,
            "catalog": json.dumps(DBF_TABLE_CATALOG, ensure_ascii=False),
            "field_semantics": json.dumps(
                {
                    "KSH": "考生号，跨表关联主键",
                    "XM": "姓名，敏感字段",
                    "ZYDH": "专业代号",
                    "ZYMC": "专业名称",
                    "JHRS": "计划人数",
                    "CJ": "成绩",
                    "TDCJ": "投档成绩",
                },
                ensure_ascii=False,
            ),
            "canonical_mapping": json.dumps(
                {
                    "candidate_master": "fact.student_identity/fact.admission_record",
                    "plan": "fact.plan",
                    "admission_detail": "fact.admission_record",
                    "subject_score": "fact.exam_subject_score",
                    "major_choice": "fact.major_choice",
                    "medical_record": "fact.medical_summary",
                },
                ensure_ascii=False,
            ),
            "validation_rules": json.dumps(
                {
                    "required_keys": ["KSH", "ZYDH"],
                    "privacy_fields": ["XM", "ZJHM", "LXDH", "LXSJ", "TXDZ"],
                    "numeric_non_negative": ["JHRS", "CJ", "TDCJ"],
                },
                ensure_ascii=False,
            ),
            "checksum": checksum,
        },
        mysql_select="""
            SELECT id, school_id, profile_code, profile_name, schema_version,
                   table_catalog, field_semantics, canonical_mapping,
                   validation_rules, checksum, is_active
            FROM gov.dbf_interface_profile
            WHERE school_id=:school_id AND profile_code='default-dbf-v1'
            LIMIT 1
        """,
    )
    await db.commit()
    return profile or {}


async def resolve_school_context(
    db: AsyncSession,
    *,
    user_id: int | None = None,
    context: dict[str, Any] | None = None,
    allow_fallback: bool = True,
) -> dict[str, Any]:
    context = context or {}
    school_id = context.get("school_id")
    school_code = context.get("school_code")
    school_name = context.get("school_name")

    if school_id is not None:
        result = await db.execute(
            text(
                """
                SELECT id, school_code, school_name, school_short_name, status,
                       timezone, settings, dbf_profile, knowledge_scope
                FROM dim.school
                WHERE id=:school_id
                """
            ),
            {"school_id": int(school_id)},
        )
    elif school_code:
        result = await db.execute(
            text(
                """
                SELECT id, school_code, school_name, school_short_name, status,
                       timezone, settings, dbf_profile, knowledge_scope
                FROM dim.school
                WHERE school_code=:school_code
                ORDER BY id
                LIMIT 1
                """
            ),
            {"school_code": str(school_code)},
        )
    elif school_name:
        result = await db.execute(
            text(
                """
                SELECT id, school_code, school_name, school_short_name, status,
                       timezone, settings, dbf_profile, knowledge_scope
                FROM dim.school
                WHERE school_name ILIKE :school_name
                ORDER BY id
                LIMIT 1
                """
            ),
            {"school_name": f"%{school_name}%"},
        )
    elif user_id is not None:
        result = await db.execute(
            text(
                """
                SELECT s.id, s.school_code, s.school_name, s.school_short_name,
                       s.status, s.timezone, s.settings, s.dbf_profile, s.knowledge_scope
                FROM sys.user_school us
                JOIN dim.school s ON s.id=us.school_id
                WHERE us.user_id=:user_id
                ORDER BY us.is_default DESC, s.id
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        )
    else:
        result = None

    row = result.mappings().first() if result is not None else None
    if row is None and not allow_fallback:
        return {}
    if row is None:
        fallback = await db.execute(
            text(
                """
                SELECT id, school_code, school_name, school_short_name, status,
                       timezone, settings, dbf_profile, knowledge_scope
                FROM dim.school
                ORDER BY id
                LIMIT 1
                """
            )
        )
        row = fallback.mappings().first()

    if row is None:
        return {
            "school_id": None,
            "school_code": "DEFAULT",
            "school_name": "默认学校",
            "school_short_name": None,
            "settings": {},
            "knowledge_scope": {},
            "dbf_profile": {"schema_version": "dbf-catalog-v1"},
        }

    school = dict(row)
    profile = await get_or_create_dbf_profile(db, int(school["id"]))
    school["school_id"] = int(school.pop("id"))
    school["dbf_profile"] = profile
    return school

