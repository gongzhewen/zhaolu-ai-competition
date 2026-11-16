import hashlib
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.text import text
from app.core.db_compat import execute_returning_id, is_mysql
from app.core.data_change import notify_data_changed
from app.core.database import AsyncSessionLocal
from app.models.dimension import Channel, School, Year
from app.models.ingestion import EtlJob, ImportFieldMapping, ImportRecord
from app.modules.ingestion.mapping import TARGET_TABLES, auto_map_headers, infer_data_type, validate_mapping, validate_rows
from app.modules.canonicalization import service as canonicalization
from app.modules.ingestion.parser import parse_table


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _auto_code(prefix: str, value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10].upper()
    return f"AUTO-{prefix}-{digest}"


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def _int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(float(str(value).replace(",", "")))


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(str(value).replace(",", ""))


def _date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text_value = str(value).strip()
    try:
        return date.fromisoformat(text_value[:10])
    except ValueError as exc:
        raise ValueError(f"无法转换为日期：{text_value}") from exc


def _datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    text_value = str(value).strip().replace("T", " ")
    if text_value.endswith("Z"):
        text_value = text_value[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text_value)
    except ValueError as exc:
        raise ValueError(f"无法转换为时间：{text_value}") from exc


def _candidate_key(job: EtlJob, record: dict[str, Any], row_no: int) -> str:
    raw_key = _clean(record.get("candidate_key"))
    if raw_key is None:
        raw_key = "|".join(
            str(record.get(field) or "")
            for field in ("year", "province", "major_name", "score", "rank_no", "volunteer_order")
        )
        raw_key = f"{raw_key}|{job.id}|{row_no}"
    secret = settings.jwt_secret.get_secret_value()
    return hashlib.sha256(f"{secret}:{raw_key}".encode("utf-8")).hexdigest()


async def create_import_job(
    db: AsyncSession,
    *,
    file_path: Path,
    original_name: str,
    file_size: int,
    source_type: str,
    data_type: str,
    year: int | None,
    data_version: str | None,
) -> EtlJob:
    preview_table = parse_table(file_path, max_rows=100)
    mapping, confidence = auto_map_headers(preview_table.headers)

    job = EtlJob(
        source_name=source_type,
        job_name=f"{data_type}:{original_name}",
        job_status="AWAITING_MAPPING",
        file_name=original_name,
        file_path=str(file_path),
        file_size=file_size,
        file_suffix=file_path.suffix.lower(),
        encoding=preview_table.encoding,
        sheet_name=preview_table.sheet_name,
        year_no=year,
        data_type=data_type,
        data_version=data_version,
        headers=preview_table.headers,
        preview_data=preview_table.rows,
        mapping_data=mapping,
        target_table=TARGET_TABLES.get(data_type),
    )
    db.add(job)
    await db.flush()

    for source_field, target_field in mapping.items():
        db.add(
            ImportFieldMapping(
                job_id=job.id,
                source_field=source_field,
                target_field=target_field,
                confidence=confidence.get(source_field, 0.0),
                confirmed=False,
            )
        )

    await db.commit()
    await db.refresh(job)
    return job


async def confirm_mapping_and_validate(
    db: AsyncSession,
    job: EtlJob,
    mapping: dict[str, str | None],
) -> EtlJob:
    if not job.file_path or not job.data_type:
        raise ValueError("导入任务缺少文件或数据类型")

    effective_data_type = infer_data_type(job.data_type or "admission", mapping)
    job.data_type = effective_data_type
    validate_mapping(effective_data_type, mapping)
    parsed = parse_table(Path(job.file_path))
    validated = validate_rows(effective_data_type, parsed.rows, mapping)

    await db.execute(delete(ImportRecord).where(ImportRecord.job_id == job.id))
    await db.execute(delete(ImportFieldMapping).where(ImportFieldMapping.job_id == job.id))

    valid_rows = 0
    invalid_rows = 0
    for row in validated:
        if row.errors:
            invalid_rows += 1
            status = "INVALID"
            error_message = "；".join(row.errors)
        else:
            valid_rows += 1
            status = "VALID"
            error_message = None

        db.add(
            ImportRecord(
                job_id=job.id,
                row_no=row.row_no,
                raw_data=row.raw_data,
                normalized_data=row.normalized_data,
                status=status,
                error_message=error_message,
            )
        )

    for source_field, target_field in mapping.items():
        db.add(
            ImportFieldMapping(
                job_id=job.id,
                source_field=source_field,
                target_field=target_field,
                confidence=1.0,
                confirmed=True,
            )
        )

    job.headers = parsed.headers
    job.mapping_data = mapping
    job.mapping_confirmed = True
    job.total_rows = len(validated)
    job.valid_rows = valid_rows
    job.invalid_rows = invalid_rows
    job.job_status = "READY_TO_IMPORT" if valid_rows > 0 else "VALIDATION_FAILED"
    job.error_message = None
    await db.commit()
    await db.refresh(job)
    return job


