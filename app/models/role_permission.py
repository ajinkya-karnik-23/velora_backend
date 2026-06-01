"""RolePermission junction model — maps to the ``role_permissions`` table."""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BigIntTimestampMixin


class RolePermission(BigIntTimestampMixin, Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_role_perm"),
        Index("ix_role_permissions_permission_id", "permission_id"),
    )

    role_permission_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    role_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("roles.role_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    permission_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("permissions.permission_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )

    # Relationships
    role: Mapped["Role"] = relationship(back_populates="role_permissions")  # noqa: F821
    permission: Mapped["Permission"] = relationship(  # noqa: F821
        back_populates="role_permissions"
    )
