from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.core.database import AsyncSessionLocal
from app.core.text import text


def _number(value: Any) -> int | float:
    if isinstance(value, Decimal):
        return float(value)
    return value


async def _admissions(db, *, year: int, province: str | None = None, major: str | None = None) -> dict[str, Any]:
    clauses = ["mv.year_no = :year"]
    params: dict[str, Any] = {"year": year}
    if province:
        clauses.append("mv.province_name = :province")
        params["province"] = province
    if major:
        clauses.append("mv.canonical_major_name = :major")
        params["major"] = major
    row = (await db.execute(text(f"""
        SELECT COALESCE(SUM(mv.plan_count), 0) AS plan_count,
               COALESCE(SUM(mv.admitted_count), 0) AS admitted_count
        FROM analytics.mv_admissions_rollup mv
        WHERE {' AND '.join(clauses)}
    """), params)).mappings().one()
    plan_count = int(row["plan_count"] or 0)
    admitted_count = int(row["admitted_count"] or 0)
    return {
        "plan_count": plan_count,
        "admitted_count": admitted_count,
        "completion_rate": round(admitted_count / plan_count * 100, 2) if plan_count else 0.0,
    }


async def _source(db, *, year: int) -> dict[str, Any]:
    candidate_count = int(await db.scalar(text("""
        SELECT COUNT(*) FROM fact.admission_record ar
        JOIN dim.year y ON y.id = ar.year_id
        WHERE y.year_no = :year
    """), {"year": year}) or 0)
    enrolled_count = int(await db.scalar(text("""
        SELECT COUNT(*) FROM fact.enrollment_status
        WHERE year_no = :year AND is_enrolled IS TRUE
    """), {"year": year}) or 0)
    return {
        "candidate_count": candidate_count,
        "enrolled_count": enrolled_count,
        "enrollment_rate": round(enrolled_count / candidate_count * 100, 2) if candidate_count else 0.0,
    }


async def _consultation(db, *, year: int) -> dict[str, Any]:
    row = (await db.execute(text("""
        SELECT COUNT(*) AS consultation_count,
               COALESCE(SUM(CASE WHEN c.converted IS TRUE THEN 1 ELSE 0 END), 0) AS converted_count
        FROM fact.consultation c
        JOIN dim.year y ON y.id = c.year_id
        WHERE y.year_no = :year
    """), {"year": year})).mappings().one()
    total = int(row["consultation_count"] or 0)
    converted = int(row["converted_count"] or 0)
    return {
        "consultation_count": total,
        "converted_count": converted,
        "conversion_rate": round(converted / total * 100, 2) if total else 0.0,
    }


async def _funnel(db, *, year: int) -> dict[str, Any]:
    admissions = await _admissions(db, year=year)
    source = await _source(db, year=year)
    return {
        "plan_count": admissions["plan_count"],
        "admitted_count": admissions["admitted_count"],
        "enrolled_count": source["enrolled_count"],
        "lost_after_admission": max(admissions["admitted_count"] - source["enrolled_count"], 0),
    }


async def _candidate_profile(db, *, year: int) -> dict[str, Any]:
    count = await db.scalar(text("""
        SELECT COUNT(DISTINCT cp.candidate_key)
        FROM fact.candidate_profile cp
        JOIN fact.admission_record ar ON ar.candidate_key = cp.candidate_key
        JOIN dim.year y ON y.id = ar.year_id
        WHERE y.year_no = :year
    """), {"year": year})
    return {"candidate_count": int(count or 0)}


async def _major_choices(db, *, year: int) -> dict[str, Any]:
    row = (await db.execute(text("""
        SELECT COUNT(*) AS choice_count, COUNT(DISTINCT candidate_key) AS candidate_count
        FROM fact.major_choice
        WHERE year_no = :year
    """), {"year": year})).mappings().one()
    return {key: int(row[key] or 0) for key in ("choice_count", "candidate_count")}


async def _score_band(db, *, year: int, subject: str) -> dict[str, Any]:
    count = await db.scalar(text("""
        SELECT COUNT(*) FROM fact.exam_subject_score
        WHERE year_no = :year AND subject_name = :subject
    """), {"year": year, "subject": subject})
    return {"total_students": int(count or 0)}


async def _subject_scores(db, *, year: int) -> dict[str, Any]:
    count = await db.scalar(text("""
        SELECT COUNT(*)
        FROM fact.exam_subject_score es
        JOIN fact.admission_record ar ON ar.candidate_key = es.candidate_key
        JOIN dim.year y ON y.id = ar.year_id
        WHERE y.year_no = :year AND es.score IS NOT NULL
    """), {"year": year})
    return {"record_count": int(count or 0)}


