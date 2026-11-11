from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.security import check_csrf, initialize_rate_key, token_hash, verify_password
from app.core.config import Settings
from app.core.database import write_transaction
from app.core.errors import ServiceError
from app.core.time import BEIJING, serialize_time
from app.main import create_app
from app.models.identity import AppUser, UserSession, AdminUser, AdminSession, RateLimitEvent
from app.models.jobs import Job
from app.services.identity.cooldown import check_generation_admission, record_generation_success
from app.services.identity.sessions import initialize_admin, disable_admin, require_user, IdentityService

ORIGIN = 'http://127.0.0.1:5173'
ADMIN_ORIGIN = 'http://127.0.0.1:5174'
PASSWORD = 'test-only-long-password-纸上练'


@pytest.fixture
def context(tmp_path, monkeypatch):
    settings = Settings(tmp_path / 'identity.sqlite3', tmp_path / 'generated')
    monkeypatch.setenv('PAPR_DB_PATH', str(settings.db_path))
    config = Config(str(Path(__file__).resolve().parents[2] / 'alembic.ini'))
    command.upgrade(config, 'head')
    initialize_rate_key(settings.rate_limit_key_path)
    app = create_app(settings)
    now = [datetime(2030, 1, 1, 23, 59, 50, tzinfo=BEIJING)]
    app.state.clock = lambda: now[0]
    with TestClient(app, base_url=ORIGIN, client=('127.0.0.1', 1234)) as client:
        yield settings, app, client, now


def bootstrap(client):
    response = client.post('/api/v1/session', json={}, headers={'Origin': ORIGIN})
    assert response.status_code == 200, response.text
    return response.json()['data']


def login(app, client, now):
    initialize_admin(app.state.engine, 'owner', PASSWORD, now)
    response = client.post('/admin/api/v1/session/login', json={'username': 'owner', 'password': PASSWORD}, headers={'Origin': ADMIN_ORIGIN})
    assert response.status_code == 200, response.text
    return response.json()['data']


def new_job(user_id, now, *, key=None, status='queued'):
    return Job(kind='paper_generate', owner_user_id=user_id, idempotency_key=key or str(uuid4()), payload_hash='0' * 64,
        payload='{}', status=status, phase='queued', available_at=now, created_at=now, updated_at=now)


def test_persistent_cookie_hashes_and_restart(context):
    settings, app, client, now = context
    response = client.post('/api/v1/session', json={}, headers={'Origin': ORIGIN})
    data = response.json()['data']
    cookie = response.headers['set-cookie']
    assert all(part in cookie for part in ['HttpOnly', 'Max-Age=7776000', 'expires=', 'Path=/api/v1/', 'SameSite=lax'])
    assert 'Domain=' not in cookie
    assert response.headers['cache-control'] == 'no-store'
    raw_token = client.cookies.get('papr_user_session')
    with Session(app.state.engine) as session:
        stored = session.scalar(select(UserSession))
        assert stored.token_hash == token_hash(raw_token)
        assert stored.csrf_hash == token_hash(data['csrf_token'])
        assert session.scalar(select(func.count()).select_from(AppUser)) == 1
        dump = ' '.join(str(row) for row in session.execute(select(RateLimitEvent.subject_hash)))
        assert '127.0.0.1' not in dump
    reused = bootstrap(client)
    assert reused['user_id'] == data['user_id']
    assert reused['csrf_token'] != data['csrf_token']
    with sqlite3.connect(settings.db_path) as connection:
        dump = '\n'.join(connection.iterdump())
        assert raw_token not in dump and reused['csrf_token'] not in dump
        assert '+08:00' in dump
    restarted = create_app(settings)
    restarted.state.clock = lambda: now[0]
    with TestClient(restarted, base_url=ORIGIN, client=('127.0.0.1', 1234)) as other:
        other.cookies.set('papr_user_session', raw_token, path='/api/v1/')
        assert other.get('/api/v1/session').json()['data']['user_id'] == data['user_id']


