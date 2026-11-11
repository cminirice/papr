"""Append-only paper notices and administrative cancellation audit targets."""
from alembic import op
import sqlalchemy as sa
revision='0010'
down_revision='0009'
branch_labels=None
depends_on=None
OLD="target_type IN ('knowledge_revision','objective_revision','template_version','question_template','content_catalog','catalog_node','knowledge_point','training_objective','content_source')"
NEW=OLD[:-1]+",'paper','job')"


def upgrade():
    op.create_table('paper_notice',
        sa.Column('request_hash',sa.Text(),nullable=False),sa.Column('id',sa.Text(),primary_key=True),sa.Column('created_at',sa.Text(),nullable=False),sa.Column('updated_at',sa.Text(),nullable=False),
        sa.Column('paper_id',sa.Text(),sa.ForeignKey('paper.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('question_id',sa.Text(),sa.ForeignKey('question.id',ondelete='RESTRICT')),
        sa.Column('severity',sa.Text(),nullable=False),sa.Column('message',sa.Text(),nullable=False),sa.Column('action',sa.Text(),nullable=False),
        sa.Column('created_by',sa.Text(),sa.ForeignKey('admin_user.id',ondelete='RESTRICT'),nullable=False),
        sa.CheckConstraint('length(request_hash) = 64',name='ck_paper_notice_request_hash'),
        sa.CheckConstraint('length(id) = 36',name='ck_paper_notice_uuid'),
        sa.CheckConstraint("length(created_at) = 32 AND substr(created_at, 27) = '+08:00'",name='ck_paper_notice_created_at'),
        sa.CheckConstraint("length(updated_at) = 32 AND substr(updated_at, 27) = '+08:00'",name='ck_paper_notice_updated_at'),
        sa.CheckConstraint("severity IN ('info','error') AND action IN ('notice','withdraw')",name='ck_paper_notice_kind'))
    op.create_index('ix_paper_notice_date','paper_notice',['paper_id','created_at'])
    with op.batch_alter_table('admin_operation_log') as batch:
        batch.drop_constraint('ck_operation_target',type_='check');batch.create_check_constraint('ck_operation_target',NEW)


def downgrade():
    conn=op.get_bind()
    if conn.execute(sa.text('SELECT count(*) FROM paper_notice')).scalar_one() or conn.execute(sa.text("SELECT count(*) FROM admin_operation_log WHERE target_type IN ('paper','job')")).scalar_one():
        raise RuntimeError('存在试卷说明或任务管理记录，不能自动删除追溯数据')
    op.drop_table('paper_notice')
    with op.batch_alter_table('admin_operation_log') as batch:
        batch.drop_constraint('ck_operation_target',type_='check');batch.create_check_constraint('ck_operation_target',OLD)
