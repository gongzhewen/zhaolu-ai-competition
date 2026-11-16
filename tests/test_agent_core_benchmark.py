import unittest

from agent_core.benchmark import BenchmarkCase, evaluate_case, summarize_results


class BenchmarkSummaryTests(unittest.TestCase):
    def test_boundary_cases_do_not_inflate_metric_accuracy(self):
        answer_case = BenchmarkCase(
            case_id="A",
            question="q1",
            category="data",
            expected_intent="admissions_overview",
            expected_strategy="answer",
            expected_tool="admissions_overview",
            expected_metrics={"plan_count": 100},
        )
        boundary_case = BenchmarkCase(
            case_id="B",
            question="q2",
            category="boundary",
            expected_intent="out_of_scope",
            expected_strategy="out_of_scope",
        )
        rows = [
            evaluate_case(
                answer_case,
                {
                    "intent": "admissions_overview",
                    "tool_calls": [{"name": "admissions_overview", "params": {}}],
                    "tool_results": [{"metrics": {"plan_count": 100}}],
                    "risk_decision": {"strategy": "answer", "score": 0.01},
                },
                1.0,
            ),
            evaluate_case(
                boundary_case,
                {"intent": "out_of_scope", "tool_calls": [], "tool_results": [], "risk_decision": {"strategy": "out_of_scope", "score": 1.0}},
                1.0,
            ),
        ]
        summary = summarize_results(rows)
        self.assertEqual(summary["overall_accuracy"], 1.0)
        self.assertEqual(summary["tool_plan_accuracy"], 1.0)
        self.assertEqual(summary["exact_metric_accuracy"], 1.0)
        self.assertLessEqual(summary["tool_plan_accuracy"], 1.0)
        self.assertLessEqual(summary["exact_metric_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
