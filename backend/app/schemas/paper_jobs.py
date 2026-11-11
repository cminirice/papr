from typing import Literal
from uuid import UUID
from pydantic import Field
from app.schemas.common import DTO, BeijingDatetime
from app.schemas.content import MultiplicationProfile
from app.schemas.generation import CreatePaperJob, JobPhase


class PaperPart(DTO):
    """Internal immutable input: never accepted from a browser or returned as job status."""
    schema_version: Literal[1] = 1
    request: CreatePaperJob
    seed: str = Field(pattern=r'^[0-9a-f]{32}$')
    template_version_id: UUID
    content_hash: str
    profile_id: UUID
    profile_hash: str
    profile: MultiplicationProfile
    generator_id: UUID
    generator_artifact_hash: str
    validation_run_id: UUID
    review_id: UUID
    knowledge_revision_id: UUID
    objective_revision_id: UUID
    fixed: dict[str, object]
    catalog_snapshot: dict[str, str]


class PaperPlan(PaperPart):
    parts: list[PaperPart] = Field(default_factory=list, max_length=30)

    def allocations(self):
        return self.parts or [self]


class PaperJobView(DTO):
    id: UUID
    status: Literal['queued', 'running', 'succeeded', 'failed', 'cancelled']
    phase: JobPhase
    attempt: int
    progress_done: int
    progress_total: int
    created_at: BeijingDatetime
    finished_at: BeijingDatetime | None
    error_code: str | None
    error_message: str | None
    paper_id: UUID | None


class PaperJobList(DTO):
    items: list[PaperJobView]
    next_cursor: str | None
    has_more: bool
