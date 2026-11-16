from __future__ import annotations

import time
import unittest
from unittest.mock import patch

import app.modules.rag.service as rag_service
from app.core.config import settings
from app.modules.rag.vector import combine_hybrid_scores, cosine_similarity, normalize_vector


class FakeProvider:
    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            if "报到" in text or "到校" in text:
                vectors.append([1.0, 0.0, 0.0])
            elif "计划" in text or "招生" in text:
                vectors.append([0.0, 1.0, 0.0])
            else:
                vectors.append([0.0, 0.0, 1.0])
        return vectors


class FakeResult:
    def __init__(self, items: list[dict]) -> None:
        self.items = items

    def mappings(self):
        return self

    def all(self):
        return self.items


class FakeDB:
    def __init__(self, items: list[dict]) -> None:
        self.items = items

    async def execute(self, *_args, **_kwargs):
        return FakeResult(self.items)


class VectorMathTests(unittest.TestCase):
    def test_normalize_and_cosine(self):
        left = normalize_vector([3.0, 4.0])
        right = normalize_vector([3.0, 4.0])
        self.assertAlmostEqual(cosine_similarity(left, right), 1.0)

    def test_hybrid_score_uses_both_signals(self):
        scores = combine_hybrid_scores([4.0, 0.0], [0.2, 0.9], vector_weight=0.5)
        self.assertGreater(scores[0], 0.0)
        self.assertGreater(scores[1], 0.0)
        self.assertNotEqual(scores[0], scores[1])


class HybridRetrievalTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        rag_service.clear_knowledge_cache()
        rag_service._VECTOR_PROVIDER = FakeProvider()
        rag_service._VECTOR_PROVIDER_UNAVAILABLE = False
        self.original_enabled = settings.rag_vector_enabled
        self.original_timeout = settings.rag_embedding_timeout_seconds
        settings.rag_vector_enabled = True

    def tearDown(self):
        settings.rag_vector_enabled = self.original_enabled
        settings.rag_embedding_timeout_seconds = self.original_timeout
        rag_service._VECTOR_PROVIDER = None
        rag_service._VECTOR_PROVIDER_UNAVAILABLE = False
        rag_service.clear_knowledge_cache()

    async def test_vector_recall_finds_semantic_match_without_lexical_overlap(self):
        items = [
            {
                "document_id": 1,
                "chunk_id": 11,
                "title": "报到率口径",
                "document_type": "metric_definition",
                "content": "已报到人数除以录取人数。",
                "source_url": None,
                "tags": [],
                "school_id": None,
                "metadata": {},
            },
            {
                "document_id": 2,
                "chunk_id": 22,
                "title": "招生计划口径",
                "document_type": "metric_definition",
                "content": "年度计划人数。",
                "source_url": None,
                "tags": [],
                "school_id": None,
                "metadata": {},
            },
        ]
        result = await rag_service.search_knowledge(
            FakeDB(items),
            query="新生到校比例",
            limit=1,
        )
        self.assertEqual(result[0]["document_id"], 1)
        self.assertEqual(result[0]["retrieval_mode"], "hybrid")
        self.assertGreater(result[0]["score_details"]["vector"], 0.9)

    async def test_provider_timeout_falls_back_to_lexical(self):
        class SlowProvider:
            def embed(self, _texts):
                time.sleep(0.2)
                return [[1.0, 0.0]]

        rag_service._VECTOR_PROVIDER = SlowProvider()
        settings.rag_embedding_timeout_seconds = 0.01
        items = [
            {
                "document_id": 4,
                "chunk_id": 44,
                "title": "招生计划",
                "document_type": "metric_definition",
                "content": "招生计划来自数据库。",
                "source_url": None,
                "tags": [],
                "school_id": None,
                "metadata": {},
            }
        ]
        with patch.object(rag_service._LOGGER, "warning"):
            result = await rag_service.search_knowledge(FakeDB(items), query="招生计划", limit=1)
        self.assertEqual(result[0]["retrieval_mode"], "lexical")
        self.assertTrue(rag_service._VECTOR_PROVIDER_UNAVAILABLE)
    async def test_provider_failure_falls_back_to_lexical(self):
        class BrokenProvider:
            def embed(self, _texts):
                raise RuntimeError("model unavailable")

        rag_service._VECTOR_PROVIDER = BrokenProvider()
        items = [
            {
                "document_id": 3,
                "chunk_id": 33,
                "title": "招生计划",
                "document_type": "metric_definition",
                "content": "招生计划来自数据库。",
                "source_url": None,
                "tags": [],
                "school_id": None,
                "metadata": {},
            }
        ]
        with patch.object(rag_service._LOGGER, "warning"):
            result = await rag_service.search_knowledge(FakeDB(items), query="招生计划", limit=1)
        self.assertEqual(result[0]["retrieval_mode"], "lexical")
        self.assertTrue(rag_service._VECTOR_PROVIDER_UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
