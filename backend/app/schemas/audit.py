from datetime import date
from uuid import UUID
from app.schemas.common import DTO, BeijingDatetime


class OperationView(DTO):
    id: UUID
    admin_id: UUID
    action: str
    target_type: str
    target_id: str
    request_id: UUID
    before_summary: dict | list | None
    after_summary: dict | list | None
    reason: str | None
    created_at: BeijingDatetime


class OperationList(DTO):
    date_from: date
    date_to: date
    items: list[OperationView]
    next_cursor: str | None
    has_more: bool
