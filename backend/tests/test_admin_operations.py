from datetime import timedelta
from uuid import uuid4
import json

from alembic import command
from test_paper_execution import admission, prepared, opened, ready, editor, storage, NOW, run
from test_paper_jobs import submit
from test_capabilities import user_headers
from app.core.database import write_transaction
from app.models.jobs import Job
from app.models.papers import Paper


def data(client, path, **params):
    response = client.get('/admin/api/v1/' + path, params=params)
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    return response.json()['data']


def test_empty_stats_dates_validation_and_admin_only(editor):
    _, client, *_ = editor
    stats = data(client, 'overview')
    assert stats['date_from'] == '2029-12-26' and stats['date_to'] == '2030-01-01'
    assert len(stats['daily']) == 7 and all(value == 0 for value in stats['totals'].values())
    assert data(client, 'jobs')['items'] == []
    for params in ({'date_from': '2030-01-01'}, {'date_to': '2030-01-01'},
                   {'date_from': '2030-01-02', 'date_to': '2030-01-01'},
                   {'date_from': '2029-01-01', 'date_to': '2030-01-01'},
                   {'date_from': '9999-12-31', 'date_to': '9999-12-31'},
                   {'date_from': '2030-01-01T00:00:00+08:00', 'date_to': '2030-01-01'}):
        for route in ('overview', 'jobs'):
            assert client.get('/admin/api/v1/' + route, params=params).status_code == 422
    for params in ({'kind': 'invalid'}, {'status': 'passed'}, {'limit': 101}, {'cursor': 'bad'}):
        assert client.get('/admin/api/v1/jobs', params=params).status_code == 422
    assert client.get('/admin/api/v1/jobs/' + str(uuid4())).status_code == 404
    client.cookies.clear()
    user_headers(client, {})
    for path in ('overview', 'jobs', 'jobs/' + str(uuid4())):
        assert client.get('/admin/api/v1/' + path).status_code == 401


def test_cross_midnight_independent_counts_retry_replay_and_queues(admission):
    engine, client, *_ = admission
    key = str(uuid4())
    job_id = submit(admission, key).json()['data']['id']
    client.app.state.clock = lambda: NOW + timedelta(seconds=1)  # Exact Beijing midnight.
    assert run(admission)
    assert submit(admission, key).status_code == 200
    paper_id = data(client, 'jobs/' + job_id)['job']['paper_id']
    assert len(data(client, 'jobs/' + job_id)['questions']) == 3
    # Retrying and later withdrawal must not double count or erase a successful generation.
    with write_transaction(engine) as session:
        session.get(Job, job_id).attempt = 2
        session.get(Paper, paper_id).status = 'withdrawn'
    client.app.state.clock = lambda: NOW + timedelta(seconds=601)
    failed_id = submit(admission).json()['data']['id']
    def broken(*args):
        raise RuntimeError('private renderer path')
    assert run(admission, renderer=broken)
    cancelled_id = submit(admission).json()['data']['id']
    assert client.post('/api/v1/jobs/' + cancelled_id + '/cancel', json={}, headers=admission[2]).status_code == 200
    assert submit(admission).status_code == 202
    stats = data(client, 'overview', date_from='2030-01-01', date_to='2030-01-02')
    assert stats['totals'] == {'submitted': 4, 'succeeded': 1, 'failed': 1, 'cancelled': 1, 'active_subjects': 1}
    assert stats['daily'][0] == {'date': '2030-01-01', 'submitted': 1, 'succeeded': 0, 'failed': 0, 'cancelled': 0, 'active_subjects': 1}
    assert stats['daily'][1]['active_subjects'] == 1
    assert stats['daily'][1]['succeeded'] == 1
    assert stats['generation_queue'] == {'queued': 1, 'running': 0}
    jan1 = data(client, 'overview', date_from='2030-01-01', date_to='2030-01-01')
    assert jan1['totals']['succeeded'] == 0 and jan1['generation_queue']['queued'] == 1
    jan2_jobs = data(client, 'jobs', date_from='2030-01-02', date_to='2030-01-02', kind='paper_generate')
    assert len(jan2_jobs['items']) == 3 and job_id not in {j['id'] for j in jan2_jobs['items']}
    failed = data(client, 'jobs', status='failed')['items']
    assert len(failed) == 1 and failed[0]['id'] == failed_id and failed[0]['error_code'] == 'GENERATION_FAILED'
    validation = data(client, 'jobs', kind='template_validate')['items']
    assert len(validation) == 1 and validation[0]['validation_status'] == 'passed'
    assert data(client, 'jobs/' + validation[0]['id'])['validation']['report']['result'] == 'passed'


