import unittest

from agent_core.verification import verify_numeric_claims


class NumericClaimTests(unittest.TestCase):
    def test_answer_without_numbers_is_supported(self):
        result = verify_numeric_claims("暂未检索到足够的政策依据。", [{"metrics": {}}])
        self.assertTrue(result["supported"])
        self.assertEqual(result["coverage"], 1.0)
        self.assertEqual(result["answer_number_count"], 0)

    def test_decimal_trailing_zero_matches_evidence(self):
        result = verify_numeric_claims(
            "报到率为80.0%。",
            [{"metrics": {"enrollment_rate": 80}}],
        )
        self.assertTrue(result["supported"])

    def test_two_unsupported_numbers_reduce_coverage(self):
        result = verify_numeric_claims(
            "计划100人，实际120人。",
            [{"metrics": {"plan_count": 100}}],
        )
        self.assertEqual(result["answer_number_count"], 2)
        self.assertEqual(result["coverage"], 0.5)
        self.assertFalse(result["supported"])


if __name__ == "__main__":
    unittest.main()
