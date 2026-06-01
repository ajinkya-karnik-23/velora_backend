"""cascade_delete_config_control_chain

Revision ID: 2f186183f4cc
Revises: 9b4037f71058
Create Date: 2026-05-25

Fix FK constraints so that deleting a config_control cascades:
  config_controls -> control_tests_and_evidences (CASCADE)
  control_tests_and_evidences -> evidence_files    (SET NULL)
  control_tests_and_evidences -> test_logs         (SET NULL)
"""

from typing import Sequence, Union

from alembic import op

revision: str = '2f186183f4cc'
down_revision: Union[str, None] = '9b4037f71058'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # control_tests_and_evidences.config_control_id: RESTRICT -> CASCADE
    op.drop_constraint(
        'control_tests_and_evidences_config_control_id_fkey',
        'control_tests_and_evidences',
        type_='foreignkey',
    )
    op.create_foreign_key(
        'control_tests_and_evidences_config_control_id_fkey',
        'control_tests_and_evidences',
        'config_controls',
        ['config_control_id'],
        ['config_control_id'],
        ondelete='CASCADE',
        onupdate='CASCADE',
    )

    # evidence_files.test_id: RESTRICT -> SET NULL
    op.drop_constraint(
        'evidence_files_test_id_fkey',
        'evidence_files',
        type_='foreignkey',
    )
    op.create_foreign_key(
        'evidence_files_test_id_fkey',
        'evidence_files',
        'control_tests_and_evidences',
        ['test_id'],
        ['test_id'],
        ondelete='SET NULL',
        onupdate='CASCADE',
    )

    # test_logs.test_id: RESTRICT -> SET NULL
    op.drop_constraint(
        'test_logs_test_id_fkey',
        'test_logs',
        type_='foreignkey',
    )
    op.create_foreign_key(
        'test_logs_test_id_fkey',
        'test_logs',
        'control_tests_and_evidences',
        ['test_id'],
        ['test_id'],
        ondelete='SET NULL',
        onupdate='CASCADE',
    )


def downgrade() -> None:
    op.drop_constraint('test_logs_test_id_fkey', 'test_logs', type_='foreignkey')
    op.create_foreign_key(
        'test_logs_test_id_fkey', 'test_logs', 'control_tests_and_evidences',
        ['test_id'], ['test_id'], ondelete='RESTRICT', onupdate='CASCADE',
    )

    op.drop_constraint('evidence_files_test_id_fkey', 'evidence_files', type_='foreignkey')
    op.create_foreign_key(
        'evidence_files_test_id_fkey', 'evidence_files', 'control_tests_and_evidences',
        ['test_id'], ['test_id'], ondelete='RESTRICT', onupdate='CASCADE',
    )

    op.drop_constraint(
        'control_tests_and_evidences_config_control_id_fkey',
        'control_tests_and_evidences', type_='foreignkey',
    )
    op.create_foreign_key(
        'control_tests_and_evidences_config_control_id_fkey',
        'control_tests_and_evidences', 'config_controls',
        ['config_control_id'], ['config_control_id'], ondelete='RESTRICT', onupdate='CASCADE',
    )
