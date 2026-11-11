import os
import pytest
from test_content_seed import storage, NOW
from test_template_edit import editor
from test_product_fill import prepare_product
from test_paper_jobs import submit
from test_paper_execution import run
from test_browser_flow import browser_services, browser_script
from app.generators.multiplication import build_question, generate_paper, verify_question, ERROR_REASONS
from app.schemas.content import MultiplicationQuestion, MultiplicationParams
from app.services.template_tools import default_config
from app.services import paper_jobs


@pytest.mark.parametrize('a,b',[(308,26),(100,80),(999,99)])
def test_error_choice_exact_process_and_reason(a,b):
    profile=default_config('error_choice').profiles[0]
    q=build_question(profile,MultiplicationParams(a=a,b=b),seed='reason',question_type='choice')
    verify_question(q,profile)
    assert q.render_mode=='vertical' and q.difficulty=='challenge'
    assert q.render_spec.incorrect_tens_partial==str(a*(b//10))
    assert q.render_spec.incorrect_result==str(a*(b%10)+a*(b//10))
    assert q.render_spec.incorrect_result!=str(a*b)
    assert q.answer.value==ERROR_REASONS[0]
    assert len({o.value for o in q.options})==4
    for field,value in [('incorrect_result','1'),('incorrect_tens_partial',str(a*(b//10)*10))]:
        data=q.model_dump();data['render_spec'][field]=value
        with pytest.raises(ValueError):verify_question(MultiplicationQuestion.model_validate(data),profile)
    data=q.model_dump();data['options'][0]['value']='无依据的选项'
    with pytest.raises(ValueError):verify_question(MultiplicationQuestion.model_validate(data),profile)
    questions=generate_paper(profile,seed='reason-paper',count=12,question_type='choice')
    assert len({q.id for q in questions})==12


@pytest.fixture
def reason_prepared(editor):
    return prepare_product(editor,'choice','error_choice')


def test_error_choice_published_generation(reason_prepared,monkeypatch):
    _,client,*_=reason_prepared
    monkeypatch.setattr(paper_jobs,'executor_ready',lambda *args:True)
    response=submit(reason_prepared)
    assert response.status_code==202,response.text
    assert run(reason_prepared)
    job=client.get('/api/v1/jobs/'+response.json()['data']['id']).json()['data']
    assert job['status']=='succeeded',job
    paper=client.get('/api/v1/papers/'+job['paper_id']).json()['data']
    assert all(q['answer']['value']==ERROR_REASONS[0] and q['render_spec']['incorrect_result'] for q in paper['questions'])


@pytest.mark.skipif(os.environ.get('PAPR_TEST_BROWSER')!='1',reason='Real error-reason PDF')
def test_browser_error_choice(reason_prepared,tmp_path,monkeypatch):
    engine,client,*_=reason_prepared
    monkeypatch.setenv('PAPR_TEST_PRODUCT_TYPE','choice')
    monkeypatch.setenv('PAPR_TEST_PRODUCT_TASK','error_choice')
    with browser_services(engine,client.app.state.settings) as (settings,origins):
        browser_script(settings,origins,'browser_fill.mjs',tmp_path)
