"""Entry point for the server application."""

from __future__ import annotations

import argparse
import os
import sys
import time

from ..common.archive import ArchiveReader, ArchiveWriter
from ..common.config import load_server_config, save_server_config
from ..common.logging_setup import get_logger, setup_logging
from ..common.models import DeviceStatus
from .api import ApiServer, create_app, resolve_bind_host
from .modbus import ModbusReader
from .service import ServerService


def _ensure_console_streams() -> None:
    """Guarantee ``sys.stdout``/``sys.stderr`` exist.

    In a windowed GUI (``pythonw`` or a PyInstaller ``--windowed`` build) the
    standard streams are ``None``.  Libraries that call ``isatty()`` on them
    (for example uvicorn's coloured log formatter) then crash.  Pointing the
    missing streams at the null device keeps everything working.
    """

    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def _build_runtime(config, on_status=None):
    """Create the polling service and the HTTP API from a config."""

    settings = config.settings
    archive_dir = settings.resolve_archive_dir()
    archive_dir.mkdir(parents=True, exist_ok=True)
    reader = ModbusReader(inter_request_delay=settings.inter_request_delay)
    writer = ArchiveWriter(archive_dir)
    service = ServerService(reader, writer, devices=config.devices, on_status=on_status)
    app = create_app(service, ArchiveReader(archive_dir))
    api_host = resolve_bind_host(settings.api_host, settings.api_port) or settings.api_host
    api = ApiServer(app, api_host, settings.api_port)
    return service, api, archive_dir


def _wait_for_api(host: str, port: int, timeout: float = 15.0) -> bool:
    import requests

    target = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            response = requests.get(f"http://{target}:{port}/api/health", timeout=1.0)
            if response.status_code == 200:
                return True
        except requests.RequestException:
            time.sleep(0.2)
    return False


def _run_check(config) -> int:
    settings = config.settings
    service, api, archive_dir = _build_runtime(config)
    service.start()
    api.start()
    ok = _wait_for_api(api.host, api.port)
    print(
        f"API {'OK' if ok else 'FAILED'} at {api.host}:{api.port}\n"
        f"archive: {archive_dir}\n"
        f"devices: {len(config.devices)}"
    )
    api.stop()
    service.stop()
    return 0 if ok else 2


def _run_headless(config) -> int:
    settings = config.settings

    def on_status(status: DeviceStatus) -> None:
        state = "ONLINE " if status.online else "OFFLINE"
        print(f"[{state}] {status.device_id}: {status.values or status.last_error}", flush=True)

    service, api, archive_dir = _build_runtime(config, on_status=on_status)
    service.start()
    api.start()
    ok = _wait_for_api(api.host, api.port)
    print("MultiRegistrator server (headless)")
    print(f"  archive : {archive_dir}")
    print(f"  API     : http://{api.host}:{api.port} [{'OK' if ok else 'FAILED'}]")
    print("  Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        api.stop()
        service.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    _ensure_console_streams()
    log_path = setup_logging("server", console=True)
    get_logger("app").info("Запуск сервера MultiRegistrator. Лог-файл: %s", log_path)
    argv = list(sys.argv if argv is None else argv)
    parser = argparse.ArgumentParser(description="MultiRegistrator server")
    parser.add_argument("--autostart", action="store_true", help="запустить сервер сразу")
    parser.add_argument("--headless", action="store_true", help="без GUI (консольный режим)")
    parser.add_argument("--check", action="store_true", help="проверить API и выйти")
    args, qt_args = parser.parse_known_args(argv[1:])

    config = load_server_config()
    save_server_config(config)  # create the file on first run

    if args.check:
        return _run_check(config)
    if args.headless:
        return _run_headless(config)

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    from ..common.theme import apply_light_theme
    from .ui.main_window import ServerMainWindow

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication([argv[0], *qt_args])
    app.setApplicationName("MultiRegistrator Server")
    app.setOrganizationName("MultiRegistrator")
    apply_light_theme(app)

    window = ServerMainWindow(config)
    window.showMaximized()
    if args.autostart:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, window.autostart)
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
