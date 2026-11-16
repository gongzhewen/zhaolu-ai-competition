import hashlib
from typing import Any

from app.core.text import text
from app.core.db_compat import execute_returning_row
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings


def _candidate_key(ksh: str) -> str:
    secret = settings.jwt_secret.get_secret_value()
    return hashlib.sha256(f"{secret}:{ksh}".encode("utf-8")).hexdigest()


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


async def _load_raw_bmk(db: AsyncSession) -> list[dict[str, Any]]:
    result = await db.execute(
        text("""
            SELECT
                r.raw_data->>'KSH' AS ksh,
                r.raw_data->>'ZKZH' AS zkzh,
                r.raw_data->>'XM' AS student_name,
                r.raw_data->>'XBDM' AS gender_code,
                r.raw_data->>'KLDM' AS subject_code,
                r.raw_data->>'BYXXMC' AS source_school,
                r.raw_data->>'DQDM' AS region_code,
                r.raw_data->>'WYYZDM' AS foreign_language_code,
                r.raw_data->>'MZDM' AS ethnicity_code,
                r.raw_data->>'KSLXDM' AS exam_type_code,
                r.raw_data->>'ZJHM' AS id_card,
                r.raw_data->>'LXSJ' AS phone,
                r.raw_data->>'TXDZ' AS address
            FROM gov.dbf_import_row r
            JOIN gov.dbf_import_table t ON t.id = r.table_id
            WHERE r.batch_id = 1 AND t.table_name = 't_bmk'
            ORDER BY r.row_no
            """
        )
    )
    return [dict(row) for row in result.mappings().all()]


async def _load_profiles(
    db: AsyncSession,
    *,
    year: int | None = None,
) -> list[dict[str, Any]]:
    result = await db.execute(
        text(
            """
            SELECT candidate_key, year_no, data_version,
                   region_code, region_name, gender_code, gender_name,
                   ethnicity_name, exam_type_name, subject_category_code,
                   source_school_name
            FROM fact.candidate_profile
            WHERE (CAST(:year AS integer) IS NULL OR year_no = :year)
            ORDER BY year_no DESC, candidate_key
            """),
        {"year": year},
    )
    return [dict(row) for row in result.mappings().all()]


async def _load_admissions(
    db: AsyncSession,
    *,
    year: int | None = None,
) -> dict[str, dict[str, Any]]:
    result = await db.execute(
        text("""
            SELECT
                ar.candidate_key,
                y.year_no,
                ar.exam_score,
                ar.score AS filing_score,
                m.major_name,
                b.batch_name,
                s.subject_name
            FROM fact.admission_record ar
            JOIN dim.year y ON y.id = ar.year_id
            LEFT JOIN dim.major m ON m.id = ar.major_id
            LEFT JOIN dim.batch b ON b.id = ar.batch_id
            LEFT JOIN dim.subject s ON s.id = ar.subject_id
            WHERE (CAST(:year AS integer) IS NULL OR y.year_no = :year)
            """),
        {"year": year},
    )
    return {row["candidate_key"]: dict(row) for row in result.mappings().all()}


async def _load_management(
    db: AsyncSession,
    *,
    year: int | None = None,
) -> dict[str, dict[str, Any]]:
    result = await db.execute(
        text("""
            SELECT candidate_key, year_no, student_status, follow_up_status,
                   owner_name, tags, notes, updated_at
            FROM fact.student_management
            WHERE (CAST(:year AS integer) IS NULL OR year_no = :year)
            """),
        {"year": year},
    )
    return {row["candidate_key"]: dict(row) for row in result.mappings().all()}


async def _load_identities(
    db: AsyncSession,
    *,
    year: int | None = None,
) -> dict[tuple[str, int], dict[str, Any]]:
    result = await db.execute(
        text("""
            SELECT candidate_key, year_no, candidate_no, student_name,
                   id_card, phone, address, data_version
            FROM fact.student_identity
            WHERE (CAST(:year AS integer) IS NULL OR year_no = :year)
            """),
        {"year": year},
    )
    return {(row["candidate_key"], int(row["year_no"])): dict(row) for row in result.mappings().all()}


