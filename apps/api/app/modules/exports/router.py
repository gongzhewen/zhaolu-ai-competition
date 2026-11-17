from __future__ import annotations

from typing import Annotated

from app.core.database import get_db
from app.core.permissions import has_permission
from app.models.system import User
from app.modules.audit.service import write_audit_log
from app.modules.auth.dependencies import get_current_user
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from .schemas import ResultExportRequest
from .service import ExportDataError, build_export_file

router = APIRouter()


async def require_export_permission(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not (
        has_permission(user, "report:export")
        or has_permission(user, "ai:report")
    ):
        raise HTTPException(status_code=403, detail="无结果导出权限")
    return user


@router.post("/result")
async def export_result(
    payload: ResultExportRequest,
    request: Request,
    user: Annotated[User, Depends(require_export_permission)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    try:
        content, media_type, disposition = build_export_file(payload)
    except ExportDataError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await write_audit_log(
        db,
        user_id=user.id,
        action_type="RESULT_EXPORT",
        resource_type=payload.kind,
        resource_id=str(payload.metadata.get("message_id") or ""),
        request_data={
            "kind": payload.kind,
            "format": payload.format,
            "title": payload.title,
            "row_count": len(payload.table.rows) if payload.table else 0,
            "column_count": len(payload.table.columns) if payload.table else 0,
        },
        result_status="SUCCESS",
        ip_address=request.client.host if request.client else None,
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": disposition},
    )

