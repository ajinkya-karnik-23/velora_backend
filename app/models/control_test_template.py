"""ControlTestTemplate — canonical test definitions for a control, cycle-independent."""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, BigIntTimestampMixin


class ControlTestTemplate(BigIntTimestampMixin, Base):
    __tablename__ = "control_test_templates"
    __table_args__ = (
        Index("ix_control_test_templates_control_id", "control_id"),
    )

    template_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    control_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("control_repository.control_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    source_test_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    tests: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
