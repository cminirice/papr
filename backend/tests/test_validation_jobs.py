from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_content_seed import storage, NOW
from test_template_edit import editor
from app.core.database import write_transaction
from app.models.content import TemplateProfile
from app.models.jobs import Job
from app.models.system import ContentEpoch
from app.models.validation import ValidationFailure, ValidationRun
from app.schemas.validation import ValidationReport
from app.services.validation_jobs import claim, finish, LEASE_SECONDS
from app.validation_child import validate_payload
from app.worker import run_once
from alembic import command
from app.core.time import beijing_now


def submit(editor, key=None):
    _, client, headers, path, _ = editor
    draft = client.get(path).json()['data']
    body = {'lock_version': draft['lock_version'], 'content_hash': draft['content_hash']}
    response = client.post(path + '/validation-jobs', json=body,
                           headers=headers | {'Idempotency-Key': key or str(uuid4())})
    assert response.status_code == 202, response.text
    return response.json()['data'], body


def test_real_subprocess_validation_and_replay(editor):
    engine, client, headers, path, _ = editor
    key = str(uuid4())
    accepted, body = submit(editor, key)
    assert accepted['job_status'] == 'queued' and accepted['report'] is None
    assert run_once(engine, clock=lambda: NOW)
    assert not run_once(engine, clock=lambda: NOW)
    report = client.get('/admin/api/v1/validation-runs/' + accepted['id']).json()['data']
    assert report['status'] == 'passed' and report['job_status'] == 'succeeded'
    assert report['report']['sample_count'] == 1765
    assert len(report['report']['samples']) == 5
    assert [c['exact_capacity'] for c in report['report']['coverage']] == [493, 80100]
    assert all(c['checked_count_options'] == [3, 6, 8, 10, 12] for c in report['report']['coverage'])
    assert report['report']['human_review'] == 'pending'
    replay = client.post(path + '/validation-jobs', json=body, headers=headers | {'Idempotency-Key': key})
    assert replay.status_code == 202 and replay.json()['data']['id'] == accepted['id']
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 1
        assert all(json.loads(p.validated_count_options) == [3, 6, 8, 10, 12] for p in session.scalars(select(TemplateProfile)))
        assert session.get(ContentEpoch, 1).value == 0


def test_same_key_concurrency_conflict_and_queue_bound(editor):
    _, client, headers, path, _ = editor
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(editor, key), range(2)))
    assert results[0][0]['id'] == results[1][0]['id']
    body = results[0][1]
    conflict = client.post(path + '/validation-jobs', json=body | {'lock_version': 2},
                           headers=headers | {'Idempotency-Key': key})
    assert conflict.status_code == 409 and conflict.json()['error']['code'] == 'IDEMPOTENCY_CONFLICT'
    for _ in range(9):
        submit(editor)
    full = client.post(path + '/validation-jobs', json=body, headers=headers | {'Idempotency-Key': str(uuid4())})
    assert full.status_code == 503 and full.json()['error']['code'] == 'QUEUE_FULL'
    assert client.post(path + '/validation-jobs', json=body, headers=headers | {'Idempotency-Key': key}).status_code == 202


def test_edit_during_validation_keeps_old_report_stale(editor):
    engine, client, headers, path, _ = editor
    accepted, body = submit(editor)
    claimed = claim(engine, NOW)
    result = validate_payload(claimed['payload'])
    config = client.get(path).json()['data']['config']
    config['profiles'][0]['layout']['answer_space_mm'] = 40
    assert client.patch(path, json=config, headers=headers).status_code == 200
    assert finish(engine, claimed, NOW, report=result)
    run = client.get('/admin/api/v1/validation-runs/' + accepted['id']).json()['data']
    assert run['status'] == 'stale' and run['report']['result'] == 'passed'
    with Session(engine) as session:
        assert all(p.validated_count_options == '[]' for p in session.scalars(select(TemplateProfile)))


