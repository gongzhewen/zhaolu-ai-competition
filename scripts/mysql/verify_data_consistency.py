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

from sqlalchemy import text  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402


async def scalar(db, sql: str, params: dict | None = None) -> int:
    value = await db.scalar(text(sql), params or {})
    return int(value or 0)


async def main() -> None:
    failures: list[str] = []
    async with AsyncSessionLocal() as db:
        years = [
            int(row[0])
            for row in (
                await db.execute(text("SELECT year_no FROM zhaolu_dim.year ORDER BY year_no"))
            ).all()
        ]
        for year in years:
            base_plan = await scalar(
                db,
                """
                SELECT COALESCE(SUM(p.plan_count), 0)
                FROM zhaolu_fact.plan p
                JOIN zhaolu_dim.year y ON y.id = p.year_id
                WHERE y.year_no=:year
                """,
                {"year": year},
            )
            rollup_plan = await scalar(
                db,
                "SELECT COALESCE(SUM(plan_count), 0) FROM zhaolu_analytics.mv_admissions_rollup WHERE year_no=:year",
                {"year": year},
            )
            base_admitted = await scalar(
                db,
                """
                SELECT COUNT(*)
                FROM zhaolu_fact.admission_record ar
                JOIN zhaolu_dim.year y ON y.id=ar.year_id
                WHERE y.year_no=:year
                """,
                {"year": year},
            )
            summary_admitted = await scalar(
                db,
                """
                SELECT COALESCE(SUM(s.admitted_count), 0)
                FROM zhaolu_fact.admission_summary s
                JOIN zhaolu_fact.plan p ON p.id=s.plan_id
                JOIN zhaolu_dim.year y ON y.id=p.year_id
                WHERE y.year_no=:year
                """,
                {"year": year},
            )
            rollup_admitted = await scalar(
                db,
                "SELECT COALESCE(SUM(admitted_count), 0) FROM zhaolu_analytics.mv_admissions_rollup WHERE year_no=:year",
                {"year": year},
            )
            print(
                f"year={year} base_plan={base_plan} rollup_plan={rollup_plan} "
                f"record_admitted={base_admitted} summary_admitted={summary_admitted} rollup_admitted={rollup_admitted}"
            )
            if summary_admitted != base_admitted:
                print(f"summary_lag={year}: summary={summary_admitted} records={base_admitted}")
            if base_plan != rollup_plan:
                failures.append(f"{year}: plan mismatch {base_plan} != {rollup_plan}")
            if base_admitted != rollup_admitted:
                failures.append(f"{year}: admitted mismatch {base_admitted} != {rollup_admitted}")

        checks = {
            "plan_orphans": """
                SELECT COUNT(*) FROM zhaolu_fact.plan p
                LEFT JOIN zhaolu_dim.year y ON y.id=p.year_id
                LEFT JOIN zhaolu_dim.school sc ON sc.id=p.school_id
                LEFT JOIN zhaolu_dim.province pr ON pr.id=p.province_id
                LEFT JOIN zhaolu_dim.batch b ON b.id=p.batch_id
                LEFT JOIN zhaolu_dim.subject sub ON sub.id=p.subject_id
                LEFT JOIN zhaolu_dim.major m ON m.id=p.major_id
                WHERE y.id IS NULL OR sc.id IS NULL OR pr.id IS NULL OR b.id IS NULL
                   OR sub.id IS NULL OR m.id IS NULL
            """,
            "summary_orphans": """
                SELECT COUNT(*) FROM zhaolu_fact.admission_summary s
                LEFT JOIN zhaolu_fact.plan p ON p.id=s.plan_id
                WHERE p.id IS NULL
            """,
            "plans_without_summary": """
                SELECT COUNT(*) FROM zhaolu_fact.plan p
                LEFT JOIN zhaolu_fact.admission_summary s ON s.plan_id=p.id
                WHERE s.id IS NULL
            """,
            "invalid_plan_count": "SELECT COUNT(*) FROM zhaolu_fact.plan WHERE plan_count IS NULL OR plan_count<0",
            "major_alias_orphans": """
                SELECT COUNT(*) FROM zhaolu_dim.major_alias ma
                LEFT JOIN zhaolu_dim.major m ON m.id=ma.canonical_major_id
                WHERE m.id IS NULL OR ma.source_name_key IS NULL OR ma.source_name_key=''
            """,
        }
        for name, sql in checks.items():
            value = await scalar(db, sql)
            print(f"{name}={value}")
            if value:
                failures.append(f"{name}={value}")

    if failures:
        raise SystemExit("data_consistency=failed " + "; ".join(failures))
    print("data_consistency=ok")


if __name__ == "__main__":
    asyncio.run(main())