async def commit_import_job(job_id: int) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(EtlJob).where(EtlJob.id == job_id))
        job = result.scalar_one_or_none()
        if job is None:
            return
        if job.job_status in {"IMPORTING", "IMPORTED"}:
            return
        if not job.mapping_confirmed:
            job.job_status = "VALIDATION_FAILED"
            job.error_message = "字段映射尚未确认"
            await db.commit()
            return

        job.job_status = "IMPORTING"
        job.started_at = _now()
        job.error_message = None
        await db.commit()

        try:
            records_result = await db.execute(
                select(ImportRecord)
                .where(ImportRecord.job_id == job.id, ImportRecord.status == "VALID")
                .order_by(ImportRecord.row_no)
            )
            records = records_result.scalars().all()
            cache: dict[str, Any] = {
                "years": {},
                "provinces": {},
                "subjects": {},
                "batches": {},
                "schools": {},
                "majors": {},
                "plan_types": {},
                "channels": {},
                "canonicalization_events": set(),
            }
            for record in records:
                if not record.normalized_data:
                    continue
                await _publish_record(db, job, record.row_no, record.normalized_data, cache)

            job.job_status = "IMPORTED"
            job.finished_at = _now()
            await db.commit()
            await notify_data_changed()
        except Exception as exc:
            await db.rollback()
            failed = await db.execute(select(EtlJob).where(EtlJob.id == job_id))
            failed_job = failed.scalar_one_or_none()
            if failed_job is not None:
                failed_job.job_status = "IMPORT_FAILED"
                failed_job.error_message = str(exc)
                failed_job.finished_at = _now()
                await db.commit()


async def _publish_record(
    db: AsyncSession,
    job: EtlJob,
    row_no: int,
    record: dict[str, Any],
    cache: dict[str, dict[Any, int]],
) -> None:
    if job.data_type == "plan":
        await _publish_plan(db, job, record, cache)
    elif job.data_type == "admission":
        await _publish_admission(db, job, row_no, record, cache)
    elif job.data_type == "score_line":
        await _publish_score_line(db, job, record, cache)
    elif job.data_type == "consultation":
        await _publish_consultation(db, job, record, cache)
    elif job.data_type == "enrollment":
        await _publish_enrollment(db, job, record)
    else:
        raise ValueError(f"不支持发布的数据类型：{job.data_type}")


async def _year_id(db: AsyncSession, value: Any, cache: dict[str, dict[Any, int]]) -> int:
    year_no = _int(value)
    if year_no is None:
        raise ValueError("year 不能为空")
    if year_no in cache["years"]:
        return cache["years"][year_no]
    result = await db.execute(select(Year).where(Year.year_no == year_no))
    year = result.scalar_one_or_none()
    if year is None:
        year = Year(year_no=year_no)
        db.add(year)
        await db.flush()
    cache["years"][year_no] = year.id
    return year.id


async def _province_id(db: AsyncSession, value: Any, cache: dict[str, dict[Any, int]]) -> int:
    raw = _clean(value)
    if not raw:
        raise ValueError("province 不能为空")
    if raw in cache["provinces"]:
        return cache["provinces"][raw]
    province_id, _ = await canonicalization.resolve_province(
        db,
        raw,
        pipeline="generic_import",
        event_cache=cache["canonicalization_events"],
    )
    cache["provinces"][raw] = province_id
    return province_id


async def _subject_id(db: AsyncSession, value: Any, cache: dict[str, dict[Any, int]]) -> int:
    raw = _clean(value) or "未标注科类"
    if raw in cache["subjects"]:
        return cache["subjects"][raw]
    subject_id, _ = await canonicalization.resolve_subject(
        db,
        raw,
        pipeline="generic_import",
        event_cache=cache["canonicalization_events"],
    )
    cache["subjects"][raw] = subject_id
    return subject_id


