from typing import Annotated, Literal
from uuid import UUID
from pydantic import Field, StrictBool, StringConstraints, model_validator
from app.schemas.common import BeijingDatetime, DTO

Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class ReviewRequest(DTO):
    validation_run_id: UUID
    content_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    decision: Literal['approved', 'rejected']
    comment: Reason
    sample_refs: list[UUID] = Field(min_length=1, max_length=30)
    print_checked: StrictBool

    @model_validator(mode='after')
    def confirmations(self):
        if len(set(self.sample_refs)) != len(self.sample_refs):
            raise ValueError('样题不能重复')
        if self.decision == 'approved' and not self.print_checked:
            raise ValueError('通过前须人工检查打印样张')
        return self


class ReviewView(DTO):
    id: UUID
    validation_run_id: UUID
    content_hash: str
    decision: Literal['approved', 'rejected']
    comment: str
    sample_refs: list[UUID]
    print_checked: bool
    reviewed_at: BeijingDatetime


class RevisionApproval(DTO):
    content_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    reason: Reason


class PublishRequest(DTO):
    version_id: UUID
    validation_run_id: UUID
    review_id: UUID
    reason: Reason


class DisableRequest(DTO):
    reason: Reason


class CloneRequest(DTO):
    source_version_id: UUID


class ReleaseView(DTO):
    id: UUID
    template_id: UUID
    action: str
    epoch: int
    created_at: BeijingDatetime


class DependencyView(DTO):
    id: UUID
    kind: Literal['knowledge_revision', 'objective_revision']
    name: str
    description: str
    content_hash: str
    status: str
    lock_version: int


class ReleaseContext(DTO):
    template_id: UUID
    template_lock_version: int
    template_status: str
    current_published_version_id: UUID | None
    dependencies: list[DependencyView]
    reviews: list[ReviewView]
