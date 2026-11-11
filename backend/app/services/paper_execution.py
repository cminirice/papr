"""Attempt-fenced paper pipeline. Rendering and file I/O never hold a write lock."""
from datetime import timedelta
from hashlib import sha256
import json
import re
import time
from uuid import UUID, uuid4
from sqlalchemy import select
from app.core.database import write_transaction
from app.core.errors import ServiceError
from app.core.time import beijing_now, serialize_time
from app.generators.multiplication import verify_question, semantic_signature
from app.models.identity import AppUser
from app.models.jobs import Job
from app.models.papers import Paper, Question, QuestionKnowledge, PaperQuestion, FileAsset
from app.schemas.content import MultiplicationQuestion, MultiplicationParams
from app.schemas.paper_jobs import PaperPlan
from app.services.content_seed import canonical, digest
from app.services.identity.cooldown import record_generation_success
from app.services.paper_jobs import check_snapshot_current
from app.services import paper_runtime
from app.services.pdf_storage import PdfTarget, save_pair, read_verified, PdfStorageError, KINDS

LEASE_SECONDS = 30
ATTEMPT_SECONDS = 90


class LeaseLost(Exception):
    pass


def fenced(session, claimed, now):
    job = session.get(Job, claimed['job_id'])
    if (job is None or job.status != 'running' or job.attempt != claimed['attempt']
            or job.lease_token != claimed['lease_token'] or job.lease_until is None or job.lease_until <= now):
        raise LeaseLost()
    return job


def fail_assets(session, job, now, code):
    for asset in session.scalars(select(FileAsset).where(FileAsset.job_id == job.id, FileAsset.status == 'pending')):
        asset.status, asset.error_code, asset.updated_at = 'failed', code, now


def claim(engine, now):
    with write_transaction(engine) as session:
        for job in session.scalars(select(Job).where(Job.kind == 'paper_generate', Job.status == 'running', Job.lease_until <= now)):
            fail_assets(session, job, now, 'WORKER_LOST')
            job.lease_token = job.lease_until = None
            job.updated_at = now
            if job.attempt < job.max_attempts:
                job.status, job.phase, job.available_at = 'queued', 'queued', now
            else:
                job.status, job.phase, job.error_code, job.finished_at = 'failed', 'done', 'WORKER_LOST', now
        session.flush()
        job = session.scalar(select(Job).where(Job.kind == 'paper_generate', Job.status == 'queued', Job.available_at <= now)
                             .order_by(Job.priority.desc(), Job.created_at, Job.id).limit(1))
        if job is None:
            return None
        job.status, job.phase = 'running', 'generating'
        job.attempt += 1
        job.lease_token = str(uuid4())
        job.lease_until = now + timedelta(seconds=LEASE_SECONDS)
        job.started_at = job.started_at or now
        job.updated_at = now
        job.progress_done = 0
        return {'job_id': job.id, 'attempt': job.attempt, 'lease_token': job.lease_token,
                'plan': job.payload, 'generated_at': serialize_time(job.started_at)}


def renew(engine, claimed, now):
    with write_transaction(engine) as session:
        job = fenced(session, claimed, now)
        job.lease_until = now + timedelta(seconds=LEASE_SECONDS)
        job.updated_at = now


def validate_questions(plan, values):
    questions = [MultiplicationQuestion.model_validate(q) for q in values]
    if len(questions) != plan.request.question_type_counts.total:
        raise ValueError('QUESTION_COUNT_MISMATCH')
    if {kind: sum(q.question_type == kind for q in questions) for kind in ('choice', 'fill', 'answer')} != plan.request.question_type_counts.model_dump():
        raise ValueError('QUESTION_TYPE_COUNTS_MISMATCH')
    signatures, ids = set(), set()
    owners = [part for part in plan.allocations() for _ in range(part.request.question_type_counts.total)]
    if len(owners) != len(questions):
        raise ValueError('ALLOCATION_COUNT_MISMATCH')
    for position, (question, part) in enumerate(zip(questions, owners), 1):
        if question.question_type != part.fixed['question_type']:
            raise ValueError('QUESTION_TYPE_MISMATCH')
        verify_question(question, part.profile)
        signature = signature_of(question)
        if question.position != position or question.id in ids or signature in signatures:
            raise ValueError('QUESTION_DUPLICATE_OR_ORDER')
        signatures.add(signature)
        ids.add(question.id)
    return questions


