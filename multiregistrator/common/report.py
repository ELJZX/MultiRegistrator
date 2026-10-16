"""Building the textual part of the graph report (PDF / print).

Free of any GUI dependency so it can be unit tested.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional


def build_report_lines(
    device_name: str,
    period_start: datetime,
    period_end: datetime,
    channels: Iterable[str],
    generated: Optional[datetime] = None,
) -> list[str]:
    """Return the report header.

    * line 1 — the installation (connected device) name;
    * line 2 — period, selected channels and report generation time.
    """

    channel_list = list(channels)
    generated = generated or datetime.now()
    info = (
        f"Период: {period_start:%d.%m.%Y %H:%M:%S} — {period_end:%d.%m.%Y %H:%M:%S}   |   "
        f"Каналы: {', '.join(channel_list) if channel_list else '(все)'}   |   "
        f"Дата формирования: {generated:%d.%m.%Y %H:%M:%S}"
    )
    return [f"Название установки: {device_name}", info]
