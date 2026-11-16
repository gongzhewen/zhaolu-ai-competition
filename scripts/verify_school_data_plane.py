from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.core.database import SchoolDataPlaneUnavailable, close_school_engines, school_data_session
from app.modules.agent.tools.registry import NATIVE_TOOL_EXECUTORS
from sqlalchemy import text


async def plan_total(school_id: int) -> int:
    async with school_data_session(school_id) as db:
        return int(await db.scalar(text("SELECT COALESCE(SUM(plan_count), 0) FROM zhaolu_fact.plan")) or 0)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="artifacts/G8/school_data_plane_20261110.json")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    if set(settings.school_database_url_map) != {1, 2}:
        raise SystemExit("SCHOOL_DATABASE_URLS must map both school 1 and school 2")

    school_1_total = await plan_total(1)
    school_2_total = await plan_total(2)
    async with school_data_session(2) as db:
        tool_result = await NATIVE_TOOL_EXECUTORS["admissions_overview"](
            db,
            {
                "school_id": 2,
                "year": 2026,
                "query": "2026年招生计划数是多少",
            },
        )
    unknown_plane_rejected = False
    try:
        async with school_data_session(3):
            pass
    except SchoolDataPlaneUnavailable:
        unknown_plane_rejected = True
    await close_school_engines()

    checks = {
        "school_1_plane_reachable": school_1_total > 0,
        "school_2_plane_reachable": school_2_total == 12345,
        "different_plan_totals": school_1_total != school_2_total,
        "tool_uses_school_2_session": int(tool_result.get("metrics", {}).get("plan_count") or 0) == 12345,
        "unknown_school_rejected": unknown_plane_rejected,
    }
    result = {
        "evaluation_kind": "independent_school_data_plane_verification",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "school_totals": {"school_1": school_1_total, "school_2": school_2_total},
        "school_2_tool_plan_count": tool_result.get("metrics", {}).get("plan_count"),
        "checks": checks,
        "status": "passed" if all(checks.values()) else "failed",
        "boundary": (
            "验证在第二套临时 MySQL 数据面上完成；不等同于生产学校账号权限审计、"
            "跨主机网络隔离或长期运行验证。"
        ),
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
