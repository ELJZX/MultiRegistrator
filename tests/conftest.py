import os
import socket
from datetime import datetime

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from multiregistrator.common.archive import ArchiveReader, ArchiveWriter
from multiregistrator.common.models import DeviceConfig, RegisterConfig


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def sample_device() -> DeviceConfig:
    return DeviceConfig(
        id="dev1",
        name="Tewes-Bis Цех №1",
        host="127.0.0.1",
        port=502,
        device_id=1,
        registers=[
            RegisterConfig(name="analogIn", address=1, data_type="float32"),
            RegisterConfig(name="freqIn", address=3, data_type="uint16", scale=0.1),
            RegisterConfig(name="relayStates", address=5, function="coil"),
        ],
    )


@pytest.fixture
def archive_writer(tmp_path) -> ArchiveWriter:
    return ArchiveWriter(tmp_path / "archive")


@pytest.fixture
def archive_reader(tmp_path) -> ArchiveReader:
    return ArchiveReader(tmp_path / "archive")


@pytest.fixture
def fixed_now():
    return lambda: datetime(2026, 10, 13, 12, 0, 0, 123000)
