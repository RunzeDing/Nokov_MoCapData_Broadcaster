"""Live table of every rigid body with its quality indicators."""

from __future__ import annotations

from ...i18n import tr

from typing import Dict, List, Optional

from PySide2.QtCore import Qt, Signal
from PySide2.QtGui import QBrush, QColor
from PySide2.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
)

from ...core.frames import FrameSnapshot, body_status_label
from ...core.pipeline import Pipeline
from .. import theme

def columns():
    return (
        ("id", "ID", 46),
        ("name", tr("名称"), 120),
        ("status", tr("状态"), 66),
        ("x", "X (m)", 78),
        ("y", "Y (m)", 78),
        ("z", "Z (m)", 78),
        ("speed", tr("速度 (m/s)"), 84),
        ("markers", tr("标记点"), 60),
        ("error", tr("误差 (mm)"), 76),
        ("quat", tr("四元数 (x,y,z,w)"), 230),
        ("glitch", tr("异常累计"), 68),
    )


class BodyTable(QTableWidget):
    """One row per body, updated at a modest rate to stay cheap."""

    bodySelected = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(0, len(columns()), parent)
        self.setHorizontalHeaderLabels([label for _key, label, _width in columns()])
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setSortingEnabled(False)
        self.setWordWrap(False)

        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        for index, (_key, _label, width) in enumerate(columns()):
            self.setColumnWidth(index, width)
        header.setStretchLastSection(True)

        self._rows: Dict[int, int] = {}
        self._suppress = False
        self.itemSelectionChanged.connect(self._on_selection)

    # ------------------------------------------------------------------ #
    def _on_selection(self) -> None:
        if self._suppress:
            return
        items = self.selectedItems()
        if not items:
            return
        body_id = self.item(items[0].row(), 0).data(Qt.UserRole)
        if body_id is not None:
            self.bodySelected.emit(int(body_id))

    def selected_body(self) -> int:
        items = self.selectedItems()
        if not items:
            return -1
        value = self.item(items[0].row(), 0).data(Qt.UserRole)
        return int(value) if value is not None else -1

    def select_body(self, body_id: int) -> None:
        row = self._rows.get(body_id)
        if row is None:
            return
        self._suppress = True
        try:
            self.selectRow(row)
        finally:
            self._suppress = False

    # ------------------------------------------------------------------ #
    def update_table(self, frame: Optional[FrameSnapshot], pipeline: Optional[Pipeline] = None,
                     known_names: Optional[Dict[int, str]] = None) -> None:
        rows: List[tuple] = []

        seen = set()
        if frame is not None:
            for body_id in sorted(frame.bodies):
                seen.add(body_id)
                rows.append(self._row_values(frame.bodies[body_id], pipeline, frame.frame_no))

        # bodies that exist in the project but are missing from this frame
        if known_names:
            for body_id in sorted(known_names):
                if body_id in seen:
                    continue
                if pipeline is not None and not pipeline.selector.accepts_id(body_id):
                    continue
                rows.append((
                    body_id, known_names.get(body_id, ""), body_status_label("lost"),
                    "", "", "", "", "", "", "", "", "lost",
                ))

        self._suppress = True
        try:
            self.setRowCount(len(rows))
            for row_index, values in enumerate(rows):
                body_id = values[0]
                status_code = values[11] if len(values) > 11 else "ok"
                self._rows[body_id] = row_index
                for column, value in enumerate(values[:11]):
                    if column == 0:
                        item = QTableWidgetItem(str(body_id))
                        item.setData(Qt.UserRole, body_id)
                    else:
                        item = QTableWidgetItem(str(value))
                    if column >= 3 and column not in (10,):
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    if column == 2:
                        item.setForeground(QBrush(theme.status_color(status_code)))
                    elif column == 10:
                        item.setForeground(QBrush(QColor(theme.WARN)))
                    self.setItem(row_index, column, item)

            # keep the previous selection if the body is still present
            current = self.selected_body()
            if current in self._rows:
                self.selectRow(self._rows[current])
            self._rows = {values[0]: index for index, values in enumerate(rows)}
        finally:
            self._suppress = False

    @staticmethod
    def _row_values(body, pipeline: Optional[Pipeline], frame_no: int):
        glitches = str(pipeline.glitch_count(body.body_id)) if pipeline is not None else ""
        quat = "%.3f, %.3f, %.3f, %.3f" % (body.qx, body.qy, body.qz, body.qw)
        return (
            body.body_id,
            body.name or "",
            body_status_label(body.status),
            "%+.4f" % body.x,
            "%+.4f" % body.y,
            "%+.4f" % body.z,
            "%.3f" % body.speed,
            str(body.n_markers),
            "%.3f" % body.mean_error,
            quat,
            glitches,
            # not displayed: the untranslated status code, used for row colouring
            body.status,
        )
