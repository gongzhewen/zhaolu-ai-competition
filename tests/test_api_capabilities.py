import unittest

from app.main import app
from app.modules.agent.schemas import ChatResponse
from fastapi.testclient import TestClient


class ApiCapabilitiesTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health(self):
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_chat_response_preserves_governance_fields(self):
        payload = ChatResponse(
            intent="admissions_overview",
            answer="ok",
            risk_decision={"strategy": "answer", "features": {"ambiguity": 0.0}},
            evidence_certificates=[{"tool_name": "admissions_overview"}],
            plan_consistency={"triggered": False, "consistent": True},
            algorithm_version="ECSP-Admissions-G1.2",
        ).model_dump()
        self.assertEqual(payload["risk_decision"]["strategy"], "answer")
        self.assertEqual(payload["evidence_certificates"][0]["tool_name"], "admissions_overview")
        self.assertTrue(payload["plan_consistency"]["consistent"])
        self.assertEqual(payload["algorithm_version"], "ECSP-Admissions-G1.2")

    def test_agent_capabilities_exposes_eighteen_tools(self):
        response = self.client.get("/api/v1/agent/capabilities")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["runtime"], "agent_core_v2")
        self.assertEqual(payload["algorithm_version"], "ECSP-Admissions-G1.2")
        self.assertEqual(payload["tool_count"], 18)
        self.assertEqual(len(payload["tools"]), 18)
        self.assertTrue(payload["reasoning"]["ml_intent_router"])
        self.assertTrue(payload["performance"]["rag_vector_enabled"])
        self.assertTrue(payload["reasoning"]["mandatory_self_check"])
        self.assertTrue(payload["reasoning"]["long_term_memory"])
        self.assertEqual(payload["observability"]["metrics_endpoint"], "/api/v1/agent/metrics")
        self.assertIn("cache_hit_rate", payload["observability"]["tracks"])


if __name__ == "__main__":
    unittest.main()
