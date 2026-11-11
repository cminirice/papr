from datetime import datetime
from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base, BeijingTime
from app.models.identity import Record, common_checks


class Job(Record, Base):
    """持久队列；支持template_validate与paper_generate执行。"""
    __tablename__ = "job"
    __table_args__ = (
        *common_checks("job", "available_at", nullable_times=("lease_until", "started_at", "finished_at", "expires_at")),
        CheckConstraint("kind IN ('paper_generate','template_preview','template_validate')", name="ck_job_kind"),
        CheckConstraint("status IN ('queued','running','succeeded','failed','cancelled')", name="ck_job_status"),
        CheckConstraint("phase IN ('queued','generating','rendering','saving','done')", name="ck_job_phase"),
        CheckConstraint("(owner_user_id IS NULL) != (owner_admin_id IS NULL)", name="ck_job_owner_xor"),
        CheckConstraint("(kind = 'paper_generate' AND owner_user_id IS NOT NULL) OR (kind != 'paper_generate' AND owner_admin_id IS NOT NULL)", name="ck_job_owner_kind"),
        CheckConstraint("length(idempotency_key) = 36 AND length(payload_hash) = 64", name="ck_job_keys"),
        CheckConstraint("json_valid(payload)", name="ck_job_payload_json"),
        CheckConstraint("result IS NULL OR json_valid(result)", name="ck_job_result_json"),
        CheckConstraint("intermediate_snapshot IS NULL OR json_valid(intermediate_snapshot)", name="ck_job_snapshot_json"),
        CheckConstraint("attempt >= 0 AND max_attempts BETWEEN 1 AND 2 AND attempt <= max_attempts AND priority >= 0 AND progress_done >= 0 AND progress_total >= progress_done", name="ck_job_counters"),
        UniqueConstraint("owner_user_id", "idempotency_key", name="uq_job_user_key"),
        UniqueConstraint("owner_admin_id", "idempotency_key", name="uq_job_admin_key"),
        Index("uq_job_active_user", "owner_user_id", unique=True, sqlite_where=text("kind = 'paper_generate' AND status IN ('queued','running')")),
        Index("ix_job_queue", "status", "available_at", "priority", "created_at"),
        Index("ix_job_lease", "status", "lease_until"),
        Index("ix_job_user_created", "owner_user_id", "created_at"),
        Index("ix_job_admin_created", "owner_admin_id", "created_at"),
        Index("ix_job_kind_created", "kind", "created_at", "id"),
        Index("ix_job_kind_finished", "kind", "status", "finished_at"),
    )
    kind: Mapped[str] = mapped_column(Text)
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("app_user.id", ondelete="RESTRICT"))
    owner_admin_id: Mapped[str | None] = mapped_column(ForeignKey("admin_user.id", ondelete="RESTRICT"))
    idempotency_key: Mapped[str] = mapped_column(Text)
    payload_hash: Mapped[str] = mapped_column(Text)
    payload: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="queued")
    phase: Mapped[str] = mapped_column(Text, default="queued")
    priority: Mapped[int] = mapped_column(Integer, default=0)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=2)
    lease_token: Mapped[str | None] = mapped_column(Text)
    lease_until: Mapped[datetime | None] = mapped_column(BeijingTime())
    available_at: Mapped[datetime] = mapped_column(BeijingTime())
    started_at: Mapped[datetime | None] = mapped_column(BeijingTime())
    finished_at: Mapped[datetime | None] = mapped_column(BeijingTime())
    expires_at: Mapped[datetime | None] = mapped_column(BeijingTime())
    progress_done: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    intermediate_snapshot: Mapped[str | None] = mapped_column(Text)
    content_schema_version: Mapped[int | None] = mapped_column(Integer)
