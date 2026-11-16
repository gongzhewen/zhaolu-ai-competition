import unittest

from agent_core.registry import TOOL_NAMES
from agent_core.router import RuleRouter

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


class AllIntentRoutingTests(unittest.TestCase):
    def test_every_registered_tool_has_a_route_case(self):
        self.assertEqual(set(QUESTIONS), set(TOOL_NAMES))

    def test_all_registered_intents_are_classified(self):
        router = RuleRouter()
        for expected, question in QUESTIONS.items():
            self.assertEqual(router.classify(question), expected, question)


if __name__ == "__main__":
    unittest.main()