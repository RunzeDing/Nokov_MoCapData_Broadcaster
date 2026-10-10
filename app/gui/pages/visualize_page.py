"""Visualisation page: 3D rigid-body view, live traces and a data table."""

from __future__ import annotations

from ...i18n import tr

import logging
from typing import Dict, List, Optional, Tuple

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ...core.transform import CoordinateTransform
from .. import theme
from ..context import AppContext
from ..widgets.body_table import BodyTable
from ..widgets.cards import HintLabel, SectionBox
from ..widgets.scope import Scope, channel_label
from ..widgets.view3d import View3D

log = logging.getLogger("nokov.gui.visualize")

def channel_groups():
    """``(stable_key, localised_label, channels)`` - the key is language neutral."""
    return [
        ("position", tr("位置"), ("x", "y", "z")),
        ("velocity", tr("速度"), ("vx", "vy", "vz")),
        ("acceleration", tr("加速度"), ("ax", "ay", "az")),
        ("orientation", tr("姿态角"), ("roll", "pitch", "yaw")),
        ("speed", tr("速度大小"), ("speed",)),
    ]


class VisualizePage(QWidget):
    def __init__(self, ctx: AppContext, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._next_refresh = 0.0
        self._next_table = 0.0
        self._selected_body = -1
        self._transform = CoordinateTransform(ctx.config.transform)
        self._transform_signature = None
        self._group_buttons: Dict[str, QPushButton] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Vertical, self)

        # ---- top: 3D view ------------------------------------------------ #
        view_container = QWidget()
        view_layout = QVBoxLayout(view_container)
        view_layout.setContentsMargins(0, 0, 0, 0)
        view_layout.setSpacing(6)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.labels_check = QCheckBox(tr("刚体标签"))
        self.labels_check.setChecked(ctx.config.ui.show_labels)
        self.trails_check = QCheckBox(tr("运动拖尾"))
        self.trails_check.setChecked(ctx.config.ui.show_trails)
        self.markers_check = QCheckBox(tr("标记点云"))
        self.markers_check.setChecked(ctx.config.ui.show_markers)
        self.axes_check = QCheckBox(tr("姿态坐标轴"))
        self.axes_check.setChecked(True)
        for check, key in ((self.labels_check, "show_labels"), (self.trails_check, "show_trails"),
                           (self.markers_check, "show_markers")):
            check.toggled.connect(lambda value, name=key: self._on_view_option(name, value))
            toolbar.addWidget(check)
        self.axes_check.toggled.connect(self._on_axes_toggled)
        toolbar.addWidget(self.axes_check)

        self.axis_spin = QDoubleSpinBox()
        self.axis_spin.setRange(0.0, 2.0)
        self.axis_spin.setDecimals(2)
        self.axis_spin.setSingleStep(0.05)
        self.axis_spin.setValue(ctx.config.ui.axis_length_m)
        self.axis_spin.setPrefix(tr("姿态轴长 "))
        self.axis_spin.setSuffix(" m")
        self.axis_spin.setKeyboardTracking(False)
        self.axis_spin.valueChanged.connect(self._on_axis_length)
        toolbar.addWidget(self.axis_spin)

        self.trail_spin = QDoubleSpinBox()
        self.trail_spin.setRange(2, 2000)
        self.trail_spin.setDecimals(0)
        self.trail_spin.setValue(ctx.config.ui.trail_length)
        self.trail_spin.setPrefix(tr("拖尾 "))
        self.trail_spin.setSuffix(tr(" 点"))
        self.trail_spin.setKeyboardTracking(False)
        self.trail_spin.valueChanged.connect(self._on_trail_length)
        toolbar.addWidget(self.trail_spin)

        fit_button = QPushButton(tr("自动适配视角"))
        fit_button.clicked.connect(lambda: self.view.auto_fit() if hasattr(self, "view") else None)
        reset_button = QPushButton(tr("重置视角"))
        reset_button.clicked.connect(lambda: self.view.reset_view() if hasattr(self, "view") else None)
        self._fit_button = fit_button
        self._reset_button = reset_button
        toolbar.addWidget(fit_button)
        toolbar.addWidget(reset_button)
        toolbar.addStretch(1)

        self.view = View3D()
        self.view.show_labels = ctx.config.ui.show_labels
        self.view.show_trails = ctx.config.ui.show_trails
        self.view.show_markers = ctx.config.ui.show_markers
        self.view.axis_length = ctx.config.ui.axis_length_m
        self.view.max_draw_bodies = ctx.config.ui.max_draw_bodies
        self.view.bodyPicked.connect(self._on_body_picked)
        self._fit_button.clicked.connect(self.view.auto_fit)
        self._reset_button.clicked.connect(self.view.reset_view)

        view_layout.addLayout(toolbar)
        view_layout.addWidget(self.view, 1)
        splitter.addWidget(view_container)

        # ---- bottom: table + scope -------------------------------------- #
        bottom = QSplitter(Qt.Horizontal)

        table_box = SectionBox(tr("刚体数据"), tr("实时数值与质量指标；双击不在列表中时可用上方下拉框选择。"))
        self.body_table = BodyTable()
        self.body_table.bodySelected.connect(self._on_body_picked)
        table_box.add(self.body_table)
        bottom.addWidget(table_box)

        scope_container = QWidget()
        scope_layout = QVBoxLayout(scope_container)
        scope_layout.setContentsMargins(0, 0, 0, 0)
        scope_layout.setSpacing(6)

        selector_row = QHBoxLayout()
        selector_row.setSpacing(8)
        selector_row.addWidget(QLabel(tr("曲线刚体")))
        self.body_combo = QComboBox()
        self.body_combo.setMinimumWidth(160)
        self.body_combo.currentIndexChanged.connect(self._on_body_combo)
        selector_row.addWidget(self.body_combo)

        for group_key, label, channels in channel_groups():
            button = QPushButton(label)
            button.setCheckable(True)
            button.setChecked(group_key in ("position", "velocity"))
            button.toggled.connect(self._on_channel_toggle)
            self._group_buttons[group_key] = button
            selector_row.addWidget(button)

        self.window_spin = QDoubleSpinBox()
        self.window_spin.setRange(0.5, 120.0)
        self.window_spin.setDecimals(1)
        self.window_spin.setValue(ctx.config.ui.plot_window_s)
        self.window_spin.setSuffix(tr(" 秒窗口"))
        self.window_spin.setKeyboardTracking(False)
        self.window_spin.valueChanged.connect(self._on_window_changed)
        selector_row.addWidget(self.window_spin)
        selector_row.addStretch(1)
        scope_layout.addLayout(selector_row)

        self.scope = Scope()
        self.scope.set_window(ctx.config.ui.plot_window_s)
        scope_layout.addWidget(self.scope, 1)

        self.scope_hint = HintLabel("")
        scope_layout.addWidget(self.scope_hint)
        self._sync_channels()
        bottom.addWidget(scope_container)
        bottom.setStretchFactor(0, 3)
        bottom.setStretchFactor(1, 4)
        splitter.addWidget(bottom)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        root.addWidget(splitter, 1)

    # ------------------------------------------------------------------ #
    def _on_view_option(self, name: str, value: bool) -> None:
        setattr(self.ctx.config.ui, name, bool(value))
        self.view.set_view_options(**{name: bool(value)})
        if name == "show_markers":
            self.ctx.session.capture_markers = bool(value)
        self.ctx.config_changed()

    def _on_axes_toggled(self, checked: bool) -> None:
        self.axis_spin.setEnabled(checked)
        self.view.set_view_options(axis_length=self.axis_spin.value() if checked else 0.0)

    def _on_axis_length(self, value: float) -> None:
        self.ctx.config.ui.axis_length_m = float(value)
        if self.axes_check.isChecked():
            self.view.set_view_options(axis_length=float(value))
        self.ctx.config_changed()

    def _on_trail_length(self, value: float) -> None:
        self.ctx.config.ui.trail_length = int(value)
        self.ctx.config_changed()

    def _on_window_changed(self, value: float) -> None:
        self.ctx.config.ui.plot_window_s = float(value)
        self.scope.set_window(float(value))
        self.ctx.config_changed()

    def _on_channel_toggle(self, _checked: bool) -> None:
        self._sync_channels()

    def _sync_channels(self) -> None:
        channels: List[str] = []
        for group_key, _label, group in channel_groups():
            button = self._group_buttons.get(group_key)
            if button is not None and button.isChecked():
                channels.extend(group)
        self.scope.set_channels(channels)
        labels = "、".join(channel_label(channel) for channel in channels)
        self.scope_hint.setText(tr("已选通道：%s") % labels if labels else tr("未选择任何通道"))

    # ------------------------------------------------------------------ #
    def _on_body_picked(self, body_id: int) -> None:
        self._selected_body = int(body_id)
        self.view.set_selected(self._selected_body)
        if body_id >= 0:
            index = self.body_combo.findData(body_id)
            if index >= 0 and index != self.body_combo.currentIndex():
                self.body_combo.blockSignals(True)
                self.body_combo.setCurrentIndex(index)
                self.body_combo.blockSignals(False)
            self.body_table.select_body(body_id)

    def _on_body_combo(self, _index: int) -> None:
        value = self.body_combo.currentData()
        if value is None:
            return
        self._on_body_picked(int(value))

    def _refresh_body_combo(self, frame, known: Dict[int, str]) -> None:
        ids = set()
        if frame is not None:
            ids.update(frame.bodies)
        ids.update(known or {})
        if not ids:
            return
        wanted = sorted(ids)
        current = [self.body_combo.itemData(index) for index in range(self.body_combo.count())]
        if current == wanted:
            return
        self.body_combo.blockSignals(True)
        self.body_combo.clear()
        for body_id in wanted:
            name = ""
            if frame is not None and body_id in frame.bodies:
                name = frame.bodies[body_id].name
            name = name or (known or {}).get(body_id, "")
            label = ("%d  %s" % (body_id, name)).strip() if name else str(body_id)
            self.body_combo.addItem(label, body_id)
        index = self.body_combo.findData(self._selected_body)
        if index >= 0:
            self.body_combo.setCurrentIndex(index)
        elif self.body_combo.count() and self._selected_body < 0:
            self.body_combo.setCurrentIndex(0)
            self._selected_body = int(self.body_combo.itemData(0) or -1)
            self.view.set_selected(self._selected_body)
        self.body_combo.blockSignals(False)

    # ------------------------------------------------------------------ #
    def _sync_transform(self) -> None:
        signature = (
            self.ctx.config.transform.axis_map,
            self.ctx.config.transform.sign_x,
            self.ctx.config.transform.sign_y,
            self.ctx.config.transform.sign_z,
            self.ctx.config.transform.unit_scale,
            self.ctx.config.transform.offset_x,
            self.ctx.config.transform.offset_y,
            self.ctx.config.transform.offset_z,
            self.ctx.config.transform.yaw_deg,
        )
        if signature != self._transform_signature:
            self._transform_signature = signature
            self._transform.update(self.ctx.config.transform)

    def reload_from_config(self) -> None:
        ui = self.ctx.config.ui
        for check, value in ((self.labels_check, ui.show_labels),
                             (self.trails_check, ui.show_trails),
                             (self.markers_check, ui.show_markers)):
            check.blockSignals(True)
            check.setChecked(bool(value))
            check.blockSignals(False)
        self.axis_spin.blockSignals(True)
        self.axis_spin.setValue(ui.axis_length_m)
        self.axis_spin.blockSignals(False)
        self.trail_spin.blockSignals(True)
        self.trail_spin.setValue(ui.trail_length)
        self.trail_spin.blockSignals(False)
        self.window_spin.blockSignals(True)
        self.window_spin.setValue(ui.plot_window_s)
        self.window_spin.blockSignals(False)
        self.view.set_view_options(
            show_labels=ui.show_labels,
            show_trails=ui.show_trails,
            show_markers=ui.show_markers,
            axis_length=ui.axis_length_m,
            max_draw_bodies=ui.max_draw_bodies,
        )
        self.scope.set_window(ui.plot_window_s)

    def refresh(self, now: float) -> None:
        if now < self._next_refresh:
            return
        refresh_hz = max(5, int(self.ctx.config.ui.refresh_hz))
        self._next_refresh = now + 1.0 / refresh_hz

        self._sync_transform()
        _seq, frame = self.ctx.hub.latest_processed()
        known = self.ctx.engine.pipeline.known_names or self.ctx.session.info.rigid_bodies

        trails: Dict[int, List[Tuple[float, float, float]]] = {}
        if self.ctx.config.ui.show_trails and frame is not None:
            trails = self.ctx.hub.trails_snapshot(sorted(frame.bodies),
                                                  self.ctx.config.ui.max_draw_bodies)
        markers = None
        if self.ctx.config.ui.show_markers and frame is not None:
            markers = {}
            for body_id, body in frame.bodies.items():
                if not body.markers:
                    continue
                markers[body_id] = tuple(
                    self._transform.position(mx / 1000.0, my / 1000.0, mz / 1000.0)
                    for mx, my, mz in body.markers
                )

        self.view.update_scene(frame, trails, markers)

        if frame is not None and self._selected_body >= 0:
            samples = self.ctx.hub.series_snapshot(self._selected_body)
            name = ""
            if self._selected_body in frame.bodies:
                name = frame.bodies[self._selected_body].name
            title = tr("刚体 %d %s") % (self._selected_body, name)
            self.scope.set_samples(samples, title)
            if not samples:
                self.scope_hint.setText(tr("该刚体暂无历史数据"))
        elif frame is None:
            self.scope.set_samples([], "")

        table_interval = 1.0 / max(1, int(self.ctx.config.ui.table_hz))
        if now >= self._next_table:
            self._next_table = now + table_interval
            self.body_table.update_table(frame, self.ctx.engine.pipeline, known)
            self._refresh_body_combo(frame, known)
