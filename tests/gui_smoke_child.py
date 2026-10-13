"""Standalone GUI smoke checks.

Run as a child process (see ``test_gui_smoke.py``).  It exercises the widgets
and then calls ``os._exit`` explicitly so the process never reaches the Qt
finalization path that can abort on some PySide6/Python combinations.
"""

from __future__ import annotations

import os
import socket
import sys
import tempfile
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from multiregistrator.client.api_client import ServerApiClient
from multiregistrator.client.ui.channel_dialog import ChannelDialog
from multiregistrator.client.ui.connection_dialog import ConnectionDialog
from multiregistrator.client.ui.graph_window import GraphWindow
from multiregistrator.client.ui.main_window import ClientMainWindow
from multiregistrator.common.config import ClientConfig, ClientSettings, ServerConfig
from multiregistrator.common.models import DeviceConfig, RegisterConfig
from multiregistrator.server.ui.device_dialog import DeviceDialog
from multiregistrator.server.ui.main_window import ServerMainWindow


def server_config() -> ServerConfig:
    return ServerConfig(
        devices=[
            DeviceConfig(
                id="d1",
                name="Tewes-Bis Цех №1",
                host="127.0.0.1",
                registers=[RegisterConfig(name="analogIn", address=1, data_type="float32")],
            )
        ]
    )


CHECKS = []


def check(name):
    def decorator(func):
        CHECKS.append((name, func))
        return func

    return decorator


@check("server window")
def _server_window():
    window = ServerMainWindow(server_config())
    assert window.tree.topLevelItemCount() == 1
    assert window.table.rowCount() == 1
    assert window.stop_action.isEnabled() is False
    assert window._unique_id("d1") == "d1-2"
    assert ServerMainWindow._port_available("127.0.0.1", 0) is True
    window.close()


@check("device dialog")
def _device_dialog():
    dialog = DeviceDialog(server_config().devices[0])
    dialog.name_edit.setText("Renamed")
    rebuilt = dialog._build_device()
    assert rebuilt.name == "Renamed"
    assert rebuilt.registers[0].name == "analogIn"

    empty = DeviceDialog()
    empty.name_edit.setText("")
    empty.host_edit.setText("")
    try:
        empty._build_device()
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


@check("client window")
def _client_window():
    window = ClientMainWindow(ClientConfig(settings=ClientSettings(connection_name="Сервер")))
    assert window.api is None
    assert window.disconnect_action.isEnabled() is False
    window.close()


@check("connection dialog")
def _connection_dialog():
    config = ClientConfig(settings=ClientSettings(server_host="10.0.0.7", server_port=9000))
    dialog = ConnectionDialog(config)
    dialog.host_edit.setText("10.0.0.8")
    dialog.port_spin.setValue(9100)
    settings = dialog.settings()
    assert settings.server_host == "10.0.0.8"
    assert settings.server_port == 9100


@check("channel dialog")
def _channel_dialog():
    dialog = ChannelDialog(["a", "b", "c"], ["a"])
    assert dialog.selected_channels() == ["a"]
    dialog.list.item(1).setCheckState(Qt.Checked)
    assert set(dialog.selected_channels()) == {"a", "b"}


@check("graph window")
def _graph_window():
    import pyqtgraph as pg

    window = GraphWindow(ServerApiClient("127.0.0.1", 1), "d1", "Test")
    assert window.curves == {}
    assert pg.getConfigOption("background") == "w"
    assert window.plot.backgroundBrush().color().name() == "#ffffff"
    window.close()


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@check("server table headers")
def _server_headers():
    from PySide6.QtWidgets import QHeaderView

    window = ServerMainWindow(server_config())
    assert window.table.columnCount() == 7
    assert window.table.horizontalHeader().sectionResizeMode(0) == QHeaderView.ResizeToContents
    assert window.table.horizontalHeader().stretchLastSection() is True
    window.close()


@check("server start/stop buttons")
def _server_start_stop():
    config = server_config()
    config.settings.api_host = "127.0.0.1"
    config.settings.api_port = _free_port()
    config.settings.archive_dir = tempfile.mkdtemp()
    window = ServerMainWindow(config)
    try:
        assert window.stop_action.isEnabled() is False
        window._start_server()
        assert window.start_action.isEnabled() is False
        assert window.stop_action.isEnabled() is True
        assert window.service is not None and window.service.is_running
        assert window.api is not None and window.api.is_running
    finally:
        window._stop_server()
    assert window.start_action.isEnabled() is True
    assert window.stop_action.isEnabled() is False
    window.close()


@check("client connects without dialog")
def _client_connect_without_dialog():
    import multiregistrator.client.ui.main_window as client_mw

    class FakeApi:
        def __init__(self, host, port):
            self.host = host
            self.port = port

        def health(self):
            return {"status": "ok"}

        def list_devices(self):
            return []

        def close(self):
            pass

    original = client_mw.ServerApiClient
    client_mw.ServerApiClient = FakeApi
    try:
        config = ClientConfig(settings=ClientSettings(server_host="127.0.0.1", server_port=9999))
        window = ClientMainWindow(config)
        assert window.disconnect_action.isEnabled() is False
        window._connect()
        assert window.api is not None
        assert window.connect_action.isEnabled() is False
        assert window.disconnect_action.isEnabled() is True
        window.close()
    finally:
        client_mw.ServerApiClient = original


def main() -> int:
    app = QApplication.instance() or QApplication([])
    failures = []
    for name, func in CHECKS:
        try:
            func()
            app.processEvents()
        except Exception:
            failures.append((name, traceback.format_exc()))

    if failures:
        for name, tb in failures:
            print(f"FAILED: {name}\n{tb}")
        print(f"GUI SMOKE FAILED ({len(failures)}/{len(CHECKS)})")
        sys.stdout.flush()
        os._exit(1)

    print(f"GUI SMOKE OK ({len(CHECKS)} checks)")
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
