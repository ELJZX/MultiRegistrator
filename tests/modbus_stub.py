"""A tiny Modbus/TCP server used to exercise the real pymodbus client.

It implements just enough of the protocol (functions 1-4) to validate that
our :class:`ModbusReader` talks to a real client correctly, without dragging
in the (frequently changing) pymodbus server implementation.
"""

from __future__ import annotations

import socketserver
import struct
import threading
from typing import Optional


def _mbap(transaction_id: int, unit: int, pdu: bytes) -> bytes:
    return struct.pack(">HHHB", transaction_id, 0, len(pdu) + 1, unit) + pdu


class _Handler(socketserver.BaseRequestHandler):
    def _recv(self, size: int) -> Optional[bytes]:
        data = b""
        while len(data) < size:
            chunk = self.request.recv(size - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def handle(self) -> None:
        server: "ModbusTcpStub" = self.server  # type: ignore[assignment]
        while True:
            header = self._recv(7)
            if header is None:
                return
            transaction_id, _protocol, length, unit = struct.unpack(">HHHB", header)
            pdu = self._recv(length - 1)
            if pdu is None:
                return
            function = pdu[0]
            if server.fail:
                continue  # simulate a hung / silent device
            try:
                response_pdu = self._dispatch(server, function, pdu)
            except Exception:  # pragma: no cover - defensive
                response_pdu = struct.pack(">BB", function | 0x80, 0x02)
            self.request.sendall(_mbap(transaction_id, unit, response_pdu))

    @staticmethod
    def _dispatch(server: "ModbusTcpStub", function: int, pdu: bytes) -> bytes:
        if function in (3, 4):
            address, count = struct.unpack(">HH", pdu[1:5])
            if not 1 <= count <= 125:
                return struct.pack(">BB", function | 0x80, 0x03)
            registers = [
                server.registers.get(address + offset, 0) & 0xFFFF
                for offset in range(count)
            ]
            payload = b"".join(struct.pack(">H", value) for value in registers)
            return struct.pack(">BB", function, count * 2) + payload
        if function in (1, 2):
            address, count = struct.unpack(">HH", pdu[1:5])
            bits = [
                1 if server.bits.get(address + offset, 0) else 0
                for offset in range(count)
            ]
            byte_count = (count + 7) // 8
            packed = bytearray(byte_count)
            for index, bit in enumerate(bits):
                if bit:
                    packed[index // 8] |= 1 << (index % 8)
            return struct.pack(">BB", function, byte_count) + bytes(packed)
        return struct.pack(">BB", function | 0x80, 0x01)


class ModbusTcpStub(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, host: str, port: int) -> None:
        super().__init__((host, port), _Handler)
        self.registers: dict[int, int] = {}
        self.bits: dict[int, bool] = {}
        self.fail = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> "ModbusTcpStub":
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self.shutdown()
        self.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
