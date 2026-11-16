from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from typing import Any

from pydantic import BaseModel, Field
from app.core.text import text
from app.core.db_compat import execute_returning_row
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.system import User
from app.modules.agent_intelligence.school_context import (
    get_or_create_dbf_profile,
    resolve_school_context,
)
from app.modules.auth.dependencies import require_permission
from app.modules.rag.service import seed_admissions_knowledge, search_knowledge

router = APIRouter()


class KnowledgeSeedRequest(BaseModel):
    school_code: str | None = None


class SchoolUpsertRequest(BaseModel):
    school_code: str = Field(min_length=2, max_length=64)
    school_name: str = Field(min_length=2, max_length=255)
    school_short_name: str | None = Field(default=None, max_length=128)
    timezone: str = Field(default="Asia/Shanghai", max_length=64)
    status: str = Field(default="ACTIVE", pattern="^(ACTIVE|DISABLED)$")
    settings: dict[str, Any] = Field(default_factory=dict)
    dbf_profile: dict[str, Any] = Field(default_factory=dict)
    knowledge_scope: dict[str, Any] = Field(default_factory=dict)


class DbfProfileUpdateRequest(BaseModel):
    profile_code: str = Field(default="default-dbf-v1", max_length=128)
    profile_name: str = Field(default="学校 DBF 标准接口", max_length=255)
    schema_version: str = Field(default="dbf-catalog-v1", max_length=64)
    field_semantics: dict[str, Any] = Field(default_factory=dict)
    canonical_mapping: dict[str, Any] = Field(default_factory=dict)
    validation_rules: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


