from __future__ import annotations

from typing import Any, Protocol

from .contracts import AgentContext, RouteDecision, ToolCall


class ToolExecutor(Protocol):
    async def __call__(self, call: ToolCall, context: AgentContext) -> dict[str, Any]:
        ...


class KnowledgeProvider(Protocol):
    async def search(self, query: str, *, school_id: int | None, limit: int = 4) -> list[dict[str, Any]]:
        ...


class MemoryProvider(Protocol):
    async def load(self, query: str, *, user_id: int, school_id: int | None, limit: int = 5) -> list[dict[str, Any]]:
        ...

    async def remember(self, payload: dict[str, Any]) -> None:
        ...


class LLMPlanner(Protocol):
    async def plan(self, decision: RouteDecision, *, history: list[dict[str, str]]) -> list[ToolCall] | None:
        ...


class AnswerComposer(Protocol):
    async def compose(
        self,
        decision: RouteDecision,
        *,
        answer: str,
        tool_results: list[dict[str, Any]],
        knowledge_items: list[dict[str, Any]],
        memories: list[dict[str, Any]],
    ) -> str:
        ...


class CacheProvider(Protocol):
    async def get(self, key: str) -> dict[str, Any] | None:
        ...

    async def set(self, key: str, value: dict[str, Any], *, ttl_seconds: int) -> None:
        ...

    async def invalidate(self, namespace: str) -> None:
        ...
