from itertools import product
from copy import deepcopy
import os
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_content_seed import storage, NOW
from test_template_edit import editor
from test_releases import ready, approve
from test_capabilities import identifiers, enable, matrix, policy_body, user_headers, select_body
from test_paper_jobs import submit
from test_paper_execution import run, counts
from test_browser_flow import browser_services, browser_script
from app.models.content import KnowledgePoint
from app.models.jobs import Job
from app.models.papers import Question, QuestionKnowledge
from app.schemas.paper_jobs import PaperPlan
from app.services.allocation import allocate
from app.services import paper_jobs, paper_execution
from app.generators.multiplication import generate_paper, verify_question
from app.services.template_tools import default_config


def test_allocation_exact_totals_coverage_and_capacity():
    for limits in product(range(3),repeat=4):
        context={p:{k:{'max_count':limits[i*2+j],'exact_capacity':100,'version_id':p+k} for j,k in enumerate(('choice','fill')) if limits[i*2+j]} for i,p in enumerate(('p','q'))}
        for a,b in product(range(4),repeat=2):
            result=allocate(context,{'choice':a,'fill':b,'answer':0})
            possible=any(x+y>=1 and a-x+b-y>=1 and x<=limits[0] and y<=limits[1] and a-x<=limits[2] and b-y<=limits[3] for x in range(a+1) for y in range(b+1))
            assert (result is not None)==possible,(limits,a,b,result)
            if result:
                assert {r['point_id'] for r in result}=={'p','q'}
                assert [sum(r['count'] for r in result if r['kind']==k) for k in ('choice','fill')]==[a,b]
    narrow={'p':{'fill':{'version_id':'x','max_count':3,'exact_capacity':3}},'q':{'fill':{'version_id':'y','max_count':3,'exact_capacity':3}}}
    assert allocate(narrow,{'choice':0,'fill':6,'answer':0}) is None


def test_zero_factor_has_real_primary_coverage():
    profile=default_config('zero_product').profiles[0]
    for kind in ('choice','fill','answer'):
        questions=generate_paper(profile,seed='zero-test',count=12,question_type=kind)
        for q in questions:
            assert q.primary_knowledge_code=='O003'
            assert '0' in q.render_spec.multiplicand+q.render_spec.multiplier
            verify_question(q,profile)


def publish_template(editor,task,kind,target):
    engine,client,headers,_,imported=editor
    choice=next(c for c in client.get('/admin/api/v1/generators').json()['data'] if c['available'])
    body={'code':task.upper()+'_'+kind.upper(),'name':task+' '+kind,'task':task,'question_type':kind,
          'generator_id':choice['id'],'objective_revision_id':target,'config':choice['task_configs'][task],'reason':'隔离测试多模板发布'}
    created=client.post('/admin/api/v1/templates',json=body,headers=headers)
    assert created.status_code==201,created.text
    draft=created.json()['data']
    path='/admin/api/v1/template-versions/'+draft['id']
    nested=(engine,client,headers,path,imported|{'template_id':draft['template_id'],'template_version_id':draft['id']})
    tested=ready.__wrapped__(nested)
    for dependency in client.get(path+'/release-context').json()['data']['dependencies']:
        if dependency['status']=='draft':
            route='knowledge-revisions' if dependency['kind']=='knowledge_revision' else 'objective-revisions'
            r=client.post('/admin/api/v1/'+route+'/'+dependency['id']+'/publish',headers=headers|{'If-Match':f'"{dependency["lock_version"]}"'},json={'content_hash':dependency['content_hash'],'reason':'隔离测试修订发布'})
            assert r.status_code==204,r.text
    response=client.post('/admin/api/v1/templates/'+draft['template_id']+'/publish',headers=headers,json=approve(tested))
    assert response.status_code==200,response.text
    return draft


