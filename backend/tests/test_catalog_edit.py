from uuid import uuid4
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_content_seed import storage, NOW
from test_template_edit import editor
from test_releases import ready
from test_capabilities import opened, user_headers, select_body, set_policy
from app.models.content import ContentCatalog, CatalogNode
from app.models.releases import AdminOperationLog
from app.models.system import ContentEpoch


def create_catalog(client, headers, code='TEST_CATALOG'):
    response = client.post('/admin/api/v1/catalogs', headers=headers,
        json={'code': code, 'name': '测试目录', 'term': 'upper', 'reason': '测试创建目录'})
    assert response.status_code == 201, response.text
    return response.json()['data']


def create_node(client, headers, catalog, code, parent=None):
    response = client.post(f'/admin/api/v1/catalogs/{catalog}/nodes', headers=headers,
        json={'code': code, 'name': code, 'parent_id': parent, 'reason': '测试节点'})
    assert response.status_code == 201, response.text
    return response.json()['data']


def test_catalog_creation_edit_lock_and_auth(editor):
    engine, client, headers, *_ = editor
    row = create_catalog(client, headers)
    assert row['status'] == 'draft' and row['verification_status'] == 'provisional'
    assert all(c['id'] != row['id'] for c in client.get('/api/v1/catalogs').json()['data'])
    route = '/admin/api/v1/catalogs/' + row['id']
    body = {'name': '改名目录', 'term': 'lower', 'reason': '测试修改'}
    assert client.patch(route, headers=headers, json=body).status_code == 204
    assert client.patch(route, headers=headers, json=body).status_code == 409
    changed = client.get(route).json()['data']
    assert changed['lock_version'] == 2 and changed['name'] == '改名目录'
    assert client.patch(route, headers=headers | {'If-Match': '"2"'}, json={'reason': '无变化'}).status_code == 422
    assert client.patch(route, headers=headers | {'If-Match': '"2"'}, json={'name': None, 'reason': '非法空值'}).status_code == 422
    assert client.post('/admin/api/v1/catalogs', headers=headers,
        json={'code': row['code'], 'name': '重复', 'term': 'upper', 'reason': '重复编码'}).status_code == 409
    assert client.patch(route, headers={'Origin': headers['Origin'], 'If-Match': '"2"'}, json=body).status_code == 403
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(AdminOperationLog).where(AdminOperationLog.target_id == row['id'])) == 2
    client.cookies.clear()
    assert client.get(route).status_code == 401
    assert client.post('/admin/api/v1/catalogs', headers=headers,
        json={'code': 'OTHER', 'name': '未授权', 'term': 'upper', 'reason': '测试'}).status_code == 401


def test_node_cycles_cross_catalog_sort_and_atomic_mapping(editor):
    engine, client, headers, *_ = editor
    first = create_catalog(client, headers)
    other = create_catalog(client, headers, 'OTHER')
    root = create_node(client, headers, first['id'], 'ROOT')
    child = create_node(client, headers, first['id'], 'CHILD', root['id'])
    alien = create_node(client, headers, other['id'], 'ALIEN')
    route = '/admin/api/v1/catalog-nodes/' + root['id']
    for parent in (root['id'], child['id'], alien['id']):
        result = client.patch(route, headers=headers, json={'parent_id': parent, 'reason': '非法父节点'})
        assert result.status_code == 409, result.text
    assert client.patch(route, headers=headers, json={'sort_order': 10, 'name': '根节点', 'reason': '排序'}).status_code == 204
    nodes = client.get(f'/admin/api/v1/catalogs/{first["id"]}/nodes').json()['data']
    assert [n['id'] for n in nodes] == [child['id'], root['id']]
    assert nodes[1]['parent_id'] is None and nodes[1]['lock_version'] == 2
    options = client.get('/admin/api/v1/knowledge-revision-options?limit=1').json()['data']
    revision = options['items'][0]['id']
    mapping_route = route + '/knowledge-mappings'
    items = [{'knowledge_revision_id': revision, 'role': 'review'}]
    lock = headers | {'If-Match': '"2"'}
    saved = client.put(mapping_route, headers=lock, json={'items': items, 'reason': '映射草稿'})
    assert saved.status_code == 200, saved.text
    assert saved.json()['data']['items'] == items
    assert saved.json()['data']['lock_version'] == 3
    assert client.put(mapping_route, headers=lock, json={'items': [], 'reason': '过期版本'}).status_code == 409
    current = headers | {'If-Match': '"3"'}
    assert client.put(mapping_route, headers=current, json={'items': items * 2, 'reason': '重复修订'}).status_code == 422
    assert client.put(mapping_route, headers=current,
        json={'items': [{'knowledge_revision_id': str(uuid4())}], 'reason': '无效修订'}).status_code == 404
    assert client.get(mapping_route).json()['data'] == saved.json()['data']
    assert client.put(mapping_route, headers=current, json={'items': [], 'reason': '移除映射'}).status_code == 200
    assert client.get(mapping_route).json()['data']['items'] == []


def test_mapping_removal_immediately_invalidates_public_selection(opened):
    fixture, catalog, node, point, _ = opened
    engine, client, headers, *_ = fixture
    set_policy(opened)
    user = user_headers(client, headers)
    before = client.post('/api/v1/capabilities', headers=user, json=select_body(node, point)).json()['data']
    assert before['feasible_counts']
    route = f'/admin/api/v1/catalog-nodes/{node}/knowledge-mappings'
    old = client.get(route).json()['data']
    response = client.put(route, headers=headers | {'If-Match': f'"{old["lock_version"]}"'},
        json={'items': [], 'reason': '测试移除公开映射'})
    assert response.status_code == 200
    assert client.get(f'/api/v1/themes/{node}/knowledge-points').json()['data'] == []
    assert client.post('/api/v1/capabilities', headers=user, json=select_body(node, point)).status_code == 409
    with Session(engine) as session:
        assert session.get(ContentEpoch, 1).value > before['content_epoch']
    restored = client.put(route, headers=headers | {'If-Match': f'"{response.json()["data"]["lock_version"]}"'},
        json={'items': old['items'], 'reason': '恢复已验证映射'})
    assert restored.status_code == 200
    assert client.post('/api/v1/capabilities', headers=user, json=select_body(node, point)).json()['data']['feasible_counts']
