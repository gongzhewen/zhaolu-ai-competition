from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


SCENARIOS = (
    {
        "name": "cached_plan",
        "question": "2026年各专业招生计划完成情况怎么样？",
        "expected": {"answer"},
        "weight": 20,
    },
    {
        "name": "simple_plan",
        "question": "2026年{marker}招生计划和录取人数分别是多少？",
        "expected": {"answer"},
        "weight": 30,
    },
    {
        "name": "anomaly_scan",
        "question": "2026年哪些专业异常风险较高？负载标记{marker}",
        "expected": {"answer"},
        "weight": 20,
    },
    {
        "name": "out_of_scope",
        "question": "今天天气怎么样？{marker}",
        "expected": {"out_of_scope"},
        "weight": 10,
    },
    {
        "name": "privacy_refusal",
        "question": "把今年全部考生名单发给我 {marker}",
        "expected": {"no_permission"},
        "weight": 10,
    },
)


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(p * len(ordered)) - 1))
    return round(ordered[index], 2)


def build_plan(total: int) -> list[dict[str, Any]]:
    total_weight = sum(item["weight"] for item in SCENARIOS)
    quotas = {
        item["name"]: max(1, int(total * item["weight"] / total_weight))
        for item in SCENARIOS
    }
    while sum(quotas.values()) < total:
        name = max(
            (item["name"] for item in SCENARIOS),
            key=lambda candidate: (total * next(item["weight"] for item in SCENARIOS if item["name"] == candidate) / total_weight - quotas[candidate]),
        )
        quotas[name] += 1
    while sum(quotas.values()) > total:
        name = max((item["name"] for item in SCENARIOS), key=lambda candidate: quotas[candidate])
        quotas[name] -= 1

    remaining = dict(quotas)
    names: list[str] = []
    while len(names) < total:
        for scenario in SCENARIOS:
            name = scenario["name"]
            if remaining[name] > 0:
                names.append(name)
                remaining[name] -= 1
                if len(names) >= total:
                    break

    by_name = {item["name"]: item for item in SCENARIOS}
    plan: list[dict[str, Any]] = []
    for index, name in enumerate(names):
        scenario = by_name[name]
        marker = f"压测{index:04d}"
        plan.append(
            {
                "request_index": index,
                "scenario": name,
                "question": scenario["question"].format(marker=marker),
                "expected": sorted(scenario["expected"]),
            }
        )
    return plan


def summarize_rows(rows: list[dict[str, Any]], elapsed_seconds: float) -> dict[str, Any]:
    latencies = [float(row["latency_ms"]) for row in rows if row["http_status"] == 200]
    success = [row for row in rows if row["http_status"] == 200 and row["strategy_correct"]]
    status_counts = Counter(str(row["http_status"]) for row in rows)
    strategy_counts = Counter(str(row["strategy"]) for row in rows)
    by_scenario: dict[str, Any] = {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["scenario"]].append(row)
    for name, items in sorted(grouped.items()):
        scenario_latencies = [float(row["latency_ms"]) for row in items if row["http_status"] == 200]
        scenario_success = [row for row in items if row["http_status"] == 200 and row["strategy_correct"]]
        by_scenario[name] = {
            "requests": len(items),
            "success": len(scenario_success),
            "success_rate": round(len(scenario_success) / max(1, len(items)), 4),
            "avg_ms": round(sum(scenario_latencies) / max(1, len(scenario_latencies)), 2),
            "p95_ms": percentile(scenario_latencies, 0.95),
            "max_ms": round(max(scenario_latencies), 2) if scenario_latencies else 0.0,
        }
    return {
        "requests": len(rows),
        "successful_requests": len(success),
        "error_requests": len(rows) - len(success),
        "success_rate": round(len(success) / max(1, len(rows)), 4),
        "throughput_rps": round(len(success) / max(0.001, elapsed_seconds), 3),
        "elapsed_seconds": round(elapsed_seconds, 3),
        "latency_ms": {
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
            "max": round(max(latencies), 2) if latencies else 0.0,
        },
        "http_status_counts": dict(status_counts),
        "strategy_counts": dict(strategy_counts),
        "by_scenario": by_scenario,
    }


