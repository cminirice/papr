from datetime import timedelta
from hashlib import sha256
from uuid import uuid4
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import select
from test_content_seed import storage,NOW,PASSWORD
from app.auth.security import initialize_rate_key
from app.main import create_app
from app.v2 import engine as math,worker,service
from app.v2.models import Task,Template,Artifact,Directory
from app.core.database import write_transaction
from app.models.identity import AppUser
from app.services import paper_runtime,pdf_storage
from test_pdf_inspection_macos import fixture_pdf
from test_pdf_storage import fake_inspector

@pytest.fixture
def flow(storage,monkeypatch):
 settings,db,_=storage;initialize_rate_key(settings.rate_limit_key_path)
 app=create_app(settings);app.state.clock=lambda:NOW
 monkeypatch.setattr(paper_runtime,'ready',lambda *args:True)
 monkeypatch.setattr(paper_runtime,'config_hash',lambda *args:'test-renderer')
 save=pdf_storage.save_pair
 monkeypatch.setattr(worker,'save_pair',lambda *args:save(*args,inspector=fake_inspector))
 with TestClient(app,base_url='http://127.0.0.1:5174',client=('127.0.0.1',1234)) as client:
  login=client.post('/admin/api/v1/session/login',headers={'Origin':'http://127.0.0.1:5174'},json={'username':'owner','password':PASSWORD})
  headers={'Origin':'http://127.0.0.1:5174','X-CSRF-Token':login.json()['data']['csrf_token']}
  yield settings,db,app,client,headers

def put(client,h,kind,id,**fields):
 body={'code':'CODE_'+id[:8].upper(),'name':'测试','status':'启用',**fields}
 response=client.put(f'/admin/api/v2/items/{kind}/{id}',headers=h,json=body)
 assert response.status_code==200,response.text
 return response.json()['data']

def setup_content(client,h):
 root,leaf,tid=map(str,[uuid4(),uuid4(),uuid4()])
 put(client,h,'catalogs',root)
 put(client,h,'nodes',leaf,catalog=root,generators=list(math.CAPABILITIES))
 rules=[{'node':leaf,'generator':'integer_multiplication_v1','kind':'竖式计算','difficulty':'基础','count':6},{'node':leaf,'generator':'number_read_write_v1','kind':'填空题','difficulty':'提高','count':3}]
 data=put(client,h,'templates',tid,catalog=root,rules=rules,status='草稿')
 return root,leaf,data['templates'][0]

def fake_render(document,settings,pulse=None):
 if pulse:pulse()
 pdf=fixture_pdf();contents={'student_pdf':pdf,'solution_pdf':pdf+b'\n% solution\n'}
 metadata={'renderer_version':'papr-chromium-v1','content_schema_version':1,'browser_version':'test','vue_version':'test','playwright_version':'test','font_sha256':'a'*64,'print_asset_sha256':'b'*64,'input_sha256':sha256(math.canonical(document).encode()).hexdigest(),'student_sha256':sha256(pdf).hexdigest(),'solution_sha256':sha256(contents['solution_pdf']).hexdigest()}
 return contents,metadata

def start(client,h,t,kind,key=None):
 response=client.post(f'/admin/api/v2/versions/{t["version_id"]}/jobs/{kind}',headers=h|{'Idempotency-Key':key or str(uuid4())},json={'version_id':t['version_id'],'configuration_hash':t['configuration_hash']})
 assert response.status_code==202,response.text
 return response.json()['data']['id']

