"""Owned preview and print-intent observations, never print-success evidence."""
from alembic import op
import sqlalchemy as sa
revision='0012'
down_revision='0011'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('usage_event',
        sa.Column('id',sa.Text(),primary_key=True),sa.Column('event_id',sa.Text(),nullable=False),
        sa.Column('created_at',sa.Text(),nullable=False),sa.Column('updated_at',sa.Text(),nullable=False),
        sa.Column('owner_user_id',sa.Text(),sa.ForeignKey('app_user.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('paper_id',sa.Text(),sa.ForeignKey('paper.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('event_type',sa.Text(),nullable=False),sa.Column('payload',sa.Text(),nullable=False),
        sa.Column('request_hash',sa.Text(),nullable=False),sa.Column('occurred_at',sa.Text()),sa.Column('received_at',sa.Text(),nullable=False),
        sa.UniqueConstraint('owner_user_id','event_id',name='uq_usage_owner_event'),
        sa.CheckConstraint('length(id) = 36',name='ck_usage_event_uuid'),
        *(sa.CheckConstraint(f"length({field}) = 32 AND substr({field}, 27) = '+08:00'",name='ck_usage_event_'+field) for field in ('created_at','updated_at','received_at')),
        sa.CheckConstraint("event_type IN ('preview','print_intent')",name='ck_usage_type'),
        sa.CheckConstraint('json_valid(payload) AND length(request_hash) = 64',name='ck_usage_payload'),
        sa.CheckConstraint("occurred_at IS NULL OR (length(occurred_at) = 32 AND substr(occurred_at, 27) = '+08:00')",name='ck_usage_occurred'))
    op.create_index('ix_usage_type_received','usage_event',['event_type','received_at'])
    op.create_index('ix_usage_paper_type','usage_event',['paper_id','event_type'])


def downgrade():
    if op.get_bind().execute(sa.text('SELECT count(*) FROM usage_event')).scalar_one():
        raise RuntimeError('已有使用事件，不能自动降级删除')
    op.drop_table('usage_event')
