import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool
from sqlalchemy.sql.elements import TextClause

from app.core.config import settings

SCHEMA_TRANSLATE_MAP: dict[str, str] | None = (
    {
        "sys": "zhaolu_sys",
        "dim": "zhaolu_dim",
        "fact": "zhaolu_fact",
        "gov": "zhaolu_gov",
        "ai": "zhaolu_ai",
        "analytics": "zhaolu_analytics",
    }
    if settings.database_url.startswith("mysql")
    else None
)


def session_options() -> dict[str, Any]:
    if SCHEMA_TRANSLATE_MAP is None:
        return {}
    return {"schema_translate_map": SCHEMA_TRANSLATE_MAP}


def rewrite_mysql_schemas(statement: str) -> str:
    if SCHEMA_TRANSLATE_MAP is None:
        return statement
    rewritten = statement
    for source, target in SCHEMA_TRANSLATE_MAP.items():
        rewritten = re.sub(rf"(?<![A-Za-z0-9_]){source}\.", f"{target}.", rewritten)
    return rewritten


def build_engine_kwargs(database_url: str) -> dict[str, Any]:
    if settings.database_null_pool:
        return {"pool_pre_ping": True, "poolclass": NullPool}
    return {
        "pool_pre_ping": True,
        "pool_recycle": settings.database_pool_recycle_seconds,
        "pool_size": max(2, settings.database_pool_size),
        "max_overflow": max(0, settings.database_max_overflow),
        "pool_timeout": max(1.0, settings.database_pool_timeout_seconds),
        "pool_use_lifo": True,
        "poolclass": AsyncAdaptedQueuePool,
    }


_base_engine = create_async_engine(
    settings.database_url,
    **build_engine_kwargs(settings.database_url),
)


def _configure_engine(target: AsyncEngine) -> AsyncEngine:
    configured = target.execution_options(**session_options()) if SCHEMA_TRANSLATE_MAP else target
    if SCHEMA_TRANSLATE_MAP is not None:
        _listen_for_schema_rewrite(configured)
    return configured


def _listen_for_schema_rewrite(target: AsyncEngine) -> None:
    @event.listens_for(target.sync_engine, "before_execute")
    def _rewrite_mysql_text(
        connection,
        clauseelement,
        multiparams,
        params,
        execution_options,
    ):
        if isinstance(clauseelement, TextClause):
            rewritten = rewrite_mysql_schemas(clauseelement.text)
            if rewritten != clauseelement.text:
                return text(rewritten), multiparams, params
        return clauseelement, multiparams, params


engine = _configure_engine(_base_engine)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

_school_engines: dict[str, AsyncEngine] = {}
_school_sessionmakers: dict[str, async_sessionmaker[AsyncSession]] = {}


class SchoolDataPlaneUnavailable(RuntimeError):
    pass


def get_school_engine(database_url: str) -> AsyncEngine:
    if database_url == settings.database_url:
        return engine
    target = _school_engines.get(database_url)
    if target is None:
        target = _configure_engine(
            create_async_engine(database_url, **build_engine_kwargs(database_url))
        )
        _school_engines[database_url] = target
    return target


def get_school_sessionmaker(database_url: str) -> async_sessionmaker[AsyncSession]:
    if database_url == settings.database_url:
        return AsyncSessionLocal
    maker = _school_sessionmakers.get(database_url)
    if maker is None:
        maker = async_sessionmaker(
            bind=get_school_engine(database_url),
            class_=AsyncSession,
            expire_on_commit=False,
        )
        _school_sessionmakers[database_url] = maker
    return maker


@asynccontextmanager
async def school_data_session(
    school_id: int | None,
) -> AsyncGenerator[AsyncSession, None]:
    database_url = settings.database_url_for_school(school_id)
    if database_url is None:
        raise SchoolDataPlaneUnavailable(
            f"学校 {school_id!r} 没有配置独立数据面，已拒绝回落到默认数据库"
        )
    async with get_school_sessionmaker(database_url)() as session:
        yield session


@asynccontextmanager
async def agent_data_session(
    control_db: AsyncSession,
    school_id: int | None,
) -> AsyncGenerator[AsyncSession, None]:
    database_url = settings.database_url_for_school(school_id)
    if database_url is None:
        raise SchoolDataPlaneUnavailable(
            f"学校 {school_id!r} 没有配置独立数据面，已拒绝回落到默认数据库"
        )
    if database_url == settings.database_url:
        yield control_db
        return
    async with school_data_session(school_id) as session:
        yield session


async def close_school_engines() -> None:
    for target in _school_engines.values():
        await target.dispose()
    _school_engines.clear()
    _school_sessionmakers.clear()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


