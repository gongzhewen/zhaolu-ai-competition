import hashlib
import re
import unicodedata
from typing import Any

from app.core.text import text
from app.core.db_compat import execute_returning_id
from sqlalchemy.ext.asyncio import AsyncSession


PROVINCE_CODES = {
    "北京": "110000", "天津": "120000", "河北": "130000", "山西": "140000", "内蒙古": "150000",
    "辽宁": "210000", "吉林": "220000", "黑龙江": "230000", "上海": "310000", "江苏": "320000",
    "浙江": "330000", "安徽": "340000", "福建": "350000", "江西": "360000", "山东": "370000",
    "河南": "410000", "湖北": "420000", "湖南": "430000", "广东": "440000", "广西": "450000",
    "海南": "460000", "重庆": "500000", "四川": "510000", "贵州": "520000", "云南": "530000",
    "西藏": "540000", "陕西": "610000", "甘肃": "620000", "青海": "630000", "宁夏": "640000",
    "新疆": "650000", "香港": "810000", "澳门": "820000", "台湾": "710000", "专升本": "ZBK000",
}
PROVINCE_SUFFIXES = (
    "维吾尔自治区", "壮族自治区", "回族自治区", "特别行政区", "自治区", "省", "市",
)
SUBJECT_ALIASES = {
    "物理": "普通类(首选物理)", "物理类": "普通类(首选物理)", "普通类物理": "普通类(首选物理)",
    "普通类(物理)": "普通类(首选物理)", "物理科目组": "普通类(首选物理)",
    "历史": "普通类(首选历史)", "历史类": "普通类(首选历史)", "普通类历史": "普通类(首选历史)",
    "普通类(历史)": "普通类(首选历史)", "历史科目组": "普通类(首选历史)",
    "职高对口": "职高对口类", "对口类": "职高对口类", "专升本": "专升本",
}
BATCH_ALIASES = {
    "本科批": "本科批(普通)", "普通本科批": "本科批(普通)", "本科普通批": "本科批(普通)",
    "本科一批": "本科批(普通)", "本科二批": "本科批(普通)", "专升本": "专升本",
}
PLAN_TYPE_ALIASES = {
    "普通": "普通类", "正常": "普通类", "统招": "普通类", "统一招生": "普通类",
    "专升本": "专升本", "退役大学生士兵": "专升本",
}


def normalize_text(value: Any) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip().replace("（", "(").replace("）", ")")


def normalize_key(value: Any) -> str:
    return re.sub(r"\s+", "", normalize_text(value).lower())


def _auto_code(prefix: str, value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:12].upper()
    return f"AUTO-{prefix}-{digest}"


async def record_event(
    db: AsyncSession,
    *,
    pipeline: str,
    entity_type: str,
    source_value: str,
    canonical_value: str,
    rule_code: str,
    scope_key: str = "",
    confidence: float = 1.0,
) -> None:
    await db.execute(
        text("""
            INSERT INTO gov.canonicalization_event (
                pipeline, entity_type, source_value, canonical_value,
                rule_code, scope_key, confidence, hit_count
            )
            VALUES (
                :pipeline, :entity_type, :source_value, :canonical_value,
                :rule_code, :scope_key, :confidence, 1
            )
            ON CONFLICT (pipeline, entity_type, source_value, canonical_value, scope_key)
            DO UPDATE SET
                hit_count = gov.canonicalization_event.hit_count + 1,
                last_seen_at = now(),
                confidence = GREATEST(gov.canonicalization_event.confidence, EXCLUDED.confidence)
            """
        ),
        {
            "pipeline": pipeline,
            "entity_type": entity_type,
            "source_value": source_value[:512],
            "canonical_value": canonical_value[:512],
            "rule_code": rule_code,
            "scope_key": scope_key[:128],
            "confidence": confidence,
        },
    )


