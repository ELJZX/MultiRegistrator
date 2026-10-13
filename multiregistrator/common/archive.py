"""Reading and writing the on-disk archive.

Layout::

    archive/
        192.168.1.10/
            192.168.1.10_2026-10-13.txt
            192.168.1.10_2026-10-14.txt
        ...

Each text file is CSV with a header row::

    timestamp,channel1,channel2,...

A new file is started for every calendar day.  Writing is protected by a
per-file lock so the poller thread and any external reader never observe a
half written line.
"""

from __future__ import annotations

import csv
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Mapping, Optional

from .models import DeviceConfig, TimeSeries, format_timestamp, parse_timestamp

_ALLOWED = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


def sanitize_name(value: str) -> str:
    """Make a string safe to use as a file or folder name."""

    return "".join(char if char in _ALLOWED else "_" for char in str(value))


def device_folder(archive_dir: str | Path, host: str) -> Path:
    return Path(archive_dir) / sanitize_name(host)


def archive_file_path(
    archive_dir: str | Path,
    host: str,
    day: date | datetime | str,
) -> Path:
    if isinstance(day, datetime):
        day = day.date()
    elif isinstance(day, str):
        day = date.fromisoformat(day)
    name = f"{sanitize_name(host)}_{day.isoformat()}.txt"
    return device_folder(archive_dir, host) / name


class ArchiveWriter:
    """Append-only writer that produces one CSV file per device and day."""

    def __init__(self, archive_dir: str | Path) -> None:
        self.archive_dir = Path(archive_dir)
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _lock_for(self, key: str) -> threading.Lock:
        with self._locks_guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._locks[key] = lock
            return lock

    @staticmethod
    def channel_names(device: DeviceConfig, values: Mapping[str, object]) -> list[str]:
        names = device.channel_names
        if names:
            return names
        return sorted(values.keys())

    def append_sample(
        self,
        device: DeviceConfig,
        timestamp: datetime,
        values: Mapping[str, Optional[float]],
        channels: Optional[Iterable[str]] = None,
    ) -> Path:
        channel_list = list(channels) if channels is not None else self.channel_names(device, values)
        path = archive_file_path(self.archive_dir, device.host, timestamp)
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = self._lock_for(str(path))
        with lock:
            is_new = not path.exists() or path.stat().st_size == 0
            with path.open("a", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                if is_new:
                    writer.writerow(["timestamp", *channel_list])
                row: list[str] = [format_timestamp(timestamp)]
                for channel in channel_list:
                    value = values.get(channel)
                    row.append("" if value is None else repr(float(value)))
                writer.writerow(row)
        return path


class ArchiveReader:
    """Reads back archived samples for plotting / exporting."""

    def __init__(self, archive_dir: str | Path) -> None:
        self.archive_dir = Path(archive_dir)

    def list_devices(self) -> list[str]:
        if not self.archive_dir.exists():
            return []
        return sorted(p.name for p in self.archive_dir.iterdir() if p.is_dir())

    def list_dates(self, host: str) -> list[date]:
        folder = device_folder(self.archive_dir, host)
        if not folder.exists():
            return []
        prefix = f"{sanitize_name(host)}_"
        dates: list[date] = []
        for path in folder.glob(f"{prefix}*.txt"):
            stem = path.stem[len(prefix) :]
            try:
                dates.append(date.fromisoformat(stem))
            except ValueError:
                continue
        return sorted(set(dates))

    def list_channels(self, host: str) -> list[str]:
        folder = device_folder(self.archive_dir, host)
        if not folder.exists():
            return []
        files = sorted(folder.glob("*.txt"))
        if not files:
            return []
        with files[-1].open("r", encoding="utf-8", newline="") as handle:
            header = next(csv.reader(handle), None)
        if not header or len(header) < 2:
            return []
        return header[1:]

    def _files_in_range(self, host: str, start: datetime, end: datetime) -> list[Path]:
        folder = device_folder(self.archive_dir, host)
        if not folder.exists():
            return []
        prefix = f"{sanitize_name(host)}_"
        selected: list[Path] = []
        for path in folder.glob(f"{prefix}*.txt"):
            stem = path.stem[len(prefix) :]
            try:
                day = date.fromisoformat(stem)
            except ValueError:
                continue
            if start.date() <= day <= end.date():
                selected.append(path)
        return sorted(selected)

    def read_range(
        self,
        host: str,
        start: datetime,
        end: datetime,
        channels: Optional[Iterable[str]] = None,
    ) -> dict[str, TimeSeries]:
        """Return ``channel -> TimeSeries`` for ``[start, end]`` (inclusive)."""

        files = self._files_in_range(host, start, end)
        result: dict[str, TimeSeries] = {}
        available: list[str] = []

        for path in files:
            with path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.reader(handle)
                header = next(reader, None)
                if not header or len(header) < 2:
                    continue
                names = header[1:]
                if not available:
                    available = names
                    wanted = names if channels is None else [c for c in channels if c in names]
                    for channel in (channels if channels is not None else names):
                        result.setdefault(channel, TimeSeries(channel=channel))
                wanted = available if channels is None else [c for c in channels if c in available]
                index = {name: i + 1 for i, name in enumerate(names)}
                for row in reader:
                    if not row:
                        continue
                    try:
                        timestamp = parse_timestamp(row[0])
                    except (ValueError, IndexError):
                        continue
                    if timestamp < start or timestamp > end:
                        continue
                    for channel in wanted:
                        pos = index[channel]
                        raw = row[pos] if pos < len(row) else ""
                        try:
                            value = float(raw) if raw != "" else None
                        except ValueError:
                            value = None
                        result[channel].add(timestamp, value)

        if channels is not None:
            for channel in channels:
                result.setdefault(channel, TimeSeries(channel=channel))
        return result

    def read_day(
        self,
        host: str,
        day: date | str,
        channels: Optional[Iterable[str]] = None,
    ) -> dict[str, TimeSeries]:
        start = datetime.combine(parse_day(day), datetime.min.time())
        end = datetime.combine(parse_day(day), datetime.max.time())
        return self.read_range(host, start, end, channels)


def parse_day(day: date | str) -> date:
    if isinstance(day, date):
        return day
    return date.fromisoformat(day)
