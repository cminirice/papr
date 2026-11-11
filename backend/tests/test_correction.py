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


@pytest.mark.parametrize('a,b',[(308,26),(100,80),(999,99)])
def test_correction_answer_reason_and_process(a,b):
    profile=default_config('correction').profiles[0]
    q=build_question(profile,MultiplicationParams(a=a,b=b),seed='correct',question_type='answer')
    verify_question(q,profile)
    assert q.difficulty=='challenge' and not q.options
    assert q.answer.value==str(a*b)
    assert q.render_spec.incorrect_result==str(a*(b%10)+a*(b//10))
    assert '左移一位' in q.explanation_steps[1].blocks[0].text
    invalid=q.model_dump();invalid['explanation_steps'][1]['blocks'][0]['text']='不需要按十位对齐'
    with pytest.raises(ValueError):verify_question(MultiplicationQuestion.model_validate(invalid),profile)
    invalid=q.model_dump();invalid['answer']['value']=q.render_spec.incorrect_result
    with pytest.raises(ValueError):verify_question(MultiplicationQuestion.model_validate(invalid),profile)
    assert len(generate_paper(profile,seed='correct-paper',count=12,question_type='answer'))==12


@pytest.fixture
def correction_prepared(editor):
    return prepare_product(editor,'answer','correction')


def test_correction_published_generation(correction_prepared,monkeypatch):
    _,client,*_=correction_prepared
    monkeypatch.setattr(paper_jobs,'executor_ready',lambda *args:True)
    response=submit(correction_prepared)
    assert response.status_code==202,response.text
    assert run(correction_prepared)
    job=client.get('/api/v1/jobs/'+response.json()['data']['id']).json()['data']
    assert job['status']=='succeeded',job
    paper=client.get('/api/v1/papers/'+job['paper_id']).json()['data']
    assert all(q['difficulty']=='challenge' and q['question_type']=='answer' and q['answer']['value']==q['render_spec']['result'] for q in paper['questions'])


@pytest.mark.skipif(os.environ.get('PAPR_TEST_BROWSER')!='1',reason='Real correction PDF')
def test_browser_correction(correction_prepared,tmp_path,monkeypatch):
    engine,client,*_=correction_prepared
    monkeypatch.setenv('PAPR_TEST_PRODUCT_TYPE','answer')
    monkeypatch.setenv('PAPR_TEST_PRODUCT_TASK','correction')
    with browser_services(engine,client.app.state.settings) as (settings,origins):
        browser_script(settings,origins,'browser_fill.mjs',tmp_path)
