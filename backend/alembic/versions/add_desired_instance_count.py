"""add desired instance count to environment

Revision ID: add_desired_instance_count
Revises: fcfbf4f28726
Create Date: 2025-08-09 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_desired_instance_count'
down_revision = 'fcfbf4f28726'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add desired_instance_count column to environments table
    op.add_column('environments', sa.Column('desired_instance_count', sa.Integer(), nullable=False, server_default='1'))


def downgrade() -> None:
    # Remove desired_instance_count column from environments table
    op.drop_column('environments', 'desired_instance_count')