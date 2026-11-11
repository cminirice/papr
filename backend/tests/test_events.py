import os
from uuid import uuid4
from datetime import timedelta
import pytest
from alembic import command
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from test_content_seed import storage,NOW
from test_template_edit import editor
from test_releases import ready
from test_capabilities import opened,user_headers
from test_paper_jobs import prepared,admission
from test_paper_admin import completed
from test_paper_execution import counts
from app.core.database import write_transaction
from app.models.events import UsageEvent
from app.models.papers import Paper
from test_browser_flow import browser_services,browser_script


def sample(paper,**updates):
    return {'event_id':str(uuid4()),'type':'preview','paper_id':paper['id'],'payload':{'answer_mode':'student'},'occurred_at':'2020-01-01T00:00:00Z'}|updates


def test_events_batch_idempotency_conflict_owner_and_stats(admission):
    engine,client,headers,*_=admission
    paper=completed(admission);before=counts(engine)
    event=sample(paper);other=sample(paper,type='print_intent')
    batch={'events':[event,event,event|{'payload':{'answer_mode':'solution'}},other,sample(paper,type='print_success'),sample(paper,paper_id=str(uuid4())),sample(paper,payload={'answer_mode':'student','url':'https://example.invalid'})]}
    result=client.post('/api/v1/events',json=batch,headers=headers)
    assert result.status_code==200,result.text
    data=result.json()['data']
    assert data['accepted_ids']==[event['event_id'],other['event_id']]
    assert data['duplicate_ids']==[event['event_id']]
    assert [r['code'] for r in data['rejected']]==['EVENT_CONFLICT','INVALID_CONFIG','NOT_FOUND','INVALID_CONFIG']
    assert client.post('/api/v1/events',json={'events':[event]},headers=headers).json()['data']['duplicate_ids']==[event['event_id']]
    assert client.post('/api/v1/events',json={'events':[event]*21},headers=headers).status_code==422
    assert client.post('/api/v1/events',json={'events':[event]},headers={'Origin':headers['Origin']}).status_code==403
    stats=client.get('/admin/api/v1/overview').json()['data']
    assert stats['usage']=={'preview':1,'print_intent':1} and stats['totals']['succeeded']==1
    assert client.get('/admin/api/v1/overview?date_from=2020-01-01&date_to=2020-01-01').json()['data']['usage']=={'preview':0,'print_intent':0}
    assert counts(engine)==before
    with Session(engine) as session:
        rows=session.scalars(select(UsageEvent)).all()
        assert len(rows)==2 and all(r.received_at==NOW and r.occurred_at.utcoffset()==timedelta(hours=8) for r in rows)
    with write_transaction(engine) as session:session.get(Paper,paper['id']).status='withdrawn'
    assert client.post('/api/v1/events',json={'events':[sample(paper,type='print_intent')]},headers=headers).json()['data']['rejected'][0]['code']=='NOT_FOUND'
    client.cookies.clear();new_headers=user_headers(client,{})
    assert client.post('/api/v1/events',json={'events':[sample(paper)]},headers=new_headers).json()['data']['rejected'][0]['code']=='NOT_FOUND'


def test_events_migration(storage):
    command.downgrade(storage[2],'0011');command.upgrade(storage[2],'head');command.check(storage[2])


@pytest.mark.skipif(os.environ.get('PAPR_TEST_BROWSER')!='1',reason='Real preview/print-intent and failure isolation')
def test_browser_events(prepared,tmp_path):
    engine,client,*_=prepared
    with browser_services(engine,client.app.state.settings) as (settings,origins):
        browser_script(settings,origins,'browser_events.mjs',tmp_path)
