"""user profiles"""
from alembic import op
import sqlalchemy as sa

revision='64d31dc18cba'
down_revision='2fc0a687317d'
branch_labels=None
depends_on=None

def upgrade():
    columns={c['name'] for c in sa.inspect(op.get_bind()).get_columns('users')}
    additions=[('phone',sa.String(40),''),('job_title',sa.String(120),''),('department',sa.String(120),''),('timezone',sa.String(80),'Asia/Kolkata'),('language',sa.String(20),'English'),('avatar',sa.Text(),'')]
    with op.batch_alter_table('users') as batch:
        for name,kind,default in additions:
            if name not in columns: batch.add_column(sa.Column(name,kind,nullable=False,server_default=default))

def downgrade():
    with op.batch_alter_table('users') as batch:
        for name in ['avatar','language','timezone','department','job_title','phone']: batch.drop_column(name)
