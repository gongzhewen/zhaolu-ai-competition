from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from redis.asyncio import Redis


def worker_env(redis_url: str, prefix: str) -> dict[str, str]:
    env = os.environ.copy()
    env["REDIS_ENABLED"] = "true"
    env["REDIS_URL"] = redis_url
    env["REDIS_KEY_PREFIX"] = prefix
    env["PYTHONUTF8"] = "1"
    root = str(Path(__file__).resolve().parents[1])
    paths = [
        root,
        str(Path(root) / "packages" / "agent_core"),
        str(Path(root) / "packages" / "data_contracts"),
        str(Path(root) / "apps" / "api"),
    ]
    env["PYTHONPATH"] = os.pathsep.join(paths)
    return env


def run_worker(
    env: dict[str, str],
    *args: str,
) -> dict[str, Any]:
    process = subprocess.run(
        [sys.executable, "-m", "scripts.redis_cache_worker", *args],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(
            f"redis worker failed: {' '.join(args)}\n"
            f"stdout={process.stdout}\nstderr={process.stderr}"
        )
    return json.loads(process.stdout)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis-url", default="redis://127.0.0.1:6379/15")
    parser.add_argument("--prefix", default="zhaolu_verify")
    parser.add_argument("--output", default="artifacts/G8/redis_multinstance_20261110.json")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)

    client = Redis.from_url(args.redis_url, decode_responses=True)
    await client.flushdb()
    await client.aclose()
    env = worker_env(args.redis_url, args.prefix)

    write_result = run_worker(
        env,
        "put",
        "--raw-key",
        "cross-instance",
        "--school-id",
        "1",
        "--value",
        "shared-value",
    )
    read_result = run_worker(
        env,
        "get",
        "--raw-key",
        "cross-instance",
        "--school-id",
        "1",
    )
    run_worker(env, "invalidate", "--school-id", "1")
    after_school_invalidation = run_worker(
        env,
        "get",
        "--raw-key",
        "cross-instance",
        "--school-id",
        "1",
    )

    run_worker(
        env,
        "put",
        "--raw-key",
        "school-2",
        "--school-id",
        "2",
        "--value",
        "school-2-value",
    )
    run_worker(env, "invalidate", "--school-id", "1")
    school_2_after_school_1_invalidation = run_worker(
        env,
        "get",
        "--raw-key",
        "school-2",
        "--school-id",
        "2",
    )
    run_worker(env, "invalidate")
    school_2_after_global_invalidation = run_worker(
        env,
        "get",
        "--raw-key",
        "school-2",
        "--school-id",
        "2",
    )

    run_worker(env, "metric", "--duration-ms", "31")
    run_worker(env, "metric", "--duration-ms", "47")
    metrics = run_worker(env, "metrics")
    checks = {
        "cross_process_shared_hit": (
            write_result.get("ok") is True
            and read_result.get("value", {}).get("value") == "shared-value"
        ),
        "school_version_invalidation": after_school_invalidation.get("value") is None,
        "school_scope_isolation": (
            school_2_after_school_1_invalidation.get("value", {}).get("value")
            == "school-2-value"
        ),
        "global_version_invalidation": school_2_after_global_invalidation.get("value") is None,
        "redis_metric_aggregation": metrics.get("source") == "redis"
        and int(metrics.get("counters", {}).get("chat_total", 0)) >= 2,
    }
    result = {
        "evaluation_kind": "redis_shared_cache_multiprocess_verification",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "redis_url": args.redis_url,
        "namespace": args.prefix,
        "independent_processes": 6,
        "checks": checks,
        "status": "passed" if all(checks.values()) else "failed",
        "metrics": {
            "source": metrics.get("source"),
            "sample_count": metrics.get("sample_count"),
            "latency_ms": metrics.get("latency_ms"),
            "cache_hit_rate": metrics.get("rates", {}).get("cache_hit_rate"),
            "chat_total": metrics.get("counters", {}).get("chat_total"),
        },
        "boundary": (
            "本验证使用独立 Redis DB 和多个独立 Python 进程模拟应用实例；"
            "不等同于生产 Redis 集群、网络分区或高可用故障演练。"
        ),
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
