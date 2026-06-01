"""TestLog model — maps to the ``test_logs`` table."""

from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BigIntTimestampMixin


class TestLog(BigIntTimestampMixin, Base):
    __tablename__ = "test_logs"
    __table_args__ = (
        Index("ix_test_logs_test_id", "test_id"),
        Index("ix_test_logs_control_id", "control_id"),
        Index("ix_test_logs_cycle_id", "cycle_id"),
        Index("ix_test_logs_changed_by", "changed_by"),
        CheckConstraint(
            "test_id IS NOT NULL OR control_id IS NOT NULL OR cycle_id IS NOT NULL",
            name="ck_test_logs_linkage",
        ),
    )

    log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    test_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "control_tests_and_evidences.test_id", ondelete="SET NULL", onupdate="CASCADE"
        ),
        nullable=True,
    )
    control_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("control_repository.control_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=True,
    )
    cycle_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("review_cycles.cycle_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=True,
    )
    log_date: Mapped[int] = mapped_column(BigInteger, nullable=False)
    changed_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    execution_time_seconds: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    report_link: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    changer: Mapped["User"] = relationship(foreign_keys=[changed_by])  # noqa: F821
    test: Mapped["ControlTest | None"] = relationship(foreign_keys=[test_id])  # noqa: F821
    control: Mapped["ControlRepository | None"] = relationship(  # noqa: F821
        foreign_keys=[control_id]
    )
    review_cycle: Mapped["ReviewCycle | None"] = relationship(  # noqa: F821
        foreign_keys=[cycle_id]
    )
