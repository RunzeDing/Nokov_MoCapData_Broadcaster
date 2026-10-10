"""Rolling time-series plot for one rigid body (pure QPainter)."""

from __future__ import annotations

from ...i18n import tr

import math
from typing import List, Optional, Sequence, Tuple

from PySide2.QtCore import QPointF, QRectF, Qt
from PySide2.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide2.QtWidgets import QSizePolicy, QWidget

from ...core.hub import SERIES_FIELDS, SERIES_INDEX
from .. import theme

def channel_label(channel: str) -> str:
    """Localised axis label; looked up on every repaint so it follows the language."""
    return tr(_CHANNEL_LABELS_SOURCE.get(channel, channel))


_CHANNEL_LABELS_SOURCE = {
    "x": "位置 X (m)",
    "y": "位置 Y (m)",
    "z": "位置 Z (m)",
    "vx": "速度 vx (m/s)",
    "vy": "速度 vy (m/s)",
    "vz": "速度 vz (m/s)",
    "ax": "加速度 ax (m/s²)",
    "ay": "加速度 ay (m/s²)",
    "az": "加速度 az (m/s²)",
    "roll": "横滚 (deg)",
    "pitch": "俯仰 (deg)",
    "yaw": "偏航 (deg)",
    "speed": "速度大小 (m/s)",
}

_CHANNEL_PALETTE = (
    "#ff5c6c", "#3ddc97", "#3ea6ff",
    "#ffb020", "#00d4d4", "#b47cff",
    "#ff8ac4", "#8ee04a", "#7fa8ff",
    "#e0e04a", "#4ae0c0", "#ff9a52",
    "#dfe6f2",
)


def channel_color(channel: str) -> QColor:
    try:
        index = SERIES_FIELDS.index(channel)
    except ValueError:
        index = 0
    return QColor(_CHANNEL_PALETTE[index % len(_CHANNEL_PALETTE)])


def _nice_step(span: float, target_ticks: int) -> float:
    if span <= 0 or target_ticks <= 0:
        return 1.0
    rough = span / target_ticks
    magnitude = 10.0 ** math.floor(math.log10(rough))
    for factor in (1.0, 2.0, 2.5, 5.0, 10.0):
        if rough <= factor * magnitude:
            return factor * magnitude
    return 10.0 * magnitude


