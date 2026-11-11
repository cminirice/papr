from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_content_seed import storage, NOW
from test_template_edit import editor
from test_releases import ready
from test_capabilities import opened, set_policy, user_headers, select_body
from app.core.database import write_transaction
from app.core.errors import ServiceError
from app.models.identity import AppUser, RateLimitEvent
from app.models.jobs import Job
from app.models.system import ContentEpoch
from app.schemas.paper_jobs import PaperPlan
from app.services import paper_jobs
from app.generators.multiplication import generate_paper


@pytest.fixture
def prepared(opened):
    editor, catalog, node, point, payload = opened
    engine, client, headers, _, imported = editor
    set_policy(opened)
    user = user_headers(client, headers)
    effective = client.post('/api/v1/capabilities', json=select_body(node, point), headers=user).json()['data']
    body = select_body(node, point) | {'question_type_counts': {'choice': 0, 'fill': 0, 'answer': 3},
                                     'content_epoch': effective['content_epoch']}
    return engine, client, user, body, headers, imported


@pytest.fixture
def admission(prepared, monkeypatch):
    # Only the tests enable admission; no production flag may queue jobs without a PDF executor.
    monkeypatch.setattr(paper_jobs, 'executor_ready', lambda *args: True)
    return prepared


def submit(fixture, key=None, body=None):
    _, client, headers, original, *_ = fixture
    return client.post('/api/v1/paper-jobs', json=body or original,
                       headers=headers | {'Idempotency-Key': key or str(uuid4())})


def test_pdf_not_ready_never_queues_or_reserves_ip(prepared):
    engine, client, headers, body, *_ = prepared
    response = submit(prepared)
    assert response.status_code == 503 and response.json()['error']['code'] == 'SERVICE_NOT_READY'
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Job).where(Job.kind == 'paper_generate')) == 0
        assert session.scalar(select(func.count()).select_from(RateLimitEvent).where(RateLimitEvent.action == 'generation_accept')) == 0
        user = session.scalar(select(AppUser))
        assert user.next_generation_at is None and user.last_generation_succeeded_at is None


def test_snapshot_idempotency_and_no_math_at_acceptance(admission):
    engine, client, headers, body, *_ = admission
    key = str(uuid4())
    response = submit(admission, key)
    assert response.status_code == 202, response.text
    data = response.json()['data']
    assert data['status'] == 'queued' and data['phase'] == 'queued' and data['attempt'] == 0
    assert not {'payload', 'seed', 'profile', 'owner_user_id', 'intermediate_snapshot'} & data.keys()
    again = submit(admission, key)
    assert again.json()['data'] == data
    changed = body | {'question_type_counts': {'choice': 0, 'fill': 0, 'answer': 6}}
    assert submit(admission, key, changed).status_code == 409
    with Session(engine) as session:
        job = session.get(Job, data['id'])
        plan = PaperPlan.model_validate_json(job.payload)
        assert job.intermediate_snapshot is None
        assert plan.request.model_dump(mode='json') == body and len(plan.seed) == 32
        assert plan.catalog_snapshot['verification_status'] == 'provisional'
        assert plan.content_hash and plan.profile_hash and plan.generator_artifact_hash
        paper_jobs.check_snapshot_current(session, plan)
        assert session.scalar(select(func.count()).select_from(RateLimitEvent).where(RateLimitEvent.action == 'generation_accept')) == 1
    # Outside all write transactions: fixed seed/profile reproduces the same content.
    first = generate_paper(plan.profile, seed=plan.seed, count=3)
    assert first == generate_paper(plan.profile, seed=plan.seed, count=3)
    current = client.get('/api/v1/session').json()['data']
    assert current['active_job_id'] == data['id'] and not current['can_generate']
    assert current['next_generation_at'] is None


