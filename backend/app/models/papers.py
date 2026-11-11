"""Immutable paper snapshots and attempt-scoped PDF assets."""
from datetime import datetime
from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base, BeijingTime
from app.models.identity import Record, common_checks


class Paper(Record, Base):
    __tablename__ = 'paper'
    __table_args__ = (
        *common_checks('paper', 'generated_at', nullable_times=('deleted_at',)),
        CheckConstraint("status IN ('active','withdrawn')", name='ck_paper_status'),
        CheckConstraint('choice_count >= 0 AND fill_count >= 0 AND answer_count >= 0 AND total_count > 0 AND total_count = choice_count + fill_count + answer_count', name='ck_paper_counts'),
        CheckConstraint('json_valid(catalog_snapshot) AND json_valid(config_snapshot)', name='ck_paper_json'),
        Index('ix_paper_owner_generated', 'owner_user_id', 'generated_at', 'id'),
        Index('ix_paper_generated', 'generated_at', 'id'),
    )
    owner_user_id: Mapped[str] = mapped_column(ForeignKey('app_user.id', ondelete='RESTRICT'))
    job_id: Mapped[str] = mapped_column(ForeignKey('job.id', ondelete='RESTRICT'), unique=True)
    title: Mapped[str] = mapped_column(Text)
    catalog_snapshot: Mapped[str] = mapped_column(Text)
    config_snapshot: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[str] = mapped_column(Text)
    choice_count: Mapped[int] = mapped_column(Integer)
    fill_count: Mapped[int] = mapped_column(Integer)
    answer_count: Mapped[int] = mapped_column(Integer)
    total_count: Mapped[int] = mapped_column(Integer)
    content_schema_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text, default='active')
    generated_at: Mapped[datetime] = mapped_column(BeijingTime())
    deleted_at: Mapped[datetime | None] = mapped_column(BeijingTime())


class Question(Record, Base):
    __tablename__ = 'question'
    __table_args__ = (
        *common_checks('question'),
        CheckConstraint("source_type = 'generated' AND length(seed) = 32", name='ck_question_source'),
        CheckConstraint("status IN ('active','flagged','withdrawn')", name='ck_question_status'),
        CheckConstraint('json_valid(content_snapshot) AND json_valid(answer_snapshot) AND json_valid(explanation_snapshot) AND json_valid(layout_snapshot) AND json_valid(generation_params)', name='ck_question_json'),
        Index('ix_question_template', 'template_version_id', 'created_at'),
        Index('ix_question_signature', 'semantic_signature'),
    )
    source_type: Mapped[str] = mapped_column(Text, default='generated')
    template_version_id: Mapped[str] = mapped_column(ForeignKey('template_version.id', ondelete='RESTRICT'))
    profile_id: Mapped[str] = mapped_column(ForeignKey('template_profile.id', ondelete='RESTRICT'))
    generator_id: Mapped[str] = mapped_column(ForeignKey('generator_definition.id', ondelete='RESTRICT'))
    question_type: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[str] = mapped_column(Text)
    render_mode: Mapped[str] = mapped_column(Text)
    content_schema_version: Mapped[int] = mapped_column(Integer)
    content_snapshot: Mapped[str] = mapped_column(Text)
    answer_snapshot: Mapped[str] = mapped_column(Text)
    explanation_snapshot: Mapped[str] = mapped_column(Text)
    layout_snapshot: Mapped[str] = mapped_column(Text)
    generation_params: Mapped[str] = mapped_column(Text)
    seed: Mapped[str] = mapped_column(Text)
    semantic_signature: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default='active')


class QuestionKnowledge(Record, Base):
    __tablename__ = 'question_knowledge'
    __table_args__ = (*common_checks('question_knowledge'),
        UniqueConstraint('question_id', 'knowledge_revision_id', 'role', name='uq_question_knowledge'),
        CheckConstraint("role IN ('primary','secondary','prerequisite')", name='ck_question_knowledge_role'))
    question_id: Mapped[str] = mapped_column(ForeignKey('question.id', ondelete='RESTRICT'))
    knowledge_revision_id: Mapped[str] = mapped_column(ForeignKey('knowledge_revision.id', ondelete='RESTRICT'))
    objective_revision_id: Mapped[str] = mapped_column(ForeignKey('objective_revision.id', ondelete='RESTRICT'))
    role: Mapped[str] = mapped_column(Text)


