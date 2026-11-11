"""基础内容版本哨兵；业务表随模块按统一迁移序列加入。"""
from datetime import datetime
from zoneinfo import ZoneInfo
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    table = op.create_table(
        "content_epoch",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_content_epoch_singleton"),
        sa.CheckConstraint("value >= 0", name="ck_content_epoch_nonnegative"),
        sa.CheckConstraint("length(updated_at) = 32 AND substr(updated_at, 27) = '+08:00'", name="ck_content_epoch_beijing"),
    )
    op.bulk_insert(table, [{"id": 1, "value": 0, "updated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="microseconds")}])


def downgrade():
    op.drop_table("content_epoch")
