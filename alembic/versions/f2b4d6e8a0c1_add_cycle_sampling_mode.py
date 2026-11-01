"""add cycle sampling mode, cycle lock and per-control sample selection

Revision ID: f2b4d6e8a0c1
Revises: e7a9c1d3b5f4
Create Date: 2026-10-21

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "f2b4d6e8a0c1"
down_revision = "e7a9c1d3b5f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "review_cycles",
        sa.Column(
            "sampling_mode",
            sa.String(30),
            nullable=False,
            server_default="full_population",
        ),
    )
    op.add_column(
        "review_cycles",
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("config_controls", sa.Column("selected_samples", sa.JSON(), nullable=True))
    op.add_column("config_controls", sa.Column("not_tested_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("config_controls", "not_tested_reason")
    op.drop_column("config_controls", "selected_samples")
    op.drop_column("review_cycles", "is_locked")
    op.drop_column("review_cycles", "sampling_mode")
