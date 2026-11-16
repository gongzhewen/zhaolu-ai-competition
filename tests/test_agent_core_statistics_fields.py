import unittest

from app.modules.agent.tools.statistics_analysis import (
    UNSUPPORTED_DIMENSIONS,
    _detect_group_by,
)


class StatisticsFieldTests(unittest.TestCase):
    def test_supported_dimension_mappings(self):
        self.assertEqual(_detect_group_by('按考生类别统计录取数', None), 'candidate_type_code')
        self.assertEqual(_detect_group_by('按外语语种统计人数', None), 'foreign_language_code')
        self.assertEqual(_detect_group_by('按选科要求统计计划数', None), 'subject_req')
        self.assertEqual(_detect_group_by('按专业代码统计计划数', None), 'major_code')

    def test_unmapped_dimensions_stay_unsupported(self):
        self.assertIn('地市', UNSUPPORTED_DIMENSIONS)
        self.assertIn('区县', UNSUPPORTED_DIMENSIONS)
        self.assertIn('校区', UNSUPPORTED_DIMENSIONS)
        self.assertIn('政治面貌', UNSUPPORTED_DIMENSIONS)
        self.assertNotIn('考生类别', UNSUPPORTED_DIMENSIONS)
        self.assertNotIn('选科要求', UNSUPPORTED_DIMENSIONS)


if __name__ == '__main__':
    unittest.main()
