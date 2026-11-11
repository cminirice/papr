from typing import Literal
from uuid import UUID
from pydantic import Field, StrictInt
from app.schemas.common import BeijingDatetime, DTO
from app.schemas.content import MultiplicationParams, MultiplicationQuestion


class ValidationRequest(DTO):
    lock_version: StrictInt = Field(ge=1)
    content_hash: str = Field(pattern=r'^[0-9a-f]{64}$')


class ProfileCoverage(DTO):
    difficulty: Literal['basic', 'standard', 'challenge']
    exact_capacity: int
    random_cases: int
    papers_per_count: int
    checked_count_options: list[int]


class FailureSample(DTO):
    difficulty: Literal['basic', 'standard', 'challenge']
    case_code: str | None = None
    seed: str | None = None
    params: MultiplicationParams | None = None
    error_code: str
    message: str


class ValidationReport(DTO):
    result: Literal['passed', 'failed']
    sample_count: int
    failure_count: int
    failures_truncated: bool
    coverage: list[ProfileCoverage]
    failures: list[FailureSample]
    samples: list[MultiplicationQuestion] = Field(default_factory=list, max_length=30)
    human_review: Literal['pending'] = 'pending'
    pdf_review: Literal['pending'] = 'pending'


class ValidationView(DTO):
    id: UUID
    job_id: UUID
    template_version_id: UUID
    content_hash: str
    status: Literal['queued', 'running', 'passed', 'failed', 'stale']
    job_status: Literal['queued', 'running', 'succeeded', 'failed', 'cancelled']
    attempt: int
    error_code: str | None
    created_at: BeijingDatetime
    finished_at: BeijingDatetime | None
    report: ValidationReport | None


class ValidationList(DTO):
    items: list[ValidationView]
