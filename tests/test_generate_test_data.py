from datetime import datetime

from multiregistrator.common.archive import ArchiveReader
from multiregistrator.common.config import load_server_config
from multiregistrator.tools.generate_test_data import (
    generate,
    install_config,
    test_device_config,
)


def test_device_config_matches_simulator():
    device = test_device_config("127.0.0.1", 5020)
    assert device.id == "127.0.0.1"
    assert device.port == 5020
    assert device.channel_names == ["temperature", "humidity", "counter", "relay"]


def test_generate_creates_readable_archive(tmp_path):
    end = datetime(2026, 10, 13, 12, 0, 0)
    rows = generate(tmp_path / "archive", hours=2, interval=60, end=end)
    assert rows == 120

    reader = ArchiveReader(tmp_path / "archive")
    series = reader.read_range(
        "127.0.0.1",
        datetime(2026, 10, 13, 0, 0),
        datetime(2026, 10, 14, 0, 0),
    )
    assert set(series) == {"temperature", "humidity", "counter", "relay"}
    assert len(series["temperature"]) == 120
    assert all(-50.0 <= value <= 150.0 for value in series["temperature"].values if value is not None)


def test_generate_spanning_multiple_days(tmp_path):
    end = datetime(2026, 10, 14, 1, 0, 0)
    generate(tmp_path / "archive", hours=3, interval=3600, end=end)
    reader = ArchiveReader(tmp_path / "archive")
    assert len(reader.list_dates("127.0.0.1")) == 2


def test_generate_rejects_bad_interval(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        generate(tmp_path / "archive", interval=0)


def test_install_config_adds_once(tmp_path):
    assert install_config(tmp_path, host="10.0.0.5", port=5020) is True
    assert install_config(tmp_path, host="10.0.0.5", port=5020) is False
    config = load_server_config(tmp_path)
    assert [d.host for d in config.devices] == ["10.0.0.5"]
