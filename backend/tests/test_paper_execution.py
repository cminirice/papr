"""Real SQLite/queue/math/storage/HTTP; PDF rendering and page inspection are doubles."""
from dataclasses import replace
from datetime import timedelta
import os
from pathlib import Path
from hashlib import sha256
import json
import subprocess
import sys
from uuid import uuid4
import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from alembic import command
from test_content_seed import storage, NOW
from test_template_edit import editor
from test_releases import ready
from test_capabilities import opened, user_headers
from test_paper_jobs import prepared, admission, submit
from test_pdf_inspection_macos import fixture_pdf
from test_pdf_storage import fake_inspector
from app.core.database import write_transaction
from app.models.identity import AppUser, UserSession
from app.models.jobs import Job
from app.models.papers import Paper, Question, FileAsset
from app.services import paper_execution as execution, paper_runtime
from app.services.content_seed import canonical
from app.services.pdf_storage import save_pair


def renderer(document, settings, pulse):
    pulse()
    contents = {'student_pdf': fixture_pdf(), 'solution_pdf': fixture_pdf() + b'\n% solution\n'}
    metadata = {'renderer_version': 'papr-chromium-v1', 'content_schema_version': 1,
        'input_sha256': sha256(canonical(document).encode()).hexdigest(),
        'font_sha256': 'a' * 64, 'print_asset_sha256': 'b' * 64,
        'student_sha256': sha256(contents['student_pdf']).hexdigest(),
        'solution_sha256': sha256(contents['solution_pdf']).hexdigest(),
        'browser_version': 'test-double', 'vue_version': 'test-double', 'playwright_version': 'test-double'}
    return contents, metadata


def store(root, targets, contents):
    return save_pair(root, targets, contents, inspector=fake_inspector)


def run(fixture, **kwargs):
    engine, client, *_ = fixture
    return execution.run_once(engine, client.app.state.settings, clock=lambda: client.app.state.clock(),
                              renderer=kwargs.pop('renderer', renderer), store=store, **kwargs)


def counts(engine):
    with Session(engine) as session:
        return (session.scalar(select(func.count()).select_from(Paper)),
                session.scalar(select(func.count()).select_from(FileAsset).where(FileAsset.status == 'ready')),
                session.scalar(select(AppUser)).next_generation_at)


def test_success_history_files_idempotency_and_real_cooldown(admission):
    engine, client, headers, *_ = admission
    key = str(uuid4())
    identity = submit(admission, key).json()['data']['id']
    assert run(admission)
    assert counts(engine) == (1, 2, NOW + timedelta(seconds=600))
    assert not run(admission)
    job = client.get(f'/api/v1/jobs/{identity}').json()['data']
    assert job['status'] == 'succeeded' and job['progress_done'] == 3
    assert submit(admission, key).json()['data'] == job
    listing = client.get('/api/v1/papers').json()['data']
    assert len(listing['items']) == 1 and not listing['has_more']
    paper = client.get('/api/v1/papers/' + job['paper_id']).json()['data']
    assert len(paper['questions']) == 3 and len(paper['files']) == 2
    assert paper['question_type_counts'] == {'choice': 0, 'fill': 0, 'answer': 3}
    assert paper['catalog_name'] and paper['theme_name']
    for field in ('catalog_name', 'theme_name', 'question_type_counts'):
        assert listing['items'][0][field] == paper[field]
    for file in paper['files']:
        response = client.get('/api/v1/files/' + file['id'])
        assert response.status_code == 200 and response.headers['content-type'] == 'application/pdf'
        assert response.headers['cache-control'] == 'no-store'
        assert 'attachment' in response.headers['content-disposition']
        assert response.content.startswith(b'%PDF-')
        assert client.get('/api/v1/files/' + file['id'] + '?disposition=inline').status_code == 200
    assert counts(engine)[2] == NOW + timedelta(seconds=600)
    client.app.state.clock = lambda: NOW + timedelta(seconds=599)
    response = submit(admission)
    assert response.status_code == 429 and response.headers['retry-after'] == '1'
    client.app.state.clock = lambda: NOW + timedelta(seconds=600)
    assert submit(admission).status_code == 202


