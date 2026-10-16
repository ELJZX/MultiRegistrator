"""Dialog used to create/edit a device and its register map."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...common.models import DataType, DeviceConfig, RegisterConfig, RegisterFunction
from ..discovery import discover_channels
from ..modbus import ModbusReader

COLUMNS = [
    "Название канала",
    "Адрес",
    "Функция",
    "Тип",
    "Масштаб",
    "Ед.",
    "Порядок",
    "Запись",
    "Значение",
]

# Sensible defaults for a new channel (they fit the "Мультиграф" family, and are
# editable on the "Дополнительно" tab).
DEFAULT_FUNCTION = RegisterFunction.INPUT.value
DEFAULT_DATA_TYPE = DataType.FLOAT32.value
DEFAULT_WORD_ORDER = "little"

CHANNEL_HINT = (
    "По Modbus читаются только значения из ячеек памяти устройства — что именно "
    "подключено к ячейке, нужно определить на месте (сравнивая показания) и вписать "
    "понятное имя канала вручную. Это имя увидят все клиенты.\n"
    "Нажмите «Найти каналы», чтобы сервер сам опросил устройство и показал найденные "
    "каналы с текущими показаниями — по ним легко понять, где температура, где проводимость."
)

DEFAULTS_HINT = (
    "Эти значения подставляются при добавлении новых каналов и для новых устройств. "
    "Существующие каналы не меняются."
)


class DeviceDialog(QDialog):
    def __init__(self, device: Optional[DeviceConfig] = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Устройство")
        self.resize(780, 560)
        self._device = device
        self._result: Optional[DeviceConfig] = None

        self.name_edit = QLineEdit()
        self.host_edit = QLineEdit()
        self.enabled_check = QCheckBox("Опроc включён")
        self.enabled_check.setChecked(True)

        # -- polling / connection (Дополнительно) --------------------------
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(502)
        self.device_id_spin = QSpinBox()
        self.device_id_spin.setRange(0, 247)
        self.device_id_spin.setValue(1)
        self.interval_spin = QDoubleSpinBox()
        self.interval_spin.setRange(0.1, 86400.0)
        self.interval_spin.setValue(5.0)
        self.interval_spin.setSuffix(" с")
        self.timeout_spin = QDoubleSpinBox()
        self.timeout_spin.setRange(0.1, 60.0)
        self.timeout_spin.setValue(3.0)
        self.timeout_spin.setSuffix(" с")
        self.retries_spin = QSpinBox()
        self.retries_spin.setRange(0, 10)
        self.retries_spin.setValue(1)

        # -- default channel parameters (Дополнительно) --------------------
        self.default_function = self._make_combo(
            [f.value for f in RegisterFunction], DEFAULT_FUNCTION
        )
        self.default_type = self._make_combo(
            [d.value for d in DataType], DEFAULT_DATA_TYPE
        )
        self.default_word_order = self._make_combo(["big", "little"], DEFAULT_WORD_ORDER)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        tabs = QTabWidget()
        tabs.addTab(self._build_device_tab(), "Устройство")
        tabs.addTab(self._build_advanced_tab(), "Дополнительно")

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

        if device is not None:
            self._load(device)
        else:
            self._add_row()

    # -- tabs ---------------------------------------------------------------
    def _build_device_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        form = QFormLayout()
        form.addRow("Имя узла", self.name_edit)
        form.addRow("IP адрес", self.host_edit)
        form.addRow("", self.enabled_check)

        hint = QLabel(CHANNEL_HINT)
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#555;")

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        add_button = QPushButton("Добавить канал")
        remove_button = QPushButton("Удалить канал")
        add_button.clicked.connect(self._add_row)
        remove_button.clicked.connect(self._remove_row)
        row_buttons = QHBoxLayout()
        row_buttons.addWidget(add_button)
        row_buttons.addWidget(remove_button)
        row_buttons.addStretch(1)

        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addLayout(self._build_scan_row())
        layout.addWidget(self.table)
        layout.addLayout(row_buttons)
        return tab

    def _build_scan_row(self) -> QHBoxLayout:
        self.scan_function = QComboBox()
        self.scan_function.addItems(
            [RegisterFunction.INPUT.value, RegisterFunction.HOLDING.value]
        )
        self.scan_start = QSpinBox()
        self.scan_start.setRange(0, 65535)
        self.scan_start.setValue(0)
        self.scan_end = QSpinBox()
        self.scan_end.setRange(1, 65535)
        self.scan_end.setValue(4096)
        self.scan_button = QPushButton("Найти каналы")
        self.scan_button.clicked.connect(self._scan_channels)

        scan_row = QHBoxLayout()
        scan_row.addWidget(QLabel("Поиск:"))
        scan_row.addWidget(self.scan_function)
        scan_row.addWidget(QLabel("с"))
        scan_row.addWidget(self.scan_start)
        scan_row.addWidget(QLabel("по"))
        scan_row.addWidget(self.scan_end)
        scan_row.addWidget(self.scan_button)
        return scan_row

    def _build_advanced_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        connection_form = QFormLayout()
        connection_form.addRow("IP порт", self.port_spin)
        connection_form.addRow("Modbus ID", self.device_id_spin)
        connection_form.addRow("Интервал опроса", self.interval_spin)
        connection_form.addRow("Таймаут", self.timeout_spin)
        connection_form.addRow("Повторы", self.retries_spin)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)

        defaults_form = QFormLayout()
        defaults_form.addRow("Функция", self.default_function)
        defaults_form.addRow("Тип данных", self.default_type)
        defaults_form.addRow("Порядок слов", self.default_word_order)

        hint = QLabel(DEFAULTS_HINT)
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#555;")

        layout.addLayout(connection_form)
        layout.addWidget(separator)
        layout.addWidget(QLabel("<b>Параметры новых каналов по умолчанию</b>"))
        layout.addLayout(defaults_form)
        layout.addWidget(hint)
        layout.addStretch(1)
        return tab

    # -- table helpers ------------------------------------------------------
    def _make_combo(self, options: list[str], value: str) -> QComboBox:
        combo = QComboBox()
        combo.addItems(options)
        index = combo.findText(value)
        if index >= 0:
            combo.setCurrentIndex(index)
        return combo

    def _add_row(
        self, register: Optional[RegisterConfig] = None, value: Optional[float] = None
    ) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        if register is None:
            register = RegisterConfig(
                name=f"channel{row + 1}",
                address=row,
                function=self.default_function.currentText(),
                data_type=self.default_type.currentText(),
                word_order=self.default_word_order.currentText(),
            )

        self.table.setItem(row, 0, QTableWidgetItem(register.name))
        self.table.setItem(row, 1, QTableWidgetItem(str(register.address)))
        self.table.setCellWidget(
            row, 2, self._make_combo([f.value for f in RegisterFunction], register.function)
        )
        self.table.setCellWidget(
            row, 3, self._make_combo([d.value for d in DataType], register.data_type)
        )
        self.table.setItem(row, 4, QTableWidgetItem(str(register.scale)))
        self.table.setItem(row, 5, QTableWidgetItem(register.unit))
        self.table.setCellWidget(
            row, 6, self._make_combo(["big", "little"], register.word_order)
        )
        writable = QTableWidgetItem()
        writable.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        writable.setCheckState(Qt.Checked if register.writable else Qt.Unchecked)
        self.table.setItem(row, 7, writable)
        value_item = QTableWidgetItem("" if value is None else f"{value:.6g}")
        value_item.setFlags(Qt.ItemIsEnabled)
        self.table.setItem(row, 8, value_item)

    # -- discovery ----------------------------------------------------------
    def _scan_channels(self) -> None:
        host = self.host_edit.text().strip()
        if not host:
            QMessageBox.warning(self, "Поиск каналов", "Укажите IP адрес устройства.")
            return
        function = self.scan_function.currentText()
        start = self.scan_start.value()
        end = self.scan_end.value()
        if end <= start:
            QMessageBox.warning(self, "Поиск каналов", "Конец диапазона должен быть больше начала.")
            return

        device = DeviceConfig(
            id="scan",
            name="scan",
            host=host,
            port=self.port_spin.value(),
            device_id=self.device_id_spin.value(),
            timeout=self.timeout_spin.value(),
            retries=self.retries_spin.value(),
        )
        reader = ModbusReader()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            candidates = discover_channels(reader, device, function=function, start=start, end=end)
        except Exception as exc:  # pragma: no cover - defensive
            candidates = []
            QMessageBox.warning(self, "Поиск каналов", f"Ошибка опроса: {exc}")
        finally:
            reader.close()
            QApplication.restoreOverrideCursor()

        existing = self._table_keys()
        added = 0
        for candidate in candidates:
            key = (candidate.register.function, candidate.register.address)
            if key in existing:
                continue
            self._add_row(candidate.register, candidate.value)
            existing.add(key)
            added += 1

        if added:
            QMessageBox.information(
                self,
                "Поиск каналов",
                f"Найдено каналов: {added}. Впишите понятные имена и сохраните устройство.",
            )
        else:
            QMessageBox.information(
                self, "Поиск каналов", "Новые каналы не найдены в указанном диапазоне."
            )

    def _table_keys(self) -> set:
        keys = set()
        for row in range(self.table.rowCount()):
            address_item = self.table.item(row, 1)
            function_widget = self.table.cellWidget(row, 2)
            if address_item is None or function_widget is None:
                continue
            try:
                address = int(address_item.text())
            except ValueError:
                continue
            keys.add((function_widget.currentText(), address))
        return keys

    def _remove_row(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    # -- data binding -------------------------------------------------------
    def _load(self, device: DeviceConfig) -> None:
        self.name_edit.setText(device.name)
        self.host_edit.setText(device.host)
        self.port_spin.setValue(device.port)
        self.device_id_spin.setValue(device.device_id)
        self.interval_spin.setValue(device.poll_interval)
        self.timeout_spin.setValue(device.timeout)
        self.retries_spin.setValue(device.retries)
        self.enabled_check.setChecked(device.enabled)
        for register in device.registers:
            self._add_row(register)

    def _collect_registers(self) -> list[RegisterConfig]:
        registers: list[RegisterConfig] = []
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            address_item = self.table.item(row, 1)
            if name_item is None or not name_item.text().strip():
                continue
            try:
                address = int(address_item.text()) if address_item else 0
            except ValueError as exc:
                raise ValueError(f"Некорректный адрес в строке {row + 1}") from exc
            function = self.table.cellWidget(row, 2).currentText()
            data_type = self.table.cellWidget(row, 3).currentText()
            scale_item = self.table.item(row, 4)
            try:
                scale = float(scale_item.text()) if scale_item and scale_item.text() else 1.0
            except ValueError as exc:
                raise ValueError(f"Некорректный масштаб в строке {row + 1}") from exc
            unit = self.table.item(row, 5).text() if self.table.item(row, 5) else ""
            word_order = self.table.cellWidget(row, 6).currentText()
            writable_item = self.table.item(row, 7)
            writable = writable_item is not None and writable_item.checkState() == Qt.Checked
            registers.append(
                RegisterConfig(
                    name=name_item.text().strip(),
                    address=address,
                    function=function,
                    data_type=data_type,
                    scale=scale,
                    unit=unit,
                    word_order=word_order,
                    writable=writable,
                )
            )
        return registers

    def _on_accept(self) -> None:
        try:
            self.set_device(self._build_device())
        except ValueError as exc:
            QMessageBox.warning(self, "Проверьте данные", str(exc))
            return
        self.accept()

    def _build_device(self) -> DeviceConfig:
        name = self.name_edit.text().strip()
        host = self.host_edit.text().strip()
        if not name:
            raise ValueError("Укажите имя узла")
        if not host:
            raise ValueError("Укажите IP адрес")
        registers = self._collect_registers()
        identifier = self._device.id if self._device else host
        return DeviceConfig(
            id=identifier,
            name=name,
            host=host,
            port=self.port_spin.value(),
            device_id=self.device_id_spin.value(),
            enabled=self.enabled_check.isChecked(),
            poll_interval=self.interval_spin.value(),
            timeout=self.timeout_spin.value(),
            retries=self.retries_spin.value(),
            registers=registers,
        )

    def set_device(self, device: DeviceConfig) -> None:
        self._result = device

    @property
    def device(self) -> Optional[DeviceConfig]:
        return self._result
