from fastapi import APIRouter, Depends, Request, Response
from app.auth.http import ADMIN_COOKIE, ADMIN_PATH, admin_write, clock, identity_service, put_cookie, put_v2_cookie, rate_subject
from app.schemas.common import Envelope
from app.schemas.identity import EmptyRequest, AdminLogin, AdminSessionView, AdminSessionCreated, CsrfToken

router = APIRouter(prefix="/admin/api/v1/session", tags=["admin-session"])


@router.post("/login", response_model=Envelope[AdminSessionCreated], dependencies=[Depends(admin_write)])
def login(body: AdminLogin, request: Request, response: Response):
    now = clock(request)
    data, token = identity_service(request).login(body.username, body.password.get_secret_value(), rate_subject(request), now)
    put_cookie(response, request, token, data.expires_at, now, admin=True)
    return Envelope(data=data, request_id=request.state.request_id)


@router.get("", response_model=Envelope[AdminSessionView])
def current(request: Request, response: Response):
    data = identity_service(request).read_admin(request.cookies.get(ADMIN_COOKIE), clock(request))
    return Envelope(data=data, request_id=request.state.request_id)


@router.post("/csrf", response_model=Envelope[CsrfToken], dependencies=[Depends(admin_write)])
def csrf(body: EmptyRequest, request: Request, response: Response):
    value = identity_service(request).rotate_admin_csrf(request.cookies.get(ADMIN_COOKIE), rate_subject(request), clock(request))
    current = identity_service(request).read_admin(request.cookies.get(ADMIN_COOKIE), clock(request))
    put_v2_cookie(response, request, request.cookies.get(ADMIN_COOKIE), current.expires_at, clock(request), admin=True)
    return Envelope(data=CsrfToken(csrf_token=value), request_id=request.state.request_id)


@router.post("/logout", status_code=204, dependencies=[Depends(admin_write)])
def logout(body: EmptyRequest, request: Request):
    identity_service(request).logout(request.cookies.get(ADMIN_COOKIE), request.headers.get("X-CSRF-Token"), clock(request))
    response = Response(status_code=204)
    response.delete_cookie(ADMIN_COOKIE, path=ADMIN_PATH, httponly=True, secure=request.app.state.settings.cookie_secure, samesite="lax")
    response.delete_cookie(ADMIN_COOKIE+"_v2", path="/admin/api/v2/", httponly=True, secure=request.app.state.settings.cookie_secure, samesite="lax")
    return response
