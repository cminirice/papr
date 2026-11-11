from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from uuid import uuid4
import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_content_seed import storage, NOW
from test_template_edit import editor
from test_validation_jobs import submit
from app.core.database import write_transaction
from app.models.content import GeneratorDefinition, QuestionTemplate, TemplateVersion
from app.models.releases import AdminOperationLog, ContentRelease, ContentReview
from app.models.system import ContentEpoch
from app.validation_child import validate_payload
from app.worker import run_once
from alembic import command


@pytest.fixture
def ready(editor):
    engine, client, headers, path, imported = editor
    accepted, _ = submit(editor)
    assert run_once(engine, clock=lambda: NOW, runner=validate_payload)
    run = client.get('/admin/api/v1/validation-runs/' + accepted['id']).json()['data']
    request = {'validation_run_id': run['id'], 'content_hash': run['content_hash'], 'decision': 'approved',
               'comment': '测试模拟人工审题，不代表实际内容已审定',
               'sample_refs': [q['id'] for q in run['report']['samples']], 'print_checked': True}
    return editor, run, request


def prerequisites(editor):
    _, client, headers, path, _ = editor
    context = client.get(path + '/release-context').json()['data']
    for dependency in context['dependencies']:
        resource = 'knowledge-revisions' if dependency['kind'] == 'knowledge_revision' else 'objective-revisions'
        response = client.post(f"/admin/api/v1/{resource}/{dependency['id']}/publish",
            json={'content_hash': dependency['content_hash'], 'reason': '测试修订发布'},
            headers=headers | {'If-Match': f'"{dependency["lock_version"]}"'})
        assert response.status_code == 204, response.text


def approve(ready):
    editor, run, request = ready
    _, client, headers, path, _ = editor
    review = client.post(path + '/reviews', json=request, headers=headers)
    assert review.status_code == 200, review.text
    return {'version_id': run['template_version_id'], 'validation_run_id': run['id'],
            'review_id': review.json()['data']['id'], 'reason': '测试发布'}


def test_publish_disable_enable_audit_atomicity(ready):
    editor, _, _ = ready
    engine, client, headers, path, imported = editor
    payload = approve(ready)
    route = '/admin/api/v1/templates/' + imported['template_id']
    assert client.post(route + '/publish', json=payload, headers=headers).status_code == 409
    with Session(engine) as session:
        assert session.get(ContentEpoch, 1).value == 0
        assert session.scalar(select(func.count()).select_from(ContentRelease)) == 0
    prerequisites(editor)
    response = client.post(route + '/publish', json=payload, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()['data']['epoch'] == 3
    assert client.post(route + '/publish', json=payload, headers=headers).status_code == 409
    draft = client.get(path).json()['data']
    assert not draft['editable'] and draft['status'] == 'published'
    assert client.patch(path, json=draft['config'], headers=headers | {'If-Match': '"2"'}).status_code == 409
    assert client.post(route + '/disable', json={'reason': '检查停用'}, headers=headers | {'If-Match': '"2"'}).status_code == 200
    assert client.post(route + '/enable', json=payload, headers=headers | {'If-Match': '"3"'}).status_code == 200
    with Session(engine) as session:
        template = session.get(QuestionTemplate, imported['template_id'])
        assert template.current_published_version_id == imported['template_version_id']
        assert template.lock_version == 4 and session.get(ContentEpoch, 1).value == 5
        assert session.scalar(select(func.count()).select_from(ContentRelease)) == 3
        assert session.scalar(select(func.count()).select_from(AdminOperationLog)) == 6


def test_review_requires_explicit_print_and_all_sample_refs(ready):
    editor, _, request = ready
    engine, client, headers, path, _ = editor
    for invalid in [request | {'print_checked': False}, request | {'sample_refs': [str(uuid4())]},
                    request | {'sample_refs': request['sample_refs'][:1]}, request | {'comment': '  '}]:
        assert client.post(path + '/reviews', json=invalid, headers=headers).status_code == 422
    assert client.post(path + '/reviews', json=request, headers={'Origin': headers['Origin']}).status_code == 403
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ContentReview)) == 0


def test_rejection_supersedes_old_approval(ready):
    editor, _, request = ready
    engine, client, headers, path, imported = editor
    payload = approve(ready)
    rejection = client.post(path + '/reviews', json=request | {'decision': 'rejected', 'print_checked': False}, headers=headers)
    assert rejection.status_code == 200
    prerequisites(editor)
    response = client.post('/admin/api/v1/templates/' + imported['template_id'] + '/publish', json=payload, headers=headers)
    assert response.status_code == 409
    with Session(engine) as session:
        assert session.get(QuestionTemplate, imported['template_id']).current_published_version_id is None
        assert session.scalar(select(func.count()).select_from(ContentReview)) == 2


def test_edited_hash_and_generator_unavailable_block_release(ready):
    editor, _, _ = ready
    engine, client, headers, path, imported = editor
    payload = approve(ready)
    prerequisites(editor)
    route = '/admin/api/v1/templates/' + imported['template_id'] + '/publish'
    with write_transaction(engine) as session:
        session.scalar(select(GeneratorDefinition)).deployment_status = 'unavailable'
    assert client.post(route, json=payload, headers=headers).status_code == 409
    with write_transaction(engine) as session:
        session.scalar(select(GeneratorDefinition)).deployment_status = 'available'
    config = client.get(path).json()['data']['config']
    config['profiles'][0]['layout']['answer_space_mm'] = 40
    assert client.patch(path, json=config, headers=headers).status_code == 200
    assert client.post(route, json=payload, headers=headers).status_code == 409
    with Session(engine) as session:
        assert session.get(ContentEpoch, 1).value == 2


