from datetime import datetime

from multiregistrator.common.report import REPORT_TITLE, build_report_lines


def test_build_report_lines_contains_all_fields():
    generated = datetime(2026, 10, 14, 12, 30, 0)
    lines = build_report_lines(
        "Тewes-Bis Цех №1",
        datetime(2026, 10, 14, 11, 0, 0),
        datetime(2026, 10, 14, 12, 0, 0),
        ["temperature", "relay"],
        generated=generated,
    )
    assert lines[0] == f"{REPORT_TITLE}: Тewes-Bis Цех №1"
    assert lines[1] == "Период: 14.10.2026 11:00:00 — 14.10.2026 12:00:00"
    assert lines[2] == "Каналы: temperature, relay"
    assert lines[3] == "Дата формирования: 14.10.2026 12:30:00"


def test_build_report_lines_without_channels():
    lines = build_report_lines(
        "Dev",
        datetime(2026, 1, 1, 0, 0, 0),
        datetime(2026, 1, 1, 1, 0, 0),
        [],
        generated=datetime(2026, 1, 1, 2, 0, 0),
    )
    assert lines[2] == "Каналы: (все)"


def test_build_report_lines_default_generation_time():
    lines = build_report_lines(
        "Dev", datetime(2026, 1, 1), datetime(2026, 1, 2), ["a"]
    )
    assert lines[3].startswith("Дата формирования: ")
