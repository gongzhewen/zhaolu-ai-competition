from __future__ import annotations

import time
from typing import Any

from agent_core.context import normalize_history, resolve_follow_up_question
from agent_core.contracts import AgentContext
from agent_core.runtime import AgentRuntime
from app.core.config import settings
from app.core.database import agent_data_session
from app.core.permissions import is_super_admin
from app.core.runtime_metrics import record_chat_metric
from app.core.text import text
from app.models.system import User
from app.modules.agent.hybrid_adapter import build_hybrid_tool_executor
from app.modules.agent.ml_router import build_ml_router
from app.modules.agent.providers import (
    CompositePlanner,
    SQLAlchemyKnowledgeProvider,
    SQLAlchemyMemoryProvider,
)
from app.modules.agent_intelligence.optimizer import (
    record_response_evaluation,
    select_prompt_template,
    task_type_for_intent,
)
from app.modules.agent_intelligence.school_context import resolve_school_context
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession


class AgentService:
    def __init__(self, db: AsyncSession, user: User) -> None:
        self.db = db
        self.user = user

    async def chat(
        self,
        *,
        message: str,
        conversation_id: int | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        raw_context = context or {}
        history = normalize_history(raw_context.get("history"))
        contextual_message, context_resolution = resolve_follow_up_question(
            message,
            history,
        )
        raw_context = {**raw_context, "history": history}
        can_lookup_students = is_super_admin(self.user)
        raw_context = {**raw_context, "can_lookup_students": can_lookup_students}
        school = await resolve_school_context(
            self.db,
            user_id=self.user.id,
            context=raw_context,
            allow_fallback=can_lookup_students,
        )
        if not school or school.get("school_id") is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="当前账号未绑定学校范围",
            )
        agent_context = AgentContext(
            school_code=school.get("school_code"),
            school_id=school.get("school_id"),
            user_id=self.user.id,
            conversation_id=conversation_id,
            year=raw_context.get("year"),
            province=raw_context.get("province"),
            major=raw_context.get("major"),
            values=raw_context,
        )
        try:
            async with agent_data_session(self.db, agent_context.school_id) as data_db:
                known_provinces = tuple(
                    (
                        await data_db.execute(
                            text("SELECT province_name FROM dim.province ORDER BY id")
                        )
                    ).scalars().all()
                )
                known_majors = tuple(
                    (
                        await data_db.execute(
                            text(
                                "SELECT major_name FROM dim.major "
                                "WHERE is_active IS TRUE ORDER BY id"
                            )
                        )
                    ).scalars().all()
                )
                latest_year = await data_db.scalar(text("SELECT MAX(year_no) FROM dim.year"))
                runtime = AgentRuntime(
                    tool_executor=build_hybrid_tool_executor(data_db, user=self.user),
                    router=build_ml_router(),
                    llm_planner=CompositePlanner(data_db),
                    knowledge_provider=SQLAlchemyKnowledgeProvider(data_db),
                    memory_provider=SQLAlchemyMemoryProvider(data_db),
                    multi_planning_enabled=settings.agent_multi_planning_enabled,
                    llm_planner_timeout_seconds=settings.agent_llm_planner_timeout_seconds,
                    risk_threshold=settings.agent_risk_threshold,
                    privacy_min_cohort_size=settings.agent_privacy_min_cohort_size,
                    permission_scope="super_admin" if can_lookup_students else "school_scope",
                    plan_consistency_threshold=settings.agent_plan_consistency_threshold,
                    unsupported_answer_alpha=settings.agent_unsupported_answer_alpha,
                    p95_latency_budget_ms=settings.agent_p95_latency_budget_ms,
                )
                result = await runtime.chat(
                    contextual_message,
                    context=agent_context,
                    known_provinces=known_provinces,
                    known_majors=known_majors,
                    latest_year=int(latest_year) if latest_year is not None else None,
                    history=history,
                )
        except Exception:
            await record_chat_metric(
                duration_ms=(time.perf_counter() - started) * 1000,
                route_mode="error",
                cache_layers=["miss"],
                tool_count=0,
                strategy="error",
            )
            raise

        tool_results = result.get("tool_results", [])
        cache_layers = [
            str(item.get("_cache_layer"))
            for item in tool_results
            if item.get("_cache_layer") in {"l1", "l2", "miss"}
        ]
        plan_summary = str(result.get("plan_summary") or "")
        route_mode = "model" if "本地模型" in plan_summary else "fast"
        plan_consistency = result.get("plan_consistency") or {}
        await record_chat_metric(
            duration_ms=(time.perf_counter() - started) * 1000,
            route_mode=route_mode,
            cache_layers=cache_layers,
            tool_count=len(tool_results),
            multi_planning_triggered=bool(plan_consistency.get("triggered")),
            strategy=str((result.get("risk_decision") or {}).get("strategy") or "unknown"),
        )
        for item in tool_results:
            item.pop("_cache_layer", None)

        task_type = task_type_for_intent(result["intent"])
        template = await select_prompt_template(
            self.db,
            task_type=task_type,
            school_id=agent_context.school_id,
        )
        message_id = await record_response_evaluation(
            self.db,
            message_id=None,
            school_id=agent_context.school_id,
            intent=result["intent"],
            template_id=template["id"] if template else None,
            tool_names=[item["name"] for item in result.get("tool_calls", [])],
            evaluation=result["self_check"],
        )
        result["message_id"] = message_id
        result["charts"] = [
            chart
            for item in tool_results
            for chart in (item.get("charts") or [])
        ]
        result["table"] = next(
            (item.get("table") for item in tool_results if item.get("table")),
            None,
        )
        result["reasoning_trace"] = [
            f"路由识别：{result['intent']}",
            *(
                ["上下文续问：已沿用上一轮问题条件"]
                if context_resolution.get("used")
                else []
            ),
            f"工具规划：{result.get('plan_summary') or '规则工具路由'}",
            f"执行工具：{', '.join(item['name'] for item in result.get('tool_calls', [])) or '无'}",
            f"数据支撑：{result.get('data_support', {}).get('status', 'unknown')}",
            *(
                [
                    (
                        "反思修正："
                        "应用 "
                        f"{len((result.get('reflection_guidance') or {}).get('rules') or [])} "
                        "条历史检查规则"
                    )
                ]
                if (result.get("reflection_guidance") or {}).get("active")
                else []
            ),
        ]
        result["memory_used"] = [
            {"summary": item.get("summary"), "memory_type": item.get("memory_type")}
            for item in result.get("memories", [])
        ]
        result["knowledge_sources"] = [
            {
                "title": item.get("title"),
                "content": item.get("content"),
                "score": item.get("score"),
            }
            for item in result.get("knowledge_items", [])
        ]
        result["school_context"] = {
            "school_id": agent_context.school_id,
            "school_code": agent_context.school_code,
        }
        result["original_question"] = message
        result["contextual_question"] = contextual_message
        result["context_resolution"] = context_resolution
        result["prompt_template"] = {
            "task_type": task_type,
            "template_code": template.get("template_code") if template else None,
        }
        return result