def test_cursor_ties_source_version_and_sensitive_fields(admission):
    engine, client, *_ = admission
    source_id = submit(admission).json()['data']['id']
    with write_transaction(engine) as session:
        original = session.get(Job, source_id)
        for _ in range(23):
            session.add(Job(id=str(uuid4()), kind=original.kind, owner_user_id=original.owner_user_id,
                idempotency_key=str(uuid4()), payload_hash=original.payload_hash, payload=original.payload,
                status='failed', phase='done', attempt=2, created_at=NOW, updated_at=NOW,
                available_at=NOW, finished_at=NOW, error_code='SECRET/internal/path', error_message='private-key-value'))
    items, cursor = [], None
    while True:
        page = data(client, 'jobs', kind='paper_generate', limit=7, **({'cursor': cursor} if cursor else {}))
        items.extend(page['items'])
        if not page['has_more']:
            break
        cursor = page['next_cursor']
    assert len(items) == len({j['id'] for j in items}) == 24
    assert [j['id'] for j in items] == sorted([j['id'] for j in items], reverse=True)
    assert all(j['template_version_id'] == admission[-1]['template_version_id'] and j['version_no'] == 1 for j in items)
    view = data(client, 'jobs/' + next(j['id'] for j in items if j['status'] == 'failed'))
    assert view['job']['error_code'] == 'TASK_FAILED'
    raw = json.dumps(view)
    for secret in ('SECRET', 'private-key-value', 'lease_token', 'owner_user_id', 'idempotency_key', 'payload', 'storage_key'):
        assert secret not in raw
    # Unpublished/pending task detail never returns the intermediate generated snapshot.
    assert data(client, 'jobs/' + source_id)['questions'] == []


def test_new_indexes_migrate_and_downgrade_without_data_loss(storage):
    settings, engine, config = storage
    command.check(config)
    command.downgrade(config, '0007')
    command.upgrade(config, 'head')
    command.check(config)


def test_validation_queue_and_unsuccessful_report_are_not_generation_counts(editor):
    from test_validation_jobs import submit as submit_validation
    from app.services.validation_jobs import claim, finish
    from app.schemas.validation import ValidationReport
    engine, client, *_ = editor
    first, _ = submit_validation(editor)
    assert data(client, 'overview')['validation_queue'] == {'queued': 1, 'running': 0}
    claimed = claim(engine, NOW)
    assert data(client, 'overview')['validation_queue'] == {'queued': 0, 'running': 1}
    # Reporting fixture: execution succeeded, but content checks failed.
    report = ValidationReport(result='failed', sample_count=1, failure_count=1, coverage=[],
        failures_truncated=False, failures=[{'difficulty': 'basic', 'case_code': 'REPORT_FIXTURE',
            'error_code': 'TEST_CHECK_FAILED', 'message': '用于验证报告展示的失败样例'}])
    assert finish(engine, claimed, NOW, report=report)
    detail = data(client, 'jobs/' + first['job_id'])
    assert detail['job']['status'] == 'succeeded'
    assert detail['job']['validation_status'] == detail['validation']['report']['result'] == 'failed'
    assert all(value == 0 for value in data(client, 'overview')['totals'].values())
