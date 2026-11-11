from app.services.settings import value as setting_value
"""验证任务受理、租约和最终报告提交；数学计算由独立进程执行。"""
from datetime import timedelta
import json
from uuid import uuid4
from sqlalchemy import func, select
from app.auth.security import check_csrf
from app.core.database import write_transaction
from app.core.errors import ServiceError
from app.generators.registry import definition
from app.models.content import TemplateVersion
from app.models.jobs import Job
from app.models.validation import ValidationFailure, ValidationRun
from app.schemas.validation import ValidationReport, ValidationView
from app.services.content_seed import canonical, digest
from app.services.identity.sessions import require_admin
from app.services.template_edit import detail, find_version, profiles_and_cases, require_editable, snapshot

LEASE_SECONDS = 120


def view(session, run):
    job = session.get(Job, run.job_id)
    return ValidationView(id=run.id, job_id=job.id, template_version_id=run.template_version_id,
        content_hash=run.content_hash, status=run.status, job_status=job.status, attempt=job.attempt,
        error_code=job.error_code, created_at=run.created_at, finished_at=run.finished_at,
        report=ValidationReport.model_validate_json(run.report) if run.report else None)


def acceptance(engine, identity, body, key, token, csrf, now):
    deployed = definition()
    request_hash = digest({'kind': 'template_validate', 'version_id': str(identity), **body.model_dump()})
    with write_transaction(engine) as session:
        admin, stored = require_admin(session, token, now)
        check_csrf(csrf, stored.csrf_hash)
        existing = session.scalar(select(Job).where(Job.owner_admin_id == admin.id, Job.idempotency_key == str(key)))
        if existing:
            if existing.kind != 'template_validate' or existing.payload_hash != request_hash:
                raise ServiceError(409, 'IDEMPOTENCY_CONFLICT', '同一幂等key不能用于不同请求')
            run = session.scalar(select(ValidationRun).where(ValidationRun.job_id == existing.id))
            if run is None:
                raise ServiceError(409, 'CONTENT_UNAVAILABLE', '原验证记录已不可用，请使用新key发起验证')
            return view(session, run)
        version = find_version(session, identity)
        fixed, generator = snapshot(session, version)
        require_editable(session, version, fixed, generator, deployed, body.lock_version)
        if version.content_hash != body.content_hash:
            raise ServiceError(409, 'EDIT_CONFLICT', '草稿hash已变化，请重新加载')
        active = session.scalar(select(func.count()).select_from(Job).where(Job.status.in_(['queued', 'running'])))
        if active >= setting_value(session, 'generation_limits').queue_limit:
            raise ServiceError(503, 'QUEUE_FULL', '验证队列已满，请稍后重试')
        config = detail(session, version, deployed).config.model_dump(mode='json')
        profiles, _ = profiles_and_cases(session, version)
        payload = {'policy_version': 1, 'version_id': version.id, 'lock_version': version.lock_version,
            'content_hash': version.content_hash, 'fixed': fixed, 'config': config,
            'profile_ids': {p.difficulty: p.id for p in profiles}}
        job = Job(id=str(uuid4()), kind='template_validate', owner_admin_id=admin.id,
            idempotency_key=str(key), payload_hash=request_hash, payload=canonical(payload),
            available_at=now, progress_total=1, created_at=now, updated_at=now)
        session.add(job)
        session.flush()
        run = ValidationRun(id=str(uuid4()), template_version_id=version.id, job_id=job.id,
            content_hash=version.content_hash, generator_id=generator.id, validator_version=generator.validator_version,
            requested_by=admin.id, created_at=now, updated_at=now)
        session.add(run)
        session.flush()
        return view(session, run)