def test_concurrent_keys_and_same_key_replay(admission):
    engine, client, headers, body, *_ = admission
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: submit(admission, key), range(2)))
    assert all(r.status_code == 202 for r in responses)
    identity = responses[0].json()['data']['id']
    assert responses[1].json()['data']['id'] == identity
    assert client.post(f'/api/v1/jobs/{identity}/cancel', json={}, headers=headers).status_code == 200
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: submit(admission), range(2)))
    assert sorted(r.status_code for r in responses) == [202,409]
    assert next(r for r in responses if r.status_code == 409).json()['error']['code'] == 'ACTIVE_JOB_EXISTS'


def test_cancel_replay_works_when_executor_off_and_epoch_changed(admission, monkeypatch):
    engine, client, headers, body, *_ = admission
    key = str(uuid4())
    identity = submit(admission, key).json()['data']['id']
    response = client.post(f'/api/v1/jobs/{identity}/cancel', json={}, headers=headers)
    assert response.status_code == 200 and response.json()['data']['status'] == 'cancelled'
    assert client.post(f'/api/v1/jobs/{identity}/cancel', json={}, headers=headers).json()['data'] == response.json()['data']
    with write_transaction(engine) as session:
        session.get(ContentEpoch, 1).value += 1
    monkeypatch.setattr(paper_jobs, 'executor_ready', lambda *args: False)
    replay = submit(admission, key)
    assert replay.status_code == 200 and replay.json()['data']['status'] == 'cancelled'
    current = client.get('/api/v1/session').json()['data']
    assert current['next_generation_at'] is None and current['can_generate']


def test_failed_task_new_key_and_599_600_boundary(admission):
    engine, client, headers, body, *_ = admission
    key = str(uuid4())
    identity = submit(admission, key).json()['data']['id']
    # Simulate a terminal executor failure, not a real PDF test.
    with write_transaction(engine) as session:
        job = session.get(Job, identity)
        job.status, job.phase, job.finished_at = 'failed', 'done', NOW
        job.error_code, job.error_message = 'PDF_FAILED', '/private/should/not/leak'
    replay = submit(admission, key)
    assert replay.status_code == 200 and '/private' not in replay.text
    response = submit(admission)
    assert response.status_code == 202
    identity = response.json()['data']['id']
    assert client.post(f'/api/v1/jobs/{identity}/cancel', json={}, headers=headers).status_code == 200
    with write_transaction(engine) as session:
        user = session.scalar(select(AppUser))
        user.last_generation_succeeded_at = NOW
        user.next_generation_at = NOW + timedelta(seconds=600)
    client.app.state.clock = lambda: NOW + timedelta(seconds=599)
    response = submit(admission)
    assert response.status_code == 429 and response.headers['retry-after'] == '1'
    client.app.state.clock = lambda: NOW + timedelta(seconds=600)
    assert submit(admission).status_code == 202


def test_stale_epoch_unsupported_counts_and_stopped_template(admission):
    engine, client, headers, body, admin, imported = admission
    response = submit(admission, body=body | {'content_epoch': body['content_epoch'] - 1})
    assert response.status_code == 409 and response.json()['error']['code'] == 'CAPABILITY_CHANGED'
    response = submit(admission, body=body | {'question_type_counts': {'choice': 0, 'fill': 0, 'answer': 8}})
    assert response.status_code == 422
    identity = submit(admission).json()['data']['id']
    with Session(engine) as session:
        plan = PaperPlan.model_validate_json(session.get(Job, identity).payload)
    response = client.post('/admin/api/v1/templates/' + imported['template_id'] + '/disable',
                           json={'reason': '测试任务最终检查'}, headers=admin | {'If-Match': '"2"'})
    assert response.status_code == 200
    with Session(engine) as session:
        with pytest.raises(ServiceError) as error:
            paper_jobs.check_snapshot_current(session, plan)
        assert error.value.code == 'CONTENT_UNAVAILABLE'
        assert session.get(Job, identity).payload == plan.model_dump_json()


