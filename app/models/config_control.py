"""ConfigControl model — maps to the ``config_controls`` table."""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BigIntTimestampMixin


class ConfigControl(BigIntTimestampMixin, Base):
    __tablename__ = "config_controls"
    __table_args__ = (
        UniqueConstraint("cycle_id", "control_id", name="uq_config_controls_cycle_control"),
        Index("ix_config_controls_control_id", "control_id"),
    )

    config_control_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    cycle_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("review_cycles.cycle_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    control_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("control_repository.control_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )

    # Relationships
    review_cycle: Mapped[ReviewCycle] = relationship()  # noqa: F821
    control: Mapped[ControlRepository] = relationship()  # noqa: F821
    test: Mapped[ControlTest | None] = relationship(  # noqa: F821
        back_populates="config_control", uselist=False, cascade="all, delete-orphan"
    )
