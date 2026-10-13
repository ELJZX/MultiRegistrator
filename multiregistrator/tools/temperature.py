"""A tiny random-walk source used by the test device to fake a temperature."""

from __future__ import annotations

import random
from typing import Optional


class TemperatureSource:
    """Produces plausible, smoothly changing values around a base point.

    The value performs a bounded random walk and is gently pulled back to
    ``base`` so it never drifts away, which makes the plotted graph look like
    a real (but noisy) temperature sensor.
    """

    def __init__(
        self,
        base: float = 25.0,
        amplitude: float = 5.0,
        step: float = 0.4,
        drift: float = 0.05,
        low: float = -50.0,
        high: float = 150.0,
        decimals: int = 2,
        rng: Optional[random.Random] = None,
    ) -> None:
        if amplitude <= 0:
            raise ValueError("amplitude must be positive")
        self.base = float(base)
        self.amplitude = float(amplitude)
        self.step = max(0.0, float(step))
        self.drift = max(0.0, float(drift))
        self.low = float(low)
        self.high = float(high)
        self.decimals = int(decimals)
        self._rng = rng or random.Random()
        self.value = self.base

    def next(self) -> float:
        self.value += self._rng.uniform(-self.step, self.step)
        self.value += (self.base - self.value) * self.drift
        lower = max(self.low, self.base - self.amplitude)
        upper = min(self.high, self.base + self.amplitude)
        self.value = max(lower, min(upper, self.value))
        return round(self.value, self.decimals)
