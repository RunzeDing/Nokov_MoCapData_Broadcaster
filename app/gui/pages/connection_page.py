"""Connection page: talk to the Nokov server and inspect what it offers."""

from __future__ import annotations

from ...i18n import tr

import copy
import logging
import threading
import time
from typing import List, Optional

from PySide2.QtCore import Qt, QTimer
from PySide2.QtGui import QGuiApplication
from PySide2.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core import netinfo
from ...core.sdk_client import load_sdk
from .. import theme
from ..context import AppContext
from ..widgets.cards import SectionBox, StatGrid
from ..widgets.forms import FieldDef, FormBuilder

log = logging.getLogger("nokov.gui.connection")

def network_fields():
    return [
        FieldDef("server_ip", tr("动捕服务器 IP"), "str", tooltip=tr("运行 Nokov XING 服务端的电脑 IP；若就在本机，可用右侧“检测本机 IP”"),
                 placeholder="192.168.1.123", grow=True),
        FieldDef("receive_mode", tr("数据接收模式"), "choice", choices=[
            ("callback", tr("回调模式 (SDK 主动推送，推荐)")),
            ("poll", tr("主动读取模式 (本程序轮询)")),
        ]),
        FieldDef("timestamp_unit", tr("服务器时间戳单位"), "choice", choices=[
            ("auto", tr("自动识别 (推荐)")),
            ("ns", tr("纳秒")), ("us", tr("微秒")), ("ms", tr("毫秒")), ("s", tr("秒")),
        ], tooltip=tr("仅影响报文中的“服务器时间戳”字段；内部计时始终使用单调时钟")),
        FieldDef("connect_timeout_s", tr("等待数据超时"), "float", 0.5, 30.0, decimals=1,
                 suffix=tr(" 秒"), tooltip=tr("超过该时间没有收到帧就提示“无数据”")),
        FieldDef("read_extend_data", tr("读取 SDK 速度/加速度/角度"), "bool",
                 tooltip=tr("服务器提供扩展数据时，直接使用其速度与欧拉角，比差分更准确")),
    ]


class _LocalProbe(threading.Thread):
    """Tries each candidate server address in a background thread.

    Probing the SDK blocks for a few seconds per wrong address, so it must not
    run on the GUI thread.
    """

    def __init__(self, ctx: AppContext, candidates: List[str]) -> None:
        super().__init__(name="nokov-local-probe", daemon=True)
        self.ctx = ctx
        self.candidates = list(candidates)
        self.current = ""
        self.attempted: List[str] = []
        self.result: Optional[str] = None
        self.message = ""
        self.done = False
        self.cancel = False

    def run(self) -> None:
        try:
            for ip in self.candidates:
                if self.cancel:
                    break
                self.current = ip
                network = copy.copy(self.ctx.config.network)
                network.server_ip = ip
                log.info(tr("本机自动连接：尝试 %s"), ip)
                try:
                    ok, message = self.ctx.session.connect(network)
                except Exception as exc:  # pragma: no cover - defensive
                    ok, message = False, repr(exc)
                self.attempted.append(ip)
                if ok:
                    self.result = ip
                    self.message = message
                    return
                self.message = message
                try:
                    self.ctx.session.disconnect()
                except Exception:
                    pass
        finally:
            self.current = ""
            self.done = True


