"""add control review workflow

Revision ID: e7a9c1d3b5f4
Revises: d6f8b0c2e4a5
Create Date: 2026-10-01

Review hand-over and verdict per attached control, with an append-only trail
of every transition.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e7a9c1d3b5f4'
down_revision: Union[str, None] = 'd6f8b0c2e4a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'control_review_status',
        sa.Column('review_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('config_control_id', sa.BigInteger(), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('submitted_by', sa.BigInteger(), nullable=True),
        sa.Column('submitted_time', sa.BigInteger(), nullable=True),
        sa.Column('reviewed_by', sa.BigInteger(), nullable=True),
        sa.Column('reviewed_time', sa.BigInteger(), nullable=True),
        sa.Column('created_time', sa.BigInteger(), nullable=False),
        sa.Column('updated_time', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ['config_control_id'], ['config_controls.config_control_id'],
            name='control_review_status_config_control_id_fkey',
            ondelete='CASCADE', onupdate='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['submitted_by'], ['users.user_id'],
            name='control_review_status_submitted_by_fkey',
            ondelete='SET NULL', onupdate='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['reviewed_by'], ['users.user_id'],
            name='control_review_status_reviewed_by_fkey',
            ondelete='SET NULL', onupdate='CASCADE',
        ),
        sa.PrimaryKeyConstraint('review_id', name='control_review_status_pkey'),
        sa.UniqueConstraint('config_control_id', name='uq_control_review_status_cc'),
    )

    op.create_table(
        'control_review_events',
        sa.Column('event_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('config_control_id', sa.BigInteger(), nullable=False),
        sa.Column('from_status', sa.String(length=30), nullable=True),
        sa.Column('to_status', sa.String(length=30), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('actor_id', sa.BigInteger(), nullable=True),
        sa.Column('actor_persona', sa.String(length=20), nullable=False),
        sa.Column('event_time', sa.BigInteger(), nullable=False),
        sa.Column('created_time', sa.BigInteger(), nullable=False),
        sa.Column('updated_time', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ['config_control_id'], ['config_controls.config_control_id'],
            name='control_review_events_config_control_id_fkey',
            ondelete='CASCADE', onupdate='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['actor_id'], ['users.user_id'],
            name='control_review_events_actor_id_fkey',
            ondelete='SET NULL', onupdate='CASCADE',
        ),
        sa.PrimaryKeyConstraint('event_id', name='control_review_events_pkey'),
    )
    op.create_index(
        'ix_control_review_events_config_control_id',
        'control_review_events',
        ['config_control_id'],
    )


def downgrade() -> None:
    op.drop_index(
        'ix_control_review_events_config_control_id', table_name='control_review_events'
    )
    op.drop_table('control_review_events')
    op.drop_table('control_review_status')
