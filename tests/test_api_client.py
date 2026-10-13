from datetime import datetime

import pytest
import requests

from multiregistrator.client.api_client import ServerApiClient, ServerApiError, parse_series


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = str(payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, payload=None, status=200, error=None):
        self.payload = payload if payload is not None else {}
        self.status = status
        self.error = error
        self.headers = {}
        self.calls = []
        self.closed = False

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        if self.error is not None:
            raise self.error
        return FakeResponse(self.payload, self.status)

    def close(self):
        self.closed = True


def make_client(session):
    return ServerApiClient("10.0.0.5", 8120, session=session)


def test_base_url():
    client = make_client(FakeSession())
    assert client.base_url == "http://10.0.0.5:8120"


def test_health():
    session = FakeSession({"status": "ok"})
    assert make_client(session).health() == {"status": "ok"}
    assert session.calls[0][0].endswith("/api/health")


def test_list_devices():
    session = FakeSession([{"config": {"id": "d"}}])
    assert make_client(session).list_devices()[0]["config"]["id"] == "d"


def test_channels():
    session = FakeSession({"channels": ["a", "b"]})
    assert make_client(session).channels("d") == ["a", "b"]


def test_dates():
    session = FakeSession({"dates": ["2026-10-13"]})
    assert make_client(session).dates("d") == ["2026-10-13"]


def test_latest():
    session = FakeSession({"online": True})
    assert make_client(session).latest("d")["online"] is True


def test_data_builds_params_and_parses_series():
    payload = {
        "channels": {
            "a": {"times": ["2026-10-13T12:00:00"], "values": [1.5]},
        }
    }
    session = FakeSession(payload)
    result = make_client(session).data(
        "d", datetime(2026, 10, 13, 0, 0), datetime(2026, 10, 13, 23, 59), ["a"]
    )
    url, params = session.calls[0]
    assert url.endswith("/api/devices/d/data")
    assert params["channels"] == "a"
    assert result["a"].values == [1.5]
    assert result["a"].times == [datetime(2026, 10, 13, 12, 0, 0)]


def test_http_error_raises():
    session = FakeSession({"detail": "boom"}, status=500)
    with pytest.raises(ServerApiError):
        make_client(session).health()


def test_network_error_raises():
    session = FakeSession(error=requests.ConnectionError("no route"))
    with pytest.raises(ServerApiError):
        make_client(session).health()


def test_close_closes_session():
    session = FakeSession()
    client = make_client(session)
    client.close()
    assert session.closed is True


def test_parse_series_ignores_bad_rows():
    payload = {
        "channels": {
            "a": {"times": ["bad-date", "2026-10-13T12:00:00"], "values": [1.0, None]},
        }
    }
    result = parse_series(payload)
    assert len(result["a"]) == 1
    assert result["a"].values == [None]


def test_parse_series_empty():
    assert parse_series({}) == {}
