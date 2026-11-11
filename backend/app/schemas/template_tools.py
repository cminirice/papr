from typing import Literal
from uuid import UUID
from pydantic import Field, StrictInt
from app.schemas.common import DTO, BeijingDatetime
from app.schemas.catalog_edit import Code, Name
from app.schemas.template_edit import DraftEdit
from app.schemas.validation import ValidationRequest
from app.schemas.content import MultiplicationQuestion
from app.schemas.releases import Reason


class GeneratorChoice(DTO):
    id: UUID
    key: str
    version: str
    available: bool
    question_types: list[str]
    difficulties: list[str]
    objective_revision_ids: list[UUID]
    default_config: DraftEdit
    task_configs: dict[str, DraftEdit]
    task_objective_revision_ids: dict[str, list[UUID]]


class TemplateCreate(DTO):
    task: Literal['product', 'missing_digit', 'error_choice', 'correction', 'zero_product'] = 'product'
    question_type: Literal['answer', 'fill', 'choice'] = 'answer'
    code: Code
    name: Name
    generator_id: UUID
    objective_revision_id: UUID
    config: DraftEdit
    reason: Reason


class PreviewRequest(ValidationRequest):
    difficulty: Literal['basic', 'standard', 'challenge']
    count: StrictInt = Field(ge=1, le=10)
    seed: str = Field(min_length=1, max_length=128)


class PreviewView(DTO):
    id: UUID
    template_version_id: UUID
    content_hash: str
    status: Literal['queued', 'running', 'succeeded', 'failed', 'cancelled']
    attempt: int
    created_at: BeijingDatetime
    stale: bool
    error_code: str | None
    questions: list[MultiplicationQuestion]


class PreviewList(DTO):
    items: list[PreviewView]
