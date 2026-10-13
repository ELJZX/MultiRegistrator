from datetime import datetime

import pytest

from multiregistrator.common.models import (
    DataType,
    DeviceConfig,
    DeviceStatus,
    RegisterConfig,
    TimeSeries,
    decode_registers,
    encode_registers,
    format_timestamp,
    parse_timestamp,
    register_word_count,
)


@pytest.mark.parametrize(
    "data_type,expected",
    [("uint16", 1), ("int16", 1), ("int32", 2), ("uint32", 2), ("float32", 2)],
)
def test_register_word_count(data_type, expected):
    assert register_word_count(data_type) == expected


def test_decode_uint16():
    assert decode_registers([1234], DataType.UINT16) == 1234


def test_decode_int16_negative():
    assert decode_registers([0xFFFF], DataType.INT16) == -1
    assert decode_registers([0x8000], DataType.INT16) == -32768
    assert decode_registers([0x7FFF], DataType.INT16) == 32767


def test_decode_uint32():
    assert decode_registers([0x0001, 0x0002], DataType.UINT32) == 0x00010002


def test_decode_int32_negative():
    assert decode_registers([0xFFFF, 0xFFFF], DataType.INT32) == -1


def test_decode_float32():
    assert decode_registers([0x41F0, 0x0000], DataType.FLOAT32) == pytest.approx(30.0)


def test_decode_float32_swapped_words():
    assert decode_registers([0x0000, 0x41F0], DataType.FLOAT32, word_order="little") == pytest.approx(30.0)


def test_decode_applies_scale():
    assert decode_registers([100], DataType.UINT16, scale=0.1) == pytest.approx(10.0)


def test_decode_rejects_empty():
    with pytest.raises(ValueError):
        decode_registers([], DataType.UINT16)


def test_decode_rejects_short_32bit():
    with pytest.raises(ValueError):
        decode_registers([1], DataType.INT32)


@pytest.mark.parametrize(
    "data_type,value",
    [
        ("uint16", 1234.0),
        ("int16", -1234.0),
        ("uint32", 70000.0),
        ("int32", -70000.0),
        ("float32", 23.456),
    ],
)
def test_encode_decode_roundtrip(data_type, value):
    words = encode_registers(value, data_type)
    expected_words = register_word_count(data_type)
    assert len(words) == expected_words
    assert decode_registers(words, data_type) == pytest.approx(value, rel=1e-4)


def test_encode_applies_scale():
    words = encode_registers(50.0, "uint16", scale=0.1)
    assert words == [500]
    assert decode_registers(words, "uint16", scale=0.1) == pytest.approx(50.0)


def test_encode_word_order():
    assert encode_registers(1.0, "uint32", word_order="big") == [0, 1]
    assert encode_registers(1.0, "uint32", word_order="little") == [1, 0]


def test_encode_float32_matches_decode():
    words = encode_registers(30.0, "float32")
    assert words == [0x41F0, 0x0000]


def test_register_config_defaults():
    register = RegisterConfig(name="a", address=5)
    assert register.function == "holding"
    assert register.data_type == "uint16"
    assert register.word_count == 1
    assert register.is_bit is False


def test_register_config_rejects_bad_word_order():
    with pytest.raises(ValueError):
        RegisterConfig(name="a", address=0, word_order="middle")


def test_register_config_roundtrip():
    register = RegisterConfig(
        name="flow", address=10, function="input", data_type="int32", scale=2.0, unit="m3"
    )
    restored = RegisterConfig.from_dict(register.to_dict())
    assert restored == register
    assert restored.word_count == 2


def test_bit_register_flag():
    register = RegisterConfig(name="coil", address=0, function="coil")
    assert register.is_bit is True


def test_device_config_defaults_and_channels():
    device = DeviceConfig(id="d", name="D", host="10.0.0.1")
    assert device.port == 502
    assert device.enabled is True
    assert device.channel_names == []


def test_device_config_coerces_registers_from_dicts():
    device = DeviceConfig.from_dict(
        {
            "id": "d",
            "name": "D",
            "host": "10.0.0.1",
            "registers": [{"name": "a", "address": 1}],
            "unknown": "ignored",
        }
    )
    assert isinstance(device.registers[0], RegisterConfig)
    assert device.registers[0].name == "a"


def test_device_config_to_dict_roundtrip(sample_device):
    restored = DeviceConfig.from_dict(sample_device.to_dict())
    assert restored.to_dict() == sample_device.to_dict()


def test_device_config_clamps_values():
    device = DeviceConfig(id="d", name="D", host="h", poll_interval=0.0, retries=-5)
    assert device.poll_interval == 0.1
    assert device.retries == 0


def test_timestamp_roundtrip():
    moment = datetime(2026, 10, 13, 12, 30, 15, 123000)
    text = format_timestamp(moment)
    assert text == "2026-10-13 12:30:15.123"
    assert parse_timestamp(text) == moment


def test_timeseries_add_and_numeric_filters_none():
    series = TimeSeries(channel="a")
    series.add(datetime(2026, 1, 1), 1.0)
    series.add(datetime(2026, 1, 1, 0, 1), None)
    series.add(datetime(2026, 1, 1, 0, 2), 3.0)
    times, values = series.numeric()
    assert len(series) == 3
    assert values == [1.0, 3.0]
    assert len(times) == 2


def test_device_status_to_dict():
    status = DeviceStatus(device_id="d", online=True, latency_ms=1.5, values={"a": 2.0})
    payload = status.to_dict()
    assert payload["device_id"] == "d"
    assert payload["online"] is True
    assert payload["values"] == {"a": 2.0}
