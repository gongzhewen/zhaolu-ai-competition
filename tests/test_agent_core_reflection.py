import unittest

from agent_core.reflection import (
    compile_reflection_guidance,
    compress_reflection_memories,
    infer_feedback_error_points,
    select_reflection_answer,
    validate_answer_with_reflection_guidance,
)


class ReflectionTests(unittest.TestCase):
    def test_feedback_error_inference_detects_missing_evidence(self):
        findings = infer_feedback_error_points(
            question="2025年湖南计算机专业录取数是多少",
            answer="数据支撑不足，为保证严谨性，暂不回答",
            reason="年份和数据可能不对",
            intent="student_statistics",
            tool_names=[],
        )
        codes = {item["code"] for item in findings}
        self.assertIn("missing_evidence", codes)
        self.assertIn("possible_false_refusal", codes)
        self.assertIn("condition_preservation", codes)

    def test_reflection_memories_compress_into_rules(self):
        memories = [
            {
                "memory_value": {
                    "error_points": [
                        {"code": "condition_preservation"},
                        {"code": "metric_omission"},
                    ]
                }
            },
            {
                "memory_value": {
                    "error_points": [
                        {"code": "condition_preservation"},
                    ]
                }
            },
        ]
        result = compress_reflection_memories(memories)
        self.assertEqual(result["source_count"], 2)
        self.assertIn("condition_preservation", result["error_codes"])
        self.assertTrue(result["rules"])

    def test_refined_answer_is_selected_only_when_supported(self):
        result = select_reflection_answer(
            original_answer="原回答",
            second_result={
                "answer": "复核后的回答",
                "risk_decision": {"strategy": "answer"},
                "data_support": {"status": "sufficient"},
                "numeric_verification": {"supported": True},
            },
        )
        self.assertEqual(result["mode"], "refined")
        self.assertEqual(result["answer"], "复核后的回答")

    def test_unsupported_second_answer_is_replaced_with_caution(self):
        result = select_reflection_answer(
            original_answer="原回答",
            second_result={
                "answer": "无依据回答",
                "risk_decision": {"strategy": "insufficient_data"},
                "data_support": {"status": "insufficient"},
                "numeric_verification": {"supported": False},
            },
        )
        self.assertEqual(result["mode"], "insufficient")
        self.assertIn("人工核对", result["answer"])

    def test_compressed_guidance_can_trigger_critical_check(self):
        guidance = compile_reflection_guidance(
            [
                {
                    "memory_type": "reflection_summary",
                    "memory_value": {
                        "error_codes": ["missing_evidence"],
                        "rules": ["数据类结论必须绑定至少一个受控工具证据。"],
                    },
                    "summary": "历史反馈修正",
                    "confidence": 0.9,
                }
            ]
        )
        validation = validate_answer_with_reflection_guidance(
            guidance=guidance,
            decision=type("Decision", (), {"params": {}})(),
            answer="数据支撑不足",
            tool_results=[],
            evidence=[],
            numeric_verification={"supported": True, "answer_number_count": 0},
        )
        self.assertTrue(validation["critical"])
        self.assertTrue(validation["warnings"])

    def test_reflection_checks_do_not_block_policy_answers(self):
        guidance = compile_reflection_guidance(
            [
                {
                    "memory_type": "reflection_summary",
                    "memory_value": {
                        "error_codes": ["metric_omission"],
                        "rules": ["答案必须覆盖指标。"],
                    },
                    "summary": "历史反馈修正",
                    "confidence": 0.9,
                }
            ]
        )
        validation = validate_answer_with_reflection_guidance(
            guidance=guidance,
            decision=type("Decision", (), {"params": {}, "intent": "policy_faq"})(),
            answer="平行志愿按照分数和位次投档。",
            tool_results=[{"answer": "政策说明"}],
            evidence=[],
            numeric_verification={"supported": True, "answer_number_count": 0},
        )
        self.assertFalse(validation["critical"])


if __name__ == "__main__":
    unittest.main()
