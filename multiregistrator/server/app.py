"""Entry point for the server application."""

from __future__ import annotations

import argparse
import sys
import time

from ..common.archive import ArchiveReader, ArchiveWriter
from ..common.config import load_server_config, save_server_config
from ..common.models import DeviceStatus
from .api import ApiServer, create_app
from .modbus import ModbusReader
from .service import ServerService


def _build_runtime(config, on_status=None):
    """Create the polling service and the HTTP API from a config."""

    settings = config.settings
    archive_dir = settings.resolve_archive_dir()
    archive_dir.mkdir(parents=True, exist_ok=True)
    reader = ModbusReader(inter_request_delay=settings.inter_request_delay)
    writer = ArchiveWriter(archive_dir)
    service = ServerService(reader, writer, devices=config.devices, on_status=on_status)
    app = create_app(service, ArchiveReader(archive_dir))
    api = ApiServer(app, settings.api_host, settings.api_port)
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
    ok = _wait_for_api(settings.api_host, settings.api_port)
    print(
        f"API {'OK' if ok else 'FAILED'} at {settings.api_host}:{settings.api_port}\n"
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
    ok = _wait_for_api(settings.api_host, settings.api_port)
    print("MultiRegistrator server (headless)")
    print(f"  archive : {archive_dir}")
    print(f"  API     : http://{settings.api_host}:{settings.api_port} [{'OK' if ok else 'FAILED'}]")
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

    from PySide6.QtWidgets import QApplication

    from .ui.main_window import ServerMainWindow

    app = QApplication([argv[0], *qt_args])
    app.setApplicationName("MultiRegistrator Server")
    app.setOrganizationName("MultiRegistrator")

    window = ServerMainWindow(config)
    window.show()
    if args.autostart:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, window.autostart)
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
