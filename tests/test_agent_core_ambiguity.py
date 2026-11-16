import unittest

from agent_core.contracts import RouteDecision, SemanticSlots
from agent_core.semantics import estimate_slot_ambiguity


class AmbiguityTests(unittest.TestCase):
    def test_generic_major_question_needs_scope(self):
        decision = RouteDecision(intent="policy_faq", normalized_message="这个专业怎么样")
        slots = SemanticSlots(intent=decision.intent)
        result = estimate_slot_ambiguity(decision.normalized_message, decision, slots)
        self.assertTrue(result.requires_clarification)
        self.assertIn("标准专业名称", result.clarification or "")

    def test_ambiguous_arrival_metric_needs_metric_choice(self):
        decision = RouteDecision(intent="source_overview", normalized_message="新生到校情况如何")
        slots = SemanticSlots(intent=decision.intent)
        result = estimate_slot_ambiguity(decision.normalized_message, decision, slots)
        self.assertTrue(result.requires_clarification)
        self.assertIn("报到率", result.clarification or "")

    def test_complete_question_has_zero_ambiguity(self):
        decision = RouteDecision(
            intent="admissions_overview",
            normalized_message="2026年计算机科学与技术专业计划完成率是多少",
            params={"year": 2026, "major": "计算机科学与技术"},
        )
        slots = SemanticSlots(intent=decision.intent, metrics=("completion_rate",))
        result = estimate_slot_ambiguity(decision.normalized_message, decision, slots)
        self.assertFalse(result.requires_clarification)
        self.assertEqual(result.score, 0.0)


if __name__ == "__main__":
    unittest.main()