async def resolve_province(
    db: AsyncSession,
    value: Any,
    *,
    pipeline: str,
    event_cache: set[tuple[str, str, str]] | None = None,
) -> tuple[int, str]:
    raw = normalize_text(value)
    if not raw:
        raise ValueError("province 不能为空")
    canonical_name = raw
    for suffix in PROVINCE_SUFFIXES:
        if canonical_name.endswith(suffix):
            canonical_name = canonical_name[: -len(suffix)]
            break
    province_code = PROVINCE_CODES.get(canonical_name, _auto_code("PROV", canonical_name))
    province_id = await db.scalar(
        text("SELECT id FROM dim.province WHERE province_name = :name ORDER BY id LIMIT 1"),
        {"name": canonical_name},
    )
    if province_id is None:
        province_id = await execute_returning_id(
            db,
            """
            INSERT INTO dim.province (province_code, province_name)
            VALUES (:code, :name)
            ON CONFLICT (province_code) DO UPDATE SET province_name = EXCLUDED.province_name
            RETURNING id
            """,
            {"code": province_code, "name": canonical_name},
            mysql_select="SELECT id FROM dim.province WHERE province_code=:code LIMIT 1",
        )
    canonical = canonical_name
    if raw != canonical:
        event_key = ("province", raw, canonical)
        if event_cache is None or event_key not in event_cache:
            await record_event(
                db,
                pipeline=pipeline,
                entity_type="province",
                source_value=raw,
                canonical_value=canonical,
                rule_code="province_alias",
            )
            if event_cache is not None:
                event_cache.add(event_key)
    return int(province_id), canonical


async def resolve_subject(
    db: AsyncSession,
    value: Any,
    *,
    pipeline: str,
    event_cache: set[tuple[str, str, str]] | None = None,
) -> tuple[int, str]:
    raw = normalize_text(value) or "未标注科类"
    canonical = SUBJECT_ALIASES.get(normalize_key(raw), raw)
    subject_id = await db.scalar(
        text("SELECT id FROM dim.subject WHERE subject_name = :name ORDER BY id LIMIT 1"),
        {"name": canonical},
    )
    if subject_id is None:
        subject_code = _auto_code("SUBJ", canonical)
        subject_id = await execute_returning_id(
            db,
            """
            INSERT INTO dim.subject (subject_code, subject_name)
            VALUES (:code, :name)
            ON CONFLICT (subject_code) DO UPDATE SET subject_name = EXCLUDED.subject_name
            RETURNING id
            """,
            {"code": subject_code, "name": canonical},
            mysql_select="SELECT id FROM dim.subject WHERE subject_code=:code LIMIT 1",
        )
    if raw != canonical:
        event_key = ("subject", raw, canonical)
        if event_cache is None or event_key not in event_cache:
            await record_event(
                db,
                pipeline=pipeline,
                entity_type="subject",
                source_value=raw,
                canonical_value=canonical,
                rule_code="subject_alias",
            )
            if event_cache is not None:
                event_cache.add(event_key)
    return int(subject_id), canonical


async def resolve_batch(
    db: AsyncSession,
    year_id: int,
    value: Any,
    *,
    pipeline: str,
    event_cache: set[tuple[str, str, str]] | None = None,
) -> tuple[int, str]:
    raw = normalize_text(value) or "未标注批次"
    canonical = BATCH_ALIASES.get(normalize_key(raw), raw)
    batch_id = await db.scalar(
        text("SELECT id FROM dim.batch WHERE year_id = :year_id AND batch_name = :name ORDER BY id LIMIT 1"),
        {"year_id": year_id, "name": canonical},
    )
    if batch_id is None:
        batch_code = _auto_code("BATCH", canonical)
        batch_id = await execute_returning_id(
            db,
            """
            INSERT INTO dim.batch (year_id, batch_code, batch_name)
            VALUES (:year_id, :code, :name)
            RETURNING id
            """,
            {"year_id": year_id, "code": batch_code, "name": canonical},
            mysql_select="SELECT id FROM dim.batch WHERE year_id=:year_id AND batch_code=:code LIMIT 1",
        )
    if raw != canonical:
        event_key = ("batch", raw, canonical)
        if event_cache is None or event_key not in event_cache:
            await record_event(
                db,
                pipeline=pipeline,
                entity_type="batch",
                source_value=raw,
                canonical_value=canonical,
                rule_code="batch_alias",
                scope_key=str(year_id),
            )
            if event_cache is not None:
                event_cache.add(event_key)
    return int(batch_id), canonical


