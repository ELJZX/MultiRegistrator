from pathlib import Path

from multiregistrator.common.config import (
    ClientConfig,
    ClientSettings,
    ServerConfig,
    ServerSettings,
    load_client_config,
    load_server_config,
    save_client_config,
    save_server_config,
)
from multiregistrator.common.models import DeviceConfig, RegisterConfig


def test_load_missing_server_config_returns_defaults(tmp_path):
    config = load_server_config(tmp_path)
    assert config.settings.api_port == 8120
    assert config.devices == []


def test_server_config_roundtrip(tmp_path):
    config = ServerConfig(
        settings=ServerSettings(api_host="0.0.0.0", api_port=9000, archive_dir="data"),
        devices=[DeviceConfig(id="d", name="D", host="10.0.0.1",
                              registers=[RegisterConfig(name="a", address=1)])],
    )
    save_server_config(config, tmp_path)
    restored = load_server_config(tmp_path)
    assert restored.settings.api_port == 9000
    assert restored.devices[0].registers[0].name == "a"
    assert restored.device_by_id("d").host == "10.0.0.1"


def test_server_config_device_by_id_missing(tmp_path):
    assert ServerConfig().device_by_id("nope") is None


def test_client_config_roundtrip(tmp_path):
    config = ClientConfig(
        settings=ClientSettings(server_host="10.0.0.5", server_port=8121, connection_name="Цех")
    )
    config.connections.append(config.settings)
    save_client_config(config, tmp_path)
    restored = load_client_config(tmp_path)
    assert restored.settings.server_host == "10.0.0.5"
    assert restored.settings.connection_name == "Цех"
    assert len(restored.connections) == 1


def test_load_blank_config_file(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "server_config.json").write_text("", encoding="utf-8")
    assert load_server_config(tmp_path).devices == []


def test_resolve_archive_dir_relative(tmp_path):
    settings = ServerSettings(archive_dir="archive")
    assert settings.resolve_archive_dir(tmp_path) == tmp_path / "archive"


def test_resolve_archive_dir_absolute(tmp_path):
    absolute = tmp_path / "abs"
    settings = ServerSettings(archive_dir=str(absolute))
    assert settings.resolve_archive_dir(tmp_path) == absolute


def test_server_settings_from_dict_ignores_unknown():
    settings = ServerSettings.from_dict({"api_port": 1234, "bogus": True})
    assert settings.api_port == 1234
    assert isinstance(settings, ServerSettings)
