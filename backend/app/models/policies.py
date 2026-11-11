from sqlalchemy import CheckConstraint, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.models.identity import Record, common_checks


class KnowledgeTypePolicy(Record, Base):
    __tablename__ = 'knowledge_type_policy'
    __table_args__ = (
        *common_checks('knowledge_type_policy'),
        UniqueConstraint('knowledge_point_id', 'difficulty', 'question_type', name='uq_knowledge_type_policy'),
        CheckConstraint("difficulty IN ('basic','standard','challenge')", name='ck_policy_difficulty'),
        CheckConstraint("question_type IN ('choice','fill','answer')", name='ck_policy_type'),
        CheckConstraint("json_valid(count_options) AND json_type(count_options) = 'array'", name='ck_policy_options'),
        CheckConstraint('lock_version >= 1 AND (default_count IS NULL OR default_count IN (3,6,8,10,12))', name='ck_policy_lock_default'),
    )
    knowledge_point_id: Mapped[str] = mapped_column(ForeignKey('knowledge_point.id', ondelete='RESTRICT'))
    difficulty: Mapped[str] = mapped_column(Text)
    question_type: Mapped[str] = mapped_column(Text)
    count_options: Mapped[str] = mapped_column(Text)
    default_count: Mapped[int | None] = mapped_column(Integer)
    lock_version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[str] = mapped_column(ForeignKey('admin_user.id', ondelete='RESTRICT'))
