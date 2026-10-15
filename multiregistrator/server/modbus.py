"""Delicate Modbus TCP access.

The :class:`ModbusReader` keeps a single connection per device, merges
neighbouring registers into as few requests as possible and never blocks the
rest of the application.  Network behaviour is intentionally conservative:

* one shared connection per device (no reconnect storm),
* registers are coalesced into blocks (fewer round trips),
* optional small delay between requests (keeps the bus calm),
* every failure closes the connection so the next poll starts clean.
"""

from __future__ import annotations

import math
import struct
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from ..common.models import DeviceConfig, RegisterConfig, RegisterFunction, decode_registers

try:  # pragma: no cover - import only fails when pymodbus is missing
    from pymodbus.client import ModbusTcpClient
except Exception:  # pragma: no cover
    ModbusTcpClient = None  # type: ignore[assignment]

MAX_REGISTERS_PER_REQUEST = 125


class ModbusReadError(RuntimeError):
    """Raised when a device could not be read (offline / bad answer)."""


@dataclass
class ReadResult:
    """Outcome of one device poll.

    ``values`` holds every configured channel (``None`` when the value could not
    be read).  ``unavailable`` lists the channels that did not return usable data
    this time -- either because their Modbus block could not be read (e.g. the
    sensor was disconnected) or because the device answered with NaN.
    """

    values: dict[str, Optional[float]]
    unavailable: set[str] = field(default_factory=set)

    @property
    def available(self) -> dict[str, bool]:
        return {name: name not in self.unavailable for name in self.values}


@dataclass
class ReadBlock:
    """A contiguous span of registers/coils to read with one request."""

    function: str
    start: int
    count: int
    registers: list[RegisterConfig] = field(default_factory=list)

    @property
    def end(self) -> int:
        return self.start + self.count - 1


def build_read_blocks(
    registers: list[RegisterConfig],
    max_registers: int = MAX_REGISTERS_PER_REQUEST,
    max_gap: int = 8,
) -> list[ReadBlock]:
    """Group registers into minimal number of reads.

    Registers of the same function family are sorted by address and merged
    while the gap between them is small (``max_gap``) and the resulting block
    stays within the Modbus limit.  This dramatically reduces the number of
    TCP requests for devices with contiguous register maps.
    """

    blocks: list[ReadBlock] = []
    for function in RegisterFunction:
        group = [r for r in registers if r.function == function.value]
        if not group:
            continue
        group.sort(key=lambda r: r.address)
        current: Optional[ReadBlock] = None
        for register in group:
            width = 1 if register.is_bit else register.word_count
            if current is None:
                current = ReadBlock(function.value, register.address, width, [register])
                continue
            gap = register.address - (current.start + current.count)
            new_count = register.address + width - current.start
            if 0 <= gap <= max_gap and new_count <= max_registers:
                current.count = new_count
                current.registers.append(register)
            else:
                blocks.append(current)
                current = ReadBlock(function.value, register.address, width, [register])
        if current is not None:
            blocks.append(current)
    return blocks


def _default_client_factory(host: str, port: int, timeout: float, retries: int):
    if ModbusTcpClient is None:  # pragma: no cover
        raise ModbusReadError("pymodbus is not installed")
    return ModbusTcpClient(host, port=port, timeout=timeout, retries=retries)


