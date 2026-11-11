from uuid import UUID
from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.auth.dependencies import current_admin
from app.api.admin.releases import credentials, expected
from app.models.content import ContentCatalog, CatalogNode
from app.schemas.common import Envelope
from app.schemas.capabilities import CatalogState, NodeState, NodeView, PointView, PointCapabilities, PolicyEdit
from app.services.capabilities import get, linked_points, point_capabilities, save_policies, change_state
from app.schemas.catalog_edit import CatalogEdit, NodeEdit
from app.services.catalog_edit import edit

router = APIRouter(prefix='/admin/api/v1', tags=['admin-capabilities'], dependencies=[Depends(current_admin)])


@router.get('/catalogs/{identity}/nodes', response_model=Envelope[list[NodeView]])
def nodes(identity: UUID, request: Request):
    with Session(request.app.state.engine) as session:
        get(session, ContentCatalog, identity)
        data = [NodeView.model_validate(n, from_attributes=True) for n in session.scalars(select(CatalogNode)
            .where(CatalogNode.catalog_id == str(identity)).order_by(CatalogNode.sort_order, CatalogNode.code))]
    return Envelope(data=data, request_id=request.state.request_id)


@router.get('/catalog-nodes/{identity}/knowledge-points', response_model=Envelope[list[PointView]])
def points(identity: UUID, request: Request):
    with Session(request.app.state.engine) as session:
        data = linked_points(session, identity)
    return Envelope(data=data, request_id=request.state.request_id)


@router.get('/knowledge-points/{identity}/capabilities', response_model=Envelope[PointCapabilities])
def matrix(identity: UUID, request: Request):
    with Session(request.app.state.engine) as session:
        data = point_capabilities(session, identity)
    return Envelope(data=data, request_id=request.state.request_id)


@router.put('/knowledge-points/{identity}/quantity-policies', response_model=Envelope[PointCapabilities])
def policies(identity: UUID, body: PolicyEdit, request: Request, if_match: str | None = Header(default=None)):
    data = save_policies(request.app.state.engine, identity, body, expected(if_match), **credentials(request))
    return Envelope(data=data, request_id=request.state.request_id)


@router.patch('/catalogs/{identity}', status_code=204)
def catalog_state(identity: UUID, body: CatalogEdit, request: Request, if_match: str | None = Header(default=None)):
    edit(request.app.state.engine, ContentCatalog, identity, body, expected(if_match), **credentials(request))
    return Response(status_code=204)


@router.patch('/catalog-nodes/{identity}', status_code=204)
def node_state(identity: UUID, body: NodeEdit, request: Request, if_match: str | None = Header(default=None)):
    edit(request.app.state.engine, CatalogNode, identity, body, expected(if_match), **credentials(request))
    return Response(status_code=204)
