"""Declarative forms bound to configuration dataclasses.

Pages describe their options once as :class:`FieldDef` objects; :class:`FormBuilder`
creates the widgets, loads values from a config section and writes them back.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from PySide2.QtCore import Qt, Signal
from PySide2.QtGui import QFont
from PySide2.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import theme


class FieldDef:
    """Description of one configurable value."""

    __slots__ = (
        "key", "label", "kind", "minimum", "maximum", "decimals", "step",
        "choices", "suffix", "tooltip", "placeholder", "formatter", "parser",
        "grow",
    )

    def __init__(
        self,
        key: str,
        label: str,
        kind: str = "float",
        minimum: Optional[float] = None,
        maximum: Optional[float] = None,
        decimals: int = 3,
        step: Optional[float] = None,
        choices: Optional[Sequence[Tuple[Any, str]]] = None,
        suffix: str = "",
        tooltip: str = "",
        placeholder: str = "",
        formatter: Optional[Callable[[Any], str]] = None,
        parser: Optional[Callable[[str], Any]] = None,
        grow: bool = False,
    ) -> None:
        self.key = key
        self.label = label
        self.kind = kind  # int|float|bool|str|choice|ids|hex|info
        self.minimum = minimum
        self.maximum = maximum
        self.decimals = decimals
        self.step = step
        self.choices = list(choices or [])
        self.suffix = suffix
        self.tooltip = tooltip
        self.placeholder = placeholder
        self.formatter = formatter
        self.parser = parser
        self.grow = grow


class FormBuilder(QWidget):
    """Widgets for a list of :class:`FieldDef`, bound to one config object."""

    changed = Signal()

    def __init__(self, fields: Sequence[FieldDef], columns: int = 1,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._fields = list(fields)
        self._widgets: Dict[str, QWidget] = {}
        self._labels: Dict[str, QLabel] = {}
        self._loading = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        # split into `columns` independent form layouts
        per_column = max(1, (len(self._fields) + columns - 1) // columns)
        row_layout = QHBoxLayout()
        row_layout.setSpacing(18)
        outer.addLayout(row_layout)

        for index in range(columns):
            chunk = self._fields[index * per_column:(index + 1) * per_column]
            if not chunk:
                continue
            form = QFormLayout()
            form.setContentsMargins(0, 0, 0, 0)
            form.setSpacing(7)
            form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
            form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
            for field in chunk:
                widget = self._make_widget(field)
                self._widgets[field.key] = widget
                label = QLabel(field.label)
                if field.tooltip:
                    label.setToolTip(field.tooltip)
                    widget.setToolTip(field.tooltip)
                self._labels[field.key] = label
                form.addRow(label, widget)
            container = QWidget()
            container.setLayout(form)
            row_layout.addWidget(container, 1)

    # ------------------------------------------------------------------ #
    def _make_widget(self, field: FieldDef) -> QWidget:
        kind = field.kind
        if kind == "bool":
            widget = QCheckBox()
            widget.toggled.connect(self._emit_changed)
            return widget
        if kind == "int":
            widget = QSpinBox()
            widget.setRange(
                int(field.minimum if field.minimum is not None else -2147483647),
                int(field.maximum if field.maximum is not None else 2147483647),
            )
            if field.step:
                widget.setSingleStep(int(field.step))
            widget.setSuffix(field.suffix)
            widget.setKeyboardTracking(False)
            widget.valueChanged.connect(self._emit_changed)
            return widget
        if kind == "float":
            widget = QDoubleSpinBox()
            low = field.minimum if field.minimum is not None else -1e9
            high = field.maximum if field.maximum is not None else 1e9
            widget.setRange(low, high)
            widget.setDecimals(field.decimals)
            widget.setSingleStep(field.step if field.step else 10 ** (-field.decimals))
            widget.setSuffix(field.suffix)
            widget.setKeyboardTracking(False)
            widget.valueChanged.connect(self._emit_changed)
            return widget
        if kind == "choice":
            widget = QComboBox()
            for value, label in field.choices:
                widget.addItem(label, value)
            widget.currentIndexChanged.connect(self._emit_changed)
            return widget
        if kind == "info":
            widget = QLabel("—")
            widget.setStyleSheet("color: %s;" % theme.TEXT_DIM)
            return widget
        # str / ids / hex
        widget = QLineEdit()
        widget.setPlaceholderText(field.placeholder)
        if kind == "hex":
            widget.setFont(theme.mono_font(9))
        if field.grow:
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        widget.textChanged.connect(self._emit_changed)
        return widget

    def _emit_changed(self, *_args) -> None:
        if not self._loading:
            self.changed.emit()

    # ------------------------------------------------------------------ #
    def load(self, section: Any) -> None:
        self._loading = True
        try:
            for field in self._fields:
                widget = self._widgets[field.key]
                value = getattr(section, field.key, None)
                self._set_value(field, widget, value)
        finally:
            self._loading = False

    def _set_value(self, field: FieldDef, widget: QWidget, value: Any) -> None:
        if value is None:
            return
        if field.kind == "bool":
            widget.setChecked(bool(value))
            return
        if field.kind == "int":
            widget.setValue(int(float(value)))
            return
        if field.kind == "float":
            widget.setValue(float(value))
            return
        if field.kind == "choice":
            index = widget.findData(value)
            if index >= 0:
                widget.setCurrentIndex(index)
            return
        if field.kind == "info":
            widget.setText(str(value))
            return
        text = field.formatter(value) if field.formatter else str(value)
        widget.setText(text)

    def collect(self, section: Any) -> None:
        """Write the widget values back into ``section``."""
        for field in self._fields:
            widget = self._widgets[field.key]
            if field.kind == "info":
                continue
            if field.kind == "bool":
                value: Any = widget.isChecked()
            elif field.kind == "int":
                value = widget.value()
            elif field.kind == "float":
                value = widget.value()
            elif field.kind == "choice":
                value = widget.currentData()
            else:
                text = widget.text()
                value = field.parser(text) if field.parser else text
            setattr(section, field.key, value)

    def widget(self, key: str) -> Optional[QWidget]:
        return self._widgets.get(key)

    def label(self, key: str) -> Optional[QLabel]:
        return self._labels.get(key)

    def set_row_visible(self, key: str, visible: bool) -> None:
        widget = self._widgets.get(key)
        label = self._labels.get(key)
        for item in (widget, label):
            if item is not None:
                item.setVisible(visible)

    def set_row_enabled(self, key: str, enabled: bool) -> None:
        widget = self._widgets.get(key)
        label = self._labels.get(key)
        for item in (widget, label):
            if item is not None:
                item.setEnabled(enabled)

    def set_all_enabled(self, enabled: bool) -> None:
        for field in self._fields:
            self.set_row_enabled(field.key, enabled)

    def set_info(self, key: str, text: str) -> None:
        widget = self._widgets.get(key)
        if isinstance(widget, QLabel):
            widget.setText(text)


def field_value(section: Any, key: str, default: Any = None) -> Any:
    return getattr(section, key, default)
