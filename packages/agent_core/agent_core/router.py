from __future__ import annotations

import re
from typing import Any

from .contracts import RouteDecision
from .extractors import (
    extract_enrollment_filter,
    extract_exam_score_condition,
    extract_gender_name,
    extract_group_by,
    extract_major,
    extract_name_contains,
    extract_academic_subject_name,
    extract_alias_source_name,
    extract_plan_delta,
    extract_province,
    extract_student_name,
    extract_student_status,
    extract_subject_name,
    extract_surname,
    extract_year,
    uses_all_year_scope,
)
from .language import normalize_colloquial


class RuleRouter:
    OUT_OF_SCOPE_MARKERS = (
        "天气", "气温", "下雨", "股票", "基金", "比特币", "汇率", "写诗", "写歌",
        "讲笑话", "讲个笑话", "做菜", "菜谱", "电影推荐", "世界杯", "打游戏", "翻译一下",
        "新闻热点", "明星", "健身计划", "写一首诗", "写一首歌", "体检报告", "诊断",
    )

    @staticmethod
    def _is_out_of_scope(text: str) -> bool:
        return any(marker in text for marker in RuleRouter.OUT_OF_SCOPE_MARKERS)

    @staticmethod
    def _is_sensitive_request(text: str) -> bool:
        return any(keyword in text for keyword in (
            "手机号", "身份证号", "家庭住址", "联系方式", "联系电话", "电话", "邮箱",
            "完整档案", "名单", "学生数据", "考生数据", "外部网盘", "隐私",
            "root密码", "管理员密码", "清空学生表",
            "导出全部学生", "导出所有学生", "批量导出", "批量查询",
            "保证录取", "保录取", "承诺录取", "包过", "内部指标",
        ))

    @staticmethod
    def _is_vague(text: str) -> bool:
        normalized = re.sub(r"\s+", "", text)
        vague_questions = {
            "那个专业怎么样", "这个专业怎么样", "该专业怎么样",
            "这个专业就业好不好", "那个专业就业好不好",
            "哪个专业最好", "哪些专业最好", "专业好不好",
            "有多少人", "多少人", "分数线是多少", "专业怎么样", "专业情况如何",
            "这个学校今年招生怎么样", "计划数和录取数分别是什么",
            "各批次情况如何", "各批次情况如何？",
            "2022到2023年招生情况如何", "这个专业去年怎么样",
        }
        if normalized in vague_questions:
            return True
        return any(re.fullmatch(pattern, normalized) for pattern in (
            r".*各批次情况如何[？?]?", r".*招生情况如何[？?]?", r"计划数和录取数分别是什么[？?]?",
        ))

    @staticmethod
    def _clarification(intent: str, params: dict, message: str) -> str | None:
        del message
        if intent == "plan_simulation" and params.get("plan_delta") is None:
            return "请补充拟增加或减少的计划数，例如“土木工程增加 20 个计划”。"
        if intent == "student_lookup" and not params.get("student_name"):
            return "请提供学生姓名和招生年度；学生个体档案仅授权管理员可查。"
        if intent == "clarify":
            return "请补充具体查询条件，例如年份、省份、专业或学生姓名。"
        return None

    def classify(self, message: str) -> str:
        text = normalize_colloquial(message)
        if re.match(r"^(?:请)?记住[：:，,\s]?", text) or re.match(r"^以后(?:都|默认|优先)?", text):
            return "memory_command"
        if self._is_out_of_scope(text):
            return "out_of_scope"
        if self._is_sensitive_request(text):
            return "refuse"
        if self._is_vague(text):
            return "clarify"
        if extract_plan_delta(text, {}) is not None and any(
            keyword in text for keyword in ("计划", "名额", "多招", "少招", "增加", "减少", "扩招", "缩招", "模拟", "风险")
        ):
            return "plan_simulation"
        if any(keyword in text for keyword in ("怎么理解", "是什么意思", "含义", "怎么解释", "口径", "怎么计算", "如何计算")) and any(
            keyword in text for keyword in ("到校", "报到", "入学率", "计划完成率", "志愿热度", "专业名称", "投档")
        ):
            return "policy_faq"
        if any(keyword in text for keyword in ("新生报到", "按时到校", "未按时到校", "没有按时到校", "没有到校")):
            return "policy_faq"

        if any(keyword in text for keyword in ("分数段", "一分一段", "十分段", "10分段", "成绩分段", "分数区间")) or re.search(r"\d{2,3}\s*(?:到|至|-)\s*\d{2,3}\s*分", text) or re.search(r"\d{3}分以上", text):
            return "score_band_statistics"
        if any(keyword in text for keyword in ("咨询转化", "咨询渠道", "咨询热点")) or ("咨询" in text and any(keyword in text for keyword in ("转化", "人数", "类型", "效果", "热点"))):
            return "consultation_overview"
        if any(keyword in text for keyword in ("招生漏斗", "计划到录取", "计划到报到", "报到流失", "最终报到率", "报到转化", "录取率报到率")):
            return "enrollment_funnel"
        if any(keyword in text for keyword in ("官方统计", "官方招生统计", "专升本", "普通计划", "总招生", "招生总人数", "人数对比")):
            return "official_admission_stats"
        if any(keyword in text for keyword in ("招生计划", "计划数")) and any(
            keyword in text for keyword in ("录取", "报到")
        ):
            return "admissions_statistics"
        if any(keyword in text for keyword in ("生源", "渠道")) and any(
            keyword in text for keyword in ("报到", "趋势")
        ):
            return "source_overview"
        if ("录取人数统计" in text) or ("统计" in text and "录取人数" in text):
            return "student_statistics"
        if ("性别" in text or "科类" in text) and any(keyword in text for keyword in ("多少人", "人数", "统计", "录取多少")):
            return "student_statistics"

        if any(keyword in text for keyword in ("体检", "专业受限", "健康")):
            return "medical_summary"

        if len(re.findall(r"20\d{2}", text)) >= 2 and any(keyword in text for keyword in ("相比", "比较", "变化", "增减", "差值")):
            return "admissions_overview"
        advanced_stat_keywords = (
            "志愿率", "报考率", "报考数", "录取数", "各年度", "一志愿", "二志愿", "三志愿", "志愿录取情况",
            "志愿报考情况", "报到率", "报到数", "调剂率", "中位分", "下四分位",
            "各学院", "分学院", "按学院", "性别情况", "最高分及专业", "最低分及专业",
            "广东投档排位", "征集数", "专业异动", "转出专业", "转入专业", "计划编制数",
            "计划调整数", "线差", "位次占比", "考生类别", "毕业类别", "外语语种",
            "政治面貌", "年龄", "投档单位", "校区", "地市", "区县",
            "选科要求", "国际专业代码", "校编代码", "志愿数", "志愿总数", "报考数", "男生数", "女生数",
        )
        if any(keyword in text for keyword in advanced_stat_keywords):
            return "admissions_statistics"

        policy_keywords = (
            "平行志愿", "投档", "退档", "滑档", "调剂", "院校专业组", "招生章程",
            "招生简章", "征集志愿", "强基计划", "综合评价", "专项计划", "提前批",
            "冲稳保", "选科要求", "大类招生", "转专业", "体检受限", "专业级差",
            "投档比例", "录取结果", "分数线", "位次", "填报资料", "录取后不去",
        )
        if any(keyword in text for keyword in policy_keywords):
            return "policy_faq"
        if re.search(r"(?:他|她|该生|该同学|这个学生|这名学生)(?:的)?(?:成绩|录取|志愿|情况|档案)", text):
            return "student_lookup"
        if re.search(r"[\u4e00-\u9fff·]{2,4}的档案", text):
            return "student_lookup"
        if re.search(r"(?:查|查看|分析|帮我查)(?:一下)?[\u4e00-\u9fff]{2,4}的(?:档案|录取|成绩|志愿|情况)", text):
            return "student_lookup"
        if any(keyword in text for keyword in ("性别", "男女", "考生构成", "民族", "户籍", "地区分布", "考生画像")):
            return "candidate_profile"
        if any(keyword in text for keyword in ("专业别名", "名称不同", "名称修正", "标准专业", "改名", "专业名称", "是什么专业", "专业简称")):
            return "major_alias_lookup"
        if any(keyword in text for keyword in ("各专业", "各省", "按专业", "按省份")) and any(
            keyword in text for keyword in ("招生计划", "招生人数", "计划数", "录取人数", "录取情况", "完成率")
        ):
            return "admissions_overview"
        if (
            extract_surname(text, {})
            or extract_name_contains(text, {})
        ) and any(keyword in text for keyword in ("多少", "人数", "统计", "分布", "学生", "考生", "录取")):
            return "student_statistics"
        if any(keyword in text for keyword in ("男生", "女生", "男性", "女性", "男学生", "女学生")) and any(
            keyword in text for keyword in ("多少", "人数", "统计", "录取", "学生", "考生")
        ):
            return "student_statistics"
        if any(keyword in text for keyword in ("按专业", "按省份", "按性别", "按科类", "各专业", "各省")) and any(
            keyword in text for keyword in ("多少", "人数", "统计", "学生", "考生", "录取", "报到")
        ):
            return "student_statistics"
        if any(keyword in text for keyword in ("多少名学生", "多少考生", "学生人数", "考生人数", "人数统计")) and any(
            keyword in text for keyword in ("专业", "省份", "性别", "科类", "报到", "录取")
        ):
            return "student_statistics"
        if extract_exam_score_condition(text, {}) and any(
            keyword in text for keyword in ("多少", "人数", "几人", "几个", "学生", "考生", "人")
        ):
            return "student_statistics"
        if extract_student_name(text, {}) and any(
            keyword in text for keyword in ("学生", "录取", "情况", "成绩", "志愿", "档案", "分析")
        ):
            return "student_lookup"
        if any(keyword in text for keyword in ("专业别名", "名称不同", "名称修正", "标准专业", "改名", "专业名称")):
            return "major_alias_lookup"
        if any(keyword in text for keyword in ("专升本", "普通计划", "总招生", "招生总人数", "官方统计", "官方招生统计", "招生统计", "数据口径", "人数对比")):
            return "official_admission_stats"
        plan_change_patterns = (
            r"(?:增加|上调|扩招|新增|减少|下调|缩减|削减)\s*\d*\s*个?\s*(?:招生计划|计划|名额)",
            r"(?:招生计划|计划|名额)\s*(?:增加|上调|扩招|新增|减少|下调|缩减|削减)\s*\d*",
        )
        if any(
            keyword in text
            for keyword in (
                "沙盘", "模拟", "假如", "增加计划", "减少计划", "调整计划", "扩招",
                "缩招", "上调计划", "下调计划", "名额增减",
            )
        ) or any(re.search(pattern, text) for pattern in plan_change_patterns):
            return "plan_simulation"
        if any(keyword in text for keyword in ("异常", "波动异常", "风险", "不正常", "预警", "偏离", "计划缺口")):
            return "anomaly_detection"
        if any(keyword in text for keyword in ("预测", "明年", "下一年", "未来")):
            return "forecast"
        if any(keyword in text for keyword in ("志愿数", "志愿总数", "填报", "报考数")) and "志愿" in text:
            return "admissions_statistics"
        if any(keyword in text for keyword in ("志愿", "报考热度", "专业热度")):
            return "major_choices"
        if re.search(r"录取(?:最高|最低|平均)分", text):
            return "admissions_statistics"
        if any(
            keyword in text
            for keyword in (
                "成绩", "科目", "平均分", "语文", "数学", "外语", "物理", "化学",
                "生物", "政治", "历史", "地理",
            )
        ):
            return "subject_scores"
        if any(keyword in text for keyword in ("性别", "男女", "考生构成", "民族", "户籍", "地区分布", "考生画像")):
            return "candidate_profile"
        if any(keyword in text for keyword in ("生源", "报到", "渠道")):
            return "source_overview"
        if any(keyword in text for keyword in ("专业", "热门专业", "专业录取")):
            return "admissions_overview"
        if any(keyword in text for keyword in ("省份", "各省", "分省", "省际", "地区", "生源地分布")):
            return "admissions_overview"
        if any(keyword in text for keyword in ("计划", "录取", "招生", "完成率")):
            return "admissions_overview"
        return "admissions_overview"

    def route(
        self,
        message: str,
        *,
        context: dict[str, Any] | None = None,
        known_provinces: list[str] | tuple[str, ...] = (),
        known_majors: list[str] | tuple[str, ...] = (),
        latest_year: int | None = None,
        current_year: int = 2026,
    ) -> RouteDecision:
        context = context or {}
        normalized = normalize_colloquial(message)
        intent = self.classify(normalized)
        year = extract_year(normalized, context, current_year=current_year)
        if year is None and not uses_all_year_scope(normalized):
            year = latest_year
        exam_condition = extract_exam_score_condition(normalized, context) or {}
        params: dict[str, Any] = {
            "year": year,
            "province": extract_province(normalized, known_provinces),
            "major": extract_major(normalized, known_majors),
            "student_name": extract_student_name(normalized, context),
            "surname": extract_surname(normalized, context),
            "name_contains": extract_name_contains(normalized, context),
            "gender_name": extract_gender_name(normalized, context),
            "subject_name": extract_subject_name(normalized),
            "student_status": extract_student_status(normalized),
            "is_enrolled": extract_enrollment_filter(normalized),
            "group_by": extract_group_by(normalized),
            "plan_delta": extract_plan_delta(normalized, context),
            **exam_condition,
        }
        if intent == "score_band_statistics":
            academic_subject = extract_academic_subject_name(normalized)
            if academic_subject:
                params["subject_name"] = academic_subject
        if intent == "major_alias_lookup":
            source_name = extract_alias_source_name(normalized)
            if source_name:
                params["source_name"] = source_name
        if (
            ("男生" in normalized or "男性" in normalized or "男学生" in normalized)
            and ("女生" in normalized or "女性" in normalized or "女学生" in normalized)
        ):
            params.pop("gender_name", None)
        params = {key: value for key, value in params.items() if value is not None}
        clarification = self._clarification(intent, params, normalized)
        return RouteDecision(
            intent=intent,
            normalized_message=normalized,
            params=params,
            clarification=clarification,
        )












