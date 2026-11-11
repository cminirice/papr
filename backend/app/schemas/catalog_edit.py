from typing import Annotated, Literal
from uuid import UUID
from pydantic import Field, StringConstraints, StrictInt, model_validator
from app.schemas.common import DTO
from app.schemas.releases import Reason
from app.schemas.catalog import CatalogSummary

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Code = Annotated[str, StringConstraints(pattern=r'^[A-Za-z0-9_-]{1,64}$')]


class CatalogCreate(DTO):
    code: Code
    name: Name
    term: Literal['upper', 'lower']
    source_id: UUID | None = None
    reason: Reason


class CatalogDetail(CatalogSummary):
    source_id: UUID | None
    catalog_version: int


class CatalogEdit(DTO):
    name: Name | None = None
    term: Literal['upper', 'lower'] | None = None
    source_id: UUID | None = None
    status: Literal['draft', 'active', 'archived'] | None = None
    reason: Reason

    @model_validator(mode='after')
    def meaningful(self):
        fields = self.model_fields_set - {'reason'}
        if not fields or any(getattr(self, key) is None for key in fields - {'source_id'}):
            raise ValueError('必须提供有效修改字段')
        return self


class NodeCreate(DTO):
    code: Code
    name: Name
    parent_id: UUID | None = None
    node_type: Literal['theme', 'group'] = 'theme'
    sort_order: StrictInt = Field(default=0, ge=0, le=100000)
    reason: Reason


class NodeEdit(DTO):
    name: Name | None = None
    parent_id: UUID | None = None
    sort_order: StrictInt | None = Field(default=None, ge=0, le=100000)
    status: Literal['draft', 'active', 'disabled'] | None = None
    reason: Reason

    @model_validator(mode='after')
    def meaningful(self):
        fields = self.model_fields_set - {'reason'}
        if not fields or any(getattr(self, key) is None for key in fields - {'parent_id'}):
            raise ValueError('必须提供有效修改字段')
        return self


class MappingItem(DTO):
    knowledge_revision_id: UUID
    role: Literal['primary', 'review'] = 'primary'


class MappingEdit(DTO):
    items: list[MappingItem] = Field(max_length=200)
    reason: Reason

    @model_validator(mode='after')
    def unique(self):
        if len({i.knowledge_revision_id for i in self.items}) != len(self.items):
            raise ValueError('映射修订不得重复')
        return self


class MappingView(DTO):
    node_id: UUID
    lock_version: int
    items: list[MappingItem]


class RevisionOption(DTO):
    id: UUID
    point_id: UUID
    code: str
    name: str
    revision_no: int
    status: Literal['draft', 'published']


class RevisionOptions(DTO):
    items: list[RevisionOption]
    total: int
    offset: int
    limit: int