def test_user_renewal_and_expired_identity(context):
    _, app, client, now = context
    original = bootstrap(client)
    token = client.cookies.get('papr_user_session')
    with write_transaction(app.state.engine) as session:
        stored = session.scalar(select(UserSession))
        stored.expires_at = now[0] + timedelta(days=6)
    response = client.get('/api/v1/session')
    assert response.json()['data']['expires_at'] == serialize_time(now[0] + timedelta(days=90))
    assert 'Max-Age=7776000' in response.headers['set-cookie']
    assert client.cookies.get('papr_user_session') == token
    with write_transaction(app.state.engine) as session:
        session.scalar(select(UserSession)).expires_at = now[0]
    assert client.get('/api/v1/session').status_code == 401
    assert bootstrap(client)['user_id'] != original['user_id']


@pytest.mark.parametrize('origin', [None, 'null', 'http://evil.example', ORIGIN + '.evil', ADMIN_ORIGIN])
def test_origin_rejected_before_identity_creation(context, origin):
    _, app, client, _ = context
    headers = {} if origin is None else {'Origin': origin}
    assert client.post('/api/v1/session', json={}, headers=headers).status_code == 403
    with Session(app.state.engine) as session:
        assert session.scalar(select(func.count()).select_from(AppUser)) == 0


def test_body_validation_and_no_credential_echo(context):
    _, _, client, _ = context
    assert client.post('/api/v1/session', content='{}', headers={'Origin': ORIGIN, 'Content-Type': 'text/plain'}).status_code == 415
    assert client.post('/api/v1/session', json={'user_id': str(uuid4())}, headers={'Origin': ORIGIN}).status_code == 422
    response = client.post('/admin/api/v1/session/login', json={'username': 'owner', 'password': PASSWORD, 'extra': True}, headers={'Origin': ADMIN_ORIGIN})
    assert response.status_code == 422 and PASSWORD not in response.text
    schema = client.get('/openapi.json').json()
    error_schema = schema['paths']['/admin/api/v1/session/login']['post']['responses']['422']['content']['application/json']['schema']
    assert error_schema['$ref'].endswith('/ErrorResponse')


def test_get_does_not_rotate_csrf_and_post_does(context):
    _, app, client, now = context
    data = bootstrap(client)
    client.get('/api/v1/session')
    with Session(app.state.engine) as session:
        stored = session.scalar(select(UserSession))
        check_csrf(data['csrf_token'], stored.csrf_hash)
    result = client.post('/api/v1/session/csrf', json={}, headers={'Origin': ORIGIN})
    assert result.status_code == 200
    fresh = result.json()['data']['csrf_token']
    with Session(app.state.engine) as session:
        _, stored = require_user(session, client.cookies.get('papr_user_session'), now[0])
        with pytest.raises(ServiceError, match='失效'):
            check_csrf(data['csrf_token'], stored.csrf_hash)
        check_csrf(fresh, stored.csrf_hash)
    client.cookies.clear()
    assert client.post('/api/v1/session/csrf', json={}, headers={'Origin': ORIGIN}).status_code == 401


def test_admin_login_separation_csrf_logout(context):
    _, app, client, now = context
    user = bootstrap(client)
    admin = login(app, client, now[0])
    admin_token = client.cookies.get('papr_admin_session')
    user_token = client.cookies.get('papr_user_session')
    assert client.get('/admin/api/v1/session').status_code == 200
    assert client.get('/admin/api/v1/session', headers={'Cookie': f'papr_admin_session={user_token}'}).status_code == 401
    assert client.get('/api/v1/session', headers={'Cookie': f'papr_user_session={admin_token}'}).status_code == 401
    endpoint = '/admin/api/v1/session/logout'
    for token in [None, user['csrf_token']]:
        headers = {'Origin': ADMIN_ORIGIN}
        if token:
            headers['X-CSRF-Token'] = token
        assert client.post(endpoint, json={}, headers=headers).status_code == 403
    response = client.post('/admin/api/v1/session/csrf', json={}, headers={'Origin': ADMIN_ORIGIN})
    csrf = response.json()['data']['csrf_token']
    assert client.post(endpoint, json={}, headers={'Origin': ADMIN_ORIGIN, 'X-CSRF-Token': admin['csrf_token']}).status_code == 403
    result = client.post(endpoint, json={}, headers={'Origin': ADMIN_ORIGIN, 'X-CSRF-Token': csrf})
    assert result.status_code == 204 and result.content == b''
    assert 'Path=/admin/api/v1/' in result.headers['set-cookie']
    assert client.get('/admin/api/v1/session', headers={'Cookie': f'papr_admin_session={admin_token}'}).status_code == 401
    assert client.get('/api/v1/session').json()['data']['user_id'] == user['user_id']


