from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class CalibrationSample:
    risk_score: float
    should_answer: bool


@dataclass(slots=True, frozen=True)
class ThresholdEvaluation:
    threshold: float
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    precision: float
    recall: float
    false_answer_rate: float
    false_refusal_rate: float
    balanced_accuracy: float
    answer_coverage: float
    cost: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "threshold": self.threshold,
            "true_positive": self.true_positive,
            "false_positive": self.false_positive,
            "true_negative": self.true_negative,
            "false_negative": self.false_negative,
            "precision": self.precision,
            "recall": self.recall,
            "false_answer_rate": self.false_answer_rate,
            "false_refusal_rate": self.false_refusal_rate,
            "balanced_accuracy": self.balanced_accuracy,
            "answer_coverage": self.answer_coverage,
            "cost": self.cost,
        }


@dataclass(slots=True, frozen=True)
class CalibrationResult:
    threshold: float
    preferred_threshold: float
    sample_count: int
    answer_sample_count: int
    block_sample_count: int
    selected: ThresholdEvaluation
    preferred: ThresholdEvaluation
    curve: list[ThresholdEvaluation]


def evaluate_threshold(
    samples: list[CalibrationSample],
    threshold: float,
    *,
    false_answer_cost: float = 5.0,
    false_refusal_cost: float = 1.0,
) -> ThresholdEvaluation:
    tp = fp = tn = fn = 0
    for sample in samples:
        predicted_answer = sample.risk_score <= threshold
        if sample.should_answer and predicted_answer:
            tp += 1
        elif sample.should_answer:
            fn += 1
        elif predicted_answer:
            fp += 1
        else:
            tn += 1
    positives = tp + fn
    negatives = tn + fp
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / positives if positives else 0.0
    false_answer_rate = fp / negatives if negatives else 0.0
    false_refusal_rate = fn / positives if positives else 0.0
    balanced_accuracy = (recall + (tn / negatives if negatives else 0.0)) / 2
    coverage = (tp + fp) / len(samples) if samples else 0.0
    cost = false_answer_cost * fp + false_refusal_cost * fn
    return ThresholdEvaluation(
        threshold=round(threshold, 6),
        true_positive=tp,
        false_positive=fp,
        true_negative=tn,
        false_negative=fn,
        precision=round(precision, 4),
        recall=round(recall, 4),
        false_answer_rate=round(false_answer_rate, 4),
        false_refusal_rate=round(false_refusal_rate, 4),
        balanced_accuracy=round(balanced_accuracy, 4),
        answer_coverage=round(coverage, 4),
        cost=round(cost, 4),
    )


def calibrate_threshold(
    samples: list[CalibrationSample],
    *,
    preferred_threshold: float = 0.32,
    false_answer_cost: float = 5.0,
    false_refusal_cost: float = 1.0,
) -> CalibrationResult:
    if not samples:
        preferred = evaluate_threshold([], preferred_threshold)
        return CalibrationResult(preferred_threshold, preferred_threshold, 0, 0, 0, preferred, preferred, [preferred])
    answer_scores = sorted(sample.risk_score for sample in samples if sample.should_answer)
    block_scores = sorted(sample.risk_score for sample in samples if not sample.should_answer)
    if not answer_scores or not block_scores:
        preferred = evaluate_threshold(
            samples,
            preferred_threshold,
            false_answer_cost=false_answer_cost,
            false_refusal_cost=false_refusal_cost,
        )
        return CalibrationResult(
            preferred_threshold,
            preferred_threshold,
            len(samples),
            len(answer_scores),
            len(block_scores),
            preferred,
            preferred,
            [preferred],
        )

    candidates = {0.0, 1.0, preferred_threshold}
    ordered_scores = sorted({sample.risk_score for sample in samples})
    candidates.update((left + right) / 2 for left, right in zip(ordered_scores, ordered_scores[1:]))
    curve = [
        evaluate_threshold(
            samples,
            threshold,
            false_answer_cost=false_answer_cost,
            false_refusal_cost=false_refusal_cost,
        )
        for threshold in sorted(candidates)
    ]
    target = (answer_scores[-1] + block_scores[0]) / 2 if answer_scores[-1] < block_scores[0] else preferred_threshold

    def rank(item: ThresholdEvaluation) -> tuple[float, float, float, float]:
        return (
            float(item.cost),
            -float(item.balanced_accuracy),
            abs(float(item.threshold) - target),
            -float(item.answer_coverage),
        )

    selected = min(curve, key=rank)
    preferred = evaluate_threshold(
        samples,
        preferred_threshold,
        false_answer_cost=false_answer_cost,
        false_refusal_cost=false_refusal_cost,
    )
    return CalibrationResult(
        threshold=selected.threshold,
        preferred_threshold=preferred_threshold,
        sample_count=len(samples),
        answer_sample_count=len(answer_scores),
        block_sample_count=len(block_scores),
        selected=selected,
        preferred=preferred,
        curve=curve,
    )
