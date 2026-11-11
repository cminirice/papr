from datetime import datetime
from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base, BeijingTime
from app.models.identity import Record, common_checks


class ContentReview(Record, Base):
    __tablename__ = 'content_review'
    __table_args__ = (
        *common_checks('content_review', 'reviewed_at'),
        CheckConstraint("decision IN ('approved','rejected')", name='ck_review_decision'),
        CheckConstraint('length(content_hash) = 64 AND length(trim(comment)) > 0', name='ck_review_content'),
        CheckConstraint('json_valid(sample_refs)', name='ck_review_samples'),
        CheckConstraint("print_checked IN (0,1) AND (decision <> 'approved' OR print_checked = 1)", name='ck_review_print'),
        Index('ix_review_version_hash', 'template_version_id', 'content_hash', 'reviewed_at'),
    )
    template_version_id: Mapped[str] = mapped_column(ForeignKey('template_version.id', ondelete='RESTRICT'))
    validation_run_id: Mapped[str] = mapped_column(ForeignKey('validation_run.id', ondelete='RESTRICT'))
    content_hash: Mapped[str] = mapped_column(Text)
    decision: Mapped[str] = mapped_column(Text)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey('admin_user.id', ondelete='RESTRICT'))
    comment: Mapped[str] = mapped_column(Text)
    sample_refs: Mapped[str] = mapped_column(Text)
    print_checked: Mapped[int] = mapped_column(Integer)
    reviewed_at: Mapped[datetime] = mapped_column(BeijingTime())


class ContentRelease(Record, Base):
    __tablename__ = 'content_release'
    __table_args__ = (
        *common_checks('content_release'),
        CheckConstraint("action IN ('publish','disable','enable','rollback')", name='ck_release_action'),
        CheckConstraint('epoch >= 1 AND length(trim(reason)) > 0', name='ck_release_reason'),
        Index('ix_release_template_date', 'template_id', 'created_at'),
    )
    template_id: Mapped[str] = mapped_column(ForeignKey('question_template.id', ondelete='RESTRICT'))
    from_version_id: Mapped[str | None] = mapped_column(ForeignKey('template_version.id', ondelete='RESTRICT'))
    to_version_id: Mapped[str | None] = mapped_column(ForeignKey('template_version.id', ondelete='RESTRICT'))
    action: Mapped[str] = mapped_column(Text)
    operator_id: Mapped[str] = mapped_column(ForeignKey('admin_user.id', ondelete='RESTRICT'))
    reason: Mapped[str] = mapped_column(Text)
    validation_run_id: Mapped[str | None] = mapped_column(ForeignKey('validation_run.id', ondelete='RESTRICT'))
    review_id: Mapped[str | None] = mapped_column(ForeignKey('content_review.id', ondelete='RESTRICT'))
    epoch: Mapped[int] = mapped_column(Integer)


class AdminOperationLog(Record, Base):
    __tablename__ = 'admin_operation_log'
    __table_args__ = (
        *common_checks('admin_operation_log'),
        CheckConstraint("target_type IN ('knowledge_revision','objective_revision','template_version','question_template','content_catalog','catalog_node','knowledge_point','training_objective','content_source','paper','job','app_setting')", name='ck_operation_target'),
        CheckConstraint('(before_summary IS NULL OR json_valid(before_summary)) AND (after_summary IS NULL OR json_valid(after_summary))', name='ck_operation_summary'),
        Index('ix_operation_admin_date', 'admin_id', 'created_at'),
        Index('ix_operation_target_date', 'target_type', 'target_id', 'created_at'),
    )
    admin_id: Mapped[str] = mapped_column(ForeignKey('admin_user.id', ondelete='RESTRICT'))
    action: Mapped[str] = mapped_column(Text)
    target_type: Mapped[str] = mapped_column(Text)
    target_id: Mapped[str] = mapped_column(Text)
    request_id: Mapped[str] = mapped_column(Text)
    before_summary: Mapped[str | None] = mapped_column(Text)
    after_summary: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
