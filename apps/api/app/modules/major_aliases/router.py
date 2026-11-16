from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.system import User
from app.modules.audit.service import write_audit_log
from app.modules.auth.dependencies import require_permission
from app.modules.major_aliases import service
from app.modules.major_aliases.schemas import MajorAliasUpsert, MajorRenameRequest

router = APIRouter()


@router.get("/options")
async def alias_options(
    _user: User = Depends(require_permission("data:quality:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await service.get_alias_options(db)


@router.get("")
async def aliases(
    _user: User = Depends(require_permission("data:quality:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await service.list_aliases(db)


@router.put("/majors/{major_id}")
async def rename_major(
    major_id: int,
    payload: MajorRenameRequest,
    user: User = Depends(require_permission("data:quality:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        result = await service.rename_major(db, major_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await write_audit_log(
        db,
        user_id=user.id,
        action_type="MAJOR_RENAME",
        resource_type="MAJOR",
        resource_id=str(major_id),
        request_data=payload.model_dump(),
        result_status="SUCCESS",
    )
    return result


@router.post("", status_code=201)
async def create_alias(
    payload: MajorAliasUpsert,
    user: User = Depends(require_permission("data:quality:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        created = await service.create_alias(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await write_audit_log(
        db,
        user_id=user.id,
        action_type="MAJOR_ALIAS_CREATE",
        resource_type="MAJOR_ALIAS",
        resource_id=str(created["id"]),
        request_data=payload.model_dump(),
        result_status="SUCCESS",
    )
    return created


@router.put("/{alias_id}")
async def update_alias(
    alias_id: int,
    payload: MajorAliasUpsert,
    user: User = Depends(require_permission("data:quality:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        updated = await service.update_alias(db, alias_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await write_audit_log(
        db,
        user_id=user.id,
        action_type="MAJOR_ALIAS_UPDATE",
        resource_type="MAJOR_ALIAS",
        resource_id=str(alias_id),
        request_data=payload.model_dump(),
        result_status="SUCCESS",
    )
    return updated


@router.delete("/{alias_id}")
async def delete_alias(
    alias_id: int,
    user: User = Depends(require_permission("data:quality:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        deleted = await service.delete_alias(db, alias_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await write_audit_log(
        db,
        user_id=user.id,
        action_type="MAJOR_ALIAS_DELETE",
        resource_type="MAJOR_ALIAS",
        resource_id=str(alias_id),
        request_data={"alias_id": alias_id},
        result_status="SUCCESS",
    )
    return deleted

