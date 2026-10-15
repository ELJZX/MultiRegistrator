import pytest

from multiregistrator.common.models import DeviceConfig
from multiregistrator.server.discovery import discover_channels


class FakeReader:
    """Returns a fixed two-word answer for a few addresses."""

    def __init__(self, words):
        self.words = words

    def probe(self, device, function, start, count):
        return self.words.get(start)


def make_device():
    return DeviceConfig(id="d", name="D", host="10.0.0.1")


def test_discover_big_endian_float():
    reader = FakeReader({10: [0x41F0, 0x0000]})  # 30.0 big-endian
    candidates = discover_channels(reader, make_device(), "input", 0, 20)
    assert [(c.register.address, c.register.word_order) for c in candidates] == [(10, "big")]
    assert candidates[0].value == pytest.approx(30.0)
    assert candidates[0].register.data_type == "float32"


def test_discover_little_endian_float():
    reader = FakeReader({10: [0x0000, 0x41F0]})  # 30.0 word-swapped
    candidates = discover_channels(reader, make_device(), "input", 0, 20)
    assert len(candidates) == 1
    assert candidates[0].register.word_order == "little"
    assert candidates[0].value == pytest.approx(30.0)


def test_discover_skips_nan_and_garbage():
    reader = FakeReader(
        {
            10: [0x7FC0, 0x0000],  # NaN
            12: [0x0000, 0x0000],  # zero -> not a measurable value
        }
    )
    assert discover_channels(reader, make_device(), "input", 0, 20) == []


def test_discover_consumes_adjacent_address():
    # The float at 10 uses addresses 10 and 11; address 11 must not be scanned.
    reader = FakeReader({10: [0x41F0, 0x0000], 11: [0x41F0, 0x0000]})
    candidates = discover_channels(reader, make_device(), "input", 0, 20)
    assert [c.register.address for c in candidates] == [10]


def test_discover_rejects_bad_function():
    with pytest.raises(ValueError):
        discover_channels(FakeReader({}), make_device(), "coil", 0, 10)
