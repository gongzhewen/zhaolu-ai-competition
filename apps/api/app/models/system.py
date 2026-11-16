from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, Table, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

user_role = Table(
    "user_role",
    Base.metadata,
    Column("user_id", BigInteger, ForeignKey("sys.user_account.id"), primary_key=True),
    Column("role_id", BigInteger, ForeignKey("sys.role.id"), primary_key=True),
    schema="sys",
)

role_permission = Table(
    "role_permission",
    Base.metadata,
    Column("role_id", BigInteger, ForeignKey("sys.role.id"), primary_key=True),
    Column("permission_id", BigInteger, ForeignKey("sys.permission.id"), primary_key=True),
    schema="sys",
)


class User(Base):
    __tablename__ = "user_account"
    __table_args__ = {"schema": "sys"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    roles: Mapped[list["Role"]] = relationship(
        secondary=user_role,
        lazy="selectin",
        back_populates="users",
    )


class Role(Base):
    __tablename__ = "role"
    __table_args__ = {"schema": "sys"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    role_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    role_name: Mapped[str] = mapped_column(String(128), nullable=False)

    users: Mapped[list[User]] = relationship(
        secondary=user_role,
        lazy="selectin",
        back_populates="roles",
    )
    permissions: Mapped[list["Permission"]] = relationship(
        secondary=role_permission,
        lazy="selectin",
        back_populates="roles",
    )


class Permission(Base):
    __tablename__ = "permission"
    __table_args__ = {"schema": "sys"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    permission_code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    permission_name: Mapped[str] = mapped_column(String(128), nullable=False)
    permission_type: Mapped[str] = mapped_column(String(32), nullable=False)

    roles: Mapped[list[Role]] = relationship(
        secondary=role_permission,
        lazy="selectin",
        back_populates="permissions",
    )
