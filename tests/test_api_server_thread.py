"""Validate that the embedded uvicorn :class:`ApiServer` really serves HTTP."""

import time
from datetime import datetime

import pytest
import requests

from multiregistrator.common.archive import ArchiveReader, ArchiveWriter
from multiregistrator.common.models import DeviceConfig, RegisterConfig
from multiregistrator.server.api import ApiServer, create_app
from multiregistrator.server.service import ServerService

from .conftest import free_port


class FakeReader:
    def read(self, device):
        return {"analogIn": 30.0}

    def close(self, device_id=None):
        pass


def test_api_server_serves_over_http(tmp_path):
    archive_dir = tmp_path / "archive"
    device = DeviceConfig(
        id="d1", name="D", host="127.0.0.1",
        registers=[RegisterConfig(name="analogIn", address=1, data_type="float32")],
    )
    service = ServerService(FakeReader(), ArchiveWriter(archive_dir), [device])
    service.poll_once()
    app = create_app(service, ArchiveReader(archive_dir))

    port = free_port()
    server = ApiServer(app, "127.0.0.1", port)
    server.start()
    try:
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                response = requests.get(f"http://127.0.0.1:{port}/api/health", timeout=1)
                break
            except requests.RequestException:
                time.sleep(0.1)
        else:
            pytest.fail("API server did not start")
        assert response.json()["status"] == "ok"
        devices = requests.get(f"http://127.0.0.1:{port}/api/devices", timeout=2).json()
        assert devices[0]["config"]["id"] == "d1"
    finally:
        server.stop()
    assert server.is_running is False
