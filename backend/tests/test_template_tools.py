from datetime import timedelta
from uuid import uuid4
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_content_seed import storage, NOW
from test_template_edit import editor
from app.models.content import TemplateProfile
from app.models.validation import ValidationRun
from app.models.jobs import Job
from app.preview_child import preview
from app.services import preview_jobs
from app.worker import run_once


def create_template(client, headers, code='TEST_NEW_TEMPLATE'):
    choices = client.get('/admin/api/v1/generators').json()['data']
    choice = next(g for g in choices if g['available'])
    body = {'code': code, 'name': '新模板', 'generator_id': choice['id'],
        'objective_revision_id': choice['objective_revision_ids'][0], 'config': choice['default_config'], 'reason': '测试新建模板'}
    response = client.post('/admin/api/v1/templates', headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()['data'], body


def submit_preview(client, headers, draft, *, key=None, count=3):
    return client.post(f'/admin/api/v1/template-versions/{draft["id"]}/preview-jobs',
        headers=headers | {'Idempotency-Key': key or str(uuid4())}, json={
            'lock_version': draft['lock_version'], 'content_hash': draft['content_hash'],
            'difficulty': 'basic', 'count': count, 'seed': 'preview-test'})


def test_new_template_filters_and_unsupported_targets(editor):
    engine, client, headers, *_ = editor
    draft, body = create_template(client, headers)
    assert draft['editable'] and draft['status'] == 'draft'
    assert client.post('/admin/api/v1/templates', headers=headers, json=body).status_code == 409
    assert client.post('/admin/api/v1/templates', headers=headers,
        json=body | {'code': 'INVALID_TARGET', 'objective_revision_id': str(uuid4())}).status_code == 422
    assert client.get('/admin/api/v1/templates?q=TEST_NEW&published=false&status=active').json()['data']['total'] == 1
    assert client.get('/admin/api/v1/templates?q=TEST_NEW&published=true').json()['data']['total'] == 0
    assert client.get('/admin/api/v1/templates?q=%25').json()['data']['total'] == 0
    with Session(engine) as session:
        assert all(p.validated_count_options == '[]' for p in session.scalars(select(TemplateProfile).where(TemplateProfile.template_version_id == draft['id'])))
    client.cookies.clear()
    assert client.get('/admin/api/v1/generators').status_code == 401


def test_real_preview_child_idempotency_and_no_validation_evidence(editor):
    engine, client, headers, *_ = editor
    draft, _ = create_template(client, headers)
    key = str(uuid4())
    response = submit_preview(client, headers, draft, key=key)
    assert response.status_code == 202, response.text
    job = response.json()['data']
    assert submit_preview(client, headers, draft, key=key).json()['data']['id'] == job['id']
    assert submit_preview(client, headers, draft, key=key, count=2).status_code == 409
    assert submit_preview(client, headers, draft, count=11).status_code == 422
    assert run_once(engine, clock=lambda: NOW)
    result = client.get('/admin/api/v1/preview-jobs/' + job['id']).json()['data']
    assert result['status'] == 'succeeded' and len(result['questions']) == 3 and not result['stale']
    assert submit_preview(client, headers, draft, key=key).json()['data'] == result
    assert client.get(f'/admin/api/v1/template-versions/{draft["id"]}/preview-jobs').json()['data']['items'] == [result]
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ValidationRun)) == 0
        assert all(p.validated_count_options == '[]' for p in session.scalars(select(TemplateProfile).where(TemplateProfile.template_version_id == draft['id'])))
    details = client.get('/admin/api/v1/jobs/' + job['id']).json()['data']
    assert details['questions'] == result['questions']
    assert details['job']['template_version_id'] == draft['id']
    assert details['job']['total_count'] == 3


def test_preview_immutable_snapshot_stale_and_lease_recovery(editor):
    engine, client, headers, *_ = editor
    draft, _ = create_template(client, headers)
    submitted = submit_preview(client, headers, draft)
    assert submitted.status_code == 202
    first = preview_jobs.claim(engine, NOW)
    config = draft['config']
    config['profiles'][0]['layout']['questions_per_row'] = 5
    changed = client.patch('/admin/api/v1/template-versions/' + draft['id'], headers=headers, json=config)
    assert changed.status_code == 200, changed.text
    second = preview_jobs.claim(engine, NOW + timedelta(seconds=120))
    assert second['id'] == first['id'] and second['attempt'] == 2
    questions = preview(second['payload'])
    assert all(q.layout.questions_per_row == 2 for q in questions)
    assert not preview_jobs.finish(engine, first, NOW + timedelta(seconds=120), questions=questions)
    assert preview_jobs.finish(engine, second, NOW + timedelta(seconds=120), questions=questions)
    result = client.get('/admin/api/v1/preview-jobs/' + first['id']).json()['data']
    assert result['stale'] and result['status'] == 'succeeded'
    assert submit_preview(client, headers, draft).status_code == 409


def test_preview_worker_failure_and_expired_attempt_limit(editor):
    engine, client, headers, *_ = editor
    draft, _ = create_template(client, headers)
    job = submit_preview(client, headers, draft).json()['data']
    def broken(payload):
        raise ValueError('private path must not be shown')
    assert preview_jobs.run_once(engine, clock=lambda: NOW, runner=broken)
    result = client.get('/admin/api/v1/preview-jobs/' + job['id']).json()['data']
    assert result['status'] == 'failed' and result['error_code'] == 'PREVIEW_ENGINE_ERROR'
    assert 'private' not in str(result)
    submit_preview(client, headers, draft)
    first = preview_jobs.claim(engine, NOW)
    preview_jobs.claim(engine, NOW + timedelta(seconds=120))
    assert preview_jobs.claim(engine, NOW + timedelta(seconds=240)) is None
    with Session(engine) as session:
        assert session.get(Job, first['id']).error_code == 'WORKER_LOST'
