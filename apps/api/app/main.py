from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import close_school_engines
from app.core.mysql_schema import ensure_mysql_compat_indexes
from app.core.redis_cache import close_redis, redis_health
from app.modules.agent.router import router as agent_router
from app.modules.ai_gateway.router import router as ai_router
from app.modules.analytics.router import router as analytics_router
from app.modules.audit.router import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.canonicalization.router import router as canonicalization_router
from app.modules.exports.router import router as exports_router
from app.modules.forecast.router import router as forecast_router
from app.modules.ingestion.dbf_router import router as dbf_router
from app.modules.ingestion.router import router as ingestion_router
from app.modules.major_aliases.router import router as major_aliases_router
from app.modules.metadata.router import router as metadata_router
from app.modules.plans.router import router as plans_router
from app.modules.quality.router import router as quality_router
from app.modules.rag.service import warm_vector_rag
from app.modules.reports.router import router as reports_router
from app.modules.students.router import router as students_router
from app.modules.users.router import router as users_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await ensure_mysql_compat_indexes()
    await warm_vector_rag()
    try:
        yield
    finally:
        await close_redis()
        await close_school_engines()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(agent_router, prefix="/api/v1/agent", tags=["agent"])
app.include_router(ai_router, prefix="/api/v1/ai", tags=["ai"])
app.include_router(analytics_router, prefix="/api/v1/analytics", tags=["analytics"])
app.include_router(metadata_router, prefix="/api/v1/meta", tags=["metadata"])
app.include_router(forecast_router, prefix="/api/v1/forecast", tags=["forecast"])
app.include_router(major_aliases_router, prefix="/api/v1/major-aliases", tags=["major-aliases"])
app.include_router(plans_router, prefix="/api/v1/plans", tags=["plans"])
app.include_router(students_router, prefix="/api/v1/students", tags=["students"])
app.include_router(users_router, prefix="/api/v1/users", tags=["users"])
app.include_router(reports_router, prefix="/api/v1/reports", tags=["reports"])
app.include_router(audit_router, prefix="/api/v1/audit", tags=["audit"])
app.include_router(quality_router, prefix="/api/v1/data/quality", tags=["quality"])
app.include_router(ingestion_router, prefix="/api/v1/data", tags=["data"])
app.include_router(dbf_router, prefix="/api/v1/data", tags=["dbf-import"])
app.include_router(canonicalization_router, prefix="/api/v1/canonicalization", tags=["canonicalization"])
app.include_router(exports_router, prefix="/api/v1/exports", tags=["exports"])


@app.get("/api/v1")
async def api_root() -> dict:
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "ok",
        "docs": "/docs",
    }


@app.get("/api/v1/health")
async def health() -> dict:
    return {
        "status": "ok",
        "environment": settings.environment,
        "instance_id": settings.instance_id,
        "deployment_mode": settings.deployment_mode,
        "redis": await redis_health(),
    }




