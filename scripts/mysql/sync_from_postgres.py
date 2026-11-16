from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

SCHEMA_MAP = {
    "dim": "zhaolu_dim",
    "fact": "zhaolu_fact",
    "gov": "zhaolu_gov",
    "ai": "zhaolu_ai",
    "sys": "zhaolu_sys",
}

TABLE_ORDER: list[tuple[str, str]] = [
    ("dim", "year"), ("dim", "province"), ("dim", "region"), ("dim", "subject"),
    ("dim", "plan_type"), ("dim", "batch"), ("dim", "channel"), ("dim", "school"),
    ("dim", "major"), ("dim", "major_alias"), ("dim", "policy"),
    ("fact", "plan"), ("fact", "admission_summary"), ("fact", "authoritative_admission_stat"),
    ("fact", "admission_record"), ("fact", "candidate_profile"), ("fact", "student_identity"),
    ("fact", "exam_subject_score"), ("fact", "major_choice"), ("fact", "candidate_resume"),
    ("fact", "medical_summary"), ("fact", "student_management"), ("fact", "enrollment_status"),
    ("fact", "source_quality"), ("fact", "score_line"), ("fact", "metric_snapshot"),
    ("fact", "channel_touch"), ("fact", "consultation"),
    ("gov", "canonicalization_event"), ("gov", "data_source"), ("gov", "data_issue"),
    ("gov", "metric_definition"), ("gov", "quality_rule"), ("gov", "dbf_interface_profile"),
    ("gov", "dbf_import_batch"), ("gov", "dbf_import_table"), ("gov", "dbf_import_row"),
    ("gov", "etl_job"), ("gov", "import_field_mapping"), ("gov", "import_record"),
    ("ai", "knowledge_document"), ("ai", "knowledge_chunk"), ("ai", "prompt_template"),
    ("ai", "agent_memory"), ("ai", "conversation"), ("ai", "message"), ("ai", "tool_call"),
    ("ai", "response_evaluation"), ("ai", "optimization_event"), ("ai", "feedback"), ("ai", "eval_case"),
    ("sys", "permission"), ("sys", "role"), ("sys", "role_permission"), ("sys", "alert_rule"),
    ("sys", "user_account"), ("sys", "user_role"), ("sys", "user_school"), ("sys", "alert_record"),
    ("sys", "audit_log"),
]

GENERATED_OR_AUTO = {"plan_type_key", "province_scope_id", "event_key"}


def load_env() -> None:
    root = Path(__file__).resolve().parents[2]
    env_file = root / "apps" / "api" / ".env.mysql"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


def convert_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, default=str)
    if isinstance(value, (list, tuple)):
        # PostgreSQL arrays, vector embeddings and JSON arrays all become JSON.
        return json.dumps(list(value), ensure_ascii=False, default=str)
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
        return value
    if isinstance(value, date):
        return value
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    if hasattr(value, "isoformat") and value.__class__.__module__ == "uuid":
        return str(value)
    return value


async def source_columns(conn: asyncpg.Connection, schema: str, table: str) -> list[str]:
    rows = await conn.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema=$1 AND table_name=$2
        ORDER BY ordinal_position
        """,
        schema,
        table,
    )
    return [row["column_name"] for row in rows]


async def target_columns(engine, schema: str, table: str) -> set[str]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema=:schema AND table_name=:table
                ORDER BY ordinal_position
                """
            ),
            {"schema": schema, "table": table},
        )
        return {row[0] for row in rows}


async def target_has_table(engine, schema: str, table: str) -> bool:
    async with engine.connect() as conn:
        value = await conn.scalar(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema=:schema AND table_name=:table
                """
            ),
            {"schema": schema, "table": table},
        )
        return bool(value)


async def reset_auto_increment(engine, schema: str, table: str) -> None:
    async with engine.connect() as conn:
        has_id = await conn.scalar(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_schema=:schema AND table_name=:table AND column_name='id'
                """
            ),
            {"schema": schema, "table": table},
        )
        if not has_id:
            return
        max_id = await conn.scalar(text(f"SELECT MAX(id) FROM `{schema}`.`{table}`"))
        if max_id is None:
            return
    async with engine.begin() as conn:
        await conn.execute(text(f"ALTER TABLE `{schema}`.`{table}` AUTO_INCREMENT = {int(max_id) + 1}"))


async def copy_table(
    source: asyncpg.Connection,
    engine,
    schema: str,
    table: str,
    *,
    batch_size: int,
    dry_run: bool,
) -> tuple[int, int]:
    target_schema = SCHEMA_MAP[schema]
    if not await target_has_table(engine, target_schema, table):
        print(f"SKIP {schema}.{table}: target table missing")
        return 0, 0
    source_cols = await source_columns(source, schema, table)
    target_cols = await target_columns(engine, target_schema, table)
    common = [column for column in source_cols if column in target_cols and column not in GENERATED_OR_AUTO]
    missing_required = sorted(target_cols - set(source_cols) - GENERATED_OR_AUTO)
    if missing_required:
        print(f"NOTE {schema}.{table}: target-only columns={missing_required}; using defaults/NULL")
    if "id" in source_cols and "id" not in common:
        raise RuntimeError(f"{schema}.{table}: id column not writable")

    total = int(await source.fetchval(f"SELECT COUNT(*) FROM {schema}.{table}") or 0)
    print(f"COPY {schema}.{table}: rows={total} columns={len(common)}")
    if dry_run:
        return total, total

    rows = await source.fetch(f"SELECT {', '.join(common)} FROM {schema}.{table} ORDER BY 1")
    placeholders = ", ".join(f":{column}" for column in common)
    column_sql = ", ".join(f"`{column}`" for column in common)
    insert_sql = text(
        f"INSERT INTO `{target_schema}`.`{table}` ({column_sql}) VALUES ({placeholders})"
    )

    async with engine.begin() as conn:
        await conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        await conn.execute(text(f"DELETE FROM `{target_schema}`.`{table}`"))
        for start in range(0, len(rows), batch_size):
            batch = []
            for row in rows[start:start + batch_size]:
                batch.append({column: convert_value(row[column]) for column in common})
            if batch:
                await conn.execute(insert_sql, batch)
        await conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
    await reset_auto_increment(engine, target_schema, table)
    return total, len(rows)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-url", default=os.environ.get("V1_DATABASE_URL", "postgresql://zhaolu:change_me@127.0.0.1:5432/zhaolu"))
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_env()
    target_url = os.environ.get("DATABASE_URL")
    if not target_url or not target_url.startswith("mysql"):
        raise SystemExit("DATABASE_URL must be a MySQL URL")

    source = await asyncpg.connect(args.source_url)
    engine = create_async_engine(target_url, poolclass=NullPool, pool_pre_ping=True)
    try:
        print("SCHEMA_CONVERSION Postgres -> MySQL")
        copied = 0
        for schema, table in TABLE_ORDER:
            try:
                expected, actual = await copy_table(
                    source,
                    engine,
                    schema,
                    table,
                    batch_size=args.batch_size,
                    dry_run=args.dry_run,
                )
            except Exception as exc:
                raise RuntimeError(f"failed copying {schema}.{table}: {exc}") from exc
            if expected != actual:
                raise RuntimeError(f"row count mismatch {schema}.{table}: {expected} != {actual}")
            copied += actual
        print(f"sync_rows={copied} dry_run={args.dry_run}")
    finally:
        await source.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
