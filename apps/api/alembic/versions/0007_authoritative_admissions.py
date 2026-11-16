
import sqlalchemy as sa
from alembic import op

revision = "0007_authoritative_admissions"
down_revision = "0006_plan_management"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "authoritative_admission_stat",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("year_no", sa.Integer(), nullable=False),
        sa.Column("college_name", sa.String(length=255)),
        sa.Column("major_name", sa.String(length=255), nullable=False),
        sa.Column("plan_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("regular_admitted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("zhuan_admitted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_admitted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_file", sa.String(length=512), nullable=False),
        sa.Column("data_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("year_no", "major_name", "data_version", name="uk_authoritative_admission_major"),
        schema="fact",
    )
    op.create_index(
        "idx_authoritative_admission_year",
        "authoritative_admission_stat",
        ["year_no", "major_name"],
        schema="fact",
    )


def downgrade() -> None:
    op.drop_index("idx_authoritative_admission_year", table_name="authoritative_admission_stat", schema="fact")
    op.drop_table("authoritative_admission_stat", schema="fact")
