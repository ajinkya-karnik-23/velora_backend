"""audit log sources on test_logs

Revision ID: d6f8b0c2e4a5
Revises: c4e6a8b0d2f3
Create Date: 2026-09-15

Records what each test log came from (a sample run or a manual step result)
and which sample or step it covers.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd6f8b0c2e4a5'
down_revision: Union[str, None] = 'c4e6a8b0d2f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('test_logs', sa.Column('source', sa.String(length=20), nullable=True))
    op.add_column('test_logs', sa.Column('sample_no', sa.Integer(), nullable=True))
    op.add_column('test_logs', sa.Column('manual_step_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        'test_logs_manual_step_id_fkey', 'test_logs', 'manual_test_steps',
        ['manual_step_id'], ['step_id'], ondelete='SET NULL', onupdate='CASCADE',
    )


def downgrade() -> None:
    op.drop_constraint('test_logs_manual_step_id_fkey', 'test_logs', type_='foreignkey')
    op.drop_column('test_logs', 'manual_step_id')
    op.drop_column('test_logs', 'sample_no')
    op.drop_column('test_logs', 'source')
