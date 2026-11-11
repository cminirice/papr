import os
from uuid import uuid4
import pytest
from test_content_seed import storage, NOW
from test_template_edit import editor
from test_settings import save
from app.core.database import write_transaction
from app.models.releases import AdminOperationLog
from test_browser_flow import browser_services, browser_script


def test_audit_filter_pagination_redaction_auth(editor):
    engine,client,headers,*_=editor
    for version in range(1,4):
        assert save(client,headers,'generation_limits',{'queue_limit':version},version).status_code==200
    first=client.get('/admin/api/v1/operations?limit=1').json()['data']
    assert first['has_more'] and len(first['items'])==1
    item=first['items'][0]
    assert item['created_at'].endswith('+08:00')
    params={'admin_id':item['admin_id'],'target_type':'app_setting','target_id':'generation_limits','action':'update_setting','limit':1}
    identities=[];cursor=None
    while True:
        page=client.get('/admin/api/v1/operations',params=params|({'cursor':cursor} if cursor else {})).json()['data']
        identities.extend(r['id'] for r in page['items'])
        if not page['has_more']:break
        cursor=page['next_cursor']
    assert len(set(identities))==len(identities)==3
    assert client.get('/admin/api/v1/operations?target_type=paper').json()['data']['items']==[]
    assert client.get('/admin/api/v1/operations?cursor=bad').status_code==422
    assert client.get('/admin/api/v1/operations?date_from=2030-01-02&date_to=2030-01-03').json()['data']['items']==[]
    with write_transaction(engine) as session:
        row=session.get(AdminOperationLog,item['id']);row.before_summary='{"password":"test-secret", "nested":{"csrf_token":"test-secret","safe":1}}'
    result=client.get('/admin/api/v1/operations').json()['data']
    assert 'test-secret' not in str(result)
    assert next(r for r in result['items'] if r['id']==item['id'])['before_summary']=={'nested':{'safe':1}}
    assert client.get('/admin/api/v1/operations?admin_id='+str(uuid4())).json()['data']['items']==[]
    client.cookies.clear();assert client.get('/admin/api/v1/operations').status_code==401


@pytest.mark.skipif(os.environ.get('PAPR_TEST_BROWSER')!='1',reason='Real audit filters')
def test_browser_audit(editor,tmp_path):
    engine,client,headers,*_=editor
    for version in range(1,23):assert save(client,headers,'generation_limits',{'queue_limit':version},version).status_code==200
    with browser_services(engine,client.app.state.settings,pdf=False) as (settings,origins):
        browser_script(settings,origins,'browser_audit.mjs',tmp_path)
