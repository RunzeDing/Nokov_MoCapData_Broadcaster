"""Main application window."""

from __future__ import annotations

import logging
import time
from typing import List, Optional

from PySide2.QtCore import Qt, QTimer
from PySide2.QtGui import QCloseEvent, QIcon
from PySide2.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QWidget,
)

from ..i18n import LANGUAGES, get_language, language_label, set_language, tr
from ..version import APP_TITLE, __version__
from . import theme
from .context import AppContext
from .pages.broadcast_page import BroadcastPage
from .pages.connection_page import ConnectionPage
from .pages.log_page import LogPage
from .pages.processing_page import ProcessingPage
from .pages.visualize_page import VisualizePage

log = logging.getLogger("nokov.gui")

def nav_items():
    """Built on demand so a language switch is reflected immediately."""
    return (
        (tr("连接"), tr("与动捕服务器建立连接，查看服务器信息与刚体列表")),
        (tr("广播"), tr("设置 UDP 目标与广播数据格式")),
        (tr("数据处理"), tr("刚体筛选、鲁棒性、平滑与坐标变换")),
        (tr("可视化"), tr("3D 姿态视图、实时曲线与数据表")),
        (tr("日志与配置"), tr("运行日志、参数方案与启动行为")),
    )


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("%s v%s" % (tr(APP_TITLE), __version__))
        self.resize(1500, 950)
        self.setMinimumSize(1100, 720)

        central = QWidget()
        self._layout = QHBoxLayout(central)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # ---- navigation -------------------------------------------------- #
        self.nav = QListWidget()
        self.nav.setFixedWidth(168)
        self.nav.setStyleSheet("QListWidget { background: %s; }" % theme.PANEL)
        self.nav.currentRowChanged.connect(self._on_nav_changed)
        self._layout.addWidget(self.nav)

        # ---- pages ------------------------------------------------------- #
        self.pages: List[QWidget] = []
        self.stack = QStackedWidget()
        self._layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self._build_navigation()
        self._build_pages()

        # ---- status bar --------------------------------------------------- #
        status = QStatusBar()
        self.setStatusBar(status)
        self.link_label = QLabel(tr("未连接"))
        self.broadcast_label = QLabel(tr("未广播"))
        self.format_label = QLabel("")
        self.rate_label = QLabel("")
        for widget in (self.link_label, self.broadcast_label, self.format_label):
            widget.setMinimumWidth(120)
            status.addPermanentWidget(widget)
        status.addPermanentWidget(self.rate_label)

        self.language_button = QPushButton(self._language_button_text())
        self.language_button.setToolTip(tr("切换界面语言（立即生效）"))
        self.language_button.setFlat(True)
        self.language_button.setStyleSheet(
            "QPushButton { border: 1px solid %s; border-radius: 4px; padding: 2px 10px; }"
            % theme.BORDER
        )
        self.language_button.clicked.connect(self.toggle_language)
        status.addPermanentWidget(self.language_button)

        self._status_message = QLabel(tr("就绪"))
        status.addWidget(self._status_message, 1)

        # ---- timers ------------------------------------------------------- #
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.timeout.connect(self._on_tick)
        self._last_tick = 0.0
        self._next_slow_tick = 0.0

        ctx.configReloaded.connect(self._on_config_reloaded)
        ctx.languageChangeRequested.connect(self.switch_language)

        self.nav.setCurrentRow(0)
        self._apply_refresh_rate()
        self._timer.start(16)
        self._on_tick()

    # ------------------------------------------------------------------ #
    def _apply_refresh_rate(self) -> None:
        hz = max(5, min(144, int(self.ctx.config.ui.refresh_hz)))
        self._timer.setInterval(max(6, int(1000 / hz)))

    # ------------------------------------------------------------------ #
    # language
    # ------------------------------------------------------------------ #
    def _language_button_text(self) -> str:
        """Show the language you would switch *to*, which is what a toggle implies."""
        current = get_language()
        for code, label in LANGUAGES:
            if code != current:
                return "🌐 %s" % label
        return "🌐"

    def toggle_language(self) -> None:
        current = get_language()
        for code, _label in LANGUAGES:
            if code != current:
                self.switch_language(code)
                return

    def switch_language(self, code: str) -> None:
        """Switch the interface language and rebuild every page in place.

        The engine, the SDK session and the hub are owned by :class:`AppContext`
        and survive the rebuild, so a running broadcast is not interrupted.
        """
        resolved = set_language(code)
        self.ctx.config.ui.language = resolved
        self.ctx.config.save()
        log.info("界面语言已切换为 %s", resolved)
        self._rebuild_ui()

    def _rebuild_ui(self) -> None:
        row = max(0, self.nav.currentRow())

        self.nav.blockSignals(True)
        for page in self.pages:
            self.stack.removeWidget(page)
            page.setParent(None)
            page.deleteLater()
        self.pages = []
        self.nav.clear()
        self.nav.blockSignals(False)

        self._build_navigation()
        self._build_pages()

        self.setWindowTitle("%s v%s" % (tr(APP_TITLE), __version__))
        self.language_button.setText(self._language_button_text())
        self.language_button.setToolTip(tr("切换界面语言（立即生效）"))
        self.link_label.setText(tr("未连接"))
        self.broadcast_label.setText(tr("未广播"))
        self._status_message.setText(tr("就绪"))

        self.nav.setCurrentRow(min(row, max(0, self.nav.count() - 1)))
        self._on_tick()

    def _build_navigation(self) -> None:
        for title, tooltip in nav_items():
            item = QListWidgetItem(title)
            item.setToolTip(tooltip)
            self.nav.addItem(item)

    def _build_pages(self) -> None:
        ctx = self.ctx
        self.connection_page = ConnectionPage(ctx)
        self.broadcast_page = BroadcastPage(ctx)
        self.processing_page = ProcessingPage(ctx)
        self.visualize_page = VisualizePage(ctx)
        self.log_page = LogPage(ctx)
        for page in (self.connection_page, self.broadcast_page, self.processing_page,
                     self.visualize_page, self.log_page):
            self.pages.append(page)
            self.stack.addWidget(page)
            reload_hook = getattr(page, "reload_from_config", None)
            if callable(reload_hook):
                ctx.configReloaded.connect(reload_hook)

    def _on_config_reloaded(self) -> None:
        self._apply_refresh_rate()
        log.info(tr("配置已重新载入"))

    def _on_nav_changed(self, row: int) -> None:
        if 0 <= row < self.stack.count():
            self.stack.setCurrentIndex(row)

    # ------------------------------------------------------------------ #
    def _on_tick(self) -> None:
        now = time.monotonic()
        self._last_tick = now
        current = self.stack.currentWidget()
        if current is not None:
            current.refresh(now)
        # background pages still need the occasional tick (log pump, tables)
        if now >= self._next_slow_tick:
            self._next_slow_tick = now + 0.3
            for page in self.pages:
                if page is not current:
                    page.refresh(now)
        self._update_status()

    def _update_status(self) -> None:
        ctx = self.ctx
        session = ctx.session
        if ctx.simulator_running:
            self.link_label.setText(tr("模拟数据源"))
            self.link_label.setStyleSheet("color: %s;" % theme.ACCENT)
        elif session.is_running:
            alive = session.last_frame_at and (time.monotonic() - session.last_frame_at) < 1.0
            self.link_label.setText(tr("已连接") if alive else tr("已连接(无数据)"))
            self.link_label.setStyleSheet("color: %s;" % (theme.OK if alive else theme.WARN))
        else:
            self.link_label.setText(tr("未连接"))
            self.link_label.setStyleSheet("color: %s;" % theme.TEXT_DIM)

        engine = ctx.engine
        stats = engine.stats
        if engine.broadcasting:
            targets = engine.broadcaster.targets
            self.broadcast_label.setText(tr("广播中 %d 个目标") % len(targets))
            self.broadcast_label.setStyleSheet("color: %s;" % theme.OK)
        else:
            self.broadcast_label.setText(tr("未广播"))
            self.broadcast_label.setStyleSheet("color: %s;" % theme.TEXT_DIM)

        try:
            from ..core.formats import get_format
            encoder = get_format(ctx.config.broadcast.format_id)
            self.format_label.setText(encoder.name.split(" ")[0])
            self.format_label.setStyleSheet("color: %s;" % theme.TEXT_DIM)
        except Exception:
            self.format_label.setText("")

        broadcast_stats = engine.broadcaster.stats
        self.rate_label.setText(
            tr("%.1f fps · %.0f 包/秒 · %d 刚体")
            % (stats.fps, broadcast_stats.rate_hz, stats.bodies)
        )
        if stats.last_error:
            self._status_message.setText(stats.last_error[:180])
            self._status_message.setStyleSheet("color: %s;" % theme.WARN)
        elif session.build_errors:
            self._status_message.setText(session.last_error[:180])
            self._status_message.setStyleSheet("color: %s;" % theme.WARN)
        else:
            self._status_message.setText(tr("就绪"))
            self._status_message.setStyleSheet("color: %s;" % theme.TEXT_DIM)

    # ------------------------------------------------------------------ #
    def autostart(self) -> None:
        """Honour the "start automatically" options."""
        ui = self.ctx.config.ui
        if ui.autoconnect:
            log.info(tr("按配置自动连接动捕服务器…"))
            self.connection_page.request_connect()
        if ui.autostart_broadcast:
            log.info(tr("按配置自动开始广播…"))
            self.broadcast_page.request_start()

    def show_page(self, index: int) -> None:
        self.nav.setCurrentRow(index)

    # ------------------------------------------------------------------ #
    def closeEvent(self, event: QCloseEvent) -> None:
        if self.ctx.engine.broadcasting:
            answer = QMessageBox.question(
                self, tr("退出"), tr("正在广播动捕数据，确定要退出吗？"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
        log.info(tr("正在退出…"))
        self._timer.stop()
        try:
            self.ctx.shutdown()
        except Exception:  # pragma: no cover - never block shutdown
            log.exception(tr("退出清理时出错"))
        event.accept()
