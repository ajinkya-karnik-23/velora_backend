"""session table creation

Revision ID: 9b4037f71058
Revises: 0f5f739b07b7
Create Date: 2026-05-21 14:57:56.269934

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b4037f71058'
down_revision: Union[str, None] = '0f5f739b07b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass
    # op.create_table(
    #     # 'control_test_results',
    #     # sa.Column('id', sa.Integer(), nullable=False),
    #     # sa.Column('test_id', sa.Integer(), nullable=False),
    #     # sa.Column('control_id', sa.String(), nullable=False),
    #     # sa.Column('cycle_id', sa.Integer(), nullable=False),
    #     # sa.Column('compliance_test', sa.String(), nullable=False),
    #     # sa.Column('audit_justification', sa.Text(), nullable=True),
    #     # sa.Column('task_id', sa.String(), nullable=True),
    #     # sa.Column('execution_time_ms', sa.Integer(), nullable=True),
    #     # sa.Column('execution_status', sa.String(), nullable=True),
    #     # sa.Column('user_id', sa.String(), nullable=True),
    #     # sa.Column(
    #     #     'created_at',
    #     #     sa.DateTime(timezone=True),
    #     #     server_default=sa.text('now()'),
    #     #     nullable=False,
    #     # ),
    #     # sa.Column(
    #     #     'updated_at',
    #     #     sa.DateTime(timezone=True),
    #     #     server_default=sa.text('now()'),
    #     #     nullable=False,
    #     # ),
    #     # sa.PrimaryKeyConstraint('id'),
    # )
    # ### end Alembic commands ###


def downgrade() -> None:
    pass
    # op.drop_table('control_test_results')