def publish(flow,t):
 settings,db,app,c,h=flow
 p=start(c,h,t,'preview');assert worker.run_once(db,settings,clock=lambda:NOW,render=fake_render,on_error=lambda e:pytest.fail(str(e)))
 v=start(c,h,t,'validate');worker.run_once(db,settings,clock=lambda:NOW,render=fake_render,on_error=lambda e:pytest.fail(str(e)))
 for id in [p,v]:assert c.get('/admin/api/v2/jobs/'+id).json()['data']['status']=='succeeded'
 r=c.post(f'/admin/api/v2/versions/{t["version_id"]}/review',headers=h,json={'preview_id':p,'validation_id':v,'approved':True,'comment':'完整样卷审核通过'})
 assert r.status_code==200,r.text
 result=c.post(f'/admin/api/v2/templates/{t["id"]}/publish',headers=h,json={'revision':t['revision'],'version_id':t['version_id'],'review_id':r.json()['data']['id']})
 assert result.status_code==200,result.text
 return result.json()['data']['templates'][0]

def user(app):
 c=TestClient(app,base_url='http://127.0.0.1:5173',client=('127.0.0.1',1235));r=c.post('/api/v1/session',headers={'Origin':'http://127.0.0.1:5173'},json={})
 assert r.status_code==200,r.text
 return c,{'Origin':'http://127.0.0.1:5173','X-CSRF-Token':r.json()['data']['csrf_token']}

def submit(c,h,t,key):return c.post('/api/v2/jobs',headers=h|{'Idempotency-Key':key},json={'version_id':t['version_id'],'configuration_hash':t['configuration_hash']})

def test_real_math_determinism_capacity_and_answers():
 for number,expected in [(10,'十'),(10001,'一万零一'),(120040080,'一亿二千零四万零八十'),(305006,'三十万五千零六')]:assert math.read_number(number)==expected
 rules=[]
 for key,caps in math.CAPABILITIES.items():
  if key.startswith('g4_upper_'):continue  # New components have their own exhaustive matrix.
  for kind,levels in caps.items():
   for level in levels:rules.append({'node':'leaf','point':'内容','generator':key,'kind':kind,'difficulty':level,'count':3})
 content={'rules':rules,'columns':5}
 questions=math.generate(content,'fixed');math.verify(content,questions)
 assert questions==math.generate(content,'fixed')
 assert len({q['semantic_signature'] for q in questions})==len(questions)
 questions[0]['answer']['value']='0'
 with pytest.raises(ValueError):math.verify(content,questions)
 content={'rules':[{'node':'leaf','point':'读写','generator':'number_read_write_v1','kind':'填空题','difficulty':'基础','count':100},{'node':'leaf','point':'读写','generator':'number_read_write_v1','kind':'选择题','difficulty':'提高','count':100}],'columns':5}
 q=math.generate(content,'200');math.verify(content,q);assert len(q)==200

def test_tree_auth_revision_and_publish_guard(flow):
 settings,db,app,c,h=flow;root,leaf,t=setup_content(c,h)
 assert c.get('/api/v2/templates').json()['data']==[]
 response=c.put('/admin/api/v2/items/nodes/'+str(uuid4()),headers=h,json={'code':'THIRD','name':'三级','catalog':leaf})
 assert response.status_code==422
 assert c.put('/admin/api/v2/items/catalogs/'+root,headers=h,json={'code':'X','name':'冲突','revision':0}).status_code==409
 assert c.put('/admin/api/v2/items/catalogs/'+root,json={'code':'X','name':'未授权'}).status_code==403
 assert c.post(f'/admin/api/v2/templates/{t["id"]}/publish',headers=h,json={'revision':1,'version_id':t['version_id'],'review_id':str(uuid4())}).status_code==404
 with pytest.raises(Exception):
  with write_transaction(db) as s:
   s.add(Directory(parent_id=leaf,code='THIRD',name='third'));s.flush()

