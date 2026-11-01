"""SampleReview — the reviewer's word on one tested sample.

Beside the tool's result (testing output) and the tester's judgement
(sample_judgements), the reviewer may change the outcome, rewrite the
conclusion, comment, involve others and record a verdict on the sample. The
reviewer's outcome, where set, is the sample's effective result everywhere.
Every change is also kept as an event, which is what the tester is notified of.
"""

from __future__ import annotations

from sqlalchemy import JSON, BigInteger, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BigIntTimestampMixin


class SampleReview(BigIntTimestampMixin, Base):
    __tablename__ = "sample_reviews"
    __table_args__ = (
        UniqueConstraint("config_control_id", "sample_no", name="uq_sample_reviews_control_sample"),
    )

    review_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    config_control_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("config_controls.config_control_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    sample_no: Mapped[int] = mapped_column(Integer, nullable=False)
    # The reviewer's outcome: PASS | FAIL | NOT_VALIDATED; null keeps the tester's.
    result: Mapped[str | None] = mapped_column(String(50), nullable=True)
    conclusion: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # [{"name": ..., "email": ...}] — people the reviewer brought in.
    involved: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # under_review | reviewed | approved | returned_to_tester
    verdict: Mapped[str | None] = mapped_column(String(30), nullable=True)
    verdict_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="SET NULL", onupdate="CASCADE"),
        nullable=True,
    )

    reviewer: Mapped[User | None] = relationship(foreign_keys=[reviewed_by])  # noqa: F821


class SampleReviewEvent(BigIntTimestampMixin, Base):
    """One reviewer action on a sample. Append-only."""

    __tablename__ = "sample_review_events"
    __table_args__ = (Index("ix_sample_review_events_config_control_id", "config_control_id"),)

    event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    config_control_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("config_controls.config_control_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    sample_no: Mapped[int] = mapped_column(Integer, nullable=False)
    # edited | commented | involved | verdict
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="SET NULL", onupdate="CASCADE"),
        nullable=True,
    )
    event_time: Mapped[int] = mapped_column(BigInteger, nullable=False)

    actor: Mapped[User | None] = relationship(foreign_keys=[actor_id])  # noqa: F821
