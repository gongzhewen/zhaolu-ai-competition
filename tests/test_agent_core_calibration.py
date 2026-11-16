import unittest

from agent_core.calibration import CalibrationSample, calibrate_threshold, evaluate_threshold


class CalibrationTests(unittest.TestCase):
    def test_separable_scores_select_centered_threshold(self):
        samples = [
            CalibrationSample(0.02, True),
            CalibrationSample(0.05, True),
            CalibrationSample(0.70, False),
            CalibrationSample(0.90, False),
        ]
        result = calibrate_threshold(samples, preferred_threshold=0.32)
        self.assertGreater(result.threshold, 0.05)
        self.assertLess(result.threshold, 0.70)
        self.assertEqual(result.selected.cost, 0.0)
        self.assertEqual(result.selected.balanced_accuracy, 1.0)
        self.assertEqual(result.preferred.cost, 0.0)

    def test_false_answer_costs_more_than_false_refusal(self):
        samples = [
            CalibrationSample(0.20, True),
            CalibrationSample(0.40, False),
        ]
        low = evaluate_threshold(samples, 0.10)
        high = evaluate_threshold(samples, 0.50)
        self.assertGreater(high.cost, low.cost)
        self.assertEqual(low.false_negative, 1)
        self.assertEqual(high.false_positive, 1)

    def test_empty_samples_keep_preferred_threshold(self):
        result = calibrate_threshold([], preferred_threshold=0.32)
        self.assertEqual(result.threshold, 0.32)
        self.assertEqual(result.sample_count, 0)


if __name__ == "__main__":
    unittest.main()
