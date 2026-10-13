"""Main window of the client application."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QFormLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ... import __version__
from ...common.config import ClientConfig, load_client_config, save_client_config
from ..api_client import ServerApiClient, ServerApiError
from .connection_dialog import ConnectionDialog
from .graph_window import GraphWindow

ONLINE_COLOR = QColor(0, 150, 0)
OFFLINE_COLOR = QColor(200, 0, 0)
UNKNOWN_COLOR = QColor(120, 120, 120)


class ClientMainWindow(QMainWindow):
    def __init__(self, config: Optional[ClientConfig] = None) -> None:
        super().__init__()
        self.setWindowTitle(f"MultiRegistrator — Клиент {__version__}")
        self.resize(1000, 640)
        self.config = config or load_client_config()
        self.api: Optional[ServerApiClient] = None
        self.devices: list[dict] = []
        self.graph_windows: dict[str, GraphWindow] = {}

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(2000)
        self.refresh_timer.timeout.connect(self._refresh_devices)

        self._build_ui()
        self._build_menu()

    # -- UI -----------------------------------------------------------------
    def _build_ui(self) -> None:
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Сеть"])
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.currentItemChanged.connect(lambda *_: self._show_info())

        self.info = QWidget()
        self.info_layout = QVBoxLayout(self.info)
        self.info_title = QLabel("<b>Общие настройки клиента</b>")
        self.info_form = QFormLayout()
        self.info_layout.addWidget(self.info_title)
        self.info_layout.addLayout(self.info_form)
        self.info_layout.addStretch(1)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.tree)
        splitter.addWidget(self.info)
        splitter.setSizes([280, 720])
        self.setCentralWidget(splitter)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Не подключено")

    def _build_menu(self) -> None:
        self.connect_action = QAction("Подключиться к серверу", self)
        self.connect_action.triggered.connect(self._connect)
        self.disconnect_action = QAction("Отключиться от сервера", self)
        self.disconnect_action.triggered.connect(self._disconnect)
        self.disconnect_action.setEnabled(False)
        settings_action = QAction("Настройка соединения", self)
        settings_action.triggered.connect(self._open_settings)
        exit_action = QAction("Выход", self)
        exit_action.triggered.connect(self.close)

        toolbar = self.addToolBar("Основные")
        toolbar.addAction(self.connect_action)
        toolbar.addAction(self.disconnect_action)
        toolbar.addAction(settings_action)

        network_menu = self.menuBar().addMenu("Сеть")
        network_menu.addAction(self.connect_action)
        network_menu.addAction(self.disconnect_action)

        settings_menu = self.menuBar().addMenu("Настройка")
        settings_menu.addAction(settings_action)

        file_menu = self.menuBar().addMenu("Файл")
        file_menu.addAction(exit_action)

    # -- connection ---------------------------------------------------------
    def _open_settings(self) -> None:
        dialog = ConnectionDialog(self.config, parent=self)
        if dialog.exec():
            self.config.settings = dialog.settings()
            self.config.connections = [
                dialog.combo.itemData(i) for i in range(dialog.combo.count())
            ]
            save_client_config(self.config)

    def autoconnect(self) -> None:
        """Connect using the saved settings (used by the ``--autoconnect`` flag)."""

        self._connect()

    def _connect(self) -> None:
        """Connect to the server from the saved settings (no dialog).

        The server address is preconfigured and can be changed in
        «Настройка → Настройка соединения».
        """

        if self.api is not None:
            return
        settings = self.config.settings

        api = ServerApiClient(settings.server_host, settings.server_port)
        try:
            api.health()
        except ServerApiError as exc:
            api.close()
            QMessageBox.critical(
                self,
                "Ошибка подключения",
                f"{exc}\n\nПроверьте, что сервер запущен и адрес/порт "
                f"({settings.server_host}:{settings.server_port}) заданы верно. "
                f"Изменить можно в меню «Настройка → Настройка соединения».",
            )
            return
        self.api = api
        self.connect_action.setEnabled(False)
        self.disconnect_action.setEnabled(True)
        self.statusBar().showMessage(
            f"Подключено к {settings.server_host}:{settings.server_port}"
        )
        self._refresh_devices()
        self.refresh_timer.start()

    def _disconnect(self) -> None:
        self.refresh_timer.stop()
        for window in list(self.graph_windows.values()):
            window.close()
        self.graph_windows.clear()
        if self.api is not None:
            self.api.close()
            self.api = None
        self.devices = []
        self.tree.clear()
        self.connect_action.setEnabled(True)
        self.disconnect_action.setEnabled(False)
        self.statusBar().showMessage("Не подключено")

    # -- devices ------------------------------------------------------------
    def _refresh_devices(self) -> None:
        if self.api is None:
            return
        try:
            self.devices = self.api.list_devices()
        except ServerApiError as exc:
            self.statusBar().showMessage(f"Ошибка связи: {exc}")
            return
        self._rebuild_tree()

    def _rebuild_tree(self) -> None:
        self.tree.clear()
        network = QTreeWidgetItem(["Сеть"])
        connection = QTreeWidgetItem([self.config.settings.connection_name])
        network.addChild(connection)
        for entry in self.devices:
            config = entry["config"]
            status = entry["status"]
            item = QTreeWidgetItem([config["name"]])
            item.setData(0, Qt.UserRole, config)
            item.setData(0, Qt.UserRole + 1, status)
            item.setForeground(0, ONLINE_COLOR if status.get("online") else OFFLINE_COLOR)
            connection.addChild(item)
        self.tree.addTopLevelItem(network)
        network.setExpanded(True)
        connection.setExpanded(True)

    def _selected_entry(self) -> Optional[dict]:
        item = self.tree.currentItem()
        if item is None or item.data(0, Qt.UserRole) is None:
            return None
        return {"config": item.data(0, Qt.UserRole), "status": item.data(0, Qt.UserRole + 1)}

    def _show_info(self) -> None:
        while self.info_form.rowCount():
            self.info_form.removeRow(0)
        entry = self._selected_entry()
        if entry is None:
            self.info_title.setText("<b>Общие настройки клиента</b>")
            return
        config = entry["config"]
        status = entry["status"]
        self.info_title.setText(f"<b>{config['name']}</b>")
        self.info_form.addRow("IP адрес", QLabel(config["host"]))
        self.info_form.addRow("IP порт", QLabel(str(config["port"])))
        self.info_form.addRow("Modbus ID", QLabel(str(config["device_id"])))
        self.info_form.addRow("Состояние", QLabel("в сети" if status.get("online") else "нет связи"))
        self.info_form.addRow("Задержка, мс", QLabel(f"{status.get('latency_ms', 0):.1f}"))
        self.info_form.addRow("Последний успех", QLabel(str(status.get("last_success") or "—")))
        channels = [r["name"] for r in config.get("registers", [])]
        self.info_form.addRow("Каналы", QLabel(", ".join(channels) if channels else "—"))

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        config = item.data(0, Qt.UserRole)
        if config is None or self.api is None:
            return
        self._open_graph(config)

    def _open_graph(self, config: dict) -> None:
        device_id = config["id"]
        window = self.graph_windows.get(device_id)
        if window is None:
            window = GraphWindow(
                self.api,
                device_id,
                config["name"],
                refresh_ms=self.config.settings.live_refresh_ms,
                parent=None,
            )
            self.graph_windows[device_id] = window
        window.show()
        window.raise_()
        window.activateWindow()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._disconnect()
        super().closeEvent(event)
