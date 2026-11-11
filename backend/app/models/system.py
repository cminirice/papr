from datetime import datetime
from sqlalchemy import CheckConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base, BeijingTime
from app.core.time import beijing_now


class ContentEpoch(Base):
    __tablename__ = "content_epoch"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_content_epoch_singleton"),
        CheckConstraint("value >= 0", name="ck_content_epoch_nonnegative"),
        CheckConstraint("length(updated_at) = 32 AND substr(updated_at, 27) = '+08:00'", name="ck_content_epoch_beijing"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(BeijingTime(), nullable=False, default=beijing_now)


from sqlalchemy import Text, ForeignKey


class AppSetting(Base):
    __tablename__ = 'app_setting'
    __table_args__ = (
        CheckConstraint("key IN ('question_count_options','generation_limits','retention_policy')", name='ck_setting_key'),
        CheckConstraint('json_valid(value) AND schema_version = 1 AND lock_version >= 1', name='ck_setting_value'),
        CheckConstraint("length(updated_at) = 32 AND substr(updated_at, 27) = '+08:00'", name='ck_setting_time'),
    )
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    schema_version: Mapped[int] = mapped_column(Integer)
    lock_version: Mapped[int] = mapped_column(Integer)
    updated_by: Mapped[str | None] = mapped_column(ForeignKey('admin_user.id', ondelete='RESTRICT'))
    updated_at: Mapped[datetime] = mapped_column(BeijingTime())
