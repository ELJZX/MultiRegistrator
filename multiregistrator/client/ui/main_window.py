"""Main window of the client application (single window, stacked pages)."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QFormLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
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
from .graph_window import GraphView

ONLINE_COLOR = QColor(0, 150, 0)
OFFLINE_COLOR = QColor(200, 0, 0)

TREE_STYLE = "QTreeView::item:selected { background: #cce8ff; color: #000; }"


class ClientMainWindow(QMainWindow):
    def __init__(self, config: Optional[ClientConfig] = None) -> None:
        super().__init__()
        self.setWindowTitle(f"MultiRegistrator — Клиент {__version__}")
        self.resize(1040, 620)
        self.config = config or load_client_config()
        self.api: Optional[ServerApiClient] = None
        self.devices: list[dict] = []
        self._selected_id: Optional[str] = None

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(2000)
        self.refresh_timer.timeout.connect(self._refresh_devices)

        self._build_ui()
        self._build_toolbar()

    # -- UI -----------------------------------------------------------------
    def _build_ui(self) -> None:
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_list_page())

        self.graph_view = GraphView(refresh_ms=self.config.settings.live_refresh_ms)
        self.stack.addWidget(self.graph_view)

        self.setCentralWidget(self.stack)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Не подключено")

    def _build_list_page(self) -> QWidget:
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Устройства"])
        self.tree.setRootIsDecorated(False)
        self.tree.setStyleSheet(TREE_STYLE)
        self.tree.currentItemChanged.connect(lambda *_: self._show_info())

        self.info = QWidget()
        self.info_layout = QVBoxLayout(self.info)
        self.info_title = QLabel("<b>Устройства</b>")
        self.info_form = QFormLayout()
        self.info_connect_button = QPushButton("Подключиться")
        self.info_connect_button.clicked.connect(self._open_selected_device)
        self.info_connect_button.setVisible(False)
        self.info_layout.addWidget(self.info_title)
        self.info_layout.addLayout(self.info_form)
        self.info_layout.addWidget(self.info_connect_button)
        self.info_layout.addStretch(1)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.tree)
        splitter.addWidget(self.info)
        splitter.setSizes([280, 760])
        return splitter

    def _build_toolbar(self) -> None:
        self.connect_action = QAction("Подключиться к серверу", self)
        self.connect_action.triggered.connect(self._connect)
        self.disconnect_action = QAction("Отключиться от сервера", self)
        self.disconnect_action.triggered.connect(self._disconnect)
        self.disconnect_action.setEnabled(False)
        self.settings_action = QAction("Настройка соединения", self)
        self.settings_action.triggered.connect(self._open_settings)
        self.back_action = QAction("Назад к списку устройств", self)
        self.back_action.triggered.connect(self._show_list)
        self.back_action.setVisible(False)
        self.back_action.setEnabled(False)

        # A single row of buttons (no duplicated menu entries).
        self.toolbar = self.addToolBar("Панель")
        self.toolbar.setMovable(False)
        self.toolbar.addAction(self.connect_action)
        self.toolbar.addAction(self.disconnect_action)
        self.toolbar.addAction(self.settings_action)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.back_action)

        # No menu bar: the app is closed/minimised with the window buttons.
        self.menuBar().setVisible(False)

    def _set_graph_toolbar(self, on_graph: bool) -> None:
        """On the graph page keep only the single 'back' button."""

        for action in (self.connect_action, self.disconnect_action, self.settings_action):
            action.setVisible(not on_graph)
        self.back_action.setVisible(on_graph)
        self.back_action.setEnabled(on_graph)

    # -- pages --------------------------------------------------------------
    def _show_graph(self, config: dict) -> None:
        self.graph_view.set_device(self.api, config["id"], config["name"])
        self.stack.setCurrentWidget(self.graph_view)
        self._set_graph_toolbar(True)

    def _show_list(self) -> None:
        self.graph_view.stop()
        self.stack.setCurrentIndex(0)
        self._set_graph_toolbar(False)

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
        """Connect to the server from the saved settings (no dialog)."""

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
                f"Изменить можно в меню «Настройка соединения».",
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
        self._show_list()
        self.graph_view.set_device(None, "", "")
        if self.api is not None:
            self.api.close()
            self.api = None
        self.devices = []
        self._selected_id = None
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
        selected_item: Optional[QTreeWidgetItem] = None
        for entry in self.devices:
            config = entry["config"]
            status = entry["status"]
            item = QTreeWidgetItem([config["name"]])
            item.setData(0, Qt.UserRole, config)
            item.setData(0, Qt.UserRole + 1, status)
            item.setForeground(0, ONLINE_COLOR if status.get("online") else OFFLINE_COLOR)
            self.tree.addTopLevelItem(item)
            if config["id"] == self._selected_id:
                selected_item = item
        if selected_item is not None:
            self.tree.setCurrentItem(selected_item)

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
            self._selected_id = None
            self.info_title.setText("<b>Устройства</b>")
            self.info_connect_button.setVisible(False)
            return

        config = entry["config"]
        status = entry["status"]
        self._selected_id = config["id"]
        self.info_title.setText(f"<b>{config['name']}</b>")
        self.info_form.addRow("IP адрес", QLabel(config["host"]))
        self.info_form.addRow("IP порт", QLabel(str(config["port"])))
        self.info_form.addRow("Состояние", QLabel("в сети" if status.get("online") else "нет связи"))
        channels = [r["name"] for r in config.get("registers", [])]
        availability = status.get("channel_available", {})
        available = [c for c in channels if availability.get(c, True)]
        unavailable = [c for c in channels if c not in available]
        self.info_form.addRow("Каналы", QLabel(", ".join(available) if available else "—"))
        if unavailable:
            self.info_form.addRow("Недоступны", QLabel(", ".join(unavailable)))
        self.info_connect_button.setVisible(True)

    def _open_selected_device(self) -> None:
        entry = self._selected_entry()
        if entry is None or self.api is None:
            return
        self._show_graph(entry["config"])

    def closeEvent(self, event) -> None:  # noqa: N802
        self._disconnect()
        super().closeEvent(event)
