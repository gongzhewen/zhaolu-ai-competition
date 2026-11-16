from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.config import settings
from app.core.database import engine, school_data_session
from app.core.text import text

logger = logging.getLogger(__name__)
_refresh_tasks: set[asyncio.Task[Any]] = set()
_refresh_locks: dict[int, asyncio.Lock] = {}


async def _refresh_admissions_rollup_unlocked(db=None) -> None:
    if settings.database_url.startswith("mysql"):
        if db is not None:
            await db.execute(text("DELETE FROM zhaolu_analytics.mv_admissions_rollup"))
            await db.execute(text(MYSQL_ROLLUP_INSERT))
            return
        async with engine.begin() as connection:
            await connection.execute(text("DELETE FROM zhaolu_analytics.mv_admissions_rollup"))
            await connection.execute(text(MYSQL_ROLLUP_INSERT))
        return

    refresh_sql = "REFRESH MATERIALIZED VIEW analytics.mv_admissions_rollup"
    if db is not None:
        await db.execute(text(refresh_sql))
        return
    try:
        async with engine.connect() as connection:
            await connection.execution_options(isolation_level="AUTOCOMMIT")
            await connection.execute(
                text("REFRESH MATERIALIZED VIEW CONCURRENTLY analytics.mv_admissions_rollup")
            )
    except Exception:
        logger.warning("Concurrent materialized view refresh failed; retrying transactionally", exc_info=True)
        async with engine.begin() as connection:
            await connection.execute(text(refresh_sql))


MYSQL_ROLLUP_INSERT = """
                    INSERT INTO zhaolu_analytics.mv_admissions_rollup (
                        year_no, school_id, school_name, province_id, province_name,
                        source_major_id, source_major_name, canonical_major_id,
                        canonical_major_name, subject_id, subject_name,
                        plan_type_id, plan_type_key, plan_type_code, batch_id,
                        plan_count, admitted_count, min_score, max_score,
                        min_rank_no, data_version
                    )
                    SELECT
                        y.year_no,
                        p.school_id,
                        sc.school_name,
                        p.province_id,
                        pr.province_name,
                        p.major_id,
                        m.major_name,
                        COALESCE(rm.id, m.id),
                        COALESCE(rm.major_name, m.major_name),
                        p.subject_id,
                        sub.subject_name,
                        p.plan_type_id,
                        COALESCE(p.plan_type_id, 0),
                        COALESCE(pt.type_code, ''),
                        p.batch_id,
                        COALESCE(p.plan_count, 0),
                        COALESCE(ar.admitted_count, 0),
                        ar.min_score,
                        ar.max_score,
                        ar.min_rank_no,
                        p.data_version
                    FROM (
                        SELECT year_id, school_id, province_id, major_id, subject_id,
                               plan_type_id, batch_id, SUM(plan_count) AS plan_count,
                               MAX(data_version) AS data_version
                        FROM zhaolu_fact.plan
                        GROUP BY year_id, school_id, province_id, major_id, subject_id, plan_type_id, batch_id
                    ) p
                    JOIN zhaolu_dim.year y ON y.id = p.year_id
                    JOIN zhaolu_dim.school sc ON sc.id = p.school_id
                    JOIN zhaolu_dim.province pr ON pr.id = p.province_id
                    JOIN zhaolu_dim.major m ON m.id = p.major_id
                    JOIN zhaolu_dim.subject sub ON sub.id = p.subject_id
                    LEFT JOIN zhaolu_dim.plan_type pt ON pt.id = p.plan_type_id
                    LEFT JOIN zhaolu_dim.major rm ON rm.id = (
                        SELECT ma.canonical_major_id
                        FROM zhaolu_dim.major_alias ma
                        WHERE ma.is_active = TRUE
                          AND ma.source_name_key = LOWER(
                              REPLACE(REPLACE(REPLACE(m.major_name, '（', '('), '）', ')'), ' ', '')
                          )
                          AND (ma.province_id IS NULL OR ma.province_id = p.province_id)
                        ORDER BY (ma.province_id IS NOT NULL) DESC, ma.id DESC
                        LIMIT 1
                    )
                    LEFT JOIN (
                        SELECT year_id, province_id, major_id, subject_id, batch_id,
                               COUNT(*) AS admitted_count,
                               MIN(NULLIF(score, 0)) AS min_score,
                               MAX(NULLIF(score, 0)) AS max_score,
                               MIN(NULLIF(rank_no, 0)) AS min_rank_no
                        FROM zhaolu_fact.admission_record
                        GROUP BY year_id, province_id, major_id, subject_id, batch_id
                    ) ar
                      ON ar.year_id = p.year_id
                     AND ar.province_id = p.province_id
                     AND ar.major_id = p.major_id
                     AND ar.subject_id = p.subject_id
                     AND ar.batch_id = p.batch_id
"""


async def refresh_admissions_rollup(db=None) -> None:
    loop = asyncio.get_running_loop()
    lock = _refresh_locks.setdefault(id(loop), asyncio.Lock())
    async with lock:
        await _refresh_admissions_rollup_unlocked(db)


async def refresh_admissions_rollup_for_school(school_id: int | None) -> None:
    async with school_data_session(school_id) as db:
        await refresh_admissions_rollup(db)
        await db.commit()


def _discard_task(task: asyncio.Task[Any]) -> None:
    _refresh_tasks.discard(task)
    try:
        task.result()
    except asyncio.CancelledError:
        return
    except Exception:
        logger.warning("Background analytics refresh failed", exc_info=True)


def schedule_analytics_refresh(school_id: int | None = None) -> None:
    task = asyncio.create_task(refresh_admissions_rollup_for_school(school_id))
    _refresh_tasks.add(task)
    task.add_done_callback(_discard_task)



