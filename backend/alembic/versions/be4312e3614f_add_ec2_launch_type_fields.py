"""add_ec2_launch_type_fields

Revision ID: be4312e3614f
Revises: d0024d5055af
Create Date: 2025-07-21 12:06:59.209724

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'be4312e3614f'
down_revision: Union[str, None] = 'd0024d5055af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add EC2 launch type fields to environments table
    op.add_column('environments', sa.Column('launch_type', sa.String(), nullable=False, server_default='EC2'))
    op.add_column('environments', sa.Column('ec2_instance_type', sa.String(), nullable=False, server_default='t3a.small'))
    op.add_column('environments', sa.Column('ec2_min_size', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('environments', sa.Column('ec2_max_size', sa.Integer(), nullable=False, server_default='3'))
    op.add_column('environments', sa.Column('ec2_desired_capacity', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('environments', sa.Column('ec2_use_spot', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('environments', sa.Column('ec2_spot_max_price', sa.String(), nullable=True))
    op.add_column('environments', sa.Column('ec2_key_name', sa.String(), nullable=True))
    op.add_column('environments', sa.Column('capacity_provider_target_capacity', sa.Integer(), nullable=False, server_default='80'))


def downgrade() -> None:
    # Remove EC2 launch type fields from environments table
    op.drop_column('environments', 'capacity_provider_target_capacity')
    op.drop_column('environments', 'ec2_key_name')
    op.drop_column('environments', 'ec2_spot_max_price')
    op.drop_column('environments', 'ec2_use_spot')
    op.drop_column('environments', 'ec2_desired_capacity')
    op.drop_column('environments', 'ec2_max_size')
    op.drop_column('environments', 'ec2_min_size')
    op.drop_column('environments', 'ec2_instance_type')
    op.drop_column('environments', 'launch_type')
