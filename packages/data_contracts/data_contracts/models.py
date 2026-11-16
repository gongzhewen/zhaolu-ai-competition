from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ToolCall:
    name: str
    params: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None


@dataclass(slots=True)
class ToolResult:
    tool: str
    answer: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    table: dict[str, Any] = field(default_factory=dict)
    charts: list[dict[str, Any]] = field(default_factory=list)
    data_sources: list[dict[str, Any]] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    duration_ms: float | None = None
    cache_hit: bool = False


@dataclass(slots=True)
class AgentChatRequest:
    message: str
    conversation_id: int | None = None
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentChatResponse:
    conversation_id: int | None
    intent: str
    answer: str
    confidence: str = "normal"
    need_human: bool = False
    data_sources: list[dict[str, Any]] = field(default_factory=list)
    charts: list[dict[str, Any]] = field(default_factory=list)
    table: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    plan_summary: str = ""
    self_check: dict[str, Any] = field(default_factory=dict)
    reasoning_trace: list[str] = field(default_factory=list)
