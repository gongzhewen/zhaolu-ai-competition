from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


DEFAULT_SLOT_WEIGHTS: dict[str, float] = {
    "metric": 0.30,
    "year": 0.15,
    "major": 0.20,
    "student_identity": 0.20,
    "province": 0.10,
}


@dataclass(slots=True, frozen=True)
class SemanticUncertainty:
    raw_entropy: dict[str, float]
    normalized_entropy: dict[str, float]
    weighted_uncertainty: float


@dataclass(slots=True, frozen=True)
class AnswerConditions:
    constraints_complete: bool
    evidence_sufficient: bool
    result_consistent: bool
    permission_allowed: bool
    risk_below_threshold: bool

    @property
    def can_answer(self) -> bool:
        return all(
            (
                self.constraints_complete,
                self.evidence_sufficient,
                self.result_consistent,
                self.permission_allowed,
                self.risk_below_threshold,
            )
        )

    def as_dict(self) -> dict[str, bool]:
        return {
            "constraints_complete": self.constraints_complete,
            "evidence_sufficient": self.evidence_sufficient,
            "result_consistent": self.result_consistent,
            "permission_allowed": self.permission_allowed,
            "risk_below_threshold": self.risk_below_threshold,
            "can_answer": self.can_answer,
        }


def entropy(probabilities: Sequence[float]) -> float:
    values = [float(value) for value in probabilities if float(value) > 0]
    if not values:
        return 0.0
    total = sum(values)
    if total <= 0:
        return 0.0
    normalized = [value / total for value in values]
    return -sum(value * math.log(value) for value in normalized)


def normalized_entropy(probabilities: Sequence[float]) -> float:
    values = [float(value) for value in probabilities if float(value) > 0]
    if len(values) <= 1:
        return 0.0
    maximum = math.log(len(values))
    return min(1.0, entropy(values) / maximum) if maximum > 0 else 0.0


def candidate_probabilities(candidates: Any) -> dict[str, float]:
    if isinstance(candidates, Mapping):
        values = {
            str(key): float(value)
            for key, value in candidates.items()
            if float(value) > 0
        }
        total = sum(values.values())
        if total <= 0:
            return {}
        return {key: value / total for key, value in values.items()}
    if isinstance(candidates, Sequence) and not isinstance(candidates, (str, bytes)):
        values = list(candidates)
        if not values:
            return {}
        probability = 1.0 / len(values)
        return {str(value): probability for value in values}
    return {str(candidates): 1.0} if candidates is not None else {}


def estimate_semantic_uncertainty(
    candidates: Mapping[str, Any],
    *,
    slot_weights: Mapping[str, float] | None = None,
) -> SemanticUncertainty:
    weights = dict(DEFAULT_SLOT_WEIGHTS if slot_weights is None else slot_weights)
    raw: dict[str, float] = {}
    normalized: dict[str, float] = {}
    weighted = 0.0
    for slot, values in candidates.items():
        probabilities = candidate_probabilities(values)
        if not probabilities:
            continue
        slot_raw = entropy(list(probabilities.values()))
        slot_normalized = normalized_entropy(list(probabilities.values()))
        raw[slot] = round(slot_raw, 6)
        normalized[slot] = round(slot_normalized, 6)
        weighted += weights.get(slot, 0.05) * slot_normalized
    return SemanticUncertainty(
        raw_entropy=raw,
        normalized_entropy=normalized,
        weighted_uncertainty=round(min(1.0, weighted), 6),
    )


def evaluate_answer_conditions(
    *,
    constraints_complete: bool,
    evidence_sufficient: bool,
    result_consistent: bool,
    permission_allowed: bool,
    risk_below_threshold: bool,
) -> AnswerConditions:
    return AnswerConditions(
        constraints_complete=bool(constraints_complete),
        evidence_sufficient=bool(evidence_sufficient),
        result_consistent=bool(result_consistent),
        permission_allowed=bool(permission_allowed),
        risk_below_threshold=bool(risk_below_threshold),
    )
