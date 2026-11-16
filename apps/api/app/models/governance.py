from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MetricDefinition(Base):
    __tablename__ = "metric_definition"
    __table_args__ = {"schema": "gov"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    metric_code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    metric_name: Mapped[str] = mapped_column(String(255), nullable=False)
    metric_formula: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    version_no: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
