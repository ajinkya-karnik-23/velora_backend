"""ControlFramework model — maps to the ``control_frameworks`` table."""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BigIntTimestampMixin


class ControlFramework(BigIntTimestampMixin, Base):
    __tablename__ = "control_frameworks"
    __table_args__ = (
        UniqueConstraint("control_id", "framework_name", name="uq_control_frameworks_ctrl_fw"),
        Index("ix_control_frameworks_framework_name", "framework_name"),
    )

    control_framework_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    control_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("control_repository.control_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    framework_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Relationships
    control: Mapped[ControlRepository] = relationship(  # noqa: F821
        back_populates="frameworks"
    )
