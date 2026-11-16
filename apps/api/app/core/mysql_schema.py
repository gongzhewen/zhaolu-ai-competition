from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings

logger = logging.getLogger(__name__)

INDEXES: list[tuple[str, str, str, bool, tuple[str, ...]]] = [
    ("zhaolu_fact", "plan", "uk_plan_natural", True, ("year_id", "school_id", "province_id", "batch_id", "subject_id", "major_id", "plan_type_key", "data_version")),
    ("zhaolu_fact", "plan", "idx_plan_dimensions", False, ("year_id", "school_id", "province_id", "batch_id", "subject_id", "major_id")),
    ("zhaolu_fact", "plan", "idx_plan_school_year_province_major", False, ("school_id", "year_id", "province_id", "major_id")),
    ("zhaolu_fact", "admission_summary", "uk_admission_summary_plan_version", True, ("plan_id", "data_version")),
    ("zhaolu_fact", "admission_summary", "idx_admission_summary_plan", False, ("plan_id", "data_version")),
    ("zhaolu_fact", "admission_record", "idx_admission_record_dimensions", False, ("year_id", "province_id", "major_id", "subject_id")),
    ("zhaolu_fact", "score_line", "idx_score_line_dimensions", False, ("year_id", "province_id", "batch_id", "subject_id", "major_id")),
    ("zhaolu_dim", "major_alias", "uk_major_alias_scope", True, ("source_name_key", "province_scope_id")),
    ("zhaolu_dim", "major_alias", "idx_major_alias_canonical", False, ("canonical_major_id", "is_active")),
    ("zhaolu_gov", "canonicalization_event", "uk_canonicalization_event", True, ("event_key",)),
    ("zhaolu_gov", "canonicalization_event", "idx_canonicalization_event_type", False, ("entity_type", "last_seen_at")),
    ("zhaolu_gov", "data_issue", "idx_quality_issue_status", False, ("issue_status", "created_at")),
    ("zhaolu_gov", "import_field_mapping", "ix_import_field_mapping_job", False, ("job_id",)),
    ("zhaolu_gov", "import_record", "ix_import_record_job_status", False, ("job_id", "status")),
    ("zhaolu_gov", "etl_job", "ix_etl_job_status", False, ("job_status", "created_at")),
    ("zhaolu_gov", "dbf_import_table", "ix_dbf_import_table_batch", False, ("batch_id",)),
    ("zhaolu_gov", "dbf_import_row", "ix_dbf_import_row_batch_table", False, ("batch_id", "table_id")),
    ("zhaolu_dim", "school", "idx_school_province_status", False, ("province_id", "status")),
    ("zhaolu_fact", "candidate_profile", "idx_candidate_profile_key", False, ("candidate_key",)),
    ("zhaolu_fact", "candidate_profile", "idx_candidate_profile_region", False, ("year_no", "region_code")),
    ("zhaolu_fact", "exam_subject_score", "idx_exam_subject_score_candidate", False, ("candidate_key", "subject_code")),
    ("zhaolu_fact", "major_choice", "idx_major_choice_candidate", False, ("candidate_key", "choice_order")),
    ("zhaolu_fact", "major_choice", "idx_major_choice_year_candidate", False, ("year_no", "candidate_key")),
    ("zhaolu_fact", "major_choice", "idx_major_choice_candidate_year", False, ("candidate_key", "year_no")),
    ("zhaolu_fact", "admission_record", "idx_admission_record_candidate_year_province", False, ("candidate_key", "year_id", "province_id")),
    ("zhaolu_fact", "exam_subject_score", "idx_exam_subject_score_year_candidate", False, ("year_no", "candidate_key")),
    ("zhaolu_dim", "major_alias", "idx_major_alias_source_province", False, ("source_name_key", "province_id", "is_active", "id")),
    ("zhaolu_fact", "candidate_resume", "idx_candidate_resume_candidate", False, ("candidate_key", "start_date")),
    ("zhaolu_fact", "medical_summary", "idx_medical_summary_candidate", False, ("candidate_key",)),
    ("zhaolu_fact", "student_management", "idx_student_management_status", False, ("student_status", "follow_up_status")),
    ("zhaolu_fact", "student_management", "idx_student_management_owner", False, ("owner_name",)),
    ("zhaolu_fact", "authoritative_admission_stat", "idx_authoritative_admission_year", False, ("year_no", "major_name")),
    ("zhaolu_fact", "student_identity", "idx_student_identity_year", False, ("year_no", "candidate_no")),
    ("zhaolu_fact", "enrollment_status", "idx_enrollment_status_year_enrolled", False, ("year_no", "is_enrolled")),
    ("zhaolu_fact", "enrollment_status", "idx_enrollment_status_candidate_no", False, ("candidate_no",)),
    ("zhaolu_ai", "knowledge_chunk", "idx_knowledge_chunk_document", False, ("document_id", "chunk_index")),
    ("zhaolu_ai", "knowledge_document", "uk_knowledge_document_checksum", True, ("checksum",)),
    ("zhaolu_ai", "knowledge_document", "idx_knowledge_document_school_status", False, ("school_id", "status")),
    ("zhaolu_ai", "message", "idx_ai_message_conversation", False, ("conversation_id", "created_at")),
    ("zhaolu_ai", "agent_memory", "idx_agent_memory_query", False, ("user_id", "school_id", "memory_type")),
    ("zhaolu_ai", "response_evaluation", "idx_response_evaluation_school_created", False, ("school_id", "created_at")),
    ("zhaolu_sys", "audit_log", "idx_audit_log_created", False, ("created_at",)),
    ("zhaolu_sys", "audit_log", "idx_audit_log_user", False, ("user_id", "created_at")),
]

