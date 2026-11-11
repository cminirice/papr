from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_CONFIG = "INVALID_CONFIG"
    NOT_FOUND = "NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    CSRF_INVALID = "CSRF_INVALID"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    CAPABILITY_CHANGED = "CAPABILITY_CHANGED"
    EDIT_CONFLICT = "EDIT_CONFLICT"
    ACTIVE_JOB_EXISTS = "ACTIVE_JOB_EXISTS"
    CONTENT_UNAVAILABLE = "CONTENT_UNAVAILABLE"
    UNSUPPORTED_COMBINATION = "UNSUPPORTED_COMBINATION"
    GENERATION_COOLDOWN = "GENERATION_COOLDOWN"
    RATE_LIMITED = "RATE_LIMITED"
    QUEUE_FULL = "QUEUE_FULL"
    DATABASE_BUSY = "DATABASE_BUSY"
    GENERATION_EXHAUSTED = "GENERATION_EXHAUSTED"
    ENGINE_TIMEOUT = "ENGINE_TIMEOUT"
    WORKER_LOST = "WORKER_LOST"
    JOB_NOT_CANCELLABLE = "JOB_NOT_CANCELLABLE"
    FILE_UNAVAILABLE = "FILE_UNAVAILABLE"
    LOGIN_FAILED = "LOGIN_FAILED"
    ORIGIN_INVALID = "ORIGIN_INVALID"
    SERVICE_NOT_READY = "SERVICE_NOT_READY"


class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str, *, details: dict | None = None, headers: dict[str, str] | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}
        self.headers = headers or {}
