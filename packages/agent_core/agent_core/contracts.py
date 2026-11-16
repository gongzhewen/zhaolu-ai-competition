from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Confidence = Literal["high", "normal", "medium", "low"]


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    params: tuple[str, ...] = ()


@dataclass(slots=True)
class ToolCall:
    name: str
    params: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None


@dataclass(slots=True)
class RouteDecision:
    intent: str
    normalized_message: str
    params: dict[str, Any] = field(default_factory=dict)
    requires_llm_plan: bool = False
    confidence: Confidence = "normal"
    reasons: list[str] = field(default_factory=list)
    clarification: str | None = None


@dataclass(slots=True)
class AgentContext:
    school_code: str | None = None
    school_id: int | None = None
    user_id: int | None = None
    conversation_id: int | None = None
    year: int | None = None
    province: str | None = None
    major: str | None = None
    values: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SelfCheckResult:
    score: float
    loss: float
    action: str
    dimensions: dict[str, float]
    issues: list[str] = field(default_factory=list)
    answer_number_count: int = 0

SlotSource = Literal["rule", "onnx", "knowledge", "local_model", "context"]
RiskStrategy = Literal[
    "answer",
    "clarify",
    "no_data",
    "no_permission",
    "out_of_scope",
    "insufficient_data",
]


@dataclass(slots=True)
class SemanticSlots:
    intent: str
    metrics: tuple[str, ...] = ()
    year: int | None = None
    province: str | None = None
    major: str | None = None
    subject: str | None = None
    filters: dict[str, Any] = field(default_factory=dict)
    aggregation: str | None = None
    output_mode: str = "summary"
    missing_required: tuple[str, ...] = ()
    sources: tuple[SlotSource, ...] = ("rule",)


@dataclass(slots=True)
class SlotAmbiguity:
    score: float
    candidates: dict[str, tuple[Any, ...]] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    clarification: str | None = None
    slot_entropy: dict[str, float] = field(default_factory=dict)
    semantic_uncertainty: float = 0.0

    @property
    def requires_clarification(self) -> bool:
        return self.score >= 0.65 or bool(self.clarification)


@dataclass(slots=True)
class EvidenceCertificate:
    tool_name: str
    data_source: tuple[str, ...]
    year_range: tuple[int | None, int | None]
    filters: dict[str, Any]
    canonical_major: str | None
    aggregation: str | None
    row_count: int | None
    result_value: dict[str, Any]
    missing_value_count: int
    permission_scope: str
    completeness: float


@dataclass(slots=True)
class PlanCandidate:
    name: str
    tool_calls: list[ToolCall]
    source: SlotSource


@dataclass(slots=True)
class PlanConsistency:
    triggered: bool
    primary: str
    secondary: str | None
    consistent: bool
    score: float
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RiskFeatures:
    ambiguity: float = 0.0
    required_slot_gap: float = 0.0
    alias_risk: float = 0.0
    confidence_gap: float = 0.0
    evidence_gap: float = 0.0
    numeric_gap: float = 0.0
    plan_consistency_gap: float = 0.0
    permission_risk: float = 0.0
    privacy_risk: float = 0.0
    missing_data_risk: float = 0.0
    data_support_gap: float = 0.0


@dataclass(slots=True)
class RiskDecision:
    score: float
    strategy: RiskStrategy
    threshold: float
    reasons: list[str] = field(default_factory=list)
    response: str | None = None
    features: RiskFeatures = field(default_factory=RiskFeatures)
    answer_conditions: dict[str, bool] = field(default_factory=dict)
