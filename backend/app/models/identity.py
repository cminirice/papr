from datetime import datetime
from uuid import uuid4
from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base, BeijingTime
from app.core.time import beijing_now


def time_check(column: str, nullable: bool = False) -> str:
    rule = f"length({column}) = 32 AND substr({column}, 27) = '+08:00'"
    return f"{column} IS NULL OR ({rule})" if nullable else rule


def common_checks(table: str, *times: str, nullable_times: tuple[str, ...] = ()):
    return (
        CheckConstraint("length(id) = 36", name=f"ck_{table}_uuid"),
        *(CheckConstraint(time_check(name), name=f"ck_{table}_{name}") for name in ("created_at", "updated_at", *times)),
        *(CheckConstraint(time_check(name, True), name=f"ck_{table}_{name}") for name in nullable_times),
    )


class Record:
    id: Mapped[str] = mapped_column(Text, primary_key=True, default=lambda: str(uuid4()))
    created_at: Mapped[datetime] = mapped_column(BeijingTime(), default=beijing_now)
    updated_at: Mapped[datetime] = mapped_column(BeijingTime(), default=beijing_now)


class AppUser(Record, Base):
    __tablename__ = "app_user"
    __table_args__ = (
        *common_checks("app_user", "first_seen_at", "last_seen_at", nullable_times=("deleted_at", "last_generation_succeeded_at", "next_generation_at")),
        CheckConstraint("status IN ('active', 'disabled')", name="ck_app_user_status"),
        CheckConstraint("(last_generation_succeeded_at IS NULL) = (next_generation_at IS NULL)", name="ck_app_user_cooldown_pair"),
        Index("ix_app_user_status_last_seen", "status", "last_seen_at"),
    )
    status: Mapped[str] = mapped_column(Text, default="active")
    first_seen_at: Mapped[datetime] = mapped_column(BeijingTime())
    last_seen_at: Mapped[datetime] = mapped_column(BeijingTime())
    deleted_at: Mapped[datetime | None] = mapped_column(BeijingTime())
    last_generation_succeeded_at: Mapped[datetime | None] = mapped_column(BeijingTime())
    next_generation_at: Mapped[datetime | None] = mapped_column(BeijingTime())


class UserSession(Record, Base):
    __tablename__ = "user_session"
    __table_args__ = (
        *common_checks("user_session", "expires_at", "last_seen_at", nullable_times=("revoked_at",)),
        CheckConstraint("length(token_hash) = 64 AND length(csrf_hash) = 64", name="ck_user_session_hash"),
        Index("ix_user_session_expires_at", "expires_at"),
        Index("ix_user_session_user_revoked", "user_id", "revoked_at"),
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("app_user.id", ondelete="RESTRICT"))
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    csrf_hash: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(BeijingTime())
    last_seen_at: Mapped[datetime] = mapped_column(BeijingTime())
    revoked_at: Mapped[datetime | None] = mapped_column(BeijingTime())


class AdminUser(Record, Base):
    __tablename__ = "admin_user"
    __table_args__ = (
        *common_checks("admin_user", nullable_times=("last_login_at",)),
        CheckConstraint("status IN ('active', 'disabled')", name="ck_admin_user_status"),
        CheckConstraint("length(username) BETWEEN 1 AND 64", name="ck_admin_user_username"),
        CheckConstraint("length(password_hash) <= 255", name="ck_admin_user_password_hash"),
        CheckConstraint("lock_version >= 1", name="ck_admin_user_lock_version"),
        # 一期单管理员：固定值唯一列，禁止并发初始化第二个账户。
        CheckConstraint("singleton = 1", name="ck_admin_user_singleton"),
    )
    singleton: Mapped[int] = mapped_column(Integer, default=1, server_default="1", unique=True)
    username: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="active")
    last_login_at: Mapped[datetime | None] = mapped_column(BeijingTime())
    lock_version: Mapped[int] = mapped_column(Integer, default=1)


class AdminSession(Record, Base):
    __tablename__ = "admin_session"
    __table_args__ = (
        *common_checks("admin_session", "expires_at", "last_seen_at", nullable_times=("revoked_at",)),
        CheckConstraint("length(token_hash) = 64 AND length(csrf_hash) = 64", name="ck_admin_session_hash"),
        Index("ix_admin_session_expires_at", "expires_at"),
        Index("ix_admin_session_admin_revoked", "admin_id", "revoked_at"),
    )
    admin_id: Mapped[str] = mapped_column(ForeignKey("admin_user.id", ondelete="RESTRICT"))
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    csrf_hash: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(BeijingTime())
    last_seen_at: Mapped[datetime] = mapped_column(BeijingTime())
    revoked_at: Mapped[datetime | None] = mapped_column(BeijingTime())


class RateLimitEvent(Record, Base):
    __tablename__ = "rate_limit_event"
    __table_args__ = (
        *common_checks("rate_limit_event"),
        CheckConstraint("action IN ('identity_create','generation_accept','admin_login','session_refresh')", name="ck_rate_limit_event_action"),
        CheckConstraint("length(subject_hash) = 64", name="ck_rate_limit_event_hash"),
        Index("ix_rate_limit_event_window", "action", "subject_hash", "created_at"),
    )
    action: Mapped[str] = mapped_column(Text)
    subject_hash: Mapped[str] = mapped_column(Text)
