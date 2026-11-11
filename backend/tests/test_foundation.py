from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import sqlite3

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest
from sqlalchemy.exc import IntegrityError, OperationalError, StatementError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import make_engine, write_transaction
from app.core.time import BEIJING, parse_stored_time, serialize_time
from app.main import create_app
from app.models.system import ContentEpoch
from app.schemas.generation import CreatePaperJob, QuestionCounts


@pytest.fixture
def database(tmp_path, monkeypatch):
    path = tmp_path / 'papr.sqlite3'
    monkeypatch.setenv('PAPR_DB_PATH', str(path))
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    command.upgrade(config, 'head')
    engine = make_engine(path)
    yield path, engine, config
    engine.dispose()


def test_beijing_midnight_and_precision():
    value = datetime(2026, 10, 27, 16, 0, 0, 123456, tzinfo=timezone.utc)
    stored = serialize_time(value)
    assert stored == '2026-10-28T00:00:00.123456+08:00'
    assert parse_stored_time(stored) == value
    with pytest.raises(ValueError):
        serialize_time(datetime(2026, 10, 27))
    with pytest.raises(ValueError):
        parse_stored_time('2026-10-27T16:00:00.123456Z')


def test_sqlite_migration_and_real_storage(database):
    path, engine, config = database
    now = datetime(2026, 10, 27, 16, tzinfo=timezone.utc)
    with write_transaction(engine) as session:
        row = session.get(ContentEpoch, 1)
        row.updated_at = now
        row.value += 1
    with sqlite3.connect(path) as raw:
        assert raw.execute('select updated_at from content_epoch').fetchone()[0] == '2026-10-28T00:00:00.000000+08:00'
        assert raw.execute('pragma journal_mode').fetchone()[0] == 'wal'
        assert raw.execute('pragma integrity_check').fetchone()[0] == 'ok'
    with engine.connect() as conn:
        assert conn.exec_driver_sql('pragma foreign_keys').scalar() == 1
        assert conn.exec_driver_sql('pragma busy_timeout').scalar() == 5000
        assert conn.exec_driver_sql('pragma synchronous').scalar() == 2
    with Session(engine) as session:
        row = session.get(ContentEpoch, 1)
        assert row.value == 1
        assert row.updated_at.tzinfo == BEIJING
    command.check(config)
    command.downgrade(config, 'base')
    command.upgrade(config, 'head')


def test_write_rollback_and_reject_naive_time(database):
    _, engine, _ = database
    with pytest.raises(RuntimeError):
        with write_transaction(engine) as session:
            session.get(ContentEpoch, 1).value = 12
            session.flush()
            raise RuntimeError('模拟提交前失败')
    with Session(engine) as session:
        assert session.get(ContentEpoch, 1).value == 0
    with pytest.raises(StatementError):
        with write_transaction(engine) as session:
            session.get(ContentEpoch, 1).updated_at = datetime(2026, 10, 27)
    with engine.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.exec_driver_sql("update content_epoch set updated_at='2026-10-27T00:00:00.000000Z'")


def test_write_lock_and_foreign_keys(database):
    _, engine, _ = database
    with engine.begin() as connection:
        connection.exec_driver_sql('create table parent (id integer primary key)')
        connection.exec_driver_sql('create table child (parent_id integer references parent(id))')
    with engine.begin() as connection:
        with pytest.raises(IntegrityError):
            connection.exec_driver_sql('insert into child values (999)')
    with write_transaction(engine):
        with engine.connect() as competitor:
            competitor.exec_driver_sql('pragma busy_timeout=1')
            competitor.rollback()
            with pytest.raises(OperationalError, match='locked'):
                competitor.execution_options(papr_write=True).begin()


def test_ddl_and_savepoint_rollback(database):
    _, engine, _ = database
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.exec_driver_sql('create table transient_table (id integer)')
        transaction.rollback()
        assert connection.exec_driver_sql("select count(*) from sqlite_master where name='transient_table'").scalar() == 0
        connection.rollback()
        with connection.begin():
            with connection.begin_nested() as nested:
                connection.exec_driver_sql('update content_epoch set value=7')
                nested.rollback()
            assert connection.exec_driver_sql('select value from content_epoch').scalar() == 0


def test_missing_database_not_created(tmp_path):
    path = tmp_path / 'missing.sqlite3'
    engine = make_engine(path)
    try:
        with pytest.raises(OperationalError):
            engine.connect()
        assert not path.exists()
    finally:
        engine.dispose()
    with pytest.raises(ValueError):
        Settings(Path('relative.sqlite3'), tmp_path)


def test_health_envelope_and_errors(tmp_path, monkeypatch):
    path = tmp_path / 'never-created.sqlite3'
    monkeypatch.setenv('PAPR_DB_PATH', str(path))
    with TestClient(create_app()) as client:
        response = client.get('/api/v1/health')
        assert response.status_code == 200
        body = response.json()
        assert body['request_id'] == response.headers['X-Request-ID']
        parse_stored_time(body['data']['server_now'])
        assert body['data']['status'] == 'ok'
        missing = client.get('/api/v1/absent')
        assert missing.status_code == 404
        assert missing.json()['error']['code'] == 'NOT_FOUND'
    assert not path.exists()


def test_question_counts_are_whole_paper():
    counts = QuestionCounts(choice=3, fill=6, answer=8)
    assert counts.total == 17
    request = dict(theme_id=uuid4(), knowledge_point_ids=[uuid4(), uuid4()], difficulty='basic', question_type_counts=counts, content_epoch=0)
    assert CreatePaperJob(**request).question_type_counts.total == 17
    for invalid in ['3', 3.0, True, -1, 13]:
        with pytest.raises(ValidationError):
            QuestionCounts(choice=invalid, fill=0, answer=0)
    with pytest.raises(ValidationError):
        CreatePaperJob(**{**request, 'question_type_counts': {'choice': 0, 'fill': 0, 'answer': 0}})
