"""when the tester computed a phase run's sample count

Revision ID: f1a3c5e7b9d0
Revises: e9b1d3f5a7c8
Create Date: 2026-10-28

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "f1a3c5e7b9d0"
down_revision = "e9b1d3f5a7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "control_phase_runs", sa.Column("size_computed_time", sa.BigInteger(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("control_phase_runs", "size_computed_time")
