from uuid import UUID
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.auth.dependencies import current_user
from app.core.errors import ServiceError
from app.models.content import ContentCatalog, CatalogNode
from app.schemas.catalog import CatalogSummary
from app.schemas.common import Envelope
from app.schemas.capabilities import NodeView, PointView, CapabilitySelection, CapabilityView
from app.services.capabilities import get, public_node, linked_points, capabilities

router = APIRouter(prefix='/api/v1', tags=['catalog'])


@router.get('/catalogs', response_model=Envelope[list[CatalogSummary]])
def catalogs(request: Request):
    with Session(request.app.state.engine) as session:
        data = [CatalogSummary.model_validate(row, from_attributes=True) for row in session.scalars(
            select(ContentCatalog).where(ContentCatalog.status == 'active', ContentCatalog.subject == 'math',
                ContentCatalog.grade == 4).order_by(ContentCatalog.code))]
    return Envelope(data=data, request_id=request.state.request_id)


@router.get('/catalogs/{identity}/themes', response_model=Envelope[list[NodeView]])
def themes(identity: UUID, request: Request):
    with Session(request.app.state.engine) as session:
        catalog = get(session, ContentCatalog, identity)
        if catalog.status != 'active' or catalog.grade != 4 or catalog.subject != 'math':
            raise ServiceError(404, 'NOT_FOUND', '目录未开放')
        data = []
        for node in session.scalars(select(CatalogNode).where(CatalogNode.catalog_id == catalog.id,
            CatalogNode.node_type == 'theme', CatalogNode.status == 'active').order_by(CatalogNode.sort_order, CatalogNode.code)):
            try:
                public_node(session, node.id)
            except ServiceError:
                continue
            data.append(NodeView.model_validate(node, from_attributes=True))
    return Envelope(data=data, request_id=request.state.request_id)


@router.get('/themes/{identity}/knowledge-points', response_model=Envelope[list[PointView]])
def points(identity: UUID, request: Request):
    with Session(request.app.state.engine) as session:
        node = public_node(session, identity)
        if node.node_type != 'theme':
            raise ServiceError(404, 'NOT_FOUND', '主题不存在')
        data = linked_points(session, identity, public=True)
    return Envelope(data=data, request_id=request.state.request_id)


@router.post('/capabilities', response_model=Envelope[CapabilityView], dependencies=[Depends(current_user)])
def selection(body: CapabilitySelection, request: Request):
    with Session(request.app.state.engine) as session:
        data = capabilities(session, body)
    return Envelope(data=data, request_id=request.state.request_id)
