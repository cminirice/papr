import re
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.orm import Session
from app.auth.dependencies import current_admin
from app.auth.http import ADMIN_COOKIE, clock
from app.core.errors import ServiceError
from app.schemas.common import Envelope
from app.schemas.releases import (DisableRequest, PublishRequest, ReleaseContext, ReleaseView,
    ReviewRequest, ReviewView, RevisionApproval, CloneRequest)
from app.schemas.template_edit import DraftDetail
from app.services.releases import add_review, context, publish_revision, release, clone_version
from app.services.template_edit import find_version

router = APIRouter(prefix='/admin/api/v1', tags=['admin-release'], dependencies=[Depends(current_admin)])


def expected(value):
    if value is None or re.fullmatch(r'"[1-9][0-9]{0,9}"', value) is None:
        raise ServiceError(422, 'INVALID_CONFIG', '须携带带引号的If-Match版本号')
    return int(value[1:-1])


def credentials(request):
    return dict(token=request.cookies.get(ADMIN_COOKIE), csrf=request.headers.get('X-CSRF-Token'),
                now=clock(request), request_id=request.state.request_id)


@router.get('/template-versions/{identity}/release-context', response_model=Envelope[ReleaseContext])
def release_context(identity: UUID, request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    with Session(request.app.state.engine) as session:
        data = context(session, find_version(session, identity))
    return Envelope(data=data, request_id=request.state.request_id)


@router.post('/template-versions/{identity}/reviews', response_model=Envelope[ReviewView])
def review(identity: UUID, body: ReviewRequest, request: Request, if_match: str | None = Header(default=None)):
    data = add_review(request.app.state.engine, identity, body, expected(if_match), **credentials(request))
    return Envelope(data=data, request_id=request.state.request_id)


@router.post('/knowledge-revisions/{identity}/publish', status_code=204)
def publish_knowledge(identity: UUID, body: RevisionApproval, request: Request, if_match: str | None = Header(default=None)):
    publish_revision(request.app.state.engine, 'knowledge_revision', identity, body, expected(if_match), **credentials(request))
    return Response(status_code=204, headers={'Cache-Control': 'no-store'})


@router.post('/objective-revisions/{identity}/publish', status_code=204)
def publish_objective(identity: UUID, body: RevisionApproval, request: Request, if_match: str | None = Header(default=None)):
    publish_revision(request.app.state.engine, 'objective_revision', identity, body, expected(if_match), **credentials(request))
    return Response(status_code=204, headers={'Cache-Control': 'no-store'})


def change(action, identity, body, request, if_match):
    data = release(request.app.state.engine, identity, body, expected(if_match), action, **credentials(request))
    return Envelope(data=data, request_id=request.state.request_id)


@router.post('/templates/{identity}/publish', response_model=Envelope[ReleaseView])
def publish(identity: UUID, body: PublishRequest, request: Request, if_match: str | None = Header(default=None)):
    return change('publish', identity, body, request, if_match)


@router.post('/templates/{identity}/disable', response_model=Envelope[ReleaseView])
def disable(identity: UUID, body: DisableRequest, request: Request, if_match: str | None = Header(default=None)):
    return change('disable', identity, body, request, if_match)


@router.post('/templates/{identity}/enable', response_model=Envelope[ReleaseView])
def enable(identity: UUID, body: PublishRequest, request: Request, if_match: str | None = Header(default=None)):
    return change('enable', identity, body, request, if_match)


@router.post('/templates/{identity}/rollback', response_model=Envelope[ReleaseView])
def rollback(identity: UUID, body: PublishRequest, request: Request, if_match: str | None = Header(default=None)):
    return change('rollback', identity, body, request, if_match)


@router.post('/templates/{identity}/versions', response_model=Envelope[DraftDetail])
def clone(identity: UUID, body: CloneRequest, request: Request, if_match: str | None = Header(default=None)):
    data = clone_version(request.app.state.engine, identity, body.source_version_id, expected(if_match), **credentials(request))
    return Envelope(data=data, request_id=request.state.request_id)
