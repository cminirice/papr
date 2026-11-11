"""目录与模板草稿模型；发布/验证记录在后续流程迁入。"""
from datetime import datetime
from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base, BeijingTime
from app.models.identity import Record, common_checks


class Locked:
    lock_version: Mapped[int] = mapped_column(Integer, default=1)


class ContentSource(Record, Locked, Base):
    __tablename__ = "content_source"
    __table_args__ = (
        *common_checks("content_source", nullable_times=('checked_at',)),
        CheckConstraint("verification_status IN ('unverified','reference','verified')", name="ck_content_source_0"),
        CheckConstraint("length(coalesce(url, '')) > 0 OR length(coalesce(reference_note, '')) > 0", name="ck_content_source_1"),
        CheckConstraint('lock_version >= 1', name="ck_content_source_2"),
    )
    title: Mapped[str] = mapped_column(Text)
    publisher: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    reference_note: Mapped[str | None] = mapped_column(Text)
    published_on: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime | None] = mapped_column(BeijingTime())
    verification_status: Mapped[str] = mapped_column(Text, default='reference')
    evidence_note: Mapped[str | None] = mapped_column(Text)


class ContentCatalog(Record, Locked, Base):
    __tablename__ = "content_catalog"
    __table_args__ = (
        *common_checks("content_catalog"),
        CheckConstraint("subject = 'math'", name="ck_content_catalog_0"),
        CheckConstraint('grade = 4', name="ck_content_catalog_1"),
        CheckConstraint("term IN ('upper','lower')", name="ck_content_catalog_2"),
        CheckConstraint('catalog_version >= 1', name="ck_content_catalog_3"),
        CheckConstraint("status IN ('draft','active','archived')", name="ck_content_catalog_4"),
        CheckConstraint("verification_status IN ('provisional','verified')", name="ck_content_catalog_5"),
        CheckConstraint('lock_version >= 1', name="ck_content_catalog_6"),
    )
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text, default='math')
    grade: Mapped[int] = mapped_column(Integer, default=4)
    term: Mapped[str] = mapped_column(Text)
    catalog_version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(Text, default='draft')
    verification_status: Mapped[str] = mapped_column(Text, default='provisional')
    source_id: Mapped[str | None] = mapped_column(ForeignKey("content_source.id", ondelete="RESTRICT"))


class CatalogNode(Record, Locked, Base):
    __tablename__ = "catalog_node"
    __table_args__ = (
        *common_checks("catalog_node"),
        CheckConstraint("node_type IN ('theme','group')", name="ck_catalog_node_0"),
        CheckConstraint("status IN ('draft','active','disabled')", name="ck_catalog_node_1"),
        CheckConstraint('parent_id IS NULL OR parent_id <> id', name="ck_catalog_node_2"),
        CheckConstraint('lock_version >= 1', name="ck_catalog_node_3"),
        UniqueConstraint('catalog_id', 'code', name="uq_catalog_node_0"),
        Index("ix_catalog_node_0", 'catalog_id', 'parent_id', 'sort_order'),
    )
    catalog_id: Mapped[str] = mapped_column(ForeignKey("content_catalog.id", ondelete="RESTRICT"))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("catalog_node.id", ondelete="RESTRICT"))
    code: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    node_type: Mapped[str] = mapped_column(Text, default='theme')
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(Text, default='draft')


class KnowledgePoint(Record, Locked, Base):
    __tablename__ = "knowledge_point"
    __table_args__ = (
        *common_checks("knowledge_point"),
        CheckConstraint("domain IN ('number','operation','geometry','model','statistics','practice')", name="ck_knowledge_point_0"),
        CheckConstraint("status IN ('draft','active','disabled')", name="ck_knowledge_point_1"),
        CheckConstraint('lock_version >= 1', name="ck_knowledge_point_2"),
    )
    code: Mapped[str] = mapped_column(Text, unique=True)
    domain: Mapped[str] = mapped_column(Text, default='operation')
    current_revision_id: Mapped[str | None] = mapped_column(ForeignKey("knowledge_revision.id", ondelete="RESTRICT", use_alter=True, name="fk_knowledge_point_current"))
    status: Mapped[str] = mapped_column(Text, default='draft')


