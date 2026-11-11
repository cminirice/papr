from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from test_content_seed import storage, NOW, PASSWORD  # Shared temporary-file fixture.
from app.auth.security import initialize_rate_key
from app.core.database import write_transaction
from app.main import create_app
from app.models.content import TemplateProfile, TemplateVersion, GeneratorDefinition
from app.models.identity import AdminUser
from app.models.system import ContentEpoch
from app.services.content_seed import seed_content

ORIGIN = 'http://127.0.0.1:5174'


@pytest.fixture
def editor(storage):
    settings, engine, _ = storage
    imported = seed_content(engine, 'owner', NOW)
    initialize_rate_key(settings.rate_limit_key_path)
    app = create_app(settings)
    app.state.clock = lambda: NOW
    with TestClient(app, base_url=ORIGIN, client=('127.0.0.1', 1234)) as client:
        response = client.post('/admin/api/v1/session/login', json={'username': 'owner', 'password': PASSWORD}, headers={'Origin': ORIGIN})
        assert response.status_code == 200
        headers = {'Origin': ORIGIN, 'X-CSRF-Token': response.json()['data']['csrf_token'], 'If-Match': '"1"'}
        path = f"/admin/api/v1/template-versions/{imported['template_version_id']}"
        yield engine, client, headers, path, imported


def test_detail_save_hash_and_validation_invalidation(editor):
    engine, client, headers, path, imported = editor
    template = client.get(f"/admin/api/v1/templates/{imported['template_id']}")
    assert template.json()['data']['versions'][0]['id'] == imported['template_version_id']
    response = client.get(path)
    assert response.headers['etag'] == '"1"'
    original = response.json()['data']
    body = deepcopy(original['config'])
    body['profiles'][0]['layout']['answer_space_mm'] = 40
    with write_transaction(engine) as session:
        for profile in session.scalars(select(TemplateProfile)):
            profile.validated_count_options = '[3,6]'
    saved = client.patch(path, json=body, headers=headers)
    assert saved.status_code == 200, saved.text
    data = saved.json()['data']
    assert data['lock_version'] == 2 and saved.headers['etag'] == '"2"'
    assert data['content_hash'] != original['content_hash']
    assert data['updated_at'].endswith('+08:00')
    assert data['config']['profiles'][0]['layout']['answer_space_mm'] == 40
    with Session(engine) as session:
        assert all(json.loads(p.validated_count_options) == [] for p in session.scalars(select(TemplateProfile)))
        assert session.get(ContentEpoch, 1).value == 0
    reordered = deepcopy(body)
    reordered['profiles'].reverse()
    reordered['test_cases'].reverse()
    again = client.patch(path, json=reordered, headers=headers | {'If-Match': '"2"'})
    assert again.status_code == 200
    assert again.json()['data']['content_hash'] == data['content_hash']
    assert client.patch(path, json=body, headers=headers).json()['error']['code'] == 'EDIT_CONFLICT'


def test_atomic_invalid_cases_and_protected_fields(editor):
    _, client, headers, path, _ = editor
    original = client.get(path).json()['data']
    body = original['config']
    invalid = deepcopy(body)
    invalid['profiles'][0]['layout']['answer_space_mm'] = 45
    invalid['test_cases'][0]['expected_answer'] = '1'
    assert client.patch(path, json=invalid, headers=headers).status_code == 422
    for key, value in [('status', 'published'), ('content_hash', '0' * 64), ('validated_count_options', [12])]:
        assert client.patch(path, json=body | {key: value}, headers=headers).status_code == 422
    invalid = deepcopy(body)
    invalid['profiles'][0]['difficulty'] = 'challenge'
    assert client.patch(path, json=invalid, headers=headers).status_code == 422
    assert client.get(path).json()['data'] == original


def test_fixed_cases_replaced_as_one_aggregate(editor):
    _, client, headers, path, _ = editor
    body = client.get(path).json()['data']['config']
    body['test_cases'] = [c for c in body['test_cases'] if c['difficulty'] != 'basic']
    body['test_cases'].append({'code': 'NEW_BASIC', 'difficulty': 'basic',
                              'params': {'a': 111, 'b': 12}, 'expected_answer': '1332'})
    saved = client.patch(path, json=body, headers=headers)
    assert saved.status_code == 200
    cases = saved.json()['data']['config']['test_cases']
    assert len(cases) == 5 and any(c['code'] == 'NEW_BASIC' for c in cases)
    duplicate = deepcopy(body)
    duplicate['test_cases'].append(duplicate['test_cases'][0])
    assert client.patch(path, json=duplicate, headers=headers | {'If-Match': '"2"'}).status_code == 422


