"""User model — maps to the ``users`` table."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BigIntTimestampMixin


class User(BigIntTimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_status", "status"),)

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    profile_picture: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Pending")
    two_factor_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    api_access_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_login: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Relationships
    user_roles: Mapped[list["UserRole"]] = relationship(back_populates="user")  # noqa: F821
