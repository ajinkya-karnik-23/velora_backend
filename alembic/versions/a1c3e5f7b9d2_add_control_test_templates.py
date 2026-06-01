"""add_control_test_templates

Revision ID: a1c3e5f7b9d2
Revises: 2f186183f4cc
Create Date: 2026-05-25

Cycle-independent canonical test definitions per control.
Used by _seed_tests so Reset+Reattach always restores full IPE/CPT rows.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a1c3e5f7b9d2'
down_revision: Union[str, None] = '2f186183f4cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'control_test_templates',
        sa.Column('template_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('control_id', sa.BigInteger(), nullable=False),
        sa.Column('tests', sa.Text(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('comments', sa.Text(), nullable=True),
        sa.Column('created_time', sa.BigInteger(), nullable=False),
        sa.Column('updated_time', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ['control_id'],
            ['control_repository.control_id'],
            name='control_test_templates_control_id_fkey',
            ondelete='CASCADE',
            onupdate='CASCADE',
        ),
        sa.PrimaryKeyConstraint('template_id', name='control_test_templates_pkey'),
    )
    op.create_index(
        'ix_control_test_templates_control_id',
        'control_test_templates',
        ['control_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_control_test_templates_control_id', table_name='control_test_templates')
    op.drop_table('control_test_templates')
