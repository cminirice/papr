"""Short, locked catalogue edits; old papers always retain their snapshots."""
from sqlalchemy import delete, select
from app.core.database import write_transaction
from app.core.errors import ServiceError
from app.models.content import ContentCatalog, ContentSource, CatalogNode, CatalogKnowledge, KnowledgeRevision
from app.schemas.catalog_edit import CatalogDetail, MappingView, MappingItem
from app.schemas.capabilities import NodeView
from app.services.capabilities import get
from app.services.releases import actor, check_lock, epoch, audit


def view(row):
    dto = CatalogDetail if isinstance(row, ContentCatalog) else NodeView
    return dto.model_validate(row, from_attributes=True)


def parent_check(session, catalog_id, parent_id, node_id=None):
    seen = {node_id} if node_id else set()
    while parent_id:
        if str(parent_id) in seen:
            raise ServiceError(409, 'INVALID_CONFIG', '节点不能作为自己的祖先')
        seen.add(str(parent_id))
        parent = get(session, CatalogNode, parent_id)
        if parent.catalog_id != catalog_id:
            raise ServiceError(409, 'INVALID_CONFIG', '父节点必须属于同一目录')
        parent_id = parent.parent_id


def create(engine, model, body, *, catalog_id=None, token, csrf, now, request_id):
    with write_transaction(engine) as session:
        admin = actor(session, token, csrf, now)
        values = body.model_dump(mode='json', exclude={'reason'})
        query = select(model).where(model.code == body.code)
        if model is CatalogNode:
            catalog = get(session, ContentCatalog, catalog_id)
            values['catalog_id'] = catalog.id
            parent_check(session, catalog.id, body.parent_id)
            query = query.where(CatalogNode.catalog_id == catalog.id)
        elif body.source_id is not None:
            get(session, ContentSource, body.source_id)
        if session.scalar(query):
            raise ServiceError(409, 'INVALID_CONFIG', '编码已存在，请使用其他编码')
        row = model(**values, status='draft', lock_version=1, created_at=now, updated_at=now)
        session.add(row)
        session.flush()
        value = epoch(session, now)
        result = view(row)
        audit(session, admin, 'create', model.__tablename__, row.id, request_id, body.reason,
              None, result.model_dump(mode='json') | {'epoch': value}, now)
        return result


def edit(engine, model, identity, body, expected, *, token, csrf, now, request_id):
    with write_transaction(engine) as session:
        admin = actor(session, token, csrf, now)
        row = get(session, model, identity)
        check_lock(row, expected)
        before = view(row).model_dump(mode='json')
        values = body.model_dump(mode='json', exclude={'reason'}, exclude_unset=True)
        if model is CatalogNode and 'parent_id' in values:
            parent_check(session, row.catalog_id, values['parent_id'], row.id)
        if model is ContentCatalog and values.get('source_id'):
            get(session, ContentSource, values['source_id'])
        for key, value in values.items():
            setattr(row, key, value)
        if model is ContentCatalog and set(values) & {'name', 'term', 'source_id'}:
            row.verification_status = 'provisional'
        row.lock_version += 1
        row.updated_at = now
        value = epoch(session, now)
        result = view(row)
        audit(session, admin, 'edit', model.__tablename__, row.id, request_id, body.reason,
              before, result.model_dump(mode='json') | {'epoch': value}, now)
        return result


def mappings(session, identity):
    node = get(session, CatalogNode, identity)
    rows = session.scalars(select(CatalogKnowledge).where(CatalogKnowledge.node_id == node.id)
                           .order_by(CatalogKnowledge.sort_order, CatalogKnowledge.id))
    return MappingView(node_id=node.id, lock_version=node.lock_version,
        items=[MappingItem(knowledge_revision_id=r.knowledge_revision_id, role=r.role) for r in rows])


def replace_mappings(engine, identity, body, expected, *, token, csrf, now, request_id):
    with write_transaction(engine) as session:
        admin = actor(session, token, csrf, now)
        node = get(session, CatalogNode, identity)
        check_lock(node, expected)
        before = mappings(session, identity).model_dump(mode='json')
        points = set()
        for item in body.items:
            revision = get(session, KnowledgeRevision, item.knowledge_revision_id)
            if revision.point_id in points:
                raise ServiceError(409, 'INVALID_CONFIG', '一个节点不能同时映射同一知识点的多个修订')
            points.add(revision.point_id)
        session.execute(delete(CatalogKnowledge).where(CatalogKnowledge.node_id == node.id))
        for position, item in enumerate(body.items):
            session.add(CatalogKnowledge(node_id=node.id, knowledge_revision_id=str(item.knowledge_revision_id),
                sort_order=position, role=item.role, created_at=now, updated_at=now))
        node.lock_version += 1
        node.updated_at = now
        value = epoch(session, now)
        session.flush()
        result = mappings(session, identity)
        audit(session, admin, 'replace_mappings', 'catalog_node', node.id, request_id, body.reason,
              before, result.model_dump(mode='json') | {'epoch': value}, now)
        return result
