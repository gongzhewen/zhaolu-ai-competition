from __future__ import annotations


def task_type_for_intent(intent: str) -> str:
    if intent in {"plan_simulation", "forecast_professional_analysis", "anomaly_detection"}:
        return "decision"
    if intent in {"policy_faq", "admissions_knowledge_base"}:
        return "policy"
    if intent in {
        "admissions_overview",
        "source_overview",
        "candidate_profile",
        "subject_scores",
        "major_choices",
        "medical_summary",
        "anomaly_detection",
    }:
        return "analysis"
    return "lookup"


def calculate_weight_update(
    *,
    current_score: float,
    rating: int,
    previous_weight: float,
    learning_rate: float = 0.05,
    minimum_weight: float = 0.1,
    maximum_weight: float = 3.0,
) -> dict[str, float]:
    target_score = max(0.0, min(1.0, rating / 5.0))
    gradient = current_score - target_score
    new_weight = max(
        minimum_weight,
        min(maximum_weight, previous_weight - learning_rate * gradient),
    )
    reward = target_score - current_score
    return {
        "target_score": round(target_score, 4),
        "gradient": round(gradient, 4),
        "reward": round(reward, 4),
        "previous_weight": round(previous_weight, 4),
        "new_weight": round(new_weight, 4),
    }
