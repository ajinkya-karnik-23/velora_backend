"""ControlTest model — maps to the ``control_tests_and_evidences`` table."""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BigIntTimestampMixin


class ControlTest(BigIntTimestampMixin, Base):
    __tablename__ = "control_tests_and_evidences"
    __table_args__ = (
        Index("ix_control_tests_config_control_id", "config_control_id"),
    )

    test_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    config_control_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("config_controls.config_control_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    tests: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    config_control: Mapped[ConfigControl] = relationship(  # noqa: F821
        back_populates="test"
    )
