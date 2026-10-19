"""PostgreSQL mirror for the archive and the application logs.

The application keeps writing the human-readable CSV files under ``archive/``
and the rotating ``logs/*.log`` files; this module *additionally* stores the
same data in PostgreSQL so it can be inspected with pgAdmin.

Schema
------
``devices``          one row per configured device (updated on every sample)
``measurements``     one row per device sample and channel
``measurements_wide`` optional convenience view is not created; the long table
                     is used because channel sets change over time
``app_logs``         every log record written by the application

Everything is best-effort: a database outage must never stop the poller, so all
errors are logged and swallowed.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Mapping, Optional

try:  # pragma: no cover - exercised only when psycopg is installed
    import psycopg
except Exception:  # pragma: no cover
    psycopg = None  # type: ignore[assignment]

from .config import DatabaseSettings
from .models import DeviceConfig

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS devices (
    device_id     TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    host          TEXT NOT NULL,
    port          INTEGER NOT NULL,
    modbus_id     INTEGER NOT NULL,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS measurements (
    id            BIGSERIAL PRIMARY KEY,
    device_id     TEXT NOT NULL,
    device_host   TEXT NOT NULL,
    channel       TEXT NOT NULL,
    value         DOUBLE PRECISION,
    measured_at   TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS measurements_device_time_idx
    ON measurements (device_id, measured_at);
CREATE INDEX IF NOT EXISTS measurements_channel_time_idx
    ON measurements (device_id, channel, measured_at);

CREATE TABLE IF NOT EXISTS app_logs (
    id            BIGSERIAL PRIMARY KEY,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    level         TEXT NOT NULL,
    logger        TEXT NOT NULL,
    message       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS app_logs_time_idx ON app_logs (created_at);
"""


def dsn(settings: DatabaseSettings) -> str:
    """Build a libpq connection string for ``settings``."""

    return (
        f"host={settings.host} port={settings.port} dbname={settings.name} "
        f"user={settings.user} password={settings.password} "
        f"connect_timeout={settings.connect_timeout}"
    )


class Database:
    """Thin wrapper around a PostgreSQL connection (reconnects on demand)."""

    def __init__(self, settings: DatabaseSettings) -> None:
        self.settings = settings
        self._lock = threading.RLock()
        self._conn = None

    # -- connection ---------------------------------------------------------
    @property
    def available(self) -> bool:
        return psycopg is not None and self.settings.enabled

    def _connection(self):
        if psycopg is None:
            raise RuntimeError("psycopg is not installed")
        if self._conn is None or self._conn.closed:
            self._conn = psycopg.connect(dsn(self.settings), autocommit=True)
            self._ensure_schema(self._conn)
        return self._conn

    @staticmethod
    def _ensure_schema(conn) -> None:
        with conn.cursor() as cursor:
            cursor.execute(SCHEMA_SQL)

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                finally:
                    self._conn = None

    # -- writes -------------------------------------------------------------
    def upsert_device(self, device: DeviceConfig, moment: datetime) -> None:
        with self._lock:
            conn = self._connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO devices (device_id, name, host, port, modbus_id, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (device_id) DO UPDATE
                    SET name = EXCLUDED.name,
                        host = EXCLUDED.host,
                        port = EXCLUDED.port,
                        modbus_id = EXCLUDED.modbus_id,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        device.id,
                        device.name,
                        device.host,
                        device.port,
                        device.device_id,
                        moment,
                    ),
                )

    def write_sample(
        self,
        device: DeviceConfig,
        moment: datetime,
        values: Mapping[str, Optional[float]],
    ) -> None:
        rows = [
            (device.id, device.host, channel, value, moment)
            for channel, value in values.items()
        ]
        with self._lock:
            conn = self._connection()
            self.upsert_device(device, moment)
            if not rows:
                return
            with conn.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO measurements
                        (device_id, device_host, channel, value, measured_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    rows,
                )

    def write_log(self, created_at: datetime, level: str, logger: str, message: str) -> None:
        with self._lock:
            conn = self._connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO app_logs (created_at, level, logger, message) "
                    "VALUES (%s, %s, %s, %s)",
                    (created_at, level, logger, message),
                )


class DatabaseArchiveWriter:
    """``ArchiveWriter``-compatible writer backed by PostgreSQL.

    ``csv_writer`` may be ``None`` (database-only mode).  When given, the CSV is
    written first and the database copy afterwards; a database failure never
    stops polling.
    """

    def __init__(self, csv_writer, database: Database, logger: Optional[logging.Logger] = None) -> None:
        self._csv = csv_writer
        self._db = database
        self._logger = logger or logging.getLogger("multiregistrator.database")

    @property
    def archive_dir(self):
        return getattr(self._csv, "archive_dir", None)

    def append_sample(self, device, timestamp, values, channels=None):
        path = None
        if self._csv is not None:
            path = self._csv.append_sample(device, timestamp, values, channels)
        if not self._db.available:
            return path
        try:
            self._db.write_sample(device, timestamp, values)
        except Exception:  # pragma: no cover - DB outage must not stop polling
            self._logger.exception("не удалось записать измерения в PostgreSQL")
        return path


