"""Main window of the server application."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ... import __version__
from ...common.config import ServerConfig, load_server_config, save_server_config
from ...common.database import attach_database_logging, build_storage
from ...common.models import DeviceConfig, DeviceStatus
from ..api import ApiServer, create_app, is_port_available, resolve_bind_host
from ..modbus import ModbusReader
from ..service import ServerService
from .device_dialog import DeviceDialog
from .settings_dialog import ServerSettingsDialog

ONLINE_COLOR = QColor(0, 150, 0)
OFFLINE_COLOR = QColor(200, 0, 0)
UNKNOWN_COLOR = QColor(120, 120, 120)

DEVICE_COLUMNS = [
    "Имя узла",
    "IP адрес",
    "Порт",
    "Состояние",
    "Задержка, мс",
    "Последний успех",
    "Ошибка",
]


class StatusBridge(QObject):
    """Thread-safe bridge used to marshal service callbacks into Qt."""

    statusChanged = Signal(object)
    message = Signal(str)


class ServerMainWindow(QMainWindow):
    def __init__(self, config: Optional[ServerConfig] = None) -> None:
        super().__init__()
        self.setWindowTitle(f"MultiRegistrator — Сервер {__version__}")
        self.resize(1100, 700)
        self.config = config or load_server_config()
        self.service: Optional[ServerService] = None
        self.api: Optional[ApiServer] = None
        self._statuses: dict[str, DeviceStatus] = {}
        self._device_map: dict[str, DeviceConfig] = {}
        self.bridge = StatusBridge()
        self.bridge.statusChanged.connect(self._on_status)
        self.bridge.message.connect(self._log)

        self._build_ui()
        self._build_menu()
        self._refresh_devices()

    # -- UI -----------------------------------------------------------------
    def _build_ui(self) -> None:
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Сеть"])
        self.tree.itemDoubleClicked.connect(self._on_tree_double_clicked)
        self.tree.currentItemChanged.connect(lambda *_: self._update_values())

        self.table = QTableWidget(0, len(DEVICE_COLUMNS))
        self.table.setHorizontalHeaderLabels(DEVICE_COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.itemSelectionChanged.connect(lambda: self._update_values())
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        header.setMinimumSectionSize(90)
        self.table.setTextElideMode(Qt.ElideNone)

        self.values_table = QTableWidget(0, 3)
        self.values_table.setHorizontalHeaderLabels(["Канал", "Значение", "Состояние"])
        self.values_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        values_header = self.values_table.horizontalHeader()
        values_header.setSectionResizeMode(QHeaderView.ResizeToContents)
        values_header.setStretchLastSection(True)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)

        right = QSplitter(Qt.Vertical)
        right.addWidget(self.table)
        right.addWidget(self.values_table)
        right.addWidget(self.log)
        right.setSizes([300, 220, 160])

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.tree)
        splitter.addWidget(right)
        splitter.setSizes([260, 840])
        self.setCentralWidget(splitter)
        self.setStatusBar(QStatusBar())

    def _build_menu(self) -> None:
        self.start_action = QAction("Запустить сервер", self)
        self.start_action.triggered.connect(self._start_server)
        self.stop_action = QAction("Остановить сервер", self)
        self.stop_action.triggered.connect(self._stop_server)
        self.stop_action.setEnabled(False)

        add_action = QAction("Добавить устройство", self)
        add_action.triggered.connect(self._add_device)
        edit_action = QAction("Изменить устройство", self)
        edit_action.triggered.connect(self._edit_device)
        remove_action = QAction("Удалить устройство", self)
        remove_action.triggered.connect(self._remove_device)
        settings_action = QAction("Настройки сервера", self)
        settings_action.triggered.connect(self._open_settings)

        # A single row of buttons (no duplicated menu entries).
        toolbar = self.addToolBar("Панель")
        toolbar.setMovable(False)
        toolbar.addAction(self.start_action)
        toolbar.addAction(self.stop_action)
        toolbar.addSeparator()
        toolbar.addAction(add_action)
        toolbar.addAction(edit_action)
        toolbar.addAction(remove_action)
        toolbar.addSeparator()
        toolbar.addAction(settings_action)

        # No menu bar: the app is closed/minimised with the window buttons.
        self.menuBar().setVisible(False)

    # -- device list --------------------------------------------------------
    def _refresh_devices(self) -> None:
        self._device_map = {device.id: device for device in self.config.devices}
        self.tree.clear()
        # Flat list: only the configured devices (no "Сеть" / "Сервер" nodes).
        for device in self.config.devices:
            item = QTreeWidgetItem([device.name])
            item.setData(0, Qt.UserRole, device.id)
            self.tree.addTopLevelItem(item)

        self.table.setRowCount(len(self.config.devices))
        for row, device in enumerate(self.config.devices):
            self.table.setItem(row, 0, QTableWidgetItem(device.name))
            self.table.setItem(row, 1, QTableWidgetItem(device.host))
            self.table.setItem(row, 2, QTableWidgetItem(str(device.port)))
            for column in range(3, len(DEVICE_COLUMNS)):
                if self.table.item(row, column) is None:
                    self.table.setItem(row, column, QTableWidgetItem(""))
        self._refresh_colors()

    def _refresh_colors(self) -> None:
        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            device_id = item.data(0, Qt.UserRole)
            status = self._statuses.get(device_id)
            device = self._device_by_id(device_id)
            if status is not None and status.online:
                color = ONLINE_COLOR
            elif status is not None:
                color = OFFLINE_COLOR
            elif device is not None and not device.enabled:
                color = UNKNOWN_COLOR
            else:
                color = UNKNOWN_COLOR
            item.setForeground(0, color)
        self._update_table()

    def _device_by_id(self, device_id: str) -> Optional[DeviceConfig]:
        return self._device_map.get(device_id)

    def _update_table(self) -> None:
        for row, device in enumerate(self.config.devices):
            status = self._statuses.get(device.id)
            if status is None:
                state = "не опрошен"
                latency = ""
                success = ""
                error = ""
            else:
                state = "в сети" if status.online else "нет связи"
                latency = f"{status.latency_ms:.1f}"
                success = status.last_success.strftime("%Y-%m-%d %H:%M:%S") if status.last_success else ""
                error = status.last_error
            self._set_cell(row, 3, state, ONLINE_COLOR if status and status.online else (OFFLINE_COLOR if status else UNKNOWN_COLOR))
            self._set_cell(row, 4, latency)
            self._set_cell(row, 5, success)
            self._set_cell(row, 6, error)

    def _set_cell(self, row: int, column: int, text: str, color: Optional[QColor] = None) -> None:
        item = self.table.item(row, column)
        if item is None:
            item = QTableWidgetItem()
            self.table.setItem(row, column, item)
        item.setText(text)
        if color is not None:
            item.setForeground(color)

    def _selected_device_id(self) -> Optional[str]:
        item = self.tree.currentItem()
        if item is not None:
            device_id = item.data(0, Qt.UserRole)
            if device_id is not None:
                return device_id
        row = self.table.currentRow()
        if 0 <= row < len(self.config.devices):
            return self.config.devices[row].id
        return None

    def _update_values(self) -> None:
        device_id = self._selected_device_id()
        device = self._device_by_id(device_id) if device_id else None
        status = self._statuses.get(device_id) if device_id else None
        channels = device.channel_names if device is not None else []
        values = status.values if status else {}
        availability = status.channel_available if status else {}

        self.values_table.setRowCount(len(channels))
        for row, channel in enumerate(channels):
            value = values.get(channel)
            known = availability.get(channel)
            if known is False:
                state = "нет данных"
                color = OFFLINE_COLOR
            elif value is None:
                state = "—"
                color = UNKNOWN_COLOR
            else:
                state = "ок"
                color = ONLINE_COLOR
            name_item = QTableWidgetItem(channel)
            self.values_table.setItem(row, 0, name_item)
            self.values_table.setItem(
                row, 1, QTableWidgetItem("" if value is None else f"{value:.6g}")
            )
            state_item = QTableWidgetItem(state)
            state_item.setForeground(color)
            self.values_table.setItem(row, 2, state_item)
            if known is False:
                name_item.setForeground(OFFLINE_COLOR)

    # -- server lifecycle ---------------------------------------------------
    def _start_server(self) -> None:
        if self.service is not None and self.service.is_running:
            return
        settings = self.config.settings
        api_host = resolve_bind_host(settings.api_host, settings.api_port)
        if api_host is None:
            QMessageBox.critical(
                self,
                "Порт занят",
                f"Не удалось занять {settings.api_host}:{settings.api_port}. "
                f"Измените адрес или порт в настройках.",
            )
            return
        archive_dir = settings.resolve_archive_dir()
        if settings.uses_files:
            archive_dir.mkdir(parents=True, exist_ok=True)
        reader = ModbusReader(inter_request_delay=settings.inter_request_delay)
        writer, archive_reader, database = build_storage(settings, archive_dir)
        if database is not None:
            attach_database_logging(database)
            self._log(
                f"Хранилище: {settings.archive_storage} (PostgreSQL "
                f"{settings.database.host}:{settings.database.port}/{settings.database.name})"
            )
        self.service = ServerService(
            reader,
            writer,
            devices=self.config.devices,
            on_status=self.bridge.statusChanged.emit,
        )
        # Enable "stop" right away so the server can always be stopped, even if
        # starting the HTTP API fails afterwards.
        self.start_action.setEnabled(False)
        self.stop_action.setEnabled(True)
        try:
            self.service.start()
            app = create_app(self.service, archive_reader)
            self.api = ApiServer(app, api_host, settings.api_port)
            self.api.start()
        except Exception as exc:  # pragma: no cover - defensive
            self._stop_server()
            QMessageBox.critical(self, "Ошибка запуска сервера", str(exc))
            return

        if api_host != settings.api_host:
            self._log(
                f"Адрес {settings.api_host} недоступен для прослушивания, "
                f"API слушает 0.0.0.0:{settings.api_port}"
            )
        if settings.uses_files:
            storage = f"Архив: {archive_dir}"
        else:
            storage = "Архив: PostgreSQL"
        self.statusBar().showMessage(
            f"Сервер запущен. API: {api_host}:{settings.api_port}. {storage}"
        )
        self._log(f"Сервер запущен. {storage}")

    def autostart(self) -> None:
        """Start polling + API immediately (used by the ``--autostart`` flag)."""

        self._start_server()

    def _stop_server(self) -> None:
        if self.api is not None:
            self.api.stop()
            self.api = None
        if self.service is not None:
            self.service.stop()
            self.service = None
        self.start_action.setEnabled(True)
        self.stop_action.setEnabled(False)
        self._statuses.clear()
        self._refresh_colors()
        self._update_values()
        self.statusBar().showMessage("Сервер остановлен")
        self._log("Сервер остановлен")

    @staticmethod
    def _port_available(host: str, port: int) -> bool:
        return is_port_available(host, port)

    # -- device management --------------------------------------------------
    def _add_device(self) -> None:
        dialog = DeviceDialog(parent=self)
        if dialog.exec() and dialog.device is not None:
            device = dialog.device
            device.id = self._unique_id(device.id)
            self.config.devices.append(device)
            self._after_devices_changed()

    def _edit_device(self) -> None:
        device_id = self._selected_device_id()
        device = self._device_by_id(device_id) if device_id else None
        if device is None:
            QMessageBox.information(self, "Устройство", "Выберите устройство в списке.")
            return
        dialog = DeviceDialog(device, parent=self)
        if dialog.exec() and dialog.device is not None:
            updated = dialog.device
            index = self.config.devices.index(device)
            self.config.devices[index] = updated
            self._after_devices_changed()

    def _remove_device(self) -> None:
        device_id = self._selected_device_id()
        device = self._device_by_id(device_id) if device_id else None
        if device is None:
            QMessageBox.information(self, "Устройство", "Выберите устройство в списке.")
            return
        answer = QMessageBox.question(
            self, "Удаление", f"Удалить устройство «{device.name}»?"
        )
        if answer == QMessageBox.Yes:
            self.config.devices.remove(device)
            self._after_devices_changed()

    def _after_devices_changed(self) -> None:
        save_server_config(self.config)
        self._refresh_devices()
        if self.service is not None:
            self.service.set_devices(self.config.devices)

    def _unique_id(self, base: str) -> str:
        existing = {d.id for d in self.config.devices}
        if base not in existing:
            return base
        index = 2
        while f"{base}-{index}" in existing:
            index += 1
        return f"{base}-{index}"

    def _on_tree_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        if item.data(0, Qt.UserRole) is not None:
            self._edit_device()

    # -- settings -----------------------------------------------------------
    def _open_settings(self) -> None:
        dialog = ServerSettingsDialog(self.config.settings, parent=self)
        if dialog.exec():
            self.config.settings = dialog.settings()
            save_server_config(self.config)
            self._log("Настройки сохранены")

    # -- callbacks ----------------------------------------------------------
    def _on_status(self, status: DeviceStatus) -> None:
        self._statuses[status.device_id] = status
        self._refresh_colors()
        if status.device_id == self._selected_device_id():
            self._update_values()

    def _log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log.appendPlainText(f"[{stamp}] {message}")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._stop_server()
        super().closeEvent(event)
