from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EnrollmentStatus(Base):
    __tablename__ = "enrollment_status"
    __table_args__ = (
        UniqueConstraint("candidate_key", "year_no", name="uk_enrollment_status_candidate_year"),
        {"schema": "fact"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    candidate_key: Mapped[str] = mapped_column(String(128), nullable=False)
    year_no: Mapped[int] = mapped_column(Integer, nullable=False)
    candidate_no: Mapped[str | None] = mapped_column(String(64))
    student_name: Mapped[str | None] = mapped_column(String(128))
    is_enrolled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enrolled_at: Mapped[date | None] = mapped_column(Date)
    remark: Mapped[str | None] = mapped_column(Text)
    source_file: Mapped[str | None] = mapped_column(String(255))
    data_version: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
