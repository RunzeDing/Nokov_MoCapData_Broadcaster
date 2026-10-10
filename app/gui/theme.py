"""Application look and feel."""

from __future__ import annotations

from PySide2.QtCore import Qt
from PySide2.QtGui import QColor, QFont, QPalette

# Colours shared by the 3D view, the plots and the tables.
BACKGROUND = "#10141b"
PANEL = "#161c26"
PANEL_ALT = "#1d2531"
BORDER = "#2b3648"
TEXT = "#dfe6f2"
TEXT_DIM = "#8b97ab"
ACCENT = "#3ea6ff"
OK = "#3ddc97"
WARN = "#ffb020"
ERROR = "#ff5c6c"

#: Distinguishable colour per rigid body, indexed by position in the body list.
BODY_COLORS = (
    "#3ea6ff", "#3ddc97", "#ffb020", "#ff5c6c", "#b47cff",
    "#00d4d4", "#ff8ac4", "#8ee04a", "#ff9a52", "#7fa8ff",
    "#e0e04a", "#4ae0c0", "#ff6f91", "#a0a0ff", "#5ad1ff",
    "#d4b800", "#63c7a0", "#ff7a45", "#c58cff", "#6ec6ff",
)

STATUS_COLORS = {
    "ok": OK,
    "new": ACCENT,
    "held": WARN,
    "held_lost": ERROR,
    "lost": ERROR,
    "glitch": ERROR,
}


def body_color(body_id: int) -> QColor:
    try:
        index = int(body_id)
    except (TypeError, ValueError):
        index = 0
    return QColor(BODY_COLORS[index % len(BODY_COLORS)])


def status_color(status: str) -> QColor:
    return QColor(STATUS_COLORS.get(status, TEXT_DIM))


def mono_font(point_size: int = 9) -> QFont:
    font = QFont("Consolas")
    font.setStyleHint(QFont.Monospace)
    font.setPointSize(point_size)
    return font


def apply_theme(app) -> None:
    """Apply the Fusion dark palette plus a compact stylesheet."""
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(PANEL))
    palette.setColor(QPalette.WindowText, QColor(TEXT))
    palette.setColor(QPalette.Base, QColor(BACKGROUND))
    palette.setColor(QPalette.AlternateBase, QColor(PANEL_ALT))
    palette.setColor(QPalette.ToolTipBase, QColor(PANEL_ALT))
    palette.setColor(QPalette.ToolTipText, QColor(TEXT))
    palette.setColor(QPalette.Text, QColor(TEXT))
    palette.setColor(QPalette.Button, QColor(PANEL_ALT))
    palette.setColor(QPalette.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.BrightText, QColor(ERROR))
    palette.setColor(QPalette.Link, QColor(ACCENT))
    palette.setColor(QPalette.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.HighlightedText, QColor("#06121f"))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(TEXT_DIM))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(TEXT_DIM))
    palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(TEXT_DIM))
    app.setPalette(palette)

    app.setStyleSheet(
        """
        QWidget { font-size: 12px; }
        QGroupBox {
            border: 1px solid %(border)s;
            border-radius: 6px;
            margin-top: 14px;
            padding-top: 6px;
            font-weight: 600;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 10px;
            padding: 0 4px;
            color: %(accent)s;
        }
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit {
            background: %(bg)s;
            border: 1px solid %(border)s;
            border-radius: 4px;
            padding: 3px 6px;
            selection-background-color: %(accent)s;
        }
        QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
            border: 1px solid %(accent)s;
        }
        QLineEdit[invalid="true"] { border: 1px solid %(error)s; }
        QPushButton {
            background: %(panel_alt)s;
            border: 1px solid %(border)s;
            border-radius: 4px;
            padding: 5px 12px;
        }
        QPushButton:hover { border-color: %(accent)s; }
        QPushButton:pressed { background: %(accent)s; color: #06121f; }
        QPushButton:disabled { color: %(dim)s; border-color: %(border)s; }
        QPushButton[accent="true"] {
            background: %(accent)s; color: #06121f; font-weight: 600;
        }
        QPushButton[accent="true"]:hover { background: #63b8ff; }
        QPushButton[danger="true"] { background: %(error)s; color: #1a0205; font-weight: 600; }
        QListWidget {
            background: %(bg)s;
            border: none;
            outline: none;
        }
        QListWidget::item {
            padding: 9px 14px;
            border-left: 3px solid transparent;
            color: %(dim)s;
        }
        QListWidget::item:selected {
            background: %(panel_alt)s;
            border-left: 3px solid %(accent)s;
            color: %(text)s;
        }
        QListWidget::item:hover { color: %(text)s; }
        QHeaderView::section {
            background: %(panel_alt)s;
            color: %(dim)s;
            border: none;
            border-right: 1px solid %(border)s;
            border-bottom: 1px solid %(border)s;
            padding: 4px 6px;
        }
        QTableWidget {
            background: %(bg)s;
            gridline-color: %(border)s;
            border: 1px solid %(border)s;
            border-radius: 4px;
        }
        QTableWidget::item:selected { background: %(accent)s; color: #06121f; }
        QTabWidget::pane { border: 1px solid %(border)s; border-radius: 4px; }
        QTabBar::tab {
            background: %(bg)s; color: %(dim)s;
            padding: 6px 14px; border: 1px solid %(border)s; border-bottom: none;
            border-top-left-radius: 4px; border-top-right-radius: 4px;
        }
        QTabBar::tab:selected { background: %(panel_alt)s; color: %(text)s; }
        QScrollBar:vertical { background: %(bg)s; width: 10px; margin: 0; }
        QScrollBar::handle:vertical { background: %(border)s; border-radius: 5px; min-height: 24px; }
        QScrollBar::handle:vertical:hover { background: %(accent)s; }
        QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
        QScrollBar:horizontal { background: %(bg)s; height: 10px; margin: 0; }
        QScrollBar::handle:horizontal { background: %(border)s; border-radius: 5px; min-width: 24px; }
        QCheckBox::indicator, QRadioButton::indicator { width: 14px; height: 14px; }
        QCheckBox::indicator:unchecked {
            border: 1px solid %(border)s; border-radius: 3px; background: %(bg)s;
        }
        QCheckBox::indicator:checked {
            border: 1px solid %(accent)s; border-radius: 3px; background: %(accent)s;
        }
        QStatusBar { background: %(panel_alt)s; color: %(dim)s; }
        QToolTip {
            background: %(panel_alt)s; color: %(text)s;
            border: 1px solid %(accent)s; padding: 4px;
        }
        """
        % {
            "bg": BACKGROUND,
            "panel": PANEL,
            "panel_alt": PANEL_ALT,
            "border": BORDER,
            "text": TEXT,
            "dim": TEXT_DIM,
            "accent": ACCENT,
            "error": ERROR,
        }
    )
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
