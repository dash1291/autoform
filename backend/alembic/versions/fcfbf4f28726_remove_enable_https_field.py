"""remove enable_https field

Revision ID: fcfbf4f28726
Revises: daba9dcdbfeb
Create Date: 2025-07-25 18:33:22.212263

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fcfbf4f28726'
down_revision: Union[str, None] = 'daba9dcdbfeb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove enable_https column as HTTPS is now enabled by default
    op.drop_column('environments', 'enable_https')


def downgrade() -> None:
    # Add back enable_https column
    op.add_column('environments', sa.Column('enable_https', sa.Boolean(), nullable=True, server_default='false'))
