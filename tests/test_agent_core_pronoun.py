import unittest
from agent_core.router import RuleRouter

class PronounClarifyTests(unittest.TestCase):
    def setUp(self):
        self.router = RuleRouter()

    def test_pronoun_student_query_asks_for_name(self):
        decision = self.router.route("查一下他的成绩", latest_year=2026)
        self.assertEqual(decision.intent, "student_lookup")
        self.assertIsNotNone(decision.clarification)

if __name__ == "__main__":
    unittest.main()
