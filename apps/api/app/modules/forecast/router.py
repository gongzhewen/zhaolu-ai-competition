from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.forecast import service

router = APIRouter()


@router.get("/overview")
async def forecast_overview(db: AsyncSession = Depends(get_db)) -> dict:
    return await service.get_forecast_overview(db)


@router.post("/run")
async def run_forecast(db: AsyncSession = Depends(get_db)) -> dict:
    return await service.get_forecast_overview(db)


@router.get("/status")
async def forecast_status() -> dict:
    return {"status": "ready", "model": "linear_regression"}
