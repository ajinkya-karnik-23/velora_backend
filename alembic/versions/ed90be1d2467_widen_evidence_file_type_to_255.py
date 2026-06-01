"""widen_evidence_file_type_to_255

Revision ID: ed90be1d2467
Revises: b2d4f6a8c0e1
Create Date: 2026-05-27 10:56:13.455236

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'ed90be1d2467'
down_revision: Union[str, None] = 'b2d4f6a8c0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'evidence_files',
        'file_type',
        existing_type=sa.String(50),
        type_=sa.String(255),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'evidence_files',
        'file_type',
        existing_type=sa.String(255),
        type_=sa.String(50),
        existing_nullable=True,
    )
