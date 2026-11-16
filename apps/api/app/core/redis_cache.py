from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: Redis | None = None
_unavailable_until = 0.0
_last_error: str | None = None


def _prefix() -> str:
    return settings.redis_key_prefix.strip(":") or "zhaolu"


def _global_version_key() -> str:
    return f"{_prefix()}:cache:version:global"


def _school_version_key(school_id: int | None) -> str:
    return f"{_prefix()}:cache:version:school:{school_id or 'default'}"


async def get_redis_client() -> Redis | None:
    global _client, _unavailable_until, _last_error
    if not settings.redis_enabled or not settings.redis_url:
        return None
    if time.monotonic() < _unavailable_until:
        return None
    if _client is None:
        _client = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=0.75,
            socket_timeout=1.5,
            health_check_interval=30,
        )
        try:
            await _client.ping()
            _last_error = None
        except RedisError as exc:
            _last_error = str(exc)
            _unavailable_until = time.monotonic() + 30
            logger.warning("Redis unavailable, using in-process fallback: %s", exc)
            return None
    return _client


def _mark_unavailable(exc: Exception) -> None:
    global _unavailable_until, _last_error
    _last_error = str(exc)
    _unavailable_until = time.monotonic() + 30
    logger.warning("Redis operation failed, using in-process fallback: %s", exc)


async def _get_version(key: str) -> int:
    client = await get_redis_client()
    if client is None:
        return 1
    try:
        value = await client.get(key)
        if value is None:
            await client.set(key, 1, nx=True)
            value = await client.get(key)
        return int(value or 1)
    except (RedisError, TypeError, ValueError) as exc:
        _mark_unavailable(exc)
        return 1


async def _bump_version(key: str) -> int:
    client = await get_redis_client()
    if client is None:
        return 1
    try:
        return int(await client.incr(key))
    except (RedisError, TypeError, ValueError) as exc:
        _mark_unavailable(exc)
        return 1


async def versioned_key(namespace: str, raw_key: str, school_id: int | None) -> str:
    global_version = await _get_version(_global_version_key())
    school_version = await _get_version(_school_version_key(school_id))
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    return (
        f"{_prefix()}:{namespace}:g{global_version}:"
        f"s{school_id or 'default'}:v{school_version}:{digest}"
    )


async def shared_get_json(namespace: str, raw_key: str, school_id: int | None) -> Any | None:
    client = await get_redis_client()
    if client is None:
        return None
    key = await versioned_key(namespace, raw_key, school_id)
    try:
        payload = await client.get(key)
        return json.loads(payload) if payload else None
    except (RedisError, json.JSONDecodeError) as exc:
        _mark_unavailable(exc)
        return None


async def shared_set_json(
    namespace: str,
    raw_key: str,
    value: Any,
    *,
    school_id: int | None,
    ttl_seconds: int,
) -> bool:
    client = await get_redis_client()
    if client is None:
        return False
    key = await versioned_key(namespace, raw_key, school_id)
    try:
        payload = json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
        await client.set(key, payload, ex=max(1, ttl_seconds))
        return True
    except (RedisError, TypeError, ValueError) as exc:
        _mark_unavailable(exc)
        return False


async def invalidate_shared_cache(school_id: int | None = None) -> int:
    if school_id is None:
        return await _bump_version(_global_version_key())
    return await _bump_version(_school_version_key(school_id))


async def redis_health() -> dict[str, Any]:
    client = await get_redis_client()
    if client is None:
        return {
            "enabled": settings.redis_enabled,
            "available": False,
            "error": _last_error,
        }
    started = time.perf_counter()
    try:
        await client.ping()
        return {
            "enabled": True,
            "available": True,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }
    except RedisError as exc:
        _mark_unavailable(exc)
        return {"enabled": True, "available": False, "error": str(exc)}


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None

