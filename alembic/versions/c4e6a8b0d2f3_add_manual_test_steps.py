"""add manual test steps

Revision ID: c4e6a8b0d2f3
Revises: 662cfaa36a76
Create Date: 2026-09-15

Auditor-defined test steps per control (cycle-scoped or kept on the control),
their recorded results per attached control, and the evidence link.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c4e6a8b0d2f3'
down_revision: Union[str, None] = '662cfaa36a76'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'manual_test_steps',
        sa.Column('step_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('control_id', sa.BigInteger(), nullable=False),
        sa.Column('config_control_id', sa.BigInteger(), nullable=True),
        sa.Column('serial', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('test_type', sa.String(length=50), nullable=False),
        sa.Column('evidence_name', sa.String(length=255), nullable=False),
        sa.Column('evidence_description', sa.Text(), nullable=True),
        sa.Column('parameters', sa.JSON(), nullable=False),
        sa.Column('created_by', sa.BigInteger(), nullable=True),
        sa.Column('created_time', sa.BigInteger(), nullable=False),
        sa.Column('updated_time', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ['control_id'], ['control_repository.control_id'],
            name='manual_test_steps_control_id_fkey', ondelete='CASCADE', onupdate='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['config_control_id'], ['config_controls.config_control_id'],
            name='manual_test_steps_config_control_id_fkey', ondelete='CASCADE', onupdate='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['created_by'], ['users.user_id'],
            name='manual_test_steps_created_by_fkey', ondelete='SET NULL', onupdate='CASCADE',
        ),
        sa.PrimaryKeyConstraint('step_id', name='manual_test_steps_pkey'),
    )
    op.create_index('ix_manual_test_steps_control_id', 'manual_test_steps', ['control_id'])
    op.create_index(
        'ix_manual_test_steps_config_control_id', 'manual_test_steps', ['config_control_id']
    )

    op.create_table(
        'manual_test_step_results',
        sa.Column('result_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('step_id', sa.BigInteger(), nullable=False),
        sa.Column('config_control_id', sa.BigInteger(), nullable=False),
        sa.Column('verdict', sa.String(length=20), nullable=False),
        sa.Column('remark', sa.Text(), nullable=True),
        sa.Column('evidence_token', sa.String(length=1000), nullable=False),
        sa.Column('recorded_by', sa.BigInteger(), nullable=True),
        sa.Column('created_time', sa.BigInteger(), nullable=False),
        sa.Column('updated_time', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ['step_id'], ['manual_test_steps.step_id'],
            name='manual_test_step_results_step_id_fkey', ondelete='CASCADE', onupdate='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['config_control_id'], ['config_controls.config_control_id'],
            name='manual_test_step_results_config_control_id_fkey',
            ondelete='CASCADE', onupdate='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['recorded_by'], ['users.user_id'],
            name='manual_test_step_results_recorded_by_fkey', ondelete='SET NULL', onupdate='CASCADE',
        ),
        sa.PrimaryKeyConstraint('result_id', name='manual_test_step_results_pkey'),
        sa.UniqueConstraint(
            'step_id', 'config_control_id', name='uq_manual_test_step_results_step_cc'
        ),
    )
    op.create_index(
        'ix_manual_test_step_results_config_control_id',
        'manual_test_step_results',
        ['config_control_id'],
    )

    op.add_column('evidence_files', sa.Column('manual_step_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        'evidence_files_manual_step_id_fkey', 'evidence_files', 'manual_test_steps',
        ['manual_step_id'], ['step_id'], ondelete='SET NULL', onupdate='CASCADE',
    )
    op.create_index('ix_evidence_files_manual_step_id', 'evidence_files', ['manual_step_id'])


def downgrade() -> None:
    op.drop_index('ix_evidence_files_manual_step_id', table_name='evidence_files')
    op.drop_constraint('evidence_files_manual_step_id_fkey', 'evidence_files', type_='foreignkey')
    op.drop_column('evidence_files', 'manual_step_id')
    op.drop_index(
        'ix_manual_test_step_results_config_control_id', table_name='manual_test_step_results'
    )
    op.drop_table('manual_test_step_results')
    op.drop_index('ix_manual_test_steps_config_control_id', table_name='manual_test_steps')
    op.drop_index('ix_manual_test_steps_control_id', table_name='manual_test_steps')
    op.drop_table('manual_test_steps')
