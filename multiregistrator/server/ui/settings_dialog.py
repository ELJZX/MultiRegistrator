"""Server settings dialog."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from ...common.config import ServerSettings


class ServerSettingsDialog(QDialog):
    def __init__(self, settings: ServerSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Настройки сервера")
        self.resize(560, 320)

        self.host_edit = QLineEdit(settings.api_host)
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(settings.api_port)
        self.archive_edit = QLineEdit(settings.archive_dir)
        browse_button = QPushButton("...")
        browse_button.setFixedWidth(32)
        browse_button.clicked.connect(self._browse)

        self.interval_spin = QDoubleSpinBox()
        self.interval_spin.setRange(0.1, 86400.0)
        self.interval_spin.setValue(settings.default_poll_interval)
        self.interval_spin.setSuffix(" с")
        self.timeout_spin = QDoubleSpinBox()
        self.timeout_spin.setRange(0.1, 60.0)
        self.timeout_spin.setValue(settings.default_timeout)
        self.timeout_spin.setSuffix(" с")
        self.retries_spin = QSpinBox()
        self.retries_spin.setRange(0, 10)
        self.retries_spin.setValue(settings.default_retries)
        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0.0, 10.0)
        self.delay_spin.setSingleStep(0.01)
        self.delay_spin.setValue(settings.inter_request_delay)
        self.delay_spin.setSuffix(" с")

        form = QFormLayout()
        form.addRow("Адрес API", self.host_edit)
        form.addRow("Порт API", self.port_spin)
        container = QHBoxLayout()
        container.addWidget(self.archive_edit)
        container.addWidget(browse_button)
        form.addRow("Папка архива", container)
        form.addRow("Интервал опроса", self.interval_spin)
        form.addRow("Таймаут", self.timeout_spin)
        form.addRow("Повторы", self.retries_spin)
        form.addRow("Пауза между запросами", self.delay_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _browse(self) -> None:
        current = self.archive_edit.text() or str(Path.cwd())
        chosen = QFileDialog.getExistingDirectory(self, "Папка архива", current)
        if chosen:
            self.archive_edit.setText(chosen)

    def settings(self) -> ServerSettings:
        return ServerSettings(
            api_host=self.host_edit.text().strip() or "0.0.0.0",
            api_port=self.port_spin.value(),
            archive_dir=self.archive_edit.text().strip() or "archive",
            default_poll_interval=self.interval_spin.value(),
            default_timeout=self.timeout_spin.value(),
            default_retries=self.retries_spin.value(),
            inter_request_delay=self.delay_spin.value(),
        )
