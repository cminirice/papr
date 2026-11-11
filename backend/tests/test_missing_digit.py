import os
import pytest
from test_content_seed import storage, NOW
from test_template_edit import editor
from test_product_fill import prepare_product
from test_paper_jobs import submit
from test_paper_execution import run
from test_browser_flow import browser_services, browser_script
from app.generators.multiplication import build_question, generate_paper, verify_question
from app.schemas.content import MultiplicationQuestion, MultiplicationParams
from app.services.template_tools import default_config
from app.services import paper_jobs


@pytest.mark.parametrize('a,b', [(123,12),(100,80),(909,99),(999,99)])
def test_missing_digit_unique_solution_and_tampering(a,b):
    profile=default_config('missing_digit').profiles[0]
    q=build_question(profile,MultiplicationParams(a=a,b=b),seed='missing',question_type='fill')
    assert q.answer.value == str(a)[1] and q.difficulty == 'challenge'
    assert q.render_spec.missing_digit_index == 1
    candidates=[d for d in range(10) if int(str(a)[0]+str(d)+str(a)[2])*b == a*b]
    assert candidates == [int(q.answer.value)]
    verify_question(q,profile)
    for field,value in [('answer',{'kind':'numeric','value':str((int(q.answer.value)+1)%10)}),
                        ('stem_blocks',[{'type':'text','text':'缺少条件的题目'}]),('render_mode','direct')]:
        with pytest.raises(ValueError):
            verify_question(MultiplicationQuestion.model_validate(q.model_dump()|{field:value}),profile)
    questions=generate_paper(profile,seed='missing-set',count=12,question_type='fill')
    assert len({(q.render_spec.multiplicand,q.render_spec.multiplier) for q in questions})==12
    assert questions==generate_paper(profile,seed='missing-set',count=12,question_type='fill')


@pytest.fixture
def missing_prepared(editor):
    return prepare_product(editor,'fill','missing_digit')


def test_missing_public_generation_and_fixed_answer(missing_prepared,monkeypatch):
    _,client,_,body,*_=missing_prepared
    assert body['difficulty']=='challenge'
    monkeypatch.setattr(paper_jobs,'executor_ready',lambda *args:True)
    accepted=submit(missing_prepared)
    assert accepted.status_code==202,accepted.text
    assert run(missing_prepared)
    job=client.get('/api/v1/jobs/'+accepted.json()['data']['id']).json()['data']
    assert job['status']=='succeeded',job
    paper=client.get('/api/v1/papers/'+job['paper_id']).json()['data']
    assert all(q['render_spec']['missing_digit_index']==1 and q['answer']['value']==q['render_spec']['multiplicand'][1] for q in paper['questions'])


@pytest.mark.skipif(os.environ.get('PAPR_TEST_BROWSER')!='1',reason='Real missing-digit PDF')
def test_browser_missing_digit(missing_prepared,tmp_path,monkeypatch):
    engine,client,*_=missing_prepared
    monkeypatch.setenv('PAPR_TEST_PRODUCT_TASK','missing_digit')
    with browser_services(engine,client.app.state.settings) as (settings,origins):
        browser_script(settings,origins,'browser_fill.mjs',tmp_path)
