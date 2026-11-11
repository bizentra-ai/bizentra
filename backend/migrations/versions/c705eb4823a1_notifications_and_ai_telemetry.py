"""notifications and ai telemetry"""
from alembic import op
import sqlalchemy as sa

revision='c705eb4823a1'
down_revision='64d31dc18cba'
branch_labels=None
depends_on=None

def upgrade():
    existing=set(sa.inspect(op.get_bind()).get_table_names())
    if 'notifications' not in existing:
        op.create_table('notifications',sa.Column('company_id',sa.Integer(),nullable=False),sa.Column('user_id',sa.Integer(),nullable=False),sa.Column('source_key',sa.String(160),nullable=False),sa.Column('category',sa.String(40),nullable=False),sa.Column('title',sa.String(200),nullable=False),sa.Column('detail',sa.Text(),nullable=False,server_default=''),sa.Column('entity',sa.String(40),nullable=False,server_default=''),sa.Column('entity_id',sa.Integer(),nullable=True),sa.Column('route',sa.String(200),nullable=False,server_default=''),sa.Column('read_at',sa.DateTime(),nullable=True),sa.Column('resolved_at',sa.DateTime(),nullable=True),sa.Column('id',sa.Integer(),primary_key=True),sa.Column('created_at',sa.DateTime(),nullable=False),sa.ForeignKeyConstraint(['company_id'],['companies.id']),sa.ForeignKeyConstraint(['user_id'],['users.id']),sa.UniqueConstraint('company_id','user_id','source_key'))
        op.create_index('ix_notifications_company_id','notifications',['company_id']);op.create_index('ix_notifications_user_id','notifications',['user_id'])
    if 'notification_preferences' not in existing:
        op.create_table('notification_preferences',sa.Column('company_id',sa.Integer(),nullable=False),sa.Column('user_id',sa.Integer(),nullable=False),sa.Column('categories',sa.JSON(),nullable=False),sa.Column('email_enabled',sa.Boolean(),nullable=False,server_default=sa.false()),sa.Column('id',sa.Integer(),primary_key=True),sa.Column('created_at',sa.DateTime(),nullable=False),sa.ForeignKeyConstraint(['company_id'],['companies.id']),sa.ForeignKeyConstraint(['user_id'],['users.id']),sa.UniqueConstraint('company_id','user_id'))
        op.create_index('ix_notification_preferences_company_id','notification_preferences',['company_id']);op.create_index('ix_notification_preferences_user_id','notification_preferences',['user_id'])
    columns={c['name'] for c in sa.inspect(op.get_bind()).get_columns('ai_runs')}
    with op.batch_alter_table('ai_runs') as batch:
        for name in ['duration_ms','input_tokens','output_tokens']:
            if name not in columns:batch.add_column(sa.Column(name,sa.Integer(),nullable=False,server_default='0'))

def downgrade():
    with op.batch_alter_table('ai_runs') as batch:
        for name in ['output_tokens','input_tokens','duration_ms']:batch.drop_column(name)
    op.drop_table('notification_preferences');op.drop_table('notifications')