GENERATED_COLUMNS = [
    ("zhaolu_fact", "plan", "plan_type_key", "BIGINT", "COALESCE(plan_type_id, 0)"),
    ("zhaolu_dim", "major_alias", "province_scope_id", "BIGINT", "COALESCE(province_id, 0)"),
    (
        "zhaolu_gov",
        "canonicalization_event",
        "event_key",
        "CHAR(64)",
        "SHA2(CONCAT_WS('|', pipeline, entity_type, source_value, canonical_value, scope_key), 256)",
    ),
]


async def exists_column(conn, schema: str, table: str, column: str) -> bool:
    value = await conn.scalar(
        text(
            """
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_schema=:schema AND table_name=:table AND column_name=:column
            """
        ),
        {"schema": schema, "table": table, "column": column},
    )
    return bool(value)


async def exists_index(conn, schema: str, table: str, index_name: str) -> bool:
    value = await conn.scalar(
        text(
            """
            SELECT COUNT(*) FROM information_schema.statistics
            WHERE table_schema=:schema AND table_name=:table AND index_name=:index_name
            """
        ),
        {"schema": schema, "table": table, "index_name": index_name},
    )
    return bool(value)


async def ensure_mysql_compat_indexes() -> tuple[int, int]:
    database_url = settings.database_url
    if not database_url.startswith("mysql"):
        return 0, 0
    engine = create_async_engine(database_url, pool_pre_ping=True)
    applied = 0
    skipped = 0
    try:
        for schema, table, column, column_type, expression in GENERATED_COLUMNS:
            async with engine.begin() as conn:
                if await exists_column(conn, schema, table, column):
                    skipped += 1
                    continue
                try:
                    await conn.execute(
                        text(
                            f"ALTER TABLE `{schema}`.`{table}` "
                            f"ADD COLUMN `{column}` {column_type} "
                            f"GENERATED ALWAYS AS ({expression}) STORED"
                        )
                    )
                    applied += 1
                except Exception:
                    logger.warning(
                        "MySQL generated column repair skipped: %s.%s.%s",
                        schema,
                        table,
                        column,
                        exc_info=True,
                    )

        for schema, table, index_name, unique, columns in INDEXES:
            async with engine.begin() as conn:
                if await exists_index(conn, schema, table, index_name):
                    skipped += 1
                    continue
                unique_sql = "UNIQUE " if unique else ""
                column_sql = ", ".join(f"`{column}`" for column in columns)
                try:
                    await conn.execute(
                        text(
                            f"ALTER TABLE `{schema}`.`{table}` "
                            f"ADD {unique_sql}KEY `{index_name}` ({column_sql})"
                        )
                    )
                    applied += 1
                except Exception:
                    logger.warning(
                        "MySQL index repair skipped: %s.%s.%s",
                        schema,
                        table,
                        index_name,
                        exc_info=True,
                    )
    finally:
        await engine.dispose()
    return applied, skipped


