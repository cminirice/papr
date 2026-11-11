from typing import Literal
from uuid import UUID
from pydantic import Field
from app.schemas.common import DTO, BeijingDatetime


class EventPayload(DTO):
    answer_mode: Literal['student','solution']


class EventInput(DTO):
    event_id: UUID
    type: Literal['preview','print_intent']
    paper_id: UUID
    occurred_at: BeijingDatetime | None = None
    payload: EventPayload


class EventBatch(DTO):
    # Validate each item separately so a malformed event does not reject valid peers.
    events: list[dict[str,object]] = Field(min_length=1,max_length=20)


class EventRejection(DTO):
    event_id: str | None
    code: Literal['INVALID_CONFIG','NOT_FOUND','EVENT_CONFLICT']


class EventResult(DTO):
    accepted_ids: list[UUID]
    duplicate_ids: list[UUID]
    rejected: list[EventRejection]


class UsageCounts(DTO):
    preview: int = 0
    print_intent: int = 0