def params_of(question):
    return MultiplicationParams(a=int(question.render_spec.multiplicand), b=int(question.render_spec.multiplier))


def signature_of(question):
    return sha256(semantic_signature(params_of(question)).encode()).hexdigest()


def reserve(engine, claimed, document, now):
    with write_transaction(engine) as session:
        job = fenced(session, claimed, now)
        plan = PaperPlan.model_validate_json(job.payload)
        check_snapshot_current(session, plan)
        snapshot = canonical(document)
        if job.intermediate_snapshot is not None and job.intermediate_snapshot != snapshot:
            raise ValueError('SNAPSHOT_MISMATCH')
        job.intermediate_snapshot = snapshot
        job.phase, job.progress_done, job.updated_at = 'rendering', 1, now
        targets = {}
        for kind in KINDS:
            target = PdfTarget(uuid4(), now)
            targets[kind] = target
            session.add(FileAsset(id=str(target.asset_id), owner_user_id=job.owner_user_id, job_id=job.id,
                attempt=job.attempt, lease_token=job.lease_token, kind=kind, storage_key=target.storage_key,
                created_at=now, updated_at=now))
        return targets


def saving(engine, claimed, now):
    with write_transaction(engine) as session:
        job = fenced(session, claimed, now)
        job.phase, job.progress_done, job.updated_at = 'saving', 2, now


def check_metadata(document, contents, metadata):
    fields = ('font_sha256', 'print_asset_sha256', 'input_sha256', 'student_sha256', 'solution_sha256')
    if (not isinstance(metadata, dict) or any(not isinstance(metadata.get(k), str)
            or not re.fullmatch('[0-9a-f]{64}', metadata[k]) for k in fields)
            or metadata.get('renderer_version') != 'papr-chromium-v1'
            or metadata.get('content_schema_version') != 1
            or any(not isinstance(metadata.get(k), str) or not metadata[k] for k in ('browser_version', 'vue_version', 'playwright_version'))
            or metadata['input_sha256'] != sha256(canonical(document).encode()).hexdigest()
            or metadata['student_sha256'] != sha256(contents['student_pdf']).hexdigest()
            or metadata['solution_sha256'] != sha256(contents['solution_pdf']).hexdigest()):
        raise ValueError('PDF_METADATA_MISMATCH')


