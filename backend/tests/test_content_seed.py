from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
import json
import sqlite3

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.security import initialize_rate_key
from app.core.config import Settings
from app.core.database import make_engine, write_transaction
from app.core.time import BEIJING
from app.main import create_app
from app.models.content import (ContentCatalog, GeneratorDefinition, KnowledgePoint, KnowledgeRevision,
    ObjectiveRevision, QuestionTemplate, TemplateProfile, TemplateTestCase, TemplateVersion)
from app.models.identity import AdminUser
from app.models.system import ContentEpoch
from app.services.content_seed import seed_content
from app.services.identity.sessions import initialize_admin

NOW = datetime(2030, 1, 1, 23, 59, 59, tzinfo=BEIJING)
PASSWORD = 'test-only-admin-password'


@pytest.fixture
def storage(tmp_path, monkeypatch):
    settings = Settings(tmp_path / 'content.sqlite3', tmp_path / 'generated')
    monkeypatch.setenv('PAPR_DB_PATH', str(settings.db_path))
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    command.upgrade(config, 'head')
    engine = make_engine(settings.db_path)
    initialize_admin(engine, 'owner', PASSWORD, NOW)
    yield settings, engine, config
    engine.dispose()


def test_seed_replay_preserves_drafts_and_beijing_time(storage):
    settings, engine, config = storage
    first = seed_content(engine, 'owner', NOW)
    again = seed_content(engine, 'owner', NOW + timedelta(days=1))
    assert first['created'] == 20
    assert again['created'] == 0 and again['unchanged'] == 20
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ContentCatalog)) == 2
        assert session.scalar(select(func.count()).select_from(TemplateTestCase)) == 5
        point = session.scalar(select(KnowledgePoint))
        assert session.get(KnowledgeRevision, point.current_revision_id).point_id == point.id
        assert session.scalar(select(TemplateVersion)).status == 'draft'
        assert session.scalar(select(QuestionTemplate)).current_published_version_id is None
        assert all(json.loads(p.validated_count_options) == [] for p in session.scalars(select(TemplateProfile)))
        assert session.get(ContentEpoch, 1).value == 0
    with sqlite3.connect(settings.db_path) as raw:
        assert raw.execute('PRAGMA foreign_key_check').fetchall() == []
        assert raw.execute('SELECT registered_at FROM generator_definition').fetchone()[0] == '2030-01-01T23:59:59.000000+08:00'
    command.check(config)


def test_parallel_import_is_idempotent(storage):
    _, engine, _ = storage
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: seed_content(engine, 'owner', NOW), range(2)))
    assert sorted(r['created'] for r in results) == [0, 20]


@pytest.mark.parametrize('model,field,value', [
    (TemplateProfile, 'param_config', '{"a_min":123}'),
    (GeneratorDefinition, 'artifact_hash', '0' * 64),
    (QuestionTemplate, 'name', '人工编辑的名称'),
])
def test_seed_refuses_to_overwrite_edits(storage, model, field, value):
    _, engine, _ = storage
    seed_content(engine, 'owner', NOW)
    with write_transaction(engine) as session:
        setattr(session.scalar(select(model)), field, value)
    with pytest.raises(ValueError, match='拒绝覆盖'):
        seed_content(engine, 'owner', NOW)
    with Session(engine) as session:
        assert getattr(session.scalar(select(model)), field) == value


def test_conflict_rolls_back_whole_import(storage):
    _, engine, _ = storage
    with write_transaction(engine) as session:
        session.add(QuestionTemplate(code='MUL_VERTICAL', name='已存在的内容'))
    with pytest.raises(ValueError, match='整批未写入'):
        seed_content(engine, 'owner', NOW)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ContentCatalog)) == 0
        assert session.scalar(select(func.count()).select_from(GeneratorDefinition)) == 0


def test_disabled_admin_and_missing_admin_cannot_import(storage):
    _, engine, _ = storage
    with pytest.raises(ValueError):
        seed_content(engine, 'absent', NOW)
    with write_transaction(engine) as session:
        session.scalar(select(AdminUser)).status = 'disabled'
    with pytest.raises(ValueError):
        seed_content(engine, 'owner', NOW)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ContentCatalog)) == 0


def test_populated_migration_downgrade_and_constraints(storage):
    _, engine, config = storage
    seed_content(engine, 'owner', NOW)
    for sql in ["UPDATE template_profile SET max_per_paper = 13",
                "UPDATE template_profile SET param_config = 'not-json'",
                "UPDATE objective_revision SET knowledge_revision_id = 'missing'",
                "UPDATE template_version SET status = 'published'",
                "UPDATE content_catalog SET updated_at = '2030-01-01T00:00:00Z'"]:
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.exec_driver_sql(sql)
    command.downgrade(config, '0002')
    with Session(engine) as session:
        assert session.scalar(select(AdminUser)).username == 'owner'
    command.upgrade(config, 'head')
    assert seed_content(engine, 'owner', NOW)['created'] == 20


def test_admin_read_api_and_user_isolation(storage):
    settings, engine, _ = storage
    seed_content(engine, 'owner', NOW)
    initialize_rate_key(settings.rate_limit_key_path)
    app = create_app(settings)
    app.state.clock = lambda: NOW
    with TestClient(app, base_url='http://127.0.0.1:5174', client=('127.0.0.1', 1234)) as client:
        assert client.get('/admin/api/v1/catalogs').status_code == 401
        assert client.post('/api/v1/session', json={}, headers={'Origin': 'http://127.0.0.1:5173'}).status_code == 200
        assert client.get('/admin/api/v1/templates').status_code == 401
        login = client.post('/admin/api/v1/session/login', json={'username': 'owner', 'password': PASSWORD},
                            headers={'Origin': 'http://127.0.0.1:5174'})
        assert login.status_code == 200
        catalogs = client.get('/admin/api/v1/catalogs?limit=1')
        assert catalogs.headers['cache-control'] == 'no-store'
        assert catalogs.json()['data']['total'] == 2
        assert len(catalogs.json()['data']['items']) == 1
        templates = client.get('/admin/api/v1/templates').json()['data']
        assert templates['items'][0]['current_published_version_id'] is None
        assert templates['items'][0]['updated_at'].endswith('+08:00')
        assert client.get('/admin/api/v1/templates?limit=1000').status_code == 422
        rejected = client.post('/admin/api/v1/templates', json={})
        assert rejected.status_code == 403
        assert rejected.json()['error']['code'] == 'ORIGIN_INVALID'
        origin = {'Origin': 'http://127.0.0.1:5174'}
        rejected = client.post('/admin/api/v1/templates', json={}, headers=origin)
        assert rejected.status_code == 403
        assert rejected.json()['error']['code'] == 'CSRF_INVALID'
        invalid = client.post('/admin/api/v1/templates', json={}, headers=origin | {
            'X-CSRF-Token': login.json()['data']['csrf_token']})
        assert invalid.status_code == 422
        assert invalid.json()['error']['code'] == 'INVALID_CONFIG'
        assert client.get('/api/v1/templates').status_code == 404


def test_seed_cli_replay(storage, capsys):
    from app.cli import main
    assert main(['seed-content', '--admin-username', 'owner']) == 0
    assert '新增20条' in capsys.readouterr().out
    assert main(['seed-content', '--admin-username', 'owner']) == 0
    assert '新增0条' in capsys.readouterr().out
