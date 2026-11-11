from uuid import UUID
from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.auth.dependencies import current_admin
from app.api.admin.releases import credentials, expected
from app.models.content import ContentSource, KnowledgePoint, KnowledgeRevision, TrainingObjective, ObjectiveRevision
from app.schemas.common import Envelope
from app.schemas.knowledge_edit import (SourceEdit, SourceView, SourceList, KnowledgeCreate, ObjectiveCreate,
    KnowledgeEdit, ObjectiveEdit, CopyRevision, KnowledgeView, ObjectiveView, KnowledgeDetail,
    ObjectiveDetail, KnowledgeList, ObjectiveList)
from app.services.capabilities import get
from app.services import knowledge_edit as service

router = APIRouter(prefix='/admin/api/v1', tags=['admin-knowledge'], dependencies=[Depends(current_admin)])


@router.get('/sources', response_model=Envelope[SourceList])
def sources(request: Request, offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100)):
    with Session(request.app.state.engine) as session:
        total = session.scalar(select(func.count()).select_from(ContentSource))
        rows = session.scalars(select(ContentSource).order_by(ContentSource.title, ContentSource.id).offset(offset).limit(limit))
        data = SourceList(items=[SourceView.model_validate(r, from_attributes=True) for r in rows], total=total, offset=offset, limit=limit)
    return Envelope(data=data, request_id=request.state.request_id)


@router.get('/sources/{identity}', response_model=Envelope[SourceView])
def source(identity: UUID, request: Request):
    with Session(request.app.state.engine) as session:
        data = SourceView.model_validate(get(session, ContentSource, identity), from_attributes=True)
    return Envelope(data=data, request_id=request.state.request_id)


@router.post('/sources', response_model=Envelope[SourceView], status_code=201)
def source_create(body: SourceEdit, request: Request):
    return Envelope(data=service.save_source(request.app.state.engine, None, body, **credentials(request)), request_id=request.state.request_id)


@router.patch('/sources/{identity}', response_model=Envelope[SourceView])
def source_edit(identity: UUID, body: SourceEdit, request: Request, if_match: str | None = Header(default=None)):
    return Envelope(data=service.save_source(request.app.state.engine, identity, body, expected(if_match), **credentials(request)), request_id=request.state.request_id)


@router.get('/knowledge-points', response_model=Envelope[KnowledgeList])
def points(request: Request, offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100)):
    with Session(request.app.state.engine) as session:
        total = session.scalar(select(func.count()).select_from(KnowledgePoint))
        rows = session.scalars(select(KnowledgePoint).order_by(KnowledgePoint.code, KnowledgePoint.id).offset(offset).limit(limit))
        data = KnowledgeList(items=[service.detail(session, r) for r in rows], total=total, offset=offset, limit=limit)
    return Envelope(data=data, request_id=request.state.request_id)


@router.get('/knowledge-points/{identity}', response_model=Envelope[KnowledgeDetail])
def point(identity: UUID, request: Request):
    with Session(request.app.state.engine) as session:
        data = service.detail(session, get(session, KnowledgePoint, identity))
    return Envelope(data=data, request_id=request.state.request_id)


@router.post('/knowledge-points', response_model=Envelope[KnowledgeDetail], status_code=201)
def point_create(body: KnowledgeCreate, request: Request):
    return Envelope(data=service.create(request.app.state.engine, KnowledgePoint, body, **credentials(request)), request_id=request.state.request_id)


@router.post('/knowledge-points/{identity}/revisions', response_model=Envelope[KnowledgeDetail], status_code=201)
def point_copy(identity: UUID, body: CopyRevision, request: Request, if_match: str | None = Header(default=None)):
    return Envelope(data=service.copy_revision(request.app.state.engine, KnowledgePoint, identity, body, expected(if_match), **credentials(request)), request_id=request.state.request_id)


@router.get('/knowledge-revisions/{identity}', response_model=Envelope[KnowledgeView])
def knowledge_revision(identity: UUID, request: Request):
    with Session(request.app.state.engine) as session:
        data = service.revision_view(get(session, KnowledgeRevision, identity))
    return Envelope(data=data, request_id=request.state.request_id)


@router.patch('/knowledge-revisions/{identity}', response_model=Envelope[KnowledgeView])
def knowledge_edit(identity: UUID, body: KnowledgeEdit, request: Request, if_match: str | None = Header(default=None)):
    return Envelope(data=service.edit_revision(request.app.state.engine, KnowledgeRevision, identity, body, expected(if_match), **credentials(request)), request_id=request.state.request_id)


@router.get('/knowledge-points/{identity}/objectives', response_model=Envelope[ObjectiveList])
def objectives(identity: UUID, request: Request, offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100)):
    with Session(request.app.state.engine) as session:
        point = get(session, KnowledgePoint, identity)
        query = select(TrainingObjective).where(TrainingObjective.point_id == point.id)
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        rows = session.scalars(query.order_by(TrainingObjective.code, TrainingObjective.id).offset(offset).limit(limit))
        data = ObjectiveList(items=[service.detail(session, r) for r in rows], total=total, offset=offset, limit=limit)
    return Envelope(data=data, request_id=request.state.request_id)


@router.post('/knowledge-points/{identity}/objectives', response_model=Envelope[ObjectiveDetail], status_code=201)
def objective_create(identity: UUID, body: ObjectiveCreate, request: Request):
    return Envelope(data=service.create(request.app.state.engine, TrainingObjective, body, point_id=identity, **credentials(request)), request_id=request.state.request_id)


@router.get('/objectives/{identity}', response_model=Envelope[ObjectiveDetail])
def objective(identity: UUID, request: Request):
    with Session(request.app.state.engine) as session:
        data = service.detail(session, get(session, TrainingObjective, identity))
    return Envelope(data=data, request_id=request.state.request_id)


@router.post('/objectives/{identity}/revisions', response_model=Envelope[ObjectiveDetail], status_code=201)
def objective_copy(identity: UUID, body: CopyRevision, request: Request, if_match: str | None = Header(default=None)):
    return Envelope(data=service.copy_revision(request.app.state.engine, TrainingObjective, identity, body, expected(if_match), **credentials(request)), request_id=request.state.request_id)


@router.get('/objective-revisions/{identity}', response_model=Envelope[ObjectiveView])
def objective_revision(identity: UUID, request: Request):
    with Session(request.app.state.engine) as session:
        data = service.revision_view(get(session, ObjectiveRevision, identity))
    return Envelope(data=data, request_id=request.state.request_id)


@router.patch('/objective-revisions/{identity}', response_model=Envelope[ObjectiveView])
def objective_edit(identity: UUID, body: ObjectiveEdit, request: Request, if_match: str | None = Header(default=None)):
    return Envelope(data=service.edit_revision(request.app.state.engine, ObjectiveRevision, identity, body, expected(if_match), **credentials(request)), request_id=request.state.request_id)
