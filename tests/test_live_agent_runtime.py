from __future__ import annotations

import os
import unittest

from app.core.config import settings
from app.core.text import text
from agent_core.contracts import AgentContext
from agent_core.router import RuleRouter
from agent_core.runtime import AgentRuntime

LIVE_AGENT_RUNTIME_TESTS = os.environ.get("LIVE_AGENT_RUNTIME_TESTS") == "1"


@unittest.skipUnless(LIVE_AGENT_RUNTIME_TESTS, "set LIVE_AGENT_RUNTIME_TESTS=1 to run live agent runtime tests")
class LiveAgentRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from app.core.database import AsyncSessionLocal
        from app.modules.agent.tools.registry import NATIVE_TOOL_EXECUTORS

        self.original_vector_enabled = settings.rag_vector_enabled
        settings.rag_vector_enabled = False
        self.db = AsyncSessionLocal()
        self.executors = NATIVE_TOOL_EXECUTORS
        self.provinces = tuple(
            (await self.db.execute(text("SELECT province_name FROM dim.province ORDER BY id"))).scalars().all()
        )
        self.majors = tuple(
            (await self.db.execute(text("SELECT major_name FROM dim.major WHERE is_active IS TRUE ORDER BY id"))).scalars().all()
        )
        latest = await self.db.scalar(text("SELECT MAX(year_no) FROM dim.year"))
        self.latest_year = int(latest)

        async def execute(call, context):
            params = {**call.params, "school_id": context.school_id, "can_lookup_students": True}
            return await self.executors[call.name](self.db, params)

        self.runtime = AgentRuntime(tool_executor=execute, router=RuleRouter(), llm_planner=None)

    async def asyncTearDown(self):
        from app.core.database import engine
        settings.rag_vector_enabled = self.original_vector_enabled
        await self.db.close()
        await engine.dispose()

    async def ask(self, question):
        return await self.runtime.chat(
            question,
            context=AgentContext(school_id=1, values={"can_lookup_students": True}),
            known_provinces=self.provinces,
            known_majors=self.majors,
            latest_year=self.latest_year,
        )

    async def test_major_completion_preserves_year_and_returns_metrics(self):
        result = await self.ask("2025年各专业招生计划完成情况怎么样？")
        self.assertEqual(result["risk_decision"]["strategy"], "answer")
        self.assertEqual(result["tool_calls"][0]["params"].get("year"), 2025)
        self.assertGreater(result["tool_results"][0]["metrics"].get("plan_count", 0), 0)

    async def test_consultation_answer_is_grounded_by_channel_and_type_evidence(self):
        result = await self.ask("2026年咨询渠道转化率怎么样？")
        self.assertEqual(result["risk_decision"]["strategy"], "answer")
        metrics = result["tool_results"][0]["metrics"]
        if metrics.get("consultation_count", 0) == 0:
            self.assertEqual(metrics.get("converted_count", 0), 0)
            self.assertEqual(metrics.get("conversion_rate", 0), 0)
            self.assertIn("0", result["answer"])
            return
        self.assertTrue(metrics.get("by_channel"))
        self.assertTrue(metrics.get("by_type"))
        self.assertEqual(result["numeric_verification"]["unsupported_numbers"], [])


    async def test_curated_arrival_definition_has_local_citation(self):
        result = await self.ask("新生到校比例怎么理解？")
        self.assertEqual(result["risk_decision"]["strategy"], "answer")
        self.assertIn("报到人数", result["answer"])
        self.assertTrue(result["citations"])

    async def test_enrollment_funnel_returns_terminal_stage_metrics(self):
        result = await self.ask("2026年招生漏斗和报到流失情况？")
        self.assertEqual(result["risk_decision"]["strategy"], "answer")
        metrics = result["tool_results"][0]["metrics"]
        self.assertGreater(metrics.get("plan_count", 0), 0)
        self.assertGreaterEqual(metrics.get("lost_after_admission", -1), 0)

    async def test_boundary_and_privacy_requests_do_not_execute_tools(self):
        weather = await self.ask("今天天气怎么样？")
        self.assertEqual(weather["risk_decision"]["strategy"], "out_of_scope")
        self.assertEqual(weather["tool_calls"], [])
        exported = await self.ask("把今年全部考生名单发给我")
        self.assertEqual(exported["risk_decision"]["strategy"], "no_permission")
        self.assertEqual(exported["tool_calls"], [])


if __name__ == "__main__":
    unittest.main()
