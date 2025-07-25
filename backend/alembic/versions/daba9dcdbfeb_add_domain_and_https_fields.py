"""add domain and https fields

Revision ID: daba9dcdbfeb
Revises: d0024d5055af
Create Date: 2025-07-25 18:33:02.608665

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'daba9dcdbfeb'
down_revision: Union[str, None] = 'd0024d5055af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add domain and HTTPS fields to environments table
    op.add_column('environments', sa.Column('certificate_arn', sa.String(length=255), nullable=True))
    op.add_column('environments', sa.Column('enable_https', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('environments', sa.Column('auto_provision_certificate', sa.Boolean(), nullable=True, server_default='true'))
    op.add_column('environments', sa.Column('use_route53_validation', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('environments', sa.Column('custom_domain', sa.String(length=255), nullable=True))
    
    # Update existing environments to have sensible defaults
    op.execute("UPDATE environments SET enable_https = FALSE WHERE enable_https IS NULL")
    op.execute("UPDATE environments SET auto_provision_certificate = TRUE WHERE auto_provision_certificate IS NULL")
    op.execute("UPDATE environments SET use_route53_validation = FALSE WHERE use_route53_validation IS NULL")
    
    # Migrate existing custom domains: if domain doesn't contain 'elb.amazonaws.com', 
    # it's a custom domain and should be moved to custom_domain field
    op.execute("""
        UPDATE environments 
        SET custom_domain = domain,
            domain = NULL
        WHERE domain IS NOT NULL 
        AND domain NOT LIKE '%.elb.amazonaws.com'
    """)


def downgrade() -> None:
    # Move custom domains back to domain field
    op.execute("""
        UPDATE environments 
        SET domain = custom_domain
        WHERE custom_domain IS NOT NULL
    """)
    
    # Remove the new columns
    op.drop_column('environments', 'custom_domain')
    op.drop_column('environments', 'use_route53_validation')
    op.drop_column('environments', 'auto_provision_certificate')
    op.drop_column('environments', 'enable_https')
    op.drop_column('environments', 'certificate_arn')
