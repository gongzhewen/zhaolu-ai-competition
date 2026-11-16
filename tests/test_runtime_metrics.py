import unittest
from unittest.mock import AsyncMock, patch

from app.core.runtime_metrics import (
    metrics_snapshot,
    record_chat_metric,
    record_llm_metric,
    reset_runtime_metrics,
)


class RuntimeMetricsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        reset_runtime_metrics()
        self.redis_patch = patch(
            "app.core.runtime_metrics.get_redis_client",
            new=AsyncMock(return_value=None),
        )
        self.redis_patch.start()

    async def asyncTearDown(self):
        self.redis_patch.stop()
        reset_runtime_metrics()

    async def test_snapshot_reports_latency_cache_planning_and_llm_rates(self):
        await record_chat_metric(
            duration_ms=10,
            route_mode="fast",
            cache_layers=["l1"],
            tool_count=1,
            strategy="answer",
        )
        await record_chat_metric(
            duration_ms=30,
            route_mode="model",
            cache_layers=["miss"],
            tool_count=2,
            multi_planning_triggered=True,
            strategy="clarify",
        )
        await record_llm_metric(kind="minimind", status="success", duration_ms=20)
        await record_llm_metric(kind="minimind", status="timeout", duration_ms=2500)
        snapshot = await metrics_snapshot()
        self.assertEqual(snapshot["source"], "memory")
        self.assertEqual(snapshot["sample_count"], 2)
        self.assertEqual(snapshot["latency_ms"]["p50"], 10)
        self.assertEqual(snapshot["latency_ms"]["p95"], 30)
        self.assertEqual(snapshot["rates"]["fast_route_rate"], 0.5)
        self.assertEqual(snapshot["rates"]["cache_hit_rate"], 0.5)
        self.assertEqual(snapshot["rates"]["dual_planning_trigger_rate"], 0.5)
        self.assertEqual(snapshot["rates"]["llm_timeout_rate"], 0.5)
        self.assertEqual(snapshot["rates"]["answer_rate"], 0.5)
        self.assertEqual(snapshot["rates"]["clarification_rate"], 0.5)
        self.assertTrue(snapshot["formal_constraints"]["p95_within_budget"])
        self.assertEqual(snapshot["formal_constraints"]["p95_latency_budget_ms"], 2000.0)


if __name__ == "__main__":
    unittest.main()
