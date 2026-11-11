from typing import Literal
from uuid import UUID
from pydantic import Field
from app.schemas.common import DTO, BeijingDatetime
from app.schemas.content import MultiplicationQuestion
from app.schemas.capabilities import CapabilitySelection
from app.schemas.generation import QuestionCounts


class PaperFile(DTO):
    id: UUID
    kind: Literal['student_pdf', 'solution_pdf']
    pages: int
    byte_size: int


class NoticeView(DTO):
    id: UUID
    question_id: UUID | None
    severity: Literal['info','error']
    action: Literal['notice','withdraw']
    message: str
    created_at: BeijingDatetime


class PaperSummary(DTO):
    status: Literal['active','withdrawn'] = 'active'
    notices: list[NoticeView] = Field(default_factory=list)
    id: UUID
    title: str
    difficulty: Literal['basic', 'standard', 'challenge']
    total_count: int
    catalog_name: str
    theme_name: str
    question_type_counts: QuestionCounts
    generated_at: BeijingDatetime
    files: list[PaperFile]


class PaperSelection(CapabilitySelection):
    """Reusable public selection; never carries old seed or publication evidence."""
    catalog_id: UUID
    question_type_counts: QuestionCounts


class PaperDetail(PaperSummary):
    questions: list[MultiplicationQuestion]
    selection: PaperSelection


class PaperList(DTO):
    items: list[PaperSummary]
    next_cursor: str | None
    has_more: bool