def test_admin_fixed_expiry_and_disable(context):
    _, app, client, now = context
    data = login(app, client, now[0])
    now[0] += timedelta(hours=7)
    response = client.get('/admin/api/v1/session')
    assert response.json()['data']['expires_at'] == data['expires_at']
    assert 'set-cookie' not in response.headers
    with write_transaction(app.state.engine) as session:
        disable_admin(session, session.get(AdminUser, data['admin_id']), now[0])
    assert client.get('/admin/api/v1/session').status_code == 401
    with Session(app.state.engine) as session:
        assert session.scalar(select(AdminSession)).revoked_at == now[0]


def test_admin_expiry_exact_boundary(context):
    _, app, client, now = context
    login(app, client, now[0])
    now[0] += timedelta(hours=8)
    assert client.get('/admin/api/v1/session').status_code == 401


def test_login_limit_persists_and_boundary(context):
    settings, app, client, now = context
    initialize_admin(app.state.engine, 'owner', PASSWORD, now[0])
    endpoint = '/admin/api/v1/session/login'
    for index in range(5):
        result = client.post(endpoint, json={'username': 'owner' if index % 2 else 'missing', 'password': 'wrong'}, headers={'Origin': ADMIN_ORIGIN, 'X-Forwarded-For': f'8.8.8.{index}'})
        assert result.status_code == 401
        assert result.json()['error']['code'] == 'LOGIN_FAILED'
    restarted = create_app(settings)
    restarted.state.clock = lambda: now[0]
    with TestClient(restarted, base_url=ORIGIN, client=('127.0.0.1', 1234)) as other:
        result = other.post(endpoint, json={'username': 'owner', 'password': PASSWORD}, headers={'Origin': ADMIN_ORIGIN})
        assert result.status_code == 429 and result.headers['Retry-After'] == '300'
        now[0] += timedelta(seconds=300)
        assert other.post(endpoint, json={'username': 'owner', 'password': PASSWORD}, headers={'Origin': ADMIN_ORIGIN}).status_code == 200


def test_identity_ip_limit_does_not_merge_users(context):
    settings, app, client, now = context
    app.state.settings = replace(settings, identity_limit=2)
    first = bootstrap(client)
    assert bootstrap(client)['user_id'] == first['user_id']
    client.cookies.clear()
    second = bootstrap(client)
    assert first['user_id'] != second['user_id']
    client.cookies.clear()
    result = client.post('/api/v1/session', json={}, headers={'Origin': ORIGIN, 'X-Forwarded-For': '8.8.8.8'})
    assert result.status_code == 429
    now[0] += timedelta(hours=1)
    assert bootstrap(client)['user_id'] not in {first['user_id'], second['user_id']}


def test_single_admin_no_overwrite_and_hash_outside_write_lock(context, monkeypatch):
    _, app, _, now = context
    from app.services.identity import sessions
    real_hash = sessions.hash_password
    def checked_hash(value):
        with write_transaction(app.state.engine):
            pass
        return real_hash(value)
    monkeypatch.setattr(sessions, 'hash_password', checked_hash)
    admin_id = initialize_admin(app.state.engine, 'owner', PASSWORD, now[0])
    with pytest.raises(ValueError, match='已存在'):
        initialize_admin(app.state.engine, 'other', 'different-password-long', now[0])
    with Session(app.state.engine) as session:
        admin = session.get(AdminUser, admin_id)
        assert admin.password_hash.startswith('$argon2id$')
        assert verify_password(admin.password_hash, PASSWORD)
        assert not verify_password(admin.password_hash, 'wrong')
    with pytest.raises(IntegrityError):
        with write_transaction(app.state.engine) as session:
            session.add(AdminUser(username='bypass', password_hash='x', created_at=now[0], updated_at=now[0]))


