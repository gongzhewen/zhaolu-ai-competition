from __future__ import annotations

import importlib.util
import os
import unittest
from unittest.mock import patch

from agent_core.contracts import RouteDecision
from app.core.config import Settings, settings
from app.modules.agent.providers import CompositePlanner
from app.modules.reports.service import _build_local_commentary


class LocalOnlyAITests(unittest.IsolatedAsyncioTestCase):
    def test_external_llm_client_module_is_removed(self):
        self.assertIsNone(importlib.util.find_spec("app.modules.ai_gateway.llm"))

    def test_legacy_external_llm_settings_are_ignored(self):
        values = {
            "LLM_PROVIDER": "deepseek",
            "LLM_BASE_URL": "https://api.example.invalid/v1",
            "LLM_API_KEY": "not-used",
            "LLM_MODEL": "not-used",
        }
        with patch.dict(os.environ, values, clear=False):
            loaded = Settings(_env_file=None)
        self.assertFalse(hasattr(loaded, "llm_provider"))
        self.assertFalse(hasattr(loaded, "llm_base_url"))
        self.assertFalse(hasattr(loaded, "llm_api_key"))
        self.assertFalse(hasattr(loaded, "llm_model"))

    async def test_planner_makes_no_http_request_without_local_model(self):
        previous = settings.minimind_enabled
        settings.minimind_enabled = False
        try:
            decision = RouteDecision(
                intent="admissions_overview",
                normalized_message="综合分析2026年招生计划",
                params={"year": 2026},
            )
            with patch("httpx.AsyncClient", side_effect=AssertionError("external HTTP is forbidden")):
                result = await CompositePlanner(object()).plan(decision, history=[])
            self.assertIsNone(result)
        finally:
            settings.minimind_enabled = previous

    def test_report_commentary_is_built_from_local_evidence(self):
        commentary = _build_local_commentary(
            {
                "insights": [
                    {
                        "title": "计划执行",
                        "finding": "计划 100 人，录取 96 人。",
                        "analysis": "完成率偏低。",
                        "suggestion": "核查专业计划与调剂情况。",
                    }
                ]
            }
        )
        self.assertIsNotNone(commentary)
        self.assertIn("计划执行", commentary)
        self.assertIn("核查专业计划与调剂情况", commentary)


if __name__ == "__main__":
    unittest.main()
