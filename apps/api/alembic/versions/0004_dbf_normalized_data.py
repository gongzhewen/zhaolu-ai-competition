
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_dbf_normalized_data"
down_revision = "0003_dbf_import"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "region",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("region_code", sa.String(length=32), nullable=False, unique=True),
        sa.Column("region_name", sa.String(length=128), nullable=False),
        sa.Column("parent_code", sa.String(length=32)),
        sa.Column("region_level", sa.Integer()),
        sa.Column("data_version", sa.String(length=64)),
        schema="dim",
    )

    op.create_table(
        "candidate_profile",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("candidate_key", sa.String(length=128), nullable=False),
        sa.Column("year_no", sa.Integer(), nullable=False),
        sa.Column("region_code", sa.String(length=32)),
        sa.Column("region_name", sa.String(length=128)),
        sa.Column("gender_code", sa.String(length=8)),
        sa.Column("gender_name", sa.String(length=32)),
        sa.Column("ethnicity_code", sa.String(length=16)),
        sa.Column("ethnicity_name", sa.String(length=64)),
        sa.Column("exam_type_code", sa.String(length=16)),
        sa.Column("exam_type_name", sa.String(length=64)),
        sa.Column("subject_category_code", sa.String(length=16)),
        sa.Column("candidate_type_code", sa.String(length=16)),
        sa.Column("foreign_language_code", sa.String(length=16)),
        sa.Column("source_school_code", sa.String(length=32)),
        sa.Column("source_school_name", sa.String(length=255)),
        sa.Column("household_type_code", sa.String(length=16)),
        sa.Column("data_version", sa.String(length=64), nullable=False),
        schema="fact",
    )
    op.create_index(
        "idx_candidate_profile_key",
        "candidate_profile",
        ["candidate_key"],
        schema="fact",
    )
    op.create_index(
        "idx_candidate_profile_region",
        "candidate_profile",
        ["year_no", "region_code"],
        schema="fact",
    )

    op.create_table(
        "exam_subject_score",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("candidate_key", sa.String(length=128), nullable=False),
        sa.Column("year_no", sa.Integer(), nullable=False),
        sa.Column("exam_number", sa.String(length=32)),
        sa.Column("subject_code", sa.String(length=16), nullable=False),
        sa.Column("subject_name", sa.String(length=64)),
        sa.Column("score_type", sa.String(length=16)),
        sa.Column("exam_year_month", sa.String(length=16)),
        sa.Column("score", sa.Numeric(8, 2)),
        sa.Column("grade_point", sa.Numeric(8, 2)),
        sa.Column("data_version", sa.String(length=64), nullable=False),
        schema="fact",
    )
    op.create_index(
        "idx_exam_subject_score_candidate",
        "exam_subject_score",
        ["candidate_key", "subject_code"],
        schema="fact",
    )

    op.create_table(
        "major_choice",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("candidate_key", sa.String(length=128), nullable=False),
        sa.Column("year_no", sa.Integer(), nullable=False),
        sa.Column("batch_code", sa.String(length=16)),
        sa.Column("subject_code", sa.String(length=16)),
        sa.Column("plan_type_code", sa.String(length=16)),
        sa.Column("group_code", sa.String(length=16)),
        sa.Column("choice_order", sa.Integer()),
        sa.Column("major_code", sa.String(length=64)),
        sa.Column("major_name", sa.String(length=255)),
        sa.Column("data_version", sa.String(length=64), nullable=False),
        schema="fact",
    )
    op.create_index(
        "idx_major_choice_candidate",
        "major_choice",
        ["candidate_key", "choice_order"],
        schema="fact",
    )

    op.create_table(
        "candidate_resume",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("candidate_key", sa.String(length=128), nullable=False),
        sa.Column("year_no", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date()),
        sa.Column("end_date", sa.Date()),
        sa.Column("school_name", sa.String(length=255)),
        sa.Column("role_name", sa.String(length=128)),
        sa.Column("award_name", sa.String(length=255)),
        sa.Column("data_version", sa.String(length=64), nullable=False),
        schema="fact",
    )
    op.create_index(
        "idx_candidate_resume_candidate",
        "candidate_resume",
        ["candidate_key", "start_date"],
        schema="fact",
    )

    op.create_table(
        "medical_summary",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("candidate_key", sa.String(length=128), nullable=False),
        sa.Column("year_no", sa.Integer(), nullable=False),
        sa.Column("medical_result_code", sa.String(length=16)),
        sa.Column("medical_result_name", sa.String(length=64)),
        sa.Column("restricted_major_codes", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("data_version", sa.String(length=64), nullable=False),
        schema="fact",
    )
    op.create_index(
        "idx_medical_summary_candidate",
        "medical_summary",
        ["candidate_key"],
        schema="fact",
    )


def downgrade() -> None:
    op.drop_index("idx_medical_summary_candidate", table_name="medical_summary", schema="fact")
    op.drop_table("medical_summary", schema="fact")
    op.drop_index("idx_candidate_resume_candidate", table_name="candidate_resume", schema="fact")
    op.drop_table("candidate_resume", schema="fact")
    op.drop_index("idx_major_choice_candidate", table_name="major_choice", schema="fact")
    op.drop_table("major_choice", schema="fact")
    op.drop_index("idx_exam_subject_score_candidate", table_name="exam_subject_score", schema="fact")
    op.drop_table("exam_subject_score", schema="fact")
    op.drop_index("idx_candidate_profile_region", table_name="candidate_profile", schema="fact")
    op.drop_index("idx_candidate_profile_key", table_name="candidate_profile", schema="fact")
    op.drop_table("candidate_profile", schema="fact")
    op.drop_table("region", schema="dim")