def test_concurrent_saves_have_one_winner(editor):
    _, client, headers, path, _ = editor
    original = client.get(path).json()['data']['config']
    def save(size):
        body = deepcopy(original)
        body['profiles'][0]['layout']['answer_space_mm'] = size
        return client.patch(path, json=body, headers=headers)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(save, [40, 50]))
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert client.get(path).json()['data']['lock_version'] == 2


@pytest.mark.parametrize('status', ['published', 'retired'])
def test_immutable_versions(editor, status):
    engine, client, headers, path, _ = editor
    body = client.get(path).json()['data']['config']
    with write_transaction(engine) as session:
        admin_id = session.scalar(select(AdminUser)).id
        version = session.scalar(select(TemplateVersion))
        version.status = status
        if status == 'published':
            version.published_by = admin_id
            version.published_at = NOW
    assert client.get(path).json()['data']['editable'] is False
    response = client.patch(path, json=body, headers=headers)
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'CONTENT_UNAVAILABLE'


def test_auth_etag_and_generator_availability(editor):
    engine, client, headers, path, _ = editor
    body = client.get(path).json()['data']['config']
    assert client.patch(path, json=body, headers={'Origin': ORIGIN}).status_code == 403
    for value in ('1', '*', 'W/"1"', '"0"'):
        assert client.patch(path, json=body, headers=headers | {'If-Match': value}).status_code == 422
    missing = {k: v for k, v in headers.items() if k != 'If-Match'}
    assert client.patch(path, json=body, headers=missing).status_code == 422
    assert client.get(f'/admin/api/v1/template-versions/{uuid4()}').status_code == 404
    with write_transaction(engine) as session:
        session.scalar(select(GeneratorDefinition)).deployment_status = 'unavailable'
    assert client.patch(path, json=body, headers=headers).status_code == 409


def test_admin_revoked_during_math_validation(editor, monkeypatch):
    engine, client, headers, path, _ = editor
    import app.services.template_edit as service
    original = client.get(path).json()['data']
    actual = service.build_question
    revoked = False
    def revoke(*args, **kwargs):
        nonlocal revoked
        if not revoked:
            with write_transaction(engine) as session:
                session.scalar(select(AdminUser)).status = 'disabled'
            revoked = True
        return actual(*args, **kwargs)
    monkeypatch.setattr(service, 'build_question', revoke)
    response = client.patch(path, json=original['config'], headers=headers)
    assert response.status_code == 401
    with Session(engine) as session:
        version = session.scalar(select(TemplateVersion))
        assert version.lock_version == 1 and version.content_hash == original['content_hash']


def test_row_counts_persist_per_difficulty_and_reject_invalid_values(editor):
    from app.generators.multiplication import build_question
    from app.schemas.content import MultiplicationProfile, MultiplicationParams
    engine, client, headers, path, _ = editor
    original = client.get(path).json()['data']
    body = deepcopy(original['config'])
    basic = next(p for p in body['profiles'] if p['difficulty'] == 'basic')
    standard = next(p for p in body['profiles'] if p['difficulty'] == 'standard')
    assert basic['layout']['questions_per_row'] == 2 and basic['layout']['solutions_per_row'] == 1
    old_question = build_question(MultiplicationProfile.model_validate(basic), MultiplicationParams(a=123, b=12), seed="row-layout-check")
    for field in ('questions_per_row', 'solutions_per_row'):
        for invalid in (0, 6, True, '2', 1.5):
            changed = deepcopy(body)
            changed['profiles'][0]['layout'][field] = invalid
            assert client.patch(path, json=changed, headers=headers).status_code == 422
    basic['layout'].update(questions_per_row=5, solutions_per_row=4)
    standard['layout'].update(questions_per_row=3, solutions_per_row=1)
    with write_transaction(engine) as session:
        for profile in session.scalars(select(TemplateProfile)):
            profile.validated_count_options = '[3,6]'
    response = client.patch(path, json=body, headers=headers)
    assert response.status_code == 200, response.text
    saved = response.json()['data']
    assert saved['content_hash'] != original['content_hash']
    reloaded = client.get(path).json()['data']
    assert reloaded == saved
    for profile in reloaded['config']['profiles']:
        expected = basic if profile['difficulty'] == 'basic' else standard
        assert profile['layout'] == expected['layout']
    with Session(engine) as session:
        for profile in session.scalars(select(TemplateProfile)):
            assert json.loads(profile.layout_config)['questions_per_row'] == (5 if profile.difficulty == 'basic' else 3)
            assert profile.validated_count_options == '[]'
    new_question = build_question(MultiplicationProfile.model_validate(basic), MultiplicationParams(a=123, b=12), seed="row-layout-check")
    assert new_question.layout.questions_per_row == 5 and new_question.layout.solutions_per_row == 4
    assert old_question.layout.questions_per_row == 2 and old_question.layout.solutions_per_row == 1