class ModbusReader:
    """Reads all configured channels of a device as one :class:`dict`."""

    def __init__(
        self,
        inter_request_delay: float = 0.0,
        client_factory: Optional[Callable[..., object]] = None,
    ) -> None:
        self.inter_request_delay = max(0.0, float(inter_request_delay))
        self._client_factory = client_factory or _default_client_factory
        self._clients: dict[str, object] = {}

    # -- connection management ---------------------------------------------
    def _get_client(self, device: DeviceConfig):
        client = self._clients.get(device.id)
        if client is not None and getattr(client, "connected", False):
            return client
        if client is not None:
            self._safe_close(client)
        client = self._client_factory(
            device.host, device.port, device.timeout, device.retries
        )
        if hasattr(client, "connect") and not client.connect():
            raise ModbusReadError(f"cannot connect to {device.host}:{device.port}")
        self._clients[device.id] = client
        return client

    @staticmethod
    def _safe_close(client) -> None:
        try:
            client.close()
        except Exception:  # pragma: no cover - defensive
            pass

    def close(self, device_id: Optional[str] = None) -> None:
        if device_id is None:
            for client in self._clients.values():
                self._safe_close(client)
            self._clients.clear()
            return
        client = self._clients.pop(device_id, None)
        if client is not None:
            self._safe_close(client)

    # -- reading ------------------------------------------------------------
    def read(self, device: DeviceConfig) -> dict[str, Optional[float]]:
        """Read every channel; return a plain ``name -> value`` mapping.

        Kept for backward compatibility -- use :meth:`read_full` when the
        per-channel availability is needed.
        """

        return self.read_full(device).values

    def read_full(self, device: DeviceConfig) -> ReadResult:
        """Read every channel, tolerating individual blocks going missing.

        The whole device is only considered offline (an exception is raised)
        when *no* block could be read at all -- for example when the device is
        unreachable or answers nothing.  A single unreadable block (a sensor
        that was removed) simply marks its channels as unavailable while the
        remaining channels keep working.
        """

        if not device.registers:
            raise ModbusReadError(f"device {device.id} has no registers configured")

        blocks = build_read_blocks(device.registers)
        values: dict[str, Optional[float]] = {}
        unavailable: set[str] = set()
        client = None
        readable_blocks = 0
        last_error: Optional[str] = None
        try:
            client = self._get_client(device)
            for index, block in enumerate(blocks):
                if index and self.inter_request_delay:
                    time.sleep(self.inter_request_delay)
                for register in block.registers:
                    values.setdefault(register.name, None)
                try:
                    raw = self._read_block(client, device, block)
                except ModbusReadError as exc:
                    # A missing sensor / unreadable block: keep the device
                    # online but flag these channels as unavailable.
                    last_error = str(exc)
                    for register in block.registers:
                        unavailable.add(register.name)
                    continue
                readable_blocks += 1
                for register in block.registers:
                    offset = register.address - block.start
                    if register.is_bit:
                        values[register.name] = float(1 if raw[offset] else 0)
                    else:
                        width = register.word_count
                        words = raw[offset : offset + width]
                        try:
                            decoded = decode_registers(
                                words,
                                register.data_type,
                                register.scale,
                                register.word_order,
                            )
                        except (ValueError, struct.error) as exc:
                            last_error = f"cannot decode {register.name}: {exc}"
                            unavailable.add(register.name)
                            values[register.name] = None
                            continue
                        if isinstance(decoded, float) and math.isnan(decoded):
                            # The device reports unused channels as NaN.
                            unavailable.add(register.name)
                            values[register.name] = None
                        else:
                            values[register.name] = decoded
        except ModbusReadError:
            self.close(device.id)
            raise
        except Exception as exc:  # network errors -> offline
            self.close(device.id)
            raise ModbusReadError(str(exc)) from exc

        if readable_blocks == 0:
            self.close(device.id)
            raise ModbusReadError(last_error or f"no data from {device.host}")
        return ReadResult(values=values, unavailable=unavailable)

    def probe(
        self,
        device: DeviceConfig,
        function: str,
        start: int,
        count: int,
    ) -> Optional[list]:
        """Read a single raw block without raising (used by discovery).

        Returns the raw register/bits list on success or ``None`` when the
        device rejects the request (illegal address, no answer, ...).
        """

        block = ReadBlock(RegisterFunction(function).value, start, count)
        try:
            client = self._get_client(device)
            return self._read_block(client, device, block)
        except Exception:
            return None

    def _read_block(self, client, device: DeviceConfig, block: ReadBlock) -> list:
        function = RegisterFunction(block.function)
        try:
            if function is RegisterFunction.HOLDING:
                response = client.read_holding_registers(
                    block.start, count=block.count, device_id=device.device_id
                )
            elif function is RegisterFunction.INPUT:
                response = client.read_input_registers(
                    block.start, count=block.count, device_id=device.device_id
                )
            elif function is RegisterFunction.COIL:
                response = client.read_coils(
                    block.start, count=block.count, device_id=device.device_id
                )
            else:
                response = client.read_discrete_inputs(
                    block.start, count=block.count, device_id=device.device_id
                )
        except TypeError:
            # Older pymodbus releases use ``slave`` instead of ``device_id``.
            response = self._read_block_legacy(client, device, block, function)
        if response is None or response.isError():
            raise ModbusReadError(
                f"bad response for {device.host} @{block.start}+{block.count}"
            )
        if function.is_bit:
            return list(getattr(response, "bits", []))[: block.count]
        return list(getattr(response, "registers", []))

    @staticmethod
    def _read_block_legacy(client, device, block: ReadBlock, function: RegisterFunction):
        kwargs = {"slave": device.device_id}
        if function is RegisterFunction.HOLDING:
            return client.read_holding_registers(block.start, count=block.count, **kwargs)
        if function is RegisterFunction.INPUT:
            return client.read_input_registers(block.start, count=block.count, **kwargs)
        if function is RegisterFunction.COIL:
            return client.read_coils(block.start, count=block.count, **kwargs)
        return client.read_discrete_inputs(block.start, count=block.count, **kwargs)
