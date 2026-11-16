import unittest

from agent_core.router import RuleRouter


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.router = RuleRouter()

    def test_province_admissions_question(self):
        decision = self.router.route(
            "2025年湖南招生多少人",
            known_provinces=("湖南", "湖北"),
            latest_year=2026,
        )
        self.assertEqual(decision.intent, "admissions_overview")
        self.assertEqual(decision.params["year"], 2025)
        self.assertEqual(decision.params["province"], "湖南")

    def test_major_extraction_prefers_longest_match(self):
        decision = self.router.route(
            "2025年电气工程及其自动化专业招生计划完成情况怎么样",
            known_majors=("自动化", "电气工程及其自动化"),
            latest_year=2026,
        )
        self.assertEqual(decision.params["major"], "电气工程及其自动化")

    def test_current_year_major_question(self):
        decision = self.router.route(
            "计算机科学与技术专业今年招生多少人",
            known_majors=("计算机科学与技术", "软件工程"),
            latest_year=2026,
        )
        self.assertEqual(decision.intent, "admissions_overview")
        self.assertEqual(decision.params["year"], 2026)
        self.assertEqual(decision.params["major"], "计算机科学与技术")

    def test_single_subject_score_statistics(self):
        decision = self.router.route("政治考了66分的人有多少", latest_year=2026)
        self.assertEqual(decision.intent, "student_statistics")
        self.assertEqual(decision.params["exam_subject_name"], "政治")
        self.assertEqual(decision.params["exam_score_operator"], "=")
        self.assertEqual(str(decision.params["exam_score_value"]), "66")

    def test_surname_typo_is_normalized(self):
        decision = self.router.route("张性同学有多少人", latest_year=2026)
        self.assertEqual(decision.intent, "student_statistics")
        self.assertEqual(decision.params["surname"], "张")

    def test_named_student_lookup(self):
        decision = self.router.route(
            "帮我分析2024年录取的名为“龚哲文”的学生",
            latest_year=2026,
        )
        self.assertEqual(decision.intent, "student_lookup")
        self.assertEqual(decision.params["student_name"], "龚哲文")
        self.assertEqual(decision.params["year"], 2024)

    def test_plan_simulation(self):
        decision = self.router.route(
            "如果土木工程增加20个计划，录取和风险会怎样变化",
            known_majors=("土木工程",),
            latest_year=2026,
        )
        self.assertEqual(decision.intent, "plan_simulation")
        self.assertEqual(decision.params["plan_delta"], 20)
        self.assertEqual(decision.params["major"], "土木工程")

    def test_major_choice_heat(self):
        decision = self.router.route("哪个专业最火", latest_year=2026)
        self.assertEqual(decision.intent, "major_choices")

    def test_anomaly_question(self):
        decision = self.router.route("哪些专业存在高风险", latest_year=2026)
        self.assertEqual(decision.intent, "anomaly_detection")

    def test_policy_question(self):
        decision = self.router.route("平行志愿如何投档", latest_year=2026)
        self.assertEqual(decision.intent, "policy_faq")

    def test_candidate_profile_question(self):
        decision = self.router.route("考生性别和科类分布怎么样", latest_year=2026)
        self.assertEqual(decision.intent, "candidate_profile")

    def test_major_alias_question(self):
        decision = self.router.route("计算机类是什么专业", latest_year=2026)
        self.assertEqual(decision.intent, "major_alias_lookup")
        self.assertEqual(decision.params["source_name"], "计算机类")

    def test_score_band_extracts_academic_subject(self):
        decision = self.router.route("2026年政治分数段分布", latest_year=2026)
        self.assertEqual(decision.intent, "score_band_statistics")
        self.assertEqual(decision.params["subject_name"], "政治")

    def test_official_admission_statistics_question(self):
        decision = self.router.route("2026年官方招生统计", latest_year=2026)
        self.assertEqual(decision.intent, "official_admission_stats")
    def test_follow_up_keeps_short_question_route(self):
        decision = self.router.route("这个专业呢", latest_year=2026)
        self.assertEqual(decision.intent, "admissions_overview")


if __name__ == "__main__":
    unittest.main()

