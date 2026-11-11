"""content_release"""
from datetime import datetime, timedelta, timezone
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('admin_operation_log',
    sa.Column('admin_id', sa.Text(), nullable=False),
    sa.Column('action', sa.Text(), nullable=False),
    sa.Column('target_type', sa.Text(), nullable=False),
    sa.Column('target_id', sa.Text(), nullable=False),
    sa.Column('request_id', sa.Text(), nullable=False),
    sa.Column('before_summary', sa.Text(), nullable=True),
    sa.Column('after_summary', sa.Text(), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('created_at', sa.Text(), nullable=False),
    sa.Column('updated_at', sa.Text(), nullable=False),
    sa.CheckConstraint("length(created_at) = 32 AND substr(created_at, 27) = '+08:00'", name='ck_admin_operation_log_created_at'),
    sa.CheckConstraint("length(updated_at) = 32 AND substr(updated_at, 27) = '+08:00'", name='ck_admin_operation_log_updated_at'),
    sa.CheckConstraint("target_type IN ('knowledge_revision','objective_revision','template_version','question_template')", name='ck_operation_target'),
    sa.CheckConstraint('(before_summary IS NULL OR json_valid(before_summary)) AND (after_summary IS NULL OR json_valid(after_summary))', name='ck_operation_summary'),
    sa.CheckConstraint('length(id) = 36', name='ck_admin_operation_log_uuid'),
    sa.ForeignKeyConstraint(['admin_id'], ['admin_user.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('admin_operation_log', schema=None) as batch_op:
        batch_op.create_index('ix_operation_admin_date', ['admin_id', 'created_at'], unique=False)
        batch_op.create_index('ix_operation_target_date', ['target_type', 'target_id', 'created_at'], unique=False)

    op.create_table('content_review',
    sa.Column('template_version_id', sa.Text(), nullable=False),
    sa.Column('validation_run_id', sa.Text(), nullable=False),
    sa.Column('content_hash', sa.Text(), nullable=False),
    sa.Column('decision', sa.Text(), nullable=False),
    sa.Column('reviewer_id', sa.Text(), nullable=False),
    sa.Column('comment', sa.Text(), nullable=False),
    sa.Column('sample_refs', sa.Text(), nullable=False),
    sa.Column('print_checked', sa.Integer(), nullable=False),
    sa.Column('reviewed_at', sa.Text(), nullable=False),
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('created_at', sa.Text(), nullable=False),
    sa.Column('updated_at', sa.Text(), nullable=False),
    sa.CheckConstraint("decision IN ('approved','rejected')", name='ck_review_decision'),
    sa.CheckConstraint("length(created_at) = 32 AND substr(created_at, 27) = '+08:00'", name='ck_content_review_created_at'),
    sa.CheckConstraint("length(reviewed_at) = 32 AND substr(reviewed_at, 27) = '+08:00'", name='ck_content_review_reviewed_at'),
    sa.CheckConstraint("length(updated_at) = 32 AND substr(updated_at, 27) = '+08:00'", name='ck_content_review_updated_at'),
    sa.CheckConstraint("print_checked IN (0,1) AND (decision <> 'approved' OR print_checked = 1)", name='ck_review_print'),
    sa.CheckConstraint('json_valid(sample_refs)', name='ck_review_samples'),
    sa.CheckConstraint('length(content_hash) = 64 AND length(trim(comment)) > 0', name='ck_review_content'),
    sa.CheckConstraint('length(id) = 36', name='ck_content_review_uuid'),
    sa.ForeignKeyConstraint(['reviewer_id'], ['admin_user.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['template_version_id'], ['template_version.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['validation_run_id'], ['validation_run.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('content_review', schema=None) as batch_op:
        batch_op.create_index('ix_review_version_hash', ['template_version_id', 'content_hash', 'reviewed_at'], unique=False)

    op.create_table('content_release',
    sa.Column('template_id', sa.Text(), nullable=False),
    sa.Column('from_version_id', sa.Text(), nullable=True),
    sa.Column('to_version_id', sa.Text(), nullable=True),
    sa.Column('action', sa.Text(), nullable=False),
    sa.Column('operator_id', sa.Text(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('validation_run_id', sa.Text(), nullable=True),
    sa.Column('review_id', sa.Text(), nullable=True),
    sa.Column('epoch', sa.Integer(), nullable=False),
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('created_at', sa.Text(), nullable=False),
    sa.Column('updated_at', sa.Text(), nullable=False),
    sa.CheckConstraint("action IN ('publish','disable','enable','rollback')", name='ck_release_action'),
    sa.CheckConstraint("length(created_at) = 32 AND substr(created_at, 27) = '+08:00'", name='ck_content_release_created_at'),
    sa.CheckConstraint("length(updated_at) = 32 AND substr(updated_at, 27) = '+08:00'", name='ck_content_release_updated_at'),
    sa.CheckConstraint('epoch >= 1 AND length(trim(reason)) > 0', name='ck_release_reason'),
    sa.CheckConstraint('length(id) = 36', name='ck_content_release_uuid'),
    sa.ForeignKeyConstraint(['from_version_id'], ['template_version.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['operator_id'], ['admin_user.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['review_id'], ['content_review.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['template_id'], ['question_template.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['to_version_id'], ['template_version.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['validation_run_id'], ['validation_run.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('content_release', schema=None) as batch_op:
        batch_op.create_index('ix_release_template_date', ['template_id', 'created_at'], unique=False)


def downgrade():
    # Removing review evidence must not leave a template enabled for new generation.
    now = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='microseconds')
    op.execute(sa.text("UPDATE content_epoch SET value=value+1, updated_at=:now WHERE EXISTS (SELECT 1 FROM question_template WHERE current_published_version_id IS NOT NULL AND status='active')").bindparams(now=now))
    op.execute(sa.text("UPDATE question_template SET status='disabled', lock_version=lock_version+1, updated_at=:now WHERE current_published_version_id IS NOT NULL AND status='active'").bindparams(now=now))
    with op.batch_alter_table('content_release', schema=None) as batch_op:
        batch_op.drop_index('ix_release_template_date')

    op.drop_table('content_release')
    with op.batch_alter_table('content_review', schema=None) as batch_op:
        batch_op.drop_index('ix_review_version_hash')

    op.drop_table('content_review')
    with op.batch_alter_table('admin_operation_log', schema=None) as batch_op:
        batch_op.drop_index('ix_operation_target_date')
        batch_op.drop_index('ix_operation_admin_date')

    op.drop_table('admin_operation_log')
