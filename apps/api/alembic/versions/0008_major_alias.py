
import sqlalchemy as sa
from alembic import op

revision = "0008_major_alias"
down_revision = "0007_authoritative_admissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "major_alias",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("source_name_key", sa.String(length=255), nullable=False),
        sa.Column("province_id", sa.BigInteger(), sa.ForeignKey("dim.province.id")),
        sa.Column("canonical_major_id", sa.BigInteger(), sa.ForeignKey("dim.major.id"), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        schema="dim",
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uk_major_alias_scope
        ON dim.major_alias (source_name_key, COALESCE(province_id, 0))
        """
    )
    op.create_index(
        "idx_major_alias_canonical",
        "major_alias",
        ["canonical_major_id", "is_active"],
        schema="dim",
    )


def downgrade() -> None:
    op.drop_index("idx_major_alias_canonical", table_name="major_alias", schema="dim")
    op.execute("DROP INDEX IF EXISTS dim.uk_major_alias_scope")
    op.drop_table("major_alias", schema="dim")

