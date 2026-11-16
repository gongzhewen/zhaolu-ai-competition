from __future__ import annotations

import copy
import hashlib
import json
import time
from typing import Any

from agent_core.contracts import AgentContext, ToolCall
from app.core.config import settings
from app.core.permissions import is_super_admin
from app.core.redis_cache import shared_get_json, shared_set_json
from app.modules.agent.tools.registry import NATIVE_TOOL_EXECUTORS
from sqlalchemy.ext.asyncio import AsyncSession

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_MAX_ENTRIES = 512


def clear_hybrid_tool_cache() -> None:
    _CACHE.clear()
_NEVER_CACHE = {"student_lookup", "student_statistics"}


class HybridToolExecutor:
    def __init__(self, db: AsyncSession, *, user: Any, prefer_native: bool = True) -> None:
        self.db = db
        self.user = user
        self.prefer_native = prefer_native

    def _params(self, call: ToolCall, context: AgentContext) -> dict[str, Any]:
        params = {
            **call.params,
            "school_id": context.school_id,
            "user": self.user,
            "can_lookup_students": bool(self.user and is_super_admin(self.user)),
        }
        if not params.get("query"):
            params["query"] = call.params.get("message") or ""
        return params

    def _cache_key(self, call: ToolCall, context: AgentContext, params: dict[str, Any]) -> str:
        payload = {
            "tool": call.name,
            "school_id": context.school_id,
            "params": {key: value for key, value in params.items() if key not in {"user", "can_lookup_students"}},
        }
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()

    async def __call__(self, call: ToolCall, context: AgentContext) -> dict[str, Any]:
        executor = NATIVE_TOOL_EXECUTORS.get(call.name) if self.prefer_native else None
        if executor is None:
            from app.modules.agent.legacy_adapter import LegacyToolAdapter

            return await LegacyToolAdapter(self.db, user=self.user)(call, context)

        params = self._params(call, context)
        cache_key = self._cache_key(call, context, params)
        if call.name not in _NEVER_CACHE:
            cached = _CACHE.get(cache_key)
            if cached and cached[0] > time.monotonic():
                result = copy.deepcopy(cached[1])
                result["cache_hit"] = True
                result["_cache_layer"] = "l1"
                return result
            shared_value = await shared_get_json(
                "agent:tool",
                cache_key,
                context.school_id,
            )
            if isinstance(shared_value, dict):
                _CACHE[cache_key] = (
                    time.monotonic() + max(1, settings.agent_cache_ttl_seconds),
                    copy.deepcopy(shared_value),
                )
                result = copy.deepcopy(shared_value)
                result["cache_hit"] = True
                result["_cache_layer"] = "l2"
                return result

        result = await executor(self.db, params)
        result["cache_hit"] = False
        result["_cache_layer"] = "bypass" if call.name in _NEVER_CACHE else "miss"
        if call.name not in _NEVER_CACHE:
            if len(_CACHE) >= _CACHE_MAX_ENTRIES:
                _CACHE.clear()
            _CACHE[cache_key] = (
                time.monotonic() + max(1, settings.agent_cache_ttl_seconds),
                copy.deepcopy({key: value for key, value in result.items() if key != "_cache_layer"}),
            )
            await shared_set_json(
                "agent:tool",
                cache_key,
                {key: value for key, value in result.items() if key != "_cache_layer"},
                school_id=context.school_id,
                ttl_seconds=settings.agent_cache_ttl_seconds,
            )
        return result


def build_hybrid_tool_executor(
    db: AsyncSession,
    *,
    user: Any,
    prefer_native: bool = True,
) -> HybridToolExecutor:
    return HybridToolExecutor(db, user=user, prefer_native=prefer_native)
