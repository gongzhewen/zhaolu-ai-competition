from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


async def login(client: httpx.AsyncClient, username: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": password},
    )
    response.raise_for_status()
    return response.json()["access_token"]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8013")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="ChangeMe123!")
    parser.add_argument("--output", default="artifacts/G12/feedback_learning_20261110.json")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%H%M%S")

    async with httpx.AsyncClient(base_url=args.base_url, timeout=120.0) as client:
        token = await login(client, args.username, args.password)
        headers = {"Authorization": f"Bearer {token}"}

        context_history: list[dict[str, str]] = []
        first = await client.post(
            "/api/v1/ai/chat",
            headers=headers,
            json={
                "message": "分析2026年录取的王小明",
                "context": {"history": context_history},
            },
        )
        first.raise_for_status()
        context_history.extend(
            [
                {"role": "user", "content": "分析2026年录取的王小明"},
                {"role": "assistant", "content": first.json()["answer"]},
            ]
        )
        follow_up = await client.post(
            "/api/v1/ai/chat",
            headers=headers,
            json={
                "message": "他的成绩是多少？",
                "context": {"history": context_history},
            },
        )
        follow_up.raise_for_status()

        questions = (
            f"2026年招生计划数是多少？反馈验证{run_id}A",
            f"2025年招生计划数是多少？反馈验证{run_id}B",
            f"2024年各专业录取数是多少？反馈验证{run_id}C",
            f"2023年各省招生计划是多少？反馈验证{run_id}D",
        )
        feedback_runs: list[dict[str, Any]] = []
        for index, question in enumerate(questions, start=1):
            chat = await client.post(
                "/api/v1/ai/chat",
                headers=headers,
                json={"message": question, "context": {"history": []}},
            )
            chat.raise_for_status()
            chat_result = chat.json()
            feedback = await client.post(
                "/api/v1/ai/feedback",
                headers=headers,
                json={
                    "message_id": chat_result["message_id"],
                    "rating": 1,
                    "question": question,
                    "answer": chat_result["answer"],
                    "reason": (
                        "请复核年份、筛选条件和指标覆盖"
                        if index % 2
                        else "请复核数字口径和工具证据"
                    ),
                    "history": [],
                },
            )
            feedback.raise_for_status()
            feedback_result = feedback.json()
            reflection = feedback_result.get("reflection") or {}
            feedback_runs.append(
                {
                    "question": question,
                    "original_answer": chat_result["answer"],
                    "error_points": reflection.get("error_points") or [],
                    "second_answer": reflection.get("second_answer"),
                    "selection_mode": reflection.get("selection_mode"),
                    "compression": reflection.get("compression") or {},
                }
            )

    follow_up_result = follow_up.json()
    checks = {
        "context_follow_up_resolved": bool(
            (follow_up_result.get("context_resolution") or {}).get("used")
        ),
        "context_contains_student": "王小明"
        in str(follow_up_result.get("contextual_question") or ""),
        "all_feedback_reflections_completed": all(
            item["second_answer"] and item["selection_mode"]
            for item in feedback_runs
        ),
        "reflection_memories_compressed": any(
            (item["compression"] or {}).get("compressed")
            for item in feedback_runs
        ),
    }
    report = {
        "evaluation_kind": "feedback_learning_and_context_verification",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run_id": run_id,
        "context": {
            "original_question": follow_up_result.get("original_question"),
            "contextual_question": follow_up_result.get("contextual_question"),
            "resolution": follow_up_result.get("context_resolution"),
        },
        "feedback_runs": feedback_runs,
        "checks": checks,
        "status": "passed" if all(checks.values()) else "failed",
        "boundary": (
            "否定反馈会生成反思记忆并触发二次受控工具复核；"
            "不等同于模型参数训练，也不会绕过数据证据直接改写规则。"
        ),
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