class KnowledgeRevision(Record, Locked, Base):
    __tablename__ = "knowledge_revision"
    __table_args__ = (
        *common_checks("knowledge_revision"),
        CheckConstraint('revision_no >= 1', name="ck_knowledge_revision_0"),
        CheckConstraint("status IN ('draft','published')", name="ck_knowledge_revision_1"),
        CheckConstraint('length(content_hash) = 64', name="ck_knowledge_revision_2"),
        CheckConstraint('json_valid(aliases)', name="ck_knowledge_revision_3"),
        CheckConstraint('json_valid(misconceptions)', name="ck_knowledge_revision_4"),
        CheckConstraint('lock_version >= 1', name="ck_knowledge_revision_5"),
        UniqueConstraint('point_id', 'revision_no', name="uq_knowledge_revision_0"),
    )
    point_id: Mapped[str] = mapped_column(ForeignKey("knowledge_point.id", ondelete="RESTRICT"))
    revision_no: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(Text)
    aliases: Mapped[str] = mapped_column(Text, default='[]')
    definition: Mapped[str] = mapped_column(Text)
    boundary: Mapped[str] = mapped_column(Text)
    misconceptions: Mapped[str] = mapped_column(Text, default='[]')
    source_id: Mapped[str | None] = mapped_column(ForeignKey("content_source.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(Text, default='draft')
    content_hash: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(ForeignKey("admin_user.id", ondelete="RESTRICT"))


class CatalogKnowledge(Record, Base):
    __tablename__ = "catalog_knowledge"
    __table_args__ = (
        *common_checks("catalog_knowledge"),
        CheckConstraint("role IN ('primary','review')", name="ck_catalog_knowledge_0"),
        UniqueConstraint('node_id', 'knowledge_revision_id', name="uq_catalog_knowledge_0"),
    )
    node_id: Mapped[str] = mapped_column(ForeignKey("catalog_node.id", ondelete="RESTRICT"))
    knowledge_revision_id: Mapped[str] = mapped_column(ForeignKey("knowledge_revision.id", ondelete="RESTRICT"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    role: Mapped[str] = mapped_column(Text, default='primary')


class TrainingObjective(Record, Locked, Base):
    __tablename__ = "training_objective"
    __table_args__ = (
        *common_checks("training_objective"),
        CheckConstraint("status IN ('draft','active','disabled')", name="ck_training_objective_0"),
        CheckConstraint('lock_version >= 1', name="ck_training_objective_1"),
    )
    point_id: Mapped[str] = mapped_column(ForeignKey("knowledge_point.id", ondelete="RESTRICT"))
    code: Mapped[str] = mapped_column(Text, unique=True)
    current_revision_id: Mapped[str | None] = mapped_column(ForeignKey("objective_revision.id", ondelete="RESTRICT", use_alter=True, name="fk_training_objective_current"))
    status: Mapped[str] = mapped_column(Text, default='draft')


class ObjectiveRevision(Record, Locked, Base):
    __tablename__ = "objective_revision"
    __table_args__ = (
        *common_checks("objective_revision"),
        CheckConstraint('revision_no >= 1', name="ck_objective_revision_0"),
        CheckConstraint("status IN ('draft','published')", name="ck_objective_revision_1"),
        CheckConstraint('length(content_hash) = 64', name="ck_objective_revision_2"),
        CheckConstraint('json_valid(success_criteria)', name="ck_objective_revision_3"),
        CheckConstraint('json_valid(allowed_prerequisites)', name="ck_objective_revision_4"),
        CheckConstraint('lock_version >= 1', name="ck_objective_revision_5"),
        UniqueConstraint('objective_id', 'revision_no', name="uq_objective_revision_0"),
    )
    objective_id: Mapped[str] = mapped_column(ForeignKey("training_objective.id", ondelete="RESTRICT"))
    revision_no: Mapped[int] = mapped_column(Integer)
    knowledge_revision_id: Mapped[str] = mapped_column(ForeignKey("knowledge_revision.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(Text)
    success_criteria: Mapped[str] = mapped_column(Text)
    allowed_prerequisites: Mapped[str] = mapped_column(Text, default='[]')
    content_hash: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default='draft')
    created_by: Mapped[str] = mapped_column(ForeignKey("admin_user.id", ondelete="RESTRICT"))


class GeneratorDefinition(Record, Base):
    __tablename__ = "generator_definition"
    __table_args__ = (
        *common_checks("generator_definition", "registered_at"),
        CheckConstraint("deployment_status IN ('available','unavailable')", name="ck_generator_definition_0"),
        CheckConstraint('length(artifact_hash) = 64', name="ck_generator_definition_1"),
        CheckConstraint('json_valid(param_schema)', name="ck_generator_definition_2"),
        CheckConstraint('json_valid(output_schema)', name="ck_generator_definition_3"),
        CheckConstraint('json_valid(supported_render_modes)', name="ck_generator_definition_4"),
        CheckConstraint('json_valid(supported_question_types)', name="ck_generator_definition_5"),
        CheckConstraint('json_valid(supported_target_rules)', name="ck_generator_definition_6"),
        CheckConstraint('json_valid(supported_difficulties)', name="ck_generator_definition_7"),
        UniqueConstraint('key', 'version', name="uq_generator_definition_0"),
    )
    key: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(Text)
    param_schema: Mapped[str] = mapped_column(Text)
    output_schema: Mapped[str] = mapped_column(Text)
    supported_render_modes: Mapped[str] = mapped_column(Text)
    supported_question_types: Mapped[str] = mapped_column(Text)
    supported_target_rules: Mapped[str] = mapped_column(Text)
    supported_difficulties: Mapped[str] = mapped_column(Text)
    artifact_hash: Mapped[str] = mapped_column(Text)
    validator_version: Mapped[str] = mapped_column(Text)
    deployment_status: Mapped[str] = mapped_column(Text, default='available')
    registered_at: Mapped[datetime] = mapped_column(BeijingTime())


class QuestionTemplate(Record, Locked, Base):
    __tablename__ = "question_template"
    __table_args__ = (
        *common_checks("question_template"),
        CheckConstraint("status IN ('active','disabled')", name="ck_question_template_0"),
        CheckConstraint('lock_version >= 1', name="ck_question_template_1"),
    )
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default='active')
    current_published_version_id: Mapped[str | None] = mapped_column(ForeignKey("template_version.id", ondelete="RESTRICT", use_alter=True, name="fk_question_template_current"))


class TemplateVersion(Record, Locked, Base):
    __tablename__ = "template_version"
    __table_args__ = (
        *common_checks("template_version", nullable_times=('published_at',)),
        CheckConstraint('version_no >= 1', name="ck_template_version_0"),
        CheckConstraint('content_schema_version >= 1', name="ck_template_version_1"),
        CheckConstraint("question_type IN ('choice','fill','answer')", name="ck_template_version_2"),
        CheckConstraint("render_mode IN ('direct','vertical','word','diagram','grid')", name="ck_template_version_3"),
        CheckConstraint("status IN ('draft','published','retired')", name="ck_template_version_4"),
        CheckConstraint('length(content_hash) = 64', name="ck_template_version_5"),
        CheckConstraint('(published_by IS NULL) = (published_at IS NULL)', name="ck_template_version_6"),
        CheckConstraint("status <> 'published' OR published_by IS NOT NULL", name="ck_template_version_7"),
        CheckConstraint('json_valid(stem_config)', name="ck_template_version_8"),
        CheckConstraint('json_valid(answer_config)', name="ck_template_version_9"),
        CheckConstraint('json_valid(explanation_config)', name="ck_template_version_10"),
        CheckConstraint('diagram_config IS NULL OR json_valid(diagram_config)', name="ck_template_version_11"),
        CheckConstraint('lock_version >= 1', name="ck_template_version_12"),
        UniqueConstraint('template_id', 'version_no', name="uq_template_version_0"),
        Index("ix_template_version_0", 'generator_id', 'status'),
    )
    template_id: Mapped[str] = mapped_column(ForeignKey("question_template.id", ondelete="RESTRICT"))
    version_no: Mapped[int] = mapped_column(Integer)
    generator_id: Mapped[str] = mapped_column(ForeignKey("generator_definition.id", ondelete="RESTRICT"))
    question_type: Mapped[str] = mapped_column(Text)
    render_mode: Mapped[str] = mapped_column(Text)
    content_schema_version: Mapped[int] = mapped_column(Integer, default=1)
    stem_config: Mapped[str] = mapped_column(Text)
    answer_config: Mapped[str] = mapped_column(Text)
    explanation_config: Mapped[str] = mapped_column(Text)
    diagram_config: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default='draft')
    created_by: Mapped[str] = mapped_column(ForeignKey("admin_user.id", ondelete="RESTRICT"))
    published_by: Mapped[str | None] = mapped_column(ForeignKey("admin_user.id", ondelete="RESTRICT"))
    published_at: Mapped[datetime | None] = mapped_column(BeijingTime())


class TemplateObjective(Record, Base):
    __tablename__ = "template_objective"
    __table_args__ = (
        *common_checks("template_objective"),
        CheckConstraint("role IN ('primary','secondary','prerequisite')", name="ck_template_objective_0"),
        UniqueConstraint('template_version_id', 'objective_revision_id', 'role', name="uq_template_objective_0"),
    )
    template_version_id: Mapped[str] = mapped_column(ForeignKey("template_version.id", ondelete="RESTRICT"))
    objective_revision_id: Mapped[str] = mapped_column(ForeignKey("objective_revision.id", ondelete="RESTRICT"))
    role: Mapped[str] = mapped_column(Text, default='primary')


class TemplateProfile(Record, Base):
    __tablename__ = "template_profile"
    __table_args__ = (
        *common_checks("template_profile"),
        CheckConstraint("difficulty IN ('basic','standard','challenge')", name="ck_template_profile_0"),
        CheckConstraint('max_per_paper BETWEEN 1 AND 12', name="ck_template_profile_1"),
        CheckConstraint('length(profile_hash) = 64', name="ck_template_profile_2"),
        CheckConstraint('json_valid(param_config)', name="ck_template_profile_3"),
        CheckConstraint('json_valid(constraint_config)', name="ck_template_profile_4"),
        CheckConstraint('json_valid(layout_config)', name="ck_template_profile_5"),
        CheckConstraint('json_valid(validated_count_options)', name="ck_template_profile_6"),
        UniqueConstraint('template_version_id', 'difficulty', name="uq_template_profile_0"),
    )
    template_version_id: Mapped[str] = mapped_column(ForeignKey("template_version.id", ondelete="RESTRICT"))
    difficulty: Mapped[str] = mapped_column(Text)
    param_config: Mapped[str] = mapped_column(Text)
    constraint_config: Mapped[str] = mapped_column(Text)
    layout_config: Mapped[str] = mapped_column(Text)
    semantic_dedupe_rule: Mapped[str] = mapped_column(Text)
    max_per_paper: Mapped[int] = mapped_column(Integer, default=12)
    validated_count_options: Mapped[str] = mapped_column(Text, default='[]')
    profile_hash: Mapped[str] = mapped_column(Text)


class TemplateTestCase(Record, Base):
    __tablename__ = "template_test_case"
    __table_args__ = (
        *common_checks("template_test_case"),
        CheckConstraint("kind IN ('boundary','fixed','regression')", name="ck_template_test_case_0"),
        CheckConstraint('enabled IN (0,1)', name="ck_template_test_case_1"),
        CheckConstraint("length(coalesce(seed, '')) > 0 OR params IS NOT NULL", name="ck_template_test_case_2"),
        CheckConstraint('params IS NULL OR json_valid(params)', name="ck_template_test_case_3"),
        CheckConstraint('json_valid(expected_properties)', name="ck_template_test_case_4"),
        UniqueConstraint('profile_id', 'code', name="uq_template_test_case_0"),
    )
    profile_id: Mapped[str] = mapped_column(ForeignKey("template_profile.id", ondelete="RESTRICT"))
    code: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text, default='fixed')
    seed: Mapped[str | None] = mapped_column(Text)
    params: Mapped[str | None] = mapped_column(Text)
    expected_properties: Mapped[str] = mapped_column(Text)
    enabled: Mapped[int] = mapped_column(Integer, default=1)


