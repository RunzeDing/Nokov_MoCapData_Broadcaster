"""Auto-generated settings form for an output format.

Widgets are derived from :class:`~app.core.formats.base.ParamSpec` metadata so a
new format only has to describe its parameters once, in the core.
"""

from __future__ import annotations

from ...i18n import tr

from typing import Any, Dict, List, Optional

from PySide2.QtCore import Qt, Signal
from PySide2.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.formats import DTYPES, Encoder, FieldSpec, ParamSpec
from .. import theme
from .cards import HintLabel

def field_columns():
    return (tr("数据量"), tr("类型"), tr("缩放"), tr("偏移"), tr("饱和"))


class FieldListEditor(QWidget):
    """Editor for the custom format's per-body field list."""

    changed = Signal()

    def __init__(self, quantity_choices, dtype_choices, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._quantity_choices = list(quantity_choices)
        self._dtype_choices = list(dtype_choices)
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.table = QTableWidget(0, len(field_columns()))
        self.table.setHorizontalHeaderLabels(list(field_columns()))
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setMinimumHeight(170)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for index in range(1, len(field_columns())):
            header.setSectionResizeMode(index, QHeaderView.ResizeToContents)
        layout.addWidget(self.table)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        self.add_button = QPushButton(tr("添加字段"))
        self.remove_button = QPushButton(tr("删除选中"))
        self.up_button = QPushButton(tr("上移"))
        self.down_button = QPushButton(tr("下移"))
        self.reset_button = QPushButton(tr("恢复默认"))
        for button in (self.add_button, self.remove_button, self.up_button,
                       self.down_button, self.reset_button):
            button.setAutoDefault(False)
        self.add_button.clicked.connect(self._on_add)
        self.remove_button.clicked.connect(self._on_remove)
        self.up_button.clicked.connect(lambda: self._on_move(-1))
        self.down_button.clicked.connect(lambda: self._on_move(1))
        self.reset_button.clicked.connect(self._on_reset)
        for button in (self.add_button, self.remove_button, self.up_button,
                       self.down_button, self.reset_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        layout.addWidget(HintLabel(
            tr("每行一个字段，顺序即报文中的字节顺序。位置单位为米、速度 m/s、"
            "角度为度；缩放系数决定定点数精度（例如 int16 × 2000 表示 0.0005 m 的分辨率）。")
        ))

    # ------------------------------------------------------------------ #
    def _make_row_widgets(self, spec: FieldSpec):
        quantity = QComboBox()
        for value, label in self._quantity_choices:
            quantity.addItem(label, value)
        index = quantity.findData(spec.quantity)
        quantity.setCurrentIndex(index if index >= 0 else 0)
        quantity.currentIndexChanged.connect(self._emit)

        dtype = QComboBox()
        for value, label in self._dtype_choices:
            dtype.addItem(label, value)
        index = dtype.findData(spec.dtype)
        dtype.setCurrentIndex(index if index >= 0 else 0)
        dtype.currentIndexChanged.connect(self._emit)

        scale = QDoubleSpinBox()
        scale.setDecimals(6)
        scale.setRange(-1e9, 1e9)
        scale.setValue(spec.scale)
        scale.setKeyboardTracking(False)
        scale.valueChanged.connect(self._emit)

        offset = QDoubleSpinBox()
        offset.setDecimals(6)
        offset.setRange(-1e9, 1e9)
        offset.setValue(spec.offset)
        offset.setKeyboardTracking(False)
        offset.valueChanged.connect(self._emit)

        clamp = QCheckBox()
        clamp.setChecked(spec.clamp)
        clamp.toggled.connect(self._emit)

        return quantity, dtype, scale, offset, clamp

    def _emit(self, *_args) -> None:
        if not self._loading:
            self.changed.emit()

    # ------------------------------------------------------------------ #
    def set_values(self, fields: List[Dict[str, Any]]) -> None:
        self._loading = True
        try:
            self.table.setRowCount(0)
            for raw in fields or []:
                self._append(FieldSpec.from_dict(raw))
        finally:
            self._loading = False

    def _append(self, spec: FieldSpec) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        quantity, dtype, scale, offset, clamp = self._make_row_widgets(spec)
        self.table.setCellWidget(row, 0, quantity)
        self.table.setCellWidget(row, 1, dtype)
        self.table.setCellWidget(row, 2, scale)
        self.table.setCellWidget(row, 3, offset)
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.addWidget(clamp)
        layout.addStretch(1)
        self.table.setCellWidget(row, 4, container)

    def values(self) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        for row in range(self.table.rowCount()):
            quantity = self.table.cellWidget(row, 0)
            dtype = self.table.cellWidget(row, 1)
            scale = self.table.cellWidget(row, 2)
            offset = self.table.cellWidget(row, 3)
            container = self.table.cellWidget(row, 4)
            clamp = container.findChild(QCheckBox) if container else None
            result.append({
                "quantity": quantity.currentData(),
                "dtype": dtype.currentData(),
                "scale": float(scale.value()),
                "offset": float(offset.value()),
                "clamp": bool(clamp.isChecked()) if clamp else True,
            })
        return result

    # ------------------------------------------------------------------ #
    def _selected_row(self) -> int:
        rows = {index.row() for index in self.table.selectedIndexes()}
        return min(rows) if rows else -1

    def _on_add(self) -> None:
        self._append(FieldSpec("x", "int16", 2000.0, 0.0, True))
        self.table.selectRow(self.table.rowCount() - 1)
        self.changed.emit()

    def _on_remove(self) -> None:
        row = self._selected_row()
        if row < 0:
            return
        self.table.removeRow(row)
        self.changed.emit()

    def _on_move(self, delta: int) -> None:
        row = self._selected_row()
        target = row + delta
        if row < 0 or not (0 <= target < self.table.rowCount()):
            return
        specs = [FieldSpec.from_dict(item) for item in self.values()]
        specs[row], specs[target] = specs[target], specs[row]
        self.set_values([spec.to_dict() for spec in specs])
        self.table.selectRow(target)
        self.changed.emit()

    def _on_reset(self) -> None:
        from ...core.formats.custom_bin import DEFAULT_FIELDS
        self.set_values([dict(item) for item in DEFAULT_FIELDS])
        self.changed.emit()


class FormatParamsWidget(QWidget):
    """Renders every :class:`ParamSpec` of an encoder."""

    changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(10)
        self._widgets: Dict[str, QWidget] = {}
        self._encoder: Optional[Encoder] = None
        self._loading = False

    # ------------------------------------------------------------------ #
    def set_encoder(self, encoder: Encoder, params: Dict[str, Any]) -> None:
        self._encoder = encoder
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._widgets = {}

        self._loading = True
        try:
            groups: Dict[str, List[ParamSpec]] = {}
            order: List[str] = []
            for spec in encoder.param_specs():
                group = spec.group or tr("参数")
                if group not in groups:
                    groups[group] = []
                    order.append(group)
                groups[group].append(spec)

            merged = encoder.normalize_params(params)
            for group in order:
                box = QGroupBox(group)
                form = QFormLayout(box)
                form.setContentsMargins(12, 8, 12, 10)
                form.setSpacing(7)
                form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
                form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
                for spec in groups[group]:
                    widget = self._make_widget(spec, merged.get(spec.key, spec.default))
                    self._widgets[spec.key] = widget
                    if spec.kind == "fieldlist":
                        form.addRow(widget)
                    else:
                        label = QLabel(spec.label)
                        if spec.help:
                            label.setToolTip(spec.help)
                            widget.setToolTip(spec.help)
                        form.addRow(label, widget)
                self._layout.addWidget(box)
            self._layout.addStretch(1)
        finally:
            self._loading = False

    def _make_widget(self, spec: ParamSpec, value: Any) -> QWidget:
        kind = spec.kind
        if kind == "bool":
            widget = QCheckBox()
            widget.setChecked(bool(value))
            widget.toggled.connect(self._emit)
            return widget
        if kind == "int":
            widget = QSpinBox()
            widget.setRange(
                int(spec.minimum if spec.minimum is not None else -2147483647),
                int(spec.maximum if spec.maximum is not None else 2147483647),
            )
            widget.setValue(int(value or 0))
            widget.setKeyboardTracking(False)
            widget.valueChanged.connect(self._emit)
            return widget
        if kind == "float":
            widget = QDoubleSpinBox()
            widget.setRange(
                spec.minimum if spec.minimum is not None else -1e9,
                spec.maximum if spec.maximum is not None else 1e9,
            )
            widget.setDecimals(spec.decimals)
            widget.setSingleStep(spec.step if spec.step else 10 ** (-spec.decimals))
            widget.setValue(float(value if value is not None else 0.0))
            widget.setKeyboardTracking(False)
            widget.valueChanged.connect(self._emit)
            return widget
        if kind == "choice":
            widget = QComboBox()
            for choice_value, label in spec.choices:
                widget.addItem(label, choice_value)
            index = widget.findData(value)
            widget.setCurrentIndex(index if index >= 0 else 0)
            widget.currentIndexChanged.connect(self._emit)
            return widget
        if kind == "fieldlist":
            widget = FieldListEditor(spec.choices,
                                     [(key, tr("%s (%d字节)") % (key, DTYPES[key][1]))
                                      for key in DTYPES])
            fields = value if isinstance(value, list) else spec.default
            widget.set_values([dict(item) for item in fields or []])
            widget.changed.connect(self._emit)
            return widget
        widget = QLineEdit(str(value if value is not None else ""))
        if kind == "hex":
            widget.setFont(theme.mono_font(9))
            widget.setPlaceholderText(tr("例如 AA 55"))
        widget.textChanged.connect(self._emit)
        return widget

    def _emit(self, *_args) -> None:
        if not self._loading:
            self.changed.emit()

    # ------------------------------------------------------------------ #
    def params(self) -> Dict[str, Any]:
        if self._encoder is None:
            return {}
        result: Dict[str, Any] = {}
        for spec in self._encoder.param_specs():
            widget = self._widgets.get(spec.key)
            if widget is None:
                continue
            if spec.kind == "bool":
                result[spec.key] = bool(widget.isChecked())
            elif spec.kind == "int":
                result[spec.key] = int(widget.value())
            elif spec.kind == "float":
                result[spec.key] = float(widget.value())
            elif spec.kind == "choice":
                result[spec.key] = widget.currentData()
            elif spec.kind == "fieldlist":
                result[spec.key] = widget.values()
            else:
                result[spec.key] = widget.text()
        return result
