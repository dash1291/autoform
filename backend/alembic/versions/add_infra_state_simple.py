"""add infrastructure state fields

Revision ID: add_infra_state_simple
Revises: be4312e3614f
Create Date: 2025-07-21 22:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'add_infra_state_simple'
down_revision: Union[str, None] = 'be4312e3614f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add infrastructure state columns to projects table
    op.add_column('projects', sa.Column('target_group_arn', sa.String(), nullable=True))
    op.add_column('projects', sa.Column('vpc_id', sa.String(), nullable=True))
    op.add_column('projects', sa.Column('subnet_ids', sa.String(), nullable=True))
    op.add_column('projects', sa.Column('alb_security_group_id', sa.String(), nullable=True))
    op.add_column('projects', sa.Column('ecs_security_group_id', sa.String(), nullable=True))


def downgrade() -> None:
    # Remove infrastructure state columns from projects table
    op.drop_column('projects', 'ecs_security_group_id')
    op.drop_column('projects', 'alb_security_group_id')
    op.drop_column('projects', 'subnet_ids')
    op.drop_column('projects', 'vpc_id')
    op.drop_column('projects', 'target_group_arn')