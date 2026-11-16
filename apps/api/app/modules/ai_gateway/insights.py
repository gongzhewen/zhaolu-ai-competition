import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.core.text import text
from app.modules.analytics import service
from sqlalchemy.ext.asyncio import AsyncSession


def _numeric_values(value: str) -> set[Decimal]:
    values: set[Decimal] = set()
    for token in re.findall(r"\d+(?:\.\d+)?", value):
        try:
            values.add(Decimal(token).normalize())
        except InvalidOperation:
            continue
    return values


def _pct(part: int, total: int) -> float:
    return round(part / total * 100, 2) if total else 0.0


def _fallback_year_insights(
    *,
    year_no: int,
    scope: str,
    admissions: dict | None,
    source: dict | None,
    candidate: dict | None,
    subjects: dict | None,
    choices: dict | None,
    medical: dict | None,
) -> list[dict]:
    insights: list[dict] = []
    if admissions and scope in {"all", "admissions"}:
        metrics = admissions["metrics"]
        plan_count = int(metrics.get("plan_count") or 0)
        admitted_count = int(metrics.get("admitted_count") or 0)
        completion_rate = float(metrics.get("completion_rate") or 0)
        plan_gap = admitted_count - plan_count
        if plan_count > 0:
            risk_level = (
                "high"
                if completion_rate > 105 or completion_rate < 90
                else "medium"
                if completion_rate > 101 or completion_rate < 98
                else "low"
            )
            analysis = (
                "计划执行基本吻合，后续重点应转向专业结构、生源质量和增量计划的边际收益。"
                if 98 <= completion_rate <= 101
                else "计划完成存在缺口，需要拆分到省份、批次、科类和专业定位原因。"
                if 90 <= completion_rate < 98
                else "计划与实际录取偏离较大，应核对计划口径、调剂录取和统计版本，优先排查执行风险。"
            )
            finding = (
                f"计划 {plan_count} 人、录取 {admitted_count} 人、完成率 {completion_rate}%，"
                f"较计划{'多出' if plan_gap > 0 else '少'} {abs(plan_gap)} 人。"
            )
        else:
            risk_level = "unknown"
            analysis = "该年度暂无可用招生计划数据，无法判断执行偏差。"
            detail_count = int(((source or {}).get("metrics") or {}).get("detail_count") or 0)
            finding = (
                f"计划数据缺失，录取汇总为 {admitted_count} 人；"
                f"现有生源明细 {detail_count} 人，不能据此计算真实计划完成率。"
            )
        insights.append(
            {
                "year_no": year_no,
                "title": f"{year_no}年招生计划执行",
                "finding": finding,
                "analysis": analysis,
                "suggestion": (
                    "对异常专业做年度、省份、科类和批次四层下钻；计划增加前先核验志愿热度、"
                    "调剂压力和培养容量，形成可回滚的投放方案。"
                ),
                "risk_level": risk_level,
                "evidence": ["fact.plan", "fact.admission_record"],
            }
        )
    if source and scope in {"all", "admissions"}:
        metrics = source["metrics"]
        detail_count = int(metrics.get("detail_count") or metrics.get("candidate_count") or 0)
        official_total = int(metrics.get("official_total_count") or 0)
        coverage_basis = str(metrics.get("coverage_basis") or "unverified")
        detail_gap = int(metrics.get("detail_gap_count") or (max(official_total - detail_count, 0) if official_total else 0))
        enrolled = int(metrics.get("enrolled_count") or 0)
        enrollment_available = bool(metrics.get("enrollment_data_available"))
        coverage = float(metrics.get("coverage_rate") or 0)
        coverage_status = (
            "完整"
            if coverage_basis == "official" and coverage >= 99.5
            else "部分覆盖"
            if coverage_basis == "official"
            else "待核验"
        )
        enrollment_analysis = (
            f"报到数据已导入 {int(metrics.get('enrollment_record_count') or 0)} 条，可计算报到率并继续分析专业和渠道差异。"
            if enrollment_available
            else "当前没有独立的报到名单，已报到人数和报到率显示为未导入，不能把缺失值解释为真实零报到。"
        )
        if coverage_basis == "official":
            coverage_finding = (
                f"官方录取总数 {official_total} 人，生源明细 {detail_count} 人，"
                f"缺 {detail_gap} 人，覆盖率 {coverage}%（{coverage_status}）。"
            )
            coverage_analysis = (
                f"当前生源明细覆盖率为 {coverage}%，省份、渠道和考生结构只能代表已导入明细，不能直接外推全部录取群体。"
            )
            coverage_risk = "high" if coverage < 90 else "medium" if coverage < 99.5 or not enrollment_available else "low"
        else:
            coverage_finding = f"官方录取总数尚未导入，现有生源明细 {detail_count} 人，覆盖率无法计算。"
            coverage_analysis = (
                "缺少官方录取总数时不能把明细人数当成完整总数，也无法判断生源结构是否存在系统性缺口。"
            )
            coverage_risk = "unknown"
        insights.append(
            {
                "year_no": year_no,
                "title": f"{year_no}年生源完整性与报到",
                "finding": coverage_finding + (f"已报到 {enrolled} 人。" if enrollment_available else "报到名单未导入。"),
                "analysis": coverage_analysis + enrollment_analysis,
                "suggestion": (
                    "先核对官方录取总数与明细差异，再补导缺失名单；报到数据导入后按省份、专业、渠道计算真实报到率。"
                ),
                "risk_level": coverage_risk,
                "evidence": ["fact.admission_record", "fact.enrollment_status"],
            }
        )
    if candidate and scope in {"all", "candidate"}:
        metrics = candidate["metrics"]
        total = int(metrics.get("candidate_count") or 0)
        gender = candidate.get("by_gender") or []
        subject = candidate.get("by_subject") or []
        region = candidate.get("by_region") or []
        top_gender = gender[0] if gender else None
        top_subject = subject[0] if subject else None
        top_region = region[0] if region else None
        top_gender_share = _pct(int(top_gender["count"]), total) if top_gender else 0.0
        top_subject_share = _pct(int(top_subject["count"]), total) if top_subject else 0.0
        insights.append(
            {
                "year_no": year_no,
                "title": f"{year_no}年学生成长画像",
                "finding": (
                    f"已匹配考生画像 {total} 人；"
                    + (f"性别最高为{top_gender['name']} {top_gender['count']} 人（{top_gender_share}%）；" if top_gender else "")
                    + (f"科类最大为{top_subject['name']} {top_subject['count']} 人（{top_subject_share}%）；" if top_subject else "")
                    + (f"地区最高为{top_region['name']} {top_region['count']} 人。" if top_region else "地区画像缺失。")
                ),
                "analysis": (
                    "考生画像只覆盖已成功关联学籍或录取记录的样本；结构过度集中时，宣传触达和咨询资源可能出现偏差，"
                    "但性别、地区和科类本身不能直接作为录取质量结论。"
                ),
                "suggestion": (
                    "把高占比科类与专业志愿、录取分数、报到率和就业去向做交叉分层，识别宣传盲区和专业适配差异。"
                ),
                "risk_level": "medium" if top_gender_share >= 75 or top_subject_share >= 75 else "low",
                "evidence": ["fact.candidate_profile"],
            }
        )
    if subjects and scope in {"all", "subject"} and subjects.get("subjects"):
        sorted_subjects = sorted(subjects["subjects"], key=lambda item: float(item.get("avg_score") or 0))
        low = sorted_subjects[0]
        high = sorted_subjects[-1]
        score_gap = round(float(high.get("avg_score") or 0) - float(low.get("avg_score") or 0), 2)
        max_stddev_row = max(subjects["subjects"], key=lambda item: float(item.get("score_stddev") or 0))
        max_stddev = float(max_stddev_row.get("score_stddev") or 0)
        insights.append(
            {
                "year_no": year_no,
                "title": f"{year_no}年学科成绩结构",
                "finding": (
                    f"平均分最高为{high['subject_name']} {high['avg_score']} 分，最低为"
                    f"{low['subject_name']} {low['avg_score']} 分，差距 {score_gap} 分；"
                    f"{max_stddev_row['subject_name']}离散度最高（标准差 {max_stddev}）。"
                ),
                "analysis": (
                    "平均分差距反映学科间难度或考生群体差异，标准差反映同一学科内部差异；"
                    "跨年度比较前必须确认满分制、选考科目和统计口径一致。"
                ),
                "suggestion": (
                    "对低均分或高离散科目按科类、专业志愿和地区下钻，识别基础薄弱群体并优化选科说明、"
                    "入学准备和学习支持。"
                ),
                "risk_level": "high" if score_gap >= 60 or max_stddev >= 80 else "medium" if score_gap >= 40 or max_stddev >= 60 else "low",
                "evidence": ["fact.exam_subject_score"],
            }
        )
    if choices and scope in {"all", "major"} and choices.get("majors"):
        majors = choices["majors"]
        top = majors[0]
        total_choices = int((choices.get("metrics") or {}).get("choice_count") or 0)
        top3_count = sum(int(item.get("choice_count") or 0) for item in majors[:3])
        concentration = _pct(top3_count, total_choices)
        top_share = _pct(int(top.get("choice_count") or 0), total_choices)
        insights.append(
            {
                "year_no": year_no,
                "title": f"{year_no}年专业志愿集中度",
                "finding": (
                    f"志愿热度最高为{top['major_name']}，{top['choice_count']} 次（{top_share}%）；"
                    f"前三专业占全部志愿的 {concentration}%。"
                ),
                "analysis": (
                    "集中度过高会增加热门专业竞争、调剂压力和录取波动；集中度过低则可能反映专业辨识度不足或志愿填报分散。"
                ),
                "suggestion": (
                    "对热门专业测算扩招的录取位次变化和培养容量，对低热度专业检查课程、就业和招生宣传，而不是直接按热度增减计划。"
                ),
                "risk_level": "high" if concentration >= 50 else "medium" if concentration >= 35 else "low",
                "evidence": ["fact.major_choice"],
            }
        )
    if medical and scope in {"all", "medical"} and medical.get("medical_results"):
        rows = medical["medical_results"]
        total = sum(int(item.get("count") or 0) for item in rows)
        restricted = next((item for item in rows if "受限" in str(item.get("result_name"))), None)
        if total and restricted:
            ratio = _pct(int(restricted["count"]), total)
            restricted_categories = sum(1 for item in rows if "受限" in str(item.get("result_name")))
            insights.append(
                {
                    "year_no": year_no,
                    "title": f"{year_no}年体检专业受限",
                    "finding": (
                        f"专业受限 {restricted['count']} 人，占体检摘要总数 {ratio}%；"
                        f"共有 {restricted_categories} 类受限结果。"
                    ),
                    "analysis": (
                        "体检受限会直接影响部分专业的可填报范围；受限人数不等于退档人数，需与志愿专业和录取结果关联后判断影响。"
                    ),
                    "suggestion": (
                        "在专业介绍和填报提示中明确体检要求，对高风险专业建立填报前提示和录取后复核流程。"
                    ),
                    "risk_level": "medium" if ratio >= 10 else "low",
                    "evidence": ["fact.medical_summary"],
                }
            )
    if admissions and source and scope in {"all", "admissions"}:
        admissions_metrics = admissions.get("metrics") or {}
        source_metrics = source.get("metrics") or {}
        admitted_count = int(admissions_metrics.get("admitted_count") or 0)
        official_total = int(source_metrics.get("official_total_count") or 0)
        coverage_basis = str(source_metrics.get("coverage_basis") or "unverified")
        detail_gap = int(source_metrics.get("detail_gap_count") or 0)
        coverage = float(source_metrics.get("coverage_rate") or 0)
        reconciliation_gap = admitted_count - official_total if official_total else 0
        issues = []
        if coverage_basis != "official":
            issues.append("官方录取总数缺失")
        if detail_gap:
            issues.append(f"生源明细缺 {detail_gap} 人")
        if reconciliation_gap:
            issues.append(f"录取汇总与官方统计相差 {abs(reconciliation_gap)} 人")
        if issues:
            insights.append(
                {
                    "year_no": year_no,
                    "title": f"{year_no}年数据口径校验",
                    "finding": "；".join(issues)
                    + (f"；生源明细覆盖率 {coverage}%。" if coverage_basis == "official" else "；当前无法计算可信覆盖率。"),
                    "analysis": "差异可能来自数据版本、统计时点、重复记录或专业映射，必须先完成口径校验再做趋势归因。",
                    "suggestion": "锁定官方统计版本，按省份和专业对账；未解释差异前，跨年结论应标注为临时结果并保留审计记录。",
                    "risk_level": "high" if detail_gap > 0 and coverage < 90 else "medium",
                    "evidence": ["fact.admission_record", "fact.authoritative_admission_stat", "fact.admission_record"],
                }
            )
    return insights


