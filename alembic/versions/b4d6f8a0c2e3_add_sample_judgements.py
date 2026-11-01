"""tester judgements on tool-generated sample results

Revision ID: b4d6f8a0c2e3
Revises: a3c5e7f9b1d2
Create Date: 2026-10-21

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "b4d6f8a0c2e3"
down_revision = "a3c5e7f9b1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sample_judgements",
        sa.Column("judgement_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "config_control_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "config_controls.config_control_id", ondelete="CASCADE", onupdate="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column("sample_no", sa.Integer(), nullable=False),
        sa.Column("tool_result", sa.String(50), nullable=True),
        sa.Column("result", sa.String(50), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("conclusion", sa.Text(), nullable=True),
        sa.Column("root_cause_category", sa.String(50), nullable=True),
        sa.Column("root_cause_note", sa.Text(), nullable=True),
        sa.Column(
            "judged_by",
            sa.BigInteger(),
            sa.ForeignKey("users.user_id", ondelete="SET NULL", onupdate="CASCADE"),
            nullable=True,
        ),
        sa.Column("created_time", sa.BigInteger(), nullable=False),
        sa.Column("updated_time", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint(
            "config_control_id", "sample_no", name="uq_sample_judgements_control_sample"
        ),
    )


def downgrade() -> None:
    op.drop_table("sample_judgements")
