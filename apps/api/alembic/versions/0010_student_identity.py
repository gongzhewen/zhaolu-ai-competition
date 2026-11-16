
import sqlalchemy as sa
from alembic import op

revision = "0010_student_identity"
down_revision = "0009_canonicalization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "student_identity",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("candidate_key", sa.String(length=128), nullable=False),
        sa.Column("year_no", sa.Integer(), nullable=False),
        sa.Column("candidate_no", sa.String(length=64), nullable=False),
        sa.Column("student_name", sa.String(length=128), nullable=False),
        sa.Column("id_card", sa.String(length=64)),
        sa.Column("phone", sa.String(length=32)),
        sa.Column("address", sa.Text()),
        sa.Column("data_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("candidate_key", "year_no", name="uk_student_identity_candidate_year"),
        schema="fact",
    )
    op.create_index("idx_student_identity_year", "student_identity", ["year_no", "candidate_no"], schema="fact")


def downgrade() -> None:
    op.drop_index("idx_student_identity_year", table_name="student_identity", schema="fact")
    op.drop_table("student_identity", schema="fact")
