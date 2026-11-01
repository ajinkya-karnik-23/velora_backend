"""when testing of an attached control's current round was started, and by whom

Revision ID: d8f0a2c4e6b8
Revises: c6e8a0b2d4f6
Create Date: 2026-10-23

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "d8f0a2c4e6b8"
down_revision = "c6e8a0b2d4f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("config_controls", sa.Column("testing_started_time", sa.BigInteger(), nullable=True))
    op.add_column(
        "config_controls",
        sa.Column(
            "testing_started_by",
            sa.BigInteger(),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "config_controls", sa.Column("testing_started_by_name", sa.String(255), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("config_controls", "testing_started_by_name")
    op.drop_column("config_controls", "testing_started_by")
    op.drop_column("config_controls", "testing_started_time")
