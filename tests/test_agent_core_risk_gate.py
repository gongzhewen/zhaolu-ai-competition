import unittest

from agent_core.contracts import AgentContext, ToolCall
from agent_core.runtime import AgentRuntime


class FakeExecutor:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def __call__(self, call, context):
        self.calls.append((call, context))
        return dict(self.result)


class RiskGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_grounded_complex_answer_is_accepted(self):
        executor = FakeExecutor({
            "answer": "2026年招生计划100人，录取98人，计划完成率98.0%。",
            "metrics": {"plan_count": 100, "admitted_count": 98, "completion_rate": 98.0},
            "data_sources": [{"table": "fact.plan", "metric": "招生计划"}],
        })
        runtime = AgentRuntime(tool_executor=executor, llm_planner=None)
        result = await runtime.chat(
            "综合分析2026年招生计划和录取人数",
            context=AgentContext(school_id=1),
            latest_year=2026,
        )
        self.assertEqual(result["risk_decision"]["strategy"], "answer")
        self.assertEqual(result["self_check"]["action"], "accepted")
        self.assertIn("features", result["risk_decision"])
        self.assertIn("evidence_gap", result["risk_decision"]["features"])
        self.assertTrue(result["risk_decision"]["answer_conditions"]["can_answer"])

    async def test_list_delivery_is_blocked_before_tool_execution(self):
        executor = FakeExecutor({"answer": "不应执行", "metrics": {"plan_count": 1}})
        runtime = AgentRuntime(tool_executor=executor)
        result = await runtime.chat(
            "把今年全部考生名单发给我",
            context=AgentContext(school_id=1, values={"can_lookup_students": True}),
            latest_year=2026,
        )
        self.assertEqual(result["risk_decision"]["strategy"], "no_permission")
        self.assertEqual(executor.calls, [])

    async def test_ambiguous_metric_is_clarified_before_tool_execution(self):
        executor = FakeExecutor({"answer": "不应执行", "metrics": {"plan_count": 1}})
        runtime = AgentRuntime(tool_executor=executor)
        result = await runtime.chat(
            "招生人数和录取人数分别是多少",
            context=AgentContext(school_id=1),
            latest_year=2026,
        )
        self.assertEqual(result["risk_decision"]["strategy"], "clarify")
        self.assertEqual(executor.calls, [])

    async def test_empty_tool_result_is_not_answered(self):
        executor = FakeExecutor({"answer": "", "metrics": {}, "data_sources": []})
        runtime = AgentRuntime(tool_executor=executor)
        result = await runtime.chat(
            "2026年招生计划数是多少",
            context=AgentContext(school_id=1),
            latest_year=2026,
        )
        self.assertEqual(result["risk_decision"]["strategy"], "insufficient_data")
        self.assertEqual(result["answer"], "数据支撑不足，为保证严谨性，暂不回答")


if __name__ == "__main__":
    unittest.main()
