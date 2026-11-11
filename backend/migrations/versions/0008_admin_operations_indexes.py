"""Indexes for admin history and Beijing-date aggregates; no data changes."""
from alembic import op

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('ix_job_kind_created', 'job', ['kind', 'created_at', 'id'])
    op.create_index('ix_job_kind_finished', 'job', ['kind', 'status', 'finished_at'])
    op.create_index('ix_paper_generated', 'paper', ['generated_at', 'id'])


def downgrade():
    op.drop_index('ix_paper_generated', table_name='paper')
    op.drop_index('ix_job_kind_finished', table_name='job')
    op.drop_index('ix_job_kind_created', table_name='job')
