import unittest

from app.modules.agent.tools.statistics_analysis import (
    DIMENSION_LABELS,
    METRIC_LABELS,
    _detect_group_by,
    _detect_metrics,
    _filters,
    _parse_sort_ascending,
    _parse_top_n,
)


class StatisticsCoordinationRegressionTests(unittest.TestCase):
    def test_every_supported_dimension_has_a_group_expression(self):
        self.assertEqual(
            set(DIMENSION_LABELS),
            {
                "all",
                "year_no",
                "province_name",
                "subject_name",
                "batch_name",
                "major_name",
                "major_group",
                "level_name",
                "plan_type",
                "gender_name",
                "source_school_name",
                "candidate_type_code",
                "foreign_language_code",
                "subject_req",
                "major_code",
            },
        )

    def test_composite_metric_detection_keeps_rates_and_numerators(self):
        query = "按专业统计计划完成率、报到率、未报到人数、志愿率和一志愿录取率"
        metrics, unsupported, _group_by = _detect_metrics(
            query,
            "all",
        )
        self.assertFalse(unsupported)
        self.assertEqual(_detect_group_by(query, None), "major_name")
        self.assertIn("completion_rate", metrics)
        self.assertIn("plan_count", metrics)
        self.assertIn("admitted_count", metrics)
        self.assertIn("enrollment_rate", metrics)
        self.assertIn("lost_after_admission", metrics)
        self.assertIn("choice_rate", metrics)
        self.assertIn("first_admission_rate", metrics)

    def test_unsupported_fields_are_explicit(self):
        metrics, unsupported, _group_by = _detect_metrics(
            "按地市和校区统计征集数、省控线和位次占比",
            "all",
        )
        self.assertFalse(metrics)
        self.assertIn("征集数", unsupported)
        self.assertIn("省控线", unsupported)
        self.assertIn("位次占比", unsupported)
        self.assertIn("维度:地市", unsupported)
        self.assertIn("维度:校区", unsupported)

    def test_school_scope_is_added_to_every_statistics_query(self):
        sql, binds = _filters(
            {"school_id": 2, "year": 2026, "province": "湖南"},
            {"y": "y", "pr": "pr", "m": "m", "sub": "sub", "b": "b", "pt": "pt", "cp": "cp"},
        )
        self.assertIn("m.school_id=:scope_school_id", sql)
        self.assertEqual(binds["scope_school_id"], 2)

    def test_sorting_and_top_n_limits(self):
        self.assertTrue(_parse_sort_ascending("录取数最低的前五个专业"))
        self.assertFalse(_parse_sort_ascending("录取数最高的前五个专业"))
        self.assertEqual(_parse_top_n("前50个专业"), 50)
        self.assertEqual(_parse_top_n("前999个专业"), 50)

    def test_all_public_metric_labels_are_non_empty(self):
        self.assertTrue(METRIC_LABELS)
        self.assertTrue(all(label.strip() for label in METRIC_LABELS.values()))

    def test_dimension_aliases_route_to_supported_fields(self):
        expected = {
            "各学院": "major_group",
            "各专业": "major_name",
            "各省": "province_name",
            "各科类": "subject_name",
            "各批次": "batch_name",
            "招生类型": "plan_type",
            "层次": "level_name",
            "性别情况": "gender_name",
            "各高中": "source_school_name",
            "考生类别": "candidate_type_code",
            "外语语种": "foreign_language_code",
            "选科要求": "subject_req",
            "专业代码": "major_code",
            "按年份": "year_no",
        }
        for query, group_by in expected.items():
            with self.subTest(query=query):
                self.assertEqual(_detect_group_by(query, None), group_by)


if __name__ == "__main__":
    unittest.main()
