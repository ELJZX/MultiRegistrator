import pytest

from multiregistrator.common.models import DeviceConfig, RegisterConfig
from multiregistrator.server.modbus import ModbusReadError, ModbusReader


class FakeResponse:
    def __init__(self, registers=None, bits=None, error=False):
        self.registers = registers or []
        self.bits = bits or []
        self._error = error

    def isError(self):
        return self._error


class FakeClient:
    def __init__(self, host, port, timeout, retries):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.retries = retries
        self.connected = False
        self.closed = False
        self.connect_result = True
        self.error = False
        self.holding = {}
        self.input = {}
        self.coils = {}
        self.discrete = {}
        self.calls = []

    def connect(self):
        if not self.connect_result:
            return False
        self.connected = True
        return True

    def close(self):
        self.connected = False
        self.closed = True

    def _registers(self, memory, address, count, kind):
        self.calls.append((kind, address, count))
        if self.error:
            return FakeResponse(error=True)
        return FakeResponse(registers=[memory.get(address + i, 0) for i in range(count)])

    def _bits(self, memory, address, count, kind):
        self.calls.append((kind, address, count))
        if self.error:
            return FakeResponse(error=True)
        return FakeResponse(bits=[memory.get(address + i, False) for i in range(count)])

    def read_holding_registers(self, address, count=1, device_id=1):
        return self._registers(self.holding, address, count, "holding")

    def read_input_registers(self, address, count=1, device_id=1):
        return self._registers(self.input, address, count, "input")

    def read_coils(self, address, count=1, device_id=1):
        return self._bits(self.coils, address, count, "coil")

    def read_discrete_inputs(self, address, count=1, device_id=1):
        return self._bits(self.discrete, address, count, "discrete")


def make_reader(client):
    return ModbusReader(client_factory=lambda host, port, timeout, retries: client)


def make_device(registers, **kwargs):
    return DeviceConfig(id="d", name="D", host="10.0.0.1", **kwargs, registers=registers)


def test_read_decodes_all_channel_types():
    client = FakeClient("10.0.0.1", 502, 1.0, 0)
    client.holding = {1: 0x41F0, 2: 0x0000, 3: 500}
    client.coils = {5: True}
    device = make_device(
        [
            RegisterConfig(name="analogIn", address=1, data_type="float32"),
            RegisterConfig(name="freqIn", address=3, data_type="uint16", scale=0.1),
            RegisterConfig(name="relay", address=5, function="coil"),
        ]
    )
    values = make_reader(client).read(device)
    assert values["analogIn"] == pytest.approx(30.0)
    assert values["freqIn"] == pytest.approx(50.0)
    assert values["relay"] == 1.0


def test_read_uses_block_merging():
    client = FakeClient("10.0.0.1", 502, 1.0, 0)
    client.holding = {1: 1, 2: 2, 3: 3}
    device = make_device(
        [
            RegisterConfig(name="a", address=1),
            RegisterConfig(name="b", address=2),
            RegisterConfig(name="c", address=3),
        ]
    )
    make_reader(client).read(device)
    assert client.calls == [("holding", 1, 3)]


def test_reader_passes_connection_parameters():
    captured = {}

    def factory(host, port, timeout, retries):
        captured.update(host=host, port=port, timeout=timeout, retries=retries)
        return FakeClient(host, port, timeout, retries)

    reader = ModbusReader(client_factory=factory)
    device = DeviceConfig(
        id="d", name="D", host="10.0.0.9", port=1502, timeout=2.5, retries=2,
        registers=[RegisterConfig(name="a", address=1)],
    )
    reader.read(device)
    assert captured == {"host": "10.0.0.9", "port": 1502, "timeout": 2.5, "retries": 2}


def test_connection_is_reused_between_reads():
    client = FakeClient("10.0.0.1", 502, 1.0, 0)
    client.holding = {1: 1}
    reader = make_reader(client)
    device = make_device([RegisterConfig(name="a", address=1)])
    reader.read(device)
    reader.read(device)
    assert len([c for c in client.calls]) == 2
    assert client.closed is False


def test_error_response_raises_and_closes():
    client = FakeClient("10.0.0.1", 502, 1.0, 0)
    client.error = True
    reader = make_reader(client)
    device = make_device([RegisterConfig(name="a", address=1)])
    with pytest.raises(ModbusReadError):
        reader.read(device)
    assert client.closed is True


def test_connect_failure_raises():
    client = FakeClient("10.0.0.1", 502, 1.0, 0)
    client.connect_result = False
    reader = make_reader(client)
    device = make_device([RegisterConfig(name="a", address=1)])
    with pytest.raises(ModbusReadError):
        reader.read(device)


def test_network_exception_becomes_read_error():
    class BoomClient(FakeClient):
        def read_holding_registers(self, address, count=1, device_id=1):
            raise IOError("socket closed")

    client = BoomClient("10.0.0.1", 502, 1.0, 0)
    reader = make_reader(client)
    device = make_device([RegisterConfig(name="a", address=1)])
    with pytest.raises(ModbusReadError):
        reader.read(device)
    assert client.closed is True


def test_device_without_registers_raises():
    reader = ModbusReader(client_factory=lambda *a, **k: FakeClient(*a, **k))
    with pytest.raises(ModbusReadError):
        reader.read(make_device([]))


def test_missing_block_marks_channel_unavailable():
    class PartialClient(FakeClient):
        def read_holding_registers(self, address, count=1, device_id=1):
            self.calls.append(("holding", address, count))
            if address == 1:  # the "removed sensor" answers with an error
                return FakeResponse(error=True)
            return FakeResponse(
                registers=[self.holding.get(address + i, 0) for i in range(count)]
            )

    client = PartialClient("10.0.0.1", 502, 1.0, 0)
    client.holding = {20: 0x41F0, 21: 0x0000}
    device = make_device(
        [
            RegisterConfig(name="gone", address=1),
            RegisterConfig(name="ok", address=20, data_type="float32"),
        ]
    )
    result = make_reader(client).read_full(device)
    assert result.values["ok"] == pytest.approx(30.0)
    assert result.values["gone"] is None
    assert result.unavailable == {"gone"}
    assert result.available == {"gone": False, "ok": True}


def test_nan_channel_is_unavailable():
    client = FakeClient("10.0.0.1", 502, 1.0, 0)
    client.holding = {1: 0x7FC0, 2: 0x0000}  # NaN (unused channel)
    device = make_device([RegisterConfig(name="empty", address=1, data_type="float32")])
    result = make_reader(client).read_full(device)
    assert result.values["empty"] is None
    assert result.unavailable == {"empty"}


def test_all_blocks_missing_raises_offline():
    client = FakeClient("10.0.0.1", 502, 1.0, 0)
    client.error = True
    reader = make_reader(client)
    device = make_device([RegisterConfig(name="a", address=1)])
    with pytest.raises(ModbusReadError):
        reader.read_full(device)


def test_close_clears_clients():
    client = FakeClient("10.0.0.1", 502, 1.0, 0)
    client.holding = {1: 1}
    reader = make_reader(client)
    device = make_device([RegisterConfig(name="a", address=1)])
    reader.read(device)
    reader.close()
    assert client.closed is True
