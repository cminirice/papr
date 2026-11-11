from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from uuid import uuid4
import pytest
from alembic import command
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from test_content_seed import storage, NOW
from test_template_edit import editor
from test_releases import ready, approve, prerequisites
from app.core.database import write_transaction
from app.models.content import CatalogNode, ContentCatalog, KnowledgePoint, GeneratorDefinition, TemplateProfile
from app.models.policies import KnowledgeTypePolicy
from app.models.releases import AdminOperationLog
from app.models.system import ContentEpoch


def identifiers(engine):
    with Session(engine) as session:
        node = session.scalar(select(CatalogNode))
        return node.catalog_id, node.id, session.scalar(select(KnowledgePoint.id))


def matrix(client, point):
    response = client.get(f'/admin/api/v1/knowledge-points/{point}/capabilities')
    assert response.status_code == 200, response.text
    return response.json()['data']


def policy_body(view):
    return {'reason': '测试显式开放经过验证的题量', 'policies': [
        {k: p[k] for k in ('difficulty', 'question_type', 'count_options', 'default_count')} for p in view['policies']]}


def enable(client, headers, catalog, node):
    for route in (f'/admin/api/v1/catalogs/{catalog}', f'/admin/api/v1/catalog-nodes/{node}'):
        response = client.patch(route, json={'status': 'active', 'reason': '测试目录开放'}, headers=headers)
        assert response.status_code == 204, response.text


def user_headers(client, headers):
    origin = {'Origin': 'http://127.0.0.1:5173'}
    response = client.post('/api/v1/session', json={}, headers=origin)
    assert response.status_code == 200
    return origin | {'X-CSRF-Token': response.json()['data']['csrf_token']}


@pytest.fixture
def opened(ready):
    editor, _, _ = ready
    engine, client, headers, _, imported = editor
    payload = approve(ready)
    prerequisites(editor)
    assert client.post('/admin/api/v1/templates/' + imported['template_id'] + '/publish', json=payload, headers=headers).status_code == 200
    catalog, node, point = identifiers(engine)
    enable(client, headers, catalog, node)
    return editor, catalog, node, point, payload


def set_policy(opened, counts=(3, 6, 12)):
    editor, _, _, point, _ = opened
    _, client, headers, _, _ = editor
    view = matrix(client, point)
    body = policy_body(view)
    for cell in body['policies']:
        if cell['question_type'] == 'answer' and cell['difficulty'] in ('basic', 'standard'):
            cell['count_options'], cell['default_count'] = list(counts), counts[0] if counts else None
    response = client.put(f'/admin/api/v1/knowledge-points/{point}/quantity-policies', json=body,
                          headers=headers | {'If-Match': f'"{view["lock_version"]}"'})
    assert response.status_code == 200, response.text
    return response.json()['data']


def select_body(node, point, difficulty='basic'):
    return {'theme_id': node, 'knowledge_point_ids': [point], 'difficulty': difficulty}


def test_drafts_hidden_and_authenticated_policy_only(editor):
    engine, client, headers, _, _ = editor
    catalog, node, point = identifiers(engine)
    assert client.get('/api/v1/catalogs').json()['data'] == []
    assert client.get(f'/api/v1/catalogs/{catalog}/themes').status_code == 404
    assert client.get(f'/api/v1/themes/{node}/knowledge-points').status_code == 404
    assert client.post('/api/v1/capabilities', json=select_body(node, point), headers={'Origin': 'http://127.0.0.1:5173'}).status_code == 401
    view = matrix(client, point)
    assert all(not c['supported_count_options'] for c in view['policies'])
    enable(client, headers, catalog, node)
    assert client.get(f'/api/v1/themes/{node}/knowledge-points').json()['data'] == []
    body = policy_body(view)
    body['policies'][2]['count_options'] = [3]
    route = f'/admin/api/v1/knowledge-points/{point}/quantity-policies'
    assert client.put(route, json=body, headers=headers).status_code == 409
    assert client.put(route, json=body, headers={'Origin': headers['Origin']}).status_code == 403


