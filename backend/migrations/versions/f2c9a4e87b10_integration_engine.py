"""integration engine state and webhook replay protection"""
from alembic import op
import sqlalchemy as sa

revision='f2c9a4e87b10'
down_revision='e1b8f7d30a12'
branch_labels=None
depends_on=None

def upgrade():
    with op.batch_alter_table('integrations') as b:
        b.add_column(sa.Column('encrypted_config',sa.Text(),nullable=False,server_default=''))
        b.add_column(sa.Column('account_id',sa.String(200),nullable=False,server_default=''))
        b.add_column(sa.Column('account_name',sa.String(200),nullable=False,server_default=''))
        b.add_column(sa.Column('sync_cursor',sa.JSON(),nullable=False,server_default='{}'))
        b.add_column(sa.Column('imported_counts',sa.JSON(),nullable=False,server_default='{}'))
        b.add_column(sa.Column('last_attempt',sa.DateTime(),nullable=True))
        b.add_column(sa.Column('next_sync',sa.DateTime(),nullable=True))
    with op.batch_alter_table('sync_logs') as b:
        b.add_column(sa.Column('counts',sa.JSON(),nullable=False,server_default='{}'))
        b.add_column(sa.Column('trigger',sa.String(30),nullable=False,server_default='manual'))
        b.add_column(sa.Column('finished_at',sa.DateTime(),nullable=True))
    with op.batch_alter_table('external_records') as b:
        b.add_column(sa.Column('source_updated_at',sa.DateTime(),nullable=True))
        b.add_column(sa.Column('checksum',sa.String(64),nullable=False,server_default=''))
        b.add_column(sa.Column('deleted',sa.Boolean(),nullable=False,server_default=sa.false()))
    op.create_table('webhook_deliveries',
        sa.Column('company_id',sa.Integer(),nullable=False),sa.Column('integration_id',sa.Integer(),nullable=False),
        sa.Column('provider',sa.String(40),nullable=False),sa.Column('delivery_id',sa.String(200),nullable=False),
        sa.Column('topic',sa.String(120),nullable=False),sa.Column('status',sa.String(30),nullable=False),
        sa.Column('payload',sa.JSON(),nullable=False),sa.Column('processed_at',sa.DateTime(),nullable=True),
        sa.Column('id',sa.Integer(),primary_key=True),sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.ForeignKeyConstraint(['company_id'],['companies.id']),sa.ForeignKeyConstraint(['integration_id'],['integrations.id']),
        sa.UniqueConstraint('provider','delivery_id'))
    op.create_index('ix_webhook_deliveries_company_id','webhook_deliveries',['company_id'])

def downgrade():
    op.drop_index('ix_webhook_deliveries_company_id',table_name='webhook_deliveries');op.drop_table('webhook_deliveries')
    with op.batch_alter_table('external_records') as b:
        b.drop_column('deleted');b.drop_column('checksum');b.drop_column('source_updated_at')
    with op.batch_alter_table('sync_logs') as b:
        b.drop_column('finished_at');b.drop_column('trigger');b.drop_column('counts')
    with op.batch_alter_table('integrations') as b:
        for c in ['next_sync','last_attempt','imported_counts','sync_cursor','account_name','account_id','encrypted_config']:b.drop_column(c)
