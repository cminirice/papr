"""identity_and_job_contract"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('admin_user',
    sa.Column('singleton', sa.Integer(), server_default='1', nullable=False),
    sa.Column('username', sa.Text(), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('last_login_at', sa.Text(), nullable=True),
    sa.Column('lock_version', sa.Integer(), nullable=False),
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('created_at', sa.Text(), nullable=False),
    sa.Column('updated_at', sa.Text(), nullable=False),
    sa.CheckConstraint("last_login_at IS NULL OR (length(last_login_at) = 32 AND substr(last_login_at, 27) = '+08:00')", name='ck_admin_user_last_login_at'),
    sa.CheckConstraint("length(created_at) = 32 AND substr(created_at, 27) = '+08:00'", name='ck_admin_user_created_at'),
    sa.CheckConstraint("length(updated_at) = 32 AND substr(updated_at, 27) = '+08:00'", name='ck_admin_user_updated_at'),
    sa.CheckConstraint("status IN ('active', 'disabled')", name='ck_admin_user_status'),
    sa.CheckConstraint('length(id) = 36', name='ck_admin_user_uuid'),
    sa.CheckConstraint('length(password_hash) <= 255', name='ck_admin_user_password_hash'),
    sa.CheckConstraint('length(username) BETWEEN 1 AND 64', name='ck_admin_user_username'),
    sa.CheckConstraint('lock_version >= 1', name='ck_admin_user_lock_version'),
    sa.CheckConstraint('singleton = 1', name='ck_admin_user_singleton'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('singleton'),
    sa.UniqueConstraint('username')
    )
    op.create_table('app_user',
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('first_seen_at', sa.Text(), nullable=False),
    sa.Column('last_seen_at', sa.Text(), nullable=False),
    sa.Column('deleted_at', sa.Text(), nullable=True),
    sa.Column('last_generation_succeeded_at', sa.Text(), nullable=True),
    sa.Column('next_generation_at', sa.Text(), nullable=True),
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('created_at', sa.Text(), nullable=False),
    sa.Column('updated_at', sa.Text(), nullable=False),
    sa.CheckConstraint("deleted_at IS NULL OR (length(deleted_at) = 32 AND substr(deleted_at, 27) = '+08:00')", name='ck_app_user_deleted_at'),
    sa.CheckConstraint("last_generation_succeeded_at IS NULL OR (length(last_generation_succeeded_at) = 32 AND substr(last_generation_succeeded_at, 27) = '+08:00')", name='ck_app_user_last_generation_succeeded_at'),
    sa.CheckConstraint("length(created_at) = 32 AND substr(created_at, 27) = '+08:00'", name='ck_app_user_created_at'),
    sa.CheckConstraint("length(first_seen_at) = 32 AND substr(first_seen_at, 27) = '+08:00'", name='ck_app_user_first_seen_at'),
    sa.CheckConstraint("length(last_seen_at) = 32 AND substr(last_seen_at, 27) = '+08:00'", name='ck_app_user_last_seen_at'),
    sa.CheckConstraint("length(updated_at) = 32 AND substr(updated_at, 27) = '+08:00'", name='ck_app_user_updated_at'),
    sa.CheckConstraint("next_generation_at IS NULL OR (length(next_generation_at) = 32 AND substr(next_generation_at, 27) = '+08:00')", name='ck_app_user_next_generation_at'),
    sa.CheckConstraint("status IN ('active', 'disabled')", name='ck_app_user_status'),
    sa.CheckConstraint('(last_generation_succeeded_at IS NULL) = (next_generation_at IS NULL)', name='ck_app_user_cooldown_pair'),
    sa.CheckConstraint('length(id) = 36', name='ck_app_user_uuid'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('app_user', schema=None) as batch_op:
        batch_op.create_index('ix_app_user_status_last_seen', ['status', 'last_seen_at'], unique=False)

    op.create_table('rate_limit_event',
    sa.Column('action', sa.Text(), nullable=False),
    sa.Column('subject_hash', sa.Text(), nullable=False),
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('created_at', sa.Text(), nullable=False),
    sa.Column('updated_at', sa.Text(), nullable=False),
    sa.CheckConstraint("action IN ('identity_create','generation_accept','admin_login','session_refresh')", name='ck_rate_limit_event_action'),
    sa.CheckConstraint("length(created_at) = 32 AND substr(created_at, 27) = '+08:00'", name='ck_rate_limit_event_created_at'),
    sa.CheckConstraint("length(updated_at) = 32 AND substr(updated_at, 27) = '+08:00'", name='ck_rate_limit_event_updated_at'),
    sa.CheckConstraint('length(id) = 36', name='ck_rate_limit_event_uuid'),
    sa.CheckConstraint('length(subject_hash) = 64', name='ck_rate_limit_event_hash'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('rate_limit_event', schema=None) as batch_op:
        batch_op.create_index('ix_rate_limit_event_window', ['action', 'subject_hash', 'created_at'], unique=False)

    op.create_table('admin_session',
    sa.Column('admin_id', sa.Text(), nullable=False),
    sa.Column('token_hash', sa.Text(), nullable=False),
    sa.Column('csrf_hash', sa.Text(), nullable=False),
    sa.Column('expires_at', sa.Text(), nullable=False),
    sa.Column('last_seen_at', sa.Text(), nullable=False),
    sa.Column('revoked_at', sa.Text(), nullable=True),
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('created_at', sa.Text(), nullable=False),
    sa.Column('updated_at', sa.Text(), nullable=False),
    sa.CheckConstraint("length(created_at) = 32 AND substr(created_at, 27) = '+08:00'", name='ck_admin_session_created_at'),
    sa.CheckConstraint("length(expires_at) = 32 AND substr(expires_at, 27) = '+08:00'", name='ck_admin_session_expires_at'),
    sa.CheckConstraint("length(last_seen_at) = 32 AND substr(last_seen_at, 27) = '+08:00'", name='ck_admin_session_last_seen_at'),
    sa.CheckConstraint("length(updated_at) = 32 AND substr(updated_at, 27) = '+08:00'", name='ck_admin_session_updated_at'),
    sa.CheckConstraint("revoked_at IS NULL OR (length(revoked_at) = 32 AND substr(revoked_at, 27) = '+08:00')", name='ck_admin_session_revoked_at'),
    sa.CheckConstraint('length(id) = 36', name='ck_admin_session_uuid'),
    sa.CheckConstraint('length(token_hash) = 64 AND length(csrf_hash) = 64', name='ck_admin_session_hash'),
    sa.ForeignKeyConstraint(['admin_id'], ['admin_user.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    with op.batch_alter_table('admin_session', schema=None) as batch_op:
        batch_op.create_index('ix_admin_session_admin_revoked', ['admin_id', 'revoked_at'], unique=False)
        batch_op.create_index('ix_admin_session_expires_at', ['expires_at'], unique=False)

    op.create_table('job',
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('owner_user_id', sa.Text(), nullable=True),
    sa.Column('owner_admin_id', sa.Text(), nullable=True),
    sa.Column('idempotency_key', sa.Text(), nullable=False),
    sa.Column('payload_hash', sa.Text(), nullable=False),
    sa.Column('payload', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('phase', sa.Text(), nullable=False),
    sa.Column('priority', sa.Integer(), nullable=False),
    sa.Column('attempt', sa.Integer(), nullable=False),
    sa.Column('max_attempts', sa.Integer(), nullable=False),
    sa.Column('lease_token', sa.Text(), nullable=True),
    sa.Column('lease_until', sa.Text(), nullable=True),
    sa.Column('available_at', sa.Text(), nullable=False),
    sa.Column('started_at', sa.Text(), nullable=True),
    sa.Column('finished_at', sa.Text(), nullable=True),
    sa.Column('expires_at', sa.Text(), nullable=True),
    sa.Column('progress_done', sa.Integer(), nullable=False),
    sa.Column('progress_total', sa.Integer(), nullable=False),
    sa.Column('result', sa.Text(), nullable=True),
    sa.Column('error_code', sa.Text(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('intermediate_snapshot', sa.Text(), nullable=True),
    sa.Column('content_schema_version', sa.Integer(), nullable=True),
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('created_at', sa.Text(), nullable=False),
    sa.Column('updated_at', sa.Text(), nullable=False),
    sa.CheckConstraint("(kind = 'paper_generate' AND owner_user_id IS NOT NULL) OR (kind != 'paper_generate' AND owner_admin_id IS NOT NULL)", name='ck_job_owner_kind'),
    sa.CheckConstraint("expires_at IS NULL OR (length(expires_at) = 32 AND substr(expires_at, 27) = '+08:00')", name='ck_job_expires_at'),
    sa.CheckConstraint("finished_at IS NULL OR (length(finished_at) = 32 AND substr(finished_at, 27) = '+08:00')", name='ck_job_finished_at'),
    sa.CheckConstraint("kind IN ('paper_generate','template_preview','template_validate')", name='ck_job_kind'),
    sa.CheckConstraint("lease_until IS NULL OR (length(lease_until) = 32 AND substr(lease_until, 27) = '+08:00')", name='ck_job_lease_until'),
    sa.CheckConstraint("length(available_at) = 32 AND substr(available_at, 27) = '+08:00'", name='ck_job_available_at'),
    sa.CheckConstraint("length(created_at) = 32 AND substr(created_at, 27) = '+08:00'", name='ck_job_created_at'),
    sa.CheckConstraint("length(updated_at) = 32 AND substr(updated_at, 27) = '+08:00'", name='ck_job_updated_at'),
    sa.CheckConstraint("phase IN ('queued','generating','rendering','saving','done')", name='ck_job_phase'),
    sa.CheckConstraint("started_at IS NULL OR (length(started_at) = 32 AND substr(started_at, 27) = '+08:00')", name='ck_job_started_at'),
    sa.CheckConstraint("status IN ('queued','running','succeeded','failed','cancelled')", name='ck_job_status'),
    sa.CheckConstraint('(owner_user_id IS NULL) != (owner_admin_id IS NULL)', name='ck_job_owner_xor'),
    sa.CheckConstraint('attempt >= 0 AND max_attempts BETWEEN 1 AND 2 AND attempt <= max_attempts AND priority >= 0 AND progress_done >= 0 AND progress_total >= progress_done', name='ck_job_counters'),
    sa.CheckConstraint('intermediate_snapshot IS NULL OR json_valid(intermediate_snapshot)', name='ck_job_snapshot_json'),
    sa.CheckConstraint('json_valid(payload)', name='ck_job_payload_json'),
    sa.CheckConstraint('length(id) = 36', name='ck_job_uuid'),
    sa.CheckConstraint('length(idempotency_key) = 36 AND length(payload_hash) = 64', name='ck_job_keys'),
    sa.CheckConstraint('result IS NULL OR json_valid(result)', name='ck_job_result_json'),
    sa.ForeignKeyConstraint(['owner_admin_id'], ['admin_user.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['owner_user_id'], ['app_user.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('owner_admin_id', 'idempotency_key', name='uq_job_admin_key'),
    sa.UniqueConstraint('owner_user_id', 'idempotency_key', name='uq_job_user_key')
    )
    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.create_index('ix_job_admin_created', ['owner_admin_id', 'created_at'], unique=False)
        batch_op.create_index('ix_job_lease', ['status', 'lease_until'], unique=False)
        batch_op.create_index('ix_job_queue', ['status', 'available_at', 'priority', 'created_at'], unique=False)
        batch_op.create_index('ix_job_user_created', ['owner_user_id', 'created_at'], unique=False)
        batch_op.create_index('uq_job_active_user', ['owner_user_id'], unique=True, sqlite_where=sa.text("kind = 'paper_generate' AND status IN ('queued','running')"))

    op.create_table('user_session',
    sa.Column('user_id', sa.Text(), nullable=False),
    sa.Column('token_hash', sa.Text(), nullable=False),
    sa.Column('csrf_hash', sa.Text(), nullable=False),
    sa.Column('expires_at', sa.Text(), nullable=False),
    sa.Column('last_seen_at', sa.Text(), nullable=False),
    sa.Column('revoked_at', sa.Text(), nullable=True),
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('created_at', sa.Text(), nullable=False),
    sa.Column('updated_at', sa.Text(), nullable=False),
    sa.CheckConstraint("length(created_at) = 32 AND substr(created_at, 27) = '+08:00'", name='ck_user_session_created_at'),
    sa.CheckConstraint("length(expires_at) = 32 AND substr(expires_at, 27) = '+08:00'", name='ck_user_session_expires_at'),
    sa.CheckConstraint("length(last_seen_at) = 32 AND substr(last_seen_at, 27) = '+08:00'", name='ck_user_session_last_seen_at'),
    sa.CheckConstraint("length(updated_at) = 32 AND substr(updated_at, 27) = '+08:00'", name='ck_user_session_updated_at'),
    sa.CheckConstraint("revoked_at IS NULL OR (length(revoked_at) = 32 AND substr(revoked_at, 27) = '+08:00')", name='ck_user_session_revoked_at'),
    sa.CheckConstraint('length(id) = 36', name='ck_user_session_uuid'),
    sa.CheckConstraint('length(token_hash) = 64 AND length(csrf_hash) = 64', name='ck_user_session_hash'),
    sa.ForeignKeyConstraint(['user_id'], ['app_user.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    with op.batch_alter_table('user_session', schema=None) as batch_op:
        batch_op.create_index('ix_user_session_expires_at', ['expires_at'], unique=False)
        batch_op.create_index('ix_user_session_user_revoked', ['user_id', 'revoked_at'], unique=False)


def downgrade():
    with op.batch_alter_table('user_session', schema=None) as batch_op:
        batch_op.drop_index('ix_user_session_user_revoked')
        batch_op.drop_index('ix_user_session_expires_at')

    op.drop_table('user_session')
    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.drop_index('uq_job_active_user', sqlite_where=sa.text("kind = 'paper_generate' AND status IN ('queued','running')"))
        batch_op.drop_index('ix_job_user_created')
        batch_op.drop_index('ix_job_queue')
        batch_op.drop_index('ix_job_lease')
        batch_op.drop_index('ix_job_admin_created')

    op.drop_table('job')
    with op.batch_alter_table('admin_session', schema=None) as batch_op:
        batch_op.drop_index('ix_admin_session_expires_at')
        batch_op.drop_index('ix_admin_session_admin_revoked')

    op.drop_table('admin_session')
    with op.batch_alter_table('rate_limit_event', schema=None) as batch_op:
        batch_op.drop_index('ix_rate_limit_event_window')

    op.drop_table('rate_limit_event')
    with op.batch_alter_table('app_user', schema=None) as batch_op:
        batch_op.drop_index('ix_app_user_status_last_seen')

    op.drop_table('app_user')
    op.drop_table('admin_user')
