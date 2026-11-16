from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.analytics import service

router = APIRouter()


class PlanAdjustment(BaseModel):
    major_name: str = Field(min_length=1, max_length=128)
    plan_delta: int = Field(ge=-5000, le=5000)


class PlanSimulationRequest(BaseModel):
    year: int | None = Field(default=None, ge=2000, le=2100)
    adjustments: list[PlanAdjustment] = Field(default_factory=list, max_length=50)


@router.get("/dashboard/overview")
async def dashboard_overview(
    year: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await service.get_dashboard_overview(db, year=year)


@router.get("/admissions/overview")
async def admissions_overview(
    year: int | None = Query(default=None),
    province: str | None = Query(default=None),
    major: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await service.get_admissions_overview(
        db,
        year=year,
        province=province,
        major=major,
    )


@router.get("/admissions/plans")
async def admissions_plans(
    year: int | None = Query(default=None),
    province: str | None = Query(default=None),
    major: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return {
        "items": await service.get_plans(
            db,
            year=year,
            province=province,
            major=major,
            limit=limit,
        )
    }


@router.get("/source/overview")
async def source_overview(
    year: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await service.get_source_overview(db, year=year)


@router.get("/trends")
async def trends(
    year: int | None = Query(default=None),
    province: str | None = Query(default=None),
    major: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    payload = await service.get_admissions_overview(
        db,
        year=year,
        province=province,
        major=major,
    )
    return {"items": payload["year_trend"]}


@router.get("/anomalies")
async def anomalies(
    year: int | None = Query(default=None, ge=2000, le=2100),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await service.get_anomalies(db, year=year)


@router.post("/simulate")
async def simulate(
    payload: PlanSimulationRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await service.simulate_plan(
        db,
        year=payload.year,
        adjustments=[item.model_dump() for item in payload.adjustments],
    )
