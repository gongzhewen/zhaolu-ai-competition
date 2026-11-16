from __future__ import annotations

import re
from typing import Any


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value.lower())


def text_tokens(value: str) -> set[str]:
    normalized = normalize_text(value)
    tokens = set(re.findall(r"[a-z0-9]+", normalized))
    for size in (2, 3, 4):
        tokens.update(
            normalized[index:index + size]
            for index in range(max(0, len(normalized) - size + 1))
        )
    return tokens


def chunk_text(content: str, max_chars: int = 700) -> list[str]:
    parts = [part.strip() for part in re.split(r"\n{2,}", content) if part.strip()]
    result: list[str] = []
    current = ""
    for part in parts:
        if current and len(current) + len(part) > max_chars:
            result.append(current)
            current = part
        else:
            current = f"{current}\n\n{part}".strip()
    if current:
        result.append(current)
    return result or [content]


def score_knowledge_items(
    query: str,
    items: list[dict[str, Any]],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    query_tokens = text_tokens(query)
    scored: list[dict[str, Any]] = []
    for item in items:
        title = str(item.get("title") or "")
        content = str(item.get("content") or "")
        document_type = str(item.get("document_type") or "")
        content_tokens = text_tokens(f"{title} {content}")
        overlap = len(query_tokens & content_tokens)
        title_overlap = len(query_tokens & text_tokens(title))
        score = overlap + title_overlap * 2.0
        if document_type in {"policy_faq", "metric_definition", "agent_policy"}:
            score += 0.5
        if score <= 0:
            continue
        scored.append({**item, "score": round(score, 3)})
    scored.sort(
        key=lambda item: (
            -float(item["score"]),
            int(item.get("document_id") or 0),
            int(item.get("chunk_id") or 0),
        )
    )
    return scored[:limit]


def build_knowledge_chunks(
    *,
    title: str,
    content: str,
    document_type: str,
    document_id: int,
    metadata: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    metadata = metadata or {}
    return [
        {
            "document_id": document_id,
            "chunk_id": index,
            "title": title,
            "document_type": document_type,
            "content": chunk,
            "metadata": metadata,
        }
        for index, chunk in enumerate(chunk_text(content))
    ]
