"""ConfigControl model — maps to the ``config_controls`` table."""

from __future__ import annotations

from sqlalchemy import JSON, BigInteger, ForeignKey, Index, String, UniqueConstraint
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

    # Snapshot of the entity-specific control JSON resolved at attach time
    # (control_number + the cycle's entity_code) — captured once here so it
    # survives even if the source JSON on disk later changes.
    entity_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_detail_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Sample size computed from the client's sampling matrix (or falling back
    # to the control JSON's own "Sample Size"). Stored as text because the
    # matrix legitimately contains ranges such as "2 to 5".
    sample_size: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # "matrix" | "control_json" — where the stored sample_size came from.
    sample_size_source: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Relationships
    review_cycle: Mapped[ReviewCycle] = relationship()  # noqa: F821
    control: Mapped[ControlRepository] = relationship()  # noqa: F821
    test: Mapped[ControlTest | None] = relationship(  # noqa: F821
        back_populates="config_control", uselist=False, cascade="all, delete-orphan"
    )