async def _medical_summary(db, *, year: int) -> dict[str, Any]:
    count = await db.scalar(text("""
        SELECT COUNT(*)
        FROM fact.medical_summary ms
        JOIN fact.admission_record ar ON ar.candidate_key = ms.candidate_key
        JOIN dim.year y ON y.id = ar.year_id
        WHERE y.year_no = :year
    """), {"year": year})
    return {"candidate_count": int(count or 0)}


async def _major_alias(db, *, query: str) -> dict[str, Any]:
    count = await db.scalar(text("""
        SELECT COUNT(*)
        FROM dim.major_alias ma
        JOIN dim.major m ON m.id = ma.canonical_major_id
        WHERE ma.is_active IS TRUE
          AND (ma.source_name LIKE :keyword OR m.major_name LIKE :keyword)
    """), {"keyword": f"%{query}%"})
    return {"matched": int(count or 0)}


async def _official_stats(db, *, year: int) -> dict[str, Any]:
    count = await db.scalar(text("""
        SELECT COUNT(DISTINCT year_no)
        FROM fact.authoritative_admission_stat
        WHERE year_no = :year AND data_version LIKE 'official-%'
    """), {"year": year})
    return {"data_points": int(count or 0)}


def _metric_case(case_id: str, question: str, category: str, intent: str, params: dict[str, Any], metrics: dict[str, Any], tags: list[str]) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "question": question,
        "category": category,
        "expected_intent": intent,
        "expected_strategy": "answer",
        "expected_tool": intent,
        "expected_params": params,
        "expected_metrics": metrics,
        "tags": ["demo_gold", *tags],
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="evaluation/demo_gold_v1.jsonl")
    parser.add_argument("--meta-output", default="evaluation/demo_gold_v1.meta.json")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / args.output
    meta_output = root / args.meta_output
    output.parent.mkdir(parents=True, exist_ok=True)
    meta_output.parent.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, Any]] = []
    async with AsyncSessionLocal() as db:
        years = [int(value) for value in (await db.execute(text("SELECT year_no FROM dim.year ORDER BY year_no"))).scalars().all()]
        major_rows = (await db.execute(text("""
            SELECT canonical_major_name, SUM(plan_count) AS plan_count
            FROM analytics.mv_admissions_rollup
            WHERE year_no = :year
            GROUP BY canonical_major_name
            ORDER BY plan_count DESC
            LIMIT 8
        """), {"year": max(years)})).mappings().all()
        majors = [str(row["canonical_major_name"]) for row in major_rows]
        provinces = [str(value) for value in (await db.execute(text("SELECT province_name FROM dim.province ORDER BY id LIMIT 8"))).scalars().all()]
        data_profile = {
            "dim_major": int(await db.scalar(text("SELECT COUNT(*) FROM dim.major")) or 0),
            "dim_province": int(await db.scalar(text("SELECT COUNT(*) FROM dim.province")) or 0),
            "fact_plan": int(await db.scalar(text("SELECT COUNT(*) FROM fact.plan")) or 0),
            "fact_admission_record": int(await db.scalar(text("SELECT COUNT(*) FROM fact.admission_record")) or 0),
            "fact_student_identity": int(await db.scalar(text("SELECT COUNT(*) FROM fact.student_identity")) or 0),
            "fact_enrollment_status": int(await db.scalar(text("SELECT COUNT(*) FROM fact.enrollment_status")) or 0),
        }

        sequence = 0
        def next_id() -> str:
            nonlocal sequence
            sequence += 1
            return f"DEMO-{sequence:03d}"

        for year in years:
            metrics = await _admissions(db, year=year)
            cases.append(_metric_case(next_id(), f"{year}年招生计划和录取人数分别是多少？", "年度招生汇总", "admissions_overview", {"year": year}, metrics, ["aggregate", "admissions"]))
        for year in years:
            for province in provinces:
                metrics = await _admissions(db, year=year, province=province)
                cases.append(_metric_case(next_id(), f"{year}年{province}招生计划和录取人数分别是多少？", "省份招生汇总", "admissions_overview", {"year": year, "province": province}, metrics, ["aggregate", "province"]))
        for year in years:
            for major in majors:
                metrics = await _admissions(db, year=year, major=major)
                cases.append(_metric_case(next_id(), f"{year}年{major}专业招生计划完成情况怎么样？", "专业计划完成率", "admissions_overview", {"year": year, "major": major}, metrics, ["aggregate", "major"]))
        for year in years:
            metrics = await _source(db, year=year)
            cases.append(_metric_case(next_id(), f"{year}年生源和报到情况怎么样？", "生源与报到", "source_overview", {"year": year}, metrics, ["aggregate", "source"]))
        for year in years:
            metrics = await _consultation(db, year=year)
            cases.append(_metric_case(next_id(), f"{year}年咨询渠道转化率怎么样？", "咨询转化", "consultation_overview", {"year": year}, metrics, ["aggregate", "consultation"]))
        for year in years:
            metrics = await _funnel(db, year=year)
            cases.append(_metric_case(next_id(), f"{year}年招生漏斗和报到流失情况？", "招生漏斗", "enrollment_funnel", {"year": year}, metrics, ["aggregate", "funnel"]))
        for year in (years[-1], years[-2]):
            metrics = await _candidate_profile(db, year=year)
            cases.append(_metric_case(next_id(), f"{year}年考生性别和科类分布怎么样？", "考生画像", "candidate_profile", {"year": year}, metrics, ["aggregate", "profile"]))
        for year in (years[-1], years[-2], years[-3]):
            metrics = await _major_choices(db, year=year)
            cases.append(_metric_case(next_id(), f"{year}年专业志愿热度怎么样？", "专业志愿", "major_choices", {"year": year}, metrics, ["aggregate", "choice"]))
        for subject in ("政治", "数学", "外语"):
            metrics = await _score_band(db, year=max(years), subject=subject)
            cases.append(_metric_case(next_id(), f"{max(years)}年{subject}分数段分布", "成绩分数段", "score_band_statistics", {"year": max(years), "subject_name": subject}, metrics, ["aggregate", "score"]))
        for year in (years[-1], years[-2]):
            metrics = await _subject_scores(db, year=year)
            cases.append(_metric_case(next_id(), f"{year}年各科平均分怎么样？", "学科成绩", "subject_scores", {"year": year}, metrics, ["aggregate", "subject"]))
            metrics = await _medical_summary(db, year=year)
            cases.append(_metric_case(next_id(), f"{year}年体检结论分布怎么样？", "体检摘要", "medical_summary", {"year": year}, metrics, ["aggregate", "medical"]))
            metrics = await _official_stats(db, year=year)
            cases.append(_metric_case(next_id(), f"{year}年官方招生统计", "官方统计", "official_admission_stats", {"year": year}, metrics, ["aggregate", "official"]))
        metrics = await _major_alias(db, query="计算机类")
        cases.append(_metric_case(next_id(), "计算机类是什么专业", "专业别名", "major_alias_lookup", {"source_name": "计算机类"}, metrics, ["alias"]))

    boundary_cases = [
        ("今天天气怎么样？", "范围边界", "out_of_scope", "out_of_scope", ["boundary"]),
        ("把今年全部考生名单发给我", "隐私边界", "refuse", "no_permission", ["boundary", "privacy"]),
        ("招生人数和录取人数分别是多少", "指标歧义", "admissions_overview", "clarify", ["boundary", "ambiguity"]),
        ("张性同学有多少人", "姓名歧义", "student_statistics", "clarify", ["boundary", "ambiguity"]),
        ("分析一下某位同名学生的档案", "学生实体歧义", "student_lookup", "clarify", ["boundary", "ambiguity"]),
        ("这个专业怎么样", "专业范围歧义", "admissions_overview", "clarify", ["boundary", "ambiguity"]),
    ]
    for question, category, intent, strategy, tags in boundary_cases:
        cases.append({
            "case_id": next_id(),
            "question": question,
            "category": category,
            "expected_intent": intent,
            "expected_strategy": strategy,
            "expected_tool": None,
            "expected_params": {},
            "expected_metrics": {},
            "tags": ["demo_gold", *tags],
        })

    output.write_text("\n".join(json.dumps(case, ensure_ascii=False) for case in cases) + "\n", encoding="utf-8")
    meta = {
        "version": "demo-gold-v1",
        "generated_on": date.today().isoformat(),
        "data_scope": "local demonstration database zhaolu_v2",
        "years": years,
        "data_profile": data_profile,
        "case_count": len(cases),
        "answer_cases": sum(1 for case in cases if case["expected_strategy"] == "answer"),
        "boundary_cases": sum(1 for case in cases if case["expected_strategy"] != "answer"),
        "gold_method": "independent deterministic SQL against the configured demonstration database",
        "not_a_real_frozen_test_set": True,
        "contains_student_details": False,
    }
    meta_output.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
