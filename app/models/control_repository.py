"""ControlRepository model — maps to the ``control_repository`` table."""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BigIntTimestampMixin


class ControlRepository(BigIntTimestampMixin, Base):
    __tablename__ = "control_repository"
    __table_args__ = (
        Index("ix_control_repository_control_number", "control_number"),
        Index("ix_control_repository_version_id", "version_id"),
        Index("ix_control_repository_domain", "domain"),
        Index("ix_control_repository_status", "status"),
        Index("ix_control_repository_control_owner", "control_owner"),
        Index("ix_control_repository_units_fccg_contact", "units_fccg_contact"),
    )

    control_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    control_number: Mapped[str] = mapped_column(String(255), nullable=False)
    version_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("versions.version_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=True,
    )
    control_name: Mapped[str] = mapped_column(String(255), nullable=False)
    reference_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    entity: Mapped[str] = mapped_column(String(255), nullable=False)
    control_desc: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Active")
    frequency: Mapped[str] = mapped_column(String(50), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(50), nullable=False)
    pwc_reliance: Mapped[str | None] = mapped_column(String(255), nullable=True)
    control_owner: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    units_fccg_contact: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )

    # Relationships
    owner: Mapped[User] = relationship(foreign_keys=[control_owner])  # noqa: F821
    fccg_contact: Mapped[User] = relationship(  # noqa: F821
        foreign_keys=[units_fccg_contact]
    )
    version: Mapped[Version | None] = relationship()  # noqa: F821
    frameworks: Mapped[list[ControlFramework]] = relationship(  # noqa: F821
        back_populates="control"
    )
