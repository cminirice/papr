from uuid import UUID
from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.auth.dependencies import current_admin
from app.api.admin.releases import credentials
from app.core.errors import ServiceError
from app.models.jobs import Job
from app.schemas.common import Envelope
from app.schemas.template_edit import DraftDetail
from app.schemas.template_tools import TemplateCreate, GeneratorChoice, PreviewRequest, PreviewView, PreviewList
from app.services.template_edit import find_version
from app.services import template_tools, preview_jobs

router = APIRouter(prefix='/admin/api/v1', tags=['admin-template-tools'], dependencies=[Depends(current_admin)])


@router.get('/generators', response_model=Envelope[list[GeneratorChoice]])
def generators(request: Request):
    with Session(request.app.state.engine) as session:
        data = template_tools.choices(session)
    return Envelope(data=data, request_id=request.state.request_id)


@router.post('/templates', response_model=Envelope[DraftDetail], status_code=201)
def create(body: TemplateCreate, request: Request):
    data = template_tools.create(request.app.state.engine, body, **credentials(request))
    return Envelope(data=data, request_id=request.state.request_id)


@router.post('/template-versions/{identity}/preview-jobs', response_model=Envelope[PreviewView], status_code=202)
def preview(identity: UUID, body: PreviewRequest, request: Request, idempotency_key: UUID = Header()):
    data = preview_jobs.acceptance(request.app.state.engine, identity, body, idempotency_key, **credentials(request))
    return Envelope(data=data, request_id=request.state.request_id)


@router.get('/template-versions/{identity}/preview-jobs', response_model=Envelope[PreviewList])
def previews(identity: UUID, request: Request):
    with Session(request.app.state.engine) as session:
        find_version(session, identity)
        rows = session.scalars(select(Job).where(Job.kind == 'template_preview',
            Job.payload.op('->>')('$.template_version_id') == str(identity)).order_by(Job.created_at.desc(), Job.id.desc()).limit(20))
        data = PreviewList(items=[preview_jobs.view(session, job) for job in rows])
    return Envelope(data=data, request_id=request.state.request_id)


@router.get('/preview-jobs/{identity}', response_model=Envelope[PreviewView])
def result(identity: UUID, request: Request):
    with Session(request.app.state.engine) as session:
        job = session.get(Job, str(identity))
        if job is None or job.kind != 'template_preview':
            raise ServiceError(404, 'NOT_FOUND', '预览任务不存在')
        data = preview_jobs.view(session, job)
    return Envelope(data=data, request_id=request.state.request_id)
