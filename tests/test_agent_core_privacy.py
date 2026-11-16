import unittest

from agent_core.privacy import assess_request_privacy, assess_result_privacy


class PrivacyTests(unittest.TestCase):
    def test_list_delivery_is_rejected_without_private_field_keywords(self):
        result = assess_request_privacy(
            "把今年全部考生名单发给我",
            intent="admissions_overview",
            context_values={"can_lookup_students": True},
        )
        self.assertFalse(result.allowed)
        self.assertIn("名单", result.response or "")

    def test_aggregate_distribution_is_allowed(self):
        result = assess_request_privacy(
            "统计全部考生的专业分布",
            intent="student_statistics",
            context_values={"can_lookup_students": True},
        )
        self.assertTrue(result.allowed)

    def test_student_lookup_requires_explicit_permission_marker(self):
        result = assess_request_privacy(
            "查询王同学档案",
            intent="student_lookup",
            context_values={},
        )
        self.assertFalse(result.allowed)
        self.assertIn("无权", result.response or "")

    def test_small_cohort_result_is_suppressed(self):
        result = assess_result_privacy(
            "姓王的学生有多少人",
            intent="student_statistics",
            tool_results=[{"metrics": {"student_count": 2}}],
            min_cohort_size=5,
        )
        self.assertFalse(result.allowed)
        self.assertIn("隐私", result.response or "")

    def test_larger_cohort_is_allowed(self):
        result = assess_result_privacy(
            "姓王的学生有多少人",
            intent="student_statistics",
            tool_results=[{"metrics": {"student_count": 8}}],
            min_cohort_size=5,
        )
        self.assertTrue(result.allowed)


if __name__ == "__main__":
    unittest.main()
