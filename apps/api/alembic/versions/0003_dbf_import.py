
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_dbf_import"
down_revision = "0002_import_pipeline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dbf_import_batch",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("batch_name", sa.String(length=255), nullable=False),
        sa.Column("source_file", sa.String(length=255)),
        sa.Column("source_sha256", sa.String(length=64)),
        sa.Column("file_size", sa.BigInteger()),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("total_files", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("total_records", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("encoding", sa.String(length=32)),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        schema="gov",
    )
    op.create_table(
        "dbf_import_table",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("batch_id", sa.BigInteger(), sa.ForeignKey("gov.dbf_import_batch.id", ondelete="CASCADE"), nullable=False),
        sa.Column("table_name", sa.String(length=128), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("record_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("field_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("header_length", sa.Integer()),
        sa.Column("record_length", sa.Integer()),
        sa.Column("language_driver", sa.Integer()),
        sa.Column(
            "fields",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        schema="gov",
    )
    op.create_table(
        "dbf_import_row",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("batch_id", sa.BigInteger(), sa.ForeignKey("gov.dbf_import_batch.id", ondelete="CASCADE"), nullable=False),
        sa.Column("table_id", sa.BigInteger(), sa.ForeignKey("gov.dbf_import_table.id", ondelete="CASCADE"), nullable=False),
        sa.Column("row_no", sa.Integer(), nullable=False),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("table_id", "row_no", name="uk_dbf_import_row_table_row"),
        schema="gov",
    )
    op.create_index(
        "ix_dbf_import_table_batch",
        "dbf_import_table",
        ["batch_id"],
        schema="gov",
    )
    op.create_index(
        "ix_dbf_import_row_batch_table",
        "dbf_import_row",
        ["batch_id", "table_id"],
        schema="gov",
    )


def downgrade() -> None:
    op.drop_index("ix_dbf_import_row_batch_table", table_name="dbf_import_row", schema="gov")
    op.drop_index("ix_dbf_import_table_batch", table_name="dbf_import_table", schema="gov")
    op.drop_table("dbf_import_row", schema="gov")
    op.drop_table("dbf_import_table", schema="gov")
    op.drop_table("dbf_import_batch", schema="gov")
