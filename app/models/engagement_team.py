"""EngagementTeam model — maps to the ``engagement_team`` table."""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BigIntTimestampMixin


class EngagementTeam(BigIntTimestampMixin, Base):
    __tablename__ = "engagement_team"
    __table_args__ = (
        UniqueConstraint("cycle_id", "user_id", name="uq_engagement_team_cycle_user"),
        Index("ix_engagement_team_user_id", "user_id"),
    )

    engagement_team_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    cycle_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("review_cycles.cycle_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    team_role: Mapped[str] = mapped_column(String(50), nullable=False)

    # Relationships
    review_cycle: Mapped["ReviewCycle"] = relationship(  # noqa: F821
        back_populates="engagement_team"
    )
    user: Mapped["User"] = relationship()  # noqa: F821
