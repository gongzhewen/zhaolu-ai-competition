
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_student_management"
down_revision = "0004_dbf_normalized_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "student_management",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("candidate_key", sa.String(length=128), nullable=False),
        sa.Column("year_no", sa.Integer(), nullable=False),
        sa.Column("student_status", sa.String(length=32), server_default="NEW", nullable=False),
        sa.Column("follow_up_status", sa.String(length=32), server_default="PENDING", nullable=False),
        sa.Column("owner_name", sa.String(length=128)),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("updated_by_user_id", sa.BigInteger()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("candidate_key", name="uk_student_management_candidate"),
        schema="fact",
    )
    op.create_index(
        "idx_student_management_status",
        "student_management",
        ["student_status", "follow_up_status"],
        schema="fact",
    )
    op.create_index(
        "idx_student_management_owner",
        "student_management",
        ["owner_name"],
        schema="fact",
    )


def downgrade() -> None:
    op.drop_index("idx_student_management_owner", table_name="student_management", schema="fact")
    op.drop_index("idx_student_management_status", table_name="student_management", schema="fact")
    op.drop_table("student_management", schema="fact")
