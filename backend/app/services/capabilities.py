"""Fail-closed public selection backed by live release evidence; no generation here."""
import json
from itertools import product
from app.services.allocation import allocate
from app.services.settings import value as setting_value
from sqlalchemy import select
from app.core.database import write_transaction
from app.core.errors import ServiceError
from app.generators.registry import definition
from app.models.content import (ContentCatalog, CatalogNode, CatalogKnowledge, KnowledgePoint,
    KnowledgeRevision, ObjectiveRevision, TrainingObjective, QuestionTemplate, TemplateVersion, TemplateProfile)
from app.models.policies import KnowledgeTypePolicy
from app.models.system import ContentEpoch
from app.schemas.capabilities import PointView, PointCapabilities, PolicyCell, CapabilityView, CountOptions
from app.schemas.generation import QuestionCounts
from app.services.content_seed import canonical, digest
from app.services.releases import actor, check_lock, epoch, audit, valid_run, reviews

DIFFICULTIES = ('basic', 'standard', 'challenge')
TYPES = ('choice', 'fill', 'answer')


def get(session, model, identity):
    row = session.get(model, str(identity))
    if row is None:
        raise ServiceError(404, 'NOT_FOUND', '内容不存在或未开放')
    return row


def public_node(session, identity):
    node = get(session, CatalogNode, identity)
    catalog = get(session, ContentCatalog, node.catalog_id)
    if catalog.status != 'active' or catalog.grade != 4 or catalog.subject != 'math':
        raise ServiceError(404, 'NOT_FOUND', '目录未开放')
    current, seen = node, set()
    while current:
        if current.id in seen or current.catalog_id != catalog.id or current.status != 'active':
            raise ServiceError(404, 'NOT_FOUND', '主题未开放')
        seen.add(current.id)
        current = get(session, CatalogNode, current.parent_id) if current.parent_id else None
    return node


def linked_points(session, node_id, *, public=False):
    # Includes descendants; a disabled ancestor blocks its whole subtree publicly.
    root = get(session, CatalogNode, node_id)
    nodes = session.scalars(select(CatalogNode).where(CatalogNode.catalog_id == root.catalog_id)).all()
    selected, pending = set(), [root.id]
    while pending:
        identity = pending.pop()
        if identity in selected:
            continue
        node = next(n for n in nodes if n.id == identity)
        if public and node.status != 'active':
            continue
        selected.add(identity)
        pending.extend(n.id for n in nodes if n.parent_id == identity)
    rows = session.execute(select(KnowledgePoint, KnowledgeRevision).join(KnowledgeRevision,
        KnowledgeRevision.point_id == KnowledgePoint.id).join(CatalogKnowledge,
        CatalogKnowledge.knowledge_revision_id == KnowledgeRevision.id).where(CatalogKnowledge.node_id.in_(selected))
        .order_by(KnowledgePoint.code)).all()
    result = {}
    for point, revision in rows:
        if public and (point.status != 'active' or revision.status != 'published' or point.current_revision_id != revision.id):
            continue
        result[point.id] = PointView(id=point.id, code=point.code, name=revision.name)
    return list(result.values())


def support(session, point):
    matrix = {(d, t): {} for d in DIFFICULTIES for t in TYPES}
    if point.status != 'active' or not point.current_revision_id:
        return matrix
    deployed = definition()
    templates = session.scalars(select(QuestionTemplate).where(QuestionTemplate.status == 'active',
        QuestionTemplate.current_published_version_id.is_not(None))).all()
    for template in templates:
        version = get(session, TemplateVersion, template.current_published_version_id)
        if version.status != 'published':
            continue
        latest = next((r for r in reviews(session, version) if r.content_hash == version.content_hash), None)
        if latest is None or latest.decision != 'approved' or not latest.print_checked:
            continue
        try:
            _, _, fixed = valid_run(session, version, latest.validation_run_id, deployed)
        except ServiceError:
            continue
        # The first deployed engine supports one primary target only. Do not invent combined capacity.
        if len(fixed['targets']) != 1:
            continue
        target = fixed['targets'][0]
        if target['role'] != 'primary' or target['knowledge_revision_id'] != point.current_revision_id:
            continue
        knowledge = get(session, KnowledgeRevision, target['knowledge_revision_id'])
        objective = get(session, ObjectiveRevision, target['id'])
        owner = get(session, TrainingObjective, objective.objective_id)
        if (knowledge.status != 'published' or objective.status != 'published' or owner.status != 'active'
                or owner.point_id != point.id or owner.current_revision_id != objective.id):
            continue
        for profile in session.scalars(select(TemplateProfile).where(TemplateProfile.template_version_id == version.id)):
            matrix[profile.difficulty, version.question_type][version.id] = set(json.loads(profile.validated_count_options))
    return matrix


def point_capabilities(session, identity):
    point = get(session, KnowledgePoint, identity)
    revision = get(session, KnowledgeRevision, point.current_revision_id) if point.current_revision_id else session.scalar(
        select(KnowledgeRevision).where(KnowledgeRevision.point_id == point.id).order_by(KnowledgeRevision.revision_no.desc()))
    stored = {(p.difficulty, p.question_type): p for p in session.scalars(select(KnowledgeTypePolicy)
        .where(KnowledgeTypePolicy.knowledge_point_id == point.id))}
    matrix = support(session, point)
    cells = []
    for (difficulty, kind), evidence in matrix.items():
        supported = set().union(*evidence.values())
        policy = stored.get((difficulty, kind))
        configured = json.loads(policy.count_options) if policy else []
        effective = sorted(set(configured) & supported & set(getattr(setting_value(session, 'question_count_options'), kind)))
        cells.append(PolicyCell(difficulty=difficulty, question_type=kind, count_options=configured,
            default_count=policy.default_count if policy else None, supported_count_options=sorted(supported),
            effective_count_options=effective, evidence_version_ids=sorted(evidence),
            unavailable_reason=None if effective else ('尚未配置开放题量' if supported else '没有有效的已发布模板与验证证据')))
    return PointCapabilities(point=PointView(id=point.id, code=point.code, name=revision.name if revision else point.code),
                             lock_version=point.lock_version, policies=cells)


