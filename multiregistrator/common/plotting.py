"""Helpers for plotting time series.

Kept free of any GUI dependency so they can be unit tested directly (the Qt
widgets import from here).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Union

#: Maximum span shown on the time axis, before the safety margin is applied.
MAX_PERIOD_HOURS = 24.0

#: Extra headroom (10%) so the user can still shrink/zoom the graph a little.
PERIOD_MARGIN = 1.1


def max_period_delta(
    max_hours: float = MAX_PERIOD_HOURS, margin: float = PERIOD_MARGIN
) -> timedelta:
    """The maximum time window: ``max_hours`` plus the margin (24h * 1.1)."""

    return timedelta(hours=float(max_hours)) * float(margin)


def clamp_period_start(
    start: datetime,
    end: datetime,
    max_hours: float = MAX_PERIOD_HOURS,
    margin: float = PERIOD_MARGIN,
) -> datetime:
    """Return the start of the visible window for the period ``[start, end]``.

    If the selected period is longer than :func:`max_period_delta` (24h + 10%)
    the window is trimmed so that its most recent part is shown, keeping
    ``end`` fixed.  For shorter periods the original ``start`` is returned.
    """

    if end < start:
        start, end = end, start
    limit = max_period_delta(max_hours, margin)
    if end - start > limit:
        return end - limit
    return start


def axis_tick_text(timestamp: Union[int, float], spacing_seconds: float) -> str:
    """Label for the time axis: time on top, date on the line below.

    Seconds are included when the ticks are dense (``spacing < 60``).  The date
    is always shown, and for ranges longer than a day the time is shown too --
    i.e. every label carries both the time and the date.
    """

    try:
        moment = datetime.fromtimestamp(float(timestamp))
    except (OverflowError, OSError, ValueError):
        return ""

    if spacing_seconds < 60:
        time_text = moment.strftime("%H:%M:%S")
    else:
        time_text = moment.strftime("%H:%M")
    return f"{time_text}\n{moment:%d.%m.%Y}"


def with_margin(
    start: datetime, end: datetime, margin: float = 0.1
) -> tuple[datetime, datetime]:
    """Grow ``[start, end]`` by ``margin`` on both sides (for zoom headroom)."""

    if end < start:
        start, end = end, start
    pad = (end - start) * float(margin)
    return start - pad, end + pad
