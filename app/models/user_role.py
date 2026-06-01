"""UserRole junction model — maps to the ``user_roles`` table."""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BigIntTimestampMixin


class UserRole(BigIntTimestampMixin, Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),
        Index("ix_user_roles_role_id", "role_id"),
    )

    user_role_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    role_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("roles.role_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="user_roles")  # noqa: F821
    role: Mapped["Role"] = relationship(back_populates="user_roles")  # noqa: F821
