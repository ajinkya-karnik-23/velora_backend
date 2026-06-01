"""Version model — maps to the ``versions`` table."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BigIntTimestampMixin


class Version(BigIntTimestampMixin, Base):
    __tablename__ = "versions"
    __table_args__ = (
        # Partial unique index: only one row where is_current = TRUE
        Index("ix_versions_is_current", "is_current", unique=True, postgresql_where="is_current"),
    )

    version_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    version_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    released_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
