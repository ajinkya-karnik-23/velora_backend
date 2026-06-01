"""ReviewCycle model — maps to the ``review_cycles`` table."""

from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BigIntTimestampMixin


class ReviewCycle(BigIntTimestampMixin, Base):
    __tablename__ = "review_cycles"
    __table_args__ = (
        Index("ix_review_cycles_client_id", "client_id"),
        Index("ix_review_cycles_project_lead", "project_lead"),
        Index("ix_review_cycles_status", "status"),
        CheckConstraint("start_date <= due_date", name="ck_review_cycles_start_lte_due"),
        CheckConstraint(
            "end_date IS NULL OR end_date >= start_date",
            name="ck_review_cycles_end_gte_start",
        ),
        CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 100)",
            name="ck_review_cycles_score_range",
        ),
    )

    cycle_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("clients.client_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    project_lead: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="SET NULL", onupdate="CASCADE"),
        nullable=True,
    )
    review_period: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    audit_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(20), nullable=True)
    framework: Mapped[str | None] = mapped_column(String(100), nullable=True)
    start_date: Mapped[int] = mapped_column(BigInteger, nullable=False)
    due_date: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_date: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Draft")
    score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    overview: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    client: Mapped["Client"] = relationship()  # noqa: F821
    lead: Mapped["User | None"] = relationship(foreign_keys=[project_lead])  # noqa: F821
    engagement_team: Mapped[list["EngagementTeam"]] = relationship(  # noqa: F821
        back_populates="review_cycle"
    )
