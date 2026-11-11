import importlib.util
from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('config_export', ROOT/'scripts/export_config_sql.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def migrate(path, monkeypatch):
    monkeypatch.setenv('PAPR_DB_PATH', str(path))
    command.upgrade(Config(str(ROOT/'backend/alembic.ini')), 'head')


def test_shipped_config_roundtrip_and_empty_database_guard(tmp_path, monkeypatch):
    source = tmp_path/'source.sqlite3'
    migrate(source, monkeypatch)
    sql = (ROOT/'deploy/config.sql').read_text()
    with sqlite3.connect(source) as db:
        db.executescript(sql)
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        assert db.execute('SELECT count(*) FROM v2_directory').fetchone()[0] == 12
        assert db.execute('SELECT count(*) FROM v2_component_state').fetchone()[0] == 14
        assert db.execute('SELECT count(*) FROM v2_template').fetchone()[0] == 2
        assert db.execute('SELECT count(*) FROM v2_template WHERE enabled OR published_id IS NOT NULL').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM v2_version WHERE sealed=0').fetchone()[0] == 2
        assert db.execute('SELECT count(*) FROM admin_user').fetchone()[0] == 0
        before = db.execute('SELECT * FROM v2_directory ORDER BY id').fetchall()
        with pytest.raises(sqlite3.IntegrityError):
            db.executescript(sql)
        db.rollback()
        assert db.execute('SELECT * FROM v2_directory ORDER BY id').fetchall() == before
    exported = tmp_path/'export.sql'
    counts = module.export(source, exported)
    assert counts['app_setting'] == 3
    destination = tmp_path/'target.sqlite3'
    migrate(destination, monkeypatch)
    with sqlite3.connect(destination) as db:
        db.executescript(exported.read_text())
        assert db.execute('SELECT * FROM v2_directory ORDER BY id').fetchall() == before
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
