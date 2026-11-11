from app.services.settings import value as setting_value
"""Paper admission and immutable input, gated by a probed worker heartbeat."""
import base64
import json
import secrets
from uuid import UUID
from sqlalchemy import and_, func, or_, select
from app.auth.security import check_csrf
from app.core.database import write_transaction
from app.core.errors import ServiceError
from app.core.time import parse_stored_time, serialize_time
from app.generators.registry import definition
from app.models.content import CatalogNode, ContentCatalog, KnowledgePoint, TemplateProfile, TemplateVersion
from app.models.jobs import Job
from app.schemas.capabilities import CapabilitySelection
from app.schemas.paper_jobs import PaperPart, PaperPlan, PaperJobView, PaperJobList
from app.services.capabilities import allocation_context, capabilities, get, support, point_capabilities
from app.services.content_seed import canonical, digest
from app.services.identity.cooldown import check_generation_admission
from app.services.identity.limits import reserve_event
from app.services.identity.sessions import require_user
from app.services.releases import reviews, valid_run
from app.services.template_edit import detail



def executor_ready(session, settings, now):
    from app.services.paper_runtime import ready
    return ready(session, settings, now)


def view(job):
    result = json.loads(job.result) if job.result and job.status == 'succeeded' else {}
    return PaperJobView(id=job.id, status=job.status, phase=job.phase, attempt=job.attempt,
        progress_done=job.progress_done, progress_total=job.progress_total,
        created_at=job.created_at, finished_at=job.finished_at, error_code=job.error_code,
        error_message='本次生成未完成，请使用新请求重试' if job.status == 'failed' else None,
        paper_id=result.get('paper_id'))


def owned(session, identity, owner_id):
    job = session.get(Job, str(identity))
    if job is None or job.kind != 'paper_generate' or job.owner_user_id != owner_id:
        raise ServiceError(404, 'NOT_FOUND', '任务不存在')
    return job


def selection(body):
    return CapabilitySelection(theme_id=body.theme_id, knowledge_point_ids=body.knowledge_point_ids,
                               difficulty=body.difficulty)


def normalize(body):
    return body.model_copy(update={'knowledge_point_ids': sorted(body.knowledge_point_ids, key=str)})


def freeze_selection(session, body):
    from app.services.allocation import allocate
    effective = capabilities(session, selection(body))
    if body.content_epoch != effective.content_epoch:
        raise ServiceError(409, 'CAPABILITY_CHANGED', '内容已更新，请重新查询可用题量')
    if body.question_type_counts not in effective.feasible_counts:
        raise ServiceError(422, 'UNSUPPORTED_COMBINATION', '当前内容无法生成所选数量与覆盖组合')
    context, _ = allocation_context(session, sorted(str(p) for p in body.knowledge_point_ids), body.difficulty)
    allocation = allocate(context, body.question_type_counts.model_dump())
    if not allocation:
        raise ServiceError(422, 'UNSUPPORTED_COMBINATION', '不能覆盖所选知识点')
    parts = []
    for item in allocation:
        part_body = body.model_copy(update={'knowledge_point_ids': [UUID(item['point_id'])],
            'question_type_counts': body.question_type_counts.model_validate({k: item['count'] if k == item['kind'] else 0 for k in ('choice', 'fill', 'answer')})})
        parts.append(freeze_part(session, part_body, item['version_id']))
    return PaperPlan(**(parts[0].model_dump() | {'request': body}), parts=parts if len(parts) > 1 else [])


def freeze_part(session, body, version_id):
    version = get(session, TemplateVersion, version_id)
    review = next(r for r in reviews(session, version) if r.content_hash == version.content_hash)
    run, _, fixed = valid_run(session, version, review.validation_run_id, definition())
    profile = session.scalar(select(TemplateProfile).where(TemplateProfile.template_version_id == version.id,
                                                          TemplateProfile.difficulty == body.difficulty))
    config = next(p for p in detail(session, version, definition()).config.profiles if p.difficulty == body.difficulty)
    theme = get(session, CatalogNode, body.theme_id)
    catalog = get(session, ContentCatalog, theme.catalog_id)
    return PaperPart(request=body, seed=secrets.token_hex(16), template_version_id=version.id,
        content_hash=version.content_hash, profile_id=profile.id, profile_hash=profile.profile_hash,
        profile=config, generator_id=version.generator_id, generator_artifact_hash=fixed['generator']['artifact_hash'],
        validation_run_id=run.id, review_id=review.id, knowledge_revision_id=fixed['targets'][0]['knowledge_revision_id'],
        objective_revision_id=fixed['targets'][0]['id'], fixed=fixed,
        catalog_snapshot={'catalog_id': catalog.id, 'catalog_name': catalog.name, 'theme_id': theme.id,
                          'theme_name': theme.name, 'verification_status': catalog.verification_status})


def check_snapshot_current(session, plan):
    """For the worker's final transaction: recheck availability without silently replacing the plan."""
    effective = capabilities(session, selection(plan.request))
    if plan.request.question_type_counts not in effective.feasible_counts:
        raise ServiceError(409, 'CONTENT_UNAVAILABLE', '原配置已不可用')
    if {str(p) for part in plan.allocations() for p in part.request.knowledge_point_ids} != {str(p) for p in plan.request.knowledge_point_ids}:
        raise ServiceError(409, 'CONTENT_UNAVAILABLE', '原分配不能覆盖所选知识点')
    for part in plan.allocations():
        check_part_current(session, part)


