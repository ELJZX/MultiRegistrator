"""Tests for the server entry point helpers (autostart / headless / check)."""

from multiregistrator.common.config import ServerConfig, ServerSettings
from multiregistrator.server import app as server_app

from .conftest import free_port


def test_build_runtime_creates_components(tmp_path):
    config = ServerConfig(
        settings=ServerSettings(
            api_host="127.0.0.1", api_port=free_port(), archive_dir=str(tmp_path / "archive")
        )
    )
    service, api, archive_dir = server_app._build_runtime(config)
    assert archive_dir.exists()
    assert service.is_running is False
    assert api.is_running is False


def test_check_mode_starts_and_stops_api(tmp_path):
    config = ServerConfig(
        settings=ServerSettings(
            api_host="127.0.0.1", api_port=free_port(), archive_dir=str(tmp_path / "archive")
        )
    )
    assert server_app._run_check(config) == 0
