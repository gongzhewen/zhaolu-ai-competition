import unittest

from agent_core.registry import TOOL_BY_NAME, TOOL_NAMES
from app.modules.agent.tools.registry import LEGACY_ONLY_TOOLS, NATIVE_TOOL_EXECUTORS
from app.modules.ai_gateway.legacy_agent import TOOL_DEFINITIONS, TOOL_EXECUTORS


class LegacyToolParityTests(unittest.TestCase):
    def test_executor_names_match_v2_registry(self):
        self.assertTrue(set(TOOL_EXECUTORS).issubset(set(TOOL_NAMES)))
        self.assertEqual(len(TOOL_EXECUTORS), 17)
        self.assertNotIn("admissions_statistics", TOOL_EXECUTORS)

    def test_definition_names_match_v2_registry(self):
        self.assertTrue(set(TOOL_DEFINITIONS).issubset(set(TOOL_BY_NAME)))
        self.assertIn("admissions_statistics", TOOL_BY_NAME)

    def test_native_tools_cover_all_registered_tools(self):
        self.assertEqual(len(NATIVE_TOOL_EXECUTORS), 18)
        self.assertEqual(LEGACY_ONLY_TOOLS, frozenset())
        self.assertEqual(set(NATIVE_TOOL_EXECUTORS) | set(LEGACY_ONLY_TOOLS), set(TOOL_NAMES))

    def test_core_parameters_match_for_structured_tools(self):
        for name in (
            "admissions_overview",
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
        ):
            self.assertEqual(
                tuple(TOOL_DEFINITIONS[name]["params"]),
                TOOL_BY_NAME[name].params,
                name,
            )


if __name__ == "__main__":
    unittest.main()



