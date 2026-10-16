from datetime import datetime

from multiregistrator.common.report import (
    REPORT_SEPARATOR,
    build_report_fields,
    format_report_line,
)

GENERATED = datetime(2026, 10, 14, 12, 30, 0)
START = datetime(2026, 10, 14, 11, 0, 0)
END = datetime(2026, 10, 14, 12, 0, 0)


def test_fields_have_expected_labels_and_order():
    fields = build_report_fields("Тестовое устройство", START, END, ["temperature", "relay"], GENERATED)
    assert [label for label, _ in fields] == [
        "Название установки",
        "Период",
        "Каналы",
        "Дата формирования",
    ]
    assert fields[0] == ("Название установки", "Тестовое устройство")
    assert fields[1][1] == "14.10.2026 11:00:00 — 14.10.2026 12:00:00"
    assert fields[2] == ("Каналы", "temperature, relay")
    assert fields[3] == ("Дата формирования", "14.10.2026 12:30:00")


def test_format_report_line_is_single_line_with_all_fields():
    fields = build_report_fields("Dev", START, END, ["a", "b"], GENERATED)
    line = format_report_line(fields)
    assert "\n" not in line
    assert line.count(REPORT_SEPARATOR) == 3
    for label in ("Название установки", "Период", "Каналы", "Дата формирования"):
        assert f"{label}:" in line


def test_without_channels():
    fields = build_report_fields("Dev", START, END, [], GENERATED)
    assert fields[2] == ("Каналы", "(все)")


def test_default_generation_time():
    fields = build_report_fields("Dev", START, END, ["a"])
    assert fields[3][0] == "Дата формирования"
