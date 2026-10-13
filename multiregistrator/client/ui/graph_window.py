"""Per-device window: static and live plotting of archived data."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
from typing import Optional

import pyqtgraph as pg
from PySide6.QtCore import QDateTime, Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QDateTimeEdit,
    QGroupBox,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...common.models import TimeSeries
from ..api_client import ServerApiClient, ServerApiError
from .channel_dialog import ChannelDialog

MAX_LIVE_POINTS = 7200
LIVE_COLORS = [
    "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4",
    "#46f0f0", "#f032e6", "#bcf60c", "#008080", "#9a6324",
]


class GraphWindow(QMainWindow):
    def __init__(
        self,
        api: ServerApiClient,
        device_id: str,
        device_name: str,
        refresh_ms: int = 1000,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.api = api
        self.device_id = device_id
        self.setWindowTitle(f"График — {device_name}")
        self.resize(1180, 680)

        self.selected_channels: list[str] = []
        self.curves: dict[str, pg.PlotDataItem] = {}
        self.live_data: dict[str, tuple[deque, deque]] = {}
        self.live_mode = False

        self.refresh_ms = max(200, int(refresh_ms))
        self.live_timer = QTimer(self)
        self.live_timer.setInterval(self.refresh_ms)
        self.live_timer.timeout.connect(self._poll_live)

        self._build_ui(device_name)
        self._load_channels()

    # -- UI -----------------------------------------------------------------
    def _build_ui(self, device_name: str) -> None:
        panel = QWidget()
        panel.setFixedWidth(320)
        panel_layout = QVBoxLayout(panel)

        title = QLabel(f"<b>{device_name}</b>")
        panel_layout.addWidget(title)

        period_box = QGroupBox("Период")
        period_layout = QVBoxLayout(period_box)
        self.start_edit = QDateTimeEdit()
        self.start_edit.setCalendarPopup(True)
        self.start_edit.setDisplayFormat("dd.MM.yyyy HH:mm:ss")
        self.end_edit = QDateTimeEdit()
        self.end_edit.setCalendarPopup(True)
        self.end_edit.setDisplayFormat("dd.MM.yyyy HH:mm:ss")
        now = QDateTime.currentDateTime()
        self.end_edit.setDateTime(now)
        self.start_edit.setDateTime(now.addSecs(-3600))
        period_layout.addWidget(QLabel("Начало:"))
        period_layout.addWidget(self.start_edit)
        period_layout.addWidget(QLabel("Конец:"))
        period_layout.addWidget(self.end_edit)
        panel_layout.addWidget(period_box)

        self.channel_button = QPushButton("Выбрать канал данных")
        self.channel_button.clicked.connect(self._choose_channels)
        panel_layout.addWidget(self.channel_button)

        self.channels_label = QLabel("Каналы: (все)")
        self.channels_label.setWordWrap(True)
        panel_layout.addWidget(self.channels_label)

        self.build_button = QPushButton("Сформировать график")
        self.build_button.clicked.connect(self._build_static)
        panel_layout.addWidget(self.build_button)

        self.live_check = QCheckBox("Реальное время")
        self.live_check.toggled.connect(self._toggle_live)
        panel_layout.addWidget(self.live_check)

        self.autoscale_button = QPushButton("Автомасштаб по Y")
        self.autoscale_button.clicked.connect(self._autoscale_y)
        panel_layout.addWidget(self.autoscale_button)

        panel_layout.addStretch(1)

        self.plot = pg.PlotWidget(axisItems={"bottom": pg.DateAxisItem(orientation="bottom")})
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.setLabel("bottom", "Время")
        self.plot.setLabel("left", "Значение")
        self.plot.addLegend(offset=(10, 10))
        self.plot.setMouseEnabled(x=True, y=True)
        self._legend = self.plot.getPlotItem().legend

        self.setCentralWidget(self._compose(panel, self.plot))

    @staticmethod
    def _compose(panel: QWidget, plot: QWidget) -> QWidget:
        from PySide6.QtWidgets import QHBoxLayout, QSplitter

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(panel)
        splitter.addWidget(plot)
        splitter.setStretchFactor(1, 1)
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)
        return container

    # -- channels -----------------------------------------------------------
    def _load_channels(self) -> None:
        try:
            channels = self.api.channels(self.device_id)
        except ServerApiError as exc:
            channels = []
            self.statusBar().showMessage(str(exc))
        self.available_channels = channels
        self.selected_channels = list(channels)
        self._update_channels_label()

    def _update_channels_label(self) -> None:
        if self.selected_channels and len(self.selected_channels) < len(self.available_channels):
            text = ", ".join(self.selected_channels)
        else:
            text = "(все)"
        self.channels_label.setText(f"Каналы: {text}")

    def _choose_channels(self) -> None:
        if not self.available_channels:
            QMessageBox.information(self, "Каналы", "У устройства нет доступных каналов.")
            return
        dialog = ChannelDialog(
            self.available_channels, self.selected_channels, parent=self
        )
        if dialog.exec():
            self.selected_channels = dialog.selected_channels()
            self._update_channels_label()

    # -- static plotting ----------------------------------------------------
    def _build_static(self) -> None:
        self.live_check.setChecked(False)
        start = self.start_edit.dateTime().toPython()
        end = self.end_edit.dateTime().toPython()
        if end <= start:
            start, end = end, start
        try:
            series = self.api.data(
                self.device_id, start, end, self.selected_channels or None
            )
        except ServerApiError as exc:
            QMessageBox.warning(self, "Ошибка", str(exc))
            return
        if not series:
            self.statusBar().showMessage("За указанный период данные не найдены")
            return
        self._plot_series(series)
        self._autoscale_y()
        self.statusBar().showMessage(
            f"Построено каналов: {len(series)} за {start:%d.%m.%Y %H:%M} — {end:%d.%m.%Y %H:%M}"
        )

    def _clear_plot(self) -> None:
        self.plot.clear()
        self.curves.clear()
        if self._legend is not None:
            self._legend.clear()

    def _plot_series(self, series: dict[str, TimeSeries]) -> None:
        self._clear_plot()
        for index, (channel, ts) in enumerate(sorted(series.items())):
            times, values = ts.numeric()
            if not times:
                continue
            xs = [moment.timestamp() for moment in times]
            curve = self.plot.plot(
                xs,
                values,
                pen=pg.mkPen(LIVE_COLORS[index % len(LIVE_COLORS)], width=1.6),
                name=channel,
                connect="finite",
            )
            self.curves[channel] = curve

    def _autoscale_y(self) -> None:
        values: list[float] = []
        for curve in self.curves.values():
            _, data = curve.getData()
            if data is not None and len(data):
                values.extend(float(v) for v in data if v is not None)
        if not values:
            return
        low, high = min(values), max(values)
        if low == high:
            low, high = low - 1.0, high + 1.0
        self.plot.setYRange(low, high, padding=0.05)

    # -- live plotting ------------------------------------------------------
    def _toggle_live(self, enabled: bool) -> None:
        self.live_mode = enabled
        if enabled:
            self._start_live()
        else:
            self.live_timer.stop()
            self.statusBar().showMessage("Режим реального времени остановлен")

    def _start_live(self) -> None:
        if not self.selected_channels:
            self._load_channels()
        self._clear_plot()
        self.live_data = {
            channel: (deque(maxlen=MAX_LIVE_POINTS), deque(maxlen=MAX_LIVE_POINTS))
            for channel in self.selected_channels
        }
        for index, channel in enumerate(self.selected_channels):
            self.curves[channel] = self.plot.plot(
                [],
                [],
                pen=pg.mkPen(LIVE_COLORS[index % len(LIVE_COLORS)], width=1.6),
                name=channel,
            )
        self.live_timer.start()
        self.statusBar().showMessage("Режим реального времени запущен")
        self._poll_live()

    def _poll_live(self) -> None:
        try:
            payload = self.api.latest(self.device_id)
        except ServerApiError as exc:
            self.statusBar().showMessage(str(exc))
            return
        moment = payload.get("last_success")
        if not moment:
            self.statusBar().showMessage("Ожидание данных...")
            return
        try:
            timestamp = datetime.fromisoformat(str(moment)).timestamp()
        except ValueError:
            return
        values = payload.get("values", {})
        for channel, (times, series_values) in self.live_data.items():
            value = values.get(channel)
            times.append(timestamp)
            series_values.append(None if value is None else float(value))
        for channel, curve in self.curves.items():
            times, series_values = self.live_data[channel]
            curve.setData(list(times), list(series_values))
        if payload.get("online"):
            self.statusBar().showMessage(
                f"Онлайн. Обновлено: {datetime.fromisoformat(str(moment)):%H:%M:%S}"
            )
        else:
            self.statusBar().showMessage("Устройство не в сети")

    def closeEvent(self, event) -> None:  # noqa: N802
        self.live_timer.stop()
        super().closeEvent(event)
