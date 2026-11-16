from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DbfImportBatch(Base):
    __tablename__ = "dbf_import_batch"
    __table_args__ = {"schema": "gov"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    batch_name: Mapped[str] = mapped_column(String(255), nullable=False)
    school_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("dim.school.id"))
    profile_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("gov.dbf_interface_profile.id"))
    source_file: Mapped[str | None] = mapped_column(String(255))
    source_sha256: Mapped[str | None] = mapped_column(String(64))
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    total_files: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_records: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    encoding: Mapped[str | None] = mapped_column(String(32))
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DbfImportTable(Base):
    __tablename__ = "dbf_import_table"
    __table_args__ = {"schema": "gov"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("gov.dbf_import_batch.id", ondelete="CASCADE"),
        nullable=False,
    )
    table_name: Mapped[str] = mapped_column(String(128), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    field_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    header_length: Mapped[int | None] = mapped_column(Integer)
    record_length: Mapped[int | None] = mapped_column(Integer)
    language_driver: Mapped[int | None] = mapped_column(Integer)
    fields: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DbfImportRow(Base):
    __tablename__ = "dbf_import_row"
    __table_args__ = (
        UniqueConstraint("table_id", "row_no", name="uk_dbf_import_row_table_row"),
        {"schema": "gov"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("gov.dbf_import_batch.id", ondelete="CASCADE"),
        nullable=False,
    )
    table_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("gov.dbf_import_table.id", ondelete="CASCADE"),
        nullable=False,
    )
    row_no: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

