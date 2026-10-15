"""Entry point for the client application."""

from __future__ import annotations

import argparse
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from ..common.config import load_client_config, save_client_config
from ..common.logging_setup import get_logger, setup_logging
from ..common.theme import apply_light_theme
from .ui.main_window import ClientMainWindow


def _enable_high_dpi_scaling() -> None:
    """Honour the exact Windows display scaling (e.g. 125%, 150%)."""

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    parser = argparse.ArgumentParser(description="MultiRegistrator client")
    parser.add_argument("--autoconnect", action="store_true", help="подключиться к серверу сразу")
    parser.add_argument("--server", help="адрес сервера, например 127.0.0.1:8120")
    args, qt_args = parser.parse_known_args(argv[1:])

    log_path = setup_logging("client")
    get_logger("app").info("Запуск клиента MultiRegistrator. Лог-файл: %s", log_path)

    _enable_high_dpi_scaling()
    app = QApplication([argv[0], *qt_args])
    app.setApplicationName("MultiRegistrator Client")
    app.setOrganizationName("MultiRegistrator")
    apply_light_theme(app)

    config = load_client_config()
    if args.server:
        host, _, port = args.server.partition(":")
        config.settings.server_host = host or config.settings.server_host
        if port:
            config.settings.server_port = int(port)
    save_client_config(config)

    window = ClientMainWindow(config)
    window.showMaximized()
    if args.autoconnect:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, window.autoconnect)
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
