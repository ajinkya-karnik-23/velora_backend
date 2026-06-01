"""template_source_test_id

Revision ID: b2d4f6a8c0e1
Revises: a1c3e5f7b9d2
Create Date: 2026-05-25

Add source_test_id to control_test_templates so _seed_tests can reuse
the canonical IDs from the detailed JSON files instead of auto-incrementing.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b2d4f6a8c0e1'
down_revision: Union[str, None] = 'a1c3e5f7b9d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'control_test_templates',
        sa.Column('source_test_id', sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('control_test_templates', 'source_test_id')
