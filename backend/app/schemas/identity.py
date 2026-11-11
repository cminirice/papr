from uuid import UUID
from pydantic import Field, SecretStr
from app.schemas.common import DTO, BeijingDatetime


class EmptyRequest(DTO):
    pass


class UserSessionView(DTO):
    user_id: UUID
    expires_at: BeijingDatetime
    server_now: BeijingDatetime
    next_generation_at: BeijingDatetime | None
    active_job_id: UUID | None
    can_generate: bool


class UserSessionCreated(UserSessionView):
    csrf_token: str


class CsrfToken(DTO):
    csrf_token: str


class AdminLogin(DTO):
    username: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: SecretStr = Field(min_length=1, max_length=128)


class AdminSessionView(DTO):
    admin_id: UUID
    expires_at: BeijingDatetime
    server_now: BeijingDatetime


class AdminSessionCreated(AdminSessionView):
    csrf_token: str