def test_explicit_policy_public_selection_no_cooldown(opened):
    editor, catalog, node, point, _ = opened
    engine, client, headers, _, _ = editor
    uh = user_headers(client, headers)
    before = client.get('/api/v1/session').json()['data']
    body = select_body(node, point)
    empty = client.post('/api/v1/capabilities', json=body, headers=uh).json()['data']
    assert empty['feasible_counts'] == []
    view = set_policy(opened)
    assert len(view['policies']) == 9
    assert client.get('/api/v1/catalogs').json()['data'][0]['verification_status'] == 'provisional'
    assert client.get(f'/api/v1/catalogs/{catalog}/themes').json()['data'][0]['id'] == node
    assert client.get(f'/api/v1/themes/{node}/knowledge-points').json()['data'][0]['id'] == point
    response = client.post('/api/v1/capabilities', json=body, headers=uh)
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    data = response.json()['data']
    assert data['feasible_counts'] == [{'choice': 0, 'fill': 0, 'answer': n} for n in (3,6,12)]
    assert data['count_options'] == {'choice': [0], 'fill': [0], 'answer': [3,6,12]}
    assert data['point_coverage'] == [point] and data['content_epoch'] > empty['content_epoch']
    assert data['selection_hash'] != empty['selection_hash']
    assert client.post('/api/v1/capabilities', json=body, headers=uh).json()['data'] == data
    assert client.get('/api/v1/session').json()['data'] == before
    challenge = client.post('/api/v1/capabilities', json=select_body(node, point, 'challenge'), headers=uh).json()['data']
    assert challenge['feasible_counts'] == [] and challenge['warnings']


def test_invalid_options_strict_schema_and_stale_locks(opened):
    editor, _, _, point, _ = opened
    _, client, headers, _, _ = editor
    view = matrix(client, point)
    route = f'/admin/api/v1/knowledge-points/{point}/quantity-policies'
    body = policy_body(view)
    locked = headers | {'If-Match': f'"{view["lock_version"]}"'}
    for counts in ([True], [3, 3], [4], ['3']):
        invalid = deepcopy(body); invalid['policies'][2]['count_options'] = counts
        assert client.put(route, json=invalid, headers=locked).status_code == 422
    invalid = deepcopy(body); invalid['policies'][2]['supported'] = True
    assert client.put(route, json=invalid, headers=locked).status_code == 422
    invalid = deepcopy(body); invalid['policies'][0]['count_options'] = [3]
    assert client.put(route, json=invalid, headers=locked).status_code == 409
    invalid = deepcopy(body); invalid['policies'][2]['default_count'] = 3
    assert client.put(route, json=invalid, headers=locked).status_code == 422
    assert client.put(route, json=body, headers=headers | {'If-Match': '*'}).status_code == 422
    assert client.put(route, json=body, headers=locked).status_code == 200
    assert client.put(route, json=body, headers=locked).status_code == 409


def test_template_disable_and_enable_preserve_policy(opened):
    editor, _, node, point, payload = opened
    engine, client, headers, _, imported = editor
    set_policy(opened)
    uh = user_headers(client, headers)
    body = select_body(node, point)
    original = client.post('/api/v1/capabilities', json=body, headers=uh).json()['data']
    route = '/admin/api/v1/templates/' + imported['template_id']
    assert client.post(route + '/disable', json={'reason': '测试停用'}, headers=headers | {'If-Match': '"2"'}).status_code == 200
    view = matrix(client, point)
    cell = next(c for c in view['policies'] if c['difficulty'] == 'basic' and c['question_type'] == 'answer')
    assert cell['count_options'] == [3,6,12] and cell['effective_count_options'] == []
    data = client.post('/api/v1/capabilities', json=body, headers=uh).json()['data']
    assert data['feasible_counts'] == [] and data['content_epoch'] > original['content_epoch']
    assert client.post(route + '/enable', json=payload, headers=headers | {'If-Match': '"3"'}).status_code == 200
    assert client.post('/api/v1/capabilities', json=body, headers=uh).json()['data']['feasible_counts'] == original['feasible_counts']


@pytest.mark.parametrize('mutation', ['generator', 'counts', 'point'])
def test_invalid_evidence_removed_immediately(opened, mutation):
    editor, _, node, point, _ = opened
    engine, client, headers, _, _ = editor
    set_policy(opened)
    uh = user_headers(client, headers)
    with write_transaction(engine) as session:
        if mutation == 'generator':
            session.scalar(select(GeneratorDefinition)).artifact_hash = '0' * 64
        elif mutation == 'counts':
            session.scalar(select(TemplateProfile)).validated_count_options = '[3]'
        else:
            session.get(KnowledgePoint, point).status = 'disabled'
    response = client.post('/api/v1/capabilities', json=select_body(node, point), headers=uh)
    if mutation == 'point':
        assert response.status_code == 409
    else:
        assert response.status_code == 200 and response.json()['data']['feasible_counts'] == []


def test_catalog_node_disable_and_foreign_selection(opened):
    editor, catalog, node, point, _ = opened
    _, client, headers, _, _ = editor
    set_policy(opened)
    uh = user_headers(client, headers)
    body = select_body(node, point)
    assert client.post('/api/v1/capabilities', json=body, headers={'Origin': headers['Origin']}).status_code == 403
    assert client.post('/api/v1/capabilities', json=body | {'knowledge_point_ids': [str(uuid4())]}, headers=uh).status_code == 409
    assert client.post('/api/v1/capabilities', json=body | {'knowledge_point_ids': [point, point]}, headers=uh).status_code == 422
    assert client.patch(f'/admin/api/v1/catalog-nodes/{node}', json={'status': 'disabled', 'reason': '测试'}, headers=headers | {'If-Match': '"2"'}).status_code == 204
    assert client.get(f'/api/v1/catalogs/{catalog}/themes').json()['data'] == []
    assert client.post('/api/v1/capabilities', json=body, headers=uh).status_code == 404
    assert client.patch(f'/admin/api/v1/catalogs/{catalog}', json={'status': 'archived', 'reason': '测试'}, headers=headers | {'If-Match': '"2"'}).status_code == 204
    assert client.get('/api/v1/catalogs').json()['data'] == []


