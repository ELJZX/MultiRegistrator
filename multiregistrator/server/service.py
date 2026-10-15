"""Polling scheduler.

:class:`ServerService` is a plain Python object (no Qt, no HTTP) that polls
all enabled devices on their own interval in a single background thread,
keeps the latest status of every device and delegates persistence to an
:class:`~multiregistrator.common.archive.ArchiveWriter`.

Because everything happens sequentially on one thread the network is never
flooded and the archive writer is never called concurrently.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Callable, Optional

from ..common.archive import ArchiveWriter
from ..common.models import DeviceConfig, DeviceStatus


class ServerService:
    def __init__(
        self,
        reader,
        archive_writer: ArchiveWriter,
        devices: Optional[list[DeviceConfig]] = None,
        on_status: Optional[Callable[[DeviceStatus], None]] = None,
        monotonic: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = datetime.now,
        poll_tick: float = 0.05,
    ) -> None:
        self._reader = reader
        self._archive = archive_writer
        self._on_status = on_status
        self._monotonic = monotonic
        self._now = now
        self._poll_tick = max(0.01, float(poll_tick))

        self._lock = threading.RLock()
        self._devices: dict[str, DeviceConfig] = {}
        self._status: dict[str, DeviceStatus] = {}
        self._next_poll: dict[str, float] = {}
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False

        for device in devices or []:
            self._devices[device.id] = device
            self._status[device.id] = DeviceStatus(device_id=device.id)

    # -- device management --------------------------------------------------
    def set_devices(self, devices: list[DeviceConfig]) -> None:
        with self._lock:
            new_ids = {d.id for d in devices}
            for removed in set(self._devices) - new_ids:
                self._devices.pop(removed, None)
                self._status.pop(removed, None)
                self._next_poll.pop(removed, None)
                try:
                    self._reader.close(removed)
                except Exception:  # pragma: no cover - defensive
                    pass
            for device in devices:
                self._devices[device.id] = device
                self._status.setdefault(device.id, DeviceStatus(device_id=device.id))

    def get_devices(self) -> list[DeviceConfig]:
        with self._lock:
            return list(self._devices.values())

    def get_device(self, device_id: str) -> Optional[DeviceConfig]:
        with self._lock:
            return self._devices.get(device_id)

    def get_status(self, device_id: str) -> Optional[DeviceStatus]:
        with self._lock:
            status = self._status.get(device_id)
            return status

    def snapshots(self) -> dict[str, DeviceStatus]:
        with self._lock:
            return dict(self._status)

    # -- lifecycle ----------------------------------------------------------
    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._stop_event.clear()
        with self._lock:
            now = self._monotonic()
            for device in self._devices.values():
                self._next_poll[device.id] = now
        self._thread = threading.Thread(target=self._run, name="ServerService", daemon=True)
        self._running = True
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        if not self._running:
            return
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._thread = None
        self._running = False
        try:
            self._reader.close()
        except Exception:  # pragma: no cover - defensive
            pass

    def poll_once(self) -> dict[str, DeviceStatus]:
        """Poll every device immediately (used by tests / manual refresh)."""

        results: dict[str, DeviceStatus] = {}
        for device in self.get_devices():
            if not device.enabled:
                continue
            results[device.id] = self._poll_device(device)
        return results

    # -- internals ----------------------------------------------------------
    def _run(self) -> None:
        while not self._stop_event.is_set():
            now = self._monotonic()
            due = [
                device
                for device in self.get_devices()
                if device.enabled and now >= self._next_poll.get(device.id, 0.0)
            ]
            for device in due:
                if self._stop_event.is_set():
                    break
                self._poll_device(device)
                self._next_poll[device.id] = self._monotonic() + device.poll_interval
            self._stop_event.wait(self._poll_tick)

    def _poll_device(self, device: DeviceConfig) -> DeviceStatus:
        with self._lock:
            status = self._status.setdefault(device.id, DeviceStatus(device_id=device.id))
            status.last_attempt = self._now()
        start = time.perf_counter()
        try:
            values, available = self._read_values(device)
        except Exception as exc:
            latency = (time.perf_counter() - start) * 1000.0
            with self._lock:
                status.online = False
                status.last_error = str(exc)
                status.latency_ms = latency
                # Keep the last known channel availability: a device that is
                # simply unreachable is not the same as a removed sensor.
            self._notify(status)
            return status

        latency = (time.perf_counter() - start) * 1000.0
        moment = self._now()
        with self._lock:
            status.online = True
            status.last_success = moment
            status.last_error = ""
            status.latency_ms = latency
            status.values = dict(values)
            status.channel_available = dict(available)
        try:
            self._archive.append_sample(device, moment, values)
        except Exception as exc:  # pragma: no cover - disk problems
            with self._lock:
                status.last_error = f"archive: {exc}"
        self._notify(status)
        return status

    def _read_values(self, device: DeviceConfig):
        """Return ``(values, available)`` for one device poll.

        Prefers the reader's :meth:`read_full` (which reports per-channel
        availability) but still works with a plain ``read`` (unit-test doubles).
        """

        read_full = getattr(self._reader, "read_full", None)
        if callable(read_full):
            result = read_full(device)
            return dict(result.values), dict(result.available)
        values = dict(self._reader.read(device))
        available = {name: True for name in device.channel_names}
        return values, available

    def _notify(self, status: DeviceStatus) -> None:
        if self._on_status is not None:
            try:
                self._on_status(status)
            except Exception:  # pragma: no cover - GUI callback must not crash us
                pass
