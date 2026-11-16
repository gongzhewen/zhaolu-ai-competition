import unittest

from agent_core.context import resolve_follow_up_question


class ContextResolutionTests(unittest.TestCase):
    def test_pronoun_question_reuses_previous_question(self):
        resolved, meta = resolve_follow_up_question(
            "他的成绩是多少",
            [
                {"role": "user", "content": "分析2026年录取的王小明"},
                {"role": "assistant", "content": "已找到该学生。"},
            ],
        )
        self.assertTrue(meta["used"])
        self.assertIn("王小明", resolved)
        self.assertIn("他的成绩", resolved)

    def test_independent_question_is_not_merged(self):
        resolved, meta = resolve_follow_up_question(
            "2025年各省招生计划是多少",
            [{"role": "user", "content": "2024年招生计划是多少"}],
        )
        self.assertFalse(meta["used"])
        self.assertEqual(resolved, "2025年各省招生计划是多少")

    def test_history_is_bounded_and_normalized(self):
        resolved, meta = resolve_follow_up_question(
            "那这个专业呢",
            [
                {"role": "user", "content": "分析人工智能专业"},
                {"role": "assistant", "content": "已完成。"},
                {"role": "invalid", "content": "忽略"},
            ],
        )
        self.assertTrue(meta["used"])
        self.assertIn("人工智能专业", resolved)


if __name__ == "__main__":
    unittest.main()
