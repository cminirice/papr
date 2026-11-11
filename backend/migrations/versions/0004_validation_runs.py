"""validation_runs"""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('validation_run',
    sa.Column('template_version_id', sa.Text(), nullable=False),
    sa.Column('job_id', sa.Text(), nullable=False),
    sa.Column('content_hash', sa.Text(), nullable=False),
    sa.Column('generator_id', sa.Text(), nullable=False),
    sa.Column('validator_version', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('sample_count', sa.Integer(), nullable=False),
    sa.Column('failure_count', sa.Integer(), nullable=False),
    sa.Column('coverage', sa.Text(), nullable=False),
    sa.Column('report', sa.Text(), nullable=True),
    sa.Column('started_at', sa.Text(), nullable=True),
    sa.Column('finished_at', sa.Text(), nullable=True),
    sa.Column('requested_by', sa.Text(), nullable=False),
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('created_at', sa.Text(), nullable=False),
    sa.Column('updated_at', sa.Text(), nullable=False),
    sa.CheckConstraint("finished_at IS NULL OR (length(finished_at) = 32 AND substr(finished_at, 27) = '+08:00')", name='ck_validation_run_finished_at'),
    sa.CheckConstraint("length(created_at) = 32 AND substr(created_at, 27) = '+08:00'", name='ck_validation_run_created_at'),
    sa.CheckConstraint("length(updated_at) = 32 AND substr(updated_at, 27) = '+08:00'", name='ck_validation_run_updated_at'),
    sa.CheckConstraint("started_at IS NULL OR (length(started_at) = 32 AND substr(started_at, 27) = '+08:00')", name='ck_validation_run_started_at'),
    sa.CheckConstraint("status IN ('queued','running','passed','failed','stale')", name='ck_validation_status'),
    sa.CheckConstraint('json_valid(coverage) AND (report IS NULL OR json_valid(report))', name='ck_validation_json'),
    sa.CheckConstraint('length(content_hash) = 64', name='ck_validation_hash'),
    sa.CheckConstraint('length(id) = 36', name='ck_validation_run_uuid'),
    sa.CheckConstraint('sample_count >= 0 AND failure_count >= 0', name='ck_validation_counts'),
    sa.ForeignKeyConstraint(['generator_id'], ['generator_definition.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['job_id'], ['job.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['requested_by'], ['admin_user.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['template_version_id'], ['template_version.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('job_id')
    )
    with op.batch_alter_table('validation_run', schema=None) as batch_op:
        batch_op.create_index('ix_validation_version_hash_status', ['template_version_id', 'content_hash', 'status', 'finished_at'], unique=False)

    op.create_table('validation_failure',
    sa.Column('run_id', sa.Text(), nullable=False),
    sa.Column('profile_id', sa.Text(), nullable=False),
    sa.Column('case_code', sa.Text(), nullable=True),
    sa.Column('seed', sa.Text(), nullable=True),
    sa.Column('params', sa.Text(), nullable=True),
    sa.Column('error_code', sa.Text(), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('sample_snapshot', sa.Text(), nullable=True),
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('created_at', sa.Text(), nullable=False),
    sa.Column('updated_at', sa.Text(), nullable=False),
    sa.CheckConstraint("length(created_at) = 32 AND substr(created_at, 27) = '+08:00'", name='ck_validation_failure_created_at'),
    sa.CheckConstraint("length(updated_at) = 32 AND substr(updated_at, 27) = '+08:00'", name='ck_validation_failure_updated_at'),
    sa.CheckConstraint('length(id) = 36', name='ck_validation_failure_uuid'),
    sa.CheckConstraint('params IS NULL OR json_valid(params)', name='ck_validation_failure_params'),
    sa.CheckConstraint('sample_snapshot IS NULL OR json_valid(sample_snapshot)', name='ck_validation_failure_snapshot'),
    sa.ForeignKeyConstraint(['profile_id'], ['template_profile.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['run_id'], ['validation_run.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('validation_failure', schema=None) as batch_op:
        batch_op.create_index('ix_validation_failure_run_profile', ['run_id', 'profile_id'], unique=False)


def downgrade():
    # Keep job history, but do not leave runnable jobs whose report table is removed.
    op.execute("UPDATE template_profile SET validated_count_options = '[]' WHERE template_version_id IN (SELECT template_version_id FROM validation_run)")
    op.execute("UPDATE job SET status='failed', phase='done', error_code='VALIDATION_SCHEMA_REMOVED', error_message='验证记录表已回退', lease_token=NULL, lease_until=NULL, result=NULL, finished_at=coalesce(finished_at,updated_at) WHERE kind='template_validate'")
    with op.batch_alter_table('validation_failure', schema=None) as batch_op:
        batch_op.drop_index('ix_validation_failure_run_profile')

    op.drop_table('validation_failure')
    with op.batch_alter_table('validation_run', schema=None) as batch_op:
        batch_op.drop_index('ix_validation_version_hash_status')

    op.drop_table('validation_run')