async def _batch_id(
    db: AsyncSession,
    year_id: int,
    value: Any,
    cache: dict[str, dict[Any, int]],
) -> int:
    raw = _clean(value) or "未标注批次"
    key = (year_id, raw)
    if key in cache["batches"]:
        return cache["batches"][key]
    batch_id, _ = await canonicalization.resolve_batch(
        db,
        year_id,
        raw,
        pipeline="generic_import",
        event_cache=cache["canonicalization_events"],
    )
    cache["batches"][key] = batch_id
    return batch_id


async def _school_id(db: AsyncSession, cache: dict[str, dict[Any, int]]) -> int:
    cache_key = "default"
    if cache_key in cache["schools"]:
        return cache["schools"][cache_key]
    result = await db.execute(select(School).order_by(School.id).limit(1))
    school = result.scalar_one_or_none()
    if school is None:
        school = School(school_code="SCHOOL-001", school_name="示例高校", school_type="UNDERGRADUATE")
        db.add(school)
        await db.flush()
    cache["schools"][cache_key] = school.id
    return school.id


async def _major_id(
    db: AsyncSession,
    record: dict[str, Any],
    cache: dict[str, dict[Any, int]],
) -> int:
    school_id = await _school_id(db, cache)
    name = _clean(record.get("major_name"))
    if not name:
        raise ValueError("major_name 不能为空")
    province_id = await _province_id(db, record.get("province"), cache) if _clean(record.get("province")) else None
    cache_key = (school_id, name, province_id)
    if cache_key in cache["majors"]:
        return cache["majors"][cache_key]
    major_id, _ = await canonicalization.resolve_major(
        db,
        school_id=school_id,
        value=name,
        province_id=province_id,
        pipeline="generic_import",
        create_if_missing=True,
        event_cache=cache["canonicalization_events"],
    )
    cache["majors"][cache_key] = major_id
    return major_id


async def _plan_type_id(
    db: AsyncSession,
    value: Any,
    cache: dict[str, dict[Any, int]],
) -> int | None:
    raw = _clean(value)
    if not raw:
        return None
    if raw in cache["plan_types"]:
        return cache["plan_types"][raw]
    plan_type_id, _ = await canonicalization.resolve_plan_type(
        db,
        raw,
        pipeline="generic_import",
        event_cache=cache["canonicalization_events"],
    )
    cache["plan_types"][raw] = plan_type_id
    return plan_type_id


async def _channel_id(
    db: AsyncSession,
    value: Any,
    cache: dict[str, dict[Any, int]],
) -> int | None:
    name = _clean(value)
    if not name:
        return None
    if name in cache["channels"]:
        return cache["channels"][name]
    result = await db.execute(select(Channel).where(Channel.channel_name == name))
    channel = result.scalar_one_or_none()
    if channel is None:
        channel = Channel(channel_code=_auto_code("CHAN", name), channel_name=name)
        db.add(channel)
        await db.flush()
    cache["channels"][name] = channel.id
    return channel.id


