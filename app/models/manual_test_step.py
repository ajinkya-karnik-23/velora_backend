"""Manual test steps — auditor-defined procedures added to a control's testing.

A step belongs either to one review cycle's attached control (the default: a
temporary customisation of that cycle's testing) or to the control itself, in
which case every cycle testing that control picks it up. `config_control_id`
tells the two apart: set for a cycle step, null for a step kept on the control.

A step has no stored verdict in the testing-output JSON, so its outcome is
recorded by the auditor and kept per attached control in
`manual_test_step_results` — a control-level step is tested afresh in each
cycle.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BigIntTimestampMixin


class ManualTestStep(BigIntTimestampMixin, Base):
    __tablename__ = "manual_test_steps"
    __table_args__ = (
        Index("ix_manual_test_steps_control_id", "control_id"),
        Index("ix_manual_test_steps_config_control_id", "config_control_id"),
    )

    step_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    control_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("control_repository.control_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    # Null when the step is kept on the control for every cycle.
    config_control_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("config_controls.config_control_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=True,
    )
    serial: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    test_type: Mapped[str] = mapped_column(String(50), nullable=False)
    evidence_name: Mapped[str] = mapped_column(String(255), nullable=False)
    evidence_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # [{"name", "data_type", "expected": {...}}] — the expected configuration's
    # shape depends on the data type, so it is stored as given.
    parameters: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="SET NULL", onupdate="CASCADE"),
        nullable=True,
    )

    control: Mapped[ControlRepository] = relationship()  # noqa: F821
    config_control: Mapped[ConfigControl | None] = relationship()  # noqa: F821
    creator: Mapped[User | None] = relationship(foreign_keys=[created_by])  # noqa: F821
    results: Mapped[list[ManualTestStepResult]] = relationship(
        back_populates="step", cascade="all, delete-orphan", passive_deletes=True
    )


class ManualTestStepResult(BigIntTimestampMixin, Base):
    __tablename__ = "manual_test_step_results"
    __table_args__ = (
        UniqueConstraint(
            "step_id", "config_control_id", name="uq_manual_test_step_results_step_cc"
        ),
        Index("ix_manual_test_step_results_config_control_id", "config_control_id"),
    )

    result_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    step_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("manual_test_steps.step_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    config_control_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("config_controls.config_control_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    # PASS | FAIL | NOT_VALIDATED
    verdict: Mapped[str] = mapped_column(String(20), nullable=False)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Fingerprint of the step's evidence when the result was recorded. If the
    # evidence changes afterwards, the result no longer describes what is
    # attached and readers treat it as void — the same rule samples follow.
    evidence_token: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    recorded_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="SET NULL", onupdate="CASCADE"),
        nullable=True,
    )

    step: Mapped[ManualTestStep] = relationship(back_populates="results")
    recorder: Mapped[User | None] = relationship(foreign_keys=[recorded_by])  # noqa: F821
