"""目录与模板只读入口；未实现发布前不向用户端暴露草稿能力。"""
import re
from uuid import UUID
from typing import Literal
from fastapi import APIRouter, Depends, Query, Request, Response, Header
from sqlalchemy import func, select, or_
from sqlalchemy.orm import Session

from app.auth.dependencies import current_admin
from app.models.content import ContentCatalog, QuestionTemplate, TemplateVersion
from app.schemas.catalog import CatalogList, CatalogSummary, TemplateList, TemplateSummary
from app.schemas.common import Envelope
from app.schemas.template_edit import DraftEdit, DraftDetail, TemplateDetail, VersionSummary
from app.auth.http import ADMIN_COOKIE, clock
from app.core.errors import ServiceError
from app.generators.registry import definition
from app.services.template_edit import detail, find_version, save_draft

router = APIRouter(prefix='/admin/api/v1', tags=['admin-content'], dependencies=[Depends(current_admin)])


def listing(request, response, model, item_dto, list_dto, offset, limit, filters=()):
    response.headers['Cache-Control'] = 'no-store'
    with Session(request.app.state.engine) as session:
        total = session.scalar(select(func.count()).select_from(model).where(*filters))
        rows = session.scalars(select(model).where(*filters).order_by(model.code, model.id).offset(offset).limit(limit)).all()
        data = list_dto(items=[item_dto.model_validate(row, from_attributes=True) for row in rows],
                        offset=offset, limit=limit, total=total)
    return Envelope(data=data, request_id=request.state.request_id)


@router.get('/catalogs', response_model=Envelope[CatalogList])
def catalogs(request: Request, response: Response, offset: int = Query(default=0, ge=0),
             limit: int = Query(default=50, ge=1, le=100)):
    return listing(request, response, ContentCatalog, CatalogSummary, CatalogList, offset, limit)


@router.get('/templates', response_model=Envelope[TemplateList])
def templates(request: Request, response: Response, offset: int = Query(default=0, ge=0),
              limit: int = Query(default=50, ge=1, le=100), q: str = Query(default='', max_length=100),
              status: Literal['active', 'disabled'] | None = None, published: bool | None = None):
    filters = []
    if q.strip():
        filters.append(or_(QuestionTemplate.name.contains(q.strip(), autoescape=True), QuestionTemplate.code.contains(q.strip(), autoescape=True)))
    if status:
        filters.append(QuestionTemplate.status == status)
    if published is not None:
        filters.append(QuestionTemplate.current_published_version_id.is_not(None) if published else QuestionTemplate.current_published_version_id.is_(None))
    return listing(request, response, QuestionTemplate, TemplateSummary, TemplateList, offset, limit, filters)


@router.get('/templates/{identity}', response_model=Envelope[TemplateDetail])
def template_detail(identity: UUID, request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    with Session(request.app.state.engine) as session:
        template = session.get(QuestionTemplate, str(identity))
        if template is None:
            raise ServiceError(404, 'NOT_FOUND', '模板不存在')
        versions = session.scalars(select(TemplateVersion).where(TemplateVersion.template_id == template.id)
                                  .order_by(TemplateVersion.version_no.desc())).all()
        data = TemplateDetail(id=template.id, name=template.name, code=template.code,
                              versions=[VersionSummary.model_validate(v, from_attributes=True) for v in versions])
    return Envelope(data=data, request_id=request.state.request_id)


@router.get('/template-versions/{identity}', response_model=Envelope[DraftDetail])
def version_detail(identity: UUID, request: Request, response: Response):
    deployed = definition()
    with Session(request.app.state.engine) as session:
        data = detail(session, find_version(session, identity), deployed)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['ETag'] = f'"{data.lock_version}"'
    return Envelope(data=data, request_id=request.state.request_id)


@router.patch('/template-versions/{identity}', response_model=Envelope[DraftDetail])
def edit_version(identity: UUID, body: DraftEdit, request: Request, response: Response,
                 if_match: str | None = Header(default=None)):
    if if_match is None or re.fullmatch(r'"[1-9][0-9]{0,9}"', if_match) is None:
        raise ServiceError(422, 'INVALID_CONFIG', '保存必须携带If-Match版本号，例如"1"')
    data = save_draft(request.app.state.engine, identity, body, int(if_match[1:-1]),
                      request.cookies.get(ADMIN_COOKIE), request.headers.get('X-CSRF-Token'), clock(request))
    response.headers['Cache-Control'] = 'no-store'
    response.headers['ETag'] = f'"{data.lock_version}"'
    return Envelope(data=data, request_id=request.state.request_id)
