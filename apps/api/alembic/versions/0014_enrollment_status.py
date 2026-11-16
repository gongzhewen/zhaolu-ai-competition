
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014_enrollment_status"
down_revision = "0013_agent_intelligence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "enrollment_status",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("candidate_key", sa.String(length=128), nullable=False),
        sa.Column("year_no", sa.Integer(), nullable=False),
        sa.Column("candidate_no", sa.String(length=64)),
        sa.Column("student_name", sa.String(length=128)),
        sa.Column("is_enrolled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("enrolled_at", sa.Date()),
        sa.Column("remark", sa.Text()),
        sa.Column("source_file", sa.String(length=255)),
        sa.Column("data_version", sa.String(length=64), nullable=False),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("candidate_key", "year_no", name="uk_enrollment_status_candidate_year"),
        schema="fact",
    )
    op.create_index("idx_enrollment_status_year_enrolled", "enrollment_status", ["year_no", "is_enrolled"], schema="fact")
    op.create_index("idx_enrollment_status_candidate_no", "enrollment_status", ["candidate_no"], schema="fact")


def downgrade() -> None:
    op.drop_index("idx_enrollment_status_candidate_no", table_name="enrollment_status", schema="fact")
    op.drop_index("idx_enrollment_status_year_enrolled", table_name="enrollment_status", schema="fact")
    op.drop_table("enrollment_status", schema="fact")
