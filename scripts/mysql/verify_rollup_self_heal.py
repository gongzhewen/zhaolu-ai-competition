from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for source_path in (
    ROOT / "packages" / "agent_core",
    ROOT / "packages" / "data_contracts",
    ROOT / "apps" / "api",
):
    sys.path.insert(0, str(source_path))
ENV_FILE = ROOT / "apps" / "api" / ".env.mysql"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())

os.environ.setdefault("JWT_SECRET", "local_test_secret_for_mysql_regression_32_bytes")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.main import app  # noqa: E402


async def delete_rollup_year() -> int:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("DELETE FROM zhaolu_analytics.mv_admissions_rollup WHERE year_no=2025")
        )
        await db.commit()
        return int(result.rowcount or 0)


async def base_plan_total(year: int) -> int:
    async with AsyncSessionLocal() as db:
        value = await db.scalar(
            text(
                """
                SELECT COALESCE(SUM(p.plan_count), 0)
                FROM zhaolu_fact.plan p
                JOIN zhaolu_dim.year y ON y.id=p.year_id
                WHERE y.year_no=:year
                """
            ),
            {"year": year},
        )
        return int(value or 0)


async def rollup_state(year: int) -> tuple[int, int]:
    async with AsyncSessionLocal() as db:
        rows = await db.scalar(
            text("SELECT COUNT(*) FROM zhaolu_analytics.mv_admissions_rollup WHERE year_no=:year"),
            {"year": year},
        )
        total = await db.scalar(
            text("SELECT SUM(plan_count) FROM zhaolu_analytics.mv_admissions_rollup WHERE year_no=:year"),
            {"year": year},
        )
        return int(rows or 0), int(total or 0)


def main() -> None:
    year = 2025
    expected = asyncio.run(base_plan_total(year))
    if expected <= 0:
        raise SystemExit(f"{year} base plan data is empty")
    deleted = asyncio.run(delete_rollup_year())
    if deleted <= 0:
        raise SystemExit("2025 rollup rows were not removed; cannot run self-heal test")

    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            data={"username": "admin", "password": "ChangeMe123!"},
        )
        login.raise_for_status()
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        response = client.post(
            "/api/v1/ai/chat",
            headers=headers,
            json={"message": "2025年各专业招生计划完成情况怎么样？", "context": {}},
        )
        response.raise_for_status()
        payload = response.json()
        result = (payload.get("tool_results") or [{}])[0]
        metrics = result.get("metrics") or {}
        plan_count = int(metrics.get("plan_count") or 0)
        if plan_count != expected:
            raise SystemExit(f"rollup self-heal failed: plan_count={plan_count}, expected={expected}")
        if "未找到招生计划数据" in payload.get("answer", ""):
            raise SystemExit("rollup self-heal returned missing-data message")

    rows, total = asyncio.run(rollup_state(year))
    if rows <= 0 or total != expected:
        raise SystemExit(f"rollup was not restored: rows={rows}, total={total}, expected={expected}")
    print(f"rollup_self_heal=ok deleted={deleted} rows={rows} plan_count={total}")


if __name__ == "__main__":
    main()