async def _publish_plan(
    db: AsyncSession,
    job: EtlJob,
    record: dict[str, Any],
    cache: dict[str, dict[Any, int]],
) -> None:
    year_id = await _year_id(db, record.get("year"), cache)
    province_id = await _province_id(db, record.get("province"), cache)
    batch_id = await _batch_id(db, year_id, record.get("batch"), cache)
    subject_id = await _subject_id(db, record.get("subject"), cache)
    major_id = await _major_id(db, record, cache)
    plan_type_id = await _plan_type_id(db, record.get("plan_type"), cache)
    data_version = _clean(record.get("data_version")) or job.data_version or f"import-{job.id}"

    plan_params = {
        "school_id": await _school_id(db, cache),
        "year_id": year_id,
        "province_id": province_id,
        "batch_id": batch_id,
        "subject_id": subject_id,
        "major_id": major_id,
        "plan_type_id": plan_type_id,
        "plan_count": _int(record.get("plan_count")) or 0,
        "tuition": _float(record.get("tuition")),
        "data_version": data_version,
    }
    if is_mysql():
        existing_plan_id = await db.scalar(
            text(
                """
                SELECT id
                FROM fact.plan
                WHERE year_id=:year_id AND school_id=:school_id AND province_id=:province_id
                  AND batch_id=:batch_id AND subject_id=:subject_id AND major_id=:major_id
                  AND plan_type_id <=> :plan_type_id AND data_version=:data_version
                ORDER BY id DESC
                LIMIT 1
                """
            ),
            plan_params,
        )
        if existing_plan_id is not None:
            await db.execute(
                text(
                    """
                    UPDATE fact.plan
                    SET plan_count=:plan_count,
                        tuition=COALESCE(:tuition, tuition)
                    WHERE id=:plan_id
                    """
                ),
                {**plan_params, "plan_id": existing_plan_id},
            )
            plan_id = int(existing_plan_id)
        else:
            plan_id = await execute_returning_id(
                db,
                """
                INSERT INTO fact.plan (
                    school_id, year_id, province_id, batch_id, subject_id, major_id,
                    plan_type_id, plan_count, tuition, policy_id, data_version
                )
                VALUES (
                    :school_id, :year_id, :province_id, :batch_id, :subject_id, :major_id,
                    :plan_type_id, :plan_count, :tuition, NULL, :data_version
                )
                RETURNING id
                """,
                plan_params,
            )
    else:
        plan_id = await execute_returning_id(
            db,
            """
            INSERT INTO fact.plan (
                school_id, year_id, province_id, batch_id, subject_id, major_id,
                plan_type_id, plan_count, tuition, policy_id, data_version
            )
            VALUES (
                :school_id, :year_id, :province_id, :batch_id, :subject_id, :major_id,
                :plan_type_id, :plan_count, :tuition, NULL, :data_version
            )
            ON CONFLICT (year_id, school_id, province_id, batch_id, subject_id, major_id, plan_type_id, data_version)
            DO UPDATE SET
                plan_count = EXCLUDED.plan_count,
                tuition = COALESCE(EXCLUDED.tuition, fact.plan.tuition)
            RETURNING id
            """,
            plan_params,
        )
    if plan_id is None:
        raise RuntimeError("招生计划写入失败")

    admitted_count = _int(record.get("admitted_count"))
    min_score = _float(record.get("min_score"))
    avg_score = _float(record.get("avg_score"))
    max_score = _float(record.get("max_score"))
    min_rank_no = _int(record.get("min_rank_no"))
    if any(value is not None for value in (admitted_count, min_score, avg_score, max_score, min_rank_no)):
        await db.execute(
            text(
                """
                INSERT INTO fact.admission_summary (
                    plan_id, admitted_count, min_score, avg_score, max_score,
                    min_rank_no, first_choice_count, adjusted_count, data_version
                )
                VALUES (
                    :plan_id, :admitted_count, :min_score, :avg_score, :max_score,
                    :min_rank_no, 0, 0, :data_version
                )
                """
            ),
            {
                "plan_id": plan_id,
                "admitted_count": admitted_count or 0,
                "min_score": min_score,
                "avg_score": avg_score,
                "max_score": max_score,
                "min_rank_no": min_rank_no,
                "data_version": data_version,
            },
        )


async def _publish_admission(
    db: AsyncSession,
    job: EtlJob,
    row_no: int,
    record: dict[str, Any],
    cache: dict[str, dict[Any, int]],
) -> None:
    year_id = await _year_id(db, record.get("year"), cache)
    province_id = await _province_id(db, record.get("province"), cache)
    batch_id = await _batch_id(db, year_id, record.get("batch"), cache)
    subject_id = await _subject_id(db, record.get("subject"), cache)
    major_id = await _major_id(db, record, cache)
    channel_id = await _channel_id(db, record.get("channel"), cache)
    data_version = _clean(record.get("data_version")) or job.data_version or f"import-{job.id}"

    await db.execute(
        text(
            """
            INSERT INTO fact.admission_record (
                candidate_key, year_id, province_id, batch_id, subject_id, major_id,
                channel_id, score, rank_no, volunteer_order, admit_type, is_enrolled, data_version
            )
            VALUES (
                :candidate_key, :year_id, :province_id, :batch_id, :subject_id, :major_id,
                :channel_id, :score, :rank_no, :volunteer_order, :admit_type, :is_enrolled, :data_version
            )
            """
        ),
        {
            "candidate_key": _candidate_key(job, record, row_no),
            "year_id": year_id,
            "province_id": province_id,
            "batch_id": batch_id,
            "subject_id": subject_id,
            "major_id": major_id,
            "channel_id": channel_id,
            "score": _float(record.get("score")),
            "rank_no": _int(record.get("rank_no")),
            "volunteer_order": _int(record.get("volunteer_order")),
            "admit_type": _clean(record.get("admit_type")),
            "is_enrolled": record.get("is_enrolled"),
            "data_version": data_version,
        },
    )


