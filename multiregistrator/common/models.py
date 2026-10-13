"""Domain models shared by the server and the client.

The module is intentionally free of any GUI / networking / hardware
dependency so that every model (and the decoding routines) can be unit
tested in isolation.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field, fields
from datetime import date, datetime
from enum import Enum
from typing import Any, Optional


class RegisterFunction(str, Enum):
    """Modbus function family used to read a register."""

    HOLDING = "holding"
    INPUT = "input"
    COIL = "coil"
    DISCRETE = "discrete"

    @property
    def is_bit(self) -> bool:
        return self in (RegisterFunction.COIL, RegisterFunction.DISCRETE)


class DataType(str, Enum):
    INT16 = "int16"
    UINT16 = "uint16"
    INT32 = "int32"
    UINT32 = "uint32"
    FLOAT32 = "float32"

    @property
    def word_count(self) -> int:
        if self in (DataType.INT32, DataType.UINT32, DataType.FLOAT32):
            return 2
        return 1


def register_word_count(data_type: DataType | str) -> int:
    """Return how many 16-bit registers the given data type occupies."""

    return DataType(data_type).word_count


def decode_registers(
    words: list[int],
    data_type: DataType | str,
    scale: float = 1.0,
    word_order: str = "big",
) -> float:
    """Decode raw 16-bit words into a scaled Python float.

    ``word_order`` only affects 32-bit types and selects which of the two
    16-bit words is the most significant one (``"big"`` = ABCD, ``"little"``
    = CDAB).  Byte order inside a word is always big-endian, as required by
    the Modbus specification.
    """

    data_type = DataType(data_type)
    if not words:
        raise ValueError("no registers to decode")

    if data_type is DataType.UINT16:
        raw: float = int(words[0]) & 0xFFFF
    elif data_type is DataType.INT16:
        value = int(words[0]) & 0xFFFF
        raw = value - 0x10000 if value >= 0x8000 else value
    else:
        if len(words) < 2:
            raise ValueError(f"{data_type.value} requires 2 registers")
        high, low = int(words[0]) & 0xFFFF, int(words[1]) & 0xFFFF
        if word_order == "little":
            high, low = low, high
        combined = (high << 16) | low
        if data_type is DataType.INT32:
            raw = combined - 0x100000000 if combined >= 0x80000000 else combined
        elif data_type is DataType.UINT32:
            raw = combined
        else:  # FLOAT32
            raw = struct.unpack(">f", struct.pack(">I", combined))[0]
    return raw * scale


TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S.%f"


def format_timestamp(value: datetime) -> str:
    """Format a datetime for the archive file (millisecond precision)."""

    return value.replace(tzinfo=None).isoformat(sep=" ", timespec="milliseconds")


def parse_timestamp(value: str) -> datetime:
    """Parse a timestamp previously produced by :func:`format_timestamp`."""

    value = value.strip()
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.strptime(value, TIMESTAMP_FORMAT)


def _filtered_kwargs(cls: type, data: dict[str, Any]) -> dict[str, Any]:
    known = {f.name for f in fields(cls)}
    return {key: value for key, value in data.items() if key in known}


@dataclass
class RegisterConfig:
    """Description of a single readable value (``channel``) of a device."""

    name: str
    address: int
    function: str = RegisterFunction.HOLDING.value
    data_type: str = DataType.UINT16.value
    scale: float = 1.0
    unit: str = ""
    word_order: str = "big"
    writable: bool = False

    def __post_init__(self) -> None:
        self.name = str(self.name)
        self.address = int(self.address)
        self.function = RegisterFunction(self.function).value
        self.data_type = DataType(self.data_type).value
        self.scale = float(self.scale)
        self.word_order = str(self.word_order).lower()
        if self.word_order not in ("big", "little"):
            raise ValueError("word_order must be 'big' or 'little'")

    @property
    def word_count(self) -> int:
        return register_word_count(self.data_type)

    @property
    def is_bit(self) -> bool:
        return RegisterFunction(self.function).is_bit

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "address": self.address,
            "function": self.function,
            "data_type": self.data_type,
            "scale": self.scale,
            "unit": self.unit,
            "word_order": self.word_order,
            "writable": self.writable,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RegisterConfig":
        return cls(**_filtered_kwargs(cls, data))


@dataclass
class DeviceConfig:
    """A single Modbus TCP device (data logger / registrator)."""

    id: str
    name: str
    host: str
    port: int = 502
    device_id: int = 1
    enabled: bool = True
    poll_interval: float = 5.0
    timeout: float = 3.0
    retries: int = 1
    registers: list[RegisterConfig] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.id = str(self.id)
        self.name = str(self.name)
        self.host = str(self.host)
        self.port = int(self.port)
        self.device_id = int(self.device_id)
        self.poll_interval = max(0.1, float(self.poll_interval))
        self.timeout = max(0.1, float(self.timeout))
        self.retries = max(0, int(self.retries))
        self.registers = [
            r if isinstance(r, RegisterConfig) else RegisterConfig.from_dict(r)
            for r in self.registers
        ]

    @property
    def channel_names(self) -> list[str]:
        return [r.name for r in self.registers]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "device_id": self.device_id,
            "enabled": self.enabled,
            "poll_interval": self.poll_interval,
            "timeout": self.timeout,
            "retries": self.retries,
            "registers": [r.to_dict() for r in self.registers],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeviceConfig":
        data = dict(data)
        registers = [RegisterConfig.from_dict(r) for r in data.pop("registers", [])]
        kwargs = _filtered_kwargs(cls, data)
        return cls(registers=registers, **kwargs)


@dataclass
class DeviceStatus:
    """Runtime status of a device (never persisted)."""

    device_id: str
    online: bool = False
    last_attempt: Optional[datetime] = None
    last_success: Optional[datetime] = None
    last_error: str = ""
    latency_ms: float = 0.0
    values: dict[str, Optional[float]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "online": self.online,
            "last_attempt": self.last_attempt,
            "last_success": self.last_success,
            "last_error": self.last_error,
            "latency_ms": self.latency_ms,
            "values": dict(self.values),
        }


@dataclass
class Sample:
    """A single decoded measurement batch."""

    device_id: str
    timestamp: datetime
    values: dict[str, Optional[float]]


@dataclass
class TimeSeries:
    """A named series of ``(time, value)`` pairs (``None`` = missing)."""

    channel: str
    times: list[datetime] = field(default_factory=list)
    values: list[Optional[float]] = field(default_factory=list)

    def add(self, timestamp: datetime, value: Optional[float]) -> None:
        self.times.append(timestamp)
        self.values.append(value)

    def __len__(self) -> int:
        return len(self.times)

    def numeric(self) -> tuple[list[datetime], list[float]]:
        """Return the series with missing values removed."""

        times: list[datetime] = []
        values: list[float] = []
        for t, v in zip(self.times, self.values):
            if v is None:
                continue
            times.append(t)
            values.append(v)
        return times, values


def parse_date(value: str | date) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value))