async def resolve_plan_type(
    db: AsyncSession,
    value: Any,
    *,
    pipeline: str,
    event_cache: set[tuple[str, str, str]] | None = None,
) -> tuple[int | None, str | None]:
    raw = normalize_text(value)
    if not raw:
        return None, None
    canonical = PLAN_TYPE_ALIASES.get(normalize_key(raw), raw)
    plan_type_id = await db.scalar(
        text("SELECT id FROM dim.plan_type WHERE type_name = :name ORDER BY id LIMIT 1"),
        {"name": canonical},
    )
    if plan_type_id is None:
        type_code = _auto_code("PLAN", canonical)
        plan_type_id = await execute_returning_id(
            db,
            """
            INSERT INTO dim.plan_type (type_code, type_name)
            VALUES (:code, :name)
            RETURNING id
            """,
            {"code": type_code, "name": canonical},
            mysql_select="SELECT id FROM dim.plan_type WHERE type_code=:code LIMIT 1",
        )
    if raw != canonical:
        event_key = ("plan_type", raw, canonical)
        if event_cache is None or event_key not in event_cache:
            await record_event(
                db,
                pipeline=pipeline,
                entity_type="plan_type",
                source_value=raw,
                canonical_value=canonical,
                rule_code="plan_type_alias",
            )
            if event_cache is not None:
                event_cache.add(event_key)
    return int(plan_type_id), canonical


async def resolve_major(
    db: AsyncSession,
    *,
    school_id: int,
    value: Any,
    province_id: int | None = None,
    pipeline: str,
    create_if_missing: bool = True,
    event_cache: set[tuple[str, str, str]] | None = None,
) -> tuple[int, str]:
    raw = normalize_text(value)
    if not raw:
        raise ValueError("major_name 不能为空")
    source_key = normalize_key(raw)
    alias = (
        await db.execute(
            text("""
                SELECT ma.canonical_major_id, cm.major_name
                FROM dim.major_alias ma
                JOIN dim.major cm ON cm.id = ma.canonical_major_id
                WHERE ma.is_active IS TRUE
                  AND ma.source_name_key = :source_key
                  AND (ma.province_id IS NULL OR ma.province_id = :province_id)
                ORDER BY (ma.province_id IS NOT NULL) DESC, ma.id DESC
                LIMIT 1
                """
            ),
            {"source_key": source_key, "province_id": province_id},
        )
    ).mappings().one_or_none()
    if alias is not None:
        canonical_id = int(alias["canonical_major_id"])
        canonical_name = str(alias["major_name"])
        event_key = ("major", raw, canonical_name)
        if event_cache is None or event_key not in event_cache:
            await record_event(
                db,
                pipeline=pipeline,
                entity_type="major",
                source_value=raw,
                canonical_value=canonical_name,
                rule_code="major_province_alias" if province_id is not None else "major_global_alias",
                scope_key=str(province_id or ""),
                confidence=1.0,
            )
            if event_cache is not None:
                event_cache.add(event_key)
        return canonical_id, canonical_name

    major = (
        await db.execute(
            text(
                """
                SELECT id, major_name
                FROM dim.major
                WHERE school_id = :school_id
                  AND lower(regexp_replace(replace(replace(major_name, '（', '('), '）', ')'), '[[:space:]]+', '', 'g')) = :source_key
                ORDER BY id
                LIMIT 1
                """
            ),
            {"school_id": school_id, "source_key": source_key},
        )
    ).mappings().one_or_none()
    if major is not None:
        return int(major["id"]), str(major["major_name"])
    if not create_if_missing:
        raise ValueError(f"标准专业未找到：{raw}")
    major_code = _auto_code("MAJOR", raw)
    major_id = await execute_returning_id(
        db,
        """
        INSERT INTO dim.major (school_id, major_code, major_name, is_active)
        VALUES (:school_id, :major_code, :major_name, TRUE)
        RETURNING id
        """,
        {"school_id": school_id, "major_code": major_code, "major_name": raw},
        mysql_select="SELECT id FROM dim.major WHERE school_id=:school_id AND major_code=:major_code LIMIT 1",
    )
    await record_event(
        db,
        pipeline=pipeline,
        entity_type="major",
        source_value=raw,
        canonical_value=raw,
        rule_code="major_create",
        scope_key=str(province_id or ""),
        confidence=0.5,
    )
    return int(major_id), raw



