from datetime import datetime
from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base, BeijingTime
from app.models.identity import Record, common_checks


class ValidationRun(Record, Base):
    __tablename__ = 'validation_run'
    __table_args__ = (
        *common_checks('validation_run', nullable_times=('started_at', 'finished_at')),
        CheckConstraint("status IN ('queued','running','passed','failed','stale')", name='ck_validation_status'),
        CheckConstraint('length(content_hash) = 64', name='ck_validation_hash'),
        CheckConstraint('sample_count >= 0 AND failure_count >= 0', name='ck_validation_counts'),
        CheckConstraint('json_valid(coverage) AND (report IS NULL OR json_valid(report))', name='ck_validation_json'),
        Index('ix_validation_version_hash_status', 'template_version_id', 'content_hash', 'status', 'finished_at'),
    )
    template_version_id: Mapped[str] = mapped_column(ForeignKey('template_version.id', ondelete='RESTRICT'))
    job_id: Mapped[str] = mapped_column(ForeignKey('job.id', ondelete='RESTRICT'), unique=True)
    content_hash: Mapped[str] = mapped_column(Text)
    generator_id: Mapped[str] = mapped_column(ForeignKey('generator_definition.id', ondelete='RESTRICT'))
    validator_version: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default='queued')
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    coverage: Mapped[str] = mapped_column(Text, default='{}')
    report: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(BeijingTime())
    finished_at: Mapped[datetime | None] = mapped_column(BeijingTime())
    requested_by: Mapped[str] = mapped_column(ForeignKey('admin_user.id', ondelete='RESTRICT'))


class ValidationFailure(Record, Base):
    __tablename__ = 'validation_failure'
    __table_args__ = (
        *common_checks('validation_failure'),
        CheckConstraint('params IS NULL OR json_valid(params)', name='ck_validation_failure_params'),
        CheckConstraint('sample_snapshot IS NULL OR json_valid(sample_snapshot)', name='ck_validation_failure_snapshot'),
        Index('ix_validation_failure_run_profile', 'run_id', 'profile_id'),
    )
    run_id: Mapped[str] = mapped_column(ForeignKey('validation_run.id', ondelete='RESTRICT'))
    profile_id: Mapped[str] = mapped_column(ForeignKey('template_profile.id', ondelete='RESTRICT'))
    case_code: Mapped[str | None] = mapped_column(Text)
    seed: Mapped[str | None] = mapped_column(Text)
    params: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    sample_snapshot: Mapped[str | None] = mapped_column(Text)
