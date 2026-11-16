from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.core.database import (
    AsyncSessionLocal,
    close_school_engines,
    engine,
)
from app.models.system import User
from app.modules.agent.service import AgentService
from sqlalchemy import select, text


async def ensure_school_2(control_db) -> bool:
    exists = await control_db.scalar(
        text("SELECT COUNT(*) FROM zhaolu_dim.school WHERE id=2")
    )
    if exists:
        return False
    await control_db.execute(
        text(
            """
            INSERT INTO zhaolu_dim.school (
                id, school_code, school_name, school_short_name, school_type,
                province_id, status, timezone, settings, dbf_profile, knowledge_scope
            ) VALUES (
                2, 'SCHOOL-VERIFY-2', '独立数据面验证学校', '验证学校',
                'UNDERGRADUATE', 1, 'ACTIVE', 'Asia/Shanghai',
                JSON_OBJECT('verification', TRUE),
                JSON_OBJECT('schema_version', 'dbf-catalog-v1'),
                JSON_OBJECT('scope', 'school')
            )
            """
        )
    )
    await control_db.commit()
    return True


async def cleanup_school_2(control_db, *, evaluation_id_floor: int = 0) -> None:
    await control_db.execute(
        text("DELETE FROM zhaolu_ai.response_evaluation WHERE id > :floor_id"),
        {"floor_id": int(evaluation_id_floor)},
    )
    await control_db.execute(
        text("DELETE FROM zhaolu_gov.dbf_interface_profile WHERE school_id=2")
    )
    await control_db.execute(
        text("DELETE FROM zhaolu_sys.user_school WHERE school_id=2")
    )
    await control_db.execute(text("DELETE FROM zhaolu_dim.school WHERE id=2"))
    await control_db.commit()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="artifacts/G8/agent_school_isolation_20261110.json")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    if set(settings.school_database_url_map) != {1, 2}:
        raise SystemExit("SCHOOL_DATABASE_URLS must map both school 1 and school 2")

    inserted = False
    try:
        async with AsyncSessionLocal() as control_db:
            evaluation_id_floor = int(
                await control_db.scalar(
                    text("SELECT COALESCE(MAX(id), 0) FROM zhaolu_ai.response_evaluation")
                )
                or 0
            )
            inserted = await ensure_school_2(control_db)
            user = (
                await control_db.execute(select(User).where(User.username == "admin"))
            ).scalar_one()
            service = AgentService(control_db, user)
            school_1 = await service.chat(
                message="2026年招生计划数是多少",
                context={"school_id": 1},
            )
            school_2 = await service.chat(
                message="2026年招生计划数是多少",
                context={"school_id": 2},
            )
            await cleanup_school_2(
                control_db,
                evaluation_id_floor=evaluation_id_floor,
            )
            inserted = False
    finally:
        if inserted:
            async with AsyncSessionLocal() as cleanup_db:
                await cleanup_school_2(cleanup_db)
        await close_school_engines()
        await engine.dispose()

    school_1_plan = int(school_1.get("tool_results", [{}])[0].get("metrics", {}).get("plan_count") or 0)
    school_2_plan = int(school_2.get("tool_results", [{}])[0].get("metrics", {}).get("plan_count") or 0)
    checks = {
        "school_1_agent_response": school_1.get("risk_decision", {}).get("strategy") == "answer",
        "school_2_agent_response": school_2.get("risk_decision", {}).get("strategy") == "answer",
        "school_1_plan_total": school_1_plan > 0,
        "school_2_plan_total": school_2_plan == 12345,
        "agent_data_plane_isolation": school_1_plan != school_2_plan,
    }
    result = {
        "evaluation_kind": "agent_service_school_isolation_verification",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "question": "2026年招生计划数是多少",
        "school_1": {
            "plan_count": school_1_plan,
            "strategy": school_1.get("risk_decision", {}).get("strategy"),
            "school_context": school_1.get("school_context"),
        },
        "school_2": {
            "plan_count": school_2_plan,
            "strategy": school_2.get("risk_decision", {}).get("strategy"),
            "school_context": school_2.get("school_context"),
        },
        "checks": checks,
        "status": "passed" if all(checks.values()) else "failed",
        "boundary": (
            "两种学校使用独立 MySQL 数据面，但共用同一控制库管理员账号；"
            "本验证不代表非管理员账号权限矩阵已完成生产审计。"
        ),
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
