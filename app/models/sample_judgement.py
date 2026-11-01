"""SampleJudgement model — the tester's judgement on a tool-generated result.

The testing output holds the tool's verdict for each sample; it is never
modified. A tester who reviews that verdict records their own judgement here:
accepting it as it stands, or changing the result, and — for a failure — the
root-cause category. One row per sample of an attached control.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BigIntTimestampMixin

ROOT_CAUSE_CATEGORIES = {
    "not_executed_as_designed": "Control not executed as designed",
    "performed_with_delays": "Control performed with delays",
    "ipe_related": "IPE-related issues",
    "lack_of_control_activity": "Lack of control activity",
    "lack_of_control_evidence": "Lack of control evidence",
}


class SampleJudgement(BigIntTimestampMixin, Base):
    __tablename__ = "sample_judgements"
    __table_args__ = (
        UniqueConstraint(
            "config_control_id", "sample_no", name="uq_sample_judgements_control_sample"
        ),
    )

    judgement_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    config_control_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("config_controls.config_control_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    sample_no: Mapped[int] = mapped_column(Integer, nullable=False)
    # The tool's verdict at the time of the judgement, kept for the record.
    tool_result: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # The tester's result: PASS | FAIL | NOT_VALIDATED.
    result: Mapped[str] = mapped_column(String(50), nullable=False)
    # "accepted" (tool result confirmed) | "modified" (tester changed it).
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    conclusion: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_cause_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    root_cause_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    judged_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="SET NULL", onupdate="CASCADE"),
        nullable=True,
    )

    judge: Mapped["User | None"] = relationship(foreign_keys=[judged_by])  # noqa: F821
