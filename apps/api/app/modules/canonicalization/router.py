from fastapi import APIRouter, Depends, Query
from app.core.text import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.system import User
from app.modules.auth.dependencies import require_permission

router = APIRouter()


@router.get("/status")
async def canonicalization_status(
    limit: int = Query(default=100, ge=1, le=500),
    _user: User = Depends(require_permission("data:quality:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    metrics = (
        await db.execute(
            text(
                """
                SELECT
                    COUNT(*) AS rule_hits,
                    COALESCE(SUM(hit_count), 0) AS total_hits,
                    COUNT(DISTINCT entity_type) AS entity_types,
                    COUNT(DISTINCT pipeline) AS pipelines
                FROM gov.canonicalization_event
                """
            )
        )
    ).mappings().one()
    by_type = await db.execute(
        text(
            """
            SELECT entity_type, rule_code, COUNT(*) AS rules, COALESCE(SUM(hit_count), 0) AS hits
            FROM gov.canonicalization_event
            GROUP BY entity_type, rule_code
            ORDER BY hits DESC, entity_type
            """
        )
    )
    events = await db.execute(
        text(
            """
            SELECT pipeline, entity_type, source_value, canonical_value,
                   rule_code, scope_key, confidence, hit_count, last_seen_at
            FROM gov.canonicalization_event
            ORDER BY last_seen_at DESC, hit_count DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    )
    alias_count = await db.scalar(text("SELECT COUNT(*) FROM dim.major_alias WHERE is_active IS TRUE"))
    return {
        "metrics": {
            "active_major_aliases": int(alias_count or 0),
            "rule_hits": int(metrics["rule_hits"] or 0),
            "total_hits": int(metrics["total_hits"] or 0),
            "entity_types": int(metrics["entity_types"] or 0),
            "pipelines": int(metrics["pipelines"] or 0),
        },
        "by_type": [dict(row) for row in by_type.mappings().all()],
        "events": [dict(row) for row in events.mappings().all()],
    }

