import unittest
from agent_core.router import RuleRouter

class ProvinceAliasTests(unittest.TestCase):
    def test_province_alias_resolved_to_known_name(self):
        decision = RuleRouter().route(
            '2025年湘招生多少人',
            known_provinces=('湖南', '广东'),
            latest_year=2026,
        )
        self.assertEqual(decision.intent, 'admissions_overview')
        self.assertEqual(decision.params.get('province'), '湖南')

if __name__ == '__main__':
    unittest.main()