def finish(engine, claimed, document, saved, metadata, now):
    """Caller has verified actual files immediately before this short transaction."""
    with write_transaction(engine) as session:
        job = fenced(session, claimed, now)
        plan = PaperPlan.model_validate_json(job.payload)
        check_snapshot_current(session, plan)
        user = session.get(AppUser, job.owner_user_id)
        if user.status != 'active' or user.deleted_at is not None:
            raise ServiceError(409, 'CONTENT_UNAVAILABLE', '用户不可用')
        if job.intermediate_snapshot != canonical(document) or set(saved) != set(KINDS):
            raise ValueError('SNAPSHOT_MISMATCH')
        assets = {}
        for kind, file in saved.items():
            asset = session.get(FileAsset, str(file.target.asset_id))
            if (asset is None or asset.status != 'pending' or asset.job_id != job.id
                    or asset.owner_user_id != user.id or asset.kind != kind or asset.attempt != job.attempt
                    or asset.lease_token != job.lease_token or asset.storage_key != file.target.storage_key
                    or asset.created_at != file.target.registered_at):
                raise LeaseLost()
            assets[kind] = asset
        questions = validate_questions(plan, document['questions'])
        counts = plan.request.question_type_counts
        paper = Paper(id=str(uuid4()), owner_user_id=user.id, job_id=job.id, title=document['title'],
            catalog_snapshot=canonical(plan.catalog_snapshot), config_snapshot=plan.model_dump_json(),
            difficulty=plan.request.difficulty, choice_count=counts.choice, fill_count=counts.fill,
            answer_count=counts.answer, total_count=counts.choice + counts.fill + counts.answer,
            content_schema_version=1, generated_at=now, created_at=now, updated_at=now)
        session.add(paper)
        session.flush()
        owners = [part for part in plan.allocations() for _ in range(part.request.question_type_counts.total)]
        for q, part in zip(questions, owners):
            signature = signature_of(q)
            session.add(Question(id=str(q.id), template_version_id=str(part.template_version_id),
                profile_id=str(part.profile_id), generator_id=str(part.generator_id), question_type=q.question_type,
                difficulty=q.difficulty, render_mode=q.render_mode, content_schema_version=1,
                content_snapshot=q.model_dump_json(), answer_snapshot=canonical(q.answer.model_dump(mode='json')),
                explanation_snapshot=canonical([s.model_dump(mode='json') for s in q.explanation_steps]),
                layout_snapshot=canonical(q.layout.model_dump()), generation_params=canonical(params_of(q).model_dump()),
                seed=part.seed, semantic_signature=signature, created_at=now, updated_at=now))
        session.flush()
        section_positions = {}
        for q, part in zip(questions, owners):
            section_positions[q.question_type] = section_positions.get(q.question_type, 0) + 1
            session.add(QuestionKnowledge(question_id=str(q.id), knowledge_revision_id=str(part.knowledge_revision_id),
                objective_revision_id=str(part.objective_revision_id), role='primary', created_at=now, updated_at=now))
            session.add(PaperQuestion(paper_id=paper.id, question_id=str(q.id), position=q.position,
                section=q.question_type, section_position=section_positions[q.question_type], semantic_signature=signature_of(q), created_at=now, updated_at=now))
        for kind, asset in assets.items():
            file = saved[kind]
            asset.paper_id, asset.status, asset.updated_at = paper.id, 'ready', now
            asset.byte_size, asset.sha256, asset.pages = file.byte_size, file.sha256, file.pages
            asset.renderer_version = metadata['renderer_version']
            asset.metadata_json = canonical({**metadata, 'parser': file.parser, 'pdf_parser_checked': True})
        record_generation_success(session, user, now)
        job.status, job.phase, job.progress_done = 'succeeded', 'done', job.progress_total
        job.finished_at = job.updated_at = now
        job.lease_token = job.lease_until = None
        job.result = canonical({'paper_id': paper.id, **{kind + '_asset_id': asset.id for kind, asset in assets.items()},
            'succeeded_at': serialize_time(now), 'next_generation_at': serialize_time(user.next_generation_at)})
        return paper.id


def fail(engine, claimed, now, code):
    try:
        with write_transaction(engine) as session:
            job = fenced(session, claimed, now)
            fail_assets(session, job, now, code)
            job.status, job.phase, job.error_code = 'failed', 'done', code
            job.finished_at = job.updated_at = now
            job.lease_token = job.lease_until = None
    except LeaseLost:
        pass


def run_once(engine, settings, *, clock=beijing_now, generator=paper_runtime.generate,
             renderer=paper_runtime.render, store=save_pair, fingerprint=None):
    claimed = claim(engine, clock())
    if claimed is None:
        return False
    deadline = time.monotonic() + ATTEMPT_SECONDS
    def pulse():
        if time.monotonic() >= deadline:
            raise TimeoutError('ATTEMPT_TIMEOUT')
        renew(engine, claimed, clock())
        if fingerprint:
            if paper_runtime.config_hash(settings) != fingerprint:
                raise ValueError('RUNTIME_CHANGED')
            paper_runtime.heartbeat(engine, fingerprint, clock())
    try:
        plan = PaperPlan.model_validate_json(claimed['plan'])
        questions = validate_questions(plan, generator(plan, pulse))
        document = {'schema_version': 1, 'title': '纸上练 · 乘法练习', 'generated_at': claimed['generated_at'],
                    'questions': [q.model_dump(mode='json') for q in questions]}
        pulse()
        targets = reserve(engine, claimed, document, clock())
        contents, metadata = renderer(document, settings, pulse)
        check_metadata(document, contents, metadata)
        pulse()
        saving(engine, claimed, clock())
        saved = store(settings.generated_root, targets, contents)
        for file in saved.values():
            read_verified(settings.generated_root, file)
        pulse()
        finish(engine, claimed, document, saved, metadata, clock())
    except LeaseLost:
        pass  # Another attempt owns the job; old files remain private orphans.
    except ServiceError:
        fail(engine, claimed, clock(), 'CONTENT_UNAVAILABLE')
    except TimeoutError:
        fail(engine, claimed, clock(), 'GENERATION_TIMEOUT')
    except (OSError, RuntimeError, ValueError, PdfStorageError):
        fail(engine, claimed, clock(), 'GENERATION_FAILED')
    # Database failures deliberately escape: leave the lease for bounded recovery.
    return True
