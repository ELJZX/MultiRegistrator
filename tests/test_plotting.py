from datetime import datetime, timedelta

import pytest

from multiregistrator.common.plotting import (
    MAX_PERIOD_HOURS,
    PERIOD_MARGIN,
    clamp_period_start,
    max_period_delta,
    with_margin,
)


def test_max_period_delta_is_24h_plus_10_percent():
    assert max_period_delta() == timedelta(hours=24) * 1.1
    assert max_period_delta().total_seconds() == pytest.approx(
        MAX_PERIOD_HOURS * 3600 * PERIOD_MARGIN
    )


def test_clamp_keeps_short_period_unchanged():
    start = datetime(2026, 10, 13, 6, 0, 0)
    end = datetime(2026, 10, 13, 12, 0, 0)
    assert clamp_period_start(start, end) == start


def test_clamp_trims_long_period_keeping_end():
    start = datetime(2026, 10, 13, 0, 0, 0)
    end = start + timedelta(hours=48)
    result = clamp_period_start(start, end)
    assert result == end - timedelta(hours=24) * 1.1
    assert (end - result).total_seconds() == pytest.approx(
        MAX_PERIOD_HOURS * 3600 * PERIOD_MARGIN
    )


def test_clamp_boundary_exactly_max_is_kept():
    start = datetime(2026, 10, 13, 0, 0, 0)
    end = start + max_period_delta()
    assert clamp_period_start(start, end) == start


def test_clamp_swaps_reversed_input():
    start = datetime(2026, 10, 13, 12, 0, 0)
    end = datetime(2026, 10, 13, 6, 0, 0)
    assert clamp_period_start(start, end) == end


def test_with_margin_adds_ten_percent_each_side():
    start = datetime(2026, 10, 13, 10, 0, 0)
    end = datetime(2026, 10, 13, 11, 0, 0)
    padded_start, padded_end = with_margin(start, end, 0.1)
    assert padded_start == start - timedelta(minutes=6)
    assert padded_end == end + timedelta(minutes=6)
