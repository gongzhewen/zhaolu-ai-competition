import hashlib
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from app.core.text import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.data_change import notify_data_changed
from app.models.dbf_import import DbfImportBatch, DbfImportRow, DbfImportTable
from app.modules.canonicalization import service as canonicalization


def _candidate_key(ksh: str) -> str:
    secret = settings.jwt_secret.get_secret_value()
    return hashlib.sha256(f"{secret}:{ksh}".encode("utf-8")).hexdigest()


def _year_from_ksh(ksh: str) -> int:
    if ksh and ksh[:2].isdigit():
        value = int(ksh[:2])
        if 20 <= value <= 30:
            return 2000 + value
    return datetime.now().year


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    text_value = str(value).strip()
    if not text_value:
        return None
    try:
        return float(text_value)
    except ValueError:
        return None


def _date_or_none(value: Any) -> date | None:
    if value is None:
        return None
    text_value = str(value).strip()
    if not text_value:
        return None
    try:
        return date.fromisoformat(text_value)
    except ValueError:
        return None


async def _load_rows(
    db: AsyncSession,
    batch_id: int,
    table_name: str,
) -> list[dict[str, Any]]:
    result = await db.execute(
        select(DbfImportRow.raw_data)
        .join(DbfImportTable, DbfImportRow.table_id == DbfImportTable.id)
        .where(
            DbfImportRow.batch_id == batch_id,
            DbfImportTable.table_name == table_name.lower(),
        )
        .order_by(DbfImportRow.row_no)
    )
    return [dict(row[0]) for row in result.all()]


