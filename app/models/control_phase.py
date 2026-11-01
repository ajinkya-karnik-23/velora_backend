"""Phase runs — one control's progress through DE, OE, RF, YE and RM rounds.

Each row is one round of testing a phase: its size, the samples it drew and
how it concluded. A remediation round (phase "RM") points at the run it
remediates, so the trail reads "OE failed → RM 1 → RM 2 passed". Phases not
yet reached have no row; they are locked until the previous one is approved.

The hand-over to the reviewer and the verdict stay in control_review_status,
which always describes the control's *current* run. Approving a run moves the
control on and clears that row for the next phase.
"""

from __future__ import annotations

from sqlalchemy import JSON, BigInteger, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BigIntTimestampMixin

ACTIVE = "active"
APPROVED = "approved"
FAILED = "failed"


class ControlPhaseRun(BigIntTimestampMixin, Base):
    __tablename__ = "control_phase_runs"
    __table_args__ = (Index("ix_control_phase_runs_config_control_id", "config_control_id"),)

    phase_run_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    config_control_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("config_controls.config_control_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    # DE | OE | RF | YE | RM
    phase: Mapped[str] = mapped_column(String(4), nullable=False)
    # RM only: the phase run being remediated (always the original phase's
    # run, so successive rounds share it) and the round number.
    remediates_run_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("control_phase_runs.phase_run_id", ondelete="CASCADE"),
        nullable=True,
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # active | approved | failed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ACTIVE)

    # Size: the matrix cell as written, where it came from (rule | matrix |
    # sub_sampling | none), and the tester's override with its reason.
    matrix_value: Mapped[str | None] = mapped_column(String(50), nullable=True)
    size_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    override_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    override_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
    )
    override_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # When the tester computed the run's sample count on the Controls table
    # (a presentation step: the server sized the run already). Kept on the run
    # so the count stays shown in every browser until the column is reset.
    size_computed_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    selected_samples: Mapped[list | None] = mapped_column(JSON, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    concluded_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    concluded_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
    )

    overrider: Mapped[User | None] = relationship(foreign_keys=[override_by])  # noqa: F821
    concluder: Mapped[User | None] = relationship(foreign_keys=[concluded_by])  # noqa: F821


class ControlPhaseEvent(BigIntTimestampMixin, Base):
    """One step in a control's phase history. Append-only."""

    __tablename__ = "control_phase_events"
    __table_args__ = (Index("ix_control_phase_events_config_control_id", "config_control_id"),)

    event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    config_control_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("config_controls.config_control_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    phase_run_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("control_phase_runs.phase_run_id", ondelete="CASCADE"),
        nullable=True,
    )
    # started | sized | overridden | submitted | returned | approved | failed
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    actor_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
    )
    event_time: Mapped[int] = mapped_column(BigInteger, nullable=False)

    actor: Mapped[User | None] = relationship(foreign_keys=[actor_id])  # noqa: F821