class Scope(QWidget):
    """Scrolls a fixed time window of samples for the selected channels."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._samples: List[Tuple[float, ...]] = []
        self._channels: List[str] = ["x", "y", "z"]
        self._window = 5.0
        self._title = ""
        self._paused = False

    # ------------------------------------------------------------------ #
    def set_samples(self, samples: Sequence[Tuple[float, ...]], title: str = "") -> None:
        self._samples = list(samples)
        self._title = title
        self._paused = False
        self.update()

    def set_channels(self, channels: Sequence[str]) -> None:
        self._channels = [channel for channel in channels if channel in SERIES_INDEX]
        self.update()

    def channels(self) -> List[str]:
        return list(self._channels)

    def set_window(self, seconds: float) -> None:
        self._window = max(0.5, float(seconds))
        self.update()

    def clear(self) -> None:
        self._samples = []
        self.update()

    # ------------------------------------------------------------------ #
    def _visible(self) -> List[Tuple[float, ...]]:
        if not self._samples:
            return []
        latest = self._samples[-1][0]
        cutoff = latest - self._window
        # samples are time ordered; binary search would be overkill for ~1500 rows
        start = 0
        for index in range(len(self._samples) - 1, -1, -1):
            if self._samples[index][0] < cutoff:
                start = index + 1
                break
        return self._samples[start:]

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#0d1017"))

        left, right, top, bottom = 58.0, 10.0, 22.0, 22.0
        plot = QRectF(left, top, max(10.0, self.width() - left - right),
                      max(10.0, self.height() - top - bottom))

        samples = self._visible()
        if not samples or not self._channels:
            painter.setPen(QColor(theme.TEXT_DIM))
            painter.setFont(QFont("", 10))
            painter.drawText(self.rect(), Qt.AlignCenter, tr("选择刚体后显示实时曲线"))
            self._draw_title(painter, plot)
            painter.end()
            return

        indices = [(channel, SERIES_INDEX[channel]) for channel in self._channels]
        ymin = float("inf")
        ymax = float("-inf")
        for sample in samples:
            for _channel, index in indices:
                if index < len(sample):
                    value = sample[index]
                    ymin = min(ymin, value)
                    ymax = max(ymax, value)
        if not math.isfinite(ymin) or not math.isfinite(ymax):
            ymin, ymax = -1.0, 1.0
        if ymax - ymin < 1e-9:
            center = 0.5 * (ymin + ymax)
            ymin, ymax = center - 0.05, center + 0.05
        padding = (ymax - ymin) * 0.12
        ymin -= padding
        ymax += padding

        t_end = samples[-1][0]
        t_start = t_end - self._window

        self._draw_grid(painter, plot, ymin, ymax, t_start, t_end)

        # clip and draw the traces
        painter.save()
        painter.setClipRect(plot)
        for channel, index in indices:
            path = QPainterPath()
            started = False
            for sample in samples:
                if index >= len(sample):
                    continue
                value = sample[index]
                if value < ymin - 1e6 and value > ymax + 1e6:
                    continue
                fraction_x = (sample[0] - t_start) / max(1e-9, (t_end - t_start))
                fraction_y = (value - ymin) / max(1e-12, (ymax - ymin))
                x = plot.left() + fraction_x * plot.width()
                y = plot.bottom() - fraction_y * plot.height()
                if not started:
                    path.moveTo(x, y)
                    started = True
                else:
                    path.lineTo(x, y)
            pen = QPen(channel_color(channel))
            pen.setWidthF(1.7)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
        painter.restore()

        self._draw_legend(painter, plot, indices, samples)
        self._draw_title(painter, plot)
        painter.end()

    def _draw_title(self, painter: QPainter, plot: QRectF) -> None:
        if not self._title:
            return
        painter.setPen(QColor(theme.TEXT_DIM))
        painter.setFont(QFont("", 9))
        painter.drawText(QPointF(plot.left(), 14), self._title)

    def _draw_grid(self, painter: QPainter, plot: QRectF, ymin: float, ymax: float,
                   t_start: float, t_end: float) -> None:
        pen = QPen(QColor(38, 48, 64))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setFont(QFont("", 8))

        span = ymax - ymin
        step = _nice_step(span, 5)
        first = math.ceil(ymin / step) * step
        value = first
        while value <= ymax + 1e-9:
            fraction = (value - ymin) / max(1e-12, span)
            y = plot.bottom() - fraction * plot.height()
            painter.setPen(pen)
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor(theme.TEXT_DIM))
            label = ("%+.3f" % value) if abs(step) < 0.1 else ("%+.2f" % value)
            painter.drawText(QPointF(4, y + 3), label)
            value += step

        time_step = _nice_step(max(1e-6, t_end - t_start), 5)
        tick = math.ceil(t_start / time_step) * time_step
        while tick <= t_end + 1e-9:
            fraction = (tick - t_start) / max(1e-9, (t_end - t_start))
            x = plot.left() + fraction * plot.width()
            painter.setPen(pen)
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            painter.setPen(QColor(theme.TEXT_DIM))
            painter.drawText(QPointF(x - 14, plot.bottom() + 14), "%.1fs" % (tick - t_end))
            tick += time_step

        painter.setPen(QPen(QColor(theme.BORDER)))
        painter.drawRect(plot)

    def _draw_legend(self, painter: QPainter, plot: QRectF, indices, samples) -> None:
        painter.setFont(QFont("", 8))
        x = plot.right() - 4
        y = plot.top() + 12
        for channel, index in reversed(indices):
            latest = samples[-1]
            value = latest[index] if index < len(latest) else float("nan")
            text = "%s  %+.4f" % (channel_label(channel), value)
            metrics = painter.fontMetrics()
            width = metrics.horizontalAdvance(text) + 8
            painter.setPen(channel_color(channel))
            painter.drawText(QPointF(x - width, y), text)
            y += 14