def claim(engine, now):
    with write_transaction(engine) as session:
        expired = session.scalars(select(Job).where(Job.kind == 'template_validate', Job.status == 'running', Job.lease_until <= now)).all()
        for job in expired:
            run = session.scalar(select(ValidationRun).where(ValidationRun.job_id == job.id))
            job.lease_token = job.lease_until = None
            job.updated_at = run.updated_at = now
            if job.attempt < job.max_attempts:
                job.status = 'queued'
                job.phase = 'queued'
                job.available_at = now
                if run.status != 'stale':
                    run.status = 'queued'
            else:
                job.status, job.phase, job.error_code = 'failed', 'done', 'WORKER_LOST'
                job.error_message = 'worker租约过期，已达到尝试上限'
                job.finished_at = run.finished_at = now
                if run.status != 'stale':
                    run.status = 'failed'
        session.flush()
        job = session.scalar(select(Job).where(Job.kind == 'template_validate', Job.status == 'queued', Job.available_at <= now)
                             .order_by(Job.priority.desc(), Job.created_at, Job.id).limit(1))
        if job is None:
            return None
        job.status, job.phase = 'running', 'generating'
        job.attempt += 1
        job.lease_token = str(uuid4())
        job.lease_until = now + timedelta(seconds=LEASE_SECONDS)
        job.started_at = job.started_at or now
        job.updated_at = now
        run = session.scalar(select(ValidationRun).where(ValidationRun.job_id == job.id))
        if run.status != 'stale':
            run.status = 'running'
        run.started_at, run.updated_at = run.started_at or now, now
        return {'job_id': job.id, 'attempt': job.attempt, 'lease_token': job.lease_token, 'payload': json.loads(job.payload)}


def finish(engine, claimed, now, report: ValidationReport | None = None, error_code: str | None = None):
    deployed = definition()
    with write_transaction(engine) as session:
        job = session.get(Job, claimed['job_id'])
        if (job.status != 'running' or job.lease_token != claimed['lease_token']
                or job.attempt != claimed['attempt'] or job.lease_until <= now):
            return False  # 过期worker禁止提交；由新的租约恢复。
        run = session.scalar(select(ValidationRun).where(ValidationRun.job_id == job.id))
        payload = json.loads(job.payload)
        version = session.get(TemplateVersion, run.template_version_id)
        fixed, generator = snapshot(session, version)
        stale = run.status == 'stale' or version.content_hash != run.content_hash or version.lock_version != payload['lock_version']
        try:
            require_editable(session, version, fixed, generator, deployed, payload['lock_version'])
            stale = stale or fixed != payload['fixed'] or detail(session, version, deployed).config.model_dump(mode='json') != payload['config']
        except ServiceError:
            stale = True
        job.status = 'failed' if error_code else 'succeeded'
        job.phase = 'done'
        job.error_code = error_code
        job.error_message = '验证执行失败，请使用新key重试' if error_code else None
        job.finished_at = run.finished_at = job.updated_at = run.updated_at = now
        job.lease_token = job.lease_until = None
        run.status = 'stale' if stale else ('failed' if error_code else report.result)
        if report is not None:
            run.report = report.model_dump_json()
            run.sample_count, run.failure_count = report.sample_count, report.failure_count
            run.coverage = canonical([item.model_dump() for item in report.coverage])
            for failure in report.failures:
                session.add(ValidationFailure(run_id=run.id, profile_id=payload['profile_ids'][failure.difficulty],
                    case_code=failure.case_code, seed=failure.seed,
                    params=canonical(failure.params.model_dump()) if failure.params else None,
                    error_code=failure.error_code, message=failure.message, created_at=now, updated_at=now))
            if run.status == 'passed':
                profiles, _ = profiles_and_cases(session, version)
                counts = {item.difficulty: item.checked_count_options for item in report.coverage}
                for profile in profiles:
                    profile.validated_count_options = canonical(counts[profile.difficulty])
                    profile.updated_at = now
            job.progress_done = job.progress_total
        job.result = canonical({'validation_run_id': run.id, 'validation_status': run.status})
        return True
