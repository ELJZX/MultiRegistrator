"""Smoke tests for the Qt widgets (run headless via the offscreen platform)."""

import pytest

from multiregistrator.common.config import ClientConfig, ClientSettings, ServerConfig
from multiregistrator.common.models import DeviceConfig, RegisterConfig


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def _server_config():
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


def test_server_window_constructs(qapp):
    from multiregistrator.server.ui.main_window import ServerMainWindow

    window = ServerMainWindow(_server_config())
    assert window.tree.topLevelItemCount() == 1
    assert window.table.rowCount() == 1
    assert window.stop_action.isEnabled() is False


def test_server_unique_id(qapp):
    from multiregistrator.server.ui.main_window import ServerMainWindow

    window = ServerMainWindow(_server_config())
    assert window._unique_id("new") == "new"
    assert window._unique_id("d1") == "d1-2"


def test_port_available_helper(qapp):
    from multiregistrator.server.ui.main_window import ServerMainWindow

    assert ServerMainWindow._port_available("127.0.0.1", 0) is True


def test_device_dialog_roundtrip(qapp):
    from multiregistrator.server.ui.device_dialog import DeviceDialog

    device = _server_config().devices[0]
    dialog = DeviceDialog(device)
    dialog.name_edit.setText("Renamed")
    rebuilt = dialog._build_device()
    assert rebuilt.name == "Renamed"
    assert rebuilt.registers[0].name == "analogIn"
    assert rebuilt.registers[0].data_type == "float32"


def test_device_dialog_validation(qapp):
    from multiregistrator.server.ui.device_dialog import DeviceDialog

    dialog = DeviceDialog()
    dialog.name_edit.setText("")
    dialog.host_edit.setText("")
    with pytest.raises(ValueError):
        dialog._build_device()


def test_client_window_constructs(qapp):
    from multiregistrator.client.ui.main_window import ClientMainWindow

    config = ClientConfig(settings=ClientSettings(connection_name="Сервер"))
    window = ClientMainWindow(config)
    assert window.api is None
    assert window.disconnect_action.isEnabled() is False


def test_connection_dialog_returns_settings(qapp):
    from multiregistrator.client.ui.connection_dialog import ConnectionDialog

    config = ClientConfig(settings=ClientSettings(server_host="10.0.0.7", server_port=9000))
    dialog = ConnectionDialog(config)
    dialog.host_edit.setText("10.0.0.8")
    dialog.port_spin.setValue(9100)
    settings = dialog.settings()
    assert settings.server_host == "10.0.0.8"
    assert settings.server_port == 9100


def test_channel_dialog_selection(qapp):
    from PySide6.QtCore import Qt

    from multiregistrator.client.ui.channel_dialog import ChannelDialog

    dialog = ChannelDialog(["a", "b", "c"], ["a"])
    assert dialog.selected_channels() == ["a"]
    dialog.list.item(1).setCheckState(Qt.Checked)
    assert set(dialog.selected_channels()) == {"a", "b"}


def test_graph_window_constructs_without_server(qapp):
    from multiregistrator.client.api_client import ServerApiClient
    from multiregistrator.client.ui.graph_window import GraphWindow

    window = GraphWindow(ServerApiClient("127.0.0.1", 1), "d1", "Test")
    assert window.curves == {}
    window.close()
