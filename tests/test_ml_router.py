from __future__ import annotations

import unittest

from agent_core.router import RuleRouter
from app.modules.agent.ml_router import (
    MlAssistedRouter,
    build_ml_router,
    clear_ml_router_cache,
)

QUESTIONS = {
    "admissions_overview": "2026年湖南招生多少人",
    "source_overview": "生源渠道和报到情况怎么样",
    "candidate_profile": "考生性别和科类分布怎么样",
    "subject_scores": "计算机科学与技术专业各科平均分",
    "major_choices": "哪个专业最火",
    "medical_summary": "体检结论如何",
    "forecast": "明年土木工程招生预测",
    "official_admission_stats": "2026年官方招生统计",
    "major_alias_lookup": "计科是什么专业",
    "student_lookup": "分析2026年录取的王小明",
    "student_statistics": "2026年录取的姓王的学生有多少",
    "anomaly_detection": "2026年有哪些专业异常风险",
    "plan_simulation": "如果土木工程增加20个计划，录取和风险会怎样变化",
    "policy_faq": "平行志愿如何投档",
    "consultation_overview": "2026年咨询渠道转化率怎么样",
    "enrollment_funnel": "2026年招生漏斗和报到流失情况",
    "score_band_statistics": "2026年政治分数段分布",
    "admissions_statistics": "2026年各专业一志愿录取率和调剂率",
}


class MlRouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        clear_ml_router_cache()
        cls.router = build_ml_router()

    @classmethod
    def tearDownClass(cls):
        clear_ml_router_cache()

    def test_all_registered_tools_route_correctly(self):
        for expected, question in QUESTIONS.items():
            with self.subTest(question=question):
                decision = self.router.route(question, latest_year=2026)
                self.assertEqual(decision.intent, expected)


    def test_definition_question_routes_to_policy_without_ml(self):
        decision = self.router.route("新生到校比例怎么理解？")
        self.assertEqual(decision.intent, "policy_faq")

    def test_classifier_failure_falls_back_to_rule(self):
        class FailingClassifier:
            def predict(self, _text):
                raise RuntimeError("model failed")

        router = MlAssistedRouter(RuleRouter(), FailingClassifier())
        decision = router.route("帮我看看今年湖南招生情况")
        self.assertEqual(decision.intent, "admissions_overview")
    def test_boundaries_are_not_overridden(self):
        self.assertEqual(self.router.route("今天天气怎么样").intent, "out_of_scope")
        self.assertEqual(self.router.route("把所有学生手机号导出来").intent, "refuse")


if __name__ == "__main__":
    unittest.main()