"""短事务基础；调用方在写事务中不得出题、渲染 PDF 或发起网络请求。"""
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import sqlite3

from sqlalchemy import Engine, Text, URL, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.types import TypeDecorator

from app.core.time import parse_stored_time, serialize_time


class BeijingTime(TypeDecorator[datetime]):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else serialize_time(value)

    def process_result_value(self, value, dialect):
        return None if value is None else parse_stored_time(value)


class Base(DeclarativeBase):
    pass


def initialize_storage(path: Path) -> None:
    """仅显式初始化/迁移命令调用；API 启动不自动建库或建表。"""
    if not path.is_absolute():
        raise ValueError("数据库路径必须为绝对路径")
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        if mode.lower() != "wal":
            raise RuntimeError("SQLite WAL 启用失败")
        if connection.execute("SELECT json_valid('{}')").fetchone()[0] != 1:
            raise RuntimeError("SQLite JSON 支持不可用")


def make_engine(path: Path) -> Engine:
    if not path.is_absolute():
        raise ValueError("数据库路径必须为绝对路径")
    # mode=rw 防止路径错误时静默创建空数据库。
    engine = create_engine(
        URL.create("sqlite+pysqlite", database=f"{path.as_uri()}", query={"mode": "rw", "uri": "true"}),
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def configure(dbapi_connection, _):
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=FULL")
        cursor.close()

    @event.listens_for(engine, "begin")
    def begin(connection):
        mode = connection.get_execution_options().get("papr_write", False)
        connection.exec_driver_sql("BEGIN IMMEDIATE" if mode else "BEGIN")

    return engine


@contextmanager
def write_transaction(engine: Engine) -> Iterator[Session]:
    # 专用新连接，避免在已有隐式事务中再次 BEGIN。
    with engine.connect().execution_options(papr_write=True) as connection:
        with connection.begin():
            with Session(bind=connection, expire_on_commit=False, join_transaction_mode="rollback_only") as session:
                yield session
                session.flush()
