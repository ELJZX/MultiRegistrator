"""Entry point for the server application."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from ..common.config import load_server_config, save_server_config
from .ui.main_window import ServerMainWindow


def main(argv: list[str] | None = None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("MultiRegistrator Server")
    app.setOrganizationName("MultiRegistrator")

    config = load_server_config()
    save_server_config(config)  # create the file on first run

    window = ServerMainWindow(config)
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
