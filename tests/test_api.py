from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from multiregistrator.common.archive import ArchiveReader, ArchiveWriter
from multiregistrator.common.models import DeviceConfig, RegisterConfig
from multiregistrator.server.api import create_app, is_port_available, resolve_bind_host
from multiregistrator.server.service import ServerService

from .conftest import free_port


class FakeReader:
    def __init__(self, values):
        self.values = values

    def read(self, device):
        return dict(self.values)

    def close(self, device_id=None):
        pass


@pytest.fixture
def client(tmp_path):
    archive_dir = tmp_path / "archive"
    device = DeviceConfig(
        id="d1",
        name="Tewes-Bis",
        host="127.0.0.1",
        registers=[
            RegisterConfig(name="analogIn", address=1, data_type="float32"),
            RegisterConfig(name="freqIn", address=3),
        ],
    )
    service = ServerService(
        FakeReader({"analogIn": 30.0, "freqIn": 50.0}),
        ArchiveWriter(archive_dir),
        [device],
        now=lambda: datetime(2026, 10, 13, 12, 0, 0),
    )
    service.poll_once()
    app = create_app(service, ArchiveReader(archive_dir))
    return TestClient(app)


def test_health(client):
    payload = client.get("/api/health").json()
    assert payload["status"] == "ok"
    assert payload["version"]


def test_info(client):
    payload = client.get("/api/info").json()
    assert payload["device_count"] == 1


def test_list_devices(client):
    payload = client.get("/api/devices").json()
    assert len(payload) == 1
    assert payload[0]["config"]["id"] == "d1"
    assert payload[0]["status"]["online"] is True
    assert payload[0]["status"]["values"]["analogIn"] == 30.0


def test_get_device(client):
    payload = client.get("/api/devices/d1").json()
    assert payload["config"]["host"] == "127.0.0.1"


def test_get_unknown_device(client):
    assert client.get("/api/devices/nope").status_code == 404


def test_find_device_by_host(client):
    assert client.get("/api/devices/127.0.0.1").status_code == 200


def test_latest(client):
    payload = client.get("/api/devices/d1/latest").json()
    assert payload["online"] is True
    assert payload["values"]["freqIn"] == 50.0


def test_channels(client):
    payload = client.get("/api/devices/d1/channels").json()
    assert payload["channels"] == ["analogIn", "freqIn"]
    assert payload["unavailable"] == []


def test_channels_hide_unavailable(tmp_path):
    class Result:
        values = {"analogIn": 30.0, "freqIn": None}
        available = {"analogIn": True, "freqIn": False}

    class FullReader:
        def read_full(self, device):
            return Result()

        def close(self, device_id=None):
            pass

    device = DeviceConfig(
        id="d1",
        name="Tewes-Bis",
        host="127.0.0.1",
        registers=[
            RegisterConfig(name="analogIn", address=1, data_type="float32"),
            RegisterConfig(name="freqIn", address=3),
        ],
    )
    service = ServerService(FullReader(), ArchiveWriter(tmp_path / "archive"), [device])
    service.poll_once()
    app = create_app(service, ArchiveReader(tmp_path / "archive"))
    payload = TestClient(app).get("/api/devices/d1/channels").json()
    assert payload["channels"] == ["analogIn"]
    assert payload["unavailable"] == ["freqIn"]


def test_dates(client):
    payload = client.get("/api/devices/d1/dates").json()
    assert payload["dates"] == ["2026-10-13"]


def test_data_endpoint(client):
    response = client.get(
        "/api/devices/d1/data",
        params={"start": "2026-10-13T00:00:00", "end": "2026-10-13T23:59:59"},
    )
    payload = response.json()
    assert payload["channels"]["analogIn"]["values"] == [30.0]
    assert payload["channels"]["freqIn"]["values"] == [50.0]


def test_data_endpoint_channel_filter(client):
    response = client.get(
        "/api/devices/d1/data",
        params={
            "start": "2026-10-13T00:00:00",
            "end": "2026-10-13T23:59:59",
            "channels": "freqIn",
        },
    )
    payload = response.json()
    assert list(payload["channels"]) == ["freqIn"]


def test_data_endpoint_bad_datetime(client):
    response = client.get(
        "/api/devices/d1/data",
        params={"start": "not-a-date", "end": "2026-10-13T23:59:59"},
    )
    assert response.status_code == 400


def test_data_endpoint_missing_params(client):
    assert client.get("/api/devices/d1/data").status_code == 422


def test_is_port_available_on_free_port():
    assert is_port_available("127.0.0.1", free_port()) is True


def test_resolve_bind_host_keeps_working_host():
    port = free_port()
    assert resolve_bind_host("127.0.0.1", port) == "127.0.0.1"


def test_resolve_bind_host_falls_back_to_all_interfaces():
    # 203.0.113.0/24 is TEST-NET-3 and is never assigned to a local adapter,
    # so binding it fails and the helper must fall back to 0.0.0.0.
    assert resolve_bind_host("203.0.113.1", free_port()) == "0.0.0.0"

