from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: int | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    conversation_id: int | None = None
    intent: str
    answer: str
    confidence: str = "normal"
    need_human: bool = False
    data_sources: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    plan_summary: str = ""
    self_check: dict[str, Any] = Field(default_factory=dict)
    data_support: dict[str, Any] = Field(default_factory=dict)
    semantic_slots: dict[str, Any] = Field(default_factory=dict)
    slot_ambiguity: dict[str, Any] = Field(default_factory=dict)
    evidence_certificates: list[dict[str, Any]] = Field(default_factory=list)
    numeric_verification: dict[str, Any] = Field(default_factory=dict)
    plan_consistency: dict[str, Any] = Field(default_factory=dict)
    risk_decision: dict[str, Any] = Field(default_factory=dict)
    verification_summary: dict[str, Any] = Field(default_factory=dict)
    clarification: str | None = None
    algorithm_version: str = ""
    memory_count: int = 0
    knowledge_count: int = 0
    message_id: int | None = None
    charts: list[dict[str, Any]] = Field(default_factory=list)
    table: dict[str, Any] | None = None
    reasoning_trace: list[str] = Field(default_factory=list)
    memory_used: list[dict[str, Any]] = Field(default_factory=list)
    knowledge_sources: list[dict[str, Any]] = Field(default_factory=list)
    school_context: dict[str, Any] = Field(default_factory=dict)
    prompt_template: dict[str, Any] = Field(default_factory=dict)
    original_question: str | None = None
    contextual_question: str | None = None
    context_resolution: dict[str, Any] = Field(default_factory=dict)
    reflection_guidance: dict[str, Any] = Field(default_factory=dict)
