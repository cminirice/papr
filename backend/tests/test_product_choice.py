from copy import deepcopy
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


@pytest.mark.parametrize('difficulty,a,b', [('basic',123,12), ('standard',308,26), ('standard',100,80), ('standard',999,99)])
def test_choice_unique_math_shuffle_and_tamper(difficulty,a,b):
    profile = next(p for p in default_config().profiles if p.difficulty == difficulty)
    question = build_question(profile, MultiplicationParams(a=a,b=b), seed='choice-case', question_type='choice')
    assert question.answer.kind == 'single_choice'
    assert len({o.value for o in question.options}) == 4
    assert sum(int(o.value) == a*b for o in question.options) == 1
    assert next(o.value for o in question.options if o.id == question.answer.correct_option_id) == str(a*b)
    verify_question(question, profile)
    data = question.model_dump()
    for mutate in ('duplicate','wrong_id','random_distractor'):
        invalid = deepcopy(data)
        if mutate == 'duplicate': invalid['options'][0] = invalid['options'][1]
        elif mutate == 'wrong_id': invalid['answer']['correct_option_id'] = next(o.id for o in question.options if o.value != str(a*b))
        else: next(o for o in invalid['options'] if o['value'] != str(a*b))['value'] = '9999999'
        with pytest.raises(ValueError): verify_question(MultiplicationQuestion.model_validate(invalid), profile)
    positions = set()
    for index in range(20):
        questions = generate_paper(profile, seed=f'choice-{index}', count=12, question_type='choice')
        assert len({q.id for q in questions}) == 12
        for q in questions:
            verify_question(q,profile)
            positions.add(next(i for i,o in enumerate(q.options) if o.id == q.answer.correct_option_id))
    assert positions == {0,1,2,3}


@pytest.fixture
def choice_prepared(editor):
    return prepare_product(editor, 'choice')


@pytest.mark.parametrize('difficulty', ['basic','standard'])
def test_choice_public_generation(choice_prepared, monkeypatch, difficulty):
    _,client,_,body,*_ = choice_prepared
    monkeypatch.setattr(paper_jobs,'executor_ready',lambda *args: True)
    response = submit(choice_prepared,body=body | {'difficulty':difficulty})
    assert response.status_code == 202, response.text
    assert run(choice_prepared)
    job = client.get('/api/v1/jobs/'+response.json()['data']['id']).json()['data']
    assert job['status'] == 'succeeded',job
    paper = client.get('/api/v1/papers/'+job['paper_id']).json()['data']
    assert paper['question_type_counts'] == {'choice':3,'fill':0,'answer':0}
    assert all(q['question_type']=='choice' and len(q['options'])==4 for q in paper['questions'])


@pytest.mark.skipif(os.environ.get('PAPR_TEST_BROWSER') != '1', reason='Real Chrome choice PDFs')
def test_browser_choice_generation(choice_prepared,tmp_path,monkeypatch):
    engine,client,*_ = choice_prepared
    monkeypatch.setenv('PAPR_TEST_PRODUCT_TYPE','choice')
    with browser_services(engine,client.app.state.settings) as (settings,origins):
        browser_script(settings,origins,'browser_fill.mjs',tmp_path)
