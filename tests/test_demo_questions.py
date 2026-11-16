from __future__ import annotations

import unittest

from app.modules.agent.demo_catalog import DEMO_QUESTIONS
from app.modules.ai_gateway.faq import search_faq


class DemoQuestionTests(unittest.TestCase):
    def test_demo_catalog_has_eight_questions(self):
        self.assertEqual(len(DEMO_QUESTIONS), 8)

    def test_new_arrival_ratio_uses_curated_answer(self):
        item = search_faq("新生到校比例怎么理解？")
        self.assertIsNotNone(item)
        self.assertEqual(item.faq_id, "new-arrival-ratio")
        self.assertIn("报到人数", item.answer)
        self.assertIn("录取人数", item.answer)
        self.assertNotIn("专业名称", item.answer)


if __name__ == "__main__":
    unittest.main()