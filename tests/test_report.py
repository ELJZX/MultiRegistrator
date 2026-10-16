from datetime import datetime

from multiregistrator.common.report import build_report_lines


def test_first_line_is_installation_name():
    lines = build_report_lines(
        "Тестовое устройство",
        datetime(2026, 10, 14, 11, 0, 0),
        datetime(2026, 10, 14, 12, 0, 0),
        ["temperature", "relay"],
        generated=datetime(2026, 10, 14, 12, 30, 0),
    )
    assert len(lines) == 2
    assert lines[0] == "Название установки: Тестовое устройство"


def test_second_line_has_period_channels_and_time():
    lines = build_report_lines(
        "Dev",
        datetime(2026, 10, 14, 11, 0, 0),
        datetime(2026, 10, 14, 12, 0, 0),
        ["temperature", "relay"],
        generated=datetime(2026, 10, 14, 12, 30, 0),
    )
    info = lines[1]
    assert "Период: 14.10.2026 11:00:00 — 14.10.2026 12:00:00" in info
    assert "Каналы: temperature, relay" in info
    assert "Дата формирования: 14.10.2026 12:30:00" in info


def test_no_title_prefix():
    lines = build_report_lines(
        "Dev", datetime(2026, 1, 1), datetime(2026, 1, 2), ["a"]
    )
    assert not lines[0].startswith("MultiRegistrator")


def test_without_channels():
    lines = build_report_lines(
        "Dev", datetime(2026, 1, 1), datetime(2026, 1, 2), []
    )
    assert "Каналы: (все)" in lines[1]


def test_default_generation_time():
    lines = build_report_lines("Dev", datetime(2026, 1, 1), datetime(2026, 1, 2), ["a"])
    assert "Дата формирования: " in lines[1]
