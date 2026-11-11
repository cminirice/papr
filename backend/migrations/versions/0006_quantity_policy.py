"""Explicit quantity policies and catalog operation audit targets."""
from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = depends_on = None
OLD = "target_type IN ('knowledge_revision','objective_revision','template_version','question_template')"
NEW = "target_type IN ('knowledge_revision','objective_revision','template_version','question_template','content_catalog','catalog_node','knowledge_point')"


def upgrade():
    op.create_table('knowledge_type_policy',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.Text(), nullable=False),
        sa.Column('knowledge_point_id', sa.Text(), sa.ForeignKey('knowledge_point.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('difficulty', sa.Text(), nullable=False),
        sa.Column('question_type', sa.Text(), nullable=False),
        sa.Column('count_options', sa.Text(), nullable=False),
        sa.Column('default_count', sa.Integer(), nullable=True),
        sa.Column('lock_version', sa.Integer(), nullable=False),
        sa.Column('updated_by', sa.Text(), sa.ForeignKey('admin_user.id', ondelete='RESTRICT'), nullable=False),
        sa.UniqueConstraint('knowledge_point_id', 'difficulty', 'question_type', name='uq_knowledge_type_policy'),
        sa.CheckConstraint('length(id) = 36', name='ck_knowledge_type_policy_uuid'),
        sa.CheckConstraint("length(created_at) = 32 AND substr(created_at, 27) = '+08:00'", name='ck_knowledge_type_policy_created_at'),
        sa.CheckConstraint("length(updated_at) = 32 AND substr(updated_at, 27) = '+08:00'", name='ck_knowledge_type_policy_updated_at'),
        sa.CheckConstraint("difficulty IN ('basic','standard','challenge')", name='ck_policy_difficulty'),
        sa.CheckConstraint("question_type IN ('choice','fill','answer')", name='ck_policy_type'),
        sa.CheckConstraint("json_valid(count_options) AND json_type(count_options) = 'array'", name='ck_policy_options'),
        sa.CheckConstraint('lock_version >= 1 AND (default_count IS NULL OR default_count IN (3,6,8,10,12))', name='ck_policy_lock_default'),
    )
    with op.batch_alter_table('admin_operation_log') as batch:
        batch.drop_constraint('ck_operation_target', type_='check')
        batch.create_check_constraint('ck_operation_target', NEW)


def downgrade():
    # Do not erase or mislabel append-only audit history to satisfy the older constraint.
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM admin_operation_log WHERE target_type IN ('content_catalog','catalog_node','knowledge_point')")):
        raise RuntimeError('0006已有目录/题量审计记录，禁止自动降级删除历史；请先制定备份与回退方案')
    op.drop_table('knowledge_type_policy')
    with op.batch_alter_table('admin_operation_log') as batch:
        batch.drop_constraint('ck_operation_target', type_='check')
        batch.create_check_constraint('ck_operation_target', OLD)