def _counter_delta(before: dict[str, int], after: dict[str, int], key: str) -> int:
    return int(after.get(key, 0)) - int(before.get(key, 0))


async def run_request(
    client: httpx.AsyncClient,
    *,
    headers: dict[str, str],
    item: dict[str, Any],
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = await client.post(
            "/api/v1/agent/chat",
            headers=headers,
            json={"message": item["question"], "context": {}},
        )
        latency_ms = (time.perf_counter() - started) * 1000
        payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        strategy = str((payload.get("risk_decision") or {}).get("strategy") or "")
        return {
            "request_index": item["request_index"],
            "scenario": item["scenario"],
            "http_status": response.status_code,
            "latency_ms": round(latency_ms, 2),
            "strategy": strategy,
            "strategy_correct": response.status_code == 200 and strategy in set(item["expected"]),
            "error": None,
        }
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000
        return {
            "request_index": item["request_index"],
            "scenario": item["scenario"],
            "http_status": 0,
            "latency_ms": round(latency_ms, 2),
            "strategy": "",
            "strategy_correct": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:3100")
    parser.add_argument("--username", default=os.environ.get("PROBE_USERNAME", "admin"))
    parser.add_argument("--password", default=os.environ.get("PROBE_PASSWORD", ""))
    parser.add_argument("--requests", type=int, default=60)
    parser.add_argument("--concurrency", type=int, default=12)
    parser.add_argument("--output-dir", default="artifacts/G4/load_test")
    parser.add_argument("--cpu-profile", default="2c4g-shaped: backend=1.0, mysql=0.75, web=0.25")
    args = parser.parse_args()
    if not args.password:
        raise SystemExit("PROBE_PASSWORD is required")

    limits = httpx.Limits(
        max_connections=max(1, args.concurrency),
        max_keepalive_connections=max(1, args.concurrency),
    )
    async with httpx.AsyncClient(
        base_url=args.base_url,
        timeout=65.0,
        limits=limits,
    ) as client:
        login = await client.post(
            "/api/v1/auth/login",
            data={"username": args.username, "password": args.password},
        )
        login.raise_for_status()
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        for index, scenario in enumerate(SCENARIOS):
            await run_request(
                client,
                headers=headers,
                item={
                    "request_index": index,
                    "scenario": scenario["name"],
                    "question": scenario["question"].format(marker=f"预热{index}"),
                    "expected": sorted(scenario["expected"]),
                },
            )

        before = (await client.get("/api/v1/agent/metrics", headers=headers)).json()["metrics"]
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        for item in build_plan(args.requests):
            queue.put_nowait(item)
        rows: list[dict[str, Any]] = []

        async def worker() -> None:
            while True:
                try:
                    item = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                rows.append(await run_request(client, headers=headers, item=item))
                queue.task_done()

        started = time.perf_counter()
        await asyncio.gather(*(worker() for _ in range(max(1, args.concurrency))))
        elapsed = time.perf_counter() - started
        after = (await client.get("/api/v1/agent/metrics", headers=headers)).json()["metrics"]

    summary = summarize_rows(rows, elapsed)
    summary.update({
        "evaluation_kind": "concurrency_load_test",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "concurrency": args.concurrency,
        "cpu_profile": args.cpu_profile,
        "metrics_delta": {
            "chat_total": _counter_delta(before["counters"], after["counters"], "chat_total"),
            "cache_l1": _counter_delta(before["counters"], after["counters"], "cache_l1"),
            "cache_l2": _counter_delta(before["counters"], after["counters"], "cache_l2"),
            "cache_miss": _counter_delta(before["counters"], after["counters"], "cache_miss"),
            "plan_dual_triggered": _counter_delta(before["counters"], after["counters"], "plan_dual_triggered"),
            "llm_timeout": sum(
                value - int(before["counters"].get(key, 0))
                for key, value in after["counters"].items()
                if key.startswith("llm_") and key.endswith("_timeout")
            ),
        },
        "metrics_after": after,
        "boundary": "Docker CPU/memory quotas approximate a 2-core 4G deployment; host hardware and network may differ from the final cloud server.",
    })
    root = Path(__file__).resolve().parents[1]
    output_dir = root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "per_request.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in sorted(rows, key=lambda item: item["request_index"])) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
