from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.dimension import Batch, Major, PlanType, Province, Subject, Year
from app.models.governance import MetricDefinition

router = APIRouter()


@router.get("/years")
async def list_years(db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(select(Year).order_by(Year.year_no.desc()))
    return {"items": [{"id": row.id, "year_no": row.year_no} for row in result.scalars().all()]}


@router.get("/provinces")
async def list_provinces(db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(select(Province).order_by(Province.province_name))
    return {
        "items": [
            {"id": row.id, "province_code": row.province_code, "province_name": row.province_name}
            for row in result.scalars().all()
        ]
    }


@router.get("/subjects")
async def list_subjects(db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(select(Subject).order_by(Subject.id))
    return {
        "items": [
            {"id": row.id, "subject_code": row.subject_code, "subject_name": row.subject_name}
            for row in result.scalars().all()
        ]
    }


@router.get("/batches")
async def list_batches(db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(select(Batch).order_by(Batch.id))
    return {
        "items": [
            {"id": row.id, "batch_code": row.batch_code, "batch_name": row.batch_name}
            for row in result.scalars().all()
        ]
    }


@router.get("/majors")
async def list_majors(db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(select(Major).where(Major.is_active.is_(True)).order_by(Major.id))
    return {
        "items": [
            {
                "id": row.id,
                "major_code": row.major_code,
                "major_name": row.major_name,
                "subject_req": row.subject_req,
            }
            for row in result.scalars().all()
        ]
    }


@router.get("/plan-types")
async def list_plan_types(db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(select(PlanType).order_by(PlanType.id))
    return {
        "items": [
            {"id": row.id, "type_code": row.type_code, "type_name": row.type_name}
            for row in result.scalars().all()
        ]
    }


@router.get("/metrics")
async def list_metrics(db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(
        select(MetricDefinition)
        .where(MetricDefinition.is_active.is_(True))
        .order_by(MetricDefinition.id)
    )
    return {
        "items": [
            {
                "id": row.id,
                "metric_code": row.metric_code,
                "metric_name": row.metric_name,
                "metric_formula": row.metric_formula,
                "description": row.description,
                "version_no": row.version_no,
            }
            for row in result.scalars().all()
        ]
    }
