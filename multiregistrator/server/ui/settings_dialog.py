"""Server settings dialog."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from ...common.config import (
    STORAGE_BOTH,
    STORAGE_DATABASE,
    STORAGE_FILES,
    DatabaseSettings,
    ServerSettings,
)


class ServerSettingsDialog(QDialog):
    def __init__(self, settings: ServerSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Настройки сервера")
        self.resize(560, 560)

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

        # -- PostgreSQL ------------------------------------------------------
        db = settings.database
        self.storage_combo = QComboBox()
        self.storage_combo.addItem("Только файлы (archive/*.txt)", STORAGE_FILES)
        self.storage_combo.addItem("Только PostgreSQL", STORAGE_DATABASE)
        self.storage_combo.addItem("Файлы + PostgreSQL", STORAGE_BOTH)
        index = self.storage_combo.findData(settings.archive_storage)
        self.storage_combo.setCurrentIndex(max(0, index))
        self.storage_combo.currentIndexChanged.connect(self._update_db_enabled)

        self.db_enabled = QCheckBox("Писать логи в PostgreSQL")
        self.db_enabled.setChecked(db.enabled)
        self.db_host = QLineEdit(db.host)
        self.db_port = QSpinBox()
        self.db_port.setRange(1, 65535)
        self.db_port.setValue(db.port)
        self.db_name = QLineEdit(db.name)
        self.db_user = QLineEdit(db.user)
        self.db_password = QLineEdit(db.password)
        self.db_password.setEchoMode(QLineEdit.Password)
        self.db_timeout = QSpinBox()
        self.db_timeout.setRange(1, 120)
        self.db_timeout.setValue(db.connect_timeout)
        self.db_timeout.setSuffix(" с")

        db_form = QFormLayout()
        db_form.addRow("Сервер БД", self.db_host)
        db_form.addRow("Порт БД", self.db_port)
        db_form.addRow("База данных", self.db_name)
        db_form.addRow("Пользователь", self.db_user)
        db_form.addRow("Пароль", self.db_password)
        db_form.addRow("Таймаут подключения", self.db_timeout)
        storage_form = QFormLayout()
        storage_form.addRow("Хранилище архива", self.storage_combo)

        db_box = QGroupBox("PostgreSQL (pgAdmin)")
        db_box_layout = QVBoxLayout(db_box)
        db_box_layout.addLayout(storage_form)
        db_box_layout.addWidget(self.db_enabled)
        db_box_layout.addLayout(db_form)

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
        layout.addWidget(db_box)
        layout.addWidget(buttons)

        self._update_db_enabled()

    def _update_db_enabled(self) -> None:
        """The DB fields only matter when the archive uses PostgreSQL."""

        mode = self.storage_combo.currentData()
        needs_db = mode in (STORAGE_DATABASE, STORAGE_BOTH)
        for widget in (
            self.db_enabled,
            self.db_host,
            self.db_port,
            self.db_name,
            self.db_user,
            self.db_password,
            self.db_timeout,
        ):
            widget.setEnabled(needs_db)
        if needs_db:
            self.db_enabled.setEnabled(True)

    def _browse(self) -> None:
        current = self.archive_edit.text() or str(Path.cwd())
        chosen = QFileDialog.getExistingDirectory(self, "Папка архива", current)
        if chosen:
            self.archive_edit.setText(chosen)

    def settings(self) -> ServerSettings:
        storage = self.storage_combo.currentData() or STORAGE_FILES
        needs_db = storage in (STORAGE_DATABASE, STORAGE_BOTH)
        return ServerSettings(
            api_host=self.host_edit.text().strip() or "0.0.0.0",
            api_port=self.port_spin.value(),
            archive_dir=self.archive_edit.text().strip() or "archive",
            archive_storage=storage,
            default_poll_interval=self.interval_spin.value(),
            default_timeout=self.timeout_spin.value(),
            default_retries=self.retries_spin.value(),
            inter_request_delay=self.delay_spin.value(),
            database=DatabaseSettings(
                enabled=needs_db,
                host=self.db_host.text().strip() or "127.0.0.1",
                port=self.db_port.value(),
                name=self.db_name.text().strip() or "multiregistrator",
                user=self.db_user.text().strip() or "multiregistrator",
                password=self.db_password.text(),
                connect_timeout=self.db_timeout.value(),
            ),
        )
