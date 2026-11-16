from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agent_core.contracts import AgentContext, ToolCall
from app.core.permissions import is_super_admin
from app.modules.ai_gateway.legacy_agent import TOOL_EXECUTORS


class LegacyToolAdapter:
    def __init__(self, db: AsyncSession, *, user: Any) -> None:
        self.db = db
        self.user = user

    async def __call__(self, call: ToolCall, context: AgentContext) -> dict[str, Any]:
        executor = TOOL_EXECUTORS.get(call.name)
        if executor is None:
            return {
                "answer": f"未注册工具：{call.name}",
                "charts": [],
                "table": None,
                "data_sources": [],
                "metrics": {},
                "error": "unknown_tool",
            }
        params = {
            **call.params,
            "school_id": context.school_id,
            "user": self.user,
            "can_lookup_students": bool(self.user and is_super_admin(self.user)),
        }
        if call.name == "policy_faq" and not params.get("query"):
            params["query"] = call.params.get("message") or ""
        return await executor(self.db, params)


def build_legacy_tool_executor(db: AsyncSession, *, user: Any) -> LegacyToolAdapter:
    return LegacyToolAdapter(db, user=user)