def test_publish_generate_cooldown_replay_auth_history(flow):
 settings,db,app,c,h=flow;_,_,t=setup_content(c,h);t=publish(flow,t)
 u,uh=user(app);other,oh=user(app);key=str(uuid4())
 result=submit(u,uh,t,key);assert result.status_code==202,result.text;j=result.json()['data']['id']
 assert submit(u,uh,t,key).json()['data']['id']==j
 assert submit(u,uh,t,str(uuid4())).status_code==409
 assert other.get('/api/v2/jobs/'+j).status_code==404
 worker.run_once(db,settings,clock=lambda:NOW,render=fake_render,on_error=lambda e:pytest.fail(str(e)))
 row=u.get('/api/v2/jobs/'+j).json()['data'];assert row['status']=='succeeded',row
 assert len(row['assets'])==2
 assert u.get('/api/v2/files/'+row['assets'][0]['id']).status_code==200
 assert other.get('/api/v2/files/'+row['assets'][0]['id']).status_code==404
 assert submit(u,uh,t,key).json()['data']['id']==j
 app.state.clock=lambda:NOW+timedelta(seconds=599)
 assert submit(u,uh,t,str(uuid4())).status_code==429
 app.state.clock=lambda:NOW+timedelta(seconds=600)
 assert submit(u,uh,t,str(uuid4())).status_code==202
 assert len(u.get('/api/v2/history').json()['data'])==2

def test_pdf_failure_and_inflight_disable_no_cooldown(flow):
 settings,db,app,c,h=flow;_,_,t=setup_content(c,h);t=publish(flow,t);u,uh=user(app)
 def broken(*a,**k):raise RuntimeError('PDF failure')
 j=submit(u,uh,t,str(uuid4())).json()['data']['id'];worker.run_once(db,settings,clock=lambda:NOW,render=broken)
 assert u.get('/api/v2/jobs/'+j).json()['data']['status']=='failed'
 assert u.get('/api/v1/session').json()['data']['next_generation_at'] is None
 j=submit(u,uh,t,str(uuid4())).json()['data']['id']
 def disabling(document,settings,pulse=None):
  r=c.post(f'/admin/api/v2/templates/{t["id"]}/disable',headers=h,json={'revision':t['revision']});assert r.status_code==200
  return fake_render(document,settings,pulse)
 worker.run_once(db,settings,clock=lambda:NOW,render=disabling)
 assert u.get('/api/v2/jobs/'+j).json()['data']['status']=='failed'
 assert u.get('/api/v1/session').json()['data']['next_generation_at'] is None
 assert c.get('/api/v2/templates').json()['data']==[]

def test_expired_lease_fencing_and_cancel(flow):
 settings,db,app,c,h=flow;_,_,t=setup_content(c,h)
 id=start(c,h,t,'preview');first=worker.claim(db,NOW);second=worker.claim(db,NOW+timedelta(seconds=31))
 assert first['token']!=second['token']
 with write_transaction(db) as s:
  with pytest.raises(worker.LeaseLost):worker.fenced(s,first,NOW+timedelta(seconds=31))
 assert worker.claim(db,NOW+timedelta(seconds=62)) is None
 with Session(db) as s:assert s.get(Task,id).status=='failed'

