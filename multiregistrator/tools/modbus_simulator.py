"""A small, dependency-free Modbus/TCP slave used as a test device.

It implements the read functions (1-4) and the write functions (5, 6, 15, 16)
of the Modbus specification on top of a plain threaded socket server.  It is
deliberately self-contained so that it does not depend on the (frequently
changing) pymodbus server API and stays compatible with every pymodbus client.

Values live in four address spaces (holding / input registers and coils /
discrete inputs) that can be updated at any time from another thread.
"""

from __future__ import annotations

import socketserver
import struct
import threading
from typing import Iterable, Union

RegisterMap = dict
Value = Union[int, bool]
Values = Union[Value, Iterable[Value]]


def pack_bits(values: Iterable[bool]) -> bytes:
    """Pack a sequence of bits LSB-first into Modbus bytes."""

    values = list(values)
    packed = bytearray((len(values) + 7) // 8)
    for index, bit in enumerate(values):
        if bit:
            packed[index // 8] |= 1 << (index % 8)
    return bytes(packed)


class _ModbusServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address) -> None:
        super().__init__(address, _ModbusRequestHandler)
        self.holding: RegisterMap = {}
        self.input: RegisterMap = {}
        self.coils: RegisterMap = {}
        self.discrete: RegisterMap = {}
        self.lock = threading.RLock()
        self.connections = 0


class _ModbusRequestHandler(socketserver.BaseRequestHandler):
    def _recv_exact(self, size: int):
        data = b""
        while len(data) < size:
            chunk = self.request.recv(size - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def handle(self) -> None:
        server: _ModbusServer = self.server  # type: ignore[assignment]
        with server.lock:
            server.connections += 1
        try:
            while True:
                header = self._recv_exact(7)
                if header is None:
                    break
                transaction_id, _protocol, length, unit = struct.unpack(">HHHB", header)
                pdu = self._recv_exact(max(1, length - 1))
                if pdu is None:
                    break
                response = self._process(server, pdu)
                self.request.sendall(
                    struct.pack(">HHHB", transaction_id, 0, len(response) + 1, unit)
                    + response
                )
        except OSError:
            pass
        finally:
            with server.lock:
                server.connections -= 1

    @staticmethod
    def _exception(function: int, code: int) -> bytes:
        return struct.pack(">BB", function | 0x80, code)

    def _process(self, server: _ModbusServer, pdu: bytes) -> bytes:
        function = pdu[0]
        with server.lock:
            if function in (3, 4):
                address, count = struct.unpack(">HH", pdu[1:5])
                if not 1 <= count <= 125:
                    return self._exception(function, 0x03)
                memory = server.holding if function == 3 else server.input
                registers = [memory.get(address + i, 0) & 0xFFFF for i in range(count)]
                payload = b"".join(struct.pack(">H", value) for value in registers)
                return struct.pack(">BB", function, count * 2) + payload

            if function in (1, 2):
                address, count = struct.unpack(">HH", pdu[1:5])
                if not 1 <= count <= 2000:
                    return self._exception(function, 0x03)
                memory = server.coils if function == 1 else server.discrete
                bits = [bool(memory.get(address + i, 0)) for i in range(count)]
                packed = pack_bits(bits)
                return struct.pack(">BB", function, len(packed)) + packed

            if function == 5:
                address, value = struct.unpack(">HH", pdu[1:5])
                server.coils[address] = value == 0xFF00
                return pdu[:5]

            if function == 6:
                address, value = struct.unpack(">HH", pdu[1:5])
                server.holding[address] = value
                return pdu[:5]

            if function == 15:
                address, count, byte_count = struct.unpack(">HHB", pdu[1:6])
                payload = pdu[6 : 6 + byte_count]
                for i in range(count):
                    server.coils[address + i] = bool(payload[i // 8] & (1 << (i % 8)))
                return struct.pack(">BHH", function, address, count)

            if function == 16:
                address, count, byte_count = struct.unpack(">HHB", pdu[1:6])
                payload = pdu[6 : 6 + byte_count]
                for i in range(count):
                    server.holding[address + i] = struct.unpack(
                        ">H", payload[i * 2 : i * 2 + 2]
                    )[0]
                return struct.pack(">BHH", function, address, count)

        return self._exception(function, 0x01)


class ModbusSimulator:
    """Threaded Modbus/TCP slave with a mutable register bank."""

    def __init__(self, host: str = "0.0.0.0", port: int = 5020) -> None:
        self._server = _ModbusServer((host, port))
        self._thread: threading.Thread | None = None

    @property
    def address(self) -> tuple[str, int]:
        return self._server.server_address  # type: ignore[return-value]

    @property
    def connections(self) -> int:
        with self._server.lock:
            return self._server.connections

    # -- value access -------------------------------------------------------
    def _write(self, memory: RegisterMap, address: int, values: Values) -> None:
        sequence = values if isinstance(values, (list, tuple)) else [values]
        with self._server.lock:
            for offset, value in enumerate(sequence):
                memory[address + offset] = int(value) & 0xFFFF

    def set_holding(self, address: int, values: Values) -> None:
        self._write(self._server.holding, address, values)

    def set_input(self, address: int, values: Values) -> None:
        self._write(self._server.input, address, values)

    def set_coil(self, address: int, value: bool) -> None:
        with self._server.lock:
            self._server.coils[address] = bool(value)

    def set_discrete(self, address: int, value: bool) -> None:
        with self._server.lock:
            self._server.discrete[address] = bool(value)

    def get_holding(self, address: int) -> int:
        with self._server.lock:
            return self._server.holding.get(address, 0)

    # -- lifecycle ----------------------------------------------------------
    def start(self) -> "ModbusSimulator":
        if self._thread is not None:
            return self
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._thread is None:
            return
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)
        self._thread = None

    def __enter__(self) -> "ModbusSimulator":
        return self.start()

    def __exit__(self, *_exc) -> None:
        self.stop()
