import time
from datetime import datetime

from multiregistrator.common.archive import ArchiveReader, ArchiveWriter
from multiregistrator.common.models import DeviceConfig, RegisterConfig
from multiregistrator.server.service import ServerService


class FakeReader:
    def __init__(self, values=None, error=None):
        self.values = values if values is not None else {"a": 1.0}
        self.error = error
        self.closed = []
        self.read_calls = 0

    def read(self, device):
        self.read_calls += 1
        if self.error:
            raise RuntimeError(self.error)
        return dict(self.values)

    def close(self, device_id=None):
        self.closed.append(device_id)


def make_device(device_id="d1", **kwargs):
    return DeviceConfig(
        id=device_id,
        name=device_id,
        host="127.0.0.1",
        poll_interval=kwargs.pop("poll_interval", 5.0),
        registers=[RegisterConfig(name="a", address=1)],
        **kwargs,
    )


def test_poll_once_writes_archive_and_sets_online(tmp_path):
    writer = ArchiveWriter(tmp_path / "archive")
    reader = FakeReader({"a": 42.0})
    service = ServerService(
        reader, writer, [make_device()],
        now=lambda: datetime(2026, 10, 13, 12, 0, 0),
    )
    results = service.poll_once()
    status = results["d1"]
    assert status.online is True
    assert status.values == {"a": 42.0}
    assert status.last_error == ""

    files = list((tmp_path / "archive" / "127.0.0.1").glob("*.txt"))
    assert len(files) == 1
    assert files[0].read_text(encoding="utf-8").splitlines()[1].startswith("2026-10-13 12:00:00")


def test_poll_once_failure_sets_offline(tmp_path):
    writer = ArchiveWriter(tmp_path / "archive")
    reader = FakeReader(error="timeout")
    service = ServerService(reader, writer, [make_device()])
    status = service.poll_once()["d1"]
    assert status.online is False
    assert "timeout" in status.last_error


def test_status_callback_is_invoked(tmp_path):
    received = []
    service = ServerService(
        FakeReader(), ArchiveWriter(tmp_path / "archive"), [make_device()],
        on_status=received.append,
    )
    service.poll_once()
    assert len(received) == 1
    assert received[0].device_id == "d1"


def test_disabled_device_is_skipped(tmp_path):
    reader = FakeReader()
    service = ServerService(
        reader, ArchiveWriter(tmp_path / "archive"), [make_device(enabled=False)]
    )
    assert service.poll_once() == {}
    assert reader.read_calls == 0


def test_set_devices_adds_and_removes(tmp_path):
    reader = FakeReader()
    service = ServerService(reader, ArchiveWriter(tmp_path / "archive"), [make_device("a")])
    service.set_devices([make_device("a"), make_device("b")])
    assert {d.id for d in service.get_devices()} == {"a", "b"}
    assert service.get_status("b") is not None

    service.set_devices([make_device("b")])
    assert [d.id for d in service.get_devices()] == ["b"]
    assert service.get_status("a") is None
    assert "a" in reader.closed


def test_start_and_stop_scheduler(tmp_path):
    reader = FakeReader()
    writer = ArchiveWriter(tmp_path / "archive")
    service = ServerService(
        reader, writer, [make_device(poll_interval=0.1)], poll_tick=0.02
    )
    service.start()
    assert service.is_running is True
    time.sleep(0.35)
    service.stop()
    assert service.is_running is False
    assert reader.read_calls >= 1
    files = list((tmp_path / "archive" / "127.0.0.1").glob("*.txt"))
    assert files


def test_start_is_idempotent(tmp_path):
    service = ServerService(FakeReader(), ArchiveWriter(tmp_path / "archive"), [make_device()])
    service.start()
    try:
        assert service.is_running is True
    finally:
        service.stop()


class _Result:
    def __init__(self, values, available):
        self.values = values
        self.available = available


class FakeReaderFull:
    def __init__(self, result):
        self._result = result

    def read_full(self, device):
        return self._result

    def close(self, device_id=None):
        pass


def test_channel_availability_is_recorded(tmp_path):
    reader = FakeReaderFull(_Result({"a": 1.0, "b": None}, {"a": True, "b": False}))
    device = DeviceConfig(
        id="d1",
        name="d1",
        host="127.0.0.1",
        registers=[
            RegisterConfig(name="a", address=1),
            RegisterConfig(name="b", address=2),
        ],
    )
    service = ServerService(reader, ArchiveWriter(tmp_path / "archive"), [device])
    status = service.poll_once()["d1"]
    assert status.online is True
    assert status.channel_available == {"a": True, "b": False}


def test_poll_populates_archive_reader(tmp_path):
    archive_dir = tmp_path / "archive"
    service = ServerService(
        FakeReader({"a": 7.0}), ArchiveWriter(archive_dir), [make_device()],
        now=lambda: datetime(2026, 10, 13, 12, 0, 0),
    )
    service.poll_once()
    series = ArchiveReader(archive_dir).read_range(
        "127.0.0.1", datetime(2026, 10, 13, 0, 0), datetime(2026, 10, 13, 23, 59)
    )
    assert series["a"].values == [7.0]


def test_notify_logs_callback_errors(tmp_path):
    import logging

    from multiregistrator.common.logging_setup import setup_logging

    log_file = setup_logging("service-notify-test", base_dir=tmp_path)

    def boom(status):
        raise RuntimeError("callback boom")

    service = ServerService(
        FakeReader({"a": 1.0}),
        ArchiveWriter(tmp_path / "archive"),
        [make_device()],
        on_status=boom,
    )
    service.poll_once()
    for handler in logging.getLogger("multiregistrator").handlers:
        handler.flush()

    text = log_file.read_text(encoding="utf-8")
    assert "callback boom" in text
    assert "service" in text
