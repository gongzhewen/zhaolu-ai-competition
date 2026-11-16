from __future__ import annotations

from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from .admissions import admissions_overview, anomaly_detection, forecast, official_admission_stats, plan_simulation
from .knowledge import major_alias_lookup, policy_faq
from .diagnostics import consultation_overview, enrollment_funnel, score_band_statistics
from .profiles import candidate_profile, major_choices, medical_summary, source_overview, subject_scores
from .statistics_analysis import admissions_statistics
from .students import student_lookup, student_statistics

ToolFunction = Callable[[AsyncSession, dict[str, Any]], Awaitable[dict[str, Any]]]

NATIVE_TOOL_EXECUTORS: dict[str, ToolFunction] = {
    "admissions_overview": admissions_overview,
    "source_overview": source_overview,
    "candidate_profile": candidate_profile,
    "subject_scores": subject_scores,
    "major_choices": major_choices,
    "medical_summary": medical_summary,
    "forecast": forecast,
    "official_admission_stats": official_admission_stats,
    "major_alias_lookup": major_alias_lookup,
    "anomaly_detection": anomaly_detection,
    "plan_simulation": plan_simulation,
    "student_lookup": student_lookup,
    "student_statistics": student_statistics,
    "policy_faq": policy_faq,
    "consultation_overview": consultation_overview,
    "enrollment_funnel": enrollment_funnel,
    "score_band_statistics": score_band_statistics,
    "admissions_statistics": admissions_statistics,
}

LEGACY_ONLY_TOOLS: frozenset[str] = frozenset()

