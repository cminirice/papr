from fastapi import APIRouter, Depends, Request, Response
from app.auth.http import USER_COOKIE, clock, identity_service, put_cookie, rate_subject, user_write
from app.schemas.common import Envelope
from app.schemas.identity import EmptyRequest, UserSessionView, UserSessionCreated, CsrfToken

router = APIRouter(prefix="/api/v1/session", tags=["user-session"])


@router.post("", response_model=Envelope[UserSessionCreated], dependencies=[Depends(user_write)])
def bootstrap(body: EmptyRequest, request: Request, response: Response):
    now = clock(request)
    data, token = identity_service(request).bootstrap(request.cookies.get(USER_COOKIE), rate_subject(request), now)
    put_cookie(response, request, token, data.expires_at, now)
    return Envelope(data=data, request_id=request.state.request_id)


@router.get("", response_model=Envelope[UserSessionView])
def current(request: Request, response: Response):
    now = clock(request)
    token = request.cookies.get(USER_COOKIE)
    data, renewed = identity_service(request).read_user(token, now)
    if renewed:
        put_cookie(response, request, token, data.expires_at, now)
    return Envelope(data=data, request_id=request.state.request_id)


@router.post("/csrf", response_model=Envelope[CsrfToken], dependencies=[Depends(user_write)])
def csrf(body: EmptyRequest, request: Request, response: Response):
    now = clock(request)
    token = request.cookies.get(USER_COOKIE)
    value, renewed, expires = identity_service(request).rotate_user_csrf(token, rate_subject(request), now)
    if renewed:
        put_cookie(response, request, token, expires, now)
    return Envelope(data=CsrfToken(csrf_token=value), request_id=request.state.request_id)
