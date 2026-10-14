"""Dialog used to create/edit a device and its register map."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ...common.models import DataType, DeviceConfig, RegisterConfig, RegisterFunction

COLUMNS = ["Название канала", "Адрес", "Функция", "Тип", "Масштаб", "Ед.", "Порядок", "Запись"]

CHANNEL_HINT = (
    "По Modbus читаются только значения из ячеек памяти устройства — что именно "
    "подключено к ячейке, нужно определить на месте (сравнивая показания) и вписать "
    "понятное имя канала вручную. Это имя увидят все клиенты."
)


class DeviceDialog(QDialog):
    def __init__(self, device: Optional[DeviceConfig] = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Устройство")
        self.resize(760, 520)
        self._device = device
        self._result: Optional[DeviceConfig] = None

        self.name_edit = QLineEdit()
        self.host_edit = QLineEdit()
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
        self.enabled_check = QCheckBox("Опроc включён")
        self.enabled_check.setChecked(True)

        form = QFormLayout()
        form.addRow("Имя узла", self.name_edit)
        form.addRow("IP адрес", self.host_edit)
        form.addRow("IP порт", self.port_spin)
        form.addRow("Modbus ID", self.device_id_spin)
        form.addRow("Интервал опроса", self.interval_spin)
        form.addRow("Таймаут", self.timeout_spin)
        form.addRow("Повторы", self.retries_spin)
        form.addRow("", self.enabled_check)

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

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        hint = QLabel(CHANNEL_HINT)
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#555;")

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addWidget(self.table)
        layout.addLayout(row_buttons)
        layout.addWidget(buttons)

        if device is not None:
            self._load(device)
        else:
            self._add_row()

    # -- table helpers ------------------------------------------------------
    def _make_combo(self, options: list[str], value: str) -> QComboBox:
        combo = QComboBox()
        combo.addItems(options)
        index = combo.findText(value)
        if index >= 0:
            combo.setCurrentIndex(index)
        return combo

    def _add_row(self, register: Optional[RegisterConfig] = None) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        if register is None:
            register = RegisterConfig(name=f"channel{row + 1}", address=row)

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