def _cross_year_insights(trend: list[dict], *, scope: str) -> list[dict]:
    valid_admissions = [item for item in trend if int(item.get("plan_count") or 0) > 0]
    valid_candidates = [item for item in trend if int(item.get("candidate_count") or 0) > 0]
    valid_coverage = [
        item
        for item in trend
        if int(item.get("candidate_count") or 0) > 0 and item.get("coverage_basis") == "official"
    ]
    insights: list[dict] = []
    if len(valid_admissions) >= 2 and scope in {"all", "admissions"}:
        first = valid_admissions[0]
        last = valid_admissions[-1]
        delta = int(last["admitted_count"]) - int(first["admitted_count"])
        direction = "增长" if delta > 0 else "下降" if delta < 0 else "持平"
        change_rate = _pct(abs(delta), int(first["admitted_count"])) if first["admitted_count"] else 0
        insights.append(
            {
                "title": "跨年度录取规模变化",
                "finding": (
                    f"{first['year_no']}—{last['year_no']}年录取人数{direction} {abs(delta)} 人（{change_rate}%），"
                    f"计划由 {first['plan_count']} 人变为 {last['plan_count']} 人。"
                ),
                "analysis": (
                    "规模变化应与计划投放、专业结构和生源需求一致；只看录取总量会把计划调整误判为市场需求变化。"
                ),
                "suggestion": "按年度、省份、专业和批次拆分增减来源，并对扩招专业的录取位次和报到风险做压力测试。",
                "risk_level": "high" if change_rate >= 20 else "medium" if change_rate >= 10 else "low",
                "evidence": ["fact.plan", "fact.admission_record"],
            }
        )
    if len(valid_candidates) >= 2 and scope in {"all", "candidate"}:
        first = valid_candidates[0]
        last = valid_candidates[-1]
        delta = int(last["candidate_count"]) - int(first["candidate_count"])
        direction = "增加" if delta > 0 else "减少" if delta < 0 else "持平"
        coverage_change = None
        first_coverage = None
        last_coverage = None
        if len(valid_coverage) >= 2:
            first_coverage = valid_coverage[0]
            last_coverage = valid_coverage[-1]
            coverage_change = round(
                float(last_coverage.get("source_coverage_rate") or 0)
                - float(first_coverage.get("source_coverage_rate") or 0),
                2,
            )
        coverage_finding = (
            f"覆盖率由 {first_coverage['source_coverage_rate']}% 变为 {last_coverage['source_coverage_rate']}%。"
            if first_coverage and last_coverage
            else "部分年度缺少官方录取总数，覆盖率无法跨年对齐。"
        )
        insights.append(
            {
                "title": "跨年度生源规模变化",
                "finding": (
                    f"{first['year_no']}—{last['year_no']}年生源明细{direction} {abs(delta)} 人；{coverage_finding}"
                ),
                "analysis": (
                    "生源明细变化同时受录取规模、导入完整度和去重口径影响；"
                    "当覆盖率下降时，明细减少不能直接解释为实际生源减少。"
                ),
                "suggestion": "先完成各年度明细覆盖率对账，再分析省份和渠道来源的净增减，并将缺失值单独列示。",
                "risk_level": "medium" if abs(delta) and abs(delta) / max(int(first['candidate_count']), 1) >= 0.1 else "low",
                "evidence": ["fact.admission_record", "fact.authoritative_admission_stat"],
            }
        )
        if coverage_change is not None and coverage_change <= -5 and first_coverage and last_coverage:
            insights.append(
                {
                    "title": "生源明细覆盖率下降",
                    "finding": (
                        f"{first_coverage['year_no']}—{last_coverage['year_no']}年明细覆盖率下降 "
                        f"{abs(coverage_change)} 个百分点。"
                    ),
                    "analysis": "覆盖率下降会放大省份、渠道、成绩和专业结构分析偏差，当前跨年结构结论可信度不足。",
                    "suggestion": "暂停仅基于明细的扩招或缩招结论，先补齐缺失记录并完成官方录取总数对账。",
                    "risk_level": "high" if float(last_coverage.get("source_coverage_rate") or 0) < 85 else "medium",
                    "evidence": ["fact.authoritative_admission_stat", "fact.admission_record"],
                }
            )
    if scope == "all" and trend:
        latest = trend[-1]
        if not latest.get("enrollment_data_available"):
            insights.append(
                {
                    "title": "报到数据完整性",
                    "finding": f"{latest['year_no']}年尚未导入独立报到名单，报到人数和报到率不可计算。",
                    "analysis": "报到率、实际入学规模和渠道转化目前不可用，不能把缺失值解释为真实零报到。",
                    "suggestion": "使用报到情况导入模板补充实际报到名单，再重新生成年度和跨年度洞察。",
                    "risk_level": "high",
                    "evidence": ["fact.enrollment_status", "fact.admission_record"],
                }
            )
    if len(valid_admissions) >= 2:
        completion_values = [float(item.get("completion_rate") or 0) for item in valid_admissions]
        volatility = round(max(completion_values) - min(completion_values), 2)
        if volatility >= 2:
            insights.append(
                {
                    "title": "计划执行波动",
                    "finding": f"有数据的年度计划完成率波动 {volatility} 个百分点。",
                    "analysis": "完成率波动可能与计划投放、批次结构、调剂规则或统计版本变化有关，单年完成率不能代表稳定趋势。",
                    "suggestion": "对波动最大的年度拆解省份和专业计划执行，建立计划版本与录取版本的双重审计。",
                    "risk_level": "medium" if volatility >= 5 else "low",
                    "evidence": ["fact.plan", "fact.admission_record"],
                }
            )
    return insights


