import unittest

from agent_core.contracts import AgentContext, RouteDecision, ToolCall
from agent_core.coordination import coordinate_tool_calls
from agent_core.router import RuleRouter
from agent_core.runtime import AgentRuntime


class FailingPlanner:
    async def plan(self, decision, *, history):
        raise AssertionError("coordinated questions should not call the local planner")


class RecordingExecutor:
    async def __call__(self, call, context):
        return {"answer": call.name, "metrics": {"ok": 1}, "data_sources": []}


class CoordinationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.router = RuleRouter()

    def test_composite_metric_route_is_statistics(self):
        decision = self.router.route(
            "综合分析2023年招生计划、录取和报到情况",
            known_majors=("人工智能",),
            latest_year=2023,
        )
        self.assertEqual(decision.intent, "admissions_statistics")

    def test_special_plan_delta_is_simulation(self):
        decision = self.router.route(
            "如果增加专项计划20个，结合历史计划完成率评估风险",
            known_majors=("人工智能",),
            latest_year=2023,
        )
        self.assertEqual(decision.intent, "plan_simulation")
        self.assertEqual(decision.params["plan_delta"], 20)

    def test_source_and_plan_are_coordinated(self):
        decision = self.router.route(
            "综合分析2023年招生计划和生源情况",
            latest_year=2023,
        )
        calls = coordinate_tool_calls(decision.normalized_message, decision)
        self.assertEqual([call.name for call in calls], ["admissions_overview", "source_overview"])

    async def test_runtime_uses_coordinated_plan_without_llm(self):
        runtime = AgentRuntime(tool_executor=RecordingExecutor(), llm_planner=FailingPlanner())
        decision = RouteDecision(
            intent="admissions_overview",
            normalized_message="综合分析2023年招生计划和生源情况",
            params={"year": 2023},
        )
        primary, secondary, summary = await runtime._plan_candidates(decision, message=decision.normalized_message)
        self.assertEqual(primary.name, "rule_multi_tool_plan")
        self.assertEqual([call.name for call in primary.tool_calls], ["admissions_overview", "source_overview"])
        self.assertIsNone(secondary)
        self.assertIn("多工具", summary)

    async def test_composite_metrics_use_statistics_without_llm(self):
        runtime = AgentRuntime(tool_executor=RecordingExecutor(), llm_planner=FailingPlanner())
        decision = RouteDecision(
            intent="student_lookup",
            normalized_message="综合分析2023年招生计划、录取和报到情况",
            params={"year": 2023},
        )
        primary, _, _ = await runtime._plan_candidates(decision, message=decision.normalized_message)
        self.assertEqual([call.name for call in primary.tool_calls], ["admissions_statistics"])


if __name__ == "__main__":
    unittest.main()
