"""HTTP API exposed by the server for the clients.

The API is deliberately read-only: clients can discover devices, read the
latest live values and query the archive for a period.  It is built with
FastAPI so it can be unit tested with :class:`fastapi.testclient.TestClient`.
"""

from __future__ import annotations

import socket
import threading
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query

from .. import __version__
from ..common.archive import ArchiveReader
from ..common.models import DeviceConfig, DeviceStatus, TimeSeries
from .service import ServerService


def is_port_available(host: str, port: int) -> bool:
    """Return True if ``host:port`` can be bound for listening."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def resolve_bind_host(host: str, port: int) -> Optional[str]:
    """Pick an address the API can actually bind.

    Some Windows setups refuse to bind a specific adapter address
    (``WinError 10013``), so if the configured host cannot be bound we fall
    back to ``0.0.0.0`` which still accepts connections on every interface.
    Returns ``None`` if the port is busy everywhere.
    """

    if is_port_available(host, port):
        return host
    if host not in ("0.0.0.0", "", "::") and is_port_available("0.0.0.0", port):
        return "0.0.0.0"
    return None


def _status_dict(status: DeviceStatus) -> dict:
    return status.to_dict()


def create_app(service: ServerService, archive: ArchiveReader) -> FastAPI:
    app = FastAPI(title="MultiRegistrator Server", version=__version__)

    def _find_device(device_id: str) -> DeviceConfig:
        device = service.get_device(device_id)
        if device is None:
            for candidate in service.get_devices():
                if candidate.host == device_id:
                    return candidate
            raise HTTPException(status_code=404, detail=f"unknown device {device_id}")
        return device

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__, "running": service.is_running}

    @app.get("/api/info")
    def info() -> dict:
        return {
            "name": "MultiRegistrator Server",
            "version": __version__,
            "running": service.is_running,
            "device_count": len(service.get_devices()),
        }

    @app.get("/api/devices")
    def list_devices() -> list[dict]:
        result = []
        for device in service.get_devices():
            status = service.get_status(device.id) or DeviceStatus(device_id=device.id)
            result.append({"config": device.to_dict(), "status": _status_dict(status)})
        return result

    @app.get("/api/devices/{device_id}")
    def get_device(device_id: str) -> dict:
        device = _find_device(device_id)
        status = service.get_status(device.id) or DeviceStatus(device_id=device.id)
        return {"config": device.to_dict(), "status": _status_dict(status)}

    @app.get("/api/devices/{device_id}/latest")
    def latest(device_id: str) -> dict:
        device = _find_device(device_id)
        status = service.get_status(device.id)
        if status is None:
            raise HTTPException(status_code=404, detail="device is not polled")
        return _status_dict(status)

    @app.get("/api/devices/{device_id}/channels")
    def channels(device_id: str) -> dict:
        device = _find_device(device_id)
        names = device.channel_names or archive.list_channels(device.host)
        status = service.get_status(device.id)
        availability = status.channel_available if status else {}
        available = [name for name in names if availability.get(name, True)]
        unavailable = [name for name in names if name not in available]
        return {
            "device_id": device.id,
            "host": device.host,
            "channels": available,
            "unavailable": unavailable,
        }

    @app.get("/api/devices/{device_id}/dates")
    def dates(device_id: str) -> dict:
        device = _find_device(device_id)
        return {
            "device_id": device.id,
            "dates": [d.isoformat() for d in archive.list_dates(device.host)],
        }

    @app.get("/api/devices/{device_id}/data")
    def data(
        device_id: str,
        start: str = Query(..., description="ISO datetime, inclusive"),
        end: str = Query(..., description="ISO datetime, inclusive"),
        channels: Optional[str] = Query(None, description="comma separated channel names"),
    ) -> dict:
        device = _find_device(device_id)
        try:
            start_dt = datetime.fromisoformat(start)
            end_dt = datetime.fromisoformat(end)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"bad datetime: {exc}") from exc
        if start_dt > end_dt:
            start_dt, end_dt = end_dt, start_dt
        wanted = [c for c in channels.split(",") if c] if channels else None
        series = archive.read_range(device.host, start_dt, end_dt, wanted)
        return _serialize_series(device, series, start_dt, end_dt)

    return app


def _serialize_series(
    device: DeviceConfig,
    series: dict[str, TimeSeries],
    start: datetime,
    end: datetime,
) -> dict:
    payload: dict = {
        "device_id": device.id,
        "host": device.host,
        "start": start,
        "end": end,
        "channels": {},
    }
    for name, ts in series.items():
        times, values = ts.numeric()
        payload["channels"][name] = {
            "times": times,
            "values": values,
        }
    return payload


class ApiServer:
    """Runs a uvicorn server for a FastAPI app inside a background thread."""

    def __init__(self, app: FastAPI, host: str, port: int) -> None:
        import uvicorn

        self.host = host
        self.port = port
        self._config = uvicorn.Config(
            app, host=host, port=port, log_level="warning", use_colors=False
        )
        self._server = uvicorn.Server(self._config)
        self._thread: Optional[threading.Thread] = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._server.should_exit = False
        self._thread = threading.Thread(target=self._server.run, name="ApiServer", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._thread = None
