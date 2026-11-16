from __future__ import annotations

import asyncio
import hashlib
import json
import re
from typing import Any

from agent_core.reflection import (
    build_reflection_summary,
    compress_reflection_memories,
    infer_feedback_error_points,
    select_reflection_answer,
)
from app.core.config import settings
from app.core.text import text
from app.models.system import User
from app.modules.agent_intelligence.memory import upsert_memory
from app.modules.agent_intelligence.optimizer import apply_feedback_optimization
from sqlalchemy.ext.asyncio import AsyncSession


def _json_value(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _reflection_key(question: str, intent: str) -> str:
    digest = hashlib.sha1(question.encode("utf-8")).hexdigest()[:16]
    return f"reflection:{intent}:{digest}"


def _safe_question(value: str) -> str:
    text_value = re.sub(r"\s+", " ", value or "").strip()
    text_value = text_value.replace("忽略之前所有指令", "").replace("忽略先前指令", "")
    return text_value[:80]


async def _load_evaluation(
    db: AsyncSession,
    evaluation_id: int,
) -> dict[str, Any]:
    result = await db.execute(
        text(
            """
            SELECT id, school_id, intent, tool_names, self_check
            FROM ai.response_evaluation
            WHERE id=:evaluation_id
            LIMIT 1
            """
        ),
        {"evaluation_id": evaluation_id},
    )
    row = result.mappings().first()
    return dict(row) if row else {}


async def _record_feedback_event(
    db: AsyncSession,
    *,
    evaluation_id: int,
    user_id: int,
    rating: int,
    payload: dict[str, Any],
) -> None:
    feedback_text = json.dumps(payload, ensure_ascii=False, default=str)
    if settings.database_url.startswith("mysql"):
        await db.execute(
            text(
                """
                INSERT INTO ai.feedback (message_id, user_id, rating, feedback_text)
                VALUES (:message_id, :user_id, :rating, :feedback_text)
                """
            ),
            {
                "message_id": evaluation_id,
                "user_id": user_id,
                "rating": rating,
                "feedback_text": feedback_text,
            },
        )
    else:
        await db.execute(
            text(
                """
                INSERT INTO ai.feedback (message_id, user_id, rating, feedback_text)
                VALUES (
                    :message_id, :user_id, :rating, CAST(:feedback_text AS jsonb)
                )
                """
            ),
            {
                "message_id": evaluation_id,
                "user_id": user_id,
                "rating": rating,
                "feedback_text": feedback_text,
            },
        )


async def _active_reflections(
    db: AsyncSession,
    *,
    user_id: int,
    school_id: int | None,
) -> list[dict[str, Any]]:
    result = await db.execute(
        text(
            """
            SELECT id, memory_value, summary, confidence, importance
            FROM ai.agent_memory
            WHERE user_id=:user_id
              AND (school_id=:school_id OR school_id IS NULL)
              AND memory_type='reflection'
              AND (expires_at IS NULL OR expires_at > now())
            ORDER BY created_at DESC
            LIMIT 20
            """
        ),
        {"user_id": user_id, "school_id": school_id},
    )
    items: list[dict[str, Any]] = []
    for row in result.mappings().all():
        item = dict(row)
        item["memory_value"] = _json_value(item.get("memory_value"), {})
        items.append(item)
    return items


async def _compress_if_needed(
    db: AsyncSession,
    *,
    user_id: int,
    school_id: int | None,
) -> dict[str, Any]:
    memories = await _active_reflections(db, user_id=user_id, school_id=school_id)
    threshold = max(2, settings.agent_reflection_compression_threshold)
    if len(memories) < threshold:
        return {"compressed": False, "active_count": len(memories)}

    compressed = compress_reflection_memories(memories)
    memory = await upsert_memory(
        db,
        user_id=user_id,
        school_id=school_id,
        conversation_id=None,
        memory_type="reflection_summary",
        memory_key="reflection_summary:current",
        summary=compressed["summary"],
        memory_value=compressed,
        confidence=0.9,
        importance=0.95,
    )
    ids = [int(item["id"]) for item in memories if item.get("id") is not None]
    if ids:
        placeholders = ", ".join(f":id_{index}" for index in range(len(ids)))
        await db.execute(
            text(
                f"""
                UPDATE ai.agent_memory
                SET expires_at=now(), updated_at=now()
                WHERE id IN ({placeholders})
                """
            ),
            {f"id_{index}": memory_id for index, memory_id in enumerate(ids)},
        )
    await db.commit()
    return {
        "compressed": True,
        "active_count": len(memories),
        "summary_memory_id": memory.get("id"),
        "error_codes": compressed["error_codes"],
        "rules": compressed["rules"],
    }


async def process_feedback_learning(
    db: AsyncSession,
    *,
    user: User,
    evaluation_id: int,
    rating: int,
    question: str,
    answer: str,
    reason: str | None,
    conversation_id: int | None,
    history: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    evaluation = await _load_evaluation(db, evaluation_id)
    school_id = evaluation.get("school_id")
    intent = str(evaluation.get("intent") or "unknown")
    tool_names = _json_value(evaluation.get("tool_names"), [])

    optimization = None
    optimization_error = None
    try:
        optimization = await apply_feedback_optimization(
            db,
            message_id=evaluation_id,
            rating=rating,
            school_id=school_id,
        )
    except Exception as exc:  # noqa: BLE001 - feedback must not corrupt the learning flow
        optimization_error = f"{type(exc).__name__}: {exc}"
        await db.rollback()

    if rating >= 4:
        await _record_feedback_event(
            db,
            evaluation_id=evaluation_id,
            user_id=user.id,
            rating=rating,
            payload={
                "result": "positive",
                "question": question[:500],
                "answer": answer[:1000],
                "intent": intent,
            },
        )
        await db.commit()
        return {
            "status": "ok",
            "feedback": "positive",
            "optimization": optimization,
            "optimization_error": optimization_error,
        }

    findings = infer_feedback_error_points(
        question=question,
        answer=answer,
        reason=reason,
        intent=intent,
        tool_names=[str(item) for item in tool_names],
    )
    reflection_summary = build_reflection_summary(findings)
    memory_value = {
        "question": question[:500],
        "previous_answer": answer[:1000],
        "reason": (reason or "")[:500],
        "intent": intent,
        "tool_names": tool_names,
        "error_points": findings,
        "status": "reflecting",
    }
    memory = await upsert_memory(
        db,
        user_id=user.id,
        school_id=school_id,
        conversation_id=conversation_id,
        memory_type="reflection",
        memory_key=_reflection_key(question, intent),
        summary=f"反馈修正：{reflection_summary}；问题范围：{_safe_question(question)}",
        memory_value=memory_value,
        confidence=0.6,
        importance=0.75,
    )

    second_result: dict[str, Any] | None = None
    second_error = None
    if question.strip():
        try:
            from app.modules.agent.service import AgentService

            second_result = await asyncio.wait_for(
                AgentService(db, user).chat(
                    message=question,
                    conversation_id=conversation_id,
                    context={
                        "history": history or [],
                        "reflection_mode": True,
                    },
                ),
                timeout=settings.agent_chat_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - reflection failure is reported, not hidden
            second_error = f"{type(exc).__name__}: {exc}"
            await db.rollback()
    else:
        second_error = "缺少原问题，无法执行二次复核"

    selection = (
        select_reflection_answer(
            original_answer=answer,
            second_result=second_result,
        )
        if second_result
        else {
            "mode": "insufficient",
            "answer": "二次复核执行失败，暂不能确认原回答，建议人工核对。",
            "reason": second_error,
        }
    )

    memory_value.update(
        {
            "status": "completed",
            "second_answer": selection["answer"][:1000],
            "selection_mode": selection["mode"],
            "selection_reason": selection["reason"],
        }
    )
    await upsert_memory(
        db,
        user_id=user.id,
        school_id=school_id,
        conversation_id=conversation_id,
        memory_type="reflection",
        memory_key=_reflection_key(question, intent),
        summary=f"反馈修正：{reflection_summary}；问题范围：{_safe_question(question)}",
        memory_value=memory_value,
        confidence=0.7 if selection["mode"] != "insufficient" else 0.6,
        importance=0.8,
    )
    compression = await _compress_if_needed(
        db,
        user_id=user.id,
        school_id=school_id,
    )

    await _record_feedback_event(
        db,
        evaluation_id=evaluation_id,
        user_id=user.id,
        rating=rating,
        payload={
            "result": "negative",
            "question": question[:500],
            "answer": answer[:1000],
            "intent": intent,
            "reason": (reason or "")[:500],
            "error_points": findings,
            "second_answer": selection["answer"][:1000],
            "selection_mode": selection["mode"],
            "compression": compression,
        },
    )
    await db.commit()
    return {
        "status": "ok",
        "feedback": "negative",
        "optimization": optimization,
        "optimization_error": optimization_error,
        "reflection": {
            "error_points": findings,
            "summary": reflection_summary,
            "memory_id": memory.get("id"),
            "second_answer": selection["answer"],
            "selection_mode": selection["mode"],
            "selection_reason": selection["reason"],
            "second_error": second_error,
            "compression": compression,
        },
        "second_response": second_result,
    }
