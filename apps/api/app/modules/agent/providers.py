from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from agent_core.contracts import RouteDecision, ToolCall
from agent_core.registry import TOOL_BY_NAME
from app.modules.agent_intelligence.memory import load_relevant_memories, remember_turn
from app.modules.ai_gateway.minimind_router import minimind_router
from app.modules.rag.service import search_knowledge
from sqlalchemy.ext.asyncio import AsyncSession

BLOCKED_LOCAL_MODEL_TOOLS = {"student_lookup", "student_statistics"}
_PLAN_CACHE: dict[str, tuple[float, list[ToolCall]]] = {}
_PLAN_CACHE_MAX_ENTRIES = 256
_PLAN_CACHE_SECONDS = 300


def clear_planner_cache() -> None:
    _PLAN_CACHE.clear()


class SQLAlchemyKnowledgeProvider:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def search(self, query: str, *, school_id: int | None, limit: int = 4) -> list[dict[str, Any]]:
        return await search_knowledge(self.db, query=query, school_id=school_id, limit=limit)


class SQLAlchemyMemoryProvider:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def load(self, query: str, *, user_id: int, school_id: int | None, limit: int = 5) -> list[dict[str, Any]]:
        return await load_relevant_memories(
            self.db,
            user_id=user_id,
            school_id=school_id,
            query=query,
            limit=limit,
        )

    async def remember(self, payload: dict[str, Any]) -> None:
        if payload.get("user_id") is None or payload.get("conversation_id") is None:
            return
        await remember_turn(
            self.db,
            user_id=payload.get("user_id"),
            school_id=payload.get("school_id"),
            conversation_id=int(payload["conversation_id"]),
            question=str(payload.get("question") or ""),
            intent=str(payload.get("intent") or ""),
            answer=str(payload.get("answer") or ""),
        )


def _cache_key(decision: RouteDecision, history: list[dict[str, str]]) -> str:
    payload = {
        "message": decision.normalized_message,
        "intent": decision.intent,
        "params": decision.params,
        "history": history[-4:],
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


class CompositePlanner:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def plan(self, decision: RouteDecision, *, history: list[dict[str, str]]) -> list[ToolCall] | None:
        cache_key = _cache_key(decision, history)
        cached = _PLAN_CACHE.get(cache_key)
        if cached and cached[0] > time.monotonic():
            return cached[1]

        local_plan = await minimind_router.route(
            message=decision.normalized_message,
            fallback_intent=decision.intent,
            params=decision.params,
        )
        if not local_plan:
            return None

        calls = [
            ToolCall(name=item["name"], params=item.get("params") or {})
            for item in local_plan.get("tools", [])
            if item.get("name") in TOOL_BY_NAME
            and item.get("name") not in BLOCKED_LOCAL_MODEL_TOOLS
        ]
        if not calls:
            return None
        if len(_PLAN_CACHE) >= _PLAN_CACHE_MAX_ENTRIES:
            _PLAN_CACHE.clear()
        _PLAN_CACHE[cache_key] = (time.monotonic() + _PLAN_CACHE_SECONDS, calls)
        return calls
