from __future__ import annotations

import os
import unittest

from app.core.config import settings

LIVE_VECTOR_RAG_TESTS = os.environ.get("LIVE_VECTOR_RAG_TESTS") == "1"


@unittest.skipUnless(LIVE_VECTOR_RAG_TESTS, "set LIVE_VECTOR_RAG_TESTS=1 to run Chinese vector RAG tests")
class LiveVectorRagTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from app.core.database import AsyncSessionLocal

        settings.rag_vector_enabled = True
        self.db = AsyncSessionLocal()

    async def asyncTearDown(self):
        from app.core.database import engine
        await self.db.close()
        await engine.dispose()

    async def test_chinese_semantic_retrieval_returns_relevant_knowledge(self):
        from app.modules.rag.service import clear_knowledge_cache, search_knowledge

        clear_knowledge_cache()
        cases = {
            "新生到校比例怎么理解": ("报到",),
            "计划完成率怎么计算": ("计划完成率", "完成率"),
            "平行志愿投档规则": ("投档", "志愿"),
        }
        for query, expected_terms in cases.items():
            with self.subTest(query=query):
                rows = await search_knowledge(self.db, query=query, school_id=1, limit=3)
                self.assertTrue(rows, query)
                self.assertEqual(rows[0]["retrieval_mode"], "hybrid")
                self.assertGreater(rows[0]["score_details"]["vector"], 0.2)
                haystack = f"{rows[0]['title']} {rows[0]['content']}"
                self.assertTrue(any(term in haystack for term in expected_terms), haystack)


if __name__ == "__main__":
    unittest.main()
