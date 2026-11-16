import unittest
from decimal import Decimal

from agent_core.text_to_sql import LocalTextToSqlClient, TextToSqlUnavailable
from scripts.run_text_to_sql_baseline import metrics_match


class TextToSqlBaselineTests(unittest.IsolatedAsyncioTestCase):
    def test_metric_match_normalizes_decimal_and_float(self):
        self.assertTrue(metrics_match({"completion_rate": 99.05}, {"completion_rate": Decimal("99.05")}))

    def test_metric_match_rejects_wrong_value(self):
        self.assertFalse(metrics_match({"plan_count": 100}, {"plan_count": 99}))

    async def test_unconfigured_client_is_unavailable(self):
        client = LocalTextToSqlClient(enabled=False, base_url="", model_name="")
        with self.assertRaises(TextToSqlUnavailable):
            await client.generate_sql("2026年招生计划", {"plan_count": 0})


if __name__ == "__main__":
    unittest.main()
