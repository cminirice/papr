from datetime import date
from typing import Literal
from uuid import UUID
from app.schemas.events import UsageCounts
from app.schemas.common import DTO, BeijingDatetime
from app.schemas.content import MultiplicationQuestion
from app.schemas.generation import Difficulty, JobPhase
from app.schemas.validation import ValidationView

JobKind = Literal['paper_generate', 'template_validate', 'template_preview']
JobStatus = Literal['queued', 'running', 'succeeded', 'failed', 'cancelled']


class AdminJobSummary(DTO):
    id: UUID
    kind: JobKind
    status: JobStatus
    phase: JobPhase
    attempt: int
    max_attempts: int
    created_at: BeijingDatetime
    started_at: BeijingDatetime | None
    finished_at: BeijingDatetime | None
    error_code: str | None
    error_message: str | None
    template_id: UUID | None
    template_name: str | None
    template_version_id: UUID | None
    version_no: int | None
    validation_run_id: UUID | None
    validation_status: Literal['queued', 'running', 'passed', 'failed', 'stale'] | None
    paper_id: UUID | None
    paper_status: Literal['active', 'withdrawn'] | None
    difficulty: Difficulty | None
    total_count: int | None
    theme_name: str | None


class AdminJobList(DTO):
    date_from: date
    date_to: date
    items: list[AdminJobSummary]
    next_cursor: str | None
    has_more: bool


class AdminJobDetail(DTO):
    job: AdminJobSummary
    questions: list[MultiplicationQuestion]
    validation: ValidationView | None


class GenerationCounts(DTO):
    submitted: int = 0
    succeeded: int = 0
    failed: int = 0
    cancelled: int = 0
    active_subjects: int = 0


class DailyGenerationCounts(GenerationCounts):
    date: date


class QueueCounts(DTO):
    queued: int = 0
    running: int = 0


class AdminOverview(DTO):
    usage: UsageCounts = UsageCounts()
    date_from: date
    date_to: date
    as_of: BeijingDatetime
    totals: GenerationCounts
    daily: list[DailyGenerationCounts]
    generation_queue: QueueCounts
    validation_queue: QueueCounts
