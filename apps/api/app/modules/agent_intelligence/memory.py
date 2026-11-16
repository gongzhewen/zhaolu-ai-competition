from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from app.core.db_compat import execute_returning_row
from app.core.text import text
from sqlalchemy.ext.asyncio import AsyncSession


def _tokens(value: str) -> set[str]:
    normalized = re.sub(r"\s+", "", value.lower())
    return {
        normalized[index:index + size]
        for size in (2, 3, 4)
        for index in range(max(0, len(normalized) - size + 1))
    }


def _memory_key(summary: str, memory_type: str) -> str:
    digest = hashlib.sha1(f"{memory_type}|{summary}".encode()).hexdigest()[:20]
    return f"{memory_type}:{digest}"


async def load_relevant_memories(
    db: AsyncSession,
    *,
    user_id: int | None,
    school_id: int | None,
    query: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    if user_id is None:
        return []
    result = await db.execute(
        text("""
            SELECT id, memory_type, memory_key, memory_value, summary,
                   confidence, importance, hit_count
            FROM ai.agent_memory
            WHERE user_id=:user_id
              AND (school_id=:school_id OR school_id IS NULL)
              AND (expires_at IS NULL OR expires_at > now())
            ORDER BY importance DESC, updated_at DESC
            LIMIT 100
            """),
        {"user_id": user_id, "school_id": school_id},
    )
    query_tokens = _tokens(query)
    scored = []
    for row in result.mappings().all():
        item = dict(row)
        overlap = len(query_tokens & _tokens(item["summary"]))
        score = overlap + float(item["importance"]) * 3 + float(item["confidence"])
        if item["memory_type"] == "preference":
            score += 1.0
        elif item["memory_type"] == "reflection_summary":
            score += 2.0
        elif item["memory_type"] == "reflection":
            score = (
                overlap * 2
                + float(item["importance"])
                + float(item["confidence"])
                if overlap
                else 0.0
            )
        if score <= 1.0:
            continue
        scored.append({**item, "score": round(score, 3)})
    scored.sort(key=lambda item: (-item["score"], -item["hit_count"]))
    selected = scored[:limit]
    if selected:
        for item in selected:
            await db.execute(
                text("""
                    UPDATE ai.agent_memory
                    SET hit_count=hit_count+1, last_accessed_at=now(), updated_at=now()
                    WHERE id=:memory_id
                    """
                ),
                {"memory_id": item["id"]},
            )
        await db.commit()
    return selected


async def upsert_memory(
    db: AsyncSession,
    *,
    user_id: int | None,
    school_id: int | None,
    conversation_id: int | None,
    memory_type: str,
    summary: str,
    memory_value: dict[str, Any] | None = None,
    confidence: float = 0.8,
    importance: float = 0.5,
    memory_key: str | None = None,
) -> dict[str, Any]:
    if user_id is None or not summary.strip():
        return {}
    key = memory_key or _memory_key(summary, memory_type)
    memory = await execute_returning_row(
        db,
        """
        INSERT INTO ai.agent_memory (
            user_id, school_id, conversation_id, memory_type, memory_key,
            memory_value, summary, confidence, importance
        )
        VALUES (
            :user_id, :school_id, :conversation_id, :memory_type, :memory_key,
            CAST(:memory_value AS jsonb), :summary, :confidence, :importance
        )
        ON CONFLICT (user_id, school_id, memory_key)
        DO UPDATE SET
            conversation_id=EXCLUDED.conversation_id,
            memory_value=EXCLUDED.memory_value,
            summary=EXCLUDED.summary,
            confidence=GREATEST(ai.agent_memory.confidence, EXCLUDED.confidence),
            importance=GREATEST(ai.agent_memory.importance, EXCLUDED.importance),
            updated_at=now()
        RETURNING id, memory_type, memory_key, memory_value, summary, confidence, importance
        """,
        {
            "user_id": user_id,
            "school_id": school_id,
            "conversation_id": conversation_id,
            "memory_type": memory_type,
            "memory_key": key,
            "memory_value": json.dumps(memory_value or {}, ensure_ascii=False),
            "summary": summary.strip(),
            "confidence": confidence,
            "importance": importance,
        },
        mysql_select="""
            SELECT id, memory_type, memory_key, memory_value, summary, confidence, importance
            FROM ai.agent_memory
            WHERE user_id=:user_id AND school_id <=> :school_id AND memory_key=:memory_key
            LIMIT 1
        """,
    )
    await db.commit()
    return memory or {}


async def remember_turn(
    db: AsyncSession,
    *,
    user_id: int | None,
    school_id: int | None,
    conversation_id: int,
    question: str,
    intent: str,
    answer: str,
) -> list[dict[str, Any]]:
    memories: list[dict[str, Any]] = []
    if user_id is None:
        return memories

    episodic_summary = f"最近问题：{question[:120]}；意图：{intent}；回答摘要：{answer[:180]}"
    memories.append(
        await upsert_memory(
            db,
            user_id=user_id,
            school_id=school_id,
            conversation_id=conversation_id,
            memory_type="episodic",
            memory_key=f"conversation:{conversation_id}",
            summary=episodic_summary,
            memory_value={"question": question, "intent": intent, "answer": answer[:500]},
            confidence=0.75,
            importance=0.45,
        )
    )

    explicit_patterns = (
        r"(?:请)?记住[：:，,\s]*(.+)",
        r"以后(?:都|默认|优先)?[：:，,\s]*(.+)",
        r"我(?:更|优先)关注(.+)",
        r"我们学校(.+)",
    )
    for pattern in explicit_patterns:
        match = re.search(pattern, question)
        if not match:
            continue
        summary = match.group(1).strip("。；; ")
        if not summary:
            continue
        value = {"source_question": question, "preference": summary}
        memories.append(
            await upsert_memory(
                db,
                user_id=user_id,
                school_id=school_id,
                conversation_id=conversation_id,
                memory_type="preference",
                summary=f"用户偏好：{summary}",
                memory_value=value,
                confidence=0.9,
                importance=0.8,
            )
        )
        break
    return [item for item in memories if item]


def format_memories(memories: list[dict[str, Any]]) -> str:
    if not memories:
        return "暂无相关长期记忆"
    return "\n".join(f"- [{item['memory_type']}] {item['summary']}" for item in memories)

