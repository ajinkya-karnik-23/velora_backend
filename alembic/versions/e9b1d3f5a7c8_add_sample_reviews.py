"""the reviewer's word on a tested sample, and its event trail

Revision ID: e9b1d3f5a7c8
Revises: d8f0a2c4e6b8
Create Date: 2026-10-23

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "e9b1d3f5a7c8"
down_revision = "d8f0a2c4e6b8"
branch_labels = None
depends_on = None


def _cc() -> sa.Column:
    return sa.Column(
        "config_control_id",
        sa.BigInteger(),
        sa.ForeignKey("config_controls.config_control_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )


def _user(name: str) -> sa.Column:
    return sa.Column(
        name,
        sa.BigInteger(),
        sa.ForeignKey("users.user_id", ondelete="SET NULL", onupdate="CASCADE"),
        nullable=True,
    )


def upgrade() -> None:
    op.create_table(
        "sample_reviews",
        sa.Column("review_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        _cc(),
        sa.Column("sample_no", sa.Integer(), nullable=False),
        sa.Column("result", sa.String(50), nullable=True),
        sa.Column("conclusion", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("involved", sa.JSON(), nullable=True),
        sa.Column("verdict", sa.String(30), nullable=True),
        sa.Column("verdict_time", sa.BigInteger(), nullable=True),
        _user("reviewed_by"),
        sa.Column("created_time", sa.BigInteger(), nullable=False),
        sa.Column("updated_time", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint(
            "config_control_id", "sample_no", name="uq_sample_reviews_control_sample"
        ),
    )
    op.create_table(
        "sample_review_events",
        sa.Column("event_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        _cc(),
        sa.Column("sample_no", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        _user("actor_id"),
        sa.Column("event_time", sa.BigInteger(), nullable=False),
        sa.Column("created_time", sa.BigInteger(), nullable=False),
        sa.Column("updated_time", sa.BigInteger(), nullable=False),
    )
    op.create_index(
        "ix_sample_review_events_config_control_id", "sample_review_events", ["config_control_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_sample_review_events_config_control_id", table_name="sample_review_events")
    op.drop_table("sample_review_events")
    op.drop_table("sample_reviews")
