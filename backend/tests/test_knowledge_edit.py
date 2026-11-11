import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_content_seed import storage, NOW
from test_template_edit import editor
from app.models.content import KnowledgePoint


def create_point(client, headers, code='TEST_POINT'):
    body = {'code': code, 'domain': 'operation', 'reason': '测试创建知识点', 'content': {
        'name': '测试知识点', 'definition': '练习整数乘法', 'boundary': '不包括小数',
        'aliases': ['测试别名'], 'misconceptions': ['错误位值'], 'source_id': None}}
    response = client.post('/admin/api/v1/knowledge-points', headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()['data']


def publish(client, headers, kind, row):
    return client.post(f'/admin/api/v1/{kind}-revisions/{row["id"]}/publish',
        headers=headers | {'If-Match': f'"{row["lock_version"]}"'},
        json={'content_hash': row['content_hash'], 'reason': '测试发布修订'})


def test_point_versions_are_immutable_after_publication(editor):
    _, client, headers, *_ = editor
    point = create_point(client, headers)
    original = point['revisions'][0]
    assert point['current_revision_id'] is None and point['status'] == 'draft'
    route = '/admin/api/v1/knowledge-revisions/' + original['id']
    body = original['content'] | {'name': '已编辑草稿', 'reason': '测试编辑'}
    response = client.patch(route, headers=headers, json=body)
    assert response.status_code == 200, response.text
    revised = response.json()['data']
    assert revised['content_hash'] != original['content_hash'] and revised['lock_version'] == 2
    assert client.patch(route, headers=headers, json=body).status_code == 409
    assert publish(client, headers, 'knowledge', revised).status_code == 204
    published = client.get(route).json()['data']
    assert published['status'] == 'published'
    assert client.patch(route, headers=headers | {'If-Match': '"3"'}, json=body).status_code == 409
    point = client.get('/admin/api/v1/knowledge-points/' + point['id']).json()['data']
    assert point['current_revision_id'] == original['id']
    copy = client.post(f'/admin/api/v1/knowledge-points/{point["id"]}/revisions',
        headers=headers | {'If-Match': f'"{point["lock_version"]}"'},
        json={'source_revision_id': original['id'], 'reason': '复制新草稿'})
    assert copy.status_code == 201, copy.text
    current = copy.json()['data']
    assert current['current_revision_id'] == original['id']
    assert current['revisions'][0]['revision_no'] == 2 and current['revisions'][0]['status'] == 'draft'
    assert client.get(route).json()['data'] == published
    assert client.get('/admin/api/v1/knowledge-points?limit=1').json()['data']['total'] == 2


def test_objective_association_and_publication_order(editor):
    _, client, headers, *_ = editor
    first = create_point(client, headers)
    other = create_point(client, headers, 'OTHER_POINT')
    knowledge = first['revisions'][0]
    body = {'code': 'TEST_OBJECTIVE', 'reason': '测试创建目标', 'content': {
        'knowledge_revision_id': other['revisions'][0]['id'], 'name': '目标', 'scope': '整数乘法',
        'success_criteria': ['部分积正确'], 'allowed_prerequisites': []}}
    path = f'/admin/api/v1/knowledge-points/{first["id"]}/objectives'
    assert client.post(path, headers=headers, json=body).status_code == 409
    body['content']['knowledge_revision_id'] = knowledge['id']
    result = client.post(path, headers=headers, json=body)
    assert result.status_code == 201, result.text
    objective = result.json()['data']
    revision = objective['revisions'][0]
    assert publish(client, headers, 'objective', revision).status_code == 409
    assert publish(client, headers, 'knowledge', knowledge).status_code == 204
    assert publish(client, headers, 'objective', revision).status_code == 204
    edit = revision['content'] | {'reason': '不允许改已发布'}
    assert client.patch('/admin/api/v1/objective-revisions/' + revision['id'], json=edit,
        headers=headers | {'If-Match': '"2"'}).status_code == 409
    parent = client.get('/admin/api/v1/objectives/' + objective['id']).json()['data']
    copied = client.post(f'/admin/api/v1/objectives/{parent["id"]}/revisions',
        headers=headers | {'If-Match': f'"{parent["lock_version"]}"'},
        json={'source_revision_id': revision['id'], 'reason': '新版本'})
    assert copied.status_code == 201
    draft = copied.json()['data']['revisions'][0]
    edit['allowed_prerequisites'] = [first['code']]
    assert client.patch('/admin/api/v1/objective-revisions/' + draft['id'], headers=headers, json=edit).status_code == 409
    edit['allowed_prerequisites'] = []
    edit['scope'] = '明确新的范围'
    saved = client.patch('/admin/api/v1/objective-revisions/' + draft['id'], headers=headers, json=edit)
    assert saved.status_code == 200
    assert saved.json()['data']['content_hash'] != draft['content_hash']
    assert client.get(path).json()['data']['total'] == 1


def test_sources_evidence_auth_and_audit_migration_guard(editor, storage):
    engine, client, headers, *_ = editor
    body = {'title': '参考资料', 'reference_note': '本地书目说明', 'reason': '录入资料',
            'verification_status': 'verified'}
    assert client.post('/admin/api/v1/sources', headers=headers, json=body).status_code == 422
    body |= {'checked_at': NOW.isoformat(), 'evidence_note': '人工核验页码', 'published_on': '2026-10-29'}
    response = client.post('/admin/api/v1/sources', headers=headers, json=body)
    assert response.status_code == 201, response.text
    source = response.json()['data']
    assert source['checked_at'].endswith('+08:00')
    assert source['published_on'] == '2026-10-29'
    path = '/admin/api/v1/sources/' + source['id']
    assert client.patch(path, headers=headers, json=body | {'title': '更新出处'}).status_code == 200
    assert client.patch(path, headers=headers, json=body).status_code == 409
    point = create_point(client, headers)
    revision = point['revisions'][0]
    linked = client.patch('/admin/api/v1/knowledge-revisions/' + revision['id'], headers=headers,
        json=revision['content'] | {'source_id': source['id'], 'reason': '绑定出处'})
    assert linked.status_code == 200
    assert client.get('/admin/api/v1/sources?limit=1').json()['data']['total'] == 2
    assert client.patch(path, headers={'Origin': headers['Origin'], 'If-Match': '"2"'}, json=body).status_code == 403
    with engine.connect() as connection:
        assert connection.execute(text('PRAGMA foreign_key_check')).all() == []
        assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == ScriptDirectory.from_config(storage[2]).get_current_head()
        assert connection.execute(text("SELECT count(*) FROM admin_operation_log WHERE target_type='content_source'")).scalar_one() == 2
    with pytest.raises(RuntimeError, match='不能自动降级'):
        command.downgrade(storage[2], '0008')
    client.cookies.clear()
    assert client.get('/admin/api/v1/sources').status_code == 401
    assert client.get('/admin/api/v1/knowledge-points').status_code == 401


def test_knowledge_audit_migration_empty_roundtrip(storage):
    _, _, config = storage
    command.check(config)
    command.downgrade(config, '0008')
    command.upgrade(config, 'head')
    command.check(config)
