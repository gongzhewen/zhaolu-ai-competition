import unittest

from agent_core.router import RuleRouter
from agent_core.semantics import compile_semantic_slots, estimate_slot_ambiguity


class SemanticSlotTests(unittest.TestCase):
    def setUp(self):
        self.router = RuleRouter()

    def compile(self, question):
        decision = self.router.route(question, latest_year=2026)
        slots = compile_semantic_slots(question, decision)
        ambiguity = estimate_slot_ambiguity(question, decision, slots)
        return decision, slots, ambiguity

    def test_arrival_ratio_definition_is_policy_faq_without_ambiguity(self):
        decision, slots, ambiguity = self.compile("新生到校比例怎么理解")
        self.assertEqual(decision.intent, "policy_faq")
        self.assertIn("enrollment_rate", slots.metrics)
        self.assertFalse(ambiguity.requires_clarification)

    def test_mixed_plan_and_admitted_metric_requires_clarification(self):
        decision, slots, ambiguity = self.compile("招生人数和录取人数分别是多少")
        self.assertEqual(decision.intent, "admissions_overview")
        self.assertIn("plan_count", slots.metrics)
        self.assertIn("admitted_count", slots.metrics)
        self.assertTrue(ambiguity.requires_clarification)
        self.assertEqual(ambiguity.slot_entropy.get("metric"), 1.0)
        self.assertEqual(ambiguity.semantic_uncertainty, 0.3)

    def test_score_filter_is_not_treated_as_ambiguous_count(self):
        decision, slots, ambiguity = self.compile("政治考了66分的人有多少")
        self.assertEqual(decision.intent, "student_statistics")
        self.assertEqual(decision.params.get("exam_subject_name"), "政治")
        self.assertEqual(str(decision.params.get("exam_score_value")), "66")
        self.assertEqual(slots.metrics, ("student_count",))
        self.assertFalse(ambiguity.requires_clarification)

    def test_surname_typo_requires_confirmation(self):
        _, _, ambiguity = self.compile("张性同学有多少人")
        self.assertTrue(ambiguity.requires_clarification)
        self.assertIn("张姓学生", ambiguity.clarification or "")

    def test_placeholder_same_name_student_requires_clarification(self):
        decision, _, ambiguity = self.compile("分析一下某位同名学生的档案")
        self.assertEqual(decision.intent, "student_lookup")
        self.assertTrue(ambiguity.requires_clarification)
        self.assertIn("完整姓名", ambiguity.clarification or "")

    def test_major_completion_keeps_year_and_completion_metrics(self):
        decision, slots, ambiguity = self.compile("2025年各专业招生计划完成情况怎么样")
        self.assertEqual(decision.params.get("year"), 2025)
        self.assertEqual(decision.params.get("group_by"), "major_name")
        self.assertIn("plan_count", slots.metrics)
        self.assertIn("completion_rate", slots.metrics)
        self.assertFalse(ambiguity.requires_clarification)


if __name__ == "__main__":
    unittest.main()
