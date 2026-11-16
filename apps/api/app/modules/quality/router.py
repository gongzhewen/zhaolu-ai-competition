from fastapi import APIRouter, Depends, Query
from app.core.text import text
from app.core.db_compat import execute_returning_row
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.system import User
from app.modules.auth.dependencies import require_permission
from app.modules.quality.schemas import QualityIssueUpdate

router = APIRouter()


@router.get("/summary")
async def quality_summary(
    _user: User = Depends(require_permission("data:quality:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    metrics = await db.execute(
        text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE issue_status = 'OPEN') AS open_count,
                COUNT(*) FILTER (WHERE issue_status = 'RESOLVED') AS resolved_count
            FROM gov.data_issue
            """
        )
    )
    metric_row = metrics.mappings().one()

    by_type = await db.execute(
        text(
            """
            SELECT issue_type, COUNT(*) AS issue_count
            FROM gov.data_issue
            GROUP BY issue_type
            ORDER BY issue_count DESC
            """
        )
    )
    by_table = await db.execute(
        text(
            """
            SELECT target_table, COUNT(*) AS issue_count
            FROM gov.data_issue
            GROUP BY target_table
            ORDER BY issue_count DESC
            """
        )
    )
    return {
        "metrics": {
            "total": int(metric_row["total"] or 0),
            "open_count": int(metric_row["open_count"] or 0),
            "resolved_count": int(metric_row["resolved_count"] or 0),
        },
        "by_type": [dict(row) for row in by_type.mappings().all()],
        "by_table": [dict(row) for row in by_table.mappings().all()],
    }


@router.get("/issues")
async def list_issues(
    status: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
    _user: User = Depends(require_permission("data:quality:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    where = "WHERE issue_status = :status" if status else ""
    params = {"status": status, "limit": limit} if status else {"limit": limit}
    result = await db.execute(
        text(
            f"""
            SELECT
                id, target_table, record_key, issue_type,
                issue_message, issue_status, created_at
            FROM gov.data_issue
            {where}
            ORDER BY created_at DESC, id DESC
            LIMIT :limit
            """
        ),
        params,
    )
    return {"items": [dict(row) for row in result.mappings().all()]}


@router.post("/scan")
async def scan_quality(
    _user: User = Depends(require_permission("data:quality:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await db.execute(
        text(
            """
            DELETE FROM gov.data_issue
            WHERE issue_status = 'OPEN'
              AND issue_type IN (
                  'MISSING_SUMMARY',
                  'INVALID_PLAN_COUNT',
                  'MISSING_SCORE_RANK',
                  'INVALID_ADMISSION_SCORE'
              )
            """
        )
    )

    await db.execute(
        text(
            """
            INSERT INTO gov.data_issue (
                target_table, record_key, issue_type, issue_message, issue_status
            )
            SELECT
                'fact.plan', p.id::text, 'MISSING_SUMMARY',
                '招生计划记录缺少录取汇总', 'OPEN'
            FROM fact.plan p
            LEFT JOIN fact.admission_summary s ON s.plan_id = p.id
            WHERE s.id IS NULL
            """
        )
    )
    await db.execute(
        text(
            """
            INSERT INTO gov.data_issue (
                target_table, record_key, issue_type, issue_message, issue_status
            )
            SELECT
                'fact.plan', p.id::text, 'INVALID_PLAN_COUNT',
                '招生计划数小于等于 0', 'OPEN'
            FROM fact.plan p
            WHERE p.plan_count <= 0 OR p.plan_count IS NULL
            """
        )
    )
    await db.execute(
        text(
            """
            INSERT INTO gov.data_issue (
                target_table, record_key, issue_type, issue_message, issue_status
            )
            SELECT
                'fact.admission_record', ar.id::text, 'MISSING_SCORE_RANK',
                '录取记录同时缺少成绩和位次', 'OPEN'
            FROM fact.admission_record ar
            WHERE ar.score IS NULL AND ar.rank_no IS NULL
            """
        )
    )
    await db.execute(
        text(
            """
            INSERT INTO gov.data_issue (
                target_table, record_key, issue_type, issue_message, issue_status
            )
            SELECT
                'fact.admission_record', ar.id::text, 'INVALID_ADMISSION_SCORE',
                '录取成绩超出合理范围', 'OPEN'
            FROM fact.admission_record ar
            WHERE ar.score IS NOT NULL AND (ar.score < 0 OR ar.score > 1000)
            """
        )
    )
    await db.commit()

    total = await db.scalar(
        text("SELECT COUNT(*) FROM gov.data_issue WHERE issue_status = 'OPEN'")
    )
    return {"message": "数据质量扫描完成", "open_issues": int(total or 0)}


@router.patch("/issues/{issue_id}")
async def update_issue(
    issue_id: int,
    payload: QualityIssueUpdate,
    _user: User = Depends(require_permission("data:quality:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    updated = await execute_returning_row(
        db,
        """
        UPDATE gov.data_issue
        SET issue_status = :issue_status
        WHERE id = :issue_id
        RETURNING id, issue_status
        """,
        {"issue_status": payload.issue_status, "issue_id": issue_id},
        mysql_select="SELECT id, issue_status FROM gov.data_issue WHERE id=:issue_id",
    )
    await db.commit()
    if updated is None:
        return {"message": "问题记录不存在"}
    return dict(updated)

