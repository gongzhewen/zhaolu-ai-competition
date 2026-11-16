from __future__ import annotations

import json
import math
import re
from collections import deque
from typing import Any

from redis.exceptions import RedisError

from app.core.config import settings
from app.core.redis_cache import get_redis_client

_fallback_samples: deque[float] = deque(maxlen=max(100, settings.runtime_metrics_window_size))
_fallback_counters: dict[str, int] = {}


def _samples_key() -> str:
    return f"{settings.redis_key_prefix}:runtime:chat:samples"


def _counters_key() -> str:
    return f"{settings.redis_key_prefix}:runtime:counters"


def reset_runtime_metrics() -> None:
    _fallback_samples.clear()
    _fallback_counters.clear()


async def record_chat_metric(
    *,
    duration_ms: float,
    route_mode: str,
    cache_layers: list[str],
    tool_count: int,
    multi_planning_triggered: bool = False,
    strategy: str = "unknown",
) -> None:
    sample = {
        "duration_ms": round(max(0.0, duration_ms), 2),
        "route_mode": route_mode,
        "tool_count": tool_count,
    }
    _fallback_samples.append(sample["duration_ms"])
    counters = {
        "chat_total": 1,
        f"route_{route_mode}": 1,
        "tool_total": max(0, tool_count),
        "plan_total": 1,
        f"strategy_{strategy}": 1,
    }
    if multi_planning_triggered:
        counters["plan_dual_triggered"] = 1
    for layer in cache_layers:
        counters[f"cache_{layer.lower()}"] = counters.get(f"cache_{layer.lower()}", 0) + 1
    for key, value in counters.items():
        _fallback_counters[key] = _fallback_counters.get(key, 0) + value

    client = await get_redis_client()
    if client is None:
        return
    try:
        async with client.pipeline(transaction=False) as pipe:
            pipe.lpush(_samples_key(), json.dumps(sample, ensure_ascii=False))
            pipe.ltrim(_samples_key(), 0, max(99, settings.runtime_metrics_window_size - 1))
            for key, value in counters.items():
                pipe.hincrby(_counters_key(), key, value)
            await pipe.execute()
    except RedisError:
        return


async def record_llm_metric(
    *,
    kind: str,
    status: str,
    duration_ms: float,
    version: str | None = None,
) -> None:
    key = f"llm_{kind}_{status}".lower()
    _fallback_counters[key] = _fallback_counters.get(key, 0) + 1
    if version:
        version_key = re.sub(r"[^a-z0-9_-]+", "_", version.lower())
        version_metric = f"llm_version_{version_key}_{status}"
        _fallback_counters[version_metric] = _fallback_counters.get(version_metric, 0) + 1
    client = await get_redis_client()
    if client is None:
        return
    try:
        async with client.pipeline(transaction=False) as pipe:
            pipe.hincrby(_counters_key(), key, 1)
            if version:
                pipe.hincrby(_counters_key(), version_metric, 1)
            await pipe.execute()
    except RedisError:
        return


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered))) - 1
    return round(ordered[min(rank, len(ordered) - 1)], 2)


async def metrics_snapshot() -> dict[str, Any]:
    samples: list[float] = list(_fallback_samples)
    counters: dict[str, int] = dict(_fallback_counters)
    source = "memory"
    client = await get_redis_client()
    if client is not None:
        try:
            raw_samples, raw_counters = await client.pipeline(transaction=False).lrange(
                _samples_key(), 0, settings.runtime_metrics_window_size - 1
            ).hgetall(_counters_key()).execute()
            samples = [
                float(json.loads(item)["duration_ms"])
                for item in raw_samples
                if item
            ]
            counters = {key: int(value) for key, value in raw_counters.items()}
            source = "redis"
        except (RedisError, TypeError, ValueError, json.JSONDecodeError):
            pass

    chat_total = max(0, counters.get("chat_total", 0))
    cache_l1 = max(0, counters.get("cache_l1", 0))
    cache_l2 = max(0, counters.get("cache_l2", 0))
    cache_miss = max(0, counters.get("cache_miss", 0))
    cache_denominator = max(1, cache_l1 + cache_l2 + cache_miss)
    llm_outcome_keys = [
        key
        for key in counters
        if key.startswith("llm_") and key.rsplit("_", 1)[-1] in {"success", "timeout", "error", "rejected"}
    ]
    llm_total = sum(counters[key] for key in llm_outcome_keys)
    llm_timeout = sum(counters[key] for key in llm_outcome_keys if key.endswith("_timeout"))
    llm_rejected = sum(counters[key] for key in llm_outcome_keys if key.endswith("_rejected"))
    model_versions: dict[str, dict[str, int]] = {}
    for key, value in counters.items():
        if not key.startswith("llm_version_"):
            continue
        remainder = key.removeprefix("llm_version_")
        version_name, separator, status = remainder.rpartition("_")
        if not separator or status not in {"success", "timeout", "error", "rejected"}:
            continue
        model_versions.setdefault(version_name, {})[status] = int(value)
    plan_total = max(0, counters.get("plan_total", 0))
    strategy_total = max(1, sum(counters.get(f"strategy_{name}", 0) for name in ("answer", "clarify", "no_data", "no_permission", "out_of_scope", "insufficient_data", "error")))
    latency_p95 = _percentile(samples, 0.95)
    return {
        "source": source,
        "sample_count": len(samples),
        "formal_constraints": {
            "unsupported_answer_alpha": settings.agent_unsupported_answer_alpha,
            "p95_latency_budget_ms": settings.agent_p95_latency_budget_ms,
            "p95_within_budget": latency_p95 <= settings.agent_p95_latency_budget_ms,
        },
        "latency_ms": {
            "p50": _percentile(samples, 0.50),
            "p95": latency_p95,
            "p99": _percentile(samples, 0.99),
            "max": round(max(samples), 2) if samples else 0.0,
        },
        "counters": counters,
        "rates": {
            "fast_route_rate": round(counters.get("route_fast", 0) / max(1, chat_total), 4),
            "cache_hit_rate": round((cache_l1 + cache_l2) / cache_denominator, 4),
            "cache_l2_rate": round(cache_l2 / cache_denominator, 4),
            "dual_planning_trigger_rate": round(counters.get("plan_dual_triggered", 0) / max(1, plan_total), 4),
            "llm_timeout_rate": round(llm_timeout / max(1, llm_total), 4),
            "llm_rejection_rate": round(llm_rejected / max(1, llm_total), 4),
            "model_versions": model_versions,
            "answer_rate": round(counters.get("strategy_answer", 0) / strategy_total, 4),
            "clarification_rate": round(counters.get("strategy_clarify", 0) / strategy_total, 4),
            "refusal_rate": round(
                (
                    counters.get("strategy_insufficient_data", 0)
                    + counters.get("strategy_no_data", 0)
                    + counters.get("strategy_no_permission", 0)
                    + counters.get("strategy_out_of_scope", 0)
                )
                / strategy_total,
                4,
            ),
        },
    }

