import random

import pytest

from multiregistrator.tools.temperature import TemperatureSource


def test_starts_at_base():
    source = TemperatureSource(base=25.0)
    assert source.value == 25.0


def test_values_stay_within_amplitude():
    source = TemperatureSource(base=20.0, amplitude=3.0, step=1.0, rng=random.Random(1))
    values = [source.next() for _ in range(2000)]
    assert all(17.0 <= value <= 23.0 for value in values)


def test_is_deterministic_with_seed():
    first = TemperatureSource(step=0.5, rng=random.Random(42))
    second = TemperatureSource(step=0.5, rng=random.Random(42))
    assert [first.next() for _ in range(20)] == [second.next() for _ in range(20)]


def test_zero_step_keeps_base():
    source = TemperatureSource(base=30.0, step=0.0)
    assert source.next() == 30.0


def test_rejects_non_positive_amplitude():
    with pytest.raises(ValueError):
        TemperatureSource(amplitude=0.0)


def test_rounds_to_decimals():
    source = TemperatureSource(step=0.123456, decimals=2, rng=random.Random(7))
    value = source.next()
    assert round(value, 2) == value
