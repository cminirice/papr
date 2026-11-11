"""Allow source and objective audit targets, preserving all existing records."""
from alembic import op
import sqlalchemy as sa

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None
OLD = "target_type IN ('knowledge_revision','objective_revision','template_version','question_template','content_catalog','catalog_node','knowledge_point')"
NEW = "target_type IN ('knowledge_revision','objective_revision','template_version','question_template','content_catalog','catalog_node','knowledge_point','training_objective','content_source')"


def upgrade():
    with op.batch_alter_table('admin_operation_log') as batch:
        batch.drop_constraint('ck_operation_target', type_='check')
        batch.create_check_constraint('ck_operation_target', NEW)


def downgrade():
    count = op.get_bind().execute(sa.text("SELECT count(*) FROM admin_operation_log WHERE target_type IN ('training_objective','content_source')")).scalar_one()
    if count:
        raise RuntimeError('存在资料来源或训练目标操作记录，不能自动降级删除审计历史')
    with op.batch_alter_table('admin_operation_log') as batch:
        batch.drop_constraint('ck_operation_target', type_='check')
        batch.create_check_constraint('ck_operation_target', OLD)
