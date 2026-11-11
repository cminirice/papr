"""Product fill: independent arithmetic, publication, immutable paper and real PDF opt-in."""
from copy import deepcopy
from datetime import timedelta
import os
import pytest
from test_content_seed import storage, NOW
from test_template_edit import editor
from test_releases import ready, prerequisites, approve
from test_capabilities import identifiers, enable, matrix, policy_body, user_headers, select_body
from test_paper_jobs import submit
from test_paper_execution import run, counts
from test_browser_flow import browser_services, browser_script
from app.generators.multiplication import build_question, generate_paper, verify_question, capacity
from app.schemas.content import MultiplicationQuestion, MultiplicationParams
from app.services.template_tools import default_config
from app.services import paper_jobs


@pytest.mark.parametrize('difficulty,a,b', [('basic', 123, 12), ('standard', 308, 26), ('standard', 999, 99)])
def test_fill_math_and_tamper(difficulty, a, b):
    profile = next(p for p in default_config().profiles if p.difficulty == difficulty)
    q = build_question(profile, MultiplicationParams(a=a, b=b), seed='fill-fixed', question_type='fill')
    assert q.question_type == 'fill' and q.render_mode == 'direct'
    assert q.answer.value == str(a * b)
    assert q.stem_blocks[-1].latex.endswith('=( )')
    verify_question(q, profile)
    for field, value in [('answer', {'kind': 'numeric', 'value': '1'}), ('render_mode', 'vertical'),
                         ('stem_blocks', [{'type': 'math', 'latex': '1+1='}])]:
        data = q.model_dump() | {field: value}
        with pytest.raises(ValueError):
            verify_question(MultiplicationQuestion.model_validate(data), profile)
    generated = generate_paper(profile, seed='fill-fixed', count=12, question_type='fill')
    assert generated == generate_paper(profile, seed='fill-fixed', count=12, question_type='fill')
    assert len({(q.render_spec.multiplicand, q.render_spec.multiplier) for q in generated}) == 12
    assert all(int(q.answer.value) == int(q.render_spec.multiplicand) * int(q.render_spec.multiplier) for q in generated)
    narrow = profile.model_copy(update={'a_min': a, 'a_max': a, 'b_min': b, 'b_max': b})
    assert capacity(narrow) == 1
    with pytest.raises(ValueError):
        generate_paper(narrow, seed='exhaust', count=3, question_type='fill')


def prepare_product(editor, kind='fill', task='product'):
    engine, client, headers, _, imported = editor
    choice = next(c for c in client.get('/admin/api/v1/generators').json()['data'] if c['available'])
    assert kind in choice['question_types']
    config = deepcopy(choice['task_configs'][task])
    for p in config['profiles']:
        p['layout']['answer_space_mm'] = 20
    response = client.post('/admin/api/v1/templates', headers=headers, json={
        'task': task, 'code': 'MUL_' + task.upper() + '_' + kind.upper(), 'name': '乘积' + kind, 'question_type': kind,
        'generator_id': choice['id'], 'objective_revision_id': choice['objective_revision_ids'][0],
        'config': config, 'reason': '隔离测试填空模板'})
    assert response.status_code == 201, response.text
    draft = response.json()['data']
    assert draft['question_type'] == kind and draft['editable']
    fill_editor = (engine, client, headers, '/admin/api/v1/template-versions/' + draft['id'],
                   imported | {'template_id': draft['template_id'], 'template_version_id': draft['id']})
    validated = ready.__wrapped__(fill_editor)
    assert validated[1]['report']['result'] == 'passed'
    assert all(q['question_type'] == kind for q in validated[1]['report']['samples'])
    prerequisites(fill_editor)
    payload = approve(validated)
    published = client.post('/admin/api/v1/templates/' + draft['template_id'] + '/publish', headers=headers, json=payload)
    assert published.status_code == 200, published.text
    catalog, node, point = identifiers(engine)
    enable(client, headers, catalog, node)
    view = matrix(client, point)
    policy = policy_body(view)
    for cell in policy['policies']:
        if cell['question_type'] == kind and cell['difficulty'] in ([p['difficulty'] for p in config['profiles']]):
            cell['count_options'], cell['default_count'] = [3, 6, 12], 3
    saved = client.put(f'/admin/api/v1/knowledge-points/{point}/quantity-policies', json=policy,
        headers=headers | {'If-Match': f'"{view["lock_version"]}"'})
    assert saved.status_code == 200, saved.text
    user = user_headers(client, headers)
    selection = select_body(node, point) | {'difficulty': config['profiles'][0]['difficulty']}
    effective = client.post('/api/v1/capabilities', json=selection, headers=user).json()['data']
    assert effective['count_options'][kind] == [3, 6, 12]
    body = selection | {'question_type_counts': {t: (3 if t == kind else 0) for t in ('choice', 'fill', 'answer')},
                                     'content_epoch': effective['content_epoch']}
    return engine, client, user, body, headers, fill_editor[4]


@pytest.fixture
def fill_prepared(editor):
    return prepare_product(editor)


@pytest.mark.parametrize('difficulty', ['basic', 'standard'])
def test_fill_public_generation_history_and_cooldown(fill_prepared, monkeypatch, difficulty):
    engine, client, _, body, *_ = fill_prepared
    monkeypatch.setattr(paper_jobs, 'executor_ready', lambda *args: True)
    accepted = submit(fill_prepared, body=body | {'difficulty': difficulty})
    assert accepted.status_code == 202, accepted.text
    assert run(fill_prepared)
    job = client.get('/api/v1/jobs/' + accepted.json()['data']['id']).json()['data']
    assert job['status'] == 'succeeded', job
    paper = client.get('/api/v1/papers/' + job['paper_id']).json()['data']
    assert paper['question_type_counts'] == {'choice': 0, 'fill': 3, 'answer': 0}
    assert all(q['question_type'] == 'fill' and q['render_mode'] == 'direct' for q in paper['questions'])
    assert counts(engine) == (1, 2, NOW + timedelta(seconds=600))
    for asset in paper['files']:
        assert client.get('/api/v1/files/' + asset['id']).status_code == 200
    assert counts(engine)[2] == NOW + timedelta(seconds=600)


@pytest.mark.skipif(os.environ.get('PAPR_TEST_BROWSER') != '1', reason='Real Chrome with actual fill PDFs')
def test_browser_fill_generation(fill_prepared, tmp_path):
    engine, client, *_ = fill_prepared
    with browser_services(engine, client.app.state.settings) as (settings, origins):
        browser_script(settings, origins, 'browser_fill.mjs', tmp_path)