def test_pdf_failure_is_terminal_without_paper_or_cooldown(admission):
    engine, client, *_ = admission
    identity = submit(admission).json()['data']['id']
    def broken(*args):
        raise RuntimeError('/private/secret/render failed')
    assert run(admission, renderer=broken)
    job = client.get('/api/v1/jobs/' + identity).json()['data']
    assert job['status'] == 'failed' and '/private' not in str(job)
    assert counts(engine) == (0, 0, None)
    with Session(engine) as session:
        assert {a.status for a in session.scalars(select(FileAsset))} == {'failed'}
    assert submit(admission).status_code == 202


def test_saved_selection_reuses_public_config_with_fresh_job_after_cooldown(admission):
    engine, client, headers, original_body, *_ = admission
    submit(admission)
    assert run(admission)
    first = client.get('/api/v1/papers').json()['data']['items'][0]
    url = '/api/v1/papers/' + first['id']
    detail = client.get(url).json()['data']
    selection = detail['selection']
    assert set(selection) == {'catalog_id', 'theme_id', 'knowledge_point_ids', 'difficulty', 'question_type_counts'}
    assert selection['catalog_id'] == client.get('/api/v1/catalogs').json()['data'][0]['id']
    public = {k: v for k, v in selection.items() if k != 'catalog_id'}
    assert public == {k: v for k, v in original_body.items() if k != 'content_epoch'}
    capability_body = {k: public[k] for k in ('theme_id', 'knowledge_point_ids', 'difficulty')}
    capability = client.post('/api/v1/capabilities', json=capability_body, headers=headers).json()['data']
    body = public | {'content_epoch': capability['content_epoch']}
    assert counts(engine)[2] == NOW + timedelta(seconds=600)
    client.app.state.clock = lambda: NOW + timedelta(seconds=599)
    assert submit(admission, body=body).status_code == 429
    client.app.state.clock = lambda: NOW + timedelta(seconds=600)
    accepted = submit(admission, body=body)
    assert accepted.status_code == 202
    assert run(admission)
    job = client.get('/api/v1/jobs/' + accepted.json()['data']['id']).json()['data']
    assert job['paper_id'] != first['id']
    second = client.get('/api/v1/papers/' + job['paper_id']).json()['data']
    assert second['selection'] == selection
    assert {q['id'] for q in second['questions']}.isdisjoint(q['id'] for q in detail['questions'])
    assert client.get(url).json()['data'] == detail
    client.cookies.clear()
    assert client.get(url).status_code == 401
    user_headers(client, headers)
    assert client.get(url).status_code == 404


def test_content_disabled_during_render_cannot_commit(admission):
    engine, client, headers, _, admin, imported = admission
    submit(admission)
    def disabling(document, settings, pulse):
        response = client.post('/admin/api/v1/templates/' + imported['template_id'] + '/disable',
            json={'reason': '测试生成中停用'}, headers=admin | {'If-Match': '"2"'})
        assert response.status_code == 200
        return renderer(document, settings, pulse)
    assert run(admission, renderer=disabling)
    assert counts(engine) == (0, 0, None)
    assert client.get('/api/v1/jobs').json()['data']['items'][0]['error_code'] == 'CONTENT_UNAVAILABLE'


