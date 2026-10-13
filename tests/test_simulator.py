"""Tests for the bundled Modbus test device simulator."""

import pytest

from multiregistrator.common.models import (
    DeviceConfig,
    RegisterConfig,
    decode_registers,
    encode_registers,
)
from multiregistrator.server.modbus import ModbusReader
from multiregistrator.tools.modbus_simulator import ModbusSimulator, pack_bits

from .conftest import free_port


@pytest.fixture
def simulator():
    server = ModbusSimulator("127.0.0.1", free_port()).start()
    yield server
    server.stop()


def test_pack_bits_lsb_first():
    assert pack_bits([True, False, True]) == bytes([0b101])


def _reader():
    return ModbusReader()


def _device(simulator, registers):
    return DeviceConfig(
        id="sim",
        name="Sim",
        host="127.0.0.1",
        port=simulator.address[1],
        timeout=2.0,
        retries=0,
        registers=registers,
    )


def test_read_holding_float_and_scaled(simulator):
    simulator.set_holding(1, encode_registers(23.5, "float32"))
    simulator.set_holding(3, encode_registers(55.0, "uint16", scale=0.1))
    device = _device(
        simulator,
        [
            RegisterConfig(name="temperature", address=1, data_type="float32"),
            RegisterConfig(name="humidity", address=3, data_type="uint16", scale=0.1),
        ],
    )
    reader = _reader()
    try:
        values = reader.read(device)
    finally:
        reader.close()
    assert values["temperature"] == pytest.approx(23.5)
    assert values["humidity"] == pytest.approx(55.0)


def test_read_coils_and_discrete(simulator):
    simulator.set_coil(1, True)
    simulator.set_coil(2, False)
    simulator.set_discrete(5, True)
    device = _device(
        simulator,
        [
            RegisterConfig(name="relay", address=1, function="coil"),
            RegisterConfig(name="relay2", address=2, function="coil"),
            RegisterConfig(name="door", address=5, function="discrete"),
        ],
    )
    reader = _reader()
    try:
        values = reader.read(device)
    finally:
        reader.close()
    assert values["relay"] == 1.0
    assert values["relay2"] == 0.0
    assert values["door"] == 1.0


def test_values_can_be_updated_live(simulator):
    simulator.set_holding(1, [0, 0])
    reader = _reader()
    device = _device(
        simulator, [RegisterConfig(name="t", address=1, data_type="uint32")]
    )
    try:
        assert reader.read(device)["t"] == 0.0
        simulator.set_holding(1, encode_registers(1234.0, "uint32"))
        assert reader.read(device)["t"] == pytest.approx(1234.0)
    finally:
        reader.close()


def test_write_single_register_with_real_client(simulator):
    from pymodbus.client import ModbusTcpClient

    client = ModbusTcpClient(
        "127.0.0.1", port=simulator.address[1], timeout=2.0, retries=0
    )
    assert client.connect()
    try:
        client.write_register(6, 4321, device_id=1)
    finally:
        client.close()
    assert simulator.get_holding(6) == 4321


def test_write_multiple_coils_with_real_client(simulator):
    from pymodbus.client import ModbusTcpClient

    client = ModbusTcpClient(
        "127.0.0.1", port=simulator.address[1], timeout=2.0, retries=0
    )
    assert client.connect()
    try:
        client.write_coils(10, [True, True, False, True], device_id=1)
    finally:
        client.close()
    device = _device(
        simulator,
        [
            RegisterConfig(name="c1", address=10, function="coil"),
            RegisterConfig(name="c4", address=13, function="coil"),
        ],
    )
    reader = _reader()
    try:
        values = reader.read(device)
    finally:
        reader.close()
    assert values["c1"] == 1.0
    assert values["c4"] == 1.0


def test_encode_decode_matches_simulator(simulator):
    words = encode_registers(99.9, "float32")
    simulator.set_holding(1, words)
    assert decode_registers([simulator.get_holding(1), simulator.get_holding(2)], "float32") == pytest.approx(99.9)
