import math
import unittest

from agent_core.contracts import EvidenceCertificate, PlanCandidate, PlanConsistency, RouteDecision, SemanticSlots, SlotAmbiguity, ToolCall
from agent_core.privacy import PrivacyAssessment
from agent_core.formal import entropy, estimate_semantic_uncertainty, normalized_entropy
from agent_core.risk import decide_risk
from agent_core.verification import build_plan_consistency, result_similarity


class FormalEntropyTests(unittest.TestCase):
    def test_uniform_two_candidate_entropy(self):
        self.assertAlmostEqual(entropy([0.5, 0.5]), math.log(2), places=6)
        self.assertEqual(normalized_entropy([0.5, 0.5]), 1.0)

    def test_single_candidate_has_zero_entropy(self):
        self.assertEqual(entropy([1.0]), 0.0)
        self.assertEqual(normalized_entropy([1.0]), 0.0)

    def test_weighted_semantic_uncertainty(self):
        result = estimate_semantic_uncertainty(
            {
                "metric": ("plan_count", "admitted_count"),
                "major": ("需要指定专业",),
            }
        )
        self.assertEqual(result.normalized_entropy["metric"], 1.0)
        self.assertEqual(result.normalized_entropy["major"], 0.0)
        self.assertEqual(result.weighted_uncertainty, 0.3)


class ContinuousSimilarityTests(unittest.TestCase):
    def test_numeric_result_similarity_is_continuous(self):
        primary = [{
            "tool": "admissions_overview",
            "metrics": {"plan_count": 100, "completion_rate": 98.0},
            "table": None,
            "data_sources": [{"table": "fact.plan"}],
        }]
        secondary = [{
            "tool": "admissions_overview",
            "metrics": {"plan_count": 99, "completion_rate": 98.0},
            "table": None,
            "data_sources": [{"table": "fact.plan"}],
        }]
        score = result_similarity(primary, secondary)
        self.assertGreater(score, 0.9)
        self.assertLess(score, 1.0)

    def test_threshold_controls_plan_consistency(self):
        primary = PlanCandidate("rule", [ToolCall("admissions_overview")], "rule")
        secondary = PlanCandidate("model", [ToolCall("admissions_overview", {"mode": "model"})], "local_model")
        results_a = [{"tool": "admissions_overview", "metrics": {"plan_count": 100}, "table": None, "data_sources": [{"table": "fact.plan"}]}]
        results_b = [{"tool": "admissions_overview", "metrics": {"plan_count": 99}, "table": None, "data_sources": [{"table": "fact.plan"}]}]
        strict = build_plan_consistency(primary, secondary, primary_results=results_a, secondary_results=results_b, triggered=True, threshold=1.0)
        tolerant = build_plan_consistency(primary, secondary, primary_results=results_a, secondary_results=results_b, triggered=True, threshold=0.9)
        self.assertFalse(strict.consistent)
        self.assertTrue(tolerant.consistent)


class FormalAnswerConditionTests(unittest.TestCase):
    @staticmethod
    def certificate():
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

    def test_answer_conditions_are_materialized(self):
        decision = RouteDecision(intent="admissions_overview", normalized_message="2026年招生计划", params={"year": 2026})
        risk = decide_risk(
            decision=decision,
            ambiguity=SlotAmbiguity(score=0.0),
            evidence=[],
            numeric_verification={"coverage": 1.0},
            plan_consistency=PlanConsistency(
                triggered=False,
                primary="rule",
                secondary=None,
                consistent=True,
                score=1.0,
            ),
            data_support={"score": 1.0, "status": "sufficient"},
            privacy=PrivacyAssessment(allowed=True, risk=0.0, reasons=[]),
            tool_results=[{"metrics": {"plan_count": 100}}],
            threshold=0.32,
            slots=SemanticSlots(intent="admissions_overview", year=2026),
        )
        # Empty evidence is intentionally insufficient even though risk may still be low.
        self.assertFalse(risk.answer_conditions["evidence_sufficient"])
        self.assertIn("can_answer", risk.answer_conditions)

    def test_all_formal_conditions_can_be_satisfied(self):
        decision = RouteDecision(intent="admissions_overview", normalized_message="2026年招生计划", params={"year": 2026})
        risk = decide_risk(
            decision=decision,
            ambiguity=SlotAmbiguity(score=0.0),
            evidence=[self.certificate()],
            numeric_verification={"coverage": 1.0},
            plan_consistency=PlanConsistency(triggered=False, primary="rule", secondary=None, consistent=True, score=1.0),
            data_support={"score": 1.0, "status": "sufficient"},
            privacy=PrivacyAssessment(allowed=True, risk=0.0, reasons=[]),
            tool_results=[{"metrics": {"plan_count": 100}}],
            threshold=0.32,
            slots=SemanticSlots(intent="admissions_overview", year=2026),
        )
        self.assertTrue(risk.answer_conditions["can_answer"])


if __name__ == "__main__":
    unittest.main()
