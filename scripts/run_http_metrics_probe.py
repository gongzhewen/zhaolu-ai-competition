from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


def _counter_delta(before: dict[str, int], after: dict[str, int], key: str) -> int:
    return int(after.get(key, 0)) - int(before.get(key, 0))


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:3000")
    parser.add_argument("--username", default=os.environ.get("PROBE_USERNAME", "admin"))
    parser.add_argument("--password", default=os.environ.get("PROBE_PASSWORD", ""))
    parser.add_argument("--output", default="artifacts/G3/http_metrics_probe.json")
    args = parser.parse_args()
    if not args.password:
        raise SystemExit("PROBE_PASSWORD is required")

    async with httpx.AsyncClient(base_url=args.base_url, timeout=60.0) as client:
        login = await client.post(
            "/api/v1/auth/login",
            data={"username": args.username, "password": args.password},
        )
        login.raise_for_status()
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        before = (await client.get("/api/v1/agent/metrics", headers=headers)).json()["metrics"]
        probe_question = (
            "2026年各专业招生计划完成情况怎么样？"
            f"性能探针{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        )
        first = await client.post(
            "/api/v1/agent/chat",
            headers=headers,
            json={"message": probe_question, "context": {}},
        )
        first.raise_for_status()
        second = await client.post(
            "/api/v1/agent/chat",
            headers=headers,
            json={"message": probe_question, "context": {}},
        )
        second.raise_for_status()
        after = (await client.get("/api/v1/agent/metrics", headers=headers)).json()["metrics"]

    first_result = first.json()
    second_result = second.json()
    cache_l1_delta = _counter_delta(before["counters"], after["counters"], "cache_l1")
    cache_miss_delta = _counter_delta(before["counters"], after["counters"], "cache_miss")
    chat_delta = _counter_delta(before["counters"], after["counters"], "chat_total")
    result: dict[str, Any] = {
        "evaluation_kind": "http_runtime_metrics_probe",
        "base_url": args.base_url,
        "question": probe_question,
        "chat_runs": chat_delta,
        "cache_l1_delta": cache_l1_delta,
        "cache_miss_delta": cache_miss_delta,
        "expected_cache_miss_then_hit": cache_miss_delta == 1 and cache_l1_delta >= 1,
        "first_strategy": (first_result.get("risk_decision") or {}).get("strategy"),
        "second_strategy": (second_result.get("risk_decision") or {}).get("strategy"),
        "first_tool_cache_hits": [
            item.get("cache_hit") for item in first_result.get("tool_results", [])
        ],
        "second_tool_cache_hits": [
            item.get("cache_hit") for item in second_result.get("tool_results", [])
        ],
        "metrics_after": after,
        "boundary": "单实例、无 Redis、演示数据下的 HTTP 缓存与运行时指标探针，不代表并发容量。",
    }
    root = Path(__file__).resolve().parents[1]
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
