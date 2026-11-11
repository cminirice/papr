from typing import Literal
from uuid import UUID
from pydantic import Field
from app.schemas.common import BeijingDatetime, DTO


class CatalogSummary(DTO):
    id: UUID
    code: str
    name: str
    term: Literal['upper', 'lower']
    status: Literal['draft', 'active', 'archived']
    verification_status: Literal['provisional', 'verified']
    lock_version: int


class TemplateSummary(DTO):
    id: UUID
    code: str
    name: str
    status: Literal['active', 'disabled']
    current_published_version_id: UUID | None
    lock_version: int
    updated_at: BeijingDatetime


class CatalogList(DTO):
    items: list[CatalogSummary]
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    total: int = Field(ge=0)


class TemplateList(DTO):
    items: list[TemplateSummary]
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
