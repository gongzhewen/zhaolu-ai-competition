from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx
from redis.asyncio import Redis


async def login(client: httpx.AsyncClient, username: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": password},
    )
    response.raise_for_status()
    return response.json()["access_token"]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url-1", default="http://127.0.0.1:8011")
    parser.add_argument("--base-url-2", default="http://127.0.0.1:8012")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default=os.environ.get("PROBE_PASSWORD", "ChangeMe123!"))
    parser.add_argument("--redis-url", default="redis://127.0.0.1:6379/14")
    parser.add_argument("--output", default="artifacts/G8/multinstance_http_20261110.json")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)

    redis_client = Redis.from_url(args.redis_url, decode_responses=True)
    await redis_client.flushdb()
    await redis_client.aclose()

    async with (
        httpx.AsyncClient(base_url=args.base_url_1, timeout=90.0) as client_1,
        httpx.AsyncClient(base_url=args.base_url_2, timeout=90.0) as client_2,
    ):
        health_1 = (await client_1.get("/api/v1/health")).json()
        health_2 = (await client_2.get("/api/v1/health")).json()
        token_1 = await login(client_1, args.username, args.password)
        token_2 = await login(client_2, args.username, args.password)
        headers_1 = {"Authorization": f"Bearer {token_1}"}
        headers_2 = {"Authorization": f"Bearer {token_2}"}
        payload = {
            "message": "2026年各专业招生计划完成情况怎么样？",
            "context": {},
        }
        started_1 = perf_counter()
        response_1 = await client_1.post("/api/v1/agent/chat", headers=headers_1, json=payload)
        response_1.raise_for_status()
        latency_1 = round((perf_counter() - started_1) * 1000, 2)
        started_2 = perf_counter()
        response_2 = await client_2.post("/api/v1/agent/chat", headers=headers_2, json=payload)
        response_2.raise_for_status()
        latency_2 = round((perf_counter() - started_2) * 1000, 2)
        metrics_1 = (await client_1.get("/api/v1/agent/metrics", headers=headers_1)).json()
        metrics_2 = (await client_2.get("/api/v1/agent/metrics", headers=headers_2)).json()

    result_1 = response_1.json()
    result_2 = response_2.json()
    first_hits = [item.get("cache_hit") for item in result_1.get("tool_results", [])]
    second_hits = [item.get("cache_hit") for item in result_2.get("tool_results", [])]
    counters_1 = metrics_1.get("metrics", {}).get("counters", {})
    counters_2 = metrics_2.get("metrics", {}).get("counters", {})
    metric_source_1 = metrics_1.get("metrics", {}).get("source")
    metric_source_2 = metrics_2.get("metrics", {}).get("source")
    checks = {
        "two_instances_healthy": (
            health_1.get("status") == "ok"
            and health_2.get("status") == "ok"
            and health_1.get("instance_id") != health_2.get("instance_id")
        ),
        "redis_available_on_both_instances": (
            health_1.get("redis", {}).get("available") is True
            and health_2.get("redis", {}).get("available") is True
        ),
        "cross_instance_l2_cache_hit": (
            bool(first_hits)
            and not any(first_hits)
            and bool(second_hits)
            and any(second_hits)
        ),
        "shared_metrics_aggregate": (
            metric_source_1 == "redis"
            and metric_source_2 == "redis"
            and int(counters_1.get("chat_total", 0)) >= 2
            and counters_1.get("chat_total") == counters_2.get("chat_total")
        ),
    }
    report: dict[str, Any] = {
        "evaluation_kind": "two_instance_http_redis_verification",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "instances": [
            {
                "base_url": args.base_url_1,
                "instance_id": health_1.get("instance_id"),
                "redis": health_1.get("redis"),
                "latency_ms": latency_1,
                "tool_cache_hits": first_hits,
                "strategy": (result_1.get("risk_decision") or {}).get("strategy"),
            },
            {
                "base_url": args.base_url_2,
                "instance_id": health_2.get("instance_id"),
                "redis": health_2.get("redis"),
                "latency_ms": latency_2,
                "tool_cache_hits": second_hits,
                "strategy": (result_2.get("risk_decision") or {}).get("strategy"),
            },
        ],
        "checks": checks,
        "metrics": {
            "source_1": metric_source_1,
            "source_2": metric_source_2,
            "chat_total_1": counters_1.get("chat_total"),
            "chat_total_2": counters_2.get("chat_total"),
            "cache_l2": counters_1.get("cache_l2"),
        },
        "status": "passed" if all(checks.values()) else "failed",
        "boundary": (
            "两个独立 Uvicorn 进程共用同一 MySQL 与 Redis，验证应用层共享缓存和指标聚合；"
            "不代表生产 Redis 集群或跨主机网络故障验证。"
        ),
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
