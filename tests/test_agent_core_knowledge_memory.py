import unittest

from agent_core.knowledge import chunk_text, score_knowledge_items
from agent_core.memory import build_turn_memory_payloads, extract_explicit_preference, rank_memories


class KnowledgeAndMemoryTests(unittest.TestCase):
    def test_knowledge_retrieval_prefers_title_match(self):
        items = [
            {"document_id": 1, "chunk_id": 1, "title": "志愿热度计算口径", "document_type": "metric_definition", "content": "志愿热度比等于志愿次数除以计划数。"},
            {"document_id": 2, "chunk_id": 2, "title": "报到情况", "document_type": "dbf_data_dictionary", "content": "报到状态写入 enrollment_status。"},
        ]
        result = score_knowledge_items("志愿热度怎么算", items, limit=1)
        self.assertEqual(result[0]["document_id"], 1)
        self.assertGreater(result[0]["score"], 0)

    def test_chunk_text_keeps_content(self):
        chunks = chunk_text("第一段\n\n第二段\n\n第三段", max_chars=8)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertEqual("".join(chunks).replace("\n", ""), "第一段第二段第三段")

    def test_explicit_preference_and_turn_payloads(self):
        preference = extract_explicit_preference("以后优先分析风险")
        self.assertEqual(preference, "分析风险")
        payloads = build_turn_memory_payloads(
            user_id=1,
            school_id=2,
            conversation_id=3,
            question="以后优先分析风险",
            intent="anomaly_detection",
            answer="已记录。",
        )
        self.assertEqual([item["memory_type"] for item in payloads], ["episodic", "preference"])
        self.assertEqual(payloads[1]["summary"], "用户偏好：分析风险")

    def test_rank_memories_keeps_preferences(self):
        items = [
            {"id": 1, "memory_type": "preference", "summary": "用户偏好：优先分析风险", "confidence": 0.9, "importance": 0.8, "hit_count": 0},
            {"id": 2, "memory_type": "episodic", "summary": "普通摘要", "confidence": 0.4, "importance": 0.2, "hit_count": 0},
        ]
        result = rank_memories("分析风险", items)
        self.assertEqual(result[0]["id"], 1)


if __name__ == "__main__":
    unittest.main()
