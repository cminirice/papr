from uuid import uuid4
import pytest
from alembic import command
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from test_content_seed import storage,NOW
from test_template_edit import editor
from test_releases import ready
from test_capabilities import opened,user_headers
from test_paper_jobs import prepared,admission,submit
from test_paper_execution import run,counts
from app.models.papers import PaperNotice,Question
from app.models.releases import AdminOperationLog
from app.services import paper_execution


def completed(admission):
    _,client,*_=admission
    accepted=submit(admission);assert accepted.status_code==202
    assert run(admission)
    job=client.get('/api/v1/jobs/'+accepted.json()['data']['id']).json()['data']
    assert job['status']=='succeeded',job
    return client.get('/api/v1/papers/'+job['paper_id']).json()['data']


def test_notices_withdrawal_preserves_snapshot_and_owner_boundary(admission):
    engine,client,user,_,admin,_=admission
    paper=completed(admission)
    before=counts(engine)
    path='/admin/api/v1/papers/'+paper['id']
    detail=client.get(path).json()['data']
    assert detail['sources'] and detail['lock_version']==1
    assert client.get('/admin/api/v1/papers').json()['data']['items'][0]['id']==paper['id']
    body={'question_id':paper['questions'][0]['id'],'severity':'error','action':'notice','message':'测试说明，不修改原题','reason':'测试记录'}
    key=str(uuid4());headers=admin|{'Idempotency-Key':key,'If-Match':'"1"'}
    added=client.post(path+'/notices',json=body,headers=headers)
    assert added.status_code==200,added.text
    assert added.json()['data']['lock_version']==2
    assert client.post(path+'/notices',json=body,headers=headers).status_code==200
    assert client.post(path+'/notices',json=body|{'message':'不同内容'},headers=headers).status_code==409
    assert client.post(path+'/notices',json=body|{'reason':'不同理由'},headers=headers).status_code==409
    assert client.post(path+'/notices',json=body,headers=headers|{'Idempotency-Key':str(uuid4())}).status_code==409
    invalid=client.post(path+'/notices',json=body|{'question_id':str(uuid4())},headers=admin|{'If-Match':'"2"','Idempotency-Key':str(uuid4())})
    assert invalid.status_code==422
    assert client.get('/api/v1/files/'+paper['files'][0]['id']).status_code==200
    withdraw=client.post(path+'/notices',json=body|{'action':'withdraw','message':'测试撤下说明'},headers=admin|{'If-Match':'"2"','Idempotency-Key':str(uuid4())})
    assert withdraw.status_code==200,withdraw.text
    public=client.get('/api/v1/papers/'+paper['id']).json()['data']
    assert public['status']=='withdrawn' and public['files']==[] and len(public['notices'])==2
    assert public['questions']==paper['questions'] and counts(engine)==before
    assert client.get('/api/v1/papers').json()['data']['items'][0]['status']=='withdrawn'
    for file in paper['files']:assert client.get('/api/v1/files/'+file['id']).status_code==404
    assert client.get('/admin/api/v1/papers?status=withdrawn').json()['data']['items'][0]['id']==paper['id']
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(PaperNotice))==2
        assert session.scalar(select(func.count()).select_from(AdminOperationLog).where(AdminOperationLog.target_type=='paper'))==2
    client.cookies.clear();user_headers(client,{})
    assert client.get('/api/v1/papers/'+paper['id']).status_code==404
    assert client.get(path).status_code==401


def test_cancel_queued_only_and_no_cooldown(admission):
    engine,client,_,_,admin,_=admission
    queued=submit(admission).json()['data']['id']
    route='/admin/api/v1/jobs/'+queued+'/cancel'
    assert client.post(route,json={'reason':'取消测试'},headers={'Origin':admin['Origin']}).status_code==403
    assert client.post(route,json={'reason':'取消测试'},headers=admin).status_code==204
    assert client.post(route,json={'reason':'同次重试'},headers=admin).status_code==204
    assert client.get('/api/v1/jobs/'+queued).json()['data']['status']=='cancelled'
    assert counts(engine)==(0,0,None)
    running=submit(admission).json()['data']['id']
    assert paper_execution.claim(engine,NOW)
    assert client.post('/admin/api/v1/jobs/'+running+'/cancel',json={'reason':'不可中断'},headers=admin).status_code==409


def test_cancel_validation_does_not_create_pass_evidence(editor):
    from test_validation_jobs import submit as validate
    _,client,headers,*_=editor
    accepted,_=validate(editor)
    result=client.get('/admin/api/v1/validation-runs/'+accepted['id']).json()['data']
    assert client.post('/admin/api/v1/jobs/'+result['job_id']+'/cancel',headers=headers,json={'reason':'停止排队验证'}).status_code==204
    result=client.get('/admin/api/v1/validation-runs/'+accepted['id']).json()['data']
    assert result['status']=='failed' and result['report'] is None


def test_notice_migration_roundtrip(storage):
    _,_,config=storage
    command.check(config)
    command.downgrade(config,'0009');command.upgrade(config,'head');command.check(config)


import os
from test_browser_flow import browser_services,browser_script

@pytest.mark.skipif(os.environ.get('PAPR_TEST_BROWSER')!='1',reason='Real admin notices and user withdrawal')
def test_browser_paper_notices(prepared,tmp_path):
    engine,client,*_=prepared
    with browser_services(engine,client.app.state.settings) as (settings,origins):
        browser_script(settings,origins,'browser_paper_admin.mjs',tmp_path)


@pytest.mark.skipif(os.environ.get('PAPR_TEST_BROWSER')!='1',reason='Real admin queue cancellation')
def test_browser_admin_cancel(admission,tmp_path):
    engine,client,*_=admission
    assert submit(admission).status_code==202
    with browser_services(engine,client.app.state.settings,pdf=False) as (settings,origins):
        browser_script(settings,origins,'browser_admin_cancel.mjs',tmp_path)
