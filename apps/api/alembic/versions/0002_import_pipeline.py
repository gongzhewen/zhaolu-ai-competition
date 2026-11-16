
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_import_pipeline"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("etl_job", sa.Column("file_size", sa.BigInteger()), schema="gov")
    op.add_column("etl_job", sa.Column("file_suffix", sa.String(length=16)), schema="gov")
    op.add_column("etl_job", sa.Column("encoding", sa.String(length=32)), schema="gov")
    op.add_column("etl_job", sa.Column("sheet_name", sa.String(length=255)), schema="gov")
    op.add_column("etl_job", sa.Column("data_type", sa.String(length=64)), schema="gov")
    op.add_column(
        "etl_job",
        sa.Column("headers", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        schema="gov",
    )
    op.add_column(
        "etl_job",
        sa.Column("preview_data", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        schema="gov",
    )
    op.add_column(
        "etl_job",
        sa.Column("mapping_data", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        schema="gov",
    )
    op.add_column(
        "etl_job",
        sa.Column("mapping_confirmed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        schema="gov",
    )
    op.add_column("etl_job", sa.Column("target_table", sa.String(length=255)), schema="gov")
    op.add_column(
        "etl_job",
        sa.Column("total_rows", sa.Integer(), server_default=sa.text("0"), nullable=False),
        schema="gov",
    )
    op.add_column(
        "etl_job",
        sa.Column("valid_rows", sa.Integer(), server_default=sa.text("0"), nullable=False),
        schema="gov",
    )
    op.add_column(
        "etl_job",
        sa.Column("invalid_rows", sa.Integer(), server_default=sa.text("0"), nullable=False),
        schema="gov",
    )
    op.add_column("etl_job", sa.Column("started_at", sa.DateTime(timezone=True)), schema="gov")
    op.add_column("etl_job", sa.Column("finished_at", sa.DateTime(timezone=True)), schema="gov")

    op.create_table(
        "import_field_mapping",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("job_id", sa.BigInteger(), nullable=False),
        sa.Column("source_field", sa.String(length=255), nullable=False),
        sa.Column("target_field", sa.String(length=128)),
        sa.Column("confidence", sa.Float()),
        sa.Column("confirmed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        schema="gov",
    )
    op.create_table(
        "import_record",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("job_id", sa.BigInteger(), nullable=False),
        sa.Column("row_no", sa.Integer(), nullable=False),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("normalized_data", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        schema="gov",
    )
    op.create_index(
        "ix_import_field_mapping_job",
        "import_field_mapping",
        ["job_id"],
        schema="gov",
    )
    op.create_index(
        "ix_import_record_job_status",
        "import_record",
        ["job_id", "status"],
        schema="gov",
    )
    op.create_index(
        "ix_etl_job_status",
        "etl_job",
        ["job_status", "created_at"],
        schema="gov",
    )


def downgrade() -> None:
    op.drop_index("ix_etl_job_status", table_name="etl_job", schema="gov")
    op.drop_index("ix_import_record_job_status", table_name="import_record", schema="gov")
    op.drop_index("ix_import_field_mapping_job", table_name="import_field_mapping", schema="gov")

    op.drop_table("import_record", schema="gov")
    op.drop_table("import_field_mapping", schema="gov")

    for column in [
        "finished_at",
        "started_at",
        "invalid_rows",
        "valid_rows",
        "total_rows",
        "target_table",
        "mapping_confirmed",
        "mapping_data",
        "preview_data",
        "headers",
        "data_type",
        "sheet_name",
        "encoding",
        "file_suffix",
        "file_size",
    ]:
        op.drop_column("etl_job", column, schema="gov")
