from datetime import date
from typing import Annotated, Literal
from uuid import UUID
from pydantic import Field, StringConstraints, model_validator
from app.schemas.common import DTO, BeijingDatetime
from app.schemas.catalog_edit import Code, Name
from app.schemas.releases import Reason

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class SourceContent(DTO):
    title: Name
    publisher: Short | None = None
    url: Annotated[str, StringConstraints(pattern=r'^https?://[^\s]+$', max_length=2000)] | None = None
    reference_note: Text | None = None
    published_on: date | None = None
    checked_at: BeijingDatetime | None = None
    verification_status: Literal['unverified', 'reference', 'verified'] = 'reference'
    evidence_note: Text | None = None

    @model_validator(mode='after')
    def evidence(self):
        if not self.url and not self.reference_note:
            raise ValueError('须填写链接或参考说明')
        if self.verification_status == 'verified' and (not self.checked_at or not self.evidence_note):
            raise ValueError('核验须有时间及证据说明')
        return self


class SourceEdit(SourceContent):
    reason: Reason


class SourceView(SourceContent):
    id: UUID
    lock_version: int


class SourceList(DTO):
    items: list[SourceView]
    total: int
    offset: int
    limit: int


class KnowledgeContent(DTO):
    name: Name
    aliases: list[Short] = Field(default_factory=list, max_length=30)
    definition: Text
    boundary: Text
    misconceptions: list[Short] = Field(default_factory=list, max_length=30)
    source_id: UUID | None = None


class ObjectiveContent(DTO):
    knowledge_revision_id: UUID
    name: Name
    scope: Text
    success_criteria: list[Short] = Field(min_length=1, max_length=30)
    allowed_prerequisites: list[Code] = Field(default_factory=list, max_length=30)

    @model_validator(mode='after')
    def unique(self):
        if len(set(self.allowed_prerequisites)) != len(self.allowed_prerequisites):
            raise ValueError('先修知识点不得重复')
        return self


class KnowledgeCreate(DTO):
    code: Code
    domain: Literal['number', 'operation', 'geometry', 'model', 'statistics', 'practice']
    content: KnowledgeContent
    reason: Reason


class ObjectiveCreate(DTO):
    code: Code
    content: ObjectiveContent
    reason: Reason


class KnowledgeEdit(KnowledgeContent):
    reason: Reason


class ObjectiveEdit(ObjectiveContent):
    reason: Reason


class CopyRevision(DTO):
    source_revision_id: UUID
    reason: Reason


class RevisionBase(DTO):
    id: UUID
    revision_no: int
    status: Literal['draft', 'published']
    lock_version: int
    content_hash: str


class KnowledgeView(RevisionBase):
    content: KnowledgeContent


class ObjectiveView(RevisionBase):
    content: ObjectiveContent


class KnowledgeDetail(DTO):
    id: UUID
    code: str
    domain: str
    status: Literal['draft', 'active', 'disabled']
    current_revision_id: UUID | None
    lock_version: int
    revisions: list[KnowledgeView]


class ObjectiveDetail(DTO):
    id: UUID
    point_id: UUID
    code: str
    status: Literal['draft', 'active', 'disabled']
    current_revision_id: UUID | None
    lock_version: int
    revisions: list[ObjectiveView]


class KnowledgeList(DTO):
    items: list[KnowledgeDetail]
    total: int
    offset: int
    limit: int


class ObjectiveList(DTO):
    items: list[ObjectiveDetail]
    total: int
    offset: int
    limit: int
