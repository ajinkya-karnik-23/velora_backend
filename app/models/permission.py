"""Permission model — maps to the ``permissions`` table."""

from __future__ import annotations

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BigIntTimestampMixin


class Permission(BigIntTimestampMixin, Base):
    __tablename__ = "permissions"

    permission_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    permission_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    permission_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    permission_description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    role_permissions: Mapped[list["RolePermission"]] = relationship(  # noqa: F821
        back_populates="permission"
    )
