"""Broadcast page: UDP targets, wire format selection and live packet preview."""

from __future__ import annotations

from ...i18n import tr

import logging
import time
from typing import List, Optional

from PySide2.QtCore import Qt
from PySide2.QtGui import QBrush, QColor
from PySide2.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...config import BroadcastTarget
from ...core import netinfo
from ...core.formats import get_format, hex_dump, list_formats
from .. import theme
from ..context import AppContext
from ..widgets.cards import HintLabel, SectionBox, StatGrid
from ..widgets.format_params import FormatParamsWidget

log = logging.getLogger("nokov.gui.broadcast")

def target_columns():
    return (tr("启用"), tr("目标 IP / 主机名"), tr("端口"), tr("备注"))


class BroadcastPage(QWidget):
    def __init__(self, ctx: AppContext, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._next_refresh = 0.0
        self._next_ip_hint = 0.0
        self._loading = False
        self._params_dirty = False

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        # ---- targets ---------------------------------------------------- #
        targets_box = SectionBox(tr("UDP 广播目标"), tr("可以同时向多个地址发送；取消勾选即可临时停用某个目标。"))
        self.target_table = QTableWidget(0, len(target_columns()))
        self.target_table.setHorizontalHeaderLabels(list(target_columns()))
        self.target_table.verticalHeader().setVisible(False)
        self.target_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.target_table.setMinimumHeight(150)
        header = self.target_table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        self.target_table.itemChanged.connect(self._on_targets_changed)
        targets_box.add(self.target_table)

        target_buttons = QHBoxLayout()
        add_button = QPushButton(tr("添加目标"))
        add_button.clicked.connect(self._on_add_target)
        remove_button = QPushButton(tr("删除选中"))
        remove_button.clicked.connect(self._on_remove_target)
        nic_button = QPushButton(tr("填入本机网卡 IP"))
        nic_button.setToolTip(
            tr("接收端也在本机时使用。接收端绑定 0.0.0.0 或绑定本机网卡地址都能收到。\n"
            "（原 NokovSDKClient_STQ.py 用的就是这个方式：192.168.1.123:22222）")
        )
        nic_button.clicked.connect(lambda: self._on_add_local_target(nic=True))
        loop_button = QPushButton(tr("填入本机回环 127.0.0.1"))
        loop_button.setToolTip(tr("接收端也在本机、且只监听 127.0.0.1 时使用"))
        loop_button.clicked.connect(lambda: self._on_add_local_target(nic=False))
        for button in (add_button, remove_button, nic_button, loop_button):
            target_buttons.addWidget(button)
        target_buttons.addStretch(1)
        targets_box.add_layout(target_buttons)

        self.local_target_hint = HintLabel(tr("本机 IPv4：检测中…"))
        targets_box.add(self.local_target_hint)

        rate_row = QHBoxLayout()
        self.rate_spin = QDoubleSpinBox()
        self.rate_spin.setRange(0.0, 1000.0)
        self.rate_spin.setDecimals(1)
        self.rate_spin.setSuffix(" Hz")
        self.rate_spin.setSpecialValueText(tr("每帧都发"))
        self.rate_spin.setValue(0.0)
        self.rate_spin.setKeyboardTracking(False)
        self.rate_spin.valueChanged.connect(self._on_rate_changed)
        self.empty_checkbox = QCheckBox(tr("没有刚体时也发送空包"))
        self.empty_checkbox.toggled.connect(self._on_rate_changed)
        self.source_edit = QLineEdit()
        self.source_edit.setPlaceholderText(tr("留空 = 系统默认网卡"))
        self.source_edit.setMaximumWidth(200)
        self.source_edit.editingFinished.connect(self._on_rate_changed)
        rate_row.addWidget(QLabel(tr("发送限速")))
        rate_row.addWidget(self.rate_spin)
        rate_row.addWidget(self.empty_checkbox)
        rate_row.addWidget(QLabel(tr("本机绑定 IP")))
        rate_row.addWidget(self.source_edit)
        rate_row.addStretch(1)
        targets_box.add_layout(rate_row)
        top_row.addWidget(targets_box, 3)

        # ---- format ----------------------------------------------------- #
        format_box = SectionBox(tr("广播数据格式"), tr("默认格式与 NokovSDKClient_STQ.py 完全一致（逐字节相同）。"))
        self.format_combo = QComboBox()
        for encoder in list_formats():
            self.format_combo.addItem(encoder.name, encoder.id)
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        format_box.add(self.format_combo)
        self.format_description = HintLabel("")
        format_box.add(self.format_description)
        top_row.addWidget(format_box, 2)
        root.addLayout(top_row)

        # ---- control + stats -------------------------------------------- #
        control_box = SectionBox(tr("广播控制"))
        control_row = QHBoxLayout()
        self.start_button = QPushButton(tr("开始广播"))
        self.start_button.setProperty("accent", True)
        self.start_button.clicked.connect(self._on_start)
        self.stop_button = QPushButton(tr("停止广播"))
        self.stop_button.setProperty("danger", True)
        self.stop_button.clicked.connect(self._on_stop)
        self.status_label = QLabel(tr("未广播"))
        self.status_label.setStyleSheet("color: %s; font-weight: 600;" % theme.TEXT_DIM)
        control_row.addWidget(self.start_button)
        control_row.addWidget(self.stop_button)
        control_row.addWidget(self.status_label)
        control_row.addStretch(1)
        control_box.add_layout(control_row)

        self.tiles = StatGrid(
            (tr("发送速率"), tr("带宽"), tr("累计包数"), tr("报文长度"), tr("编码耗时"), tr("启用目标"), tr("发送错误")),
            columns=7,
        )
        control_box.add(self.tiles)
        root.addWidget(control_box)

        # ---- preview ---------------------------------------------------- #
        preview_row = QHBoxLayout()
        preview_row.setSpacing(10)

        layout_box = SectionBox(tr("报文结构预览"), tr("显示当前参数下的字节布局与预计长度。"))
        self.layout_view = QPlainTextEdit()
        self.layout_view.setReadOnly(True)
        self.layout_view.setFont(theme.mono_font(9))
        self.layout_view.setMinimumHeight(180)
        layout_box.add(self.layout_view)
        preview_row.addWidget(layout_box, 3)

        packet_box = SectionBox(tr("最近发出的报文"), tr("前 32 字节的十六进制内容。"))
        self.packet_label = QLabel(tr("（尚未发送）"))
        self.packet_label.setFont(theme.mono_font(9))
        self.packet_label.setWordWrap(True)
        self.packet_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.packet_label.setMinimumHeight(60)
        packet_box.add(self.packet_label)
        self.packet_info = HintLabel("")
        packet_box.add(self.packet_info)
        preview_row.addWidget(packet_box, 2)
        root.addLayout(preview_row)

        self.params_widget = FormatParamsWidget()
        params_box = SectionBox(tr("格式参数"))
        params_box.add(self.params_widget)
        self.params_widget.changed.connect(self._on_params_changed)
        root.addWidget(params_box)
        root.addStretch(1)

        self._load_targets()
        self._load_format()

    # ------------------------------------------------------------------ #
    # targets
    # ------------------------------------------------------------------ #
    def _load_targets(self) -> None:
        self._loading = True
        try:
            targets = self.ctx.config.broadcast.targets
            self.target_table.setRowCount(len(targets))
            for row, target in enumerate(targets):
                check = QTableWidgetItem()
                check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                check.setCheckState(Qt.Checked if target.enabled else Qt.Unchecked)
                self.target_table.setItem(row, 0, check)
                self.target_table.setItem(row, 1, QTableWidgetItem(target.ip))
                self.target_table.setItem(row, 2, QTableWidgetItem(str(target.port)))
                self.target_table.setItem(row, 3, QTableWidgetItem(target.label))
        finally:
            self._loading = False

    def _collect_targets(self) -> List[BroadcastTarget]:
        targets: List[BroadcastTarget] = []
        for row in range(self.target_table.rowCount()):
            check = self.target_table.item(row, 0)
            ip_item = self.target_table.item(row, 1)
            port_item = self.target_table.item(row, 2)
            label_item = self.target_table.item(row, 3)
            ip = (ip_item.text().strip() if ip_item else "")
            if not ip:
                continue
            try:
                port = int((port_item.text() if port_item else "").strip() or "0")
            except ValueError:
                port = 0
            targets.append(BroadcastTarget(
                ip=ip,
                port=port,
                enabled=bool(check and check.checkState() == Qt.Checked),
                label=(label_item.text().strip() if label_item else ""),
            ))
        return targets

    def _on_targets_changed(self, _item) -> None:
        if self._loading:
            return
        self.ctx.config.broadcast.targets = self._collect_targets()
        self.ctx.config_changed()
        self._validate_targets()

    def _on_add_target(self) -> None:
        row = self.target_table.rowCount()
        self.target_table.insertRow(row)
        check = QTableWidgetItem()
        check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        check.setCheckState(Qt.Checked)
        self._loading = True
        try:
            self.target_table.setItem(row, 0, check)
            self.target_table.setItem(row, 1, QTableWidgetItem("127.0.0.1"))
            self.target_table.setItem(row, 2, QTableWidgetItem("22222"))
            self.target_table.setItem(row, 3, QTableWidgetItem(""))
        finally:
            self._loading = False
        self._on_targets_changed(None)

    def _on_add_loopback(self) -> None:
        self._on_add_local_target(nic=False)

    def _current_port(self) -> str:
        """Reuse the port already used in the table, so two targets can coexist."""
        for row in range(self.target_table.rowCount() - 1, -1, -1):
            item = self.target_table.item(row, 2)
            if item is not None:
                text = item.text().strip()
                if text.isdigit() and 0 < int(text) < 65536:
                    return text
        return "22222"

    def _on_add_local_target(self, nic: bool) -> None:
        if nic:
            try:
                ip = netinfo.primary_ipv4()
            except Exception:
                ip = ""
            if not ip or ip.startswith("127."):
                self.status_label.setText(tr("未检测到本机网卡地址，请检查网络连接"))
                self.status_label.setStyleSheet("color: %s; font-weight: 600;" % theme.ERROR)
                return
            label = tr("本机网卡")
        else:
            ip = "127.0.0.1"
            label = tr("本机回环")

        port = self._current_port()
        self._on_add_target()
        row = self.target_table.rowCount() - 1
        self.target_table.item(row, 1).setText(ip)
        self.target_table.item(row, 2).setText(port)
        self.target_table.item(row, 3).setText(label)
        self._on_targets_changed(None)
        self.status_label.setText(tr("已添加广播目标 %s:%s（%s）") % (ip, port, label))
        self.status_label.setStyleSheet("color: %s; font-weight: 600;" % theme.OK)

    def _on_remove_target(self) -> None:
        rows = sorted({index.row() for index in self.target_table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        for row in rows:
            self.target_table.removeRow(row)
        self._on_targets_changed(None)

    def _validate_targets(self) -> None:
        problems = []
        for row, target in enumerate(self.ctx.config.broadcast.targets):
            if not target.ip:
                problems.append(tr("第 %d 行缺少 IP") % (row + 1))
            elif not (0 < int(target.port or 0) < 65536):
                problems.append(tr("第 %d 行端口 %s 无效") % (row + 1, target.port))

        # Highlight malformed rows. QTableWidgetItem is not a QObject, so the
        # stylesheet property trick cannot be used here - colour the text instead.
        error_color = QColor(theme.ERROR)
        normal_color = QColor(theme.TEXT)
        for row in range(self.target_table.rowCount()):
            ip_item = self.target_table.item(row, 1)
            port_item = self.target_table.item(row, 2)
            bad = False
            if ip_item is None or not ip_item.text().strip():
                bad = True
            else:
                try:
                    port = int((port_item.text() if port_item else "").strip() or "0")
                    bad = not (0 < port < 65536)
                except ValueError:
                    bad = True
            for item in (ip_item, port_item):
                if item is not None:
                    item.setForeground(QBrush(error_color if bad else normal_color))
            if bad:
                problems.append(tr("第 %d 行的 IP 或端口不完整") % (row + 1))

        if problems:
            self.status_label.setText(tr("目标配置有误：") + "；".join(problems[:3]))
            self.status_label.setStyleSheet("color: %s; font-weight: 600;" % theme.ERROR)
        else:
            self._update_status_label()

    # ------------------------------------------------------------------ #
    # rate / format
    # ------------------------------------------------------------------ #
    def _on_rate_changed(self, *_args) -> None:
        if self._loading:
            return
        broadcast = self.ctx.config.broadcast
        broadcast.max_rate_hz = float(self.rate_spin.value())
        broadcast.send_when_empty = bool(self.empty_checkbox.isChecked())
        broadcast.source_ip = self.source_edit.text().strip()
        self.ctx.config_changed()

    def _load_format(self) -> None:
        self._loading = True
        try:
            broadcast = self.ctx.config.broadcast
            index = self.format_combo.findData(broadcast.format_id)
            self.format_combo.setCurrentIndex(index if index >= 0 else 0)
            self.rate_spin.setValue(float(broadcast.max_rate_hz))
            self.empty_checkbox.setChecked(bool(broadcast.send_when_empty))
            self.source_edit.setText(broadcast.source_ip)
            self._refresh_format_panel(broadcast.format_id)
            self._refresh_layout_preview()
        finally:
            self._loading = False

    def _refresh_format_panel(self, format_id: str) -> None:
        encoder = get_format(format_id)
        self.format_description.setText(encoder.description)
        self.params_widget.set_encoder(encoder, self.ctx.config.broadcast.params_for(format_id))

    def _on_format_changed(self, _index: int) -> None:
        if self._loading:
            return
        format_id = self.format_combo.currentData()
        self.ctx.config.broadcast.format_id = format_id
        self._refresh_format_panel(format_id)
        self._refresh_layout_preview()
        self.ctx.config_changed()

    def _on_params_changed(self) -> None:
        if self._loading:
            return
        self._params_dirty = True
        format_id = self.ctx.config.broadcast.format_id
        self.ctx.config.broadcast.set_params_for(format_id, self.params_widget.params())
        self._refresh_layout_preview()

    # ------------------------------------------------------------------ #
    # preview
    # ------------------------------------------------------------------ #
    def _refresh_layout_preview(self) -> None:
        encoder = get_format(self.ctx.config.broadcast.format_id)
        params = encoder.normalize_params(
            self.ctx.config.broadcast.params_for(encoder.id))
        lines = encoder.layout_lines(params)
        _, frame = self.ctx.hub.latest_processed()
        body_count = len(frame.bodies) if frame is not None else 0
        lines.append("")
        lines.append(tr("当前刚体数 %d，预计单包 %d 字节（UDP 上限 65507）")
                     % (body_count, encoder.packet_size(params, body_count)))
        # dedicated short labels, so the combo box wording stays independent
        endian = tr("小端字节序") if params.get("endianness", "little") == "little" \
            else tr("大端字节序")
        lines.append(tr("字节序：%s") % endian)
        self.layout_view.setPlainText("\n".join(lines))

    # ------------------------------------------------------------------ #
    # control
    # ------------------------------------------------------------------ #
    def _on_start(self) -> None:
        if not self.ctx.config.broadcast.targets:
            self.status_label.setText(tr("请先添加至少一个 UDP 目标"))
            self.status_label.setStyleSheet("color: %s; font-weight: 600;" % theme.ERROR)
            return
        self.ctx.engine.apply_broadcast_config()
        if not self.ctx.engine.broadcaster.is_open:
            self.status_label.setText(self.ctx.engine.broadcaster.stats.last_error or tr("发送套接字创建失败"))
            self.status_label.setStyleSheet("color: %s; font-weight: 600;" % theme.ERROR)
            return
        self.ctx.engine.start_broadcasting()
        log.info(tr("开始广播: %s"), self.ctx.broadcaster.targets)
        self._update_status_label()

    def _on_stop(self) -> None:
        self.ctx.engine.stop_broadcasting()
        self._update_status_label()
        log.info(tr("已停止广播"))

    def request_start(self) -> None:
        """Public entry point used by the auto-start logic."""
        self._on_start()

    def _update_status_label(self) -> None:
        if self.ctx.engine.broadcasting:
            targets = self.ctx.engine.broadcaster.targets
            text = tr("广播中 → ") + "，".join("%s:%d" % item for item in targets)
            self.status_label.setText(text)
            self.status_label.setStyleSheet("color: %s; font-weight: 600;" % theme.OK)
        else:
            self.status_label.setText(tr("未广播"))
            self.status_label.setStyleSheet("color: %s; font-weight: 600;" % theme.TEXT_DIM)
        self.start_button.setEnabled(not self.ctx.engine.broadcasting)
        self.stop_button.setEnabled(self.ctx.engine.broadcasting)

    # ------------------------------------------------------------------ #
    def reload_from_config(self) -> None:
        self._load_targets()
        self._load_format()

    def refresh(self, now: float) -> None:
        if now < self._next_refresh:
            return
        self._next_refresh = now + 0.2

        engine = self.ctx.engine
        stats = engine.stats
        broadcast_stats = engine.broadcaster.stats

        self.tiles.set(tr("发送速率"), tr("%.0f 包/秒") % broadcast_stats.rate_hz if broadcast_stats.rate_hz else "—",
                       theme.OK if engine.broadcasting else None)
        self.tiles.set(tr("带宽"), _format_rate(broadcast_stats.throughput_bps))
        self.tiles.set(tr("累计包数"), "%d" % stats.packets_sent)
        self.tiles.set(tr("报文长度"), tr("%d 字节") % stats.last_packet_size if stats.last_packet_size else "—")
        self.tiles.set(tr("编码耗时"), "%.2f ms" % stats.encode_ms if stats.encode_ms else "—")
        enabled = len(engine.broadcaster.targets)
        self.tiles.set(tr("启用目标"), tr("%d 个") % enabled, theme.WARN if enabled == 0 else None)
        self.tiles.set(tr("发送错误"), "%d" % stats.send_errors,
                       theme.ERROR if stats.send_errors else None)

        if stats.last_packet_hex:
            self.packet_label.setText(stats.last_packet_hex)
            self.packet_info.setText(
                tr("共 %d 字节；用时 %.2f ms") % (stats.last_packet_size, stats.encode_ms))
        if stats.last_error:
            self.packet_info.setText(stats.last_error)

        self._update_status_label()
        self._refresh_layout_preview()

        if now >= self._next_ip_hint:
            self._next_ip_hint = now + 3.0
            self._refresh_local_hint()

    def _refresh_local_hint(self) -> None:
        try:
            entries = netinfo.list_local_ipv4()
        except Exception:
            self.local_target_hint.setText(tr("本机 IPv4：检测失败"))
            return
        texts = []
        for item in entries:
            if item.is_loopback or item.usable:
                texts.append(item.label)
        self.local_target_hint.setText(
            tr("本机 IPv4：%s　—　接收端在本机时优先用“本机网卡 IP”；"
            "接收端在另一台电脑上时，请填写那台电脑的 IP。") % "；".join(texts)
        )


def _format_rate(bits_per_second: float) -> str:
    if bits_per_second <= 0:
        return "—"
    if bits_per_second < 1024:
        return "%.0f B/s" % bits_per_second
    if bits_per_second < 1024 * 1024:
        return "%.1f KB/s" % (bits_per_second / 1024.0)
    return "%.2f MB/s" % (bits_per_second / (1024.0 * 1024.0))
