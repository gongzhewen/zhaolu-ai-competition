from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from app.core.config import settings
from app.core.database import get_db
from app.models.system import User
from app.modules.agent.schemas import ChatRequest
from app.modules.agent.service import AgentService
from app.modules.agent_intelligence.feedback_learning import process_feedback_learning
from app.modules.ai_gateway.insights import generate_insights
from app.modules.auth.dependencies import require_permission
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

_LOGGER = logging.getLogger(__name__)

router = APIRouter()


class FeedbackRequest(BaseModel):
    message_id: int
    rating: int = Field(ge=1, le=5)
    question: str = Field(default="", max_length=2000)
    answer: str = Field(default="", max_length=12000)
    reason: str | None = Field(default=None, max_length=1000)
    conversation_id: int | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)


@router.get("/health")
async def ai_health() -> dict[str, Any]:
    return {"status": "ok", "provider": "agent_core_v2"}


@router.post("/chat")
async def ai_chat(
    payload: ChatRequest,
    user: User = Depends(require_permission("ai:chat")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        return await asyncio.wait_for(
            AgentService(db, user).chat(
                message=payload.message,
                conversation_id=payload.conversation_id,
                context=payload.context,
            ),
            timeout=settings.agent_chat_timeout_seconds,
        )
    except asyncio.TimeoutError as exc:  # noqa: UP041
        raise HTTPException(status_code=504, detail="AI 回答超时，请稍后重试") from exc

@router.post("/chat/stream")
async def ai_chat_stream(
    payload: ChatRequest,
    user: User = Depends(require_permission("ai:chat")),
    db: AsyncSession = Depends(get_db),
):
    async def event_stream():
        started = time.monotonic()
        yield 'event: heartbeat\ndata: {"elapsed_ms":0}\n\n'
        task = asyncio.create_task(
            AgentService(db, user).chat(
                message=payload.message,
                conversation_id=payload.conversation_id,
                context=payload.context,
            )
        )
        try:
            while True:
                elapsed = time.monotonic() - started
                remaining = settings.agent_chat_timeout_seconds - elapsed
                if remaining <= 0:
                    task.cancel()
                    elapsed_ms = int(elapsed * 1000)
                    yield (
                        "event: error\ndata: "
                        + json.dumps(
                            {"message": "AI 回答超时，请稍后重试", "elapsed_ms": elapsed_ms},
                            ensure_ascii=False,
                        )
                        + "\n\n"
                    )
                    return
                wait_seconds = min(settings.agent_stream_heartbeat_seconds, remaining)
                try:
                    result = await asyncio.wait_for(asyncio.shield(task), timeout=wait_seconds)
                    break
                except asyncio.TimeoutError:  # noqa: UP041
                    elapsed_ms = int((time.monotonic() - started) * 1000)
                    yield (
                        "event: heartbeat\ndata: "
                        + json.dumps({"elapsed_ms": elapsed_ms}, ensure_ascii=False)
                        + "\n\n"
                    )
            yield "event: answer\ndata: " + json.dumps(result, ensure_ascii=False, default=str) + "\n\n"
        except Exception:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            yield (
                "event: error\ndata: "
                + json.dumps(
                    {"message": "AI 回答失败，请稍后重试", "elapsed_ms": elapsed_ms},
                    ensure_ascii=False,
                )
                + "\n\n"
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )

@router.post("/feedback")
async def ai_feedback(
    payload: FeedbackRequest,
    user: User = Depends(require_permission("ai:chat")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await process_feedback_learning(
        db,
        user=user,
        evaluation_id=payload.message_id,
        rating=payload.rating,
        question=payload.question,
        answer=payload.answer,
        reason=payload.reason,
        conversation_id=payload.conversation_id,
        history=payload.history,
    )


@router.get("/insights")
async def ai_insights(
    scope: str = Query(default="all", pattern="^(all|admissions|candidate|subject|major|medical)$"),
    year: int | None = Query(default=None, ge=2000, le=2100),
    _user: User = Depends(require_permission("ai:chat")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await generate_insights(db, scope=scope, year=year)
