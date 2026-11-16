import unittest

from agent_core.analytics import build_expansion_decision, completion_rate, linear_forecast, simulate_plan_change, source_coverage_rate


class AnalyticsTests(unittest.TestCase):
    def test_completion_and_coverage(self):
        self.assertEqual(completion_rate(100, 95), 95.0)
        self.assertEqual(source_coverage_rate(98, 100), 98.0)
        self.assertEqual(completion_rate(0, 10), 0.0)

    def test_linear_forecast_uses_trend(self):
        prediction, margin = linear_forecast([100.0, 110.0, 120.0])
        self.assertEqual(prediction, 130.0)
        self.assertGreaterEqual(margin, 6.5)

    def test_plan_simulation(self):
        result = simulate_plan_change(
            major_name="土木工程",
            plan_count=100,
            admitted_count=95,
            choice_count=300,
            plan_delta=20,
        )
        self.assertEqual(result["projected_plan"], 120)
        self.assertEqual(result["projected_admitted"], 115)
        self.assertEqual(result["projected_completion_rate"], 95.83)
        self.assertEqual(result["projected_score_change"], -1.6)

    def test_expansion_decision_contains_conclusion_and_advice(self):
        scenario = simulate_plan_change(
            major_name="土木工程",
            plan_count=100,
            admitted_count=95,
            choice_count=360,
            plan_delta=20,
        )
        result = build_expansion_decision(
            major_name="土木工程",
            year_no=2026,
            metric={"plan_count": 100, "admitted_count": 95, "choice_count": 360},
            forecast={"completion_rate": 96.0, "risk_level": "low"},
            scenario=scenario,
        )
        self.assertIn("明确结论", result["answer"])
        self.assertIn("执行建议", result["answer"])
        self.assertIn(result["decision_level"], {"支持", "审慎", "不建议", "数据不足"})

    def test_low_demand_blocks_direct_expansion(self):
        result = build_expansion_decision(
            major_name="冷门专业",
            year_no=2026,
            metric={"plan_count": 100, "admitted_count": 70, "choice_count": 50},
            forecast={"completion_rate": 88.0, "risk_level": "high"},
        )
        self.assertEqual(result["decision_level"], "不建议")
        self.assertEqual(result["recommended_min"], 0)


if __name__ == "__main__":
    unittest.main()
