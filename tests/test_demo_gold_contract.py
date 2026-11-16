import json
import unittest
from pathlib import Path


class DemoGoldContractTests(unittest.TestCase):
    def test_demo_gold_shape_and_boundaries(self):
        root = Path(__file__).resolve().parents[1]
        cases = [
            json.loads(line)
            for line in (root / "evaluation/demo_gold_v1.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        meta = json.loads((root / "evaluation/demo_gold_v1.meta.json").read_text(encoding="utf-8"))
        self.assertEqual(len(cases), 121)
        self.assertEqual(meta["case_count"], 121)
        self.assertEqual(meta["answer_cases"], 115)
        self.assertEqual(meta["boundary_cases"], 6)
        self.assertTrue(meta["not_a_real_frozen_test_set"])
        self.assertFalse(meta["contains_student_details"])
        self.assertIn("data_profile", meta)
        self.assertGreater(meta["data_profile"]["dim_major"], 0)
        self.assertEqual(sum(1 for case in cases if case["expected_strategy"] == "answer"), 115)


if __name__ == "__main__":
    unittest.main()