@router.get("/schools")
async def list_schools(
    _user: User = Depends(require_permission("ai:chat")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        text("""
            SELECT id, school_code, school_name, school_short_name, status
            FROM dim.school
            ORDER BY id
            """
        )
    )
    return {"items": [dict(row) for row in result.mappings().all()]}


@router.post("/schools")
async def upsert_school(
    payload: SchoolUpsertRequest,
    user: User = Depends(require_permission("system:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    import json

    school = await execute_returning_row(
        db,
        """
        INSERT INTO dim.school (
                school_code, school_name, school_short_name, status, timezone,
                settings, dbf_profile, knowledge_scope
            )
            VALUES (
                :school_code, :school_name, :school_short_name, :status, :timezone,
                CAST(:settings AS jsonb), CAST(:dbf_profile AS jsonb),
                CAST(:knowledge_scope AS jsonb)
            )
            ON CONFLICT (school_code)
            DO UPDATE SET
                school_name=EXCLUDED.school_name,
                school_short_name=EXCLUDED.school_short_name,
                status=EXCLUDED.status,
                timezone=EXCLUDED.timezone,
                settings=EXCLUDED.settings,
                dbf_profile=EXCLUDED.dbf_profile,
                knowledge_scope=EXCLUDED.knowledge_scope,
                updated_at=now()
            RETURNING id, school_code, school_name, school_short_name, status
            """,
        {
            "school_code": payload.school_code,
            "school_name": payload.school_name,
            "school_short_name": payload.school_short_name,
            "status": payload.status,
            "timezone": payload.timezone,
            "settings": json.dumps(payload.settings, ensure_ascii=False),
            "dbf_profile": json.dumps(payload.dbf_profile, ensure_ascii=False),
            "knowledge_scope": json.dumps(payload.knowledge_scope, ensure_ascii=False),
        },
        mysql_select="""
            SELECT id, school_code, school_name, school_short_name, status
            FROM dim.school
            WHERE school_code=:school_code
            LIMIT 1
        """,
    )
    if school is None:
        raise ValueError("学校资料写入失败")
    await db.execute(
        text("""
            INSERT INTO sys.user_school (user_id, school_id, is_default)
            VALUES (:user_id, :school_id, FALSE)
            ON CONFLICT DO NOTHING
            """),
        {"user_id": user.id, "school_id": school["id"]},
    )
    await db.commit()
    profile = await get_or_create_dbf_profile(db, int(school["id"]))
    return {"school": school, "dbf_profile": profile}


@router.put("/schools/{school_id}/dbf-profile")
async def update_dbf_profile(
    school_id: int,
    payload: DbfProfileUpdateRequest,
    _user: User = Depends(require_permission("system:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    import json

    await get_or_create_dbf_profile(db, school_id)
    profile = await execute_returning_row(
        db,
        """
        UPDATE gov.dbf_interface_profile
            SET profile_code=:profile_code,
                profile_name=:profile_name,
                schema_version=:schema_version,
                field_semantics=CAST(:field_semantics AS jsonb),
                canonical_mapping=CAST(:canonical_mapping AS jsonb),
                validation_rules=CAST(:validation_rules AS jsonb),
                is_active=:is_active,
                updated_at=now()
            WHERE school_id=:school_id
            RETURNING id, school_id, profile_code, profile_name, schema_version,
                      table_catalog, field_semantics, canonical_mapping,
                      validation_rules, checksum, is_active
            """
        ,
        {
            "school_id": school_id,
            "profile_code": payload.profile_code,
            "profile_name": payload.profile_name,
            "schema_version": payload.schema_version,
            "field_semantics": json.dumps(payload.field_semantics, ensure_ascii=False),
            "canonical_mapping": json.dumps(payload.canonical_mapping, ensure_ascii=False),
            "validation_rules": json.dumps(payload.validation_rules, ensure_ascii=False),
            "is_active": payload.is_active,
        },
        mysql_select="""
            SELECT id, school_id, profile_code, profile_name, schema_version,
                   table_catalog, field_semantics, canonical_mapping,
                   validation_rules, checksum, is_active
            FROM gov.dbf_interface_profile
            WHERE school_id=:school_id
            ORDER BY id
            LIMIT 1
        """,
    )
    await db.commit()
    return {"dbf_profile": profile or {}}


@router.post("/knowledge/seed")
async def seed_knowledge(
    payload: KnowledgeSeedRequest,
    user: User = Depends(require_permission("system:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    school = await resolve_school_context(db, user_id=user.id, context={"school_code": payload.school_code} if payload.school_code else {})
    counts = await seed_admissions_knowledge(db, school_id=school.get("school_id"))
    return {"school": school.get("school_code"), **counts}


@router.get("/knowledge/search")
async def knowledge_search(
    query: str = Query(min_length=2, max_length=500),
    school_code: str | None = None,
    limit: int = Query(default=5, ge=1, le=20),
    user: User = Depends(require_permission("ai:chat")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    school = await resolve_school_context(db, user_id=user.id, context={"school_code": school_code} if school_code else {})
    items = await search_knowledge(
        db,
        query=query,
        school_id=school.get("school_id"),
        limit=limit,
    )
    return {"school": school.get("school_code"), "items": items}


@router.get("/memories")
async def list_memories(
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(require_permission("ai:chat")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        text("""
            SELECT id, school_id, memory_type, memory_key, summary, confidence,
                   importance, hit_count, updated_at
            FROM ai.agent_memory
            WHERE user_id=:user_id
            ORDER BY importance DESC, updated_at DESC
            LIMIT :limit
            """),
        {"user_id": user.id, "limit": limit},
    )
    return {"items": [dict(row) for row in result.mappings().all()]}


@router.get("/templates")
async def list_templates(
    _user: User = Depends(require_permission("ai:chat")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        text("""
            SELECT id, template_code, task_type, school_id, template_name,
                   strategy_key, weight, usage_count, success_count, version_no
            FROM ai.prompt_template
            WHERE is_active IS TRUE
            ORDER BY task_type, weight DESC, id
            """
        )
    )
    return {"items": [dict(row) for row in result.mappings().all()]}


@router.get("/optimization/report")
async def optimization_report(
    limit: int = Query(default=100, ge=1, le=500),
    _user: User = Depends(require_permission("system:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    summary = await db.execute(
        text(
            """
            SELECT COUNT(*) AS evaluations,
                   AVG(score) AS avg_score,
                   AVG(loss) AS avg_loss,
                   COUNT(*) FILTER (WHERE action='fallback_required') AS fallback_count
            FROM ai.response_evaluation
            """
        )
    )
    events = await db.execute(
        text(
            """
            SELECT oe.id, oe.school_id, oe.template_id, pt.template_code,
                   oe.signal_type, oe.reward, oe.previous_weight, oe.new_weight,
                   oe.learning_rate, oe.metadata, oe.created_at
            FROM ai.optimization_event oe
            LEFT JOIN ai.prompt_template pt ON pt.id=oe.template_id
            ORDER BY oe.id DESC
            LIMIT :limit
            """),
        {"limit": limit},
    )
    return {
        "summary": dict(summary.mappings().one()),
        "events": [dict(row) for row in events.mappings().all()],
    }

