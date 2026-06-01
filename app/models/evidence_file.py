"""EvidenceFile model — maps to the ``evidence_files`` table."""

from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BigIntTimestampMixin


class EvidenceFile(BigIntTimestampMixin, Base):
    __tablename__ = "evidence_files"
    __table_args__ = (
        Index("ix_evidence_files_uploaded_by", "uploaded_by"),
        Index("ix_evidence_files_cycle_id", "cycle_id"),
        Index("ix_evidence_files_control_id", "control_id"),
        Index("ix_evidence_files_test_id", "test_id"),
        Index("ix_evidence_files_status", "status"),
        CheckConstraint(
            "cycle_id IS NOT NULL OR control_id IS NOT NULL OR test_id IS NOT NULL",
            name="ck_evidence_files_linkage",
        ),
    )

    evidence_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    upload_date: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uploaded_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    cycle_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("review_cycles.cycle_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=True,
    )
    control_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("control_repository.control_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=True,
    )
    test_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "control_tests_and_evidences.test_id", ondelete="SET NULL", onupdate="CASCADE"
        ),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Pending")
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Relationships
    uploader: Mapped["User"] = relationship(foreign_keys=[uploaded_by])  # noqa: F821
    review_cycle: Mapped["ReviewCycle | None"] = relationship(  # noqa: F821
        foreign_keys=[cycle_id]
    )
    control: Mapped["ControlRepository | None"] = relationship(  # noqa: F821
        foreign_keys=[control_id]
    )
    test: Mapped["ControlTest | None"] = relationship(foreign_keys=[test_id])  # noqa: F821
