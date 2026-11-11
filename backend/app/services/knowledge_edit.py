import json
from sqlalchemy import func, select
from app.core.database import write_transaction
from app.core.errors import ServiceError
from app.models.content import ContentSource, KnowledgePoint, KnowledgeRevision, TrainingObjective, ObjectiveRevision
from app.schemas.knowledge_edit import (SourceContent, SourceView, KnowledgeContent, KnowledgeView,
    ObjectiveContent, ObjectiveView, KnowledgeDetail, ObjectiveDetail)
from app.services.capabilities import get
from app.services.releases import actor, check_lock, audit, epoch
from app.services.content_seed import canonical, digest

JSON_FIELDS = {'aliases', 'misconceptions', 'success_criteria', 'allowed_prerequisites'}


def content(row):
    dto = KnowledgeContent if isinstance(row, KnowledgeRevision) else ObjectiveContent
    return dto(**{key: json.loads(getattr(row, key)) if key in JSON_FIELDS else getattr(row, key)
                  for key in dto.model_fields})


def revision_view(row):
    dto = KnowledgeView if isinstance(row, KnowledgeRevision) else ObjectiveView
    return dto(id=row.id, revision_no=row.revision_no, status=row.status, lock_version=row.lock_version,
               content_hash=row.content_hash, content=content(row))


def detail(session, parent):
    knowledge = isinstance(parent, KnowledgePoint)
    model, key = (KnowledgeRevision, 'point_id') if knowledge else (ObjectiveRevision, 'objective_id')
    revisions = session.scalars(select(model).where(getattr(model, key) == parent.id).order_by(model.revision_no.desc())).all()
    fields = dict(id=parent.id, code=parent.code, status=parent.status, current_revision_id=parent.current_revision_id,
                  lock_version=parent.lock_version, revisions=[revision_view(r) for r in revisions])
    return KnowledgeDetail(**fields, domain=parent.domain) if knowledge else ObjectiveDetail(**fields, point_id=parent.point_id)


def validate_content(session, parent, value):
    if isinstance(value, KnowledgeContent):
        if value.source_id:
            get(session, ContentSource, value.source_id)
    else:
        knowledge = get(session, KnowledgeRevision, value.knowledge_revision_id)
        if knowledge.point_id != parent.point_id:
            raise ServiceError(409, 'INVALID_CONFIG', '目标必须关联所属知识点的修订')
        owner = get(session, KnowledgePoint, parent.point_id)
        for code in value.allowed_prerequisites:
            if code == owner.code or session.scalar(select(KnowledgePoint).where(KnowledgePoint.code == code)) is None:
                raise ServiceError(409, 'INVALID_CONFIG', '先修知识点须存在且不能是自身')


def assign_content(row, value):
    data = value.model_dump(mode='json')
    for key, val in data.items():
        setattr(row, key, canonical(val) if key in JSON_FIELDS else val)
    row.content_hash = digest(data)


def add_revision(session, parent, value, admin, now):
    validate_content(session, parent, value)
    knowledge = isinstance(parent, KnowledgePoint)
    model, key = (KnowledgeRevision, 'point_id') if knowledge else (ObjectiveRevision, 'objective_id')
    number = (session.scalar(select(func.max(model.revision_no)).where(getattr(model, key) == parent.id)) or 0) + 1
    row = model(**{key: parent.id}, revision_no=number, status='draft', lock_version=1,
                created_by=admin.id, created_at=now, updated_at=now)
    assign_content(row, value)
    session.add(row)
    session.flush()
    return row


def create(engine, model, body, *, point_id=None, token, csrf, now, request_id):
    with write_transaction(engine) as session:
        admin = actor(session, token, csrf, now)
        if session.scalar(select(model).where(model.code == body.code)):
            raise ServiceError(409, 'INVALID_CONFIG', '编码已存在')
        if model is KnowledgePoint:
            fields = {'domain': body.domain}
        else:
            fields = {'point_id': get(session, KnowledgePoint, point_id).id}
        parent = model(code=body.code, **fields, status='draft', lock_version=1, created_at=now, updated_at=now)
        session.add(parent)
        session.flush()
        revision = add_revision(session, parent, body.content, admin, now)
        audit(session, admin, 'create', parent.__tablename__, parent.id, request_id, body.reason, None,
              {'code': parent.code, 'draft_revision_id': revision.id, 'epoch': epoch(session, now)}, now)
        return detail(session, parent)


def copy_revision(engine, model, identity, body, expected, *, token, csrf, now, request_id):
    with write_transaction(engine) as session:
        admin = actor(session, token, csrf, now)
        parent = get(session, model, identity)
        check_lock(parent, expected)
        knowledge = model is KnowledgePoint
        source = get(session, KnowledgeRevision if knowledge else ObjectiveRevision, body.source_revision_id)
        if getattr(source, 'point_id' if knowledge else 'objective_id') != parent.id:
            raise ServiceError(409, 'INVALID_CONFIG', '只能复制当前对象的修订')
        row = add_revision(session, parent, content(source), admin, now)
        parent.lock_version += 1
        parent.updated_at = now
        audit(session, admin, 'copy_revision', row.__tablename__, row.id, request_id, body.reason,
              {'source_revision_id': source.id}, {'content_hash': row.content_hash, 'epoch': epoch(session, now)}, now)
        return detail(session, parent)


def edit_revision(engine, model, identity, body, expected, *, token, csrf, now, request_id):
    with write_transaction(engine) as session:
        admin = actor(session, token, csrf, now)
        row = get(session, model, identity)
        check_lock(row, expected)
        if row.status != 'draft':
            raise ServiceError(409, 'CONTENT_UNAVAILABLE', '已发布修订不可修改，请复制新草稿')
        parent = get(session, KnowledgePoint, row.point_id) if model is KnowledgeRevision else get(session, TrainingObjective, row.objective_id)
        dto = KnowledgeContent if model is KnowledgeRevision else ObjectiveContent
        value = dto.model_validate(body.model_dump(exclude={'reason'}))
        validate_content(session, parent, value)
        before = revision_view(row).model_dump(mode='json')
        assign_content(row, value)
        row.lock_version += 1
        row.updated_at = now
        result = revision_view(row)
        audit(session, admin, 'edit_draft', row.__tablename__, row.id, request_id, body.reason,
              before, result.model_dump(mode='json') | {'epoch': epoch(session, now)}, now)
        return result


def save_source(engine, identity, body, expected=None, *, token, csrf, now, request_id):
    with write_transaction(engine) as session:
        admin = actor(session, token, csrf, now)
        row = get(session, ContentSource, identity) if identity else ContentSource(created_at=now, lock_version=1)
        before = SourceView.model_validate(row, from_attributes=True).model_dump(mode='json') if identity else None
        if identity:
            check_lock(row, expected)
            row.lock_version += 1
        # Preserve datetime values for BeijingTime; UUID/date values use SQL-friendly forms.
        data = SourceContent.model_validate(body.model_dump(exclude={'reason'})).model_dump()
        for key, value in data.items():
            setattr(row, key, value.isoformat() if key == 'published_on' and value else value)
        row.updated_at = now
        session.add(row)
        session.flush()
        result = SourceView.model_validate(row, from_attributes=True)
        audit(session, admin, 'edit' if identity else 'create', 'content_source', row.id, request_id, body.reason,
              before, result.model_dump(mode='json'), now)
        return result
