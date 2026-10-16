from datetime import datetime

from multiregistrator.common.report import (
    REPORT_SEPARATOR,
    build_report_fields,
    format_report_line,
)

GENERATED = datetime(2026, 10, 14, 12, 30, 0)
START = datetime(2026, 10, 14, 11, 0, 0)
END = datetime(2026, 10, 14, 12, 0, 0)


def test_header_has_installation_and_period():
    header, _footer = build_report_fields(
        "Тестовое устройство", START, END, ["temperature", "relay"], GENERATED
    )
    assert [label for label, _ in header] == ["Название установки", "Период"]
    assert header[0] == ("Название установки", "Тестовое устройство")
    assert header[1][1] == "14.10.2026 11:00:00 — 14.10.2026 12:00:00"


def test_footer_has_channels_and_generation_time():
    _header, footer = build_report_fields(
        "Dev", START, END, ["temperature", "relay"], GENERATED
    )
    assert [label for label, _ in footer] == ["Каналы", "Дата формирования отчета"]
    assert footer[0] == ("Каналы", "temperature, relay")
    assert footer[1] == ("Дата формирования отчета", "14.10.2026 12:30:00")


def test_format_report_line_single_line():
    header, footer = build_report_fields("Dev", START, END, ["a", "b"], GENERATED)
    line = format_report_line(header + footer)
    assert "\n" not in line
    assert line.count(REPORT_SEPARATOR) == 3
    for label in ("Название установки:", "Период:", "Каналы:", "Дата формирования отчета:"):
        assert label in line


def test_without_channels():
    _header, footer = build_report_fields("Dev", START, END, [], GENERATED)
    assert footer[0] == ("Каналы", "(все)")


def test_default_generation_time():
    _header, footer = build_report_fields("Dev", START, END, ["a"])
    assert footer[1][0] == "Дата формирования отчета"
