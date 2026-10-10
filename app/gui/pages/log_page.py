"""Log page plus profile / configuration management."""

from __future__ import annotations

from ...i18n import LANGUAGES, get_language, tr

import logging
import os
import subprocess
import sys
from typing import Optional

from PySide2.QtCore import Qt
from PySide2.QtGui import QBrush, QColor, QDesktopServices
from PySide2.QtCore import QUrl
from PySide2.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...config import (
    AppConfig,
    delete_profile,
    list_profiles,
    load_profile,
    save_profile,
)
from ...logging_setup import BRIDGE
from ...paths import config_path, data_dir, log_dir
from ...version import APP_TITLE, __version__
from .. import theme
from ..context import AppContext
from ..widgets.cards import HintLabel, SectionBox

log = logging.getLogger("nokov.gui.log")

LEVEL_COLORS = {
    "DEBUG": theme.TEXT_DIM,
    "INFO": theme.TEXT,
    "WARNING": theme.WARN,
    "ERROR": theme.ERROR,
    "CRITICAL": theme.ERROR,
}
LEVEL_ORDER = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}


class LogPage(QWidget):
    def __init__(self, ctx: AppContext, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._last_seq = 0
        self._next_refresh = 0.0

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # ---- log --------------------------------------------------------- #
        log_box = SectionBox(tr("运行日志"), tr("记录连接、广播与错误信息；同时写入日志文件。"))
        controls = QHBoxLayout()
        controls.setSpacing(8)
        controls.addWidget(QLabel(tr("最低级别")))
        self.level_combo = QComboBox()
        for level in ("DEBUG", "INFO", "WARNING", "ERROR"):
            self.level_combo.addItem(level, level)
        self.level_combo.setCurrentIndex(1)
        controls.addWidget(self.level_combo)

        self.autoscroll_check = QCheckBox(tr("自动滚动"))
        self.autoscroll_check.setChecked(True)
        controls.addWidget(self.autoscroll_check)

        clear_button = QPushButton(tr("清空显示"))
        clear_button.clicked.connect(self._on_clear)
        controls.addWidget(clear_button)

        copy_button = QPushButton(tr("复制全部"))
        copy_button.clicked.connect(self._on_copy)
        controls.addWidget(copy_button)

        open_log_button = QPushButton(tr("打开日志文件夹"))
        open_log_button.clicked.connect(lambda: _open_path(log_dir()))
        controls.addWidget(open_log_button)
        controls.addStretch(1)
        log_box.add_layout(controls)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(theme.mono_font(9))
        self.log_view.setMaximumBlockCount(4000)
        log_box.add(self.log_view)
        root.addWidget(log_box, 3)

        # ---- profiles ---------------------------------------------------- #
        profile_row = QHBoxLayout()
        profile_row.setSpacing(10)

        profile_box = SectionBox(tr("参数配置方案"), tr("把当前所有设置保存为方案，方便在不同项目间切换。"))
        self.profile_list = QListWidget()
        self.profile_list.setMinimumHeight(120)
        self.profile_list.itemDoubleClicked.connect(lambda _item: self._on_load_profile())
        profile_box.add(self.profile_list)

        profile_buttons = QHBoxLayout()
        for label, slot in ((tr("保存为方案"), self._on_save_profile),
                            (tr("载入选中方案"), self._on_load_profile),
                            (tr("删除选中方案"), self._on_delete_profile),
                            (tr("重载当前设置"), self._on_reload_default)):
            button = QPushButton(label)
            button.clicked.connect(slot)
            profile_buttons.addWidget(button)
        profile_buttons.addStretch(1)
        profile_box.add_layout(profile_buttons)

        open_config_button = QPushButton(tr("打开配置文件夹"))
        open_config_button.clicked.connect(lambda: _open_path(data_dir()))
        profile_box.add(open_config_button)
        profile_row.addWidget(profile_box, 1)

        # ---- startup behaviour ------------------------------------------- #
        behaviour_box = SectionBox(tr("启动行为"), tr("下次启动程序时自动执行的动作。"))

        language_row = QHBoxLayout()
        language_row.setSpacing(8)
        language_row.addWidget(QLabel(tr("界面语言")))
        self.language_combo = QComboBox()
        for code, label in LANGUAGES:
            self.language_combo.addItem(label, code)
        index = self.language_combo.findData(get_language())
        self.language_combo.setCurrentIndex(index if index >= 0 else 0)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        language_row.addWidget(self.language_combo)
        language_row.addStretch(1)
        behaviour_box.add_layout(language_row)
        behaviour_box.add(HintLabel(tr("切换后界面立即重建，正在进行的广播不会中断。")))

        self.autoconnect_check = QCheckBox(tr("启动后自动连接动捕服务器"))
        self.autoconnect_check.setChecked(ctx.config.ui.autoconnect)
        self.autoconnect_check.toggled.connect(self._on_startup_option)
        behaviour_box.add(self.autoconnect_check)
        self.autostart_check = QCheckBox(tr("启动后自动开始广播"))
        self.autostart_check.setChecked(ctx.config.ui.autostart_broadcast)
        self.autostart_check.toggled.connect(self._on_startup_option)
        behaviour_box.add(self.autostart_check)

        self.filelog_check = QCheckBox(tr("写入日志文件"))
        self.filelog_check.setChecked(ctx.config.ui.log_to_file)
        self.filelog_check.toggled.connect(self._on_startup_option)
        behaviour_box.add(self.filelog_check)
        behaviour_box.add(HintLabel(tr("配置文件：%s") % config_path()))
        behaviour_box.add(HintLabel(tr("日志文件：%s") % os.path.join(log_dir(), "nokov_broadcaster.log")))
        profile_row.addWidget(behaviour_box, 1)

        # ---- about ------------------------------------------------------- #
        about_box = SectionBox(tr("关于"))
        self.about_label = QLabel()
        self.about_label.setWordWrap(True)
        self.about_label.setTextFormat(Qt.RichText)
        about_box.add(self.about_label)
        profile_row.addWidget(about_box, 1)

        root.addLayout(profile_row, 1)

        self._reload_profiles()
        self._update_about()

    # ------------------------------------------------------------------ #
    # ------------------------------------------------------------------ #
    def _on_language_changed(self, _index: int) -> None:
        code = self.language_combo.currentData()
        if code and code != get_language():
            self.ctx.languageChangeRequested.emit(code)

    def _on_startup_option(self, *_args) -> None:
        ctx = self.ctx
        ctx.config.ui.autoconnect = self.autoconnect_check.isChecked()
        ctx.config.ui.autostart_broadcast = self.autostart_check.isChecked()
        ctx.config.ui.log_to_file = self.filelog_check.isChecked()
        ctx.config_changed()

    # ------------------------------------------------------------------ #
    def _update_about(self) -> None:
        sdk = self.ctx.session.info.sdk_version or tr("未加载")
        self.about_label.setText(
            tr("<b>%s</b> v%s<br>"
            "Nokov SDK: %s<br>"
            "Python: %s<br>"
            "默认广播格式与 <code>NokovSDKClient_STQ.py</code> 逐字节一致。")
            % (APP_TITLE, __version__, sdk,
               ".".join(str(part) for part in sys.version_info[:3]))
        )

    # ------------------------------------------------------------------ #
    # profiles
    # ------------------------------------------------------------------ #
    def _reload_profiles(self) -> None:
        self.profile_list.clear()
        for name in list_profiles():
            QListWidgetItem(name, self.profile_list)

    def _selected_profile(self) -> str:
        item = self.profile_list.currentItem()
        return item.text() if item is not None else ""

    def _on_save_profile(self) -> None:
        default = self._selected_profile() or tr("默认方案")
        name, ok = QInputDialog.getText(self, tr("保存方案"), tr("方案名称："), text=default)
        if not ok or not name.strip():
            return
        try:
            path = save_profile(name.strip(), self.ctx.config)
        except OSError as exc:
            QMessageBox.warning(self, tr("保存失败"), str(exc))
            return
        log.info(tr("已保存方案 %s -> %s"), name, path)
        self._reload_profiles()

    def _on_load_profile(self) -> None:
        name = self._selected_profile()
        if not name:
            QMessageBox.information(self, tr("提示"), tr("请先选择一个方案。"))
            return
        loaded = load_profile(name)
        if loaded is None:
            QMessageBox.warning(self, tr("载入失败"), tr("方案文件不存在或已损坏。"))
            self._reload_profiles()
            return
        self.ctx.config.apply_from(loaded)
        self.ctx.config_changed()
        self._sync_widgets()
        log.info(tr("已载入方案 %s"), name)
        QMessageBox.information(
            self, tr("已载入"),
            tr("方案“%s”已载入。\n如需生效到正在运行的界面，请到各页面确认参数。"
            "（连接与广播设置已即时生效）") % name,
        )
        self.ctx.request_pages_reload()

    def _on_delete_profile(self) -> None:
        name = self._selected_profile()
        if not name:
            return
        if QMessageBox.question(self, tr("删除方案"), tr("确定删除方案“%s”？") % name) != QMessageBox.Yes:
            return
        delete_profile(name)
        self._reload_profiles()

    def _on_reload_default(self) -> None:
        self.ctx.config.apply_from(AppConfig())
        self.ctx.config_changed()
        self._sync_widgets()
        self.ctx.request_pages_reload()
        log.info(tr("已恢复默认设置"))

    # ------------------------------------------------------------------ #
    def reload_from_config(self) -> None:
        self._sync_widgets()
        self._reload_profiles()
        self._update_about()

    def _sync_widgets(self) -> None:
        self.autoconnect_check.setChecked(self.ctx.config.ui.autoconnect)
        self.autostart_check.setChecked(self.ctx.config.ui.autostart_broadcast)
        self.filelog_check.setChecked(self.ctx.config.ui.log_to_file)

    # ------------------------------------------------------------------ #
    # log view
    # ------------------------------------------------------------------ #
    def _on_clear(self) -> None:
        self.log_view.clear()

    def _on_copy(self) -> None:
        from PySide2.QtWidgets import QApplication
        QApplication.clipboard().setText(self.log_view.toPlainText())

    def refresh(self, now: float) -> None:
        if now < self._next_refresh:
            return
        self._next_refresh = now + 0.2

        minimum = LEVEL_ORDER.get(self.level_combo.currentData(), 20)
        entries = BRIDGE.tail(self._last_seq)
        if not entries:
            return
        self._last_seq = entries[-1].seq

        scrollbar = self.log_view.verticalScrollBar()
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 4
        lines = []
        for entry in entries:
            if LEVEL_ORDER.get(entry.level, 20) < minimum:
                continue
            lines.append("%s %-7s [%s] %s" % (entry.time_text, entry.level,
                                              entry.logger.replace("nokov.", ""),
                                              entry.message))
        if not lines:
            return
        self.log_view.appendPlainText("\n".join(lines))
        if self.autoscroll_check.isChecked() and at_bottom:
            scrollbar.setValue(scrollbar.maximum())


def _open_path(path: str) -> None:
    """Open a folder in the system file browser."""
    try:
        os.makedirs(path, exist_ok=True)
        if hasattr(os, "startfile"):
            os.startfile(path)  # noqa: S606 - Windows shell open
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
    except OSError as exc:
        log.warning(tr("打开路径失败 %s: %s"), path, exc)
