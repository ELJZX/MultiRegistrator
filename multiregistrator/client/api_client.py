"""Thin REST client for the MultiRegistrator server API.

Uses a single :class:`requests.Session` so TCP connections are reused and the
network is kept as quiet as possible.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import requests

from .. import __version__
from ..common.models import TimeSeries


class ServerApiError(RuntimeError):
    """Any problem talking to the server (network or protocol)."""


class ServerApiClient:
    def __init__(
        self,
        host: str,
        port: int,
        timeout: float = 5.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.timeout = float(timeout)
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": f"MultiRegistrator/{__version__}"})

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    # -- low level ----------------------------------------------------------
    def _get(self, path: str, params: Optional[dict] = None) -> dict | list:
        try:
            response = self._session.get(
                f"{self.base_url}{path}", params=params, timeout=self.timeout
            )
        except requests.RequestException as exc:
            raise ServerApiError(f"cannot reach server {self.base_url}: {exc}") from exc
        if response.status_code != 200:
            raise ServerApiError(f"server returned {response.status_code}: {response.text}")
        try:
            return response.json()
        except ValueError as exc:
            raise ServerApiError(f"invalid response: {exc}") from exc

    def close(self) -> None:
        self._session.close()

    # -- endpoints ----------------------------------------------------------
    def health(self) -> dict:
        return self._get("/api/health")

    def info(self) -> dict:
        return self._get("/api/info")

    def list_devices(self) -> list[dict]:
        return self._get("/api/devices")

    def get_device(self, device_id: str) -> dict:
        return self._get(f"/api/devices/{device_id}")

    def latest(self, device_id: str) -> dict:
        return self._get(f"/api/devices/{device_id}/latest")

    def channels(self, device_id: str) -> list[str]:
        payload = self._get(f"/api/devices/{device_id}/channels")
        return list(payload.get("channels", []))

    def dates(self, device_id: str) -> list[str]:
        payload = self._get(f"/api/devices/{device_id}/dates")
        return list(payload.get("dates", []))

    def data(
        self,
        device_id: str,
        start: datetime,
        end: datetime,
        channels: Optional[list[str]] = None,
    ) -> dict[str, TimeSeries]:
        params = {"start": start.isoformat(), "end": end.isoformat()}
        if channels:
            params["channels"] = ",".join(channels)
        payload = self._get(f"/api/devices/{device_id}/data", params=params)
        return parse_series(payload)


def parse_series(payload: dict) -> dict[str, TimeSeries]:
    """Convert a ``/data`` payload into :class:`TimeSeries` objects."""

    result: dict[str, TimeSeries] = {}
    for name, body in payload.get("channels", {}).items():
        series = TimeSeries(channel=name)
        raw_times = body.get("times", [])
        raw_values = body.get("values", [])
        for timestamp, value in zip(raw_times, raw_values):
            try:
                moment = datetime.fromisoformat(str(timestamp))
            except ValueError:
                continue
            series.add(moment, None if value is None else float(value))
        result[name] = series
    return result
