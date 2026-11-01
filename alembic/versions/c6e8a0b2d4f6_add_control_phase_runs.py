"""control phase runs and their event trail

Revision ID: c6e8a0b2d4f6
Revises: b4d6f8a0c2e3
Create Date: 2026-10-22

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "c6e8a0b2d4f6"
down_revision = "b4d6f8a0c2e3"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_time", sa.BigInteger(), nullable=False),
        sa.Column("updated_time", sa.BigInteger(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "control_phase_runs",
        sa.Column("phase_run_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "config_control_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "config_controls.config_control_id", ondelete="CASCADE", onupdate="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column("phase", sa.String(4), nullable=False),
        sa.Column(
            "remediates_run_id",
            sa.BigInteger(),
            sa.ForeignKey("control_phase_runs.phase_run_id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("matrix_value", sa.String(50), nullable=True),
        sa.Column("size_source", sa.String(20), nullable=True),
        sa.Column("override_size", sa.Integer(), nullable=True),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column(
            "override_by",
            sa.BigInteger(),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("override_time", sa.BigInteger(), nullable=True),
        sa.Column("selected_samples", sa.JSON(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("started_time", sa.BigInteger(), nullable=False),
        sa.Column("concluded_time", sa.BigInteger(), nullable=True),
        sa.Column(
            "concluded_by",
            sa.BigInteger(),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        *_timestamps(),
    )
    op.create_index(
        "ix_control_phase_runs_config_control_id", "control_phase_runs", ["config_control_id"]
    )
    op.create_table(
        "control_phase_events",
        sa.Column("event_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "config_control_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "config_controls.config_control_id", ondelete="CASCADE", onupdate="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column(
            "phase_run_id",
            sa.BigInteger(),
            sa.ForeignKey("control_phase_runs.phase_run_id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column(
            "actor_id",
            sa.BigInteger(),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_time", sa.BigInteger(), nullable=False),
        *_timestamps(),
    )
    op.create_index(
        "ix_control_phase_events_config_control_id",
        "control_phase_events",
        ["config_control_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_control_phase_events_config_control_id", table_name="control_phase_events")
    op.drop_table("control_phase_events")
    op.drop_index("ix_control_phase_runs_config_control_id", table_name="control_phase_runs")
    op.drop_table("control_phase_runs")
