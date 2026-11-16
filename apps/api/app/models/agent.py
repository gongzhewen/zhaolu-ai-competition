from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AgentMemory(Base):
    __tablename__ = "agent_memory"
    __table_args__ = (
        UniqueConstraint("user_id", "school_id", "memory_key", name="uk_agent_memory_scope_key"),
        {"schema": "ai"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sys.user_account.id"))
    school_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("dim.school.id"))
    conversation_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("ai.conversation.id"))
    memory_type: Mapped[str] = mapped_column(String(64), nullable=False)
    memory_key: Mapped[str] = mapped_column(String(255), nullable=False)
    memory_value: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.8"), nullable=False)
    importance: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.5"), nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ResponseEvaluation(Base):
    __tablename__ = "response_evaluation"
    __table_args__ = {"schema": "ai"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    message_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("ai.message.id"))
    school_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("dim.school.id"))
    intent: Mapped[str | None] = mapped_column(String(128))
    tool_names: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    self_check: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    loss: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    action: Mapped[str] = mapped_column(String(64), default="accepted", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PromptTemplate(Base):
    __tablename__ = "prompt_template"
    __table_args__ = (
        UniqueConstraint("school_id", "template_code", "strategy_key", name="uk_prompt_template_scope"),
        {"schema": "ai"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    template_code: Mapped[str] = mapped_column(String(128), nullable=False)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    school_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("dim.school.id"))
    template_name: Mapped[str] = mapped_column(String(255), nullable=False)
    template_text: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_key: Mapped[str] = mapped_column(String(64), nullable=False)
    weight: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("1.0"), nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    version_no: Mapped[str] = mapped_column(String(64), default="v1", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class OptimizationEvent(Base):
    __tablename__ = "optimization_event"
    __table_args__ = {"schema": "ai"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    school_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("dim.school.id"))
    template_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("ai.prompt_template.id"))
    signal_type: Mapped[str] = mapped_column(String(64), nullable=False)
    reward: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    previous_weight: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    new_weight: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    learning_rate: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    event_metadata: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DbfInterfaceProfile(Base):
    __tablename__ = "dbf_interface_profile"
    __table_args__ = (
        UniqueConstraint("school_id", "profile_code", name="uk_dbf_profile_school_code"),
        {"schema": "gov"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    school_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("dim.school.id"), nullable=False)
    profile_code: Mapped[str] = mapped_column(String(128), nullable=False)
    profile_name: Mapped[str] = mapped_column(String(255), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    table_catalog: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    field_semantics: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    canonical_mapping: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    validation_rules: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class UserSchool(Base):
    __tablename__ = "user_school"
    __table_args__ = {"schema": "sys"}

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys.user_account.id"), primary_key=True)
    school_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("dim.school.id"), primary_key=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

