from datetime import datetime
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Year(Base):
    __tablename__ = "year"
    __table_args__ = {"schema": "dim"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    year_no: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)


class Province(Base):
    __tablename__ = "province"
    __table_args__ = {"schema": "dim"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    province_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    province_name: Mapped[str] = mapped_column(String(64), nullable=False)


class School(Base):
    __tablename__ = "school"
    __table_args__ = {"schema": "dim"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    school_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    school_name: Mapped[str] = mapped_column(String(255), nullable=False)


class Major(Base):
    __tablename__ = "major"
    __table_args__ = {"schema": "dim"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    school_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("dim.school.id"), nullable=False)
    major_code: Mapped[str] = mapped_column(String(64), nullable=False)
    major_name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject_req: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Subject(Base):
    __tablename__ = "subject"
    __table_args__ = {"schema": "dim"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    subject_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    subject_name: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_type: Mapped[str | None] = mapped_column(String(32))


class Batch(Base):
    __tablename__ = "batch"
    __table_args__ = {"schema": "dim"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    year_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("dim.year.id"))
    batch_code: Mapped[str] = mapped_column(String(64), nullable=False)
    batch_name: Mapped[str] = mapped_column(String(128), nullable=False)


class PlanType(Base):
    __tablename__ = "plan_type"
    __table_args__ = {"schema": "dim"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    type_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    type_name: Mapped[str] = mapped_column(String(128), nullable=False)


class Channel(Base):
    __tablename__ = "channel"
    __table_args__ = {"schema": "dim"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    channel_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    channel_name: Mapped[str] = mapped_column(String(128), nullable=False)
    channel_type: Mapped[str | None] = mapped_column(String(64))