class ConnectionPage(QWidget):
    def __init__(self, ctx: AppContext, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._next_refresh = 0.0
        self._next_ip_refresh = 0.0
        self._probe: Optional[_LocalProbe] = None
        self._probe_timer = QTimer(self)
        self._probe_timer.setInterval(200)
        self._probe_timer.timeout.connect(self._on_probe_tick)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # ---- server settings ------------------------------------------- #
        server_box = SectionBox(tr("动捕服务器连接"), tr("设置服务器地址后点击“连接”，SDK 会自动开始接收数据帧。"))
        self.form = FormBuilder(network_fields(), columns=2)
        self.form.load(self.ctx.config.network)
        self.form.changed.connect(self._on_form_changed)
        server_box.add(self.form)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.connect_button = QPushButton(tr("连接"))
        self.connect_button.setProperty("accent", True)
        self.connect_button.clicked.connect(self._on_connect)
        self.disconnect_button = QPushButton(tr("断开"))
        self.disconnect_button.clicked.connect(self._on_disconnect)
        self.reload_button = QPushButton(tr("重新连接"))
        self.reload_button.clicked.connect(self._on_reconnect)
        self.detect_button = QPushButton(tr("检测本机 IP"))
        self.detect_button.setToolTip(tr("列出本机所有 IPv4 地址（含回环），选一个填入服务器 IP"))
        self.detect_button.clicked.connect(self._on_detect_local_ip)
        self.auto_local_button = QPushButton(tr("本机一键连接"))
        self.auto_local_button.setProperty("accent", True)
        self.auto_local_button.setToolTip(
            tr("动捕软件就在本机时使用：依次尝试 127.0.0.1 和本机各网卡 IP，\n"
            "自动找到能连上的那个并填入服务器 IP")
        )
        self.auto_local_button.clicked.connect(self._on_auto_connect_local)
        for widget in (self.connect_button, self.disconnect_button, self.reload_button,
                       self.detect_button, self.auto_local_button):
            buttons.addWidget(widget)
        buttons.addStretch(1)
        server_box.add_layout(buttons)

        self.local_ip_label = QLabel(tr("本机 IPv4：检测中…"))
        self.local_ip_label.setWordWrap(True)
        self.local_ip_label.setStyleSheet("color: %s; font-size: 11px;" % theme.TEXT_DIM)
        self.local_ip_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        server_box.add(self.local_ip_label)

        simulator_row = QHBoxLayout()
        self.sim_checkbox = QCheckBox(tr("启用模拟数据源（无硬件时演示/调试）"))
        self.sim_checkbox.toggled.connect(self._on_simulator_toggled)
        self.sim_bodies = QSpinBox()
        self.sim_bodies.setRange(1, 64)
        self.sim_bodies.setValue(4)
        self.sim_bodies.setPrefix(tr("刚体 "))
        self.sim_rate = QDoubleSpinBox()
        self.sim_rate.setRange(10.0, 500.0)
        self.sim_rate.setValue(120.0)
        self.sim_rate.setSuffix(" Hz")
        self.sim_rate.setPrefix(tr("速率 "))
        self.sim_bodies.valueChanged.connect(self._on_sim_params_changed)
        self.sim_rate.valueChanged.connect(self._on_sim_params_changed)
        for widget in (self.sim_checkbox, self.sim_bodies, self.sim_rate):
            simulator_row.addWidget(widget)
        simulator_row.addStretch(1)
        server_box.add_layout(simulator_row)
        root.addWidget(server_box)

        # ---- status ----------------------------------------------------- #
        status_box = SectionBox(tr("运行状态"))
        self.tiles = StatGrid(
            (tr("连接状态"), tr("SDK 版本"), tr("服务器"), tr("数据帧率"), tr("已接收帧"), tr("重复帧"),
             tr("数据来源"), tr("服务器时间戳单位")),
            columns=4,
        )
        status_box.add(self.tiles)
        self.message_label = QLabel("")
        self.message_label.setWordWrap(True)
        status_box.add(self.message_label)
        root.addWidget(status_box)

        # ---- descriptions ----------------------------------------------- #
        info_row = QHBoxLayout()
        info_row.setSpacing(10)

        info_box = SectionBox(tr("服务器信息"))
        self.info_grid = QGridLayout()
        self.info_grid.setHorizontalSpacing(14)
        self.info_grid.setVerticalSpacing(4)
        self.info_labels = {}
        for row, caption in enumerate((tr("主机名"), tr("应用程序"), tr("程序版本"), tr("地址"),
                                       tr("帧率设置"), tr("标记点集合"), tr("骨架"), tr("力台"))):
            name = QLabel(caption + "：")
            name.setStyleSheet("color: %s;" % theme.TEXT_DIM)
            value = QLabel("—")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            value.setWordWrap(True)
            self.info_grid.addWidget(name, row, 0)
            self.info_grid.addWidget(value, row, 1)
            self.info_labels[caption] = value
        self.info_grid.setColumnStretch(1, 1)
        info_box.add_layout(self.info_grid)
        info_row.addWidget(info_box, 1)

        body_box = SectionBox(tr("服务器刚体列表"), tr("双击一行可将其设为“仅广播该刚体”。"))
        self.body_table = QTableWidget(0, 2)
        self.body_table.setHorizontalHeaderLabels(["ID", tr("名称")])
        self.body_table.verticalHeader().setVisible(False)
        self.body_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.body_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.body_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.body_table.setMinimumHeight(190)
        self.body_table.itemDoubleClicked.connect(self._on_body_double_clicked)
        body_box.add(self.body_table)
        self.only_button = QPushButton(tr("仅广播选中的刚体"))
        self.only_button.clicked.connect(self._on_only_selected)
        self.all_button = QPushButton(tr("恢复为全部刚体"))
        self.all_button.clicked.connect(self._on_all_bodies)
        row = QHBoxLayout()
        row.addWidget(self.only_button)
        row.addWidget(self.all_button)
        row.addStretch(1)
        body_box.add_layout(row)
        info_row.addWidget(body_box, 1)

        root.addLayout(info_row)
        root.addStretch(1)

        self._update_buttons()
        self._check_sdk()

    # ------------------------------------------------------------------ #
    def _check_sdk(self) -> None:
        ok, message = load_sdk()
        if not ok:
            self._set_message(message, error=True)

    def _on_form_changed(self) -> None:
        self.form.collect(self.ctx.config.network)
        self.ctx.config_changed()

    def _set_message(self, text: str, error: bool = False) -> None:
        color = theme.ERROR if error else theme.TEXT_DIM
        self.message_label.setStyleSheet("color: %s;" % color)
        self.message_label.setText(text)

    # ------------------------------------------------------------------ #
    def _on_connect(self) -> None:
        self.form.collect(self.ctx.config.network)
        if self.ctx.simulator_running:
            self._set_message(tr("模拟数据源已开启，请先关闭它再连接真实服务器。"), error=True)
            return
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            ok, message = self.ctx.session.connect(self.ctx.config.network)
        finally:
            QGuiApplication.restoreOverrideCursor()

        if ok:
            self._set_message(message)
            log.info(tr("连接成功: %s"), message)
            self.ctx.hub.set_body_names(self.ctx.session.info.rigid_bodies)
            self.ctx.engine.pipeline.register_known_bodies(self.ctx.session.info.rigid_bodies)
            self._reload_body_table()
        else:
            self._set_message(message, error=True)
            log.error(tr("连接失败: %s"), message)
        self._update_buttons()

    def _on_disconnect(self) -> None:
        self.ctx.session.disconnect()
        self._set_message(tr("已断开与动捕服务器的连接。"))
        self._update_buttons()

    def _on_reconnect(self) -> None:
        self._on_disconnect()
        self._on_connect()

    def request_connect(self) -> None:
        """Public entry point used by the auto-start logic."""
        self._on_connect()

    # ------------------------------------------------------------------ #
    # local IP helpers
    # ------------------------------------------------------------------ #
    def _set_server_ip(self, ip: str) -> None:
        widget = self.form.widget("server_ip")
        if widget is None:
            return
        widget.setText(ip)
        self.form.collect(self.ctx.config.network)
        self.ctx.config_changed()

    def _on_detect_local_ip(self) -> None:
        adapters = netinfo.list_local_ipv4()
        if not adapters:
            self._set_message(tr("未能枚举到本机 IPv4 地址，请检查网络适配器。"), error=True)
            return
        labels = [item.label for item in adapters]
        preferred = netinfo.socket_ipv4()
        index = next((i for i, item in enumerate(adapters) if item.ip == preferred), 0)
        label, ok = QInputDialog.getItem(
            self, tr("检测本机 IP"),
            tr("本机检测到以下 IPv4 地址，请选择动捕服务器使用的地址：\n"
            "（动捕软件在本机时，通常就是默认出口网卡；若服务器只监听回环可用 127.0.0.1）"),
            labels, index, False,
        )
        if not ok or not label:
            return
        try:
            chosen = adapters[labels.index(label)]
        except ValueError:
            return
        self._set_server_ip(chosen.ip)
        self._set_message(tr("已填入本机地址 %s（%s）。") % (chosen.ip, chosen.name or tr("网卡")))

    def _on_auto_connect_local(self) -> None:
        if self._probe is not None:
            return
        if self.ctx.simulator_running:
            self._set_message(tr("模拟数据源已开启，请先关闭它再连接真实服务器。"), error=True)
            return
        self.ctx.session.disconnect()
        candidates = netinfo.candidate_server_ips()
        if not candidates:
            self._set_message(tr("未检测到可用的本机地址。"), error=True)
            return

        self._probe = _LocalProbe(self.ctx, candidates)
        self._probe.start()
        self._set_message(tr("本机自动连接中，正在依次尝试：%s …") % "、".join(candidates))
        self._probe_timer.start(200)
        self._update_buttons()

    def _on_probe_tick(self) -> None:
        probe = self._probe
        if probe is None:
            self._probe_timer.stop()
            return
        if not probe.done:
            if probe.current:
                self._set_message(tr("正在尝试 %s …（本机自动连接）") % probe.current)
            return

        self._probe_timer.stop()
        self._probe = None
        if probe.result:
            self._set_server_ip(probe.result)
            self._set_message(tr("本机自动连接成功：%s（%s）") % (probe.result, probe.message))
            log.info(tr("本机自动连接成功: %s"), probe.result)
            self.ctx.hub.set_body_names(self.ctx.session.info.rigid_bodies)
            self.ctx.engine.pipeline.register_known_bodies(self.ctx.session.info.rigid_bodies)
            self._reload_body_table()
        else:
            tried = "、".join(probe.attempted) or tr("（无）")
            self._set_message(
                tr("本机自动连接失败，已尝试：%s。\n最后一次错误：%s\n"
                "请确认动捕软件已启动并处于播放/采集状态；"
                "也可以手动点“检测本机 IP”选择正确网卡，或直接填写服务器的实际地址。")
                % (tried, probe.message),
                error=True,
            )
            log.warning(tr("本机自动连接失败，已尝试 %s: %s"), tried, probe.message)
        self._update_buttons()

    def _refresh_local_ips(self) -> None:
        try:
            entries = netinfo.list_local_ipv4()
        except Exception as exc:  # pragma: no cover - defensive
            self.local_ip_label.setText(tr("本机 IPv4：检测失败（%r）") % (exc,))
            return
        if not entries:
            self.local_ip_label.setText(tr("本机 IPv4：未检测到"))
            return
        current = self.ctx.config.network.server_ip.strip()
        parts = []
        for item in entries:
            text = item.label
            if item.ip == current:
                text = "▶ " + text
            parts.append(text)
        self.local_ip_label.setText(
            tr("本机 IPv4（▶ 为当前填写的服务器地址）：") + "；".join(parts)
        )

    def _on_simulator_toggled(self, checked: bool) -> None:
        if checked:
            if self.ctx.session.is_running:
                self.ctx.session.disconnect()
            self.ctx.start_simulator(self.sim_bodies.value(), self.sim_rate.value())
            self._set_message(tr("模拟数据源运行中：数据不会来自真实动捕服务器。"))
        else:
            self.ctx.stop_simulator()
            self._set_message(tr("模拟数据源已停止。"))
        self._update_buttons()

    def _on_sim_params_changed(self, *_args) -> None:
        simulator = self.ctx.simulator
        if simulator is None:
            return
        simulator.set_body_count(self.sim_bodies.value())
        simulator.set_rate(self.sim_rate.value())

    def _update_buttons(self) -> None:
        probing = self._probe is not None
        running = self.ctx.session.is_running
        self.connect_button.setEnabled(not running and not probing)
        self.disconnect_button.setEnabled(running)
        self.reload_button.setEnabled(running and not probing)
        self.detect_button.setEnabled(not probing)
        self.auto_local_button.setEnabled(not probing and not running)
        self.auto_local_button.setText(tr("本机连接中…") if probing else tr("本机一键连接"))
        self.form.set_all_enabled(not running and not probing)

    # ------------------------------------------------------------------ #
    def _reload_body_table(self) -> None:
        bodies = self.ctx.session.info.rigid_bodies
        self.body_table.setRowCount(len(bodies))
        for row, body_id in enumerate(sorted(bodies)):
            id_item = QTableWidgetItem(str(body_id))
            id_item.setData(Qt.UserRole, body_id)
            self.body_table.setItem(row, 0, id_item)
            self.body_table.setItem(row, 1, QTableWidgetItem(bodies[body_id]))

    def _selected_body_ids(self) -> List[int]:
        ids = []
        for index in self.body_table.selectionModel().selectedRows() if self.body_table.selectionModel() else []:
            item = self.body_table.item(index.row(), 0)
            if item is not None:
                ids.append(int(item.data(Qt.UserRole)))
        return ids

    def _on_body_double_clicked(self, _item) -> None:
        self._on_only_selected()

    def _on_only_selected(self) -> None:
        ids = self._selected_body_ids()
        if not ids:
            self._set_message(tr("请先在列表中选中至少一个刚体。"), error=True)
            return
        self.ctx.config.filters.include_ids = ",".join(str(value) for value in sorted(ids))
        self.ctx.config.filters.exclude_ids = ""
        self.ctx.config_changed()
        self._set_message(tr("已设置为仅广播刚体: %s（可在“数据处理”页修改）")
                          % self.ctx.config.filters.include_ids)

    def _on_all_bodies(self) -> None:
        self.ctx.config.filters.include_ids = ""
        self.ctx.config.filters.exclude_ids = ""
        self.ctx.config_changed()
        self._set_message(tr("已恢复为广播全部刚体。"))

    # ------------------------------------------------------------------ #
    def reload_from_config(self) -> None:
        self.form.load(self.ctx.config.network)

    def refresh(self, now: float) -> None:
        if now < self._next_refresh:
            return
        self._next_refresh = now + 0.25

        session = self.ctx.session
        info = session.info
        if self.ctx.simulator_running:
            state_text, state_color = tr("模拟数据"), theme.ACCENT
            source = tr("模拟数据源")
        elif session.is_running:
            if session.last_frame_at and (time.monotonic() - session.last_frame_at) < 1.0:
                state_text, state_color = tr("已连接 · 数据正常"), theme.OK
            else:
                state_text, state_color = tr("已连接 · 等待数据"), theme.WARN
            source = tr("动捕服务器")
        else:
            state_text, state_color = tr("未连接"), theme.TEXT_DIM
            source = "—"

        self.tiles.set(tr("连接状态"), state_text, state_color)
        self.tiles.set(tr("SDK 版本"), info.sdk_version or "—")
        self.tiles.set(tr("服务器"), info.server_name or (self.ctx.config.network.server_ip or "—"))
        fps = self.ctx.engine.stats.fps
        self.tiles.set(tr("数据帧率"), "%.1f Hz" % fps if fps > 0 else "—")
        self.tiles.set(tr("已接收帧"), "%d" % session.frames_received)
        self.tiles.set(tr("重复帧"), "%d" % session.duplicate_frames)
        self.tiles.set(tr("数据来源"), source)
        self.tiles.set(tr("服务器时间戳单位"), info.timestamp_unit if info.timestamp_unit != "auto" else "—")

        self.info_labels[tr("主机名")].setText(info.server_name or "—")
        self.info_labels[tr("应用程序")].setText(info.server_app or "—")
        self.info_labels[tr("程序版本")].setText(info.server_app_version or "—")
        self.info_labels[tr("地址")].setText(info.server_address or "—")
        self.info_labels[tr("帧率设置")].setText("%d fps" % info.frame_rate if info.frame_rate else "—")
        self.info_labels[tr("标记点集合")].setText(
            "、".join(info.marker_sets) if info.marker_sets else "—")
        self.info_labels[tr("骨架")].setText("、".join(info.skeletons) if info.skeletons else "—")
        self.info_labels[tr("力台")].setText(tr("%d 个") % info.force_plates if info.force_plates else "—")

        if session.is_running:
            if session.last_frame_at and (time.monotonic() - session.last_frame_at) > self.ctx.config.network.connect_timeout_s:
                self._set_message(
                    tr("已连接但 %.1f 秒没有收到数据帧：请确认动捕软件已开始播放/采集，"
                    "或检查服务器 IP 是否正确。") % (time.monotonic() - session.last_frame_at),
                    error=False,
                )
        if session.build_errors:
            self._set_message(tr("解析帧时出现 %d 次错误，最近一次: %s")
                              % (session.build_errors, session.last_error), error=True)

        if self.body_table.rowCount() != len(info.rigid_bodies):
            self._reload_body_table()
        self._update_buttons()
        if self.sim_checkbox.isChecked() != self.ctx.simulator_running:
            self.sim_checkbox.blockSignals(True)
            self.sim_checkbox.setChecked(self.ctx.simulator_running)
            self.sim_checkbox.blockSignals(False)

        if now >= self._next_ip_refresh:
            self._next_ip_refresh = now + 2.0
            self._refresh_local_ips()
