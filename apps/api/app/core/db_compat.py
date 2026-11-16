from __future__ import annotations

import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.text import text


def is_mysql() -> bool:
    return settings.database_url.startswith("mysql")


def strip_returning(statement: str) -> str:
    return re.sub(
        r"\s+RETURNING\b[\s\S]*$",
        "",
        statement,
        flags=re.IGNORECASE,
    ).strip()


async def execute_returning_id(
    db: AsyncSession,
    statement: str,
    params: dict[str, Any] | None = None,
    *,
    mysql_statement: str | None = None,
    mysql_select: str | None = None,
    mysql_select_params: dict[str, Any] | None = None,
) -> int | None:
    if not is_mysql():
        return await db.scalar(text(statement), params or {})

    result = await db.execute(text(mysql_statement or strip_returning(statement)), params or {})
    lastrowid = getattr(result, "lastrowid", None)
    if lastrowid:
        return int(lastrowid)
    if mysql_select:
        selected = await db.scalar(text(mysql_select), mysql_select_params or params or {})
        return int(selected) if selected is not None else None
    return None


async def execute_returning_row(
    db: AsyncSession,
    statement: str,
    params: dict[str, Any] | None = None,
    *,
    mysql_statement: str | None = None,
    mysql_select: str | None = None,
    mysql_select_params: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not is_mysql():
        result = await db.execute(text(statement), params or {})
        row = result.mappings().one_or_none()
        return dict(row) if row is not None else None

    await db.execute(text(mysql_statement or strip_returning(statement)), params or {})
    if not mysql_select:
        return None
    result = await db.execute(text(mysql_select), mysql_select_params or params or {})
    row = result.mappings().first()
    return dict(row) if row is not None else None
