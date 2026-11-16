from __future__ import annotations

import json
from typing import Any

from agent_core.registry import TOOL_BY_NAME
from app.core.config import settings
from app.core.database import get_db
from app.core.redis_cache import redis_health
from app.core.runtime_metrics import metrics_snapshot
from app.models.system import User
from app.modules.agent.schemas import ChatRequest, ChatResponse
from app.modules.agent.service import AgentService
from app.modules.agent.tools.registry import NATIVE_TOOL_EXECUTORS
from app.modules.auth.dependencies import require_permission
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("/capabilities")
async def capabilities() -> dict[str, Any]:
    return {
        "runtime": "agent_core_v2",
        "algorithm_version": "ECSP-Admissions-G1.2",
        "tool_count": len(NATIVE_TOOL_EXECUTORS),
        "model_provider": "minimind_local" if settings.minimind_enabled else "rules",
        "model_configured": bool(settings.minimind_enabled and settings.minimind_base_url),
        "tools": [
            {
                "name": name,
                "description": TOOL_BY_NAME[name].description,
                "params": list(TOOL_BY_NAME[name].params),
            }
            for name in NATIVE_TOOL_EXECUTORS
        ],
        "supported_targets": ["web", "desktop", "mobile"],
        "supported_modes": [
            "online_gateway",
            "desktop_sidecar",
            "mobile_gateway",
            "local_model_fallback",
        ],
        "multi_school": {
            "school_context": True,
            "independent_data_plane": bool(settings.school_database_url_map),
            "strict_data_plane_routing": bool(settings.school_database_url_map),
            "dbf_profile": True,
            "knowledge_scope": True,
            "deployment_mode": settings.deployment_mode,
            "instance_id": settings.instance_id,
            "cache_namespace": settings.redis_key_prefix,
        },
        "reasoning": {
            "data_first": True,
            "mandatory_self_check": True,
            "knowledge_retrieval": True,
            "ml_intent_router": settings.router_ml_enabled,
            "long_term_memory": True,
            "feedback_optimization": True,
            "self_learning_reflection": True,
            "context_history_turns": 6,
            "reflection_compression_threshold": settings.agent_reflection_compression_threshold,
        },
        "performance": {
            "fast_mode": settings.agent_fast_mode,
            "polish_enabled": False,
            "planner_timeout_seconds": settings.minimind_timeout_seconds,
            "tool_cache_ttl_seconds": settings.agent_cache_ttl_seconds,
            "min_data_support": settings.agent_min_data_support,
            "rag_vector_enabled": settings.rag_vector_enabled,
            "rag_embedding_model": settings.rag_embedding_model,
            "rag_vector_weight": settings.rag_vector_weight,
            "router_ml_confidence_threshold": settings.router_ml_confidence_threshold,
            "risk_threshold": settings.agent_risk_threshold,
            "multi_planning_enabled": settings.agent_multi_planning_enabled,
            "database_pool_size": settings.database_pool_size,
            "database_max_overflow": settings.database_max_overflow,
            "database_max_connections": settings.database_pool_size + settings.database_max_overflow,
            "plan_consistency_threshold": settings.agent_plan_consistency_threshold,
            "unsupported_answer_alpha": settings.agent_unsupported_answer_alpha,
            "p95_latency_budget_ms": settings.agent_p95_latency_budget_ms,
            "model_stable_version": settings.minimind_stable_version,
            "model_canary_version": settings.minimind_canary_version,
            "model_canary_percent": settings.minimind_canary_percent,
        },
        "observability": {
            "metrics_endpoint": "/api/v1/agent/metrics",
            "window_size": settings.runtime_metrics_window_size,
            "tracks": [
                "p50_p95_p99",
                "cache_hit_rate",
                "dual_planning_trigger_rate",
                "llm_timeout_rate",
                "answer_clarification_refusal_rates",
            ],
        },
    }


@router.get("/metrics")
async def runtime_metrics(
    _user: User = Depends(require_permission("ai:chat")),
) -> dict[str, Any]:
    return {
        "metrics": await metrics_snapshot(),
        "redis": await redis_health(),
    }


@router.post("/chat", response_model=ChatResponse)
async def agent_chat(
    payload: ChatRequest,
    user: User = Depends(require_permission("ai:chat")),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    service = AgentService(db, user)
    result = await service.chat(
        message=payload.message,
        conversation_id=payload.conversation_id,
        context=payload.context,
    )
    return ChatResponse(**result)


@router.post("/chat/stream")
async def agent_chat_stream(
    payload: ChatRequest,
    user: User = Depends(require_permission("ai:chat")),
    db: AsyncSession = Depends(get_db),
):
    async def event_stream():
        yield "event: status\ndata: {\"stage\":\"routing\"}\n\n"
        result = await AgentService(db, user).chat(
            message=payload.message,
            conversation_id=payload.conversation_id,
            context=payload.context,
        )
        yield "event: final\ndata: " + json.dumps(result, ensure_ascii=False, default=str) + "\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/insights")
async def agent_insights(
    scope: str = Query(default="all", pattern="^(all|admissions|candidate|subject|major|medical)$"),
    year: int | None = Query(default=None, ge=2000, le=2100),
    _user: User = Depends(require_permission("ai:chat")),
) -> dict[str, Any]:
    return {
        "status": "not_migrated",
        "scope": scope,
        "year": year,
        "message": "洞察模块将在下一阶段接入 V2。",
    }