async def _publish_enrollment(
    db: AsyncSession,
    job: EtlJob,
    record: dict[str, Any],
) -> None:
    year_no = _int(record.get("year"))
    if year_no is None:
        raise ValueError("year 不能为空")

    raw_candidate_no = _clean(record.get("candidate_key"))
    student_name = _clean(record.get("student_name"))
    candidate_key = None
    candidate_no = raw_candidate_no

    if raw_candidate_no:
        candidate_key = _candidate_key(job, {"candidate_key": raw_candidate_no}, 0)
        matched = await db.execute(
            text(
                """
                SELECT candidate_key, candidate_no, student_name
                FROM fact.student_identity
                WHERE year_no=:year_no
                  AND (candidate_key=:candidate_key OR candidate_no=:candidate_no)
                ORDER BY candidate_key
                LIMIT 2
                """
            ),
            {
                "year_no": year_no,
                "candidate_key": candidate_key,
                "candidate_no": raw_candidate_no,
            },
        )
        matches = matched.mappings().all()
        if not matches:
            raw_match = await db.execute(
                text(
                    """
                    SELECT r.raw_data->>'KSH' AS candidate_no,
                           r.raw_data->>'XM' AS student_name
                    FROM gov.dbf_import_row r
                    JOIN gov.dbf_import_table t ON t.id=r.table_id
                    WHERE t.table_name='t_bmk'
                      AND r.raw_data->>'KSH'=:candidate_no
                    ORDER BY r.id
                    LIMIT 2
                    """
                ),
                {"candidate_no": raw_candidate_no},
            )
            matches = raw_match.mappings().all()
    else:
        matched = await db.execute(
            text(
                """
                SELECT candidate_key, candidate_no, student_name
                FROM fact.student_identity
                WHERE year_no=:year_no AND student_name=:student_name
                ORDER BY candidate_key
                LIMIT 2
                """
            ),
            {"year_no": year_no, "student_name": student_name},
        )
        matches = matched.mappings().all()
        if not matches:
            raw_match = await db.execute(
                text(
                    """
                    SELECT r.raw_data->>'KSH' AS candidate_no,
                           r.raw_data->>'XM' AS student_name
                    FROM gov.dbf_import_row r
                    JOIN gov.dbf_import_table t ON t.id=r.table_id
                    WHERE t.table_name='t_bmk'
                      AND r.raw_data->>'XM'=:student_name
                    ORDER BY r.id
                    LIMIT 2
                    """
                ),
                {"student_name": student_name},
            )
            matches = raw_match.mappings().all()

    if not matches:
        raise ValueError(f"第 {year_no} 年未匹配到考生：{raw_candidate_no or student_name}")
    if len(matches) > 1:
        raise ValueError(f"第 {year_no} 年存在多名匹配考生，请使用考生号：{raw_candidate_no or student_name}")

    matched = dict(matches[0])
    candidate_no = candidate_no or matched.get("candidate_no")
    student_name = student_name or matched.get("student_name")
    candidate_key = matched.get("candidate_key") or _candidate_key(
        job, {"candidate_key": candidate_no}, 0
    )

    admission = await db.scalar(
        text(
            """
            SELECT 1
            FROM fact.admission_record ar
            JOIN dim.year y ON y.id=ar.year_id
            WHERE ar.candidate_key=:candidate_key AND y.year_no=:year_no
            LIMIT 1
            """
        ),
        {"candidate_key": candidate_key, "year_no": year_no},
    )
    if admission is None:
        raise ValueError(f"第 {year_no} 年考生没有录取记录：{raw_candidate_no or student_name}")

    is_enrolled = bool(record.get("is_enrolled"))
    data_version = _clean(record.get("data_version")) or job.data_version or f"enrollment-import-{job.id}"
    await db.execute(
        text(
            """
            INSERT INTO fact.enrollment_status (
                candidate_key, year_no, candidate_no, student_name,
                is_enrolled, enrolled_at, remark, source_file, data_version, raw_data
            )
            VALUES (
                :candidate_key, :year_no, :candidate_no, :student_name,
                :is_enrolled, :enrolled_at, :remark, :source_file, :data_version,
                CAST(:raw_data AS jsonb)
            )
            ON CONFLICT (candidate_key, year_no)
            DO UPDATE SET
                candidate_no=EXCLUDED.candidate_no,
                student_name=EXCLUDED.student_name,
                is_enrolled=EXCLUDED.is_enrolled,
                enrolled_at=EXCLUDED.enrolled_at,
                remark=EXCLUDED.remark,
                source_file=EXCLUDED.source_file,
                data_version=EXCLUDED.data_version,
                raw_data=EXCLUDED.raw_data,
                updated_at=now()
            """
        ),
        {
            "candidate_key": candidate_key,
            "year_no": year_no,
            "candidate_no": candidate_no,
            "student_name": student_name,
            "is_enrolled": is_enrolled,
            "enrolled_at": _date(record.get("enrolled_at")),
            "remark": _clean(record.get("remark")),
            "source_file": job.file_name,
            "data_version": data_version,
            "raw_data": __import__("json").dumps(record, ensure_ascii=False, default=str),
        },
    )
    admission_update = (
        """
        UPDATE fact.admission_record ar
        JOIN dim.year y ON y.id=ar.year_id
        SET ar.is_enrolled=:is_enrolled
        WHERE y.year_no=:year_no
          AND ar.candidate_key=:candidate_key
        """
        if is_mysql()
        else """
        UPDATE fact.admission_record ar
        SET is_enrolled=:is_enrolled
        FROM dim.year y
        WHERE ar.year_id=y.id
          AND y.year_no=:year_no
          AND ar.candidate_key=:candidate_key
        """
    )
    await db.execute(
        text(admission_update),
        {
            "is_enrolled": is_enrolled,
            "year_no": year_no,
            "candidate_key": candidate_key,
        },
    )
    await db.execute(
        text(
            """
            INSERT INTO fact.student_management (
                candidate_key, year_no, student_status, follow_up_status, updated_at
            )
            VALUES (
                :candidate_key, :year_no, :student_status, 'PENDING', now()
            )
            ON CONFLICT (candidate_key)
            DO UPDATE SET
                student_status=CASE
                    WHEN EXCLUDED.student_status='ENROLLED' THEN 'ENROLLED'
                    WHEN fact.student_management.student_status='ENROLLED' THEN 'ADMITTED'
                    ELSE fact.student_management.student_status
                END,
                updated_at=now()
            """
        ),
        {
            "candidate_key": candidate_key,
            "year_no": year_no,
            "student_status": "ENROLLED" if is_enrolled else "ADMITTED",
        },
    )


