import unittest

from agent_core.evaluation import assess_data_support, evaluate_answer
from agent_core.optimizer import calculate_weight_update, task_type_for_intent


class QualityTests(unittest.TestCase):
    def test_grounded_answer_is_accepted(self):
        result = evaluate_answer(
            question="2026年招生计划数是多少",
            intent="admissions_overview",
            answer="2026年招生计划为100人。",
            tool_calls=[{"name": "admissions_overview"}],
            tool_results=[{"answer": "2026年招生计划为100人。", "metrics": {"plan_count": 100}}],
        )
        self.assertEqual(result["action"], "accepted")
        self.assertEqual(result["score"], 1.0)

    def test_data_support_rejects_uncalled_tool(self):
        support = assess_data_support(
            result={"confidence": "high", "tool_results": [], "data_sources": []},
            self_check={"score": 1.0},
            canonical_intent="admissions_overview",
        )
        self.assertEqual(support["status"], "insufficient")
        self.assertLessEqual(support["score"], 0.35)

    def test_phone_number_fails_safety_check(self):
        result = evaluate_answer(
            question="学生情况",
            intent="student_lookup",
            answer="联系电话：13800138000",
            tool_calls=[{"name": "student_lookup"}],
            tool_results=[{"answer": "已隐藏", "metrics": {"count": 1}}],
        )
        self.assertEqual(result["dimensions"]["safety"], 0.0)
        self.assertIn("疑似包含手机号", " ".join(result["issues"]))

    def test_feedback_weight_update(self):
        update = calculate_weight_update(current_score=1.0, rating=3, previous_weight=1.0)
        self.assertEqual(update["gradient"], 0.4)
        self.assertEqual(update["new_weight"], 0.98)
        self.assertEqual(update["reward"], -0.4)

    def test_decision_task_type(self):
        self.assertEqual(task_type_for_intent("plan_simulation"), "decision")
        self.assertEqual(task_type_for_intent("policy_faq"), "policy")
        self.assertEqual(task_type_for_intent("admissions_overview"), "analysis")


if __name__ == "__main__":
    unittest.main()
