"""Declarative base and shared model mixins."""

import time

from sqlalchemy import BigInteger, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
# from app.models.control_test_result import ControlTestResult


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""


class BigIntTimestampMixin:
    """Mixin that adds created_time and updated_time as BIGINT Unix epoch (seconds)."""

    created_time: Mapped[int] = mapped_column(
        BigInteger,
        default=lambda: int(time.time()),
        nullable=False,
    )
    updated_time: Mapped[int] = mapped_column(
        BigInteger,
        default=lambda: int(time.time()),
        onupdate=lambda: int(time.time()),
        nullable=False,
    )


@event.listens_for(BigIntTimestampMixin, "before_update", propagate=True)
def _set_updated_time(mapper, connection, target: BigIntTimestampMixin) -> None:  # noqa: ARG001
    """Ensure updated_time is refreshed on every flush, even for partial updates."""
    target.updated_time = int(time.time())