async def _publish_score_line(
    db: AsyncSession,
    job: EtlJob,
    record: dict[str, Any],
    cache: dict[str, dict[Any, int]],
) -> None:
    year_id = await _year_id(db, record.get("year"), cache)
    province_id = await _province_id(db, record.get("province"), cache)
    batch_id = await _batch_id(db, year_id, record.get("batch"), cache)
    subject_id = await _subject_id(db, record.get("subject"), cache)
    major_id = await _major_id(db, record, cache) if _clean(record.get("major_name")) else None
    data_version = _clean(record.get("data_version")) or job.data_version or f"import-{job.id}"

    await db.execute(
        text(
            """
            INSERT INTO fact.score_line (
                year_id, province_id, batch_id, subject_id, major_id,
                min_score, min_rank_no, source_type, data_version
            )
            VALUES (
                :year_id, :province_id, :batch_id, :subject_id, :major_id,
                :min_score, :min_rank_no, :source_type, :data_version
            )
            """
        ),
        {
            "year_id": year_id,
            "province_id": province_id,
            "batch_id": batch_id,
            "subject_id": subject_id,
            "major_id": major_id,
            "min_score": _float(record.get("min_score")),
            "min_rank_no": _int(record.get("min_rank_no")),
            "source_type": _clean(record.get("source_type")) or "IMPORT",
            "data_version": data_version,
        },
    )


async def _publish_consultation(
    db: AsyncSession,
    job: EtlJob,
    record: dict[str, Any],
    cache: dict[str, dict[Any, int]],
) -> None:
    year_id = await _year_id(db, record.get("year"), cache)
    province_id = await _province_id(db, record.get("province"), cache)
    channel_id = await _channel_id(db, record.get("channel"), cache)
    data_version = _clean(record.get("data_version")) or job.data_version or f"import-{job.id}"

    await db.execute(
        text(
            """
            INSERT INTO fact.consultation (
                year_id, province_id, channel_id, consultation_type, status,
                contacted_at, converted, data_version
            )
            VALUES (
                :year_id, :province_id, :channel_id, :consultation_type, :status,
                :contacted_at, :converted, :data_version
            )
            """
        ),
        {
            "year_id": year_id,
            "province_id": province_id,
            "channel_id": channel_id,
            "consultation_type": _clean(record.get("consultation_type")),
            "status": _clean(record.get("status")),
            "contacted_at": _datetime(record.get("contacted_at")),
            "converted": record.get("converted"),
            "data_version": data_version,
        },
    )




