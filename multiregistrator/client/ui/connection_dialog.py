"""Dialog for selecting / editing the server connection."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from ...common.config import ClientConfig, ClientSettings


class ConnectionDialog(QDialog):
    def __init__(self, config: ClientConfig, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Подключение к серверу")
        self.resize(520, 260)
        self._config = config

        self.combo = QComboBox()
        for connection in config.connections:
            self.combo.addItem(connection.connection_name, connection)
        if config.connections:
            self.combo.setCurrentIndex(0)
        self.combo.currentIndexChanged.connect(self._on_connection_selected)

        self.name_edit = QLineEdit()
        self.host_edit = QLineEdit()
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        save_button = QPushButton("Сохранить соединение")
        save_button.clicked.connect(self._save_connection)

        form = QFormLayout()
        form.addRow("Список соединений", self.combo)
        form.addRow("Название соединения", self.name_edit)
        form.addRow("IP адрес", self.host_edit)
        form.addRow("IP порт", self.port_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(save_button)
        layout.addWidget(buttons)

        current = config.settings
        self.name_edit.setText(current.connection_name)
        self.host_edit.setText(current.server_host)
        self.port_spin.setValue(current.server_port)

    def _on_connection_selected(self, index: int) -> None:
        if index < 0:
            return
        connection: ClientSettings = self.combo.itemData(index)
        self.name_edit.setText(connection.connection_name)
        self.host_edit.setText(connection.server_host)
        self.port_spin.setValue(connection.server_port)

    def settings(self) -> ClientSettings:
        return ClientSettings(
            server_host=self.host_edit.text().strip() or "127.0.0.1",
            server_port=self.port_spin.value(),
            connection_name=self.name_edit.text().strip() or "Сервер",
            live_refresh_ms=self._config.settings.live_refresh_ms,
        )

    def _save_connection(self) -> None:
        settings = self.settings()
        for index in range(self.combo.count()):
            if self.combo.itemText(index) == settings.connection_name:
                self.combo.setItemData(index, settings)
                return
        self.combo.addItem(settings.connection_name, settings)
