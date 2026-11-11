from typing import Annotated, Generic, TypeVar
from uuid import UUID
from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, PlainSerializer
from app.core.time import serialize_time, to_beijing
from app.core.errors import ErrorCode

BeijingDatetime = Annotated[
    AwareDatetime,
    AfterValidator(to_beijing),
    PlainSerializer(serialize_time, return_type=str, when_used="json"),
]


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


T = TypeVar("T")


class Envelope(DTO, Generic[T]):
    data: T
    request_id: UUID


class Health(DTO):
    status: str = "ok"
    server_now: BeijingDatetime


class ErrorDetail(DTO):
    code: ErrorCode
    message: str
    details: dict[str, object]


class ErrorResponse(DTO):
    error: ErrorDetail
    request_id: UUID
