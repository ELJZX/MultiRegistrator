from datetime import date, datetime

from multiregistrator.common.archive import (
    ArchiveReader,
    ArchiveWriter,
    archive_file_path,
    device_folder,
    sanitize_name,
)
from multiregistrator.common.models import DeviceConfig


def test_sanitize_name():
    assert sanitize_name("192.168.1.10") == "192.168.1.10"
    assert sanitize_name("fe80::1") == "fe80__1"
    assert sanitize_name("bad name/") == "bad_name_"


def test_device_folder_and_file_path(tmp_path):
    folder = device_folder(tmp_path, "10.0.0.1")
    assert folder == tmp_path / "10.0.0.1"
    path = archive_file_path(tmp_path, "10.0.0.1", date(2026, 10, 13))
    assert path.name == "10.0.0.1_2026-10-13.txt"
    assert path.parent == folder


def test_append_sample_creates_header_and_row(archive_writer, sample_device, fixed_now):
    path = archive_writer.append_sample(sample_device, fixed_now(), {"analogIn": 1.5, "freqIn": 50.0, "relayStates": 1})
    assert path.exists()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "timestamp,analogIn,freqIn,relayStates"
    assert lines[1].startswith("2026-10-13 12:00:00.123,")
    assert lines[1].split(",")[1] == "1.5"


def test_append_writes_empty_for_missing_value(archive_writer, sample_device, fixed_now):
    path = archive_writer.append_sample(sample_device, fixed_now(), {"analogIn": 1.0})
    row = path.read_text(encoding="utf-8").splitlines()[1]
    assert row.split(",")[3] == ""  # freqIn missing


def test_new_day_creates_new_file(archive_writer, sample_device):
    first = archive_writer.append_sample(sample_device, datetime(2026, 10, 13, 23, 59), {"analogIn": 1.0})
    second = archive_writer.append_sample(sample_device, datetime(2026, 10, 14, 0, 1), {"analogIn": 2.0})
    assert first != second
    assert first.name.endswith("2026-10-13.txt")
    assert second.name.endswith("2026-10-14.txt")


def test_channels_fallback_when_no_registers(archive_writer, tmp_path):
    device = DeviceConfig(id="d", name="D", host="1.2.3.4")
    path = archive_writer.append_sample(device, datetime(2026, 1, 1), {"b": 2.0, "a": 1.0})
    assert path.read_text(encoding="utf-8").splitlines()[0] == "timestamp,a,b"


def test_list_devices_dates_channels(archive_writer, archive_reader, sample_device):
    archive_writer.append_sample(sample_device, datetime(2026, 10, 13, 10, 0), {"analogIn": 1.0})
    archive_writer.append_sample(sample_device, datetime(2026, 10, 14, 10, 0), {"analogIn": 2.0})
    assert archive_reader.list_devices() == ["127.0.0.1"]
    assert archive_reader.list_dates(sample_device.host) == [date(2026, 10, 13), date(2026, 10, 14)]
    assert archive_reader.list_channels(sample_device.host) == ["analogIn", "freqIn", "relayStates"]


def test_list_on_empty_archive(tmp_path):
    reader = ArchiveReader(tmp_path / "archive")
    assert reader.list_devices() == []
    assert reader.list_dates("10.0.0.1") == []
    assert reader.list_channels("10.0.0.1") == []


def test_read_range_filters_by_time(archive_writer, archive_reader, sample_device):
    archive_writer.append_sample(sample_device, datetime(2026, 10, 13, 10, 0), {"analogIn": 1.0})
    archive_writer.append_sample(sample_device, datetime(2026, 10, 13, 11, 0), {"analogIn": 2.0})
    archive_writer.append_sample(sample_device, datetime(2026, 10, 13, 12, 0), {"analogIn": 3.0})
    series = archive_reader.read_range(
        sample_device.host,
        datetime(2026, 10, 13, 10, 30),
        datetime(2026, 10, 13, 11, 30),
    )
    analog = series["analogIn"]
    assert analog.values == [2.0]
    assert analog.times == [datetime(2026, 10, 13, 11, 0)]


def test_read_range_selects_channels(archive_writer, archive_reader, sample_device):
    archive_writer.append_sample(sample_device, datetime(2026, 10, 13, 10, 0), {"analogIn": 1.0, "freqIn": 50.0})
    series = archive_reader.read_range(
        sample_device.host,
        datetime(2026, 10, 13, 0, 0),
        datetime(2026, 10, 13, 23, 59),
        channels=["freqIn"],
    )
    assert list(series) == ["freqIn"]
    assert series["freqIn"].values == [50.0]


def test_read_range_missing_channel_returns_empty(archive_writer, archive_reader, sample_device):
    archive_writer.append_sample(sample_device, datetime(2026, 10, 13, 10, 0), {"analogIn": 1.0})
    series = archive_reader.read_range(
        sample_device.host,
        datetime(2026, 10, 13, 0, 0),
        datetime(2026, 10, 13, 23, 59),
        channels=["nope"],
    )
    assert series["nope"].values == []


def test_read_day(archive_writer, archive_reader, sample_device):
    archive_writer.append_sample(sample_device, datetime(2026, 10, 13, 8, 0), {"analogIn": 5.0})
    archive_writer.append_sample(sample_device, datetime(2026, 10, 14, 8, 0), {"analogIn": 9.0})
    series = archive_reader.read_day(sample_device.host, "2026-10-13")
    assert series["analogIn"].values == [5.0]


def test_writer_channel_names_helper(sample_device):
    assert ArchiveWriter.channel_names(sample_device, {}) == ["analogIn", "freqIn", "relayStates"]
