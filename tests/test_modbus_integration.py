"""End-to-end test: real pymodbus client against a local Modbus TCP stub."""

import pytest

from multiregistrator.common.models import DeviceConfig, RegisterConfig
from multiregistrator.server.modbus import ModbusReadError, ModbusReader

from .conftest import free_port
from .modbus_stub import ModbusTcpStub


@pytest.fixture
def stub():
    port = free_port()
    server = ModbusTcpStub("127.0.0.1", port).start()
    server.registers = {1: 0x41F0, 2: 0x0000, 3: 500, 4: 0xFFFF}
    server.bits = {10: True, 11: False}
    yield server
    server.stop()


def test_real_client_reads_holding_and_coils(stub):
    device = DeviceConfig(
        id="d",
        name="D",
        host="127.0.0.1",
        port=stub.server_address[1],
        timeout=2.0,
        retries=0,
        registers=[
            RegisterConfig(name="analogIn", address=1, data_type="float32"),
            RegisterConfig(name="freqIn", address=3, data_type="uint16", scale=0.1),
            RegisterConfig(name="signed", address=4, data_type="int16"),
            RegisterConfig(name="relay", address=10, function="coil"),
            RegisterConfig(name="relay2", address=11, function="coil"),
        ],
    )
    reader = ModbusReader()
    try:
        values = reader.read(device)
    finally:
        reader.close()

    assert values["analogIn"] == pytest.approx(30.0)
    assert values["freqIn"] == pytest.approx(50.0)
    assert values["signed"] == -1.0
    assert values["relay"] == 1.0
    assert values["relay2"] == 0.0


def test_real_client_reports_offline_when_server_silent(stub):
    stub.fail = True
    device = DeviceConfig(
        id="d",
        name="D",
        host="127.0.0.1",
        port=stub.server_address[1],
        timeout=0.3,
        retries=0,
        registers=[RegisterConfig(name="a", address=1)],
    )
    reader = ModbusReader()
    try:
        with pytest.raises(ModbusReadError):
            reader.read(device)
    finally:
        reader.close()


def test_real_client_reports_offline_when_closed_port():
    port = free_port()
    device = DeviceConfig(
        id="d", name="D", host="127.0.0.1", port=port, timeout=0.3, retries=0,
        registers=[RegisterConfig(name="a", address=1)],
    )
    reader = ModbusReader()
    try:
        with pytest.raises(ModbusReadError):
            reader.read(device)
    finally:
        reader.close()