def check_part_current(session, plan):
    point = get(session, KnowledgePoint, plan.request.knowledge_point_ids[0])
    kind = plan.fixed['question_type']
    policy = next(p for p in point_capabilities(session, point.id).policies if p.difficulty == plan.request.difficulty and p.question_type == kind)
    if not policy.effective_count_options:
        raise ServiceError(409, 'CONTENT_UNAVAILABLE', '原知识点题型已停止开放')
    versions = support(session, point)[plan.request.difficulty, kind]
    if getattr(plan.request.question_type_counts, kind) > max(versions.get(str(plan.template_version_id), set()), default=0):
        raise ServiceError(409, 'CONTENT_UNAVAILABLE', '原模板已被停用或替换')
    version = get(session, TemplateVersion, plan.template_version_id)
    profile = get(session, TemplateProfile, plan.profile_id)
    _, _, fixed = valid_run(session, version, plan.validation_run_id, definition())
    latest = next(r for r in reviews(session, version) if r.content_hash == version.content_hash)
    config = next(p for p in detail(session, version, definition()).config.profiles if p.difficulty == plan.request.difficulty)
    if (version.content_hash != plan.content_hash or profile.profile_hash != plan.profile_hash
            or profile.template_version_id != version.id or profile.difficulty != plan.request.difficulty
            or config != plan.profile or fixed != plan.fixed or latest.id != str(plan.review_id)
            or version.generator_id != str(plan.generator_id)
            or fixed['generator']['artifact_hash'] != plan.generator_artifact_hash
            or fixed['targets'][0]['knowledge_revision_id'] != str(plan.knowledge_revision_id)
            or fixed['targets'][0]['id'] != str(plan.objective_revision_id)):
        raise ServiceError(409, 'CONTENT_UNAVAILABLE', '内容证据已变化，不能替换原任务内容')


def accept(engine, body, key, token, csrf, subject, now, settings=None):
    from app.core.config import Settings
    settings = settings or Settings.from_env()
    body = normalize(body)
    request_hash = digest({'kind': 'paper_generate', **body.model_dump(mode='json')})
    with write_transaction(engine) as session:
        user, stored = require_user(session, token, now)
        check_csrf(csrf, stored.csrf_hash)
        existing = session.scalar(select(Job).where(Job.owner_user_id == user.id, Job.idempotency_key == str(key)))
        if existing:
            if existing.kind != 'paper_generate' or existing.payload_hash != request_hash:
                raise ServiceError(409, 'IDEMPOTENCY_CONFLICT', '同一请求编号不能用于不同配置')
            return view(existing)
        if not executor_ready(session, settings, now):
            raise ServiceError(503, 'SERVICE_NOT_READY', 'PDF出卷服务尚未就绪，暂不受理新任务')
        check_generation_admission(session, user, now)
        plan = freeze_selection(session, body)
        active = session.scalar(select(func.count()).select_from(Job).where(Job.status.in_(['queued', 'running'])))
        if active >= setting_value(session, 'generation_limits').queue_limit:
            raise ServiceError(503, 'QUEUE_FULL', '任务队列已满，请稍后重试')
        reserve_event(session, 'generation_accept', subject, now, limit=setting_value(session, 'generation_limits').ip_accept_limit, seconds=600)
        job = Job(kind='paper_generate', owner_user_id=user.id, idempotency_key=str(key), payload_hash=request_hash,
            payload=plan.model_dump_json(), available_at=now, progress_total=3,
            content_schema_version=1, created_at=now, updated_at=now)
        session.add(job)
        session.flush()
        return view(job)


def cancel(engine, identity, token, csrf, now):
    with write_transaction(engine) as session:
        user, stored = require_user(session, token, now)
        check_csrf(csrf, stored.csrf_hash)
        job = owned(session, identity, user.id)
        if job.status == 'cancelled':
            return view(job)
        if job.status != 'queued':
            raise ServiceError(409, 'JOB_NOT_CANCELLABLE', '仅排队中的任务可以取消')
        job.status, job.phase = 'cancelled', 'done'
        job.finished_at = job.updated_at = now
        job.lease_token = job.lease_until = None
        return view(job)


def cursor_for(job):
    raw = canonical([serialize_time(job.created_at), job.id]).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')


def parse_cursor(value):
    try:
        if len(value) > 256:
            raise ValueError()
        data = json.loads(base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True))
        if not isinstance(data, list) or len(data) != 2 or not all(isinstance(v, str) for v in data):
            raise ValueError()
        now, identity = parse_stored_time(data[0]), str(UUID(data[1]))
        return now, identity
    except (ValueError, TypeError, UnicodeError):
        raise ServiceError(422, 'INVALID_CONFIG', '分页游标无效') from None


def listing(session, owner_id, cursor=None, limit=20, status=None):
    query = select(Job).where(Job.owner_user_id == owner_id, Job.kind == 'paper_generate')
    if status:
        query = query.where(Job.status == status)
    if cursor:
        created, identity = parse_cursor(cursor)
        query = query.where(or_(Job.created_at < created, and_(Job.created_at == created, Job.id < identity)))
    rows = session.scalars(query.order_by(Job.created_at.desc(), Job.id.desc()).limit(limit + 1)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    return PaperJobList(items=[view(job) for job in rows], has_more=has_more,
                        next_cursor=cursor_for(rows[-1]) if has_more else None)
