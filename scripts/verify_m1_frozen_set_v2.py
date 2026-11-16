from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.core.database import AsyncSessionLocal, rewrite_mysql_schemas

YEARS = {"calibration": {2022, 2023}, "test": {2024, 2025}}
CATEGORIES = {
    "单条件统计", "多条件筛选", "跨年趋势与比较", "计划完成率", "录取报到与流失",
    "专业别名和口语表达", "成绩与分数段", "志愿和生源画像", "缺失无数据与歧义",
    "隐私小样本与超范围",
}
PII_PATTERNS = {
    "id_18": re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
    "phone_11": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "pii_field": re.compile(r'"(?:student_name|candidate_name|id_card|id_number|phone|mobile|email|姓名|身份证号|手机号)"\s*:', re.I),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def norm(value: str) -> str:
    return re.sub(r"\s+", "", value)


async def execute(db, sql: str, params: dict[str, Any] | None = None):
    return await db.execute(text(rewrite_mysql_schemas(sql)), params or {})


async def one(db, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict((await execute(db, sql, params)).mappings().one())


def filters(year: int, province: str | None = None, major: str | None = None) -> tuple[str, dict[str, Any]]:
    clauses = ["y.year_no=:year"]
    params: dict[str, Any] = {"year": year}
    if province:
        clauses.append("pr.province_name=:province")
        params["province"] = province
    if major:
        clauses.append("m.major_name=:major")
        params["major"] = major
    return " AND ".join(clauses), params


async def admissions_metrics(db, *, year: int, province: str | None = None, major: str | None = None) -> dict[str, Any]:
    where, params = filters(year, province, major)
    plan = await one(db, f"""
        SELECT COALESCE(SUM(p.plan_count),0) AS plan_count
        FROM fact.plan p JOIN dim.year y ON y.id=p.year_id
        JOIN dim.province pr ON pr.id=p.province_id JOIN dim.major m ON m.id=p.major_id
        WHERE {where}
    """, params)
    admitted = await one(db, f"""
        SELECT COUNT(*) AS admitted_count
        FROM fact.admission_record ar JOIN dim.year y ON y.id=ar.year_id
        JOIN dim.province pr ON pr.id=ar.province_id JOIN dim.major m ON m.id=ar.major_id
        WHERE {where}
    """, params)
    plan_count = int(plan["plan_count"] or 0)
    admitted_count = int(admitted["admitted_count"] or 0)
    completion = round(admitted_count / plan_count * 100, 2) if plan_count else 0.0
    return {"plan_count": plan_count, "admitted_count": admitted_count, "completion_rate": completion}


async def record_metrics(db, *, year: int, province: str | None = None, major: str | None = None) -> dict[str, Any]:
    where, params = filters(year, province, major)
    row = await one(db, f"""
        SELECT COUNT(*) AS admitted_count,
               COALESCE(SUM(CASE WHEN ar.is_enrolled=1 THEN 1 ELSE 0 END),0) AS enrolled_count,
               MAX(ar.score) AS max_score, MIN(ar.score) AS min_score,
               ROUND(AVG(ar.score),2) AS avg_score,
               MIN(ar.rank_no) AS min_rank_no, MAX(ar.rank_no) AS max_rank_no,
               ROUND(AVG(ar.rank_no),2) AS avg_rank_no,
               COALESCE(SUM(CASE WHEN cp.gender_name='男' THEN 1 ELSE 0 END),0) AS male_count,
               COALESCE(SUM(CASE WHEN cp.gender_name='女' THEN 1 ELSE 0 END),0) AS female_count
        FROM fact.admission_record ar JOIN dim.year y ON y.id=ar.year_id
        JOIN dim.province pr ON pr.id=ar.province_id JOIN dim.major m ON m.id=ar.major_id
        LEFT JOIN fact.candidate_profile cp ON cp.candidate_key=ar.candidate_key AND cp.year_no=y.year_no
        WHERE {where}
    """, params)
    admitted = int(row["admitted_count"] or 0)
    enrolled = int(row["enrolled_count"] or 0)
    result = {key: (float(value) if isinstance(value, Decimal) else value) for key, value in row.items() if key not in {"admitted_count", "enrolled_count"}}
    result.update({
        "admitted_count": admitted,
        "enrolled_count": enrolled,
        "enrollment_rate": round(enrolled / admitted * 100, 2) if admitted else 0.0,
        "lost_after_admission": max(admitted - enrolled, 0),
    })
    return result


async def choice_metrics(db, *, year: int, major: str | None = None) -> dict[str, Any]:
    clauses = ["mc.year_no=:year"]
    params: dict[str, Any] = {"year": year}
    if major:
        clauses.append("m.major_name=:major")
        params["major"] = major
    row = await one(db, f"""
        SELECT COUNT(*) AS choice_count, COUNT(DISTINCT mc.candidate_key) AS applicant_count
        FROM fact.major_choice mc JOIN dim.major m ON m.major_code=mc.major_code
        WHERE {' AND '.join(clauses)}
    """, params)
    return {"choice_count": int(row["choice_count"] or 0), "applicant_count": int(row["applicant_count"] or 0)}


async def official_metrics(db, *, year: int) -> dict[str, Any]:
    row = await one(db, """
        SELECT COALESCE(SUM(plan_count),0) AS official_plan_count,
               COALESCE(SUM(regular_admitted_count),0) AS official_regular_admitted,
               COALESCE(SUM(zhuan_admitted_count),0) AS official_zhuan_admitted,
               COALESCE(SUM(total_admitted_count),0) AS official_total_admitted
        FROM fact.authoritative_admission_stat WHERE year_no=:year
    """, {"year": year})
    return {key: int(value or 0) for key, value in row.items()}

async def alias_value(db, source_name: str) -> dict[str, Any]:
    row = await one(db, """
        SELECT m.major_name AS canonical_major
        FROM dim.major_alias ma JOIN dim.major m ON m.id=ma.canonical_major_id
        WHERE ma.is_active=1 AND ma.source_name=:source_name
        ORDER BY ma.id LIMIT 1
    """, {"source_name": source_name})
    return {"canonical_major": str(row["canonical_major"])}


async def score_band(db, *, year: int, subject_name: str, band_start: int) -> dict[str, Any]:
    row = await one(db, """
        SELECT COUNT(*) AS student_count
        FROM fact.exam_subject_score
        WHERE year_no=:year AND subject_name=:subject_name AND score IS NOT NULL
          AND FLOOR(score/10)*10=:band_start
    """, {"year": year, "subject_name": subject_name, "band_start": band_start})
    return {"student_count": int(row["student_count"] or 0), "band_start": band_start, "band_end": band_start + 9}


async def recompute_answer(db, case: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    category = case["category"]
    params = case["expected_params"]
    expected = case["expected_metrics"]
    values: dict[str, Any] = {}
    metrics: dict[str, Any] = {}
    if category == "单条件统计":
        year = int(params["year"])
        metrics = {**await admissions_metrics(db, year=year), **await record_metrics(db, year=year), **await choice_metrics(db, year=year), **await official_metrics(db, year=year)}
    elif category == "多条件筛选":
        year = int(params["year"])
        metrics = {**await admissions_metrics(db, year=year, province=params["province"], major=params["major"]), **await record_metrics(db, year=year, province=params["province"], major=params["major"])}
    elif category == "计划完成率":
        metrics = await admissions_metrics(db, year=int(params["year"]), major=params["major"])
    elif category == "录取报到与流失":
        metrics = await record_metrics(db, year=int(params["year"]), province=params["province"])
    elif category == "跨年趋势与比较":
        metric = case["tags"][1]
        start = await admissions_metrics(db, year=int(params["start_year"]), major=params["major"])
        end = await admissions_metrics(db, year=int(params["end_year"]), major=params["major"])
        start_rec = await record_metrics(db, year=int(params["start_year"]), major=params["major"])
        end_rec = await record_metrics(db, year=int(params["end_year"]), major=params["major"])
        first = {"plan_count": start["plan_count"], "admitted_count": start["admitted_count"], "enrolled_count": start_rec["enrolled_count"]}[metric]
        second = {"plan_count": end["plan_count"], "admitted_count": end["admitted_count"], "enrolled_count": end_rec["enrolled_count"]}[metric]
        metrics = {"start_value": first, "end_value": second, "delta": second - first, "delta_rate": round((second - first) / first * 100, 2) if first else 0.0}
    elif category == "专业别名和口语表达":
        values = await alias_value(db, params["source_name"])
    elif category == "成绩与分数段":
        metrics = await score_band(db, year=int(params["year"]), subject_name=params["subject_name"], band_start=int(expected["band_start"]))
    elif category == "志愿和生源画像":
        if "choice_count" in expected:
            metrics = await choice_metrics(db, year=int(params["year"]), major=params["major"])
        else:
            record = await record_metrics(db, year=int(params["year"]), province=params["province"])
            metrics = {"male_count": record["male_count"], "female_count": record["female_count"]}
    else:
        raise ValueError(f"unexpected answer category: {category}")
    return metrics, values


def compare_case(case: dict[str, Any], actual_metrics: dict[str, Any], actual_values: dict[str, Any]) -> list[str]:
    issues = []
    for key, expected in case["expected_metrics"].items():
        actual = actual_metrics.get(key)
        tolerance = float(case["allowed_error"].get(key, 0))
        if isinstance(expected, float) or isinstance(actual, float):
            if actual is None or abs(float(actual) - float(expected)) > tolerance + 1e-9:
                issues.append(f"{key}: expected {expected}, actual {actual}, tolerance {tolerance}")
        elif actual != expected:
            issues.append(f"{key}: expected {expected}, actual {actual}")
    for key, expected in case["expected_values"].items():
        if actual_values.get(key) != expected:
            issues.append(f"{key}: expected {expected}, actual {actual_values.get(key)}")
    return issues


async def verify_no_data_condition(db, case: dict[str, Any]) -> list[str]:
    tag = case["tags"][-1]
    question = case["question"]
    if tag == "年度无数据":
        year_match = re.search(r"(20\d{2})年", question)
        year = int(year_match.group(1)) if year_match else None
        if year is None:
            return ["cannot parse year from no_data case"]
        row = await one(db, """
            SELECT
              (SELECT COUNT(*) FROM fact.plan p JOIN dim.year y ON y.id=p.year_id WHERE y.year_no=:year) AS plans,
              (SELECT COUNT(*) FROM fact.admission_record ar JOIN dim.year y ON y.id=ar.year_id WHERE y.year_no=:year) AS records
        """, {"year": year})
        if int(row["plans"] or 0) or int(row["records"] or 0):
            return [f"no_data year {year} unexpectedly has plan or admission rows"]
    elif tag in {"省份不存在", "专业不存在"}:
        name = re.sub(r"^20\d{2}年", "", question)
        name = re.split(r"招生计划|录取数|招生人数", name)[0]
        table = "dim.province" if tag == "省份不存在" else "dim.major"
        column = "province_name" if tag == "省份不存在" else "major_name"
        row = await one(db, f"SELECT COUNT(*) AS count FROM {table} WHERE {column}=:name", {"name": name})
        if int(row["count"] or 0):
            return [f"{tag} target unexpectedly exists: {name}"]
    return []

def structural_checks(data_root: Path, project_root: Path, calibration: list[dict[str, Any]], test: list[dict[str, Any]], gold_cal: list[dict[str, Any]], gold_test: list[dict[str, Any]]) -> list[str]:
    issues = []
    if len(calibration) != 120 or len(test) != 120:
        issues.append(f"unexpected split sizes: calibration={len(calibration)}, test={len(test)}")
    for split, cases, gold in (("calibration", calibration, gold_cal), ("test", test, gold_test)):
        if len(cases) != len(gold):
            issues.append(f"{split}: benchmark/gold count mismatch")
        category_counts = Counter(case["category"] for case in cases)
        if set(category_counts) != CATEGORIES or any(count != 12 for count in category_counts.values()):
            issues.append(f"{split}: invalid category balance {dict(category_counts)}")
        ids = [case["case_id"] for case in cases]
        questions = [norm(case["question"]) for case in cases]
        if len(ids) != len(set(ids)):
            issues.append(f"{split}: duplicate case_id")
        if len(questions) != len(set(questions)):
            issues.append(f"{split}: duplicate question text")
        gold_by_id = {case["case_id"]: case for case in gold}
        if set(ids) != set(gold_by_id):
            issues.append(f"{split}: benchmark/gold case ids differ")
        for case in cases:
            if case.get("source_scope") != "authorized_real_source_local_anonymized_snapshot":
                issues.append(f"{case['case_id']}: invalid source_scope")
            gold_case = gold_by_id.get(case["case_id"])
            if not gold_case:
                continue
            if gold_case.get("question") != case.get("question") or gold_case.get("category") != case.get("category"):
                issues.append(f"{case['case_id']}: benchmark/gold metadata mismatch")
            if gold_case.get("expected_strategy") not in {"answer", "clarify", "insufficient_data", "no_data", "no_permission", "out_of_scope", "refuse"}:
                issues.append(f"{case['case_id']}: invalid strategy")
            if gold_case.get("acceptable_strategies") != [gold_case.get("expected_strategy")]:
                issues.append(f"{case['case_id']}: acceptable_strategies mismatch")
            if gold_case.get("expected_strategy") == "answer":
                years = {int(value) for key, value in gold_case.get("expected_params", {}).items() if key.endswith("year") and isinstance(value, int)}
                if years and not years <= YEARS[split]:
                    issues.append(f"{case['case_id']}: answer-bearing years {sorted(years)} violate {split} split")
                if not years and case['category'] != "专业别名和口语表达":
                    issues.append(f"{case['case_id']}: answer-bearing case has no split year")
                if not gold_case.get("expected_metrics") and not gold_case.get("expected_values"):
                    issues.append(f"{case['case_id']}: answer case has no gold values")
            else:
                if gold_case.get("expected_metrics") or gold_case.get("expected_values"):
                    issues.append(f"{case['case_id']}: boundary case unexpectedly has answer values")
    cal_questions = {norm(case["question"]) for case in calibration}
    test_questions = {norm(case["question"]) for case in test}
    if cal_questions & test_questions:
        issues.append(f"cross-split question overlap: {len(cal_questions & test_questions)}")
    cal_params = {json.dumps(case.get("required_slots", {}), ensure_ascii=False, sort_keys=True) for case in calibration if case.get("required_slots")}
    test_params = {json.dumps(case.get("required_slots", {}), ensure_ascii=False, sort_keys=True) for case in test if case.get("required_slots")}
    if cal_params & test_params:
        issues.append(f"cross-split data-parameter overlap: {len(cal_params & test_params)}")
    cal_aliases = {case["required_slots"].get("source_name") for case in calibration if case["category"] == "专业别名和口语表达"}
    test_aliases = {case["required_slots"].get("source_name") for case in test if case["category"] == "专业别名和口语表达"}
    if cal_aliases & test_aliases:
        issues.append(f"cross-split alias overlap: {sorted(cal_aliases & test_aliases)}")
    all_files = [
        data_root / "benchmark" / "real_calibration_v2.jsonl",
        data_root / "benchmark" / "real_frozen_test_v2.jsonl",
        data_root / "gold" / "real_calibration_gold_v2.jsonl",
        data_root / "gold" / "real_frozen_test_gold_v2.jsonl",
        data_root / "benchmark" / "m1_split_policy_v2.json",
        data_root / "gold" / "m1_gold_manifest_v2.json",
    ]
    for path in all_files:
        text_content = path.read_text(encoding="utf-8")
        for name, pattern in PII_PATTERNS.items():
            if pattern.search(text_content):
                issues.append(f"{path.name}: sensitive pattern {name} detected")
    gitignore = (project_root / ".gitignore").read_text(encoding="utf-8")
    dockerignore = (project_root / ".dockerignore").read_text(encoding="utf-8")
    if "local_private/" not in gitignore:
        issues.append(".gitignore does not exclude local_private/")
    if "local_private/" not in dockerignore:
        issues.append(".dockerignore does not exclude local_private/")
    builder = (project_root / "scripts" / "build_competition_submission.py").read_text(encoding="utf-8")
    if "local_private" in builder:
        issues.append("submission builder references local_private")
    copied_roots = ("apps", "packages", "scripts", "tests", "deploy", "infra")
    for root_name in copied_roots:
        for path in (project_root / root_name).rglob("*"):
            if path.is_file() and path.name in {"2022.xlsx", "2023.xlsx", "2024.xlsx", "2025.xlsx", "2026.xlsx", ".env.root"}:
                issues.append(f"private source file is inside copied package root: {path}")
    return issues


def hash_checks(data_root: Path) -> tuple[list[str], dict[str, Any]]:
    issues = []
    summary = json.loads((data_root / "results" / "M1_build_summary_v2.json").read_text(encoding="utf-8"))
    manifest = json.loads((data_root / "gold" / "m1_gold_manifest_v2.json").read_text(encoding="utf-8"))
    file_hashes = {}
    for name in summary["file_sha256"]:
        path = data_root / ("benchmark" if name.startswith("real_calibration_v2") or name.startswith("real_frozen_test_v2") or name.startswith("m1_split") else "gold") / name
        if not path.exists():
            issues.append(f"hash target missing: {name}")
            continue
        file_hashes[name] = sha256(path)
        if file_hashes[name] != summary["file_sha256"][name]:
            issues.append(f"hash mismatch: {name}")
    case_set_hash = hashlib.sha256(json.dumps(file_hashes, sort_keys=True).encode("utf-8")).hexdigest()
    if case_set_hash != summary["case_set_sha256"]:
        issues.append("case_set_sha256 mismatch")
    source_identity = [{"file": item["file"], "bytes": item["bytes"], "sha256": item["sha256"]} for item in manifest["source_files"]]
    snapshot_payload = json.dumps({"source_files": source_identity, "data_profile": manifest["data_profile"]}, sort_keys=True, ensure_ascii=False)
    snapshot_id = hashlib.sha256(snapshot_payload.encode("utf-8")).hexdigest()
    if snapshot_id != manifest["data_snapshot_id"] or snapshot_id != summary["data_snapshot_id"]:
        issues.append("data_snapshot_id mismatch")
    return issues, {"file_sha256": file_hashes, "case_set_sha256": case_set_hash, "data_snapshot_id": snapshot_id}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=r"D:\Backup\Documents\ChatGPT\Desktop\_m1_v2_stage")
    parser.add_argument("--project-root", default=r"C:\Users\Administrator\Desktop\招录智策_国赛开发")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    data_root = Path(args.data_root)
    project_root = Path(args.project_root)
    benchmark_dir = data_root / "benchmark"
    gold_dir = data_root / "gold"
    calibration = load_jsonl(benchmark_dir / "real_calibration_v2.jsonl")
    test = load_jsonl(benchmark_dir / "real_frozen_test_v2.jsonl")
    gold_cal = load_jsonl(gold_dir / "real_calibration_gold_v2.jsonl")
    gold_test = load_jsonl(gold_dir / "real_frozen_test_gold_v2.jsonl")

    issues = structural_checks(data_root, project_root, calibration, test, gold_cal, gold_test)
    hash_issues, hash_report = hash_checks(data_root)
    issues.extend(hash_issues)
    per_case = []
    async with AsyncSessionLocal() as db:
        for case in [*gold_cal, *gold_test]:
            if case["expected_strategy"] != "answer":
                boundary_issues = await verify_no_data_condition(db, case)
                status = "passed" if not boundary_issues else "failed"
                per_case.append({"case_id": case["case_id"], "category": case["category"], "strategy": case["expected_strategy"], "status": status, "issues": boundary_issues})
                issues.extend(f"{case['case_id']}: {issue}" for issue in boundary_issues)
                continue
            metrics, values = await recompute_answer(db, case)
            case_issues = compare_case(case, metrics, values)
            status = "passed" if not case_issues else "failed"
            per_case.append({"case_id": case["case_id"], "category": case["category"], "strategy": "answer", "status": status, "issues": case_issues})
            issues.extend(f"{case['case_id']}: {issue}" for issue in case_issues)

    status_counts = Counter(item["status"] for item in per_case)
    strategy_counts = Counter(case["expected_strategy"] for case in [*gold_cal, *gold_test])
    report = {
        "version": "m1-verification-v2",
        "verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "passed" if not issues else "failed",
        "case_count": 240,
        "answer_cases_recalculated": sum(1 for case in [*gold_cal, *gold_test] if case["expected_strategy"] == "answer"),
        "boundary_cases_reviewed": sum(1 for case in [*gold_cal, *gold_test] if case["expected_strategy"] != "answer"),
        "status_counts": dict(status_counts),
        "strategy_counts": dict(strategy_counts),
        "hash_checks": hash_report,
        "issues": issues,
        "per_case": per_case,
        "review_boundary": {
            "technical_recalculation": "passed" if not issues else "failed",
            "human_domain_signoff": "pending",
            "signed_authorization_document": "not_provided",
        },
    }
    output = Path(args.output) if args.output else data_root / "results" / "M1_verification_report_v2.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "case_count", "answer_cases_recalculated", "boundary_cases_reviewed", "status_counts", "issues")}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not issues else 1)


if __name__ == "__main__":
    asyncio.run(main())

