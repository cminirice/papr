from uuid import UUID
from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.auth.dependencies import current_admin
from app.api.admin.releases import credentials, expected
from app.models.content import ContentCatalog, CatalogNode, KnowledgePoint, KnowledgeRevision
from app.schemas.common import Envelope
from app.schemas.capabilities import NodeView
from app.schemas.catalog_edit import CatalogCreate, CatalogDetail, NodeCreate, MappingEdit, MappingView, RevisionOption, RevisionOptions
from app.services.capabilities import get
from app.services import catalog_edit as service

router = APIRouter(prefix='/admin/api/v1', tags=['admin-catalog-edit'], dependencies=[Depends(current_admin)])


@router.post('/catalogs', response_model=Envelope[CatalogDetail], status_code=201)
def create_catalog(body: CatalogCreate, request: Request):
    data = service.create(request.app.state.engine, ContentCatalog, body, **credentials(request))
    return Envelope(data=data, request_id=request.state.request_id)


@router.get('/catalogs/{identity}', response_model=Envelope[CatalogDetail])
def catalog(identity: UUID, request: Request):
    with Session(request.app.state.engine) as session:
        data = service.view(get(session, ContentCatalog, identity))
    return Envelope(data=data, request_id=request.state.request_id)


@router.post('/catalogs/{identity}/nodes', response_model=Envelope[NodeView], status_code=201)
def create_node(identity: UUID, body: NodeCreate, request: Request):
    data = service.create(request.app.state.engine, CatalogNode, body, catalog_id=identity, **credentials(request))
    return Envelope(data=data, request_id=request.state.request_id)


@router.get('/catalog-nodes/{identity}/knowledge-mappings', response_model=Envelope[MappingView])
def mappings(identity: UUID, request: Request):
    with Session(request.app.state.engine) as session:
        data = service.mappings(session, identity)
    return Envelope(data=data, request_id=request.state.request_id)


@router.put('/catalog-nodes/{identity}/knowledge-mappings', response_model=Envelope[MappingView])
def replace(identity: UUID, body: MappingEdit, request: Request, if_match: str | None = Header(default=None)):
    data = service.replace_mappings(request.app.state.engine, identity, body, expected(if_match), **credentials(request))
    return Envelope(data=data, request_id=request.state.request_id)


@router.get('/knowledge-revision-options', response_model=Envelope[RevisionOptions])
def revision_options(request: Request, offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=100)):
    with Session(request.app.state.engine) as session:
        total = session.scalar(select(func.count()).select_from(KnowledgeRevision))
        rows = session.execute(select(KnowledgeRevision, KnowledgePoint.code).join(KnowledgePoint,
            KnowledgePoint.id == KnowledgeRevision.point_id).order_by(KnowledgePoint.code, KnowledgeRevision.revision_no.desc())
            .offset(offset).limit(limit))
        data = RevisionOptions(items=[RevisionOption(id=r.id, point_id=r.point_id, code=code, name=r.name,
            revision_no=r.revision_no, status=r.status) for r, code in rows], total=total, offset=offset, limit=limit)
    return Envelope(data=data, request_id=request.state.request_id)
