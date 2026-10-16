"""Building the textual part of the graph report (PDF / print).

The report has a header line above the graph and a footer line below it:

    header:  Название установки: ...   |   Период: ...
    footer:  Каналы: ...   |   Дата формирования отчета: ...

Labels are shown in bold.  Kept free of any GUI dependency so it can be unit
tested.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

#: Separator used between the fields of a header/footer line.
REPORT_SEPARATOR = "   |   "

Fields = list[tuple[str, str]]


def build_report_fields(
    device_name: str,
    period_start: datetime,
    period_end: datetime,
    channels: Iterable[str],
    generated: Optional[datetime] = None,
) -> tuple[Fields, Fields]:
    """Return ``(header, footer)`` field pairs for the report.

    The header (above the graph) holds the installation name and the period;
    the footer (below the graph) holds the channels and the generation time.
    """

    channel_list = list(channels)
    generated = generated or datetime.now()
    header: Fields = [
        ("Название установки", device_name),
        ("Период", f"{period_start:%d.%m.%Y %H:%M:%S} — {period_end:%d.%m.%Y %H:%M:%S}"),
    ]
    footer: Fields = [
        ("Каналы", ", ".join(channel_list) if channel_list else "(все)"),
        ("Дата формирования отчета", f"{generated:%d.%m.%Y %H:%M:%S}"),
    ]
    return header, footer


def format_report_line(fields: Iterable[tuple[str, str]], separator: str = REPORT_SEPARATOR) -> str:
    """Plain-text form of a field line (for logs / label fallbacks)."""

    return separator.join(f"{label}: {value}" for label, value in fields)
