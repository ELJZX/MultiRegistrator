"""Building the textual part of the graph report (PDF / print).

The report header is a single line with bold labels:

    Название установки: ...   |   Период: ...   |   Каналы: ...   |   Дата формирования: ...

Kept free of any GUI dependency so it can be unit tested.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

#: Separator used between the fields of the header line.
REPORT_SEPARATOR = "   |   "


def build_report_fields(
    device_name: str,
    period_start: datetime,
    period_end: datetime,
    channels: Iterable[str],
    generated: Optional[datetime] = None,
) -> list[tuple[str, str]]:
    """Return the report header as ``(label, value)`` pairs."""

    channel_list = list(channels)
    generated = generated or datetime.now()
    return [
        ("Название установки", device_name),
        ("Период", f"{period_start:%d.%m.%Y %H:%M:%S} — {period_end:%d.%m.%Y %H:%M:%S}"),
        ("Каналы", ", ".join(channel_list) if channel_list else "(все)"),
        ("Дата формирования", f"{generated:%d.%m.%Y %H:%M:%S}"),
    ]


def format_report_line(
    fields: Iterable[tuple[str, str]], separator: str = REPORT_SEPARATOR
) -> str:
    """Plain-text form of the header (for logs / label fallbacks)."""

    return separator.join(f"{label}: {value}" for label, value in fields)
