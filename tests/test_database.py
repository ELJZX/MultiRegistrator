import logging
from datetime import datetime

import pytest

from multiregistrator.common import database as db_module
from multiregistrator.common.config import DatabaseSettings, ServerSettings
from multiregistrator.common.database import (
    Database,
    DatabaseArchiveWriter,
    DatabaseLogHandler,
    attach_database_logging,
    create_database,
    dsn,
)
from multiregistrator.common.models import DeviceConfig


def make_settings(**kwargs):
    return DatabaseSettings(enabled=True, host="db", port=5433, name="mrdb",
                            user="usr", password="pwd", connect_timeout=7, **kwargs)


def test_dsn_contains_all_parts():
    text = dsn(make_settings())
    assert "host=db" in text
    assert "port=5433" in text
    assert "dbname=mrdb" in text
    assert "user=usr" in text
    assert "password=pwd" in text
    assert "connect_timeout=7" in text


def test_database_disabled_when_psycopg_missing(monkeypatch):
    monkeypatch.setattr(db_module, "psycopg", None)
    database = Database(make_settings())
    assert database.available is False


def test_create_database_returns_none_when_disabled():
    assert create_database(DatabaseSettings(enabled=False)) is None


def test_create_database_returns_instance_when_enabled():
    assert isinstance(create_database(make_settings()), Database)


def test_env_overrides_database_settings(monkeypatch):
    monkeypatch.setenv("MULTIREGISTRATOR_DB_ENABLED", "1")
    monkeypatch.setenv("MULTIREGISTRATOR_DB_HOST", "pg-host")
    monkeypatch.setenv("MULTIREGISTRATOR_DB_PORT", "6000")
    monkeypatch.setenv("MULTIREGISTRATOR_DB_NAME", "envdb")
    monkeypatch.setenv("MULTIREGISTRATOR_DB_USER", "envuser")
    monkeypatch.setenv("MULTIREGISTRATOR_DB_PASSWORD", "envpwd")
    monkeypatch.setenv("MULTIREGISTRATOR_DB_TIMEOUT", "9")

    settings = ServerSettings.from_dict({"database": {"enabled": False}})
    assert settings.database.enabled is True
    assert settings.database.host == "pg-host"
    assert settings.database.port == 6000
    assert settings.database.name == "envdb"
    assert settings.database.user == "envuser"
    assert settings.database.password == "envpwd"
    assert settings.database.connect_timeout == 9


def test_database_settings_roundtrip():
    settings = ServerSettings(database=make_settings())
    restored = ServerSettings.from_dict(settings.to_dict())
    assert restored.database == settings.database


class FakeCursor:
    def __init__(self, sink):
        self.sink = sink

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.sink.append((sql, params))

    def executemany(self, sql, rows):
        self.sink.append((sql, list(rows)))


class FakeConnection:
    closed = False

    def __init__(self):
        self.calls = []

    def cursor(self):
        return FakeCursor(self.calls)


def make_fake_database(monkeypatch):
    database = Database(make_settings())
    conn = FakeConnection()
    monkeypatch.setattr(db_module, "psycopg", object())
    monkeypatch.setattr(database, "_connection", lambda: conn)
    monkeypatch.setattr(database, "_ensure_schema", lambda _conn: None)
    return database, conn


def test_write_sample_inserts_device_and_measurements(monkeypatch):
    database, conn = make_fake_database(monkeypatch)
    device = DeviceConfig(id="d1", name="Dev", host="10.0.0.1",
                          registers=[])
    moment = datetime(2026, 10, 19, 12, 0, 0)
    database.write_sample(device, moment, {"temperature": 25.5, "humidity": None})

    sql_text = " ".join(sql for sql, _ in conn.calls)
    assert "INSERT INTO devices" in sql_text
    assert "INSERT INTO measurements" in sql_text
    rows = conn.calls[-1][1]
    assert rows == [
        ("d1", "10.0.0.1", "temperature", 25.5, moment),
        ("d1", "10.0.0.1", "humidity", None, moment),
    ]


def test_write_log_inserts_row(monkeypatch):
    database, conn = make_fake_database(monkeypatch)
    moment = datetime(2026, 10, 19, 12, 0, 0)
    database.write_log(moment, "INFO", "multiregistrator.test", "hello")
    sql, params = conn.calls[-1]
    assert "INSERT INTO app_logs" in sql
    assert params == (moment, "INFO", "multiregistrator.test", "hello")


def test_archive_writer_mirrors_to_database(monkeypatch):
    database, conn = make_fake_database(monkeypatch)

    class Csv:
        def __init__(self):
            self.samples = []

        def append_sample(self, device, timestamp, values, channels=None):
            self.samples.append((device.id, timestamp, dict(values)))
            return "archive/file.txt"

    csv = Csv()
    writer = DatabaseArchiveWriter(csv, database)
    device = DeviceConfig(id="d1", name="Dev", host="10.0.0.1")
    moment = datetime(2026, 10, 19, 12, 0, 0)
    path = writer.append_sample(device, moment, {"temperature": 1.0})

    assert path == "archive/file.txt"
    assert csv.samples == [("d1", moment, {"temperature": 1.0})]
    assert any("INSERT INTO measurements" in sql for sql, _ in conn.calls)


def test_archive_writer_survives_database_failure(monkeypatch):
    class Csv:
        def append_sample(self, *args, **kwargs):
            return "archive/file.txt"

    class BrokenDb:
        available = True

        def write_sample(self, *args, **kwargs):
            raise RuntimeError("db down")

    writer = DatabaseArchiveWriter(Csv(), BrokenDb())
    device = DeviceConfig(id="d1", name="Dev", host="10.0.0.1")
    assert writer.append_sample(device, datetime.now(), {"a": 1.0}) == "archive/file.txt"


def test_log_handler_skips_when_database_unavailable():
    class Unavailable:
        available = False

    handler = DatabaseLogHandler(Unavailable())
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", None, None)
    handler.emit(record)  # must not raise


def test_attach_database_logging_is_idempotent(monkeypatch):
    database, _conn = make_fake_database(monkeypatch)
    logger = logging.getLogger("multiregistrator")
    original = list(logger.handlers)
    try:
        first = attach_database_logging(database, "multiregistrator")
        second = attach_database_logging(database, "multiregistrator")
        assert first is second
        count = sum(isinstance(h, DatabaseLogHandler) for h in logger.handlers)
        assert count == 1
    finally:
        logger.handlers = original


def test_schema_defines_expected_tables():
    assert "CREATE TABLE IF NOT EXISTS devices" in db_module.SCHEMA_SQL
    assert "CREATE TABLE IF NOT EXISTS measurements" in db_module.SCHEMA_SQL
    assert "CREATE TABLE IF NOT EXISTS app_logs" in db_module.SCHEMA_SQL
