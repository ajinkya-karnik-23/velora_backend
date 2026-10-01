"""Review workflow state for an attached control.

Testing and review are separate hands: a tester works a control's samples and
submits it, a reviewer takes it from there. The tester's side of the lifecycle
(pending, in progress, processed) is derived from testing progress and is never
stored; only the hand-over and what the reviewer decided are recorded here, one
row per attached control.

Every transition is also appended to `control_review_events`, so the trail of
who moved a control where survives later changes of status.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BigIntTimestampMixin

# Stored statuses — the tester-side states are derived, not recorded.
SUBMITTED = "submitted_for_review"
UNDER_REVIEW = "under_review"
REVIEWED = "reviewed"
APPROVED = "approved"
RETURNED = "returned_to_tester"

REVIEW_STATUSES = (SUBMITTED, UNDER_REVIEW, REVIEWED, APPROVED, RETURNED)
# What a reviewer may decide once a control has been submitted.
REVIEWER_VERDICTS = (UNDER_REVIEW, REVIEWED, APPROVED, RETURNED)


class ControlReviewStatus(BigIntTimestampMixin, Base):
    __tablename__ = "control_review_status"
    __table_args__ = (UniqueConstraint("config_control_id", name="uq_control_review_status_cc"),)

    review_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    config_control_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("config_controls.config_control_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    submitted_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="SET NULL", onupdate="CASCADE"),
        nullable=True,
    )
    submitted_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="SET NULL", onupdate="CASCADE"),
        nullable=True,
    )
    reviewed_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    config_control: Mapped[ConfigControl] = relationship()  # noqa: F821
    submitter: Mapped[User | None] = relationship(foreign_keys=[submitted_by])  # noqa: F821
    reviewer: Mapped[User | None] = relationship(foreign_keys=[reviewed_by])  # noqa: F821


class ControlReviewEvent(BigIntTimestampMixin, Base):
    """One hand-over or verdict, kept for the trail. Append-only."""

    __tablename__ = "control_review_events"
    __table_args__ = (Index("ix_control_review_events_config_control_id", "config_control_id"),)

    event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    config_control_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("config_controls.config_control_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    # Null when the control had no stored status yet (first submission).
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="SET NULL", onupdate="CASCADE"),
        nullable=True,
    )
    # "tester" or "reviewer" — which hand made the move.
    actor_persona: Mapped[str] = mapped_column(String(20), nullable=False)
    event_time: Mapped[int] = mapped_column(BigInteger, nullable=False)

    actor: Mapped[User | None] = relationship(foreign_keys=[actor_id])  # noqa: F821
