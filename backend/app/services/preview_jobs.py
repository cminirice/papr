from app.services.settings import value as setting_value
from datetime import timedelta
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
from pydantic import TypeAdapter
from sqlalchemy import func, select
from app.core.database import write_transaction
from app.core.errors import ServiceError
from app.core.time import beijing_now
from app.generators.registry import definition
from app.generators.multiplication import verify_question
from app.models.jobs import Job
from app.models.content import TemplateVersion
from app.schemas.content import MultiplicationQuestion, MultiplicationProfile
from app.schemas.template_tools import PreviewView
from app.services.content_seed import canonical, digest
from app.services.releases import actor
from app.services.template_edit import find_version, snapshot, require_editable, detail

LEASE_SECONDS = 120


def view(session, job):
    payload = json.loads(job.payload)
    version = session.get(TemplateVersion, payload['template_version_id'])
    stale = version is None or version.content_hash != payload['content_hash'] or version.lock_version != payload['lock_version']
    if version:
        fixed, _ = snapshot(session, version)
        stale = stale or fixed != payload['fixed'] or payload['artifact_hash'] != definition()['artifact_hash']
    return PreviewView(id=job.id, template_version_id=payload['template_version_id'], content_hash=payload['content_hash'],
        status=job.status, attempt=job.attempt, created_at=job.created_at, stale=stale, error_code=job.error_code,
        questions=json.loads(job.result)['questions'] if job.status == 'succeeded' and job.result else [])


def acceptance(engine, identity, body, key, *, token, csrf, now, request_id):
    deployed = definition()
    request_hash = digest({'kind': 'template_preview', 'version_id': str(identity), **body.model_dump()})
    with write_transaction(engine) as session:
        admin = actor(session, token, csrf, now)
        existing = session.scalar(select(Job).where(Job.owner_admin_id == admin.id, Job.idempotency_key == str(key)))
        if existing:
            if existing.kind != 'template_preview' or existing.payload_hash != request_hash:
                raise ServiceError(409, 'IDEMPOTENCY_CONFLICT', '同一请求编号不能用于不同预览')
            return view(session, existing)
        version = find_version(session, identity)
        fixed, generator = snapshot(session, version)
        require_editable(session, version, fixed, generator, deployed, body.lock_version)
        if version.content_hash != body.content_hash:
            raise ServiceError(409, 'EDIT_CONFLICT', '草稿已变化，请重新加载')
        profile = next((p for p in detail(session, version, deployed).config.profiles if p.difficulty == body.difficulty), None)
        if profile is None or body.count > profile.max_per_paper:
            raise ServiceError(422, 'INVALID_CONFIG', '当前草稿不支持此难度或题量')
        active = session.scalar(select(func.count()).select_from(Job).where(Job.status.in_(['queued', 'running'])))
        if active >= setting_value(session, 'generation_limits').queue_limit:
            raise ServiceError(503, 'QUEUE_FULL', '任务队列已满，请稍后重试')
        payload = {'template_version_id': version.id, 'content_hash': version.content_hash, 'lock_version': version.lock_version,
            'fixed': fixed, 'artifact_hash': deployed['artifact_hash'], 'request': body.model_dump(), 'profile': profile.model_dump(mode='json')}
        job = Job(kind='template_preview', owner_admin_id=admin.id, idempotency_key=str(key), payload_hash=request_hash,
            payload=canonical(payload), available_at=now, progress_total=body.count, created_at=now, updated_at=now)
        session.add(job)
        session.flush()
        return view(session, job)


def claim(engine, now):
    with write_transaction(engine) as session:
        for job in session.scalars(select(Job).where(Job.kind == 'template_preview', Job.status == 'running', Job.lease_until <= now)):
            job.lease_token = job.lease_until = None
            job.updated_at = now
            if job.attempt < job.max_attempts:
                job.status = job.phase = 'queued'
                job.available_at = now
            else:
                job.status, job.phase, job.error_code, job.finished_at = 'failed', 'done', 'WORKER_LOST', now
        session.flush()
        job = session.scalar(select(Job).where(Job.kind == 'template_preview', Job.status == 'queued', Job.available_at <= now)
            .order_by(Job.created_at, Job.id).limit(1))
        if job is None:
            return None
        job.status, job.phase = 'running', 'generating'
        job.attempt += 1
        job.lease_token = str(uuid4())
        job.lease_until = now + timedelta(seconds=LEASE_SECONDS)
        job.started_at = job.started_at or now
        job.updated_at = now
        return {'id': job.id, 'attempt': job.attempt, 'lease_token': job.lease_token, 'payload': json.loads(job.payload)}


def finish(engine, claimed, now, questions=None, error=None):
    with write_transaction(engine) as session:
        job = session.get(Job, claimed['id'])
        if job.status != 'running' or job.lease_token != claimed['lease_token'] or job.attempt != claimed['attempt'] or job.lease_until <= now:
            return False
        job.status = 'failed' if error else 'succeeded'
        job.phase, job.error_code = 'done', error
        job.finished_at = job.updated_at = now
        job.lease_token = job.lease_until = None
        if not error:
            job.result = canonical({'questions': [q.model_dump(mode='json') for q in questions]})
            job.progress_done = job.progress_total
        return True


def run_child(payload):
    result = subprocess.run([sys.executable, '-m', 'app.preview_child'], cwd=Path(__file__).resolve().parents[2],
        input=canonical(payload), capture_output=True, text=True, timeout=30, check=True)
    return TypeAdapter(list[MultiplicationQuestion]).validate_json(result.stdout)


def run_once(engine, *, clock=beijing_now, runner=run_child):
    claimed = claim(engine, clock())
    if not claimed:
        return False
    try:
        questions = runner(claimed['payload'])
        if len(questions) != claimed['payload']['request']['count'] or len({q.id for q in questions}) != len(questions):
            raise ValueError('Preview count mismatch')
        profile = MultiplicationProfile.model_validate(claimed['payload']['profile'])
        for question in questions:
            if question.question_type != claimed['payload']['fixed']['question_type']:
                raise ValueError('Question type mismatch')
            verify_question(question, profile)
    except subprocess.TimeoutExpired:
        finish(engine, claimed, clock(), error='ENGINE_TIMEOUT')
    except (OSError, subprocess.SubprocessError, ValueError):
        finish(engine, claimed, clock(), error='PREVIEW_ENGINE_ERROR')
    else:
        finish(engine, claimed, clock(), questions=questions)
    return True
