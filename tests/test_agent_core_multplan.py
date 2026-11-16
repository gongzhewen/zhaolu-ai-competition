import unittest

from agent_core.contracts import AgentContext, RouteDecision, ToolCall
from agent_core.runtime import AgentRuntime


class FakeExecutor:
    async def __call__(self, call, context):
        return {
            "answer": "2026年招生计划100人。",
            "metrics": {"plan_count": 100},
            "data_sources": [{"table": "fact.plan", "metric": "招生计划"}],
        }


class FakePlanner:
    async def plan(self, decision, *, history):
        return [ToolCall("source_overview", {"year": 2026})]


class MultiPlanTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_local_model_is_honest_single_plan(self):
        runtime = AgentRuntime(tool_executor=FakeExecutor(), llm_planner=None)
        decision = RouteDecision(
            intent="admissions_overview",
            normalized_message="综合分析2026年招生计划",
            params={"year": 2026},
        )
        primary, secondary, summary = await runtime._plan_candidates(
            decision,
            message=decision.normalized_message,
        )
        self.assertEqual(primary.name, "rule_tool_plan")
        self.assertIsNone(secondary)
        self.assertIn("单计划", summary)

    async def test_local_model_and_rule_form_independent_candidates(self):
        runtime = AgentRuntime(tool_executor=FakeExecutor(), llm_planner=FakePlanner())
        decision = RouteDecision(
            intent="admissions_overview",
            normalized_message="综合分析2026年招生计划",
            params={"year": 2026},
        )
        primary, secondary, summary = await runtime._plan_candidates(
            decision,
            message=decision.normalized_message,
        )
        self.assertEqual(primary.name, "local_model_plan")
        self.assertEqual(primary.tool_calls[0].name, "source_overview")
        self.assertIsNotNone(secondary)
        self.assertEqual(secondary.tool_calls[0].name, "admissions_overview")
        self.assertIn("规则计划核验", summary)

    async def test_single_plan_complex_query_is_not_blocked_for_missing_second_plan(self):
        runtime = AgentRuntime(tool_executor=FakeExecutor(), llm_planner=None)
        result = await runtime.chat(
            "综合分析2026年招生计划",
            context=AgentContext(school_id=1),
            latest_year=2026,
        )
        self.assertEqual(result["plan_consistency"]["triggered"], False)
        self.assertEqual(result["risk_decision"]["strategy"], "answer")


if __name__ == "__main__":
    unittest.main()
