"""Controlled application settings."""
from alembic import op
import sqlalchemy as sa
revision='0011'
down_revision='0010'
branch_labels=None
depends_on=None
OLD="target_type IN ('knowledge_revision','objective_revision','template_version','question_template','content_catalog','catalog_node','knowledge_point','training_objective','content_source','paper','job')"
NEW=OLD[:-1]+",'app_setting')"


def upgrade():
    op.create_table('app_setting',
        sa.Column('key',sa.Text(),primary_key=True),sa.Column('value',sa.Text(),nullable=False),
        sa.Column('schema_version',sa.Integer(),nullable=False),sa.Column('lock_version',sa.Integer(),nullable=False),
        sa.Column('updated_by',sa.Text(),sa.ForeignKey('admin_user.id',ondelete='RESTRICT')),
        sa.Column('updated_at',sa.Text(),nullable=False),
        sa.CheckConstraint("key IN ('question_count_options','generation_limits','retention_policy')",name='ck_setting_key'),
        sa.CheckConstraint('json_valid(value) AND schema_version = 1 AND lock_version >= 1',name='ck_setting_value'),
        sa.CheckConstraint("length(updated_at) = 32 AND substr(updated_at, 27) = '+08:00'",name='ck_setting_time'))
    with op.batch_alter_table('admin_operation_log') as batch:
        batch.drop_constraint('ck_operation_target',type_='check');batch.create_check_constraint('ck_operation_target',NEW)


def downgrade():
    conn=op.get_bind()
    if conn.execute(sa.text('SELECT count(*) FROM app_setting')).scalar_one() or conn.execute(sa.text("SELECT count(*) FROM admin_operation_log WHERE target_type='app_setting'")).scalar_one():
        raise RuntimeError('已有配置或操作记录，不能自动降级删除')
    op.drop_table('app_setting')
    with op.batch_alter_table('admin_operation_log') as batch:
        batch.drop_constraint('ck_operation_target',type_='check');batch.create_check_constraint('ck_operation_target',OLD)
