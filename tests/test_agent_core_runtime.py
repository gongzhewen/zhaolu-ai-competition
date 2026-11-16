import asyncio
import unittest

from agent_core.contracts import AgentContext, ToolCall
from agent_core.runtime import AgentRuntime


class FakeExecutor:
    def __init__(self, result=None):
        self.calls = []
        self.result = result or {
            "answer": "2026年招生计划为100人。",
            "metrics": {"plan_count": 100},
            "data_sources": [{"table": "fact.plan"}],
        }

    async def __call__(self, call: ToolCall, context: AgentContext):
        self.calls.append((call, context))
        return dict(self.result)


class EmptyExecutor(FakeExecutor):
    def __init__(self):
        super().__init__(
            {
                "answer": "",
                "metrics": {},
                "data_sources": [],
            }
        )


class FailingPlanner:
    async def plan(self, decision, *, history):
        raise AssertionError("LLM planner must not be called for this route")


class SlowPlanner:
    async def plan(self, decision, *, history):
        await asyncio.sleep(0.2)
        return [ToolCall("source_overview", {"year": decision.params.get("year")})]


class TrackingKnowledge:
    def __init__(self):
        self.calls = 0

    async def search(self, query, *, school_id, limit=4):
        self.calls += 1
        return [{"title": "招生计划口径", "content": "计划数来自数据库。"}]


class NoopPlanner:
    async def plan(self, decision, *, history):
        return None


class TrackingMemory:
    def __init__(self):
        self.load_calls = 0
        self.remembered = []

    async def load(self, query, *, user_id, school_id, limit=5):
        self.load_calls += 1
        return [{"memory_type": "preference", "summary": "用户重视风险"}]

    async def remember(self, payload):
        self.remembered.append(payload)


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_fast_path_uses_single_tool(self):
        executor = FakeExecutor()
        runtime = AgentRuntime(tool_executor=executor, llm_planner=FailingPlanner())
        result = await runtime.chat("2026年招生计划数是多少", latest_year=2026)
        self.assertEqual(result["intent"], "admissions_overview")
        self.assertEqual(result["tool_calls"][0]["name"], "admissions_overview")
        self.assertEqual(len(executor.calls), 1)
        self.assertIn("100", result["answer"])
        self.assertEqual(result["self_check"]["action"], "accepted")

    async def test_student_lookup_skips_memory_and_knowledge(self):
        executor = FakeExecutor({"answer": "学生已录取。", "metrics": {"count": 1}, "data_sources": [{"table": "fact.student_identity"}]})
        memory = TrackingMemory()
        knowledge = TrackingKnowledge()
        runtime = AgentRuntime(
            tool_executor=executor,
            llm_planner=FailingPlanner(),
            memory_provider=memory,
            knowledge_provider=knowledge,
        )
        result = await runtime.chat(
            "帮我分析2024年录取的名为“龚哲文”的学生",
            context=AgentContext(user_id=1, school_id=1, values={"can_lookup_students": True}),
            latest_year=2026,
        )
        self.assertEqual(result["intent"], "student_lookup")
        self.assertEqual(memory.load_calls, 0)
        self.assertEqual(knowledge.calls, 0)
        self.assertEqual(memory.remembered, [])

    async def test_low_support_answer_is_blocked(self):
        executor = EmptyExecutor()
        runtime = AgentRuntime(tool_executor=executor)
        result = await runtime.chat("2026年招生计划数是多少", latest_year=2026)
        self.assertEqual(result["answer"], "数据支撑不足，为保证严谨性，暂不回答")
        self.assertEqual(result["data_support"]["status"], "insufficient")
        self.assertEqual(result["self_check"]["action"], "insufficient_data")

    async def test_llm_planner_timeout_falls_back_to_rule_plan(self):
        executor = FakeExecutor()
        runtime = AgentRuntime(
            tool_executor=executor,
            llm_planner=SlowPlanner(),
            llm_planner_timeout_seconds=0.01,
        )
        result = await runtime.chat("为什么2023年招生计划可能需要调整", latest_year=2023)
        self.assertEqual(result["intent"], "admissions_overview")
        self.assertEqual(result["tool_calls"][0]["name"], "admissions_overview")
        self.assertIn("规则", result["plan_summary"])
    async def test_memory_and_knowledge_loaded_for_normal_chat(self):
        executor = FakeExecutor()
        memory = TrackingMemory()
        knowledge = TrackingKnowledge()
        runtime = AgentRuntime(
            tool_executor=executor,
            llm_planner=NoopPlanner(),
            memory_provider=memory,
            knowledge_provider=knowledge,
        )
        result = await runtime.chat(
            "综合分析2026年招生计划和生源情况",
            context=AgentContext(user_id=1, school_id=1, conversation_id=9),
            latest_year=2026,
        )
        self.assertEqual(memory.load_calls, 1)
        self.assertEqual(knowledge.calls, 1)
        self.assertEqual(result["memory_count"], 1)
        self.assertEqual(result["knowledge_count"], 1)
        self.assertEqual(memory.remembered[0]["conversation_id"], 9)


if __name__ == "__main__":
    unittest.main()





