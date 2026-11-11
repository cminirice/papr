from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy.orm import Session
from app.auth.dependencies import Principal, current_user
from app.auth.http import USER_COOKIE, clock, rate_subject
from app.schemas.common import Envelope
from app.schemas.generation import CreatePaperJob
from app.schemas.identity import EmptyRequest
from app.schemas.paper_jobs import PaperJobView, PaperJobList
from app.services import paper_jobs

router = APIRouter(prefix='/api/v1', tags=['paper-jobs'])


@router.post('/paper-jobs', response_model=Envelope[PaperJobView], status_code=202)
def create(body: CreatePaperJob, request: Request, response: Response,
           idempotency_key: UUID = Header(), principal: Principal = Depends(current_user)):
    data = paper_jobs.accept(request.app.state.engine, body, idempotency_key,
        request.cookies.get(USER_COOKIE), request.headers.get('X-CSRF-Token'), rate_subject(request), clock(request), request.app.state.settings)
    if data.status not in ('queued', 'running'):
        response.status_code = 200
    return Envelope(data=data, request_id=request.state.request_id)


@router.get('/jobs', response_model=Envelope[PaperJobList])
def jobs(request: Request, principal: Principal = Depends(current_user),
         cursor: str | None = Query(default=None, max_length=256), limit: int = Query(default=20, ge=1, le=100),
         status: Literal['queued', 'running', 'succeeded', 'failed', 'cancelled'] | None = None):
    with Session(request.app.state.engine) as session:
        data = paper_jobs.listing(session, principal.owner_id, cursor, limit, status)
    return Envelope(data=data, request_id=request.state.request_id)


@router.get('/jobs/{identity}', response_model=Envelope[PaperJobView])
def job(identity: UUID, request: Request, principal: Principal = Depends(current_user)):
    with Session(request.app.state.engine) as session:
        data = paper_jobs.view(paper_jobs.owned(session, identity, principal.owner_id))
    return Envelope(data=data, request_id=request.state.request_id)


@router.post('/jobs/{identity}/cancel', response_model=Envelope[PaperJobView])
def cancel(identity: UUID, body: EmptyRequest, request: Request, principal: Principal = Depends(current_user)):
    data = paper_jobs.cancel(request.app.state.engine, identity, request.cookies.get(USER_COOKIE),
                            request.headers.get('X-CSRF-Token'), clock(request))
    return Envelope(data=data, request_id=request.state.request_id)
