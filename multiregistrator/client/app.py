"""Entry point for the client application."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from ..common.config import load_client_config, save_client_config
from .ui.main_window import ClientMainWindow


def main(argv: list[str] | None = None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("MultiRegistrator Client")
    app.setOrganizationName("MultiRegistrator")

    config = load_client_config()
    save_client_config(config)

    window = ClientMainWindow(config)
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
