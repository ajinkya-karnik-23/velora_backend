"""Role model — maps to the ``roles`` table."""

from __future__ import annotations

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BigIntTimestampMixin


class Role(BigIntTimestampMixin, Base):
    __tablename__ = "roles"

    role_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    role_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    # Relationships
    user_roles: Mapped[list["UserRole"]] = relationship(back_populates="role")  # noqa: F821
    role_permissions: Mapped[list["RolePermission"]] = relationship(  # noqa: F821
        back_populates="role"
    )