def _simple_map(rows: list[dict], code_key: str, name_key: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in rows:
        code = _clean(row.get(code_key))
        name = _clean(row.get(name_key))
        if code and name:
            mapping[code] = name
    return mapping


async def _clear_business_data(db: AsyncSession) -> None:
    await db.execute(
        text("""
            TRUNCATE TABLE
                fact.admission_summary,
                fact.admission_record,
                fact.score_line,
                fact.consultation,
                fact.channel_touch,
                fact.source_quality,
                fact.metric_snapshot,
                fact.plan,
                fact.candidate_profile,
                fact.exam_subject_score,
                fact.major_choice,
                fact.candidate_resume,
                fact.medical_summary,
                dim.region,
                dim.policy,
                dim.channel,
                dim.plan_type,
                dim.batch,
                dim.subject,
                dim.major,
                dim.province,
                dim.year,
                dim.school
            RESTART IDENTITY CASCADE
            """
        )
    )
    await db.execute(text("TRUNCATE TABLE gov.import_record, gov.etl_job, gov.data_issue RESTART IDENTITY"))
    await db.execute(
        text(
            "TRUNCATE TABLE ai.feedback, ai.tool_call, ai.message, ai.conversation RESTART IDENTITY CASCADE"
        )
    )
    await db.commit()


async def normalize_dbf_batch(
    db: AsyncSession,
    *,
    batch_id: int,
    clear_existing: bool = True,
) -> dict:
    if clear_existing:
        await _clear_business_data(db)

    batch = await db.scalar(select(DbfImportBatch).where(DbfImportBatch.id == batch_id))
    if batch is None:
        raise ValueError("DBF 导入批次不存在")

    xbdm = _simple_map(await _load_rows(db, batch_id, "td_xbdm"), "XBDM", "XBMC")
    mzdm = _simple_map(await _load_rows(db, batch_id, "td_mzdm"), "MZDM", "MZMC")
    kslx = _simple_map(await _load_rows(db, batch_id, "td_kslxdm"), "KSLXDM", "KSLXMC")
    wyyz = _simple_map(await _load_rows(db, batch_id, "td_wyyzdm"), "WYYZDM", "WYYZMC")
    hjlbdm = _simple_map(await _load_rows(db, batch_id, "td_hjlbdm"), "HJLBDM", "HJLBMC")
    dqdm_rows = await _load_rows(db, batch_id, "td_dqdm")
    dqdm = _simple_map(dqdm_rows, "DQDM", "DQMC")
    pcdm = _simple_map(await _load_rows(db, batch_id, "td_pcdm"), "PCDM", "PCMC")
    kldm = _simple_map(await _load_rows(db, batch_id, "td_kldm"), "KLDM", "KLMC")
    jhlbdm = _simple_map(await _load_rows(db, batch_id, "td_jhlbdm"), "JHLBDM", "JHLBMC")
    kmdm = _simple_map(await _load_rows(db, batch_id, "td_kmdm"), "KMDM", "KMMC")
    tjjl = _simple_map(await _load_rows(db, batch_id, "td_tjjldm"), "TJJLDM", "TJJLMC")
    lqlx = _simple_map(await _load_rows(db, batch_id, "td_lqlxdm"), "LQLXDM", "LQLXMC")

    tddw_rows = await _load_rows(db, batch_id, "t_tddw")
    tddw_map = _simple_map(tddw_rows, "TDDWDM", "TDDWMC")

    zydh_rows = await _load_rows(db, batch_id, "td_zydh")
    zydhdm_rows = await _load_rows(db, batch_id, "td_zydhdmdz")
    zydm_map = {
        (str(row.get("ZYDH") or ""), str(row.get("KLDM") or "")): _clean(row.get("ZYDM"))
        for row in zydhdm_rows
    }
    major_defs: dict[tuple[str, str], dict] = {}
    for row in zydh_rows:
        key = (str(row.get("ZYDH") or ""), str(row.get("KLDM") or ""))
        major_defs[key] = row

    plan_rows = await _load_rows(db, batch_id, "t_jhk")
    admission_rows = await _load_rows(db, batch_id, "t_tdd")
    year_no = _year_from_ksh(str(admission_rows[0].get("KSH", ""))) if admission_rows else datetime.now().year

    used_batch_codes = {
        str(row.get("PCDM") or "") for row in plan_rows + admission_rows if row.get("PCDM")
    }
    used_subject_codes = {
        str(row.get("KLDM") or "") for row in plan_rows + admission_rows if row.get("KLDM")
    }
    used_plan_type_codes = {
        str(row.get("JHLBDM") or "") for row in plan_rows + admission_rows if row.get("JHLBDM")
    }
    used_major_keys = {
        (str(row.get("ZYDH") or ""), str(row.get("KLDM") or ""))
        for row in plan_rows
        if row.get("ZYDH") and row.get("KLDM")
    }
    for row in admission_rows:
        if row.get("LQZY") and row.get("KLDM"):
            used_major_keys.add((str(row["LQZY"]), str(row["KLDM"])))

    if batch.school_id is None:
        await db.execute(
            text("INSERT INTO dim.school (school_code, school_name, school_type) VALUES ('DBF-2026', 'DBF原始数据院校', 'UNDERGRADUATE') ON CONFLICT DO NOTHING")
        )
        batch.school_id = await db.scalar(text("SELECT id FROM dim.school WHERE school_code = 'DBF-2026'"))
    await db.execute(
        text("INSERT INTO dim.year (year_no) VALUES (:year_no) ON CONFLICT (year_no) DO NOTHING"),
        {"year_no": year_no},
    )
    await db.execute(
        text("INSERT INTO dim.province (province_code, province_name) VALUES ('430000', '湖南') ON CONFLICT (province_code) DO NOTHING")
    )
    for code in used_batch_codes:
        await db.execute(
            text("INSERT INTO dim.batch (year_id, batch_code, batch_name) SELECT id, :code, :name FROM dim.year WHERE year_no = :year_no ON CONFLICT (year_id, batch_code) DO NOTHING"),
            {"code": code, "name": pcdm.get(code, code), "year_no": year_no},
        )
    for code in used_subject_codes:
        await db.execute(
            text("INSERT INTO dim.subject (subject_code, subject_name) VALUES (:code, :name) ON CONFLICT (subject_code) DO NOTHING"),
            {"code": code, "name": kldm.get(code, code)},
        )
    for code in used_plan_type_codes:
        await db.execute(
            text("INSERT INTO dim.plan_type (type_code, type_name) VALUES (:code, :name) ON CONFLICT (type_code) DO NOTHING"),
            {"code": code, "name": jhlbdm.get(code, code)},
        )

    for row in dqdm_rows:
        code = _clean(row.get("DQDM"))
        name = _clean(row.get("DQMC"))
        if code and name:
            await db.execute(
                text(
                    "INSERT INTO dim.region (region_code, region_name, data_version) "
                    "VALUES (:code, :name, 'dbf-2026-v1') "
                    "ON CONFLICT (region_code) DO NOTHING"
                ),
                {"code": code, "name": name},
            )

    school_id = batch.school_id
    year_id = await db.scalar(text("SELECT id FROM dim.year WHERE year_no = :year_no"), {"year_no": year_no})
    province_id = await db.scalar(text("SELECT id FROM dim.province WHERE province_code = '430000'"))

    for key in sorted(used_major_keys):
        zydh, kl = key
        definition = major_defs.get(key, {})
        actual_code = zydm_map.get(key)
        major_code = actual_code or zydh
        major_code = f"{major_code}-{zydh}-{kl}"
        major_name = _clean(definition.get("ZYMC")) or f"专业{zydh}"
        await db.execute(
            text(
                """
                INSERT INTO dim.major (
                    school_id, major_code, major_name, major_group, subject_req, is_active
                )
                VALUES (
                    :school_id, :major_code, :major_name, :major_group, :subject_req, TRUE
                )
                ON CONFLICT (school_id, major_code) DO NOTHING
                """
            ),
            {
                "school_id": school_id,
                "major_code": major_code,
                "major_name": major_name,
                "major_group": zydh,
                "subject_req": _clean(definition.get("CURR_ZYMC")),
            },
        )
    await db.commit()

    batch_ids = {
        row["batch_code"]: row["id"]
        for row in (
            await db.execute(text("SELECT id, batch_code FROM dim.batch WHERE year_id = :year_id"), {"year_id": year_id})
        ).mappings().all()
    }
    subject_ids = {
        row["subject_code"]: row["id"]
        for row in (await db.execute(text("SELECT id, subject_code FROM dim.subject"))).mappings().all()
    }
    plan_type_ids = {
        row["type_code"]: row["id"]
        for row in (await db.execute(text("SELECT id, type_code FROM dim.plan_type"))).mappings().all()
    }
    major_ids = {
        (row["major_group"], row["major_code"].split("-")[0]): row["id"]
        for row in (
            await db.execute(text("SELECT id, major_group, major_code FROM dim.major WHERE school_id = :school_id"), {"school_id": school_id})
        ).mappings().all()
    }
    major_id_by_key = {}
    for row in (
        await db.execute(text("SELECT id, major_code FROM dim.major WHERE school_id = :school_id"), {"school_id": school_id})
    ).mappings().all():
        parts = row["major_code"].split("-")
        if len(parts) >= 3:
            major_id_by_key[(parts[-2], parts[-1])] = row["id"]

    canonical_major_ids: dict[int, int] = {}
    canonical_major_names: dict[int, str] = {}
    canonicalization_events: set[tuple[str, str, str]] = set()
    for row in (
        await db.execute(
            text("SELECT id, major_name FROM dim.major WHERE school_id = :school_id"),
            {"school_id": school_id},
        )
    ).mappings().all():
        canonical_id, canonical_name = await canonicalization.resolve_major(
            db,
            school_id=school_id,
            value=row["major_name"],
            province_id=province_id,
            pipeline="dbf_import",
            create_if_missing=False,
            event_cache=canonicalization_events,
        )
        canonical_major_ids[int(row["id"])] = canonical_id
        canonical_major_names[int(row["id"])] = canonical_name
    await db.commit()

    plan_aggregates: dict[tuple[str, str, str, str], dict] = defaultdict(lambda: {"plan_count": 0})
    for row in plan_rows:
        pcdm_code = str(row.get("PCDM") or "")
        kl_code = str(row.get("KLDM") or "")
        jhlb_code = str(row.get("JHLBDM") or "")
        zydh_code = str(row.get("ZYDH") or "")
        key = (pcdm_code, kl_code, jhlb_code, zydh_code)
        plan_count = row.get("JHZXS") or row.get("JHRS") or 0
        try:
            plan_aggregates[key]["plan_count"] += int(float(plan_count))
        except (TypeError, ValueError):
            pass

    plan_id_by_key: dict[tuple[str, str, str, str], int] = {}
    for key, aggregate in plan_aggregates.items():
        pcdm_code, kl_code, jhlb_code, zydh_code = key
        major_id = major_id_by_key.get((zydh_code, kl_code))
        if major_id is None:
            continue
        major_id = canonical_major_ids.get(major_id, major_id)
        plan_params = {
            "school_id": school_id,
            "year_id": year_id,
            "province_id": province_id,
            "batch_id": batch_ids.get(pcdm_code),
            "subject_id": subject_ids.get(kl_code),
            "major_id": major_id,
            "plan_type_id": plan_type_ids.get(jhlb_code),
            "plan_count": aggregate["plan_count"],
            "data_version": "dbf-2026-v1",
        }
        plan_id = await execute_returning_id(
            db,
            """
            INSERT INTO fact.plan (
                school_id, year_id, province_id, batch_id, subject_id, major_id,
                plan_type_id, plan_count, data_version
            )
            VALUES (
                :school_id, :year_id, :province_id, :batch_id, :subject_id, :major_id,
                :plan_type_id, :plan_count, :data_version
            )
            RETURNING id
            """,
            plan_params,
            mysql_select="""
                SELECT id
                FROM fact.plan
                WHERE school_id=:school_id AND year_id=:year_id AND province_id=:province_id
                  AND batch_id <=> :batch_id AND subject_id <=> :subject_id AND major_id=:major_id
                  AND plan_type_id <=> :plan_type_id AND data_version=:data_version
                ORDER BY id DESC
                LIMIT 1
            """,
        )
        if plan_id is not None:
            plan_id_by_key[key] = int(plan_id)

    admission_aggregates: dict[tuple[str, str, str, str], dict] = defaultdict(
        lambda: {"count": 0, "scores": []}
    )
    for row in admission_rows:
        pcdm_code = str(row.get("PCDM") or "")
        kl_code = str(row.get("KLDM") or "")
        jhlb_code = str(row.get("JHLBDM") or "")
        zydh_code = str(row.get("LQZY") or "")
        score = row.get("TDCJ")
        aggregate = admission_aggregates[(pcdm_code, kl_code, jhlb_code, zydh_code)]
        aggregate["count"] += 1
        try:
            aggregate["scores"].append(float(score))
        except (TypeError, ValueError):
            pass

    for key, aggregate in admission_aggregates.items():
        plan_id = plan_id_by_key.get(key)
        if plan_id is None:
            continue
        scores = aggregate["scores"]
        await db.execute(
            text(
                """
                INSERT INTO fact.admission_summary (
                    plan_id, admitted_count, min_score, avg_score, max_score, data_version
                )
                VALUES (
                    :plan_id, :admitted_count, :min_score, :avg_score, :max_score, 'dbf-2026-v1'
                )
                """
            ),
            {
                "plan_id": plan_id,
                "admitted_count": aggregate["count"],
                "min_score": min(scores) if scores else None,
                "avg_score": round(sum(scores) / len(scores), 2) if scores else None,
                "max_score": max(scores) if scores else None,
            },
        )

    for row in admission_rows:
        ksh = _clean(row.get("KSH"))
        if not ksh:
            continue
        pcdm_code = str(row.get("PCDM") or "")
        kl_code = str(row.get("KLDM") or "")
        jhlb_code = str(row.get("JHLBDM") or "")
        zydh_code = str(row.get("LQZY") or "")
        major_id = major_id_by_key.get((zydh_code, kl_code))
        if major_id is None:
            continue
        major_id = canonical_major_ids.get(major_id, major_id)
        await db.execute(
            text(
                """
                INSERT INTO fact.admission_record (
                    candidate_key, year_id, province_id, batch_id, subject_id, major_id,
                    channel_id, score, rank_no, volunteer_order, admit_type, is_enrolled, data_version
                )
                VALUES (
                    :candidate_key, :year_id, :province_id, :batch_id, :subject_id, :major_id,
                    NULL, :score, NULL, :volunteer_order, :admit_type, TRUE, 'dbf-2026-v1'
                )
                """
            ),
            {
                "candidate_key": _candidate_key(ksh),
                "year_id": year_id,
                "province_id": province_id,
                "batch_id": batch_ids.get(pcdm_code),
                "subject_id": subject_ids.get(kl_code),
                "major_id": major_id,
                "score": _float_or_none(row.get("TDCJ")),
                "volunteer_order": int(row["LQXH"]) if isinstance(row.get("LQXH"), (int, float)) else None,
                "admit_type": lqlx.get(str(row.get("LQLXDM") or ""), _clean(row.get("LQLXDM"))),
            },
        )
    await db.commit()

    bmk_rows = await _load_rows(db, batch_id, "t_bmk")
    profile_params = []
    for row in bmk_rows:
        ksh = _clean(row.get("KSH"))
        if not ksh:
            continue
        profile_params.append(
            {
                "candidate_key": _candidate_key(ksh),
                "year_no": _year_from_ksh(ksh),
                "region_code": _clean(row.get("DQDM")),
                "region_name": dqdm.get(str(row.get("DQDM") or "")),
                "gender_code": _clean(row.get("XBDM")),
                "gender_name": xbdm.get(str(row.get("XBDM") or "")),
                "ethnicity_code": _clean(row.get("MZDM")),
                "ethnicity_name": mzdm.get(str(row.get("MZDM") or "")),
                "exam_type_code": _clean(row.get("KSLXDM")),
                "exam_type_name": kslx.get(str(row.get("KSLXDM") or "")),
                "subject_category_code": _clean(row.get("KLDM")),
                "candidate_type_code": _clean(row.get("KSLBDM")),
                "foreign_language_code": _clean(row.get("WYYZDM")),
                "source_school_code": _clean(row.get("BYXXDM")),
                "source_school_name": _clean(row.get("BYXXMC")),
                "household_type_code": _clean(row.get("HJLBDM")),
                "data_version": "dbf-2026-v1",
            }
        )
    if profile_params:
        await db.execute(
            text(
                """
                INSERT INTO fact.candidate_profile (
                    candidate_key, year_no, region_code, region_name,
                    gender_code, gender_name, ethnicity_code, ethnicity_name,
                    exam_type_code, exam_type_name, subject_category_code,
                    candidate_type_code, foreign_language_code,
                    source_school_code, source_school_name,
                    household_type_code, data_version
                ) VALUES (
                    :candidate_key, :year_no, :region_code, :region_name,
                    :gender_code, :gender_name, :ethnicity_code, :ethnicity_name,
                    :exam_type_code, :exam_type_name, :subject_category_code,
                    :candidate_type_code, :foreign_language_code,
                    :source_school_code, :source_school_name,
                    :household_type_code, :data_version
                )
                """
            ),
            profile_params,
        )
        await db.commit()

    score_rows = await _load_rows(db, batch_id, "t_ksxkcj")
    score_params = []
    for row in score_rows:
        ksh = _clean(row.get("KSH"))
        subject_code = _clean(row.get("KMDM"))
        if not ksh or not subject_code:
            continue
        score_params.append(
            {
                "candidate_key": _candidate_key(ksh),
                "year_no": _year_from_ksh(ksh),
                "exam_number": _clean(row.get("XKBMH")),
                "subject_code": subject_code,
                "subject_name": kmdm.get(subject_code),
                "score_type": _clean(row.get("CJLX")),
                "exam_year_month": _clean(row.get("KSNY")),
                "score": _float_or_none(row.get("DJFF")),
                "grade_point": _float_or_none(row.get("DDCJ")),
                "data_version": "dbf-2026-v1",
            }
        )
    for start in range(0, len(score_params), 5000):
        await db.execute(
            text(
                """
                INSERT INTO fact.exam_subject_score (
                    candidate_key, year_no, exam_number, subject_code, subject_name,
                    score_type, exam_year_month, score, grade_point, data_version
                ) VALUES (
                    :candidate_key, :year_no, :exam_number, :subject_code, :subject_name,
                    :score_type, :exam_year_month, :score, :grade_point, :data_version
                )
                """
            ),
            score_params[start:start + 5000],
        )
    await db.commit()

    choice_rows = await _load_rows(db, batch_id, "t_zykmx")
    choice_params = []
    for row in choice_rows:
        ksh = _clean(row.get("KSH"))
        if not ksh:
            continue
        zydh_code = str(row.get("ZYDH") or "")
        kl_code = str(row.get("KLDM") or "")
        definition = major_defs.get((zydh_code, kl_code), {})
        actual_code = zydm_map.get((zydh_code, kl_code))
        source_major_id = major_id_by_key.get((zydh_code, kl_code))
        canonical_major_name = canonical_major_names.get(source_major_id, _clean(definition.get("ZYMC")))
        choice_params.append(
            {
                "candidate_key": _candidate_key(ksh),
                "year_no": _year_from_ksh(ksh),
                "batch_code": _clean(row.get("PCDM")),
                "subject_code": _clean(row.get("KLDM")),
                "plan_type_code": _clean(row.get("JHLBDM")),
                "group_code": _clean(row.get("TDDWDM")),
                "choice_order": row.get("ZYXH"),
                "major_code": actual_code or zydh_code,
                "major_name": canonical_major_name,
                "data_version": "dbf-2026-v1",
            }
        )
    for start in range(0, len(choice_params), 5000):
        await db.execute(
            text(
                """
                INSERT INTO fact.major_choice (
                    candidate_key, year_no, batch_code, subject_code, plan_type_code,
                    group_code, choice_order, major_code, major_name, data_version
                ) VALUES (
                    :candidate_key, :year_no, :batch_code, :subject_code, :plan_type_code,
                    :group_code, :choice_order, :major_code, :major_name, :data_version
                )
                """
            ),
            choice_params[start:start + 5000],
        )
    await db.commit()

    resume_rows = await _load_rows(db, batch_id, "t_ksjl")
    resume_params = []
    for row in resume_rows:
        ksh = _clean(row.get("KSH"))
        if not ksh:
            continue
        resume_params.append(
            {
                "candidate_key": _candidate_key(ksh),
                "year_no": _year_from_ksh(ksh),
                "start_date": _date_or_none(row.get("QSRQ")),
                "end_date": _date_or_none(row.get("ZJRQ")),
                "school_name": _clean(row.get("JL")),
                "role_name": _clean(row.get("RHZW")),
                "award_name": None,
                "data_version": "dbf-2026-v1",
            }
        )
    for start in range(0, len(resume_params), 5000):
        await db.execute(
            text(
                """
                INSERT INTO fact.candidate_resume (
                    candidate_key, year_no, start_date, end_date,
                    school_name, role_name, award_name, data_version
                ) VALUES (
                    :candidate_key, :year_no, CAST(:start_date AS date), CAST(:end_date AS date),
                    :school_name, :role_name, :award_name, :data_version
                )
                """
            ),
            resume_params[start:start + 5000],
        )
    await db.commit()

    medical_rows = await _load_rows(db, batch_id, "t_tjxx")
    medical_params = []
    for row in medical_rows:
        ksh = _clean(row.get("KSH"))
        if not ksh:
            continue
        restrictions = [
            _clean(row.get(f"ZYSXDM{i}"))
            for i in range(1, 7)
            if _clean(row.get(f"ZYSXDM{i}"))
        ]
        medical_params.append(
            {
                "candidate_key": _candidate_key(ksh),
                "year_no": _year_from_ksh(ksh),
                "medical_result_code": _clean(row.get("TJJLDM")),
                "medical_result_name": tjjl.get(str(row.get("TJJLDM") or "")),
                "restricted_major_codes": restrictions,
                "data_version": "dbf-2026-v1",
            }
        )
    if medical_params:
        for start in range(0, len(medical_params), 5000):
            await db.execute(
                text(
                    """
                    INSERT INTO fact.medical_summary (
                        candidate_key, year_no, medical_result_code,
                        medical_result_name, restricted_major_codes, data_version
                    ) VALUES (
                        :candidate_key, :year_no, :medical_result_code,
                        :medical_result_name, CAST(:restricted_major_codes AS jsonb), :data_version
                    )
                    """
                ),
                [
                    {
                        **item,
                        "restricted_major_codes": __import__("json").dumps(item["restricted_major_codes"], ensure_ascii=False),
                    }
                    for item in medical_params[start:start + 5000]
                ],
            )
        await db.commit()

    await notify_data_changed(batch.school_id)
    return {
        "batch_id": batch_id,
        "year_no": year_no,
        "candidate_profiles": len(profile_params),
        "plans": len(plan_id_by_key),
        "admissions": len(admission_rows),
        "subject_scores": len(score_params),
        "major_choices": len(choice_params),
        "resumes": len(resume_params),
        "medical_summaries": len(medical_params),
    }



