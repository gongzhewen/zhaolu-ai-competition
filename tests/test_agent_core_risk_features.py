import unittest

from agent_core.contracts import (
    EvidenceCertificate,
    PlanConsistency,
    RouteDecision,
    SemanticSlots,
    SlotAmbiguity,
)
from agent_core.privacy import PrivacyAssessment
from agent_core.risk import build_risk_features, decide_risk


def certificate() -> EvidenceCertificate:
    return EvidenceCertificate(
        tool_name="admissions_overview",
        data_source=("fact.plan:招生计划",),
        year_range=(2026, 2026),
        filters={"year": 2026},
        canonical_major=None,
        aggregation="sum_ratio",
        row_count=1,
        result_value={"plan_count": 100},
        missing_value_count=0,
        permission_scope="school_scope",
        completeness=1.0,
    )


def consistency() -> PlanConsistency:
    return PlanConsistency(
        triggered=False,
        primary="rule_tool_plan",
        secondary=None,
        consistent=True,
        score=1.0,
    )


class RiskFeatureTests(unittest.TestCase):
    def test_alias_scope_is_exposed_as_feature(self):
        decision = RouteDecision(
            intent="major_alias_lookup",
            normalized_message="计算机类是什么专业",
            params={"source_name": "计算机类"},
        )
        features = build_risk_features(
            decision=decision,
            ambiguity=SlotAmbiguity(score=0.0),
            evidence=[certificate()],
            numeric_verification={"coverage": 1.0},
            plan_consistency=consistency(),
            data_support={"score": 1.0},
            privacy=PrivacyAssessment(allowed=True, risk=0.0, reasons=[]),
            tool_results=[{"metrics": {"matched": 1}}],
        )
        self.assertEqual(features.alias_risk, 0.2)
        self.assertEqual(features.ambiguity, 0.1)
        self.assertEqual(features.numeric_gap, 0.0)

    def test_missing_required_slot_raises_ambiguity_and_permission_risk(self):
        decision = RouteDecision(
            intent="student_lookup",
            normalized_message="分析某位同名学生档案",
            params={},
        )
        features = build_risk_features(
            decision=decision,
            ambiguity=SlotAmbiguity(score=0.2),
            evidence=[certificate()],
            numeric_verification={"coverage": 1.0},
            plan_consistency=consistency(),
            data_support={"score": 1.0},
            privacy=PrivacyAssessment(
                allowed=False,
                risk=1.0,
                reasons=["无权限"],
                response="无权限",
            ),
            tool_results=[],
            slots=SemanticSlots(intent="student_lookup", missing_required=("student_name",)),
        )
        self.assertEqual(features.required_slot_gap, 1.0)
        self.assertEqual(features.ambiguity, 1.0)
        self.assertEqual(features.permission_risk, 1.0)
        self.assertEqual(features.missing_data_risk, 1.0)

    def test_decide_risk_contains_complete_feature_vector(self):
        decision = RouteDecision(
            intent="admissions_overview",
            normalized_message="2026年招生计划",
            params={"year": 2026},
        )
        risk = decide_risk(
            decision=decision,
            ambiguity=SlotAmbiguity(score=0.0),
            evidence=[certificate()],
            numeric_verification={"coverage": 1.0},
            plan_consistency=consistency(),
            data_support={"score": 1.0, "status": "sufficient"},
            privacy=PrivacyAssessment(allowed=True, risk=0.0, reasons=[]),
            tool_results=[{"metrics": {"plan_count": 100}}],
            threshold=0.32,
            slots=SemanticSlots(intent="admissions_overview", year=2026),
        )
        self.assertEqual(risk.strategy, "answer")
        self.assertGreaterEqual(risk.features.evidence_gap, 0.0)
        self.assertLessEqual(risk.features.evidence_gap, 1.0)


if __name__ == "__main__":
    unittest.main()
