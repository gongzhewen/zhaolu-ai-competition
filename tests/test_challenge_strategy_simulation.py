import json
import unittest
from pathlib import Path

from scripts.run_challenge_strategy_simulation import evaluate_cases


class ChallengeStrategySimulationTests(unittest.TestCase):
    def test_simulation_is_complete_and_fully_matched(self):
        path = Path("evaluation/challenge_set_v1.jsonl")
        cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        rows, summary = evaluate_cases(cases)
        self.assertEqual(summary["total"], 120)
        self.assertEqual(len(rows), 120)
        self.assertEqual(summary["strategy_matches"], 120)
        self.assertEqual(summary["strategy_match_rate"], 1.0)
        self.assertFalse(summary["end_to_end"])
        self.assertFalse(summary["gold_dataset"])


if __name__ == "__main__":
    unittest.main()
