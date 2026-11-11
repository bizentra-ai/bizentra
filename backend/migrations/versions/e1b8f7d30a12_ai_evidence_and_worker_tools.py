"""ai evidence and worker tools"""
from alembic import op
import sqlalchemy as sa
revision='e1b8f7d30a12'
down_revision='c705eb4823a1'
branch_labels=None
depends_on=None
def upgrade():
    with op.batch_alter_table('ai_messages') as b:b.add_column(sa.Column('references',sa.JSON(),nullable=False,server_default='[]'))
    with op.batch_alter_table('ai_runs') as b:b.add_column(sa.Column('mode',sa.String(20),nullable=False,server_default='ask'))
    with op.batch_alter_table('ai_actions') as b:b.add_column(sa.Column('risk',sa.String(20),nullable=False,server_default='low'))
def downgrade():
    with op.batch_alter_table('ai_actions') as b:b.drop_column('risk')
    with op.batch_alter_table('ai_runs') as b:b.drop_column('mode')
    with op.batch_alter_table('ai_messages') as b:b.drop_column('references')
