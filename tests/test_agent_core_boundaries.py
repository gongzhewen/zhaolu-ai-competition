import unittest
from agent_core.router import RuleRouter

class BoundaryRouterTests(unittest.TestCase):
    def setUp(self):
        self.router = RuleRouter()

    def test_plan_simulation_without_delta_asks_for_delta(self):
        decision = self.router.route(
            "明年土木工程专业我可以扩招吗",
            known_majors=("土木工程",),
            latest_year=2026,
        )
        self.assertEqual(decision.intent, "plan_simulation")
        self.assertIsNotNone(decision.clarification)
        self.assertIn("计划数", decision.clarification)

    def test_weather_is_out_of_scope(self):
        decision = self.router.route("今天天气怎么样", latest_year=2026)
        self.assertEqual(decision.intent, "out_of_scope")

    def test_joke_is_out_of_scope(self):
        decision = self.router.route("给我讲个笑话", latest_year=2026)
        self.assertEqual(decision.intent, "out_of_scope")

if __name__ == "__main__":
    unittest.main()