@pytest.mark.skipif(__import__('os').environ.get('PAPR_REAL_PDF')!='1',reason='Requires installed Chrome, Node and macOS PDF parser')
def test_real_pdf_end_to_end(storage):
 from dataclasses import replace
 from pathlib import Path
 settings,db,_=storage
 settings=replace(settings,pdf_node=Path('/Users/eric/.local/node-v22.23.2/bin/node'),pdf_browser=Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),pdf_font=Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf'))
 initialize_rate_key(settings.rate_limit_key_path);app=create_app(settings);app.state.clock=lambda:NOW
 paper_runtime.probe(settings);paper_runtime.heartbeat(db,paper_runtime.config_hash(settings),NOW)
 with TestClient(app,base_url='http://127.0.0.1:5174',client=('127.0.0.1',1240)) as c:
  login=c.post('/admin/api/v1/session/login',headers={'Origin':'http://127.0.0.1:5174'},json={'username':'owner','password':PASSWORD})
  h={'Origin':'http://127.0.0.1:5174','X-CSRF-Token':login.json()['data']['csrf_token']}
  _,_,t=setup_content(c,h);ids=[]
  for kind in ('preview','validate'):
   id=start(c,h,t,kind);ids.append(id)
   worker.run_once(db,settings,clock=lambda:NOW,on_error=lambda e:pytest.fail(str(e)))
   row=c.get('/admin/api/v2/jobs/'+id).json()['data'];assert row['status']=='succeeded',row
   assert len(row['document']['questions'])==9
   assert all(c.get('/admin/api/v2/artifacts/'+a['id']).content.startswith(b'%PDF') for a in row['assets'])
  reviewed=c.post(f'/admin/api/v2/versions/{t["version_id"]}/review',headers=h,json={'preview_id':ids[0],'validation_id':ids[1],'approved':True,'comment':'自动化测试专用审题记录，非生产人工审题'})
  assert reviewed.status_code==200,reviewed.text
  result=c.post(f'/admin/api/v2/templates/{t["id"]}/publish',headers=h,json={'revision':t['revision'],'version_id':t['version_id'],'review_id':reviewed.json()['data']['id']})
  assert result.status_code==200,result.text
  u,uh=user(app);j=submit(u,uh,t,str(uuid4())).json()['data']['id']
  worker.run_once(db,settings,clock=lambda:NOW,on_error=lambda e:pytest.fail(str(e)))
  row=u.get('/api/v2/jobs/'+j).json()['data'];assert row['status']=='succeeded',row
  assert len(row['assets'])==2
  for a in row['assets']:
   data=u.get('/api/v2/files/'+a['id']);assert data.status_code==200
   assert pdf_storage.inspect_bytes(data.content)['pdf_parser_checked']
  assert u.get('/api/v1/session').json()['data']['next_generation_at'] is not None


def test_import_is_atomic_and_never_publishes(flow):
 settings,db,app,c,h=flow
 payload={'catalogs':[{'old_id':'root','item':{'code':'ROOT','name':'专项','status':'启用'}}],
  'nodes':[{'old_id':'leaf','item':{'code':'LEAF','name':'乘法','status':'启用','catalog':'root','generators':['integer_multiplication_v1']}}],
  'templates':[{'old_id':'template','item':{'code':'TEMPLATE','name':'练习','status':'启用','catalog':'root','rules':[{'node':'missing','generator':'integer_multiplication_v1','kind':'竖式计算','difficulty':'基础','count':6}]}}]}
 response=c.post('/admin/api/v2/workspace/import',headers=h,json=payload)
 assert response.status_code==422,response.text
 with Session(db) as s:assert s.scalar(select(Directory)) is None
 payload['templates'][0]['item']['rules'][0]['node']='leaf'
 response=c.post('/admin/api/v2/workspace/import',headers=h,json=payload)
 assert response.status_code==200,response.text
 data=response.json()['data'];assert len(data['templates'])==1
 assert data['templates'][0]['published_version_id'] is None
 assert c.get('/api/v2/templates').json()['data']==[]
 assert c.post('/admin/api/v2/workspace/import',headers=h,json=payload).status_code==409


def test_published_edit_keeps_old_release_and_invalidates_draft_evidence(flow):
 settings,db,app,c,h=flow;root,leaf,t=setup_content(c,h);t=publish(flow,t)
 old_version=t['version_id']
 data=put(c,h,'templates',t['id'],revision=t['revision'],catalog=root,rules=[{k:r[k] for k in ('node','generator','kind','difficulty','count')} for r in t['rules']],name='修改后的练习',columns=3,status='启用')
 draft=data['templates'][0]
 assert draft['version_id']!=old_version
 assert draft['published_version_id']==old_version
 assert draft['review_id'] is None
 assert c.get('/api/v2/templates').json()['data'][0]['version_id']==old_version


