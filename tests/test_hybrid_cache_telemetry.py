import unittest
from unittest.mock import AsyncMock, patch

from agent_core.contracts import AgentContext, ToolCall
from app.modules.agent.hybrid_adapter import HybridToolExecutor, clear_hybrid_tool_cache


class FakeUser:
    id = 1


class HybridCacheTelemetryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        clear_hybrid_tool_cache()
        self.calls = 0

        async def fake_tool(db, params):
            self.calls += 1
            return {
                "answer": "ok",
                "metrics": {"plan_count": 100},
                "data_sources": [{"table": "fact.plan"}],
                "charts": [],
                "table": None,
            }

        self.executors = {
            "admissions_overview": fake_tool,
            "student_statistics": fake_tool,
        }
        self.executors_patch = patch(
            "app.modules.agent.hybrid_adapter.NATIVE_TOOL_EXECUTORS",
            self.executors,
        )
        self.permission_patch = patch(
            "app.modules.agent.hybrid_adapter.is_super_admin",
            return_value=True,
        )
        self.shared_get_patch = patch(
            "app.modules.agent.hybrid_adapter.shared_get_json",
            AsyncMock(return_value=None),
        )
        self.shared_set_patch = patch(
            "app.modules.agent.hybrid_adapter.shared_set_json",
            AsyncMock(return_value=True),
        )
        self.executors_patch.start()
        self.permission_patch.start()
        self.shared_get = self.shared_get_patch.start()
        self.shared_set = self.shared_set_patch.start()

    async def asyncTearDown(self):
        self.shared_set_patch.stop()
        self.shared_get_patch.stop()
        self.permission_patch.stop()
        self.executors_patch.stop()
        clear_hybrid_tool_cache()

    async def test_cache_miss_then_hit_is_reported_without_leaking_internal_layer(self):
        executor = HybridToolExecutor(None, user=FakeUser())
        context = AgentContext(school_id=1)
        call = ToolCall("admissions_overview", {"year": 2026})
        first = await executor(call, context)
        second = await executor(call, context)
        self.assertEqual(self.calls, 1)
        self.assertFalse(first["cache_hit"])
        self.assertEqual(first["_cache_layer"], "miss")
        self.assertTrue(second["cache_hit"])
        self.assertEqual(second["_cache_layer"], "l1")
        self.assertNotIn("_cache_layer", second["metrics"])
        self.assertEqual(self.shared_get.await_count, 1)
        self.assertEqual(self.shared_set.await_count, 1)

    async def test_shared_redis_hit_is_reported_as_l2_and_warmed_into_l1(self):
        self.shared_get.return_value = {
            "answer": "shared",
            "metrics": {"plan_count": 100},
            "data_sources": [],
            "charts": [],
            "table": None,
        }
        executor = HybridToolExecutor(None, user=FakeUser())
        context = AgentContext(school_id=2)
        call = ToolCall("admissions_overview", {"year": 2026})
        first = await executor(call, context)
        second = await executor(call, context)
        self.assertEqual(self.calls, 0)
        self.assertEqual(first["_cache_layer"], "l2")
        self.assertEqual(second["_cache_layer"], "l1")
        self.assertEqual(first["answer"], "shared")
        self.assertEqual(self.shared_set.await_count, 0)

    async def test_shared_cache_is_school_scoped(self):
        executor = HybridToolExecutor(None, user=FakeUser())
        call = ToolCall("admissions_overview", {"year": 2026})
        await executor(call, AgentContext(school_id=1))
        await executor(call, AgentContext(school_id=2))
        school_ids = [item.kwargs["school_id"] for item in self.shared_set.await_args_list]
        self.assertEqual(school_ids, [1, 2])

    async def test_private_statistics_are_never_cached(self):
        executor = HybridToolExecutor(None, user=FakeUser())
        context = AgentContext(school_id=1)
        call = ToolCall("student_statistics", {"year": 2026, "surname": "王"})
        await executor(call, context)
        result = await executor(call, context)
        self.assertEqual(self.calls, 2)
        self.assertEqual(result["_cache_layer"], "bypass")


if __name__ == "__main__":
    unittest.main()