@pytest.fixture
def mixed_prepared(editor):
    engine,client,headers,_,imported=editor
    point=client.post('/admin/api/v1/knowledge-points',headers=headers,json={'code':'O003','domain':'operation','reason':'隔离测试含零主考查点','content':{
        'name':'含零因数的乘法','definition':'计算因数中含零的整数乘法','boundary':'三位数乘两位数','aliases':[],'misconceptions':['零占位遗漏'],'source_id':None}}).json()['data']
    revision=point['revisions'][0]
    objective=client.post('/admin/api/v1/knowledge-points/'+point['id']+'/objectives',headers=headers,json={'code':'O003_ZERO_MULTIPLY_V1','reason':'隔离测试目标','content':{
        'knowledge_revision_id':revision['id'],'name':'含零因数乘法','scope':'至少一个因数含零','success_criteria':['零占位与部分积正确'],'allowed_prerequisites':[]}}).json()['data']['revisions'][0]
    choices=client.get('/admin/api/v1/generators').json()['data'][0]
    original=choices['task_objective_revision_ids']['product'][0]
    drafts=[publish_template(editor,'product',kind,original) for kind in ('choice','fill','answer')]
    drafts.append(publish_template(editor,'zero_product','answer',objective['id']))
    catalog,node,first=identifiers(engine)
    # IDs are explicit: querying first by row order is not a source of primary attribution.
    with Session(engine) as session:
        first=session.scalar(select(KnowledgePoint.id).where(KnowledgePoint.code=='O002'))
    enable(client,headers,catalog,node)
    mapping=client.get(f'/admin/api/v1/catalog-nodes/{node}/knowledge-mappings').json()['data']
    response=client.put(f'/admin/api/v1/catalog-nodes/{node}/knowledge-mappings',headers=headers|{'If-Match':f'"{mapping["lock_version"]}"'},json={'items':mapping['items']+[{'knowledge_revision_id':revision['id'],'role':'primary'}],'reason':'隔离测试同主题两个点'})
    assert response.status_code==200,response.text
    for identity in (first,point['id']):
        view=matrix(client,identity);policy=policy_body(view)
        for cell in policy['policies']:
            if cell['difficulty']=='standard' and (identity==first or cell['question_type']=='answer'):
                cell['count_options'],cell['default_count']=[3,6,12],3
        response=client.put(f'/admin/api/v1/knowledge-points/{identity}/quantity-policies',headers=headers|{'If-Match':f'"{view["lock_version"]}"'},json=policy)
        assert response.status_code==200,response.text
    user=user_headers(client,headers)
    selection=select_body(node,first)|{'knowledge_point_ids':[first,point['id']],'difficulty':'standard'}
    capabilities=client.post('/api/v1/capabilities',headers=user,json=selection).json()['data']
    desired={'choice':3,'fill':3,'answer':3}
    assert desired in capabilities['feasible_counts']
    assert {'choice':3,'fill':3,'answer':0} not in capabilities['feasible_counts']
    body=selection|{'question_type_counts':desired,'content_epoch':capabilities['content_epoch']}
    return engine,client,user,body,headers,imported|{'drafts':drafts}


def test_mixed_counts_primary_links_snapshot_and_dedupe(mixed_prepared,monkeypatch):
    engine,client,_,body,*_=mixed_prepared
    monkeypatch.setattr(paper_jobs,'executor_ready',lambda *args:True)
    response=submit(mixed_prepared)
    assert response.status_code==202,response.text
    assert run(mixed_prepared)
    job=client.get('/api/v1/jobs/'+response.json()['data']['id']).json()['data']
    assert job['status']=='succeeded',job
    paper=client.get('/api/v1/papers/'+job['paper_id']).json()['data']
    assert paper['total_count']==9 and paper['question_type_counts']==body['question_type_counts']
    assert [q['question_type'] for q in paper['questions']]==['choice']*3+['fill']*3+['answer']*3
    assert {q['primary_knowledge_code'] for q in paper['questions']}=={'O002','O003'}
    assert len({(q['render_spec']['multiplicand'],q['render_spec']['multiplier']) for q in paper['questions']})==9
    with Session(engine) as session:
        assert len(set(session.scalars(select(Question.template_version_id))))>=3
        assert len(set(session.scalars(select(QuestionKnowledge.knowledge_revision_id))))==2


def test_mixed_stop_one_source_before_final_commit(mixed_prepared,monkeypatch):
    engine,client,_,_,headers,imported=mixed_prepared
    monkeypatch.setattr(paper_jobs,'executor_ready',lambda *args:True)
    response=submit(mixed_prepared)
    target=imported['drafts'][-1]
    disabled=client.post('/admin/api/v1/templates/'+target['template_id']+'/disable',headers=headers|{'If-Match':'"2"'},json={'reason':'测试受理后停用'})
    assert disabled.status_code==200,disabled.text
    assert run(mixed_prepared)
    job=client.get('/api/v1/jobs/'+response.json()['data']['id']).json()['data']
    assert job['status']=='failed' and counts(engine)==(0,0,None)


@pytest.mark.skipif(os.environ.get('PAPR_TEST_BROWSER')!='1',reason='Real mixed paper browser and PDFs')
def test_browser_mixed_paper(mixed_prepared,tmp_path):
    engine,client,*_=mixed_prepared
    with browser_services(engine,client.app.state.settings) as (settings,origins):
        browser_script(settings,origins,'browser_mixed.mjs',tmp_path)