def test_parallel_publish_single_epoch_and_release(ready):
    editor, _, _ = ready
    engine, client, headers, _, imported = editor
    payload = approve(ready)
    prerequisites(editor)
    route = '/admin/api/v1/templates/' + imported['template_id'] + '/publish'
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(route, json=payload, headers=headers), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 409]
    with Session(engine) as session:
        assert session.get(ContentEpoch, 1).value == 3
        assert session.scalar(select(func.count()).select_from(ContentRelease)) == 1


def test_dependency_order_hash_and_if_match(ready):
    editor, _, _ = ready
    _, client, headers, path, _ = editor
    dependencies = client.get(path + '/release-context').json()['data']['dependencies']
    objective = next(item for item in dependencies if item['kind'] == 'objective_revision')
    route = f"/admin/api/v1/objective-revisions/{objective['id']}/publish"
    body = {'content_hash': objective['content_hash'], 'reason': '先修顺序检查'}
    assert client.post(route, json=body, headers=headers).status_code == 409
    assert client.post(route, json=body, headers=headers | {'If-Match': '*'}).status_code == 422
    knowledge = next(item for item in dependencies if item['kind'] == 'knowledge_revision')
    assert client.post(f"/admin/api/v1/knowledge-revisions/{knowledge['id']}/publish",
        json=body, headers=headers).status_code == 409


def test_clone_publish_new_version_and_rollback(ready):
    editor, _, old_request = ready
    engine, client, headers, _, imported = editor
    original_payload = approve(ready)
    prerequisites(editor)
    route = '/admin/api/v1/templates/' + imported['template_id']
    assert client.post(route + '/publish', json=original_payload, headers=headers).status_code == 200
    cloned = client.post(route + '/versions', json={'source_version_id': imported['template_version_id']},
                         headers=headers | {'If-Match': '"2"'})
    assert cloned.status_code == 200, cloned.text
    version = cloned.json()['data']
    assert version['version_no'] == 2 and version['status'] == 'draft'
    new_path = '/admin/api/v1/template-versions/' + version['id']
    assert client.get(new_path + '/release-context').json()['data']['reviews'] == []
    assert client.post(route + '/versions', json={'source_version_id': imported['template_version_id']},
                       headers=headers | {'If-Match': '"3"'}).status_code == 409
    request = {'lock_version': version['lock_version'], 'content_hash': version['content_hash']}
    accepted = client.post(new_path + '/validation-jobs', json=request, headers=headers | {'Idempotency-Key': str(uuid4())})
    assert accepted.status_code == 202
    assert run_once(engine, clock=lambda: NOW, runner=validate_payload)
    run = client.get('/admin/api/v1/validation-runs/' + accepted.json()['data']['id']).json()['data']
    new_review = client.post(new_path + '/reviews', json=old_request | {'validation_run_id': run['id'],
                            'sample_refs': [q['id'] for q in run['report']['samples']]}, headers=headers)
    assert new_review.status_code == 200, new_review.text
    payload = {'version_id': version['id'], 'validation_run_id': run['id'],
               'review_id': new_review.json()['data']['id'], 'reason': '测试第二版'}
    assert client.post(route + '/publish', json=payload, headers=headers | {'If-Match': '"3"'}).status_code == 200
    assert client.post(route + '/rollback', json=original_payload, headers=headers | {'If-Match': '"4"'}).status_code == 200
    with Session(engine) as session:
        assert session.get(QuestionTemplate, imported['template_id']).current_published_version_id == imported['template_version_id']
        assert session.get(TemplateVersion, version['id']).status == 'published'
        assert session.get(ContentEpoch, 1).value == 5


def test_audit_failure_rolls_back_pointer_epoch_and_release(ready, monkeypatch):
    editor, _, _ = ready
    engine, client, headers, _, imported = editor
    payload = approve(ready)
    prerequisites(editor)
    import app.services.releases as service
    def failed_audit(*args, **kwargs):
        raise RuntimeError('模拟审计落库失败')
    monkeypatch.setattr(service, 'audit', failed_audit)
    with pytest.raises(RuntimeError, match='审计落库'):
        client.post('/admin/api/v1/templates/' + imported['template_id'] + '/publish', json=payload, headers=headers)
    with Session(engine) as session:
        assert session.get(QuestionTemplate, imported['template_id']).current_published_version_id is None
        assert session.get(TemplateVersion, imported['template_version_id']).status == 'draft'
        assert session.get(ContentEpoch, 1).value == 2
        assert session.scalar(select(func.count()).select_from(ContentRelease)) == 0


def test_populated_release_migration(ready, storage):
    editor, _, _ = ready
    engine, client, headers, _, imported = editor
    payload = approve(ready)
    prerequisites(editor)
    assert client.post('/admin/api/v1/templates/' + imported['template_id'] + '/publish', json=payload, headers=headers).status_code == 200
    _, _, migration = storage
    command.check(migration)
    command.downgrade(migration, '0004')
    command.upgrade(migration, 'head')
    with Session(engine) as session:
        assert session.get(QuestionTemplate, imported['template_id']).status == 'disabled'
        assert session.scalar(select(func.count()).select_from(ContentReview)) == 0
