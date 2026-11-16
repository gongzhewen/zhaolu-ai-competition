import unittest

from agent_core.registry import SAFE_TOOLS, TOOL_NAMES, get_tool_spec, validate_tool_call


class RegistryTests(unittest.TestCase):
    def test_exactly_eighteen_tools(self):
        self.assertEqual(len(TOOL_NAMES), 18)
        self.assertEqual(len(set(TOOL_NAMES)), 18)

    def test_required_tools_exist(self):
        required = {
            "admissions_overview",
            "source_overview",
            "candidate_profile",
            "subject_scores",
            "major_choices",
            "medical_summary",
            "forecast",
            "official_admission_stats",
            "major_alias_lookup",
            "student_lookup",
            "student_statistics",
            "anomaly_detection",
            "plan_simulation",
            "policy_faq",
            "consultation_overview",
            "enrollment_funnel",
            "score_band_statistics",
            "admissions_statistics",
        }
        self.assertEqual(set(TOOL_NAMES), required)

    def test_student_tools_are_not_local_router_safe(self):
        self.assertNotIn("student_lookup", SAFE_TOOLS)
        self.assertNotIn("student_statistics", SAFE_TOOLS)

    def test_plan_simulation_parameters(self):
        spec = get_tool_spec("plan_simulation")
        self.assertEqual(spec.params, ("year", "major", "plan_delta"))
        ok, error = validate_tool_call("plan_simulation", {"year": 2026, "major": "土木工程", "plan_delta": 20})
        self.assertTrue(ok, error)

    def test_unknown_parameter_is_rejected(self):
        ok, error = validate_tool_call("official_admission_stats", {"year": 2026, "unknown": 1})
        self.assertFalse(ok)
        self.assertIn("unsupported params", error or "")


if __name__ == "__main__":
    unittest.main()