async def _build_year_summary(db: AsyncSession, *, year_no: int, scope: str) -> dict:
    admissions = await service.get_admissions_overview(db, year=year_no)
    source = await service.get_source_overview(db, year=year_no)
    candidate = await service.get_candidate_profile_overview(db, year=year_no) if scope in {"all", "candidate"} else None
    subjects = await service.get_subject_score_overview(db, year=year_no) if scope in {"all", "subject"} else None
    choices = await service.get_major_choice_overview(db, year=year_no) if scope in {"all", "major"} else None
    medical = await service.get_medical_overview(db, year=year_no) if scope in {"all", "medical"} else None
    insights = _fallback_year_insights(
        year_no=year_no,
        scope=scope,
        admissions=admissions,
        source=source,
        candidate=candidate,
        subjects=subjects,
        choices=choices,
        medical=medical,
    )
    admissions_metrics = (admissions or {}).get("metrics", {})
    candidate_metrics = (candidate or {}).get("metrics", {})
    source_metrics = (source or {}).get("metrics", {})
    top_major = ((choices or {}).get("majors") or [{}])[0]
    plan_by_major = {
        row["major_name"]: row
        for row in (admissions or {}).get("by_major", [])
    }
    plan_count = int(admissions_metrics.get("plan_count") or 0)
    admitted_count = int(admissions_metrics.get("admitted_count") or 0)
    completion_rate = float(admissions_metrics.get("completion_rate") or 0) if plan_count > 0 else None
    plan_gap_count = admitted_count - plan_count if plan_count > 0 else None
    source_detail_count = int(source_metrics.get("detail_count") or source_metrics.get("candidate_count") or 0)
    top_major_choices = int(top_major.get("choice_count") or 0)
    total_choices = int(((choices or {}).get("metrics") or {}).get("choice_count") or 0)
    return {
        "year_no": year_no,
        "metrics": {
            "plan_count": plan_count,
            "admitted_count": admitted_count,
            "official_admitted_count": int(source_metrics.get("official_total_count") or 0),
            "plan_gap_count": plan_gap_count,
            "completion_rate": completion_rate,
            "candidate_count": source_detail_count,
            "candidate_profile_count": int(candidate_metrics.get("candidate_count") or 0),
            "source_detail_count": source_detail_count,
            "detail_gap_count": int(source_metrics.get("detail_gap_count") or 0),
            "source_coverage_rate": float(source_metrics.get("coverage_rate") or 0),
            "coverage_basis": str(source_metrics.get("coverage_basis") or "unverified"),
            "detail_complete": bool(source_metrics.get("detail_complete")),
            "enrolled_count": int(source_metrics.get("enrolled_count") or 0),
            "enrollment_rate": float(source_metrics.get("enrollment_rate") or 0),
            "enrollment_data_available": bool(source_metrics.get("enrollment_data_available")),
            "enrollment_record_count": int(source_metrics.get("enrollment_record_count") or 0),
            "data_quality_status": str(source_metrics.get("data_quality_status") or "missing"),
            "top_major_name": top_major.get("major_name"),
            "top_major_choices": top_major_choices,
            "top_major_share": round(top_major_choices / total_choices * 100, 2) if total_choices else 0.0,
        },
        "insights": insights,
        "detail": {
            "candidate": candidate,
            "subjects": subjects,
            "choices": choices,
            "medical": medical,
            "major_detail": [
                {
                    "major_name": row["major_name"],
                    "choice_count": int(row.get("choice_count") or 0),
                    "candidate_count": int(row.get("candidate_count") or 0),
                    "plan_count": int(plan_by_major.get(row["major_name"], {}).get("plan_count") or 0),
                    "completion_rate": plan_by_major.get(row["major_name"], {}).get("completion_rate"),
                    "choice_per_plan": (
                        round(int(row.get("choice_count") or 0) / int(plan_by_major.get(row["major_name"], {}).get("plan_count") or 0), 2)
                        if plan_by_major.get(row["major_name"], {}).get("plan_count")
                        else None
                    ),
                }
                for row in (choices or {}).get("majors", [])
            ],
        },
        "trend": {
            "year_no": year_no,
            "plan_count": plan_count,
            "admitted_count": admitted_count,
            "completion_rate": completion_rate,
            "candidate_count": source_detail_count,
            "source_detail_count": source_detail_count,
            "source_coverage_rate": float(source_metrics.get("coverage_rate") or 0),
            "coverage_basis": str(source_metrics.get("coverage_basis") or "unverified"),
            "enrolled_count": int(source_metrics.get("enrolled_count") or 0),
            "enrollment_rate": float(source_metrics.get("enrollment_rate") or 0),
            "enrollment_data_available": bool(source_metrics.get("enrollment_data_available")),
        },
    }


