from fastapi import APIRouter, Depends, Query
from app.core.text import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.system import User
from app.modules.auth.dependencies import require_permission

router = APIRouter()


@router.get("/summary")
async def audit_summary(
    _user: User = Depends(require_permission("audit:view")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    metrics = await db.execute(
        text(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE) AS today_count,
                COUNT(*) FILTER (WHERE result_status = 'FAILED') AS failed_count
            FROM sys.audit_log
            """
        )
    )
    metric_row = metrics.mappings().one()
    by_action = await db.execute(
        text(
            """
            SELECT action_type, COUNT(*) AS action_count
            FROM sys.audit_log
            GROUP BY action_type
            ORDER BY action_count DESC
            LIMIT 20
            """
        )
    )
    return {
        "metrics": {
            "total": int(metric_row["total"] or 0),
            "today_count": int(metric_row["today_count"] or 0),
            "failed_count": int(metric_row["failed_count"] or 0),
        },
        "by_action": [dict(row) for row in by_action.mappings().all()],
    }


@router.get("/logs")
async def audit_logs(
    action_type: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
    _user: User = Depends(require_permission("audit:view")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    where = "WHERE action_type = :action_type" if action_type else ""
    params = {"action_type": action_type, "limit": limit} if action_type else {"limit": limit}
    result = await db.execute(
        text(
            f"""
            SELECT
                id, user_id, action_type, resource_type, resource_id,
                request_data, result_status, ip_address, created_at
            FROM sys.audit_log
            {where}
            ORDER BY created_at DESC, id DESC
            LIMIT :limit
            """
        ),
        params,
    )
    return {"items": [dict(row) for row in result.mappings().all()]}

