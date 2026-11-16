from __future__ import annotations

import re
from typing import Any

_FOLLOW_UP_MARKERS = (
    "他", "她", "该生", "该同学", "这个学生", "这名学生",
    "该专业", "这个专业", "上述专业", "该省", "这个省", "上述省份",
    "刚才", "上面", "前述", "其中", "分别", "同比", "那",
)


def normalize_history(history: list[dict[str, Any]] | None, limit: int = 6) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in (history or [])[-max(1, limit):]:
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        normalized.append({"role": role, "content": content[:800]})
    return normalized


def resolve_follow_up_question(
    question: str,
    history: list[dict[str, Any]] | None,
) -> tuple[str, dict[str, Any]]:
    normalized = normalize_history(history)
    compact = re.sub(r"\s+", "", question)
    if not normalized or not any(marker in compact for marker in _FOLLOW_UP_MARKERS):
        return question, {"used": False, "reason": None}

    previous_user = next(
        (item["content"] for item in reversed(normalized) if item["role"] == "user"),
        None,
    )
    if not previous_user or previous_user == question:
        return question, {"used": False, "reason": None}

    resolved = f"{previous_user}\n继续追问：{question}"
    return resolved, {
        "used": True,
        "reason": "检测到指代或省略表达，已拼接最近一轮用户问题",
        "previous_question": previous_user[:300],
    }
