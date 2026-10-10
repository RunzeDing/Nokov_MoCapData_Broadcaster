"""Small reusable widgets: stat tiles, section boxes, hint labels."""

from __future__ import annotations

from typing import Optional

from PySide2.QtCore import Qt
from PySide2.QtGui import QFont
from PySide2.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import theme


class SectionBox(QGroupBox):
    """A group box with an optional explanatory line underneath the title."""

    def __init__(self, title: str, subtitle: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(title, parent)
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(12, 6, 12, 10)
        self._outer.setSpacing(8)
        if subtitle:
            label = QLabel(subtitle)
            label.setWordWrap(True)
            label.setStyleSheet("color: %s; font-size: 11px;" % theme.TEXT_DIM)
            self._outer.addWidget(label)
        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(6)
        self._outer.addLayout(self.body)
        self._outer.addStretch(1)

    def add(self, widget: QWidget) -> QWidget:
        self.body.addWidget(widget)
        return widget

    def add_layout(self, layout) -> None:
        self.body.addLayout(layout)


class StatTile(QFrame):
    """One headline number with a caption."""

    def __init__(self, caption: str, value: str = "—", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            "QFrame { background: %s; border: 1px solid %s; border-radius: 6px; }"
            % (theme.PANEL_ALT, theme.BORDER)
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(1)

        self._caption = QLabel(caption)
        self._caption.setStyleSheet("color: %s; font-size: 11px; border: none;" % theme.TEXT_DIM)
        self._value = QLabel(value)
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        self._value.setFont(font)
        self._value.setStyleSheet("border: none;")
        self._value.setTextInteractionFlags(Qt.TextSelectableByMouse)

        layout.addWidget(self._caption)
        layout.addWidget(self._value)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def set_value(self, text: str, color: Optional[str] = None) -> None:
        self._value.setText(text)
        self._value.setStyleSheet(
            "border: none; color: %s;" % (color or theme.TEXT)
        )


class StatGrid(QWidget):
    """A responsive grid of :class:`StatTile` objects."""

    def __init__(self, captions, columns: int = 4, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        self.tiles = {}
        for index, caption in enumerate(captions):
            tile = StatTile(caption)
            self.tiles[caption] = tile
            self._layout.addWidget(tile, index // columns, index % columns)

    def set(self, caption: str, value: str, color: Optional[str] = None) -> None:
        tile = self.tiles.get(caption)
        if tile is not None:
            tile.set_value(value, color)

    def tile(self, caption: str) -> Optional[StatTile]:
        return self.tiles.get(caption)


class HintLabel(QLabel):
    def __init__(self, text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setStyleSheet("color: %s; font-size: 11px;" % theme.TEXT_DIM)


class Row(QWidget):
    """A horizontal row of widgets with an even stretch between them."""

    def __init__(self, *widgets: QWidget, spacing: int = 8, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing)
        for widget in widgets:
            layout.addWidget(widget)
        layout.addStretch(1)
