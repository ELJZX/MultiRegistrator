"""Automatic channel discovery.

Probes a device's register space and proposes channels so the administrator can
look at the sample values, recognise the sensor and give the channel a proper
name.  Only ``float32`` channels are proposed, because measurements (temperature,
conductivity, ...) are almost always stored as 32-bit floats.  Candidates whose
value is not a sane finite number (unused channels usually answer with ``NaN``)
are filtered out.

The scan is read-only and deliberately conservative -- one two-register request
per address.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from typing import Optional

from ..common.models import DeviceConfig, RegisterConfig, RegisterFunction

WORD_ORDERS = ("little", "big")


@dataclass
class Candidate:
    """A discovered channel and the value it currently reports."""

    register: RegisterConfig
    value: float


def _decode_float32(words: list[int], word_order: str) -> Optional[float]:
    if len(words) < 2:
        return None
    high, low = int(words[0]) & 0xFFFF, int(words[1]) & 0xFFFF
    if word_order == "little":
        high, low = low, high
    try:
        return struct.unpack(">f", struct.pack(">I", (high << 16) | low))[0]
    except struct.error:  # pragma: no cover - defensive
        return None


def _plausible(value: Optional[float], min_abs: float, max_abs: float) -> bool:
    if value is None or math.isnan(value) or math.isinf(value):
        return False
    return min_abs <= abs(value) <= max_abs


def discover_channels(
    reader,
    device: DeviceConfig,
    function: str = RegisterFunction.INPUT.value,
    start: int = 0,
    end: int = 4096,
    min_abs: float = 1e-3,
    max_abs: float = 1e6,
) -> list[Candidate]:
    """Probe ``device`` and return the float32 channels it exposes.

    ``function`` selects holding or input registers.  The scan checks each
    address with a two-register read and keeps the pairs that decode to a
    plausible value.  A found channel consumes the next address as well, so
    adjacent duplicates are skipped.
    """

    function = RegisterFunction(function).value
    if function not in (RegisterFunction.INPUT.value, RegisterFunction.HOLDING.value):
        raise ValueError("discovery supports 'input' and 'holding' registers only")

    candidates: list[Candidate] = []
    address = start
    while address < end:
        words = reader.probe(device, function, address, 2)
        if words is None or len(words) < 2:
            address += 1
            continue

        found: Optional[Candidate] = None
        for order in WORD_ORDERS:
            value = _decode_float32(words, order)
            if _plausible(value, min_abs, max_abs):
                register = RegisterConfig(
                    name=f"канал {address}",
                    address=address,
                    function=function,
                    data_type="float32",
                    word_order=order,
                    scale=1.0,
                )
                found = Candidate(register=register, value=float(value))
                break

        if found is not None:
            candidates.append(found)
            address += 2  # the float already used this address and the next one
        else:
            address += 1

    return candidates