class DatabaseArchiveReader:
    """``ArchiveReader``-compatible reader that queries PostgreSQL.

    Implements the subset used by the HTTP API and the clients: channel list,
    available dates and a time range.  Keeps the same ``channel -> TimeSeries``
    contract as the file based reader.
    """

    def __init__(self, database: Database) -> None:
        self._db = database

    # -- queries ------------------------------------------------------------
    def _query(self, sql: str, params: tuple):
        with self._db._lock:
            conn = self._db._connection()
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchall()

    def list_devices(self) -> list[str]:
        rows = self._query("SELECT DISTINCT device_id FROM measurements", ())
        return sorted(row[0] for row in rows)

    def list_dates(self, host: str) -> list:
        from datetime import date as _date

        rows = self._query(
            "SELECT DISTINCT measured_at::date FROM measurements "
            "WHERE device_id = %s OR device_host = %s",
            (host, host),
        )
        return sorted({row[0] for row in rows})

    def list_channels(self, host: str) -> list[str]:
        rows = self._query(
            "SELECT DISTINCT channel FROM measurements "
            "WHERE device_id = %s OR device_host = %s ORDER BY channel",
            (host, host),
        )
        return [row[0] for row in rows]

    def read_range(self, host: str, start, end, channels=None):
        from .models import TimeSeries

        result: dict[str, TimeSeries] = {}
        for channel in channels or ():
            result.setdefault(channel, TimeSeries(channel=channel))

        sql = (
            "SELECT channel, measured_at, value FROM measurements "
            "WHERE (device_id = %s OR device_host = %s) "
            "AND measured_at >= %s AND measured_at <= %s"
        )
        params: list = [host, host, start, end]
        if channels:
            sql += " AND channel = ANY(%s)"
            params.append(list(channels))
        sql += " ORDER BY measured_at"

        for channel, moment, value in self._query(sql, tuple(params)):
            series = result.setdefault(channel, TimeSeries(channel=channel))
            series.add(moment.replace(tzinfo=None), None if value is None else float(value))
        return result

    def read_day(self, host: str, day, channels=None):
        from datetime import datetime as _datetime

        from .archive import parse_day

        day = parse_day(day)
        return self.read_range(
            host,
            _datetime.combine(day, _datetime.min.time()),
            _datetime.combine(day, _datetime.max.time()),
            channels,
        )


class DatabaseLogHandler(logging.Handler):
    """Copy every log record into the ``app_logs`` table."""

    def __init__(self, database: Database, level: int = logging.INFO) -> None:
        super().__init__(level=level)
        self._db = database

    def emit(self, record: logging.LogRecord) -> None:
        if not self._db.available:
            return
        try:
            self._db.write_log(
                datetime.fromtimestamp(record.created),
                record.levelname,
                record.name,
                self.format(record),
            )
        except Exception:  # pragma: no cover - DB outage must not break logging
            # Never log through the same logger here: that would re-enter this
            # handler and recurse.  Write the diagnostic straight to stderr.
            try:
                import sys

                if sys.stderr is not None:
                    sys.stderr.write(
                        "multiregistrator: не удалось записать лог в PostgreSQL\n"
                    )
            except Exception:
                pass


def attach_database_logging(
    database: Database,
    logger_name: str = "multiregistrator",
    level: int = logging.INFO,
) -> Optional[DatabaseLogHandler]:
    """Attach a :class:`DatabaseLogHandler` to ``logger_name`` (idempotent)."""

    if not database.available:
        return None
    logger = logging.getLogger(logger_name)
    for handler in logger.handlers:
        if isinstance(handler, DatabaseLogHandler):
            return handler
    handler = DatabaseLogHandler(database, level=level)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    return handler


def create_database(settings: DatabaseSettings) -> Optional[Database]:
    """Return a :class:`Database` when enabled, otherwise ``None``."""

    if not settings.enabled:
        return None
    return Database(settings)


def build_storage(settings, archive_dir, csv_writer_factory=None):
    """Create ``(writer, reader, database)`` for the configured storage mode.

    ``settings`` is a :class:`~multiregistrator.common.config.ServerSettings`.
    In ``database`` mode nothing is written to ``archive_dir`` at all; in
    ``both`` mode the CSV file is written first and mirrored into PostgreSQL.
    """

    from .archive import ArchiveReader, ArchiveWriter

    mode = getattr(settings, "archive_storage", "files")
    database = create_database(settings.database) if getattr(settings, "uses_database", False) else None

    if mode == "files" or database is None:
        writer = (csv_writer_factory or ArchiveWriter)(archive_dir)
        return writer, ArchiveReader(archive_dir), None

    if getattr(settings, "uses_files", False):
        csv_writer = (csv_writer_factory or ArchiveWriter)(archive_dir)
        writer = DatabaseArchiveWriter(csv_writer, database)
    else:
        writer = DatabaseArchiveWriter(None, database)
    return writer, DatabaseArchiveReader(database), database