def test_lease_recovery_old_worker_fenced_and_attempt_bound(editor):
    engine, _, _, _, _ = editor
    submit(editor)
    first = claim(engine, NOW)
    assert claim(engine, NOW) is None
    next_time = NOW + timedelta(seconds=LEASE_SECONDS)
    second = claim(engine, next_time)
    assert second['attempt'] == 2 and second['lease_token'] != first['lease_token']
    result = validate_payload(second['payload'])
    assert not finish(engine, first, next_time, report=result)
    assert finish(engine, second, next_time, report=result)
    assert not finish(engine, second, next_time, report=result)
    submit(editor)
    claim(engine, next_time)
    claim(engine, next_time + timedelta(seconds=LEASE_SECONDS))
    assert claim(engine, next_time + timedelta(seconds=LEASE_SECONDS * 2)) is None
    with Session(engine) as session:
        failed = session.scalar(select(Job).where(Job.status == 'failed'))
        assert failed.error_code == 'WORKER_LOST' and failed.attempt == 2


def test_math_failures_are_reports_and_truncated(editor):
    engine, client, headers, path, _ = editor
    config = client.get(path).json()['data']['config']
    config['profiles'][0].update(a_min=111, a_max=111, b_min=11, b_max=11)
    config['test_cases'] = [c for c in config['test_cases'] if c['difficulty'] != 'basic']
    config['test_cases'].append({'code': 'ONE', 'difficulty': 'basic', 'params': {'a': 111, 'b': 11}, 'expected_answer': '1221'})
    assert client.patch(path, json=config, headers=headers).status_code == 200
    accepted, _ = submit(editor)
    assert run_once(engine, clock=lambda: NOW, runner=validate_payload)
    result = client.get('/admin/api/v1/validation-runs/' + accepted['id']).json()['data']
    assert result['status'] == 'failed' and result['job_status'] == 'succeeded'
    assert result['report']['failure_count'] == 101
    assert result['report']['failures_truncated']
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ValidationFailure)) == 100
        assert all(p.validated_count_options == '[]' for p in session.scalars(select(TemplateProfile)))


def test_timeout_marks_job_failed_without_cooldown(editor):
    engine, client, _, _, _ = editor
    accepted, _ = submit(editor)
    def timeout(_):
        raise subprocess.TimeoutExpired('controlled-test', 60)
    assert run_once(engine, clock=lambda: NOW, runner=timeout)
    result = client.get('/admin/api/v1/validation-runs/' + accepted['id']).json()['data']
    assert result['job_status'] == 'failed' and result['error_code'] == 'ENGINE_TIMEOUT'
    assert result['report'] is None


def test_report_auth_and_admission_stale_hash(editor):
    _, client, headers, path, _ = editor
    accepted, body = submit(editor)
    assert client.get(path + '/validation-runs').json()['data']['items'][0]['id'] == accepted['id']
    assert client.post(path + '/validation-jobs', json=body, headers=headers).status_code == 422
    assert client.post(path + '/validation-jobs', json=body | {'content_hash': '0' * 64},
                       headers=headers | {'Idempotency-Key': str(uuid4())}).status_code == 409
    client.cookies.clear()
    assert client.get('/admin/api/v1/validation-runs/' + accepted['id']).status_code == 401


def test_worker_cli_and_populated_migration(editor, storage):
    engine, client, headers, path, _ = editor
    settings, _, migration = storage
    key = str(uuid4())
    accepted, body = submit(editor, key)
    with write_transaction(engine) as session:
        session.get(Job, accepted['job_id']).available_at = beijing_now() - timedelta(seconds=1)
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run([sys.executable, str(root / 'scripts/worker.py'), '--once'],
        cwd=root, env=os.environ | {'PAPR_DB_PATH': str(settings.db_path)}, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert client.get('/admin/api/v1/validation-runs/' + accepted['id']).json()['data']['status'] == 'passed'
    command.check(migration)
    command.downgrade(migration, '0003')
    command.upgrade(migration, 'head')
    with Session(engine) as session:
        assert session.get(Job, accepted['job_id']).status == 'failed'
        assert all(p.validated_count_options == '[]' for p in session.scalars(select(TemplateProfile)))
    replay = client.post(path + '/validation-jobs', json=body, headers=headers | {'Idempotency-Key': key})
    assert replay.status_code == 409