def save_policies(engine, identity, body, expected, *, token, csrf, now, request_id):
    with write_transaction(engine) as session:
        admin = actor(session, token, csrf, now)
        point = get(session, KnowledgePoint, identity)
        check_lock(point, expected)
        before = point_capabilities(session, identity)
        available = {(p.difficulty, p.question_type): set(p.supported_count_options) for p in before.policies}
        for item in body.policies:
            if not set(item.count_options) <= available[item.difficulty, item.question_type]:
                raise ServiceError(409, 'CONTENT_UNAVAILABLE', '配置含未通过验证或已停用的题量，请重新加载')
        stored = {(p.difficulty, p.question_type): p for p in session.scalars(select(KnowledgeTypePolicy)
            .where(KnowledgeTypePolicy.knowledge_point_id == point.id))}
        for item in body.policies:
            row = stored.get((item.difficulty, item.question_type))
            if row is None:
                row = KnowledgeTypePolicy(knowledge_point_id=point.id, difficulty=item.difficulty,
                    question_type=item.question_type, lock_version=1, created_at=now)
                session.add(row)
            else:
                row.lock_version += 1
            row.count_options, row.default_count = canonical(sorted(item.count_options)), item.default_count
            row.updated_by, row.updated_at = admin.id, now
        point.lock_version += 1
        point.updated_at = now
        value = epoch(session, now)
        audit(session, admin, 'quantity_policy', 'knowledge_point', point.id, request_id, body.reason,
            before.model_dump(mode='json'), {'policies': body.model_dump(mode='json')['policies'], 'epoch': value}, now)
        session.flush()
        return point_capabilities(session, identity)


def change_state(engine, model, identity, body, expected, *, token, csrf, now, request_id):
    with write_transaction(engine) as session:
        admin = actor(session, token, csrf, now)
        row = get(session, model, identity)
        check_lock(row, expected)
        before = row.status
        row.status, row.updated_at = body.status, now
        row.lock_version += 1
        value = epoch(session, now)
        audit(session, admin, 'set_status', row.__tablename__, row.id, request_id, body.reason,
            {'status': before}, {'status': row.status, 'epoch': value}, now)


def capabilities(session, body):
    theme = public_node(session, body.theme_id)
    if theme.node_type != 'theme':
        raise ServiceError(422, 'INVALID_CONFIG', '请选择主题节点')
    known = {str(p.id) for p in linked_points(session, theme.id, public=True)}
    selected = sorted(str(p) for p in body.knowledge_point_ids)
    if not set(selected) <= known:
        raise ServiceError(409, 'CONTENT_UNAVAILABLE', '知识点不属于当前已开放主题，请重新选择')
    warnings, feasible = [], []
    context, allowed = allocation_context(session, selected, body.difficulty)
    for combination in product(*(allowed[kind] for kind in TYPES)):
        values = dict(zip(TYPES, combination))
        if allocate(context, values) is not None:
            feasible.append(QuestionCounts(**values))
    if not feasible:
        warnings.append('所选难度暂无可用题量，请更换选择或等待内容开放')
    options = {kind: sorted({getattr(count, kind) for count in feasible}) if feasible else [] for kind in TYPES}
    value = get(session, ContentEpoch, 1).value
    selection = {'theme_id': theme.id, 'knowledge_point_ids': selected, 'difficulty': body.difficulty,
                 'content_epoch': value, 'feasible_counts': [c.model_dump() for c in feasible]}
    return CapabilityView(content_epoch=value, selection_hash=digest(selection), count_options=CountOptions(**options),
        feasible_counts=feasible, point_coverage=selected if feasible else [], warnings=warnings)


def allocation_context(session, selected, difficulty):
    context, policies = {}, {kind: [] for kind in TYPES}
    for identity in selected:
        point = get(session, KnowledgePoint, identity)
        view = point_capabilities(session, identity)
        evidence = support(session, point)
        cells = {}
        for cell in view.policies:
            if cell.difficulty != difficulty or not cell.effective_count_options:
                continue
            kind = cell.question_type
            policies[kind].append(set(cell.effective_count_options))
            candidates = evidence[difficulty, kind]
            version_id = min(candidates, key=lambda v: (-max(candidates[v], default=0), v))
            version = get(session, TemplateVersion, version_id)
            review = next(r for r in reviews(session, version) if r.content_hash == version.content_hash)
            run, _, _ = valid_run(session, version, review.validation_run_id, definition())
            coverage = next(c for c in json.loads(run.report)['coverage'] if c['difficulty'] == difficulty)
            cells[kind] = {'version_id': version_id, 'max_count': max(candidates[version_id]),
                           'exact_capacity': coverage['exact_capacity']}
        context[identity] = cells
    allowed = {kind: [0] + sorted(set.intersection(*sets)) if sets else [0] for kind, sets in policies.items()}
    return context, allowed