def test_queue_ip_bounds_rollback_and_replay(admission, monkeypatch):
    engine, client, headers, body, *_ = admission
    monkeypatch.setattr(paper_jobs, 'setting_value', lambda *_: SimpleNamespace(queue_limit=0, ip_accept_limit=12))
    assert submit(admission).json()['error']['code'] == 'QUEUE_FULL'
    monkeypatch.setattr(paper_jobs, 'setting_value', lambda *_: SimpleNamespace(queue_limit=10, ip_accept_limit=1))
    key = str(uuid4())
    identity = submit(admission, key).json()['data']['id']
    assert client.post(f'/api/v1/jobs/{identity}/cancel', json={}, headers=headers).status_code == 200
    assert submit(admission, key).status_code == 200
    assert submit(admission).json()['error']['code'] == 'RATE_LIMITED'
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Job).where(Job.kind == 'paper_generate')) == 1
        assert session.scalar(select(AppUser)).next_generation_at is None


def test_authorization_running_cancel_and_pagination(admission):
    engine, client, headers, body, admin, imported = admission
    ids = []
    for _ in range(3):
        identity = submit(admission).json()['data']['id']; ids.append(identity)
        assert client.post(f'/api/v1/jobs/{identity}/cancel', json={}, headers=headers).status_code == 200
    response = client.get('/api/v1/jobs?limit=2')
    data = response.json()['data']
    assert data['has_more'] and len(data['items']) == 2
    page = client.get('/api/v1/jobs', params={'limit': 2, 'cursor': data['next_cursor']}).json()['data']
    assert not page['has_more'] and len(page['items']) == 1
    assert {j['id'] for j in data['items'] + page['items']} == set(ids)
    assert client.get('/api/v1/jobs?status=failed').json()['data']['items'] == []
    for cursor in ('bad', '!!!!', 'e30', 'bnVsbA'):
        assert client.get('/api/v1/jobs', params={'cursor': cursor}).status_code == 422
    identity = submit(admission).json()['data']['id']
    with write_transaction(engine) as session:
        job = session.get(Job, identity)
        job.status, job.phase, job.attempt = 'running', 'rendering', 1
        job.lease_token, job.lease_until = str(uuid4()), NOW + timedelta(seconds=120)
    assert client.post(f'/api/v1/jobs/{identity}/cancel', json={}, headers=headers).json()['error']['code'] == 'JOB_NOT_CANCELLABLE'
    assert client.post(f'/api/v1/jobs/{identity}/cancel', json={}, headers={'Origin': headers['Origin']}).status_code == 403
    with Session(engine) as session:
        validate_job = session.scalar(select(Job.id).where(Job.kind == 'template_validate'))
    assert client.get(f'/api/v1/jobs/{validate_job}').status_code == 404
    client.cookies.clear()
    assert client.get(f'/api/v1/jobs/{identity}').status_code == 401
    other = user_headers(client, admin)
    assert client.get(f'/api/v1/jobs/{identity}').status_code == 404
    assert client.post(f'/api/v1/jobs/{identity}/cancel', json={}, headers=other).status_code == 404
    assert client.get('/api/v1/jobs').json()['data']['items'] == []


def test_admission_commit_failure_rolls_back_job_and_rate_event(admission, monkeypatch):
    from sqlalchemy import event
    engine, client, *_ = admission
    def fail_insert(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith('INSERT INTO job'):
            raise RuntimeError('模拟任务落库失败')
    event.listen(client.app.state.engine, 'before_cursor_execute', fail_insert)
    try:
        with pytest.raises(RuntimeError, match='模拟任务落库失败'):
            submit(admission)
    finally:
        event.remove(client.app.state.engine, 'before_cursor_execute', fail_insert)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Job).where(Job.kind == 'paper_generate')) == 0
        assert session.scalar(select(func.count()).select_from(RateLimitEvent).where(RateLimitEvent.action == 'generation_accept')) == 0
        assert session.scalar(select(AppUser)).next_generation_at is None
