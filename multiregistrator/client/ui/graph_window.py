"""Per-device graph view (embedded into the client's single window)."""

from __future__ import annotations

import math
from collections import deque
from datetime import datetime
from typing import Optional

import pyqtgraph as pg

pg.setConfigOption("background", "w")
pg.setConfigOption("foreground", "k")

from PySide6.QtCore import QDateTime, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QFont,
    QPageLayout,
    QPageSize,
    QPainter,
    QPdfWriter,
    QPixmap,
)
from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog
from PySide6.QtWidgets import (
    QApplication,
    QDateTimeEdit,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ...common.models import TimeSeries
from ...common.plotting import clamp_period_start, with_margin
from ...common.report import build_report_lines
from ..api_client import ServerApiClient, ServerApiError
from .channel_dialog import ChannelDialog

MAX_LIVE_POINTS = 7200
LIVE_COLORS = [
    "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4",
    "#46f0f0", "#f032e6", "#bcf60c", "#008080", "#9a6324",
]

# Real-time mode: how much time is visible at once and how much free space is
# left after the newest point (so the end of the graph is always visible).
LIVE_WINDOW_SECONDS = 120.0
LIVE_RIGHT_MARGIN = 0.2
GRID_ALPHA = 0.3

LIVE_ON_STYLE = "background-color:#2e8b57; color:white; font-weight:bold;"
LIVE_OFF_STYLE = "background-color:#c8c8c8; color:#303030;"


class TimeAxisItem(pg.DateAxisItem):
    """Time axis whose smallest step is 5 seconds.

    The default pyqtgraph date axis zooms down to sub-second labels; here ticks
    never get finer than 5 seconds, which keeps the X axis readable in live mode.
    """

    MIN_TICK_PX = 50.0
    STEPS = [
        5, 10, 15, 20, 30, 60, 120, 300, 600, 900, 1800, 3600,
        7200, 10800, 21600, 43200, 86400, 172800, 604800,
        2592000, 7776000, 15552000, 31536000,
    ]

    def tickValues(self, minVal, maxVal, size):
        if maxVal <= minVal or size <= 0:
            return []
        density = (maxVal - minVal) / size  # seconds per pixel
        step = self.STEPS[-1]
        for candidate in self.STEPS:
            if candidate / density >= self.MIN_TICK_PX:
                step = candidate
                break
        first = math.floor(minVal / step) * step
        ticks = []
        x = first
        while x <= maxVal:
            if x >= minVal:
                ticks.append(x)
            x += step
        return [(step, ticks)]

    def tickStrings(self, values, scale, spacing):
        if spacing < 60:
            fmt = "%H:%M:%S"
        elif spacing < 86400:
            fmt = "%H:%M"
        else:
            fmt = "%d.%m.%Y"
        result = []
        for value in values:
            try:
                result.append(datetime.fromtimestamp(float(value)).strftime(fmt))
            except (OverflowError, OSError, ValueError):
                result.append("")
        return result


class GraphView(QWidget):
    back_requested = Signal()

    def __init__(self, refresh_ms: int = 1000, parent=None) -> None:
        super().__init__(parent)
        self.api: Optional[ServerApiClient] = None
        self.device_id: Optional[str] = None
        self.device_name = ""
        self.available_channels: list[str] = []
        self.selected_channels: list[str] = []
        self.curves: dict[str, pg.PlotDataItem] = {}
        self.live_data: dict[str, tuple[deque, deque]] = {}
        self.live_mode = False
        self._static_built = False

        self.refresh_ms = max(200, int(refresh_ms))
        self.live_timer = QTimer(self)
        self.live_timer.setInterval(self.refresh_ms)
        self.live_timer.timeout.connect(self._poll_live)

        self._build_ui()

    # -- UI -----------------------------------------------------------------
    def _build_ui(self) -> None:
        panel = QWidget()
        panel.setFixedWidth(300)
        panel_layout = QVBoxLayout(panel)

        self.title = QLabel("<b>График</b>")
        self.title.setWordWrap(True)
        panel_layout.addWidget(self.title)

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

        self.build_button = QPushButton("Сформировать график")
        self.build_button.clicked.connect(self._build_static)
        panel_layout.addWidget(self.build_button)

        # The display/export controls form a separate group.
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        panel_layout.addWidget(separator)

        self.live_button = QPushButton("Режим реального времени")
        self.live_button.setCheckable(True)
        self.live_button.setToolTip(
            "Зелёный — обновляется в реальном времени, серый — статичный график"
        )
        self.live_button.toggled.connect(self._on_live_toggled)
        panel_layout.addWidget(self.live_button)

        self.autoscale_button = QPushButton("Автомасштаб")
        self.autoscale_button.setCheckable(True)
        self.autoscale_button.setToolTip("Автоматически масштабировать график")
        self.autoscale_button.toggled.connect(self._on_autoscale_toggled)
        panel_layout.addWidget(self.autoscale_button)

        self.grid_button = QPushButton("Убрать сетку")
        self.grid_button.setCheckable(True)
        self.grid_button.setToolTip(
            "Скрыть координатную сетку — останутся только оси и график"
        )
        self.grid_button.toggled.connect(self._on_grid_toggled)
        panel_layout.addWidget(self.grid_button)

        self.pdf_button = QPushButton("Сохранить график в PDF")
        self.pdf_button.clicked.connect(self._save_pdf)
        panel_layout.addWidget(self.pdf_button)

        self.print_button = QPushButton("Печать")
        self.print_button.clicked.connect(self._print_preview)
        panel_layout.addWidget(self.print_button)

        panel_layout.addStretch(1)

        self.plot = pg.PlotWidget(axisItems={"bottom": TimeAxisItem(orientation="bottom")})
        self.plot.setBackground("w")
        self.plot.showGrid(x=True, y=True, alpha=GRID_ALPHA)
        self.plot.setLabel("bottom", "Время")
        self.plot.setLabel("left", "Значение")
        self._legend = self.plot.addLegend(offset=(10, 10))
        self.plot.setMouseEnabled(x=True, y=True)
        self._style_legend()

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(panel)
        splitter.addWidget(self.plot)
        splitter.setStretchFactor(1, 1)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        self._update_live_style()

    def _style_legend(self) -> None:
        """Make the channel box a solid, opaque white panel.

        The default pyqtgraph legend is translucent, so the grid shows through
        it.  A fully opaque brush keeps the channel list readable.
        """

        if self._legend is None:
            return
        self._legend.frame = True
        self._legend.setBrush(pg.mkBrush(255, 255, 255, 255))
        self._legend.setPen(pg.mkPen(120, 120, 120))
        self._legend.setZValue(1_000_000)

    # -- device -------------------------------------------------------------
    def set_device(self, api: Optional[ServerApiClient], device_id: str, device_name: str) -> None:
        self.api = api
        self.device_id = device_id
        self.device_name = device_name
        self.title.setText(f"<b>{device_name}</b>")
        self._deactivate_live()
        self._clear_plot()
        self._static_built = False
        now = QDateTime.currentDateTime()
        self.end_edit.setDateTime(now)
        self.start_edit.setDateTime(now.addSecs(-3600))
        self.available_channels = []
        self.selected_channels = []
        if api is not None:
            self._load_channels()
            # A device always opens in real-time mode.
            self._static_built = False
            if not self.live_button.isChecked():
                self.live_button.setChecked(True)  # triggers _start_live
            else:
                self._start_live()
        else:
            self._update_channels_tooltip()

    # -- channels -----------------------------------------------------------
    def _load_channels(self) -> None:
        try:
            channels = self.api.channels(self.device_id) if self.api else []
        except ServerApiError:
            channels = []
        self.available_channels = channels
        self.selected_channels = list(channels)
        self._update_channels_tooltip()

    def _update_channels_tooltip(self) -> None:
        text = ", ".join(self.selected_channels) if self.selected_channels else "(все)"
        self.channel_button.setToolTip(f"Каналы: {text}")

    def _choose_channels(self) -> None:
        if not self.available_channels:
            QMessageBox.information(self, "Каналы", "У устройства нет доступных каналов.")
            return
        dialog = ChannelDialog(self.available_channels, self.selected_channels, parent=self)
        if dialog.exec():
            self.selected_channels = dialog.selected_channels()
            self._update_channels_tooltip()

    # -- static plotting ----------------------------------------------------
    def _build_static(self) -> None:
        self._deactivate_live()
        if self.autoscale_button.isChecked():
            self.autoscale_button.setChecked(False)
        start = self.start_edit.dateTime().toPython()
        end = self.end_edit.dateTime().toPython()
        if end <= start:
            start, end = end, start
        try:
            series = self.api.data(self.device_id, start, end, self.selected_channels or None)
        except ServerApiError as exc:
            QMessageBox.warning(self, "Ошибка", str(exc))
            return
        if not series:
            self._set_status("За указанный период данные не найдены")
            return
        self._plot_series(series)
        self._apply_time_window(start, end)
        self._autoscale_y()
        self._static_built = True
        self._set_status(
            f"Статичный график: {len(series)} канал(ов) за {start:%d.%m.%Y %H:%M} — {end:%d.%m.%Y %H:%M}"
        )

    def _clear_plot(self) -> None:
        self.plot.clear()
        self.curves.clear()
        if self._legend is not None:
            self._legend.clear()
        self._style_legend()

    def _plot_series(self, series: dict[str, TimeSeries]) -> None:
        self._clear_plot()
        for index, (channel, ts) in enumerate(sorted(series.items())):
            times, values = ts.numeric()
            if not times:
                continue
            xs = [moment.timestamp() for moment in times]
            self.curves[channel] = self.plot.plot(
                xs,
                values,
                pen=pg.mkPen(LIVE_COLORS[index % len(LIVE_COLORS)], width=1.6),
                name=channel,
                connect="finite",
            )

    def _apply_time_window(self, start: datetime, end: datetime) -> None:
        """Limit the visible time span to 24 h (+10%) and leave zoom headroom."""

        view_start = clamp_period_start(start, end)
        self.plot.setXRange(view_start.timestamp(), end.timestamp(), padding=0.0)
        pad_start, pad_end = with_margin(view_start, end, 0.1)
        self.plot.setLimits(xMin=pad_start.timestamp(), xMax=pad_end.timestamp())

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

    def _on_autoscale_toggled(self, checked: bool) -> None:
        """Mirror pyqtgraph's auto-range button (the small 'A')."""

        viewbox = self.plot.getPlotItem().getViewBox()
        if checked:
            viewbox.enableAutoRange(enable=True)
            viewbox.updateAutoRange()
        else:
            viewbox.enableAutoRange(enable=False)

    def _on_grid_toggled(self, checked: bool) -> None:
        """Hide/show the coordinate grid (works in both static and live mode)."""

        self.plot.getPlotItem().showGrid(x=not checked, y=not checked, alpha=GRID_ALPHA)

    # -- live mode ----------------------------------------------------------
    def _update_live_style(self) -> None:
        self.live_button.setStyleSheet(
            LIVE_ON_STYLE if self.live_button.isChecked() else LIVE_OFF_STYLE
        )

    def _deactivate_live(self) -> None:
        self.live_timer.stop()
        self.live_mode = False
        if self.live_button.isChecked():
            self.live_button.blockSignals(True)
            self.live_button.setChecked(False)
            self.live_button.blockSignals(False)
        self._update_live_style()

    def _on_live_toggled(self, checked: bool) -> None:
        if checked and self._static_built:
            answer = QMessageBox.question(
                self,
                "Режим реального времени",
                "Вы точно хотите перейти в режим просмотра графика в реальном времени? "
                "Построенная ранее диаграмма будет закрыта. Продолжить?",
            )
            if answer != QMessageBox.Yes:
                self.live_button.blockSignals(True)
                self.live_button.setChecked(False)
                self.live_button.blockSignals(False)
                self._update_live_style()
                return
        self._update_live_style()
        if checked:
            self._start_live()
        else:
            self.live_timer.stop()
            self.live_mode = False
            self._set_status("Режим реального времени остановлен")

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
        self.live_mode = True
        self._static_built = False
        self.live_timer.start()
        self._set_status("Режим реального времени запущен")
        self._poll_live()

    def _poll_live(self) -> None:
        if self.api is None:
            return
        try:
            payload = self.api.latest(self.device_id)
        except ServerApiError as exc:
            self._set_status(str(exc))
            return
        moment = payload.get("last_success")
        if not moment:
            self._set_status("Ожидание данных...")
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
        self._follow_live(timestamp)
        if payload.get("online"):
            self._set_status(
                f"Онлайн. Обновлено: {datetime.fromisoformat(str(moment)):%H:%M:%S}"
            )
        else:
            self._set_status("Устройство не в сети")

    def _follow_live(self, latest: float) -> None:
        """Scroll the live window so the newest point sits at 80% of the width.

        The remaining 20% on the right is free space, so the end of the graph is
        always visually clear.
        """

        span = LIVE_WINDOW_SECONDS
        x_max = latest + span * LIVE_RIGHT_MARGIN
        x_min = x_max - span
        self.plot.setXRange(x_min, x_max, padding=0.0)

    # -- report (PDF / print) ----------------------------------------------
    def _report_lines(self) -> list[str]:
        start = self.start_edit.dateTime().toPython()
        end = self.end_edit.dateTime().toPython()
        return build_report_lines(self.device_name, start, end, self.selected_channels)

    def _paint_report(self, painter: QPainter, rect: QRectF, pixmap: QPixmap, lines: list[str]) -> None:
        """Draw a compact header at the top and let the graph fill the sheet."""

        painter.fillRect(rect, Qt.white)
        painter.setPen(Qt.black)
        margin = rect.width() * 0.015
        x = rect.left() + margin
        y = rect.top() + margin
        width = rect.width() - 2 * margin
        base = rect.height() * 0.018

        title_font = QFont()
        title_font.setPixelSize(max(10, int(base * 1.3)))
        title_font.setBold(True)
        info_font = QFont()
        info_font.setPixelSize(max(8, int(base * 0.95)))

        painter.setFont(title_font)
        painter.drawText(int(x), int(y + base * 1.3), lines[0])

        info = "   |   ".join(lines[1:])
        painter.setFont(info_font)
        painter.drawText(int(x), int(y + base * 2.7), info)

        graph_y = y + base * 3.6
        graph_h = rect.bottom() - margin - graph_y
        if pixmap is not None and not pixmap.isNull() and graph_h > 0:
            scaled = pixmap.scaled(
                int(width), int(graph_h), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            painter.drawPixmap(int(x), int(graph_y), scaled)

    def _save_pdf(self) -> None:
        default_name = f"{self.device_name or 'graph'}_{datetime.now():%Y%m%d_%H%M%S}.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить график в PDF", default_name, "PDF (*.pdf)")
        if not path:
            return
        pixmap = self.plot.grab()
        lines = self._report_lines()
        writer = QPdfWriter(path)
        writer.setPageSize(QPageSize(QPageSize.A4))
        writer.setPageOrientation(QPageLayout.Landscape)
        writer.setResolution(300)
        painter = QPainter(writer)
        try:
            rect = QRectF(0, 0, writer.width(), writer.height())
            self._paint_report(painter, rect, pixmap, lines)
        finally:
            painter.end()
        self._set_status(f"График сохранён: {path}")

    def _print_preview(self) -> None:
        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageSize(QPageSize(QPageSize.A4))
        printer.setPageOrientation(QPageLayout.Landscape)
        dialog = QPrintPreviewDialog(printer, self)
        dialog.paintRequested.connect(self._print_report)
        dialog.setWindowState(Qt.WindowMaximized)
        dialog.exec()

    def _print_report(self, printer: QPrinter) -> None:
        pixmap = self.plot.grab()
        lines = self._report_lines()
        painter = QPainter(printer)
        try:
            rect = QRectF(printer.pageRect(QPrinter.DevicePixel))
            self._paint_report(painter, rect, pixmap, lines)
        finally:
            painter.end()

    # -- misc ---------------------------------------------------------------
    def _set_status(self, message: str) -> None:
        window = self.window()
        if hasattr(window, "statusBar"):
            window.statusBar().showMessage(message)

    def stop(self) -> None:
        self.live_timer.stop()
