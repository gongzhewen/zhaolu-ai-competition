import unittest
from decimal import Decimal

from agent_core.contracts import SemanticSlots, ToolCall
from agent_core.verification import (
    build_evidence_certificates,
    build_plan_consistency,
    compare_plan_results,
    verify_numeric_claims,
)
from agent_core.contracts import PlanCandidate


class EvidenceCertificateTests(unittest.TestCase):
    def test_complete_certificate_preserves_traceable_fields(self):
        result = {
            "tool": "admissions_overview",
            "metrics": {"plan_count": 100, "completion_rate": 98.5},
            "data_sources": [{"table": "fact.plan", "metric": "招生计划"}],
        }
        certificates = build_evidence_certificates(
            [ToolCall("admissions_overview", {"year": 2025, "query": "不得泄露", "user": object()})],
            [result],
            slots=SemanticSlots(intent="admissions_overview", aggregation="sum_ratio"),
            permission_scope="school_scope",
        )
        certificate = certificates[0]
        self.assertEqual(certificate.year_range, (2025, 2025))
        self.assertEqual(certificate.data_source, ("fact.plan:招生计划",))
        self.assertEqual(certificate.permission_scope, "school_scope")
        self.assertNotIn("query", certificate.filters)
        self.assertNotIn("user", certificate.filters)
        self.assertEqual(certificate.completeness, 1.0)

    def test_student_lookup_certificate_requires_super_admin_scope(self):
        certificates = build_evidence_certificates(
            [ToolCall("student_lookup", {"student_name": "王同学", "year": 2025})],
            [{"tool": "student_lookup", "metrics": {"matched": 1}, "data_sources": [{"table": "fact.student_identity"}]}],
            permission_scope="school_scope",
        )
        self.assertEqual(certificates[0].permission_scope, "super_admin")

    def test_numeric_claims_support_year_and_rounded_percentage(self):
        result = verify_numeric_claims(
            "2025年招生计划100人，计划完成率98.5%。",
            [
                {
                    "metrics": {"plan_count": 100, "completion_rate": 98.45},
                    "tool_params": {"year": 2025},
                }
            ],
        )
        self.assertTrue(result["supported"])
        self.assertEqual(result["coverage"], 1.0)
        self.assertEqual(result["unsupported_numbers"], [])

    def test_unmentioned_number_is_rejected(self):
        result = verify_numeric_claims(
            "2025年招生计划120人。",
            [{"metrics": {"plan_count": 100}, "tool_params": {"year": 2025}}],
        )
        self.assertFalse(result["supported"])
        self.assertEqual(Decimal(result["unsupported_numbers"][0]), Decimal("120"))

    def test_table_order_does_not_change_plan_consistency(self):
        primary = [{
            "tool": "admissions_overview",
            "metrics": {"plan_count": 100},
            "table": {"columns": ["专业", "人数"], "rows": [["A", 10], ["B", 20]]},
            "data_sources": [{"table": "fact.plan", "metric": "招生计划"}],
        }]
        secondary = [{
            "tool": "admissions_overview",
            "metrics": {"plan_count": 100.0},
            "table": {"columns": ["专业", "人数"], "rows": [["B", 20.0], ["A", 10.0]]},
            "data_sources": [{"table": "fact.plan", "metric": "招生计划"}],
        }]
        consistent, score, _ = compare_plan_results(primary, secondary)
        self.assertTrue(consistent)
        self.assertEqual(score, 1.0)

        consistency = build_plan_consistency(
            PlanCandidate("model", [ToolCall("admissions_overview")], "local_model"),
            PlanCandidate("rule", [ToolCall("admissions_overview", {"mode": "rule"})], "rule"),
            primary_results=primary,
            secondary_results=secondary,
            triggered=True,
        )
        self.assertTrue(consistency.consistent)
        self.assertEqual(consistency.score, 1.0)


if __name__ == "__main__":
    unittest.main()
