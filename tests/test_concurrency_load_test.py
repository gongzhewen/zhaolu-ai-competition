import unittest

from scripts.run_concurrency_load_test import build_plan, percentile, summarize_rows


class ConcurrencyLoadTestHelpers(unittest.TestCase):
    def test_plan_covers_all_scenarios(self):
        plan = build_plan(60)
        self.assertEqual(len(plan), 60)
        self.assertEqual(
            {item["scenario"] for item in plan},
            {"cached_plan", "simple_plan", "anomaly_scan", "out_of_scope", "privacy_refusal"},
        )

    def test_percentile_and_summary(self):
        self.assertEqual(percentile([10, 20, 30, 40], 0.95), 40)
        rows = [
            {"scenario": "cached_plan", "http_status": 200, "latency_ms": 10, "strategy": "answer", "strategy_correct": True},
            {"scenario": "cached_plan", "http_status": 200, "latency_ms": 30, "strategy": "answer", "strategy_correct": True},
            {"scenario": "out_of_scope", "http_status": 500, "latency_ms": 50, "strategy": "", "strategy_correct": False},
        ]
        summary = summarize_rows(rows, 1.5)
        self.assertEqual(summary["requests"], 3)
        self.assertEqual(summary["successful_requests"], 2)
        self.assertEqual(summary["success_rate"], 0.6667)
        self.assertEqual(summary["latency_ms"]["p50"], 10)
        self.assertEqual(summary["latency_ms"]["p95"], 30)


if __name__ == "__main__":
    unittest.main()
