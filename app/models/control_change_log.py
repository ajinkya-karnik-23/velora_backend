"""ControlChangeLog model — maps to the ``control_change_log`` table."""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BigIntTimestampMixin


class ControlChangeLog(BigIntTimestampMixin, Base):
    __tablename__ = "control_change_log"
    __table_args__ = (
        Index("ix_control_change_log_control_id", "control_id"),
        Index("ix_control_change_log_changed_by", "changed_by"),
        Index("ix_control_change_log_from_version", "from_version"),
        Index("ix_control_change_log_to_version", "to_version"),
        CheckConstraint(
            "change_percentage IS NULL OR (change_percentage >= 0 AND change_percentage <= 100)",
            name="ck_control_change_log_pct_range",
        ),
    )

    change_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    control_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("control_repository.control_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    changed_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    from_version: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("versions.version_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=True,
    )
    to_version: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("versions.version_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    change_type: Mapped[str] = mapped_column(String(50), nullable=False)
    change_timestamp: Mapped[int] = mapped_column(BigInteger, nullable=False)
    new_control_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    new_control_desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    change_percentage: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    control: Mapped[ControlRepository] = relationship()  # noqa: F821
    changer: Mapped[User] = relationship()  # noqa: F821
    version_from: Mapped[Version | None] = relationship(  # noqa: F821
        foreign_keys=[from_version]
    )
    version_to: Mapped[Version] = relationship(  # noqa: F821
        foreign_keys=[to_version]
    )
