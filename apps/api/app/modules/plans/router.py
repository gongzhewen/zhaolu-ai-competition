from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.system import User
from app.modules.audit.service import write_audit_log
from app.modules.auth.dependencies import require_permission
from app.modules.plans import service
from app.modules.plans.schemas import CopyPlanRequest, PlanUpsert, YearCreate

router = APIRouter()


@router.get("/options")
async def plan_options(
    _user: User = Depends(require_permission("admissions:plan:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await service.get_plan_options(db)


@router.post("/years", status_code=201)
async def create_year(
    payload: YearCreate,
    user: User = Depends(require_permission("admissions:plan:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    created = await service.create_year(db, payload.year_no)
    await write_audit_log(
        db,
        user_id=user.id,
        action_type="YEAR_CREATE",
        resource_type="YEAR",
        resource_id=str(payload.year_no),
        request_data=payload.model_dump(),
        result_status="SUCCESS",
    )
    return created


@router.get("")
async def plans(
    response: Response,
    year: int | None = Query(default=None, ge=2000, le=2100),
    province_id: int | None = Query(default=None),
    batch_id: int | None = Query(default=None),
    subject_id: int | None = Query(default=None),
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _user: User = Depends(require_permission("admissions:plan:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return await service.list_plans(
        db,
        year=year,
        province_id=province_id,
        batch_id=batch_id,
        subject_id=subject_id,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )


@router.post("", status_code=201)
async def create_plan(
    payload: PlanUpsert,
    user: User = Depends(require_permission("admissions:plan:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        created = await service.create_plan(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await write_audit_log(
        db,
        user_id=user.id,
        action_type="PLAN_CREATE",
        resource_type="PLAN",
        resource_id=str(created["id"]),
        request_data=payload.model_dump(),
        result_status="SUCCESS",
    )
    return created


@router.put("/{plan_id}")
async def update_plan(
    plan_id: int,
    payload: PlanUpsert,
    user: User = Depends(require_permission("admissions:plan:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        updated = await service.update_plan(db, plan_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await write_audit_log(
        db,
        user_id=user.id,
        action_type="PLAN_UPDATE",
        resource_type="PLAN",
        resource_id=str(plan_id),
        request_data=payload.model_dump(),
        result_status="SUCCESS",
    )
    return updated


@router.delete("/{plan_id}")
async def delete_plan(
    plan_id: int,
    user: User = Depends(require_permission("admissions:plan:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        deleted = await service.delete_plan(db, plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await write_audit_log(
        db,
        user_id=user.id,
        action_type="PLAN_DELETE",
        resource_type="PLAN",
        resource_id=str(plan_id),
        request_data={"plan_id": plan_id},
        result_status="SUCCESS",
    )
    return deleted


@router.post("/copy-from-year")
async def copy_from_year(
    payload: CopyPlanRequest,
    user: User = Depends(require_permission("admissions:plan:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        result = await service.copy_plans(
            db,
            source_year=payload.source_year,
            target_year=payload.target_year,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await write_audit_log(
        db,
        user_id=user.id,
        action_type="PLAN_COPY",
        resource_type="PLAN",
        resource_id=f"{payload.source_year}->{payload.target_year}",
        request_data=payload.model_dump(),
        result_status="SUCCESS",
    )
    return result

