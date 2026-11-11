"""后续模块统一复用的HTTP鉴权依赖；提交业务事务时仍须重验会话/主体。"""
from dataclasses import dataclass
from fastapi import Request, Response
from app.auth.http import ADMIN_COOKIE, USER_COOKIE, clock, enforce_write, put_cookie
from app.auth.security import check_csrf
from app.core.database import write_transaction
from app.services.identity.sessions import require_admin, require_user, touch_user


@dataclass(frozen=True)
class Principal:
    owner_id: str
    session_id: str


def current_user(request: Request, response: Response) -> Principal:
    now = clock(request)
    token = request.cookies.get(USER_COOKIE + ("_v2" if request.url.path.startswith("/api/v2/") else ""))
    writing = request.method not in {'GET', 'HEAD', 'OPTIONS'}
    if writing:
        enforce_write(request, admin=False)
    with write_transaction(request.app.state.engine) as session:
        user, stored = require_user(session, token, now)
        if writing:
            check_csrf(request.headers.get('X-CSRF-Token'), stored.csrf_hash)
        renewed = touch_user(user, stored, now)
        result = Principal(user.id, stored.id)
        expires = stored.expires_at
    if renewed:
        put_cookie(response, request, token, expires, now)
    return result


def current_admin(request: Request) -> Principal:
    now = clock(request)
    writing = request.method not in {'GET', 'HEAD', 'OPTIONS'}
    if writing:
        enforce_write(request, admin=True)
    with write_transaction(request.app.state.engine) as session:
        admin, stored = require_admin(session, request.cookies.get(ADMIN_COOKIE + ("_v2" if request.url.path.startswith("/admin/api/v2/") else "")), now)
        if writing:
            check_csrf(request.headers.get('X-CSRF-Token'), stored.csrf_hash)
        stored.last_seen_at = stored.updated_at = now
        return Principal(admin.id, stored.id)