def _display_identity(
    candidate_key: str,
    year_no: int,
    raw: dict[str, Any] | None,
    identity: dict[str, Any] | None = None,
) -> tuple[str, str]:
    if identity and identity.get("student_name"):
        return str(identity["student_name"]), str(identity.get("candidate_no") or "")
    if raw and raw.get("student_name"):
        return str(raw["student_name"]), str(raw.get("ksh") or "")
    suffix = candidate_key[:8].upper()
    return f"模拟考生-{suffix}", f"SYN-{year_no}-{suffix}"


def _gender_name(code: str | None) -> str:
    return {"1": "男", "2": "女"}.get(code or "", "未知")


def _subject_name(code: str | None) -> str:
    return {"W": "物理类", "L": "历史类", "Z": "职高对口类"}.get(code or "", code or "未知")


def _exam_type_name(code: str | None, profile: dict[str, Any] | None) -> str:
    if profile and profile.get("exam_type_name"):
        return str(profile["exam_type_name"])
    return {"1": "普高统考", "3": "职高对口考试"}.get(code or "", code or "未知")


async def list_students(
    db: AsyncSession,
    *,
    year: int | None = None,
    keyword: str | None = None,
    region_code: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    profile_rows = await _load_profiles(db, year=year)
    admissions = await _load_admissions(db, year=year)
    management = await _load_management(db, year=year)
    raw_rows = await _load_raw_bmk(db)
    raw_by_key = {
        _candidate_key(str(row["ksh"])): row
        for row in raw_rows
        if _clean(row.get("ksh"))
    }
    identities = await _load_identities(db, year=year)

    items = []
    keyword_lower = keyword.lower().strip() if keyword else None
    for profile in profile_rows:
        key = str(profile["candidate_key"])
        year_no = int(profile["year_no"])
        raw = raw_by_key.get(key)
        admission = admissions.get(key) or {}
        manage = management.get(key) or {}
        identity = identities.get((key, year_no))
        student_name, candidate_no = _display_identity(key, year_no, raw, identity)
        item = {
            "candidate_key": key,
            "candidate_no": candidate_no,
            "year_no": year_no,
            "is_synthetic": str(profile.get("data_version") or "").startswith("synthetic-"),
            "student_name": student_name,
            "gender": profile.get("gender_name") or _gender_name(raw.get("gender_code") if raw else None),
            "subject": _subject_name(profile.get("subject_category_code")),
            "exam_type": _exam_type_name(raw.get("exam_type_code") if raw else None, profile),
            "source_school": profile.get("source_school_name") or (raw.get("source_school") if raw else None),
            "region_code": profile.get("region_code") or (raw.get("region_code") if raw else None),
            "region_name": profile.get("region_name"),
            "exam_score": admission.get("exam_score"),
            "filing_score": admission.get("filing_score"),
            "major_name": admission.get("major_name"),
            "batch_name": admission.get("batch_name"),
            "student_status": manage.get("student_status") or "NEW",
            "follow_up_status": manage.get("follow_up_status") or "PENDING",
            "owner_name": manage.get("owner_name"),
            "tags": manage.get("tags") or [],
            "updated_at": manage.get("updated_at"),
        }
        if keyword_lower:
            haystack = " ".join(
                str(item.get(field) or "")
                for field in ("student_name", "candidate_no", "source_school", "region_name", "major_name")
            ).lower()
            if keyword_lower not in haystack:
                continue
        if region_code and item["region_code"] != region_code:
            continue
        if status and item["student_status"] != status:
            continue
        items.append(item)

    items.sort(
        key=lambda item: (
            -int(item["year_no"]),
            -float(item["filing_score"] or 0),
            str(item["student_name"] or ""),
        )
    )
    total = len(items)
    start = max(0, (page - 1) * page_size)
    return {
        "items": items[start:start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
        "year_no": year,
    }

async def get_student_detail(db: AsyncSession, candidate_key: str) -> dict[str, Any] | None:
    raw_rows = await _load_raw_bmk(db)
    raw_by_key = {
        _candidate_key(str(row["ksh"])): row
        for row in raw_rows
        if _clean(row.get("ksh"))
    }
    profile_result = await db.execute(
        text("""
            SELECT candidate_key, year_no, data_version, region_code, region_name,
                   gender_code, gender_name, ethnicity_code, ethnicity_name,
                   exam_type_code, exam_type_name, subject_category_code,
                   candidate_type_code, foreign_language_code,
                   source_school_code, source_school_name, household_type_code
            FROM fact.candidate_profile
            WHERE candidate_key = :candidate_key
            """),
        {"candidate_key": candidate_key},
    )
    profile = profile_result.mappings().one_or_none()
    if profile is None:
        return None

    year_no = int(profile["year_no"])
    raw = raw_by_key.get(candidate_key)
    identity = (await _load_identities(db, year=year_no)).get((candidate_key, year_no))
    student_name, candidate_no = _display_identity(candidate_key, year_no, raw, identity)
    basic = {
        **(dict(raw) if raw else {}),
        **(dict(identity) if identity else {}),
        "student_name": student_name,
        "ksh": candidate_no,
        "year_no": year_no,
        "data_version": profile["data_version"],
        "is_synthetic": str(profile["data_version"]).startswith("synthetic-"),
    }

    admission_result = await db.execute(
        text("""
            SELECT ar.exam_score, ar.score AS filing_score, m.major_name, b.batch_name, s.subject_name
            FROM fact.admission_record ar
            JOIN dim.year y ON y.id = ar.year_id
            LEFT JOIN dim.major m ON m.id = ar.major_id
            LEFT JOIN dim.batch b ON b.id = ar.batch_id
            LEFT JOIN dim.subject s ON s.id = ar.subject_id
            WHERE ar.candidate_key = :candidate_key AND y.year_no = :year_no
            LIMIT 1
            """),
        {"candidate_key": candidate_key, "year_no": year_no},
    )
    admission = admission_result.mappings().one_or_none()

    management_result = await db.execute(
        text("""
            SELECT student_status, follow_up_status, owner_name, tags, notes, updated_at
            FROM fact.student_management
            WHERE candidate_key = :candidate_key AND year_no = :year_no
            """),
        {"candidate_key": candidate_key, "year_no": year_no},
    )
    management = management_result.mappings().one_or_none()

    subject_result = await db.execute(
        text("""
            SELECT subject_name, subject_code, score, exam_year_month
            FROM fact.exam_subject_score
            WHERE candidate_key = :candidate_key AND year_no = :year_no
            ORDER BY subject_code
            """),
        {"candidate_key": candidate_key, "year_no": year_no},
    )
    choice_result = await db.execute(
        text("""
            SELECT choice_order, major_name, major_code
            FROM fact.major_choice
            WHERE candidate_key = :candidate_key AND year_no = :year_no
            ORDER BY choice_order
            """),
        {"candidate_key": candidate_key, "year_no": year_no},
    )
    resume_result = await db.execute(
        text("""
            SELECT start_date, end_date, school_name, role_name
            FROM fact.candidate_resume
            WHERE candidate_key = :candidate_key AND year_no = :year_no
            ORDER BY start_date
            """),
        {"candidate_key": candidate_key, "year_no": year_no},
    )
    medical_result = await db.execute(
        text("""
            SELECT medical_result_code, medical_result_name, restricted_major_codes
            FROM fact.medical_summary
            WHERE candidate_key = :candidate_key AND year_no = :year_no
            """),
        {"candidate_key": candidate_key, "year_no": year_no},
    )
    medical = medical_result.mappings().one_or_none()

    return {
        "candidate_key": candidate_key,
        "basic": basic,
        "profile": dict(profile),
        "admission": dict(admission) if admission else None,
        "management": dict(management) if management else {
            "student_status": "NEW",
            "follow_up_status": "PENDING",
            "owner_name": None,
            "tags": [],
            "notes": None,
            "updated_at": None,
        },
        "subject_scores": [dict(row) for row in subject_result.mappings().all()],
        "major_choices": [dict(row) for row in choice_result.mappings().all()],
        "resumes": [dict(row) for row in resume_result.mappings().all()],
        "medical_summary": dict(medical) if medical else None,
    }

async def upsert_management(
    db: AsyncSession,
    *,
    candidate_key: str,
    year_no: int,
    user_id: int,
    student_status: str | None,
    follow_up_status: str | None,
    owner_name: str | None,
    tags: list[str] | None,
    notes: str | None,
) -> dict[str, Any]:
    updated = await execute_returning_row(
        db,
        """
        INSERT INTO fact.student_management (
            candidate_key, year_no, student_status, follow_up_status,
            owner_name, tags, notes, updated_by_user_id, updated_at
        )
        VALUES (
            :candidate_key, :year_no, COALESCE(:student_status, 'NEW'),
            COALESCE(:follow_up_status, 'PENDING'), :owner_name,
            COALESCE(CAST(:tags AS jsonb), '[]'::jsonb), :notes, :user_id, now()
        )
        ON CONFLICT (candidate_key) DO UPDATE SET
            year_no = EXCLUDED.year_no,
            student_status = COALESCE(:student_status, fact.student_management.student_status),
            follow_up_status = COALESCE(:follow_up_status, fact.student_management.follow_up_status),
            owner_name = COALESCE(:owner_name, fact.student_management.owner_name),
            tags = COALESCE(CAST(:tags AS jsonb), fact.student_management.tags),
            notes = COALESCE(:notes, fact.student_management.notes),
            updated_by_user_id = :user_id,
            updated_at = now()
        RETURNING candidate_key, student_status, follow_up_status,
                  owner_name, tags, notes, updated_at
        """,
        {
            "candidate_key": candidate_key,
            "year_no": year_no,
            "student_status": student_status,
            "follow_up_status": follow_up_status,
            "owner_name": owner_name,
            "tags": __import__("json").dumps(tags, ensure_ascii=False) if tags is not None else None,
            "notes": notes,
            "user_id": user_id,
        },
        mysql_select="""
            SELECT candidate_key, student_status, follow_up_status,
                   owner_name, tags, notes, updated_at
            FROM fact.student_management
            WHERE candidate_key=:candidate_key
            LIMIT 1
        """,
    )
    await db.commit()
    return updated or {}


async def get_student_summary(
    db: AsyncSession,
    *,
    year: int | None = None,
) -> dict[str, Any]:
    metrics_result = await db.execute(
        text("""
            WITH candidates AS (
                SELECT
                    cp.candidate_key,
                    cp.data_version,
                    COALESCE(sm.student_status, 'NEW') AS student_status,
                    COALESCE(sm.follow_up_status, 'PENDING') AS follow_up_status
                FROM fact.candidate_profile cp
                LEFT JOIN fact.student_management sm
                  ON sm.candidate_key = cp.candidate_key
                 AND sm.year_no = cp.year_no
                WHERE (CAST(:year AS integer) IS NULL OR cp.year_no = :year)
            )
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE student_status = 'NEW') AS new_count,
                COUNT(*) FILTER (WHERE student_status = 'CONTACTED') AS contacted_count,
                COUNT(*) FILTER (WHERE student_status = 'ADMITTED') AS admitted_count,
                COUNT(*) FILTER (WHERE student_status = 'ENROLLED') AS enrolled_count,
                COUNT(*) FILTER (WHERE follow_up_status = 'PENDING') AS pending_count,
                COUNT(*) FILTER (WHERE follow_up_status = 'IN_PROGRESS') AS in_progress_count,
                COUNT(*) FILTER (WHERE data_version LIKE 'synthetic-%') AS synthetic_count
            FROM candidates
            """),
        {"year": year},
    )
    metrics = metrics_result.mappings().one()

    regions_result = await db.execute(
        text("""
            SELECT
                COALESCE(region_code, 'UNKNOWN') AS region_code,
                COALESCE(region_name, '未知') AS region_name,
                COUNT(*) AS count
            FROM fact.candidate_profile
            WHERE (CAST(:year AS integer) IS NULL OR year_no = :year)
            GROUP BY COALESCE(region_code, 'UNKNOWN'), COALESCE(region_name, '未知')
            ORDER BY count DESC
            LIMIT 12
            """),
        {"year": year},
    )
    return {
        "year_no": year,
        "metrics": {
            "total": int(metrics["total"] or 0),
            "new": int(metrics["new_count"] or 0),
            "contacted": int(metrics["contacted_count"] or 0),
            "admitted": int(metrics["admitted_count"] or 0),
            "enrolled": int(metrics["enrolled_count"] or 0),
            "pending": int(metrics["pending_count"] or 0),
            "in_progress": int(metrics["in_progress_count"] or 0),
            "synthetic": int(metrics["synthetic_count"] or 0),
        },
        "regions": [dict(row) for row in regions_result.mappings().all()],
    }


async def get_student_years(db: AsyncSession) -> dict[str, Any]:
    result = await db.execute(
        text(
            """
            SELECT
                year_no,
                COUNT(*) AS total,
                BOOL_OR(data_version LIKE 'synthetic-%') AS is_synthetic
            FROM fact.candidate_profile
            GROUP BY year_no
            ORDER BY year_no DESC
            """
        )
    )
    return {"items": [dict(row) for row in result.mappings().all()]}