def test_commit_failure_rolls_back_then_new_attempt_keeps_questions(admission):
    engine, client, *_ = admission
    identity = submit(admission).json()['data']['id']
    def fail_commit(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith('UPDATE app_user ') and 'next_generation_at' in statement:
            raise SQLAlchemyError('simulated publication failure')
    event.listen(engine, 'before_cursor_execute', fail_commit)
    try:
        with pytest.raises(SQLAlchemyError):
            run(admission)
    finally:
        event.remove(engine, 'before_cursor_execute', fail_commit)
    assert counts(engine) == (0, 0, None)
    root = client.app.state.settings.generated_root
    assert len(list(root.rglob('*.pdf'))) == 2
    with Session(engine) as session:
        job = session.get(Job, identity)
        snapshot = job.intermediate_snapshot
        old_ids = set(session.scalars(select(FileAsset.id)))
        assert job.status == 'running'
    client.app.state.clock = lambda: NOW + timedelta(seconds=31)
    assert run(admission)
    assert counts(engine) == (1, 2, NOW + timedelta(seconds=631))
    with Session(engine) as session:
        job = session.get(Job, identity)
        assert job.attempt == 2 and job.intermediate_snapshot == snapshot
        assert {session.get(FileAsset, i).status for i in old_ids} == {'failed'}
        assert len(session.scalars(select(Question)).all()) == 3
    assert len(list(root.rglob('*.pdf'))) == 4


def test_expired_worker_cannot_renew_or_publish_and_retry_limit(admission):
    engine, client, *_ = admission
    identity = submit(admission).json()['data']['id']
    first = execution.claim(engine, NOW)
    second = execution.claim(engine, NOW + timedelta(seconds=30))
    assert first['attempt'] == 1 and second['attempt'] == 2
    with pytest.raises(execution.LeaseLost):
        execution.renew(engine, first, NOW + timedelta(seconds=30))
    with pytest.raises(execution.LeaseLost):
        execution.finish(engine, first, {}, {}, {}, NOW + timedelta(seconds=30))
    assert execution.claim(engine, NOW + timedelta(seconds=60)) is None
    with Session(engine) as session:
        assert session.get(Job, identity).status == 'failed'
    assert counts(engine) == (0, 0, None)


def test_files_authorization_corruption_withdrawal_and_cookie_renewal(admission):
    engine, client, _, _, admin, _ = admission
    submit(admission)
    run(admission)
    paper = client.get('/api/v1/papers').json()['data']['items'][0]
    file_id = paper['files'][0]['id']
    with write_transaction(engine) as session:
        stored = session.scalar(select(UserSession))
        stored.expires_at = NOW + timedelta(days=1)
    assert 'set-cookie' in client.get('/api/v1/files/' + file_id).headers
    with Session(engine) as session:
        key = session.get(FileAsset, file_id).storage_key
    (client.app.state.settings.generated_root / key).write_bytes(b'bad')
    response = client.get('/api/v1/files/' + file_id)
    assert response.status_code == 503 and response.json()['error']['code'] == 'FILE_UNAVAILABLE'
    client.cookies.clear()
    assert client.get('/api/v1/files/' + file_id).status_code == 401
    user_headers(client, admin)
    assert client.get('/api/v1/files/' + file_id).status_code == 404
    assert client.get('/api/v1/papers/' + paper['id']).status_code == 404
    assert client.get('/api/v1/papers').json()['data']['items'] == []


def test_pending_files_invisible_and_registration_date_survives_midnight(admission):
    engine, client, *_ = admission
    submit(admission)
    def crossing(document, settings, pulse):
        with Session(engine) as session:
            assets = session.scalars(select(FileAsset)).all()
            assert len(assets) == 2
            for asset in assets:
                assert asset.storage_key.startswith('20300101/')
                assert client.get('/api/v1/files/' + asset.id).status_code == 404
        client.app.state.clock = lambda: NOW + timedelta(seconds=2)
        return renderer(document, settings, pulse)
    run(admission, renderer=crossing)
    assert counts(engine) == (1, 2, NOW + timedelta(seconds=602))
    with Session(engine) as session:
        assert all(a.storage_key.startswith('20300101/') for a in session.scalars(select(FileAsset)))


def test_readiness_requires_matching_live_worker(storage, monkeypatch):
    settings, engine, _ = storage
    monkeypatch.setattr(paper_runtime, 'config_hash', lambda s: 'a' * 64)
    with Session(engine) as session:
        assert not paper_runtime.ready(session, settings, NOW)
    paper_runtime.heartbeat(engine, 'a' * 64, NOW)
    with Session(engine) as session:
        assert paper_runtime.ready(session, settings, NOW + timedelta(seconds=29))
        assert not paper_runtime.ready(session, settings, NOW + timedelta(seconds=30))
    paper_runtime.withdraw(engine, 'a' * 64, NOW)
    with Session(engine) as session:
        assert not paper_runtime.ready(session, settings, NOW)
    monkeypatch.setattr(paper_runtime, 'config_hash', lambda s: 'b' * 64)
    with Session(engine) as session:
        assert not paper_runtime.ready(session, settings, NOW)


def test_migration_matches_metadata_and_refuses_history_loss(admission, storage):
    _, _, config = storage
    command.check(config)
    submit(admission)
    run(admission)
    with pytest.raises(RuntimeError, match='禁止自动降级'):
        command.downgrade(config, '0006')


def test_subprocess_timeout_and_renewal_abort():
    args = [sys.executable, '-c', 'import time; time.sleep(30)']
    with pytest.raises(TimeoutError):
        paper_runtime.process(args, data='', timeout=0.05)
    def lost():
        raise execution.LeaseLost()
    with pytest.raises(execution.LeaseLost):
        paper_runtime.process(args, data='', timeout=10, pulse=lost)


def test_detached_descendant_is_terminated(tmp_path):
    marker = tmp_path / 'child-status'
    pid_file = tmp_path / 'browser.pid'
    child_code = ('import signal,time,sys; from pathlib import Path; '
                  'p=Path(sys.argv[1]); '
                  'signal.signal(signal.SIGTERM, lambda *args: (p.write_text("stopped"), sys.exit(0))); '
                  'p.write_text("ready"); time.sleep(30)')
    parent_code = ('import subprocess,sys,time,signal; from pathlib import Path; '
                   'child=subprocess.Popen([sys.executable,"-c",sys.argv[1],sys.argv[2]],start_new_session=True); '
                   'Path(sys.argv[3]).write_text(str(child.pid)); '
                   'signal.signal(signal.SIGTERM, lambda *args: (child.wait(), sys.exit(0))); time.sleep(30)')
    with pytest.raises(TimeoutError):
        paper_runtime.process([sys.executable, '-c', parent_code, child_code, str(marker), str(pid_file)],
                              data='', timeout=1, browser_pid_file=pid_file)
    assert marker.read_text() == 'stopped'


@pytest.mark.skipif(os.environ.get('PAPR_TEST_REAL_PDF') != '1', reason='Opt-in: requires real Chrome and native PDF parser')
def test_real_pdf_end_to_end(prepared):
    """Temporary content approval fixture; real browser, parser, worker and download."""
    engine, client, *_ = prepared
    settings = replace(client.app.state.settings,
        pdf_node=Path(os.environ.get('PAPR_PDF_NODE', '/Users/eric/.local/node-v22.23.2/bin/node')),
        pdf_browser=Path(os.environ.get('PAPR_PDF_BROWSER', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')),
        pdf_font=Path(os.environ.get('PAPR_PDF_FONT', '/System/Library/Fonts/Supplemental/Arial Unicode.ttf')))
    client.app.state.settings = settings
    assert submit(prepared).status_code == 503
    paper_runtime.probe(settings)
    fingerprint = paper_runtime.config_hash(settings)
    assert fingerprint
    paper_runtime.heartbeat(engine, fingerprint, NOW)
    try:
        response = submit(prepared)
        assert response.status_code == 202, response.text
        identity = response.json()['data']['id']
        assert execution.run_once(engine, settings, clock=lambda: NOW, fingerprint=fingerprint)
        job = client.get('/api/v1/jobs/' + identity).json()['data']
        assert job['status'] == 'succeeded', job
        assert counts(engine) == (1, 2, NOW + timedelta(seconds=600))
        paper = client.get('/api/v1/papers/' + job['paper_id']).json()['data']
        from app.services.pdf_storage import inspect_bytes
        pages = {}
        for file in paper['files']:
            response = client.get('/api/v1/files/' + file['id'])
            assert response.status_code == 200
            report = inspect_bytes(response.content)
            assert report['pdf_parser_checked'] and report['pages'] == file['pages']
            pages[file['kind']] = report['pages']
        assert pages['solution_pdf'] > pages['student_pdf']
    finally:
        paper_runtime.withdraw(engine, fingerprint, NOW)


def test_history_pagination_preserves_withdrawn_snapshot_without_downloads(admission):
    engine, client, _, _, admin, imported = admission
    submit(admission)
    run(admission)
    original = client.get('/api/v1/papers').json()['data']['items'][0]
    before = client.get('/api/v1/papers/' + original['id']).json()['data']
    client.app.state.clock = lambda: NOW + timedelta(seconds=600)
    assert submit(admission).status_code == 202
    run(admission)
    first = client.get('/api/v1/papers?limit=1').json()['data']
    assert first['has_more'] and first['items'][0]['id'] != original['id']
    second = client.get('/api/v1/papers', params={'limit': 1, 'cursor': first['next_cursor']}).json()['data']
    assert not second['has_more'] and second['items'][0]['id'] == original['id']
    assert client.get('/api/v1/papers?cursor=bad').status_code == 422
    response = client.post('/admin/api/v1/templates/' + imported['template_id'] + '/disable',
        json={'reason': '测试历史不随模板变化'}, headers=admin | {'If-Match': '"2"'})
    assert response.status_code == 200
    assert client.get('/api/v1/papers/' + original['id']).json()['data'] == before
    assert client.get('/api/v1/files/' + original['files'][0]['id']).status_code == 200
    with write_transaction(engine) as session:
        session.get(Paper, original['id']).status = 'withdrawn'
    withdrawn = client.get('/api/v1/papers/' + original['id']).json()['data']
    assert withdrawn['status'] == 'withdrawn' and withdrawn['files'] == []
    assert withdrawn['questions'] == before['questions']
    assert client.get('/api/v1/files/' + original['files'][0]['id']).status_code == 404
    assert counts(engine)[2] == NOW + timedelta(seconds=1200)


def test_temporary_database_and_ready_files_backup_restore(admission, tmp_path):
    import shutil
    import sqlite3
    from fastapi.testclient import TestClient
    from app.main import create_app
    engine, client, *_ = admission
    submit(admission)
    run(admission)
    settings = client.app.state.settings
    backup = tmp_path / 'restored'
    backup.mkdir()
    db_path = backup / 'papr.sqlite3'
    with sqlite3.connect(f'{settings.db_path.as_uri()}?mode=ro', uri=True) as source, sqlite3.connect(db_path) as target:
        source.backup(target)
        assert target.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert target.execute('PRAGMA foreign_key_check').fetchall() == []
    shutil.copytree(settings.generated_root, backup / 'generated')
    restored = create_app(replace(settings, db_path=db_path, generated_root=backup / 'generated'))
    restored.state.clock = lambda: NOW
    with TestClient(restored, base_url=str(client.base_url)) as other:
        other.cookies.update(client.cookies)
        history = other.get('/api/v1/papers').json()['data']['items']
        assert len(history) == 1
        for file in history[0]['files']:
            assert other.get('/api/v1/files/' + file['id']).content == client.get('/api/v1/files/' + file['id']).content
        assert other.get('/api/v1/session').json()['data']['next_generation_at'] == (NOW + timedelta(seconds=600)).isoformat(timespec='microseconds')


def test_actual_worker_process_exit_leaves_recoverable_lease(admission):
    engine, client, *_ = admission
    identity = submit(admission).json()['data']['id']
    settings = client.app.state.settings
    code = ('import os,sys; from datetime import datetime; from pathlib import Path; '
            'from app.core.database import make_engine; from app.services.paper_execution import claim; '
            'job=claim(make_engine(Path(sys.argv[1])),datetime.fromisoformat(sys.argv[2])); '
            'os._exit(23 if job else 24)')
    result = subprocess.run([sys.executable, '-c', code, str(settings.db_path), NOW.isoformat()],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=10)
    assert result.returncode == 23
    with Session(engine) as session:
        job = session.get(Job, identity)
        assert job.status == 'running' and job.attempt == 1
        payload = job.payload
    assert counts(engine) == (0, 0, None)
    client.app.state.clock = lambda: NOW + timedelta(seconds=31)
    assert run(admission)
    with Session(engine) as session:
        job = session.get(Job, identity)
        assert job.status == 'succeeded' and job.attempt == 2 and job.payload == payload
    assert counts(engine) == (1, 2, NOW + timedelta(seconds=631))
