
import sqlalchemy as sa
from alembic import op

revision = "0016_agent_runtime_optimization"
down_revision = "0015_remove_ultimate_admin"
branch_labels = None
depends_on = None


MATERIALIZED_VIEW_SQL = """
CREATE SCHEMA IF NOT EXISTS analytics;

CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.mv_admissions_rollup AS
SELECT
    y.year_no,
    p.school_id,
    sc.school_name,
    p.province_id,
    pr.province_name,
    p.major_id AS source_major_id,
    m.major_name AS source_major_name,
    COALESCE(rm.id, m.id) AS canonical_major_id,
    COALESCE(rm.major_name, m.major_name) AS canonical_major_name,
    p.subject_id,
    sub.subject_name,
    p.plan_type_id,
    COALESCE(p.plan_type_id, 0) AS plan_type_key,
    COALESCE(pt.type_code, '') AS plan_type_code,
    p.batch_id,
    COALESCE(SUM(p.plan_count), 0)::bigint AS plan_count,
    COALESCE(SUM(s.admitted_count), 0)::bigint AS admitted_count,
    MIN(NULLIF(s.min_score, 0)) AS min_score,
    MAX(NULLIF(s.max_score, 0)) AS max_score,
    MIN(NULLIF(s.min_rank_no, 0)) AS min_rank_no,
    MAX(p.data_version) AS data_version
FROM fact.plan p
JOIN dim.year y ON y.id = p.year_id
JOIN dim.school sc ON sc.id = p.school_id
JOIN dim.province pr ON pr.id = p.province_id
JOIN dim.major m ON m.id = p.major_id
JOIN dim.subject sub ON sub.id = p.subject_id
LEFT JOIN dim.plan_type pt ON pt.id = p.plan_type_id
LEFT JOIN LATERAL (
    SELECT ma.canonical_major_id
    FROM dim.major_alias ma
    WHERE ma.is_active
      AND ma.source_name_key = lower(
          replace(replace(replace(m.major_name, '（', '('), '）', ')'), ' ', '')
      )
      AND (ma.province_id IS NULL OR ma.province_id = p.province_id)
    ORDER BY (ma.province_id IS NOT NULL) DESC, ma.id DESC
    LIMIT 1
) major_alias ON TRUE
LEFT JOIN dim.major rm ON rm.id = major_alias.canonical_major_id
LEFT JOIN fact.admission_summary s ON s.plan_id = p.id
GROUP BY
    y.year_no, p.school_id, sc.school_name, p.province_id, pr.province_name,
    p.major_id, m.major_name, COALESCE(rm.id, m.id),
    COALESCE(rm.major_name, m.major_name), p.subject_id, sub.subject_name,
    p.plan_type_id, COALESCE(p.plan_type_id, 0), COALESCE(pt.type_code, ''), p.batch_id;

CREATE UNIQUE INDEX IF NOT EXISTS uk_mv_admissions_rollup_grain
    ON analytics.mv_admissions_rollup (
        year_no, school_id, province_id, source_major_id, canonical_major_id,
        subject_id, plan_type_key, batch_id
    );

CREATE INDEX IF NOT EXISTS idx_mv_admissions_year_school_province_major
    ON analytics.mv_admissions_rollup (
        year_no, school_id, province_id, canonical_major_id
    );

CREATE INDEX IF NOT EXISTS idx_mv_admissions_year_school_major
    ON analytics.mv_admissions_rollup (year_no, school_id, canonical_major_id);
"""


def upgrade() -> None:
    op.execute(sa.text(MATERIALIZED_VIEW_SQL))
    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_plan_school_year_province_major
                ON fact.plan (school_id, year_id, province_id, major_id);
            CREATE INDEX IF NOT EXISTS idx_admission_summary_plan_cover
                ON fact.admission_summary (plan_id)
                INCLUDE (admitted_count, min_score, max_score, min_rank_no);
            CREATE INDEX IF NOT EXISTS idx_admission_record_year_province_enrolled
                ON fact.admission_record (year_id, province_id, is_enrolled);
            CREATE INDEX IF NOT EXISTS idx_admission_record_year_channel_enrolled
                ON fact.admission_record (year_id, channel_id, is_enrolled);
            CREATE INDEX IF NOT EXISTS idx_candidate_profile_year_gender
                ON fact.candidate_profile (year_no, gender_name);
            CREATE INDEX IF NOT EXISTS idx_student_identity_year_name
                ON fact.student_identity (year_no, student_name);
            CREATE INDEX IF NOT EXISTS idx_message_conversation_id_desc
                ON ai.message (conversation_id, id DESC);
            CREATE INDEX IF NOT EXISTS idx_knowledge_document_school_type_status
                ON ai.knowledge_document (school_id, document_type, status);
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP MATERIALIZED VIEW IF EXISTS analytics.mv_admissions_rollup"))
    op.execute(sa.text("DROP SCHEMA IF EXISTS analytics"))
    for statement in (
        "DROP INDEX IF EXISTS fact.idx_plan_school_year_province_major",
        "DROP INDEX IF EXISTS fact.idx_admission_summary_plan_cover",
        "DROP INDEX IF EXISTS fact.idx_admission_record_year_province_enrolled",
        "DROP INDEX IF EXISTS fact.idx_admission_record_year_channel_enrolled",
        "DROP INDEX IF EXISTS fact.idx_candidate_profile_year_gender",
        "DROP INDEX IF EXISTS fact.idx_student_identity_year_name",
        "DROP INDEX IF EXISTS ai.idx_message_conversation_id_desc",
        "DROP INDEX IF EXISTS ai.idx_knowledge_document_school_type_status",
    ):
        op.execute(sa.text(statement))
