from __future__ import annotations

import hashlib
import re
from typing import Any

from .knowledge import text_tokens


def memory_key(summary: str, memory_type: str) -> str:
    digest = hashlib.sha1(f"{memory_type}|{summary}".encode()).hexdigest()[:20]
    return f"{memory_type}:{digest}"


def rank_memories(
    query: str,
    items: list[dict[str, Any]],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    query_tokens = text_tokens(query)
    scored: list[dict[str, Any]] = []
    for item in items:
        summary = str(item.get("summary") or "")
        overlap = len(query_tokens & text_tokens(summary))
        score = overlap + float(item.get("importance") or 0.0) * 3 + float(item.get("confidence") or 0.0)
        if item.get("memory_type") == "preference":
            score += 1.0
        elif item.get("memory_type") == "reflection_summary":
            score += 2.0
        elif item.get("memory_type") == "reflection":
            score = (
                overlap * 2
                + float(item.get("importance") or 0.0)
                + float(item.get("confidence") or 0.0)
                if overlap
                else 0.0
            )
        if score <= 1.0:
            continue
        scored.append({**item, "score": round(score, 3)})
    scored.sort(
        key=lambda item: (
            -float(item["score"]),
            -int(item.get("hit_count") or 0),
        )
    )
    return scored[:limit]


def extract_explicit_preference(question: str) -> str | None:
    patterns = (
        r"(?:请)?记住[：:，,\s]*(.+)",
        r"以后(?:都|默认|优先)?[：:，,\s]*(.+)",
        r"我(?:更|优先)关注(.+)",
        r"我们学校(.+)",
    )
    for pattern in patterns:
        match = re.search(pattern, question)
        if not match:
            continue
        summary = match.group(1).strip("。；; ")
        if summary:
            return summary
    return None


def build_turn_memory_payloads(
    *,
    user_id: int | None,
    school_id: int | None,
    conversation_id: int | None,
    question: str,
    intent: str,
    answer: str,
) -> list[dict[str, Any]]:
    if user_id is None or conversation_id is None:
        return []
    episodic_summary = f"最近问题：{question[:120]}；意图：{intent}；回答摘要：{answer[:180]}"
    payloads = [
        {
            "user_id": user_id,
            "school_id": school_id,
            "conversation_id": conversation_id,
            "memory_type": "episodic",
            "memory_key": f"conversation:{conversation_id}",
            "memory_value": {"question": question, "intent": intent, "answer": answer[:500]},
            "summary": episodic_summary,
            "confidence": 0.75,
            "importance": 0.45,
        }
    ]
    preference = extract_explicit_preference(question)
    if preference:
        payloads.append(
            {
                "user_id": user_id,
                "school_id": school_id,
                "conversation_id": conversation_id,
                "memory_type": "preference",
                "summary": f"用户偏好：{preference}",
                "memory_value": {"source_question": question, "preference": preference},
                "confidence": 0.9,
                "importance": 0.8,
            }
        )
    return payloads


def format_memories(memories: list[dict[str, Any]]) -> str:
    if not memories:
        return "暂无相关长期记忆"
    return "\n".join(f"- [{item['memory_type']}] {item['summary']}" for item in memories)
