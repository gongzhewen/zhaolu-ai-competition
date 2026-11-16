import unittest

from agent_core.contracts import RouteDecision
from agent_core.runtime import AgentRuntime
from agent_core.contracts import ToolCall


class ParameterPropagationTests(unittest.TestCase):
    def _params(self, name, decision_params, call_params=None):
        decision = RouteDecision(
            intent=name,
            normalized_message="test",
            params=decision_params,
        )
        calls = AgentRuntime._materialize_calls(
            [ToolCall(name, call_params or {})],
            decision,
        )
        return calls[0].params

    def test_year_reaches_tools_with_legacy_empty_specs(self):
        cases = {
            "source_overview": 2025,
            "candidate_profile": 2025,
            "subject_scores": 2025,
            "forecast": 2025,
            "anomaly_detection": 2025,
            "consultation_overview": 2025,
            "enrollment_funnel": 2025,
        }
        for tool_name, year in cases.items():
            with self.subTest(tool=tool_name):
                params = self._params(tool_name, {"year": year})
                self.assertEqual(params.get("year"), year)

    def test_scope_filters_reach_supported_tools(self):
        params = self._params(
            "candidate_profile",
            {"year": 2026, "province": "河南", "major": "计算机科学与技术"},
        )
        self.assertEqual(params["province"], "河南")
        self.assertEqual(params["major"], "计算机科学与技术")

    def test_alias_and_score_band_receive_query_context(self):
        alias_params = self._params(
            "major_alias_lookup",
            {"major": "计算机类", "query": "计算机类有哪些别名"},
        )
        self.assertEqual(alias_params["major"], "计算机类")
        self.assertEqual(alias_params["query"], "计算机类有哪些别名")
        score_params = self._params(
            "score_band_statistics",
            {"year": 2026, "query": "政治分数段"},
        )
        self.assertEqual(score_params["year"], 2026)
        self.assertEqual(score_params["query"], "政治分数段")

    def test_unknown_parameters_are_still_filtered(self):
        params = self._params(
            "source_overview",
            {"year": 2026, "unexpected": "drop", "can_lookup_students": True},
        )
        self.assertEqual(params, {"year": 2026})


if __name__ == "__main__":
    unittest.main()
