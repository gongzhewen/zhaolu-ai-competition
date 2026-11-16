from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EtlJob(Base):
    __tablename__ = "etl_job"
    __table_args__ = {"schema": "gov"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    job_name: Mapped[str] = mapped_column(String(255), nullable=False)
    job_status: Mapped[str] = mapped_column(String(32), nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(255))
    file_path: Mapped[str | None] = mapped_column(Text)
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    file_suffix: Mapped[str | None] = mapped_column(String(16))
    encoding: Mapped[str | None] = mapped_column(String(32))
    sheet_name: Mapped[str | None] = mapped_column(String(255))
    year_no: Mapped[int | None] = mapped_column(Integer)
    data_type: Mapped[str | None] = mapped_column(String(64))
    data_version: Mapped[str | None] = mapped_column(String(64))
    headers: Mapped[list | None] = mapped_column(JSONB, default=list)
    preview_data: Mapped[list | None] = mapped_column(JSONB, default=list)
    mapping_data: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    mapping_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    target_table: Mapped[str | None] = mapped_column(String(255))
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    valid_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    invalid_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImportFieldMapping(Base):
    __tablename__ = "import_field_mapping"
    __table_args__ = {"schema": "gov"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_field: Mapped[str] = mapped_column(String(255), nullable=False)
    target_field: Mapped[str | None] = mapped_column(String(128))
    confidence: Mapped[float | None] = mapped_column(Float)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImportRecord(Base):
    __tablename__ = "import_record"
    __table_args__ = {"schema": "gov"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    row_no: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    normalized_data: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class QualityRule(Base):
    __tablename__ = "quality_rule"
    __table_args__ = {"schema": "gov"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rule_code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    target_table: Mapped[str] = mapped_column(String(255), nullable=False)
    target_field: Mapped[str | None] = mapped_column(String(255))
    rule_type: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_expression: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DataIssue(Base):
    __tablename__ = "data_issue"
    __table_args__ = {"schema": "gov"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rule_id: Mapped[int | None] = mapped_column(BigInteger)
    target_table: Mapped[str | None] = mapped_column(String(255))
    record_key: Mapped[str | None] = mapped_column(String(255))
    issue_type: Mapped[str | None] = mapped_column(String(64))
    issue_message: Mapped[str | None] = mapped_column(Text)
    issue_status: Mapped[str] = mapped_column(String(32), default="OPEN")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
