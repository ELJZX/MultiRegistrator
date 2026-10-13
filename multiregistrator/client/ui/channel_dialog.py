"""Dialog for choosing which data channels to plot."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)


class ChannelDialog(QDialog):
    def __init__(self, channels: list[str], selected: list[str] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Выбрать канал данных")
        self.resize(360, 460)
        selected_set = set(selected or channels)

        self.list = QListWidget()
        for channel in channels:
            item = QListWidgetItem(channel)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if channel in selected_set else Qt.Unchecked)
            self.list.addItem(item)

        select_all = QPushButton("Выбрать все")
        clear_all = QPushButton("Снять все")
        select_all.clicked.connect(lambda: self._set_all(Qt.Checked))
        clear_all.clicked.connect(lambda: self._set_all(Qt.Unchecked))
        buttons_row = QHBoxLayout()
        buttons_row.addWidget(select_all)
        buttons_row.addWidget(clear_all)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.list)
        layout.addLayout(buttons_row)
        layout.addWidget(buttons)

    def _set_all(self, state: Qt.CheckState) -> None:
        for index in range(self.list.count()):
            self.list.item(index).setCheckState(state)

    def selected_channels(self) -> list[str]:
        return [
            self.list.item(index).text()
            for index in range(self.list.count())
            if self.list.item(index).checkState() == Qt.Checked
        ]
