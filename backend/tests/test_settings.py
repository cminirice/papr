import os
import pytest
from alembic import command
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from test_content_seed import storage, NOW
from test_template_edit import editor
from test_releases import ready
from test_capabilities import opened
from test_paper_jobs import prepared, admission, submit
from app.models.releases import AdminOperationLog
from app.models.system import ContentEpoch
from test_browser_flow import browser_services, browser_script


def save(client, headers, key, value, lock=1):
    return client.patch('/admin/api/v1/settings/'+key, headers=headers|{'If-Match':f'"{lock}"'},
                        json={'value':value,'schema_version':1,'reason':'测试受控配置'})


def test_settings_schema_concurrency_auth_and_migration(editor,storage):
    engine,client,headers,*_=editor
    assert len(client.get('/admin/api/v1/settings').json()['data']['items'])==3
    assert save(client,headers,'unknown',{}).status_code==422
    for key,value in [('generation_limits',{'queue_limit':0}),('generation_limits',{'queue_limit':True}),
                      ('retention_policy',{'enabled':True}),('question_count_options',{'answer':[4]}),
                      ('question_count_options',{'answer':[3,3]}),('generation_limits',{'answer':[3]})]:
        assert save(client,headers,key,value).status_code==422
    saved=save(client,headers,'generation_limits',{'queue_limit':2,'ip_accept_limit':3})
    assert saved.status_code==200,saved.text
    assert saved.json()['data']['updated_at'].endswith('+08:00')
    assert save(client,headers,'generation_limits',{'queue_limit':3}).status_code==409
    assert save(client,{'Origin':headers['Origin']},'generation_limits',{'queue_limit':3},2).status_code==403
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(AdminOperationLog).where(AdminOperationLog.target_type=='app_setting'))==1
    command.check(storage[2])
    with pytest.raises(RuntimeError,match='不能自动降级'):
        command.downgrade(storage[2],'0010')
    client.cookies.clear()
    assert client.get('/admin/api/v1/settings').status_code==401


def test_count_setting_restricts_admission_and_epoch(admission):
    engine,client,_,body,headers,_=admission
    assert save(client,headers,'question_count_options',{'choice':[],'fill':[],'answer':[6]}).status_code==200
    assert submit(admission).json()['error']['code']=='CAPABILITY_CHANGED'
    with Session(engine) as session:body=body|{'content_epoch':session.get(ContentEpoch,1).value}
    assert submit(admission,body=body).json()['error']['code']=='UNSUPPORTED_COMBINATION'
    assert submit(admission,body=body|{'question_type_counts':{'choice':0,'fill':0,'answer':6}}).status_code==202


def test_live_ip_limit_and_no_cooldown(admission):
    _,client,user,_,admin,_=admission
    assert save(client,admin,'generation_limits',{'queue_limit':1,'ip_accept_limit':1}).status_code==200
    job=submit(admission).json()['data']['id']

    assert client.post('/api/v1/jobs/'+job+'/cancel',json={},headers=user).status_code==200
    assert submit(admission).json()['error']['code']=='RATE_LIMITED'
    assert client.get('/api/v1/session').json()['data']['next_generation_at'] is None


def test_settings_empty_migration_roundtrip(storage):
    command.downgrade(storage[2],'0010');command.upgrade(storage[2],'head');command.check(storage[2])


@pytest.mark.skipif(os.environ.get('PAPR_TEST_BROWSER')!='1',reason='Real settings UI')
def test_browser_settings(editor,tmp_path):
    engine,client,*_=editor
    with browser_services(engine,client.app.state.settings,pdf=False) as (settings,origins):
        browser_script(settings,origins,'browser_settings.mjs',tmp_path)
