"""HTTP API exposed by the server for the clients.

The API is deliberately read-only: clients can discover devices, read the
latest live values and query the archive for a period.  It is built with
FastAPI so it can be unit tested with :class:`fastapi.testclient.TestClient`.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query

from .. import __version__
from ..common.archive import ArchiveReader
from ..common.models import DeviceConfig, DeviceStatus, TimeSeries
from .service import ServerService


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
        return {"device_id": device.id, "host": device.host, "channels": names}

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
        self._config = uvicorn.Config(app, host=host, port=port, log_level="warning")
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
