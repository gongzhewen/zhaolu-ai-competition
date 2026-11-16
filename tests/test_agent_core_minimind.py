import unittest

from agent_core.minimind import MiniMindConfig, MiniMindRouter, build_minimind_planner_prompt, parse_minimind_plan
from agent_core.planner import should_use_llm_plan


class MiniMindTests(unittest.TestCase):
    def test_planner_prompt_contains_allowed_tool_and_schema(self):
        prompt = build_minimind_planner_prompt("admissions_overview")
        self.assertIn("admissions_overview", prompt)
        self.assertIn("year", prompt)
        self.assertIn('"tools"', prompt)
        self.assertNotIn("student_lookup", prompt)

    def test_plan_parser_accepts_allowed_tool(self):
        plan = parse_minimind_plan(
            '{"tools":[{"name":"admissions_overview","params":{"year":2025,"province":"湖南"}}]}',
            message="2025年湖南招生多少人",
            fallback_intent="admissions_overview",
            fallback_params={"year": 2025, "province": "湖南"},
        )
        self.assertIsNotNone(plan)
        self.assertEqual(plan["tools"][0]["params"]["year"], 2025)
        self.assertEqual(plan["tools"][0]["params"]["province"], "湖南")

    def test_plan_parser_rejects_student_tools(self):
        plan = parse_minimind_plan(
            '{"tools":[{"name":"student_lookup","params":{"student_name":"张三"}}]}',
            message="分析2024年录取的名为张三的学生",
            fallback_intent="student_lookup",
            fallback_params={"year": 2024, "student_name": "张三"},
        )
        self.assertIsNone(plan)

    def test_plan_simulation_requires_major_and_delta(self):
        valid = parse_minimind_plan(
            '{"tools":[{"name":"plan_simulation","params":{"major":"土木工程","plan_delta":20}}]}',
            message="土木工程增加20个计划",
            fallback_intent="plan_simulation",
            fallback_params={"major": "土木工程", "plan_delta": 20},
        )
        invalid = parse_minimind_plan(
            '{"tools":[{"name":"plan_simulation","params":{}}]}',
            message="土木工程增加20个计划",
            fallback_intent="plan_simulation",
            fallback_params={},
        )
        self.assertIsNotNone(valid)
        self.assertIsNone(invalid)

    def test_parser_rejects_disallowed_intent_tool_pair(self):
        plan = parse_minimind_plan(
            '{"tools":[{"name":"major_choices","params":{}}]}',
            message="2026年招生计划数是多少",
            fallback_intent="admissions_overview",
            fallback_params={},
        )
        self.assertIsNone(plan)

    def test_forecast_triggers_local_planner_in_fast_mode(self):
        self.assertTrue(
            should_use_llm_plan(
                "普通预测问题",
                "forecast",
                fast_mode=True,
                llm_configured=True,
            )
        )


class MiniMindRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_router_uses_injected_post(self):
        async def post_json(url: str, payload: dict, timeout: float):
            return {"choices": [{"message": {"content": '{"tools":[{"name":"admissions_overview","params":{"year":2025}}]}'}}]}

        router = MiniMindRouter(
            MiniMindConfig(enabled=True, base_url="http://localhost:8998/v1"),
            post_json=post_json,
        )
        plan = await router.route("2025年招生多少人")
        self.assertIsNotNone(plan)
        self.assertEqual(plan["tools"][0]["name"], "admissions_overview")


if __name__ == "__main__":
    unittest.main()