def test_concurrent_policy_one_commit_and_audit(opened):
    editor, _, _, point, _ = opened
    engine, client, headers, _, _ = editor
    view = matrix(client, point)
    body = policy_body(view)
    route = f'/admin/api/v1/knowledge-points/{point}/quantity-policies'
    with Session(engine) as session:
        previous = session.get(ContentEpoch, 1).value
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.put(route, json=body, headers=headers | {'If-Match': f'"{view["lock_version"]}"'}), range(2)))
    assert sorted(r.status_code for r in results) == [200,409]
    with Session(engine) as session:
        assert session.get(ContentEpoch, 1).value == previous + 1
        assert session.scalar(select(func.count()).select_from(KnowledgeTypePolicy)) == 9
        assert session.scalar(select(func.count()).select_from(AdminOperationLog).where(AdminOperationLog.action == 'quantity_policy')) == 1


def test_policy_audit_failure_rolls_back(opened, monkeypatch):
    editor, _, _, point, _ = opened
    engine, client, headers, _, _ = editor
    view = matrix(client, point)
    import app.services.capabilities as service
    def failed(*args, **kwargs):
        raise RuntimeError('模拟审计失败')
    monkeypatch.setattr(service, 'audit', failed)
    with Session(engine) as session:
        previous = session.get(ContentEpoch, 1).value
    with pytest.raises(RuntimeError, match='模拟审计失败'):
        client.put(f'/admin/api/v1/knowledge-points/{point}/quantity-policies', json=policy_body(view),
                   headers=headers | {'If-Match': f'"{view["lock_version"]}"'})
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(KnowledgeTypePolicy)) == 0
        assert session.get(ContentEpoch, 1).value == previous
        assert session.get(KnowledgePoint, point).lock_version == view['lock_version']


def test_migration_retains_operation_history(opened, storage):
    set_policy(opened)
    _, engine, migration = storage
    command.check(migration)
    with pytest.raises(RuntimeError, match='禁止自动降级删除历史'):
        command.downgrade(migration, '0005')
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(KnowledgeTypePolicy)) == 9
    command.check(migration)


def test_disabled_ancestor_hides_theme_and_points(opened):
    editor, catalog, node, point, _ = opened
    engine, client, headers, _, _ = editor
    with write_transaction(engine) as session:
        parent = CatalogNode(catalog_id=catalog, parent_id=None, code='TEST_GROUP', name='测试分组',
                             node_type='group', status='disabled', sort_order=0, created_at=NOW, updated_at=NOW)
        session.add(parent); session.flush()
        session.get(CatalogNode, node).parent_id = parent.id
    assert client.get(f'/api/v1/catalogs/{catalog}/themes').json()['data'] == []
    assert client.get(f'/api/v1/themes/{node}/knowledge-points').status_code == 404


def test_multi_point_not_silently_covered_by_single_template(opened):
    from app.models.content import KnowledgeRevision, CatalogKnowledge
    editor, _, node, point, _ = opened
    engine, client, headers, _, _ = editor
    set_policy(opened)
    with write_transaction(engine) as session:
        other = KnowledgePoint(code='TEST_OTHER', domain='operation', status='active', created_at=NOW, updated_at=NOW)
        session.add(other); session.flush()
        revision = KnowledgeRevision(point_id=other.id, revision_no=1, name='仅测试第二知识点', aliases='[]',
            definition='测试', boundary='测试', misconceptions='[]', content_hash='f'*64, status='published',
            created_by=session.scalar(select(KnowledgeRevision.created_by)), created_at=NOW, updated_at=NOW)
        session.add(revision); session.flush()
        other.current_revision_id = revision.id
        session.add(CatalogKnowledge(node_id=node, knowledge_revision_id=revision.id, sort_order=2,
                                      role='primary', created_at=NOW, updated_at=NOW))
        other_id = other.id
    uh = user_headers(client, headers)
    body = select_body(node, point) | {'knowledge_point_ids': [point, other_id]}
    response = client.post('/api/v1/capabilities', json=body, headers=uh)
    assert response.status_code == 200, response.text
    assert response.json()['data']['feasible_counts'] == []
    assert response.json()['data']['point_coverage'] == []