def test_cooldown_atomic_rollback_and_599_600_boundary(context):
    settings, app, client, now = context
    user_id = bootstrap(client)['user_id']
    with pytest.raises(RuntimeError):
        with write_transaction(app.state.engine) as session:
            record_generation_success(session, session.get(AppUser, user_id), now[0])
            session.flush()
            raise RuntimeError('模拟成功事务提交前失败')
    assert client.get('/api/v1/session').json()['data']['next_generation_at'] is None
    with write_transaction(app.state.engine) as session:
        record_generation_success(session, session.get(AppUser, user_id), now[0])
    with sqlite3.connect(settings.db_path) as connection:
        stored = connection.execute('select next_generation_at from app_user').fetchone()[0]
        assert stored == '2030-01-02T00:09:50.000000+08:00'
    now[0] += timedelta(seconds=599)
    assert client.get('/api/v1/session').json()['data']['can_generate'] is False
    with write_transaction(app.state.engine) as session:
        with pytest.raises(ServiceError) as exc:
            check_generation_admission(session, session.get(AppUser, user_id), now[0])
        assert exc.value.headers['Retry-After'] == '1'
    now[0] += timedelta(seconds=1)
    with write_transaction(app.state.engine) as session:
        check_generation_admission(session, session.get(AppUser, user_id), now[0])
    data = client.get('/api/v1/session').json()['data']
    assert data['can_generate'] is True and data['next_generation_at'] == stored


def test_active_job_and_failure_do_not_start_cooldown(context):
    _, app, client, now = context
    user_id = bootstrap(client)['user_id']
    with write_transaction(app.state.engine) as session:
        job = new_job(user_id, now[0]); session.add(job); session.flush(); job_id = job.id
    data = client.get('/api/v1/session').json()['data']
    assert data['active_job_id'] == job_id and data['next_generation_at'] is None and not data['can_generate']
    with write_transaction(app.state.engine) as session:
        job = session.get(Job, job_id); job.status = 'running'; job.phase = 'rendering'
    assert client.get('/api/v1/session').json()['data']['active_job_id'] == job_id
    with write_transaction(app.state.engine) as session:
        session.get(Job, job_id).status = 'failed'
    data = client.get('/api/v1/session').json()['data']
    assert data['active_job_id'] is None and data['next_generation_at'] is None and data['can_generate']


def test_two_connections_admission_and_unique_keys(context):
    _, app, client, now = context
    user_id = bootstrap(client)['user_id']
    def attempt():
        try:
            with write_transaction(app.state.engine) as session:
                check_generation_admission(session, session.get(AppUser, user_id), now[0])
                session.add(new_job(user_id, now[0]))
            return 'accepted'
        except ServiceError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(results) == ['ACTIVE_JOB_EXISTS', 'accepted']
    with pytest.raises(IntegrityError):
        with write_transaction(app.state.engine) as session:
            session.add(new_job(user_id, now[0]))
    with write_transaction(app.state.engine) as session:
        job = session.scalar(select(Job)); job.status = 'cancelled'; same_key = job.idempotency_key
    with pytest.raises(IntegrityError):
        with write_transaction(app.state.engine) as session:
            session.add(new_job(user_id, now[0], key=same_key))
    assert client.get('/api/v1/session').json()['data']['next_generation_at'] is None


def test_cli_and_security_key_are_idempotent(context, monkeypatch, capsys):
    settings, app, _, _ = context
    from app import cli
    before = settings.rate_limit_key_path.read_bytes()
    assert not initialize_rate_key(settings.rate_limit_key_path)
    assert settings.rate_limit_key_path.read_bytes() == before
    assert settings.rate_limit_key_path.stat().st_mode & 0o777 == 0o600
    monkeypatch.setattr(cli.getpass, 'getpass', lambda _: PASSWORD)
    assert cli.main(['init-admin', '--username', 'owner']) == 0
    assert cli.main(['init-admin', '--username', 'owner']) == 1
    assert PASSWORD not in capsys.readouterr().out
    with Session(app.state.engine) as session:
        assert session.scalar(select(func.count()).select_from(AdminUser)) == 1


