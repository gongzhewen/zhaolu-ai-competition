from __future__ import annotations

from .contracts import ToolCall
from .registry import TOOL_BY_NAME


def should_use_llm_plan(
    message: str,
    intent: str,
    *,
    fast_mode: bool = True,
    llm_configured: bool = True,
) -> bool:
    if intent == "admissions_statistics":
        return False
    if not fast_mode:
        return True
    if intent in {"student_lookup", "student_statistics"}:
        return False
    if not llm_configured:
        return False
    if intent in {"plan_simulation", "forecast"}:
        return True

    complex_cues = (
        "综合分析", "结合", "联合", "关联", "关系", "规律", "对比", "同时分析",
        "共同", "为什么", "原因", "如何", "怎么", "建议", "影响", "方案", "优化",
        "决策", "权衡", "优先", "利弊",
    )
    if any(cue in message for cue in complex_cues):
        return True
    if intent == "forecast" and any(
        cue in message
        for cue in ("扩招", "缩招", "必要", "应该", "建议", "可以", "风险", "调整")
    ):
        return True
    follow_up_cues = ("那", "这个专业呢", "它", "其", "上述", "前面", "继续分析")
    return len(message) <= 12 and any(cue in message for cue in follow_up_cues)


def single_tool_plan(intent: str) -> ToolCall | None:
    if intent not in TOOL_BY_NAME:
        return None
    return ToolCall(name=intent, params={}, reason="规则工具路由")


def default_suggestions(intent: str) -> list[str]:
    suggestions = {
        "admissions_overview": ["查看各专业计划完成率", "哪些专业计划数最多？", "各省招生计划是多少？"],
        "source_overview": ["分析各省生源质量", "报到率有哪些变化？", "生源渠道贡献如何？"],
        "candidate_profile": ["男女比例如何？", "各省份考生结构怎样？", "城乡和户籍分布如何？"],
        "subject_scores": ["哪些科目平均分最高？", "不同专业成绩差异如何？", "成绩分布有哪些异常？"],
        "major_choices": ["哪些专业志愿热度最高？", "热度和录取完成率是否匹配？", "冷门专业有哪些？"],
        "medical_summary": ["哪些专业受限人数较多？", "体检结论分布如何？", "专业受限风险有哪些？"],
        "forecast": ["明年计划完成率如何？", "哪些专业需要扩招？", "预测结果有哪些风险？"],
        "official_admission_stats": ["普通计划和专升本人数对比", "今年官方总录取人数是多少？", "不同年度人数变化如何？"],
        "major_alias_lookup": ["这个专业有哪些省份别名？", "某个别名对应哪个标准专业？", "哪些规则会影响统计？"],
        "student_lookup": ["分析该生录取情况", "查看该生各科成绩", "该生专业志愿顺序是什么？"],
        "student_statistics": ["2025年录取的姓王的学生有多少？", "按专业统计男生人数", "统计各省份未报到人数"],
        "anomaly_detection": ["哪些专业存在高风险？", "计划完成率异常的专业有哪些？", "志愿热度和计划是否匹配？"],
        "plan_simulation": ["土木工程增加 20 个计划会怎样？", "某专业减少计划的风险如何？", "如何调整计划更稳妥？"],
        "admissions_statistics": ["按学院统计报到率和计划完成率", "各专业一志愿录取率", "2到20志愿录取情况"],
        "policy_faq": ["平行志愿如何投档？", "退档和滑档有什么区别？", "专业调剂有哪些风险？"],
    }
    return suggestions.get(intent, ["还可以从哪些角度分析？", "生成一份综合分析报告", "有哪些异常需要关注？"])
