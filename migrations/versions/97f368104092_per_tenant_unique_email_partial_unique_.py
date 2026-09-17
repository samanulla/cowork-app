"""per-tenant unique email + partial unique for platform owner

Revision ID: 97f368104092
Revises: 8711d3dcd846
Create Date: 2026-09-16 20:11:06.224566

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '97f368104092'
down_revision = '8711d3dcd846'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index('ix_users_email')
        batch_op.create_index(batch_op.f('ix_users_email'), ['email'], unique=False)
        batch_op.create_index(
            'uq_users_platform_email', ['email'], unique=True,
            postgresql_where=sa.text('tenant_id IS NULL'),
            sqlite_where=sa.text('tenant_id IS NULL'),
        )
        batch_op.create_unique_constraint('uq_users_tenant_email', ['tenant_id', 'email'])


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('uq_users_tenant_email', type_='unique')
        batch_op.drop_index(
            'uq_users_platform_email',
            postgresql_where=sa.text('tenant_id IS NULL'),
            sqlite_where=sa.text('tenant_id IS NULL'),
        )
        batch_op.drop_index(batch_op.f('ix_users_email'))
        batch_op.create_index('ix_users_email', ['email'], unique=True)