def test_secure_configuration_and_missing_setup(context):
    settings, _, _, _ = context
    with pytest.raises(ValueError):
        replace(settings, user_origins=('http://example.com',))
    secure = replace(settings, cookie_secure=True, user_origins=('https://papr.example',), admin_origins=('https://papr.example',))
    app = create_app(secure)
    with TestClient(app, base_url='https://papr.example', client=('127.0.0.1', 1234)) as client:
        response = client.post('/api/v1/session', json={}, headers={'Origin': 'https://papr.example'})
        assert response.status_code == 200 and 'Secure' in response.headers['set-cookie']
    settings.rate_limit_key_path.unlink()
    app = create_app(settings)
    with TestClient(app, base_url=ORIGIN, client=('127.0.0.1', 1234)) as client:
        response = client.post('/api/v1/session', json={}, headers={'Origin': ORIGIN})
        assert response.status_code == 503 and response.json()['error']['code'] == 'SERVICE_NOT_READY'
        assert str(settings.rate_limit_key_path) not in response.text


def test_shared_dependencies_enforce_write_csrf(context):
    _, app, client, now = context
    from fastapi import Depends
    from app.auth.dependencies import current_user, current_admin, Principal

    @app.post('/api/v1/test-protected')
    def protected(principal: Principal = Depends(current_user)):
        return {'owner_id': principal.owner_id}

    @app.post('/admin/api/v1/test-protected')
    def admin_protected(principal: Principal = Depends(current_admin)):
        return {'owner_id': principal.owner_id}

    user = bootstrap(client)
    admin = login(app, client, now[0])
    user_headers = {'Origin': ORIGIN, 'X-CSRF-Token': user['csrf_token']}
    assert client.post('/api/v1/test-protected', json={}, headers=user_headers).json()['owner_id'] == user['user_id']
    assert client.post('/api/v1/test-protected', json={}, headers={'Origin': ORIGIN}).status_code == 403
    assert client.post('/api/v1/test-protected', json={}, headers={'Origin': ORIGIN, 'X-CSRF-Token': admin['csrf_token']}).status_code == 403
    assert client.post('/admin/api/v1/test-protected', json={}, headers={'Origin': ADMIN_ORIGIN, 'X-CSRF-Token': admin['csrf_token']}).json()['owner_id'] == admin['admin_id']


def test_concurrent_failed_logins_reserve_limit_before_hashing(context):
    _, app, _, now = context
    service = IdentityService(app.state.engine)
    initialize_admin(app.state.engine, 'owner', PASSWORD, now[0])
    def attempt(_):
        try:
            service.login('owner', 'wrong', '1' * 64, now[0])
        except ServiceError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(attempt, range(6)))
    assert results.count('LOGIN_FAILED') == 5 and results.count('RATE_LIMITED') == 1


def test_disabled_user_cannot_bootstrap_to_bypass_same_cookie(context):
    _, app, client, now = context
    user_id = bootstrap(client)['user_id']
    with write_transaction(app.state.engine) as session:
        session.get(AppUser, user_id).status = 'disabled'
    assert client.get('/api/v1/session').status_code == 401
    assert client.post('/api/v1/session', json={}, headers={'Origin': ORIGIN}).status_code == 401
    with Session(app.state.engine) as session:
        assert session.scalar(select(func.count()).select_from(AppUser)) == 1


def test_busy_database_is_retryable_without_path_leak(context):
    _, app, client, _ = context
    from sqlalchemy import event
    @event.listens_for(app.state.engine, 'checkout')
    def shorten_timeout(dbapi_connection, *_):
        dbapi_connection.execute('pragma busy_timeout=1')
    with write_transaction(app.state.engine):
        response = client.post('/api/v1/session', json={}, headers={'Origin': ORIGIN})
    assert response.status_code == 503
    assert response.json()['error']['code'] == 'DATABASE_BUSY'
    assert response.headers['Retry-After'] == '1'
    assert 'sqlite' not in response.text.lower()
