from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.system import User
from app.modules.audit.service import write_audit_log
from app.modules.auth.dependencies import require_super_admin
from app.modules.students.schemas import StudentManagementUpdate
from app.modules.students.service import (
    get_student_detail,
    get_student_summary,
    get_student_years,
    list_students,
    upsert_management,
)

router = APIRouter()


@router.get("")
async def students(
    response: Response,
    year: int | None = Query(default=None, ge=2000, le=2100),
    keyword: str | None = Query(default=None),
    region_code: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return await list_students(
        db,
        year=year,
        keyword=keyword,
        region_code=region_code,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.get("/summary")
async def student_summary(
    response: Response,
    year: int | None = Query(default=None, ge=2000, le=2100),
    _user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return await get_student_summary(db, year=year)


@router.get("/years")
async def student_years(
    response: Response,
    _user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return await get_student_years(db)


@router.get("/{candidate_key}")
async def student_detail(
    candidate_key: str,
    response: Response,
    user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    detail = await get_student_detail(db, candidate_key)
    if detail is None:
        raise HTTPException(status_code=404, detail="学生记录不存在")

    await write_audit_log(
        db,
        user_id=user.id,
        action_type="STUDENT_VIEW",
        resource_type="STUDENT",
        resource_id=candidate_key,
        request_data={
            "candidate_key": candidate_key,
            "year_no": detail["basic"].get("year_no"),
        },
        result_status="SUCCESS",
    )
    return detail


@router.patch("/{candidate_key}")
async def update_student_management(
    candidate_key: str,
    payload: StudentManagementUpdate,
    user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    existing = await get_student_detail(db, candidate_key)
    if existing is None:
        raise HTTPException(status_code=404, detail="学生记录不存在")

    year_no = int(existing["basic"]["year_no"])
    updated = await upsert_management(
        db,
        candidate_key=candidate_key,
        year_no=year_no,
        user_id=user.id,
        student_status=payload.student_status,
        follow_up_status=payload.follow_up_status,
        owner_name=payload.owner_name,
        tags=payload.tags,
        notes=payload.notes,
    )
    await write_audit_log(
        db,
        user_id=user.id,
        action_type="STUDENT_UPDATE",
        resource_type="STUDENT",
        resource_id=candidate_key,
        request_data={"year_no": year_no, **payload.model_dump(exclude_none=True)},
        result_status="SUCCESS",
    )
    return updated