class PaperQuestion(Record, Base):
    __tablename__ = 'paper_question'
    __table_args__ = (*common_checks('paper_question'),
        UniqueConstraint('paper_id', 'position', name='uq_paper_position'),
        UniqueConstraint('paper_id', 'question_id', name='uq_paper_question'),
        UniqueConstraint('paper_id', 'semantic_signature', name='uq_paper_signature'),
        CheckConstraint('position > 0 AND section_position > 0', name='ck_paper_question_position'))
    paper_id: Mapped[str] = mapped_column(ForeignKey('paper.id', ondelete='RESTRICT'))
    question_id: Mapped[str] = mapped_column(ForeignKey('question.id', ondelete='RESTRICT'))
    position: Mapped[int] = mapped_column(Integer)
    section: Mapped[str] = mapped_column(Text)
    section_position: Mapped[int] = mapped_column(Integer)
    semantic_signature: Mapped[str] = mapped_column(Text)


class FileAsset(Record, Base):
    __tablename__ = 'file_asset'
    __table_args__ = (*common_checks('file_asset'),
        CheckConstraint("kind IN ('student_pdf','solution_pdf')", name='ck_asset_kind'),
        CheckConstraint("status IN ('pending','ready','failed','deleted')", name='ck_asset_status'),
        CheckConstraint("attempt BETWEEN 1 AND 2 AND length(lease_token) = 36", name='ck_asset_attempt'),
        CheckConstraint("status != 'ready' OR (paper_id IS NOT NULL AND byte_size IS NOT NULL AND byte_size > 0 AND sha256 IS NOT NULL AND length(sha256) = 64 AND renderer_version IS NOT NULL AND pages IS NOT NULL AND pages > 0 AND metadata_json IS NOT NULL)", name='ck_asset_ready'),
        CheckConstraint('metadata_json IS NULL OR json_valid(metadata_json)', name='ck_asset_json'),
        UniqueConstraint('job_id', 'attempt', 'kind', name='uq_asset_attempt_kind'),
        Index('uq_asset_ready_kind', 'paper_id', 'kind', unique=True, sqlite_where=text("status = 'ready'")),
        Index('ix_asset_job', 'job_id', 'status'))
    owner_user_id: Mapped[str] = mapped_column(ForeignKey('app_user.id', ondelete='RESTRICT'))
    job_id: Mapped[str] = mapped_column(ForeignKey('job.id', ondelete='RESTRICT'))
    paper_id: Mapped[str | None] = mapped_column(ForeignKey('paper.id', ondelete='RESTRICT'))
    attempt: Mapped[int] = mapped_column(Integer)
    lease_token: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    storage_key: Mapped[str] = mapped_column(Text, unique=True)
    mime_type: Mapped[str] = mapped_column(Text, default='application/pdf')
    byte_size: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(Text)
    pages: Mapped[int | None] = mapped_column(Integer)
    renderer_version: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default='pending')
    error_code: Mapped[str | None] = mapped_column(Text)


class PdfWorkerState(Base):
    """Only a worker which passed an actual render/parse probe advertises readiness."""
    __tablename__ = 'pdf_worker_state'
    __table_args__ = (CheckConstraint('id = 1', name='ck_pdf_worker_singleton'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    config_hash: Mapped[str] = mapped_column(Text)
    ready_until: Mapped[datetime] = mapped_column(BeijingTime())


class PaperNotice(Record, Base):
    __tablename__ = 'paper_notice'
    request_hash: Mapped[str] = mapped_column(Text)
    __table_args__ = (*common_checks('paper_notice'),
        CheckConstraint("severity IN ('info','error') AND action IN ('notice','withdraw')", name='ck_paper_notice_kind'),
        CheckConstraint('length(request_hash) = 64', name='ck_paper_notice_request_hash'),
        Index('ix_paper_notice_date', 'paper_id', 'created_at'))
    paper_id: Mapped[str] = mapped_column(ForeignKey('paper.id', ondelete='RESTRICT'))
    question_id: Mapped[str | None] = mapped_column(ForeignKey('question.id', ondelete='RESTRICT'))
    severity: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(ForeignKey('admin_user.id', ondelete='RESTRICT'))
