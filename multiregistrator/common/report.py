"""Building the textual part of the graph report (PDF / print).

Free of any GUI dependency so it can be unit tested.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

REPORT_TITLE = "MultiRegistrator — график"


def build_report_lines(
    device_name: str,
    period_start: datetime,
    period_end: datetime,
    channels: Iterable[str],
    generated: Optional[datetime] = None,
) -> list[str]:
    """Return the header lines printed above the graph in the report."""

    channel_list = list(channels)
    generated = generated or datetime.now()
    return [
        f"{REPORT_TITLE}: {device_name}",
        f"Период: {period_start:%d.%m.%Y %H:%M:%S} — {period_end:%d.%m.%Y %H:%M:%S}",
        f"Каналы: {', '.join(channel_list) if channel_list else '(все)'}",
        f"Дата формирования: {generated:%d.%m.%Y %H:%M:%S}",
    ]
