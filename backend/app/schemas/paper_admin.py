from typing import Literal
from uuid import UUID
from pydantic import Field
from app.schemas.common import DTO, BeijingDatetime
from app.schemas.papers import PaperSummary, NoticeView
from app.schemas.content import MultiplicationQuestion
from app.schemas.releases import Reason


class NoticeCreate(DTO):
    question_id: UUID | None = None
    severity: Literal['info','error']
    action: Literal['notice','withdraw']
    message: str = Field(min_length=1,max_length=2000)
    reason: Reason


class SourceVersion(DTO):
    template_id: UUID
    version_id: UUID
    template_name: str


class AdminPaperSummary(PaperSummary):
    owner_user_id: UUID
    job_id: UUID


class AdminPaperList(DTO):
    items: list[AdminPaperSummary]
    next_cursor: str | None
    has_more: bool


class AdminPaperDetail(AdminPaperSummary):
    lock_version: int
    questions: list[MultiplicationQuestion]
    sources: list[SourceVersion]
