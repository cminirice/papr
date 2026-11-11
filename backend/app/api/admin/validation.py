from uuid import UUID
from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.auth.dependencies import current_admin
from app.auth.http import ADMIN_COOKIE, clock
from app.core.errors import ServiceError
from app.models.validation import ValidationRun
from app.schemas.common import Envelope
from app.schemas.validation import ValidationList, ValidationRequest, ValidationView
from app.services.validation_jobs import acceptance, view
from app.services.template_edit import find_version

router = APIRouter(prefix='/admin/api/v1', tags=['admin-validation'], dependencies=[Depends(current_admin)])


@router.post('/template-versions/{identity}/validation-jobs', status_code=202, response_model=Envelope[ValidationView])
def submit(identity: UUID, body: ValidationRequest, request: Request, response: Response,
           idempotency_key: UUID = Header()):
    data = acceptance(request.app.state.engine, identity, body, idempotency_key,
                      request.cookies.get(ADMIN_COOKIE), request.headers.get('X-CSRF-Token'), clock(request))
    response.headers['Cache-Control'] = 'no-store'
    return Envelope(data=data, request_id=request.state.request_id)


@router.get('/template-versions/{identity}/validation-runs', response_model=Envelope[ValidationList])
def history(identity: UUID, request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    with Session(request.app.state.engine) as session:
        find_version(session, identity)
        runs = session.scalars(select(ValidationRun).where(ValidationRun.template_version_id == str(identity))
                               .order_by(ValidationRun.created_at.desc(), ValidationRun.id.desc()).limit(20)).all()
        data = ValidationList(items=[view(session, run) for run in runs])
    return Envelope(data=data, request_id=request.state.request_id)


@router.get('/validation-runs/{identity}', response_model=Envelope[ValidationView])
def report(identity: UUID, request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    with Session(request.app.state.engine) as session:
        run = session.get(ValidationRun, str(identity))
        if run is None:
            raise ServiceError(404, 'NOT_FOUND', '验证报告不存在')
        data = view(session, run)
    return Envelope(data=data, request_id=request.state.request_id)
