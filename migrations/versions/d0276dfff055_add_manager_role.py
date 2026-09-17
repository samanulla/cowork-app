"""add manager role

Revision ID: d0276dfff055
Revises: aa65a2f67dd7
Create Date: 2026-09-16 18:39:06.385848

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd0276dfff055'
down_revision = 'aa65a2f67dd7'
branch_labels = None
depends_on = None


def upgrade():
    # Postgres requires ALTER TYPE ... ADD VALUE to run outside a transaction.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'MANAGER'")


def downgrade():
    # Removing enum values in Postgres requires recreating the type. No-op here.
    pass
