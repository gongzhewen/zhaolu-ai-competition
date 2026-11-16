
import sqlalchemy as sa
from alembic import op

revision = "0009_canonicalization"
down_revision = "0008_major_alias"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "canonicalization_event",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("pipeline", sa.String(length=32), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("source_value", sa.String(length=512), nullable=False),
        sa.Column("canonical_value", sa.String(length=512), nullable=False),
        sa.Column("rule_code", sa.String(length=64), nullable=False),
        sa.Column("scope_key", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False, server_default="1.0"),
        sa.Column("hit_count", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        schema="gov",
    )
    op.create_index(
        "uk_canonicalization_event",
        "canonicalization_event",
        ["pipeline", "entity_type", "source_value", "canonical_value", "scope_key"],
        unique=True,
        schema="gov",
    )
    op.create_index(
        "idx_canonicalization_event_type",
        "canonicalization_event",
        ["entity_type", "last_seen_at"],
        schema="gov",
    )


def downgrade() -> None:
    op.drop_index("idx_canonicalization_event_type", table_name="canonicalization_event", schema="gov")
    op.drop_index("uk_canonicalization_event", table_name="canonicalization_event", schema="gov")
    op.drop_table("canonicalization_event", schema="gov")