def test_layout_by_kind_and_legacy_fallback(flow):
 settings,db,app,c,h=flow;root,leaf,t=setup_content(c,h)
 rules=[{k:r[k] for k in ('node','generator','kind','difficulty','count')} for r in t['rules']]
 data=put(c,h,'templates',t['id'],revision=t['revision'],catalog=root,rules=rules,columns=2,columns_by_kind={'竖式计算':3,'填空题':1})
 content=data['templates'][0]
 q=math.generate(content,'layout');math.verify(content,q)
 assert [x['layout']['questions_per_row'] for x in q]==[3]*6+[1]*3
 assert [x['layout']['solutions_per_row'] for x in q]==[3]*6+[1]*3
 q[-1]['layout']['questions_per_row']=2
 with pytest.raises(ValueError,match='LAYOUT_CONFIG_MISMATCH'):math.verify(content,q)
 legacy={**content};legacy.pop('columns_by_kind')
 assert all(x['layout']['questions_per_row']==2 for x in math.generate(legacy,'layout'))
 for bad in [0,6,True,1.5]:
  response=c.put('/admin/api/v2/items/templates/'+t['id'],headers=h,json={'code':t['code'],'name':'布局','catalog':root,'rules':rules,'revision':content['revision'],'columns_by_kind':{'选择题':bad}})
  assert response.status_code==422,response.text


@pytest.mark.skipif(__import__('os').environ.get('PAPR_TEST_BROWSER')!='1',reason='Requires real Chrome and local listeners')
def test_browser_layout_filter_and_publish_feedback(storage):
 from pathlib import Path
 import subprocess
 from test_browser_flow import browser_services
 settings,db,_=storage;initialize_rate_key(settings.rate_limit_key_path)
 app=create_app(settings);app.state.clock=lambda:NOW
 with TestClient(app,base_url='http://127.0.0.1:5174',client=('127.0.0.1',1250)) as c:
  login=c.post('/admin/api/v1/session/login',headers={'Origin':'http://127.0.0.1:5174'},json={'username':'owner','password':PASSWORD})
  h={'Origin':'http://127.0.0.1:5174','X-CSRF-Token':login.json()['data']['csrf_token']}
  root,leaf,t=setup_content(c,h)
  put(c,h,'nodes',str(uuid4()),catalog=root,name='没有关联组件的目录',generators=[])
 with browser_services(db,settings,workflow_v2=True) as (_,origins):
  result=subprocess.run(['/Users/eric/.local/node-v22.23.2/bin/node',str(Path(__file__).resolve().parents[2]/'scripts/browser_workflow_layout.mjs'),*origins],capture_output=True,text=True,timeout=180)
  assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.skipif(__import__('os').environ.get('PAPR_TEST_BROWSER')!='1',reason='Requires real Chrome and local listeners')
def test_browser_grade4_components(storage):
 from pathlib import Path
 import subprocess
 from test_browser_flow import browser_services
 settings,db,_=storage;initialize_rate_key(settings.rate_limit_key_path)
 app=create_app(settings);app.state.clock=lambda:NOW
 with TestClient(app,base_url='http://127.0.0.1:5174',client=('127.0.0.1',1250)) as c:
  login=c.post('/admin/api/v1/session/login',headers={'Origin':'http://127.0.0.1:5174'},json={'username':'owner','password':PASSWORD})
  h={'Origin':'http://127.0.0.1:5174','X-CSRF-Token':login.json()['data']['csrf_token']}
  root,leaf,t=setup_content(c,h)
  put(c,h,'nodes',str(uuid4()),catalog=root,name='没有关联组件的目录',generators=[])
 with browser_services(db,settings,workflow_v2=True) as (_,origins):
  result=subprocess.run(['/Users/eric/.local/node-v22.23.2/bin/node',str(Path(__file__).resolve().parents[2]/'scripts/browser_grade4.mjs'),*origins],capture_output=True,text=True,timeout=240)
  assert result.returncode==0,result.stdout+result.stderr
