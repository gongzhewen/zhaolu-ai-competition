import unittest

from agent_core.sql_guard import SQLGuardError, extract_sql, metrics_from_rows, validate_readonly_sql


ALLOWED = {"fact.plan", "fact.admission_summary", "dim.major", "analytics.mv_admissions_rollup"}


class SQLGuardTests(unittest.TestCase):
    def test_extract_json_sql(self):
        self.assertEqual(extract_sql('{"sql":"SELECT plan_count FROM fact.plan LIMIT 1"}'), "SELECT plan_count FROM fact.plan LIMIT 1")

    def test_json_fenced_sql_is_extracted(self):
        content = '```json\n{"sql":"SELECT plan_count FROM fact.plan LIMIT 1"}\n```'
        self.assertEqual(extract_sql(content), "SELECT plan_count FROM fact.plan LIMIT 1")

    def test_valid_select_gets_limit(self):
        sql = validate_readonly_sql("SELECT SUM(plan_count) AS plan_count FROM fact.plan", allowed_tables=ALLOWED, max_rows=20)
        self.assertTrue(sql.endswith("LIMIT 20"))

    def test_limit_is_capped(self):
        sql = validate_readonly_sql("SELECT SUM(plan_count) AS plan_count FROM fact.plan LIMIT 500", allowed_tables=ALLOWED, max_rows=20)
        self.assertIn("LIMIT 20", sql)

    def test_write_sql_is_rejected(self):
        for statement in (
            "DELETE FROM fact.plan",
            "SELECT plan_count FROM fact.plan; DROP TABLE fact.plan",
            "UPDATE fact.plan SET plan_count=0",
        ):
            with self.subTest(statement=statement):
                with self.assertRaises(SQLGuardError):
                    validate_readonly_sql(statement, allowed_tables=ALLOWED)

    def test_comment_and_sensitive_field_are_rejected(self):
        with self.assertRaises(SQLGuardError):
            validate_readonly_sql("SELECT plan_count FROM fact.plan -- bypass", allowed_tables=ALLOWED)
        with self.assertRaises(SQLGuardError):
            validate_readonly_sql("SELECT student_name FROM fact.plan", allowed_tables=ALLOWED)

    def test_non_whitelisted_table_is_rejected(self):
        with self.assertRaises(SQLGuardError):
            validate_readonly_sql("SELECT id FROM sys.user_account", allowed_tables=ALLOWED)

    def test_wildcard_is_rejected(self):
        with self.assertRaises(SQLGuardError):
            validate_readonly_sql("SELECT * FROM fact.plan", allowed_tables=ALLOWED)

    def test_metric_aliases_are_mapped(self):
        metrics = metrics_from_rows([{"total_plan": 100, "admitted": 98}], {"plan_count": 0, "admitted_count": 0})
        self.assertEqual(metrics["plan_count"], 100)
        self.assertEqual(metrics["admitted_count"], 98)


if __name__ == "__main__":
    unittest.main()
