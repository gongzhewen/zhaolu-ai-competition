import unittest

from scripts.analyze_paired_significance import (
    classify_errors,
    mcnemar_exact,
    pair_summary,
    paired_bootstrap_delta,
)


def row(
    *,
    correct: bool,
    expected_strategy: str = "answer",
    answered: bool = True,
) -> dict:
    return {
        "case_id": "case",
        "expected_strategy": expected_strategy,
        "predicted_strategy": "answer" if answered else "clarify",
        "answered": answered,
        "correct": correct,
        "strategy_match": (expected_strategy == "answer") == answered,
        "expected_tool": "admissions_statistics",
        "tool_match": correct,
        "params_match": correct,
        "metrics_match": correct,
        "intent_match": correct,
        "error": None,
    }


class PairedSignificanceTests(unittest.TestCase):
    def test_mcnemar_exact_known_value(self):
        self.assertAlmostEqual(mcnemar_exact(5, 0), 0.0625)
        self.assertEqual(mcnemar_exact(0, 0), 1.0)

    def test_pair_summary_aligns_cases(self):
        first = {
            "a": {**row(correct=True), "case_id": "a"},
            "b": {**row(correct=False), "case_id": "b"},
            "c": {**row(correct=True), "case_id": "c"},
        }
        second = {
            "a": {**row(correct=True), "case_id": "a"},
            "b": {**row(correct=True), "case_id": "b"},
            "c": {**row(correct=False), "case_id": "c"},
        }
        summary = pair_summary("first", "second", first, second)
        self.assertEqual(summary["paired_cases"], 3)
        self.assertEqual(summary["only_first_correct"], 1)
        self.assertEqual(summary["only_second_correct"], 1)
        self.assertAlmostEqual(summary["mcnemar_exact_p"], 1.0)

    def test_bootstrap_interval_contains_zero_for_identical_methods(self):
        outcomes = [(1, 1), (0, 0), (1, 1), (0, 0)]
        self.assertEqual(paired_bootstrap_delta(outcomes, rounds=200), [0.0, 0.0])

    def test_error_classification_is_multi_label(self):
        result = classify_errors(
            {
                **row(correct=False, expected_strategy="no_permission", answered=True),
                "strategy_match": False,
                "metrics_match": False,
                "tool_match": False,
                "params_match": False,
                "intent_match": False,
            }
        )
        self.assertIn("privacy_violation", result)
        self.assertIn("unsafe_answer", result)
        self.assertIn("strategy_mismatch", result)
        self.assertIn("metric_mismatch", result)


if __name__ == "__main__":
    unittest.main()