async def generate_insights(
    db: AsyncSession,
    *,
    scope: str = "all",
    year: int | None = None,
) -> dict:
    result = await db.execute(text("SELECT year_no FROM dim.year ORDER BY year_no"))
    available_years = [int(row[0]) for row in result.all()]
    target_years = [year] if year in available_years else available_years
    summaries = [await _build_year_summary(db, year_no=value, scope=scope) for value in target_years]
    selected_year = target_years[-1] if target_years else None
    selected_summary = summaries[-1] if summaries else {"insights": [], "metrics": {}}

    trend = [item["trend"] for item in summaries]
    previous = None
    for item, summary in zip(trend, summaries, strict=False):
        if previous:
            for field, key in (
                ("plan_count", "plan_yoy_rate"),
                ("admitted_count", "admitted_yoy_rate"),
                ("candidate_count", "candidate_yoy_rate"),
            ):
                before = int(previous.get(field) or 0)
                current = int(item.get(field) or 0)
                item[key] = round((current - before) / before * 100, 2) if before > 0 and current > 0 else None
                summary["metrics"][key] = item[key]
            admitted_yoy = item.get("admitted_yoy_rate")
            candidate_yoy = item.get("candidate_yoy_rate")
            comparison_parts: list[str] = []
            if admitted_yoy is not None:
                comparison_parts.append(
                    f"录取人数同比{'增长' if admitted_yoy > 0 else '下降' if admitted_yoy < 0 else '持平'} {abs(admitted_yoy)}%"
                )
            if candidate_yoy is not None:
                comparison_parts.append(
                    f"生源明细同比{'增长' if candidate_yoy > 0 else '下降' if candidate_yoy < 0 else '持平'} {abs(candidate_yoy)}%"
                )
            if not comparison_parts:
                comparison_parts.append("上一年度缺少可比基数，同比不适用")
            impacts = [abs(float(value)) for value in (admitted_yoy, candidate_yoy) if value is not None]
            summary["insights"].append(
                {
                    "year_no": item["year_no"],
                    "title": f"{item['year_no']}年同比变化",
                    "finding": "；".join(comparison_parts) + "。",
                    "analysis": "同比变化用于识别规模突变，但计划缺失、覆盖率不足或统计版本变化时，百分比不能单独作为市场结论。",
                    "suggestion": "先确认两年口径一致，再对变化较大的省份、科类和专业下钻，避免把补数或改口径误判成趋势。",
                    "risk_level": "medium" if impacts and max(impacts) >= 10 else "low",
                    "evidence": ["fact.plan", "fact.admission_record", "fact.admission_record"],
                }
            )
        previous = item

    cross_year = _cross_year_insights(trend, scope=scope)
    provider = "deterministic"

    selected_insights = list(selected_summary.get("insights") or [])
    return {
        "scope": scope,
        "provider": provider,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "years": available_years,
        "selected_year": selected_year,
        "trend": trend,
        "year_summaries": summaries,
        "cross_year_insights": cross_year,
        "insights": selected_insights + cross_year,
    }


