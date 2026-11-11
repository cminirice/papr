from datetime import datetime, timezone
from math import ceil
from fastapi import Request, Response
from app.auth.security import ip_subject, load_rate_key
from app.core.errors import ServiceError
from app.core.time import to_beijing
from app.services.identity.sessions import IdentityService

USER_COOKIE = "papr_user_session"
ADMIN_COOKIE = "papr_admin_session"
USER_PATH = "/api/v1/"
ADMIN_PATH = "/admin/api/v1/"


def enforce_write(request: Request, *, admin: bool) -> None:
    settings = request.app.state.settings
    allowed = settings.admin_origins if admin else settings.user_origins
    origins = request.headers.getlist("origin")
    if len(origins) != 1 or origins[0] not in allowed:
        raise ServiceError(403, "ORIGIN_INVALID", "请求来源不受信任")
    types = request.headers.getlist("content-type")
    if len(types) != 1 or types[0].split(";", 1)[0].strip().lower() != "application/json":
        raise ServiceError(415, "INVALID_CONFIG", "请求必须使用application/json")


def user_write(request: Request) -> None:
    enforce_write(request, admin=False)


def admin_write(request: Request) -> None:
    enforce_write(request, admin=True)


def clock(request: Request) -> datetime:
    return to_beijing(request.app.state.clock())


def identity_service(request: Request) -> IdentityService:
    return IdentityService(request.app.state.engine, request.app.state.settings.identity_limit)


def rate_subject(request: Request) -> str:
    # 不读取客户端提交的X-Forwarded-For；一期启动禁用代理头重写。
    key = load_rate_key(request.app.state.settings.rate_limit_key_path)
    return ip_subject(request.client.host if request.client else "", key)


def put_cookie(response: Response, request: Request, token: str, expires: datetime, now: datetime, *, admin: bool = False):
    response.set_cookie(
        ADMIN_COOKIE if admin else USER_COOKIE, token,
        max_age=max(0, ceil((expires - now).total_seconds())),
        expires=expires.astimezone(timezone.utc),
        path=ADMIN_PATH if admin else USER_PATH,
        httponly=True, secure=request.app.state.settings.cookie_secure, samesite="lax",
    )

    put_v2_cookie(response,request,token,expires,now,admin=admin)


def put_v2_cookie(response,request,token,expires,now,*,admin=False):
    response.set_cookie(
        (ADMIN_COOKIE if admin else USER_COOKIE)+"_v2",token,
        max_age=max(0,ceil((expires-now).total_seconds())),expires=expires.astimezone(timezone.utc),
        path="/admin/api/v2/" if admin else "/api/v2/",httponly=True,
        secure=request.app.state.settings.cookie_secure,samesite="lax",
    )
