"""Real-time 3D view of the rigid bodies (pure QPainter, no OpenGL needed)."""

from __future__ import annotations

from ...i18n import tr

import math
from typing import Dict, List, Optional, Sequence, Tuple

from PySide2.QtCore import QPoint, QPointF, Qt, Signal
from PySide2.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QWheelEvent,
)
from PySide2.QtWidgets import QSizePolicy, QWidget

from ...core.math3d import quat_to_matrix
from ...core.frames import FrameSnapshot
from .. import theme

Vec3 = Tuple[float, float, float]

AXIS_COLORS = (QColor("#ff5c6c"), QColor("#3ddc97"), QColor("#3ea6ff"))


class View3D(QWidget):
    """Turntable camera 3D viewport."""

    bodyPicked = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        # camera
        self.azimuth = -62.0
        self.elevation = 24.0
        self.distance = 6.0
        self.target: Vec3 = (0.0, 0.0, 0.5)
        self.fov_deg = 45.0

        # scene
        self._bodies: List[dict] = []
        self._trails: Dict[int, List[Vec3]] = {}
        self._extent = 2.0
        self._has_data = False
        self._selected_id = -1
        self._hover_id = -1

        # options
        self.show_labels = True
        self.show_trails = True
        self.show_markers = False
        self.show_grid = True
        self.show_axes = True
        self.axis_length = 0.15
        self.max_draw_bodies = 64
        self.auto_fit_enabled = True

        self._last_mouse: Optional[QPoint] = None
        self._drag_mode = ""

    # ------------------------------------------------------------------ #
    # scene input
    # ------------------------------------------------------------------ #
    def update_scene(self, frame: Optional[FrameSnapshot],
                     trails: Optional[Dict[int, List[Vec3]]] = None,
                     markers: Optional[Dict[int, Sequence[Vec3]]] = None) -> None:
        bodies: List[dict] = []
        if frame is not None:
            for body_id in sorted(frame.bodies):
                if len(bodies) >= self.max_draw_bodies:
                    break
                body = frame.bodies[body_id]
                bodies.append({
                    "id": body_id,
                    "name": body.name,
                    "pos": (body.x, body.y, body.z),
                    "quat": (body.qx, body.qy, body.qz, body.qw),
                    "status": body.status,
                    "markers": tuple(markers.get(body_id, ())) if markers else (),
                })
        self._bodies = bodies
        self._trails = dict(trails or {})
        self._has_data = frame is not None and bool(frame.bodies)
        self._extent = self._compute_extent()
        if self.auto_fit_enabled and self._has_data:
            self._fit(keep_angles=True)
        self.update()

    def _compute_extent(self) -> float:
        points: List[Vec3] = []
        for body in self._bodies:
            points.append(body["pos"])
        for trail in self._trails.values():
            if trail:
                points.extend(trail[-30:])
        if not points:
            return self._extent
        largest = 1.0
        for x, y, z in points:
            largest = max(largest, abs(x), abs(y), abs(z))
        wanted = max(1.0, math.ceil(largest))
        # hysteresis so the grid does not twitch every frame
        if abs(wanted - self._extent) < 0.75:
            return self._extent
        return min(wanted, 25.0)

    def set_selected(self, body_id: int) -> None:
        if body_id != self._selected_id:
            self._selected_id = body_id
            self.update()

    def selected_id(self) -> int:
        return self._selected_id

    def set_view_options(self, **options) -> None:
        for key, value in options.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.update()

    # ------------------------------------------------------------------ #
    # camera helpers
    # ------------------------------------------------------------------ #
    def reset_view(self) -> None:
        self.azimuth = -62.0
        self.elevation = 24.0
        self.distance = 6.0
        self.target = (0.0, 0.0, 0.5)
        self.update()

    def auto_fit(self) -> None:
        self._fit(keep_angles=True)
        self.update()

    def _fit(self, keep_angles: bool = True) -> None:
        points: List[Vec3] = [body["pos"] for body in self._bodies]
        for trail in self._trails.values():
            if trail:
                points.extend(trail[-60:])
        if not points:
            return
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        zs = [p[2] for p in points]
        center = (
            0.5 * (min(xs) + max(xs)),
            0.5 * (min(ys) + max(ys)),
            0.5 * (min(zs) + max(zs)),
        )
        radius = max(
            0.4,
            0.5 * max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)),
        )
        # smooth towards the target so the view does not jump between frames
        blend = 0.25
        self.target = tuple(
            self.target[i] + (center[i] - self.target[i]) * blend for i in range(3)
        )
        wanted = max(1.5, radius * 3.4)
        self.distance = self.distance + (wanted - self.distance) * blend

    def _camera_basis(self):
        az = math.radians(self.azimuth)
        el = math.radians(self.elevation)
        ca, sa = math.cos(az), math.sin(az)
        ce, se = math.cos(el), math.sin(el)
        forward = (-ce * ca, -ce * sa, -se)
        right = (-sa, ca, 0.0)
        up = (-ca * se, -sa * se, ce)
        return forward, right, up

    def _project(self, point: Vec3):
        """Return ``(screen_x, screen_y, depth)`` or ``None`` when behind."""
        forward, right, up = self._camera_basis()
        vx = point[0] - self.target[0]
        vy = point[1] - self.target[1]
        vz = point[2] - self.target[2]
        cam_x = vx * right[0] + vy * right[1] + vz * right[2]
        cam_y = vx * up[0] + vy * up[1] + vz * up[2]
        cam_z = vx * forward[0] + vy * forward[1] + vz * forward[2]
        depth = cam_z + self.distance
        if depth < 0.05:
            return None
        focal = 0.5 * self.height() / math.tan(math.radians(self.fov_deg) * 0.5)
        sx = self.width() * 0.5 + focal * cam_x / depth
        sy = self.height() * 0.5 - focal * cam_y / depth
        return sx, sy, depth

    # ------------------------------------------------------------------ #
    # painting
    # ------------------------------------------------------------------ #
    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0.0, QColor("#0d1017"))
        gradient.setColorAt(1.0, QColor("#161d28"))
        painter.fillRect(self.rect(), QBrush(gradient))

        if self.show_grid:
            self._draw_grid(painter)
        if self.show_axes:
            self._draw_world_axes(painter)

        self._draw_trails(painter)
        self._draw_bodies(painter)

        if not self._has_data:
            self._draw_placeholder(painter)

        painter.setPen(QColor(theme.TEXT_DIM))
        painter.setFont(QFont("", 8))
        painter.drawText(
            8, self.height() - 8,
            tr("左键拖动=旋转  右键/中键拖动=平移  滚轮=缩放  双击=自动适配  R=重置"),
        )
        painter.end()

    def _draw_placeholder(self, painter: QPainter) -> None:
        painter.setPen(QColor(theme.TEXT_DIM))
        font = QFont()
        font.setPointSize(12)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, tr("等待动捕数据…\n（连接动捕服务器，或开启模拟数据源）"))

    def _draw_grid(self, painter: QPainter) -> None:
        extent = self._extent
        step = 0.5 if extent <= 4.0 else 1.0
        count = int(extent / step)
        pen = QPen(QColor(60, 74, 96, 110))
        pen.setWidthF(1.0)
        axis_pen = QPen(QColor(90, 110, 140, 170))
        axis_pen.setWidthF(1.4)

        for index in range(-count, count + 1):
            value = index * step
            self._draw_line(painter, (value, -extent, 0.0), (value, extent, 0.0),
                            axis_pen if index == 0 else pen)
            self._draw_line(painter, (-extent, value, 0.0), (extent, value, 0.0),
                            axis_pen if index == 0 else pen)

    def _draw_world_axes(self, painter: QPainter) -> None:
        length = max(0.35, min(1.0, self._extent * 0.25))
        origin = (0.0, 0.0, 0.0)
        names = ("X", "Y", "Z")
        for axis in range(3):
            end = [0.0, 0.0, 0.0]
            end[axis] = length
            pen = QPen(AXIS_COLORS[axis])
            pen.setWidthF(2.0)
            self._draw_line(painter, origin, tuple(end), pen)
            projected = self._project(tuple(end))
            if projected is not None:
                painter.setPen(AXIS_COLORS[axis])
                painter.setFont(QFont("", 9, QFont.Bold))
                painter.drawText(QPointF(projected[0] + 4, projected[1] - 4), names[axis])

    def _draw_line(self, painter: QPainter, start: Vec3, end: Vec3, pen: QPen) -> None:
        a = self._project(start)
        b = self._project(end)
        if a is None or b is None:
            return
        painter.setPen(pen)
        painter.drawLine(QPointF(a[0], a[1]), QPointF(b[0], b[1]))

    def _draw_trails(self, painter: QPainter) -> None:
        if not self.show_trails:
            return
        for body in self._bodies:
            body_id = body["id"]
            trail = self._trails.get(body_id)
            if not trail or len(trail) < 2:
                continue
            color = theme.body_color(body_id)
            path = QPainterPath()
            started = False
            for point in trail:
                projected = self._project(point)
                if projected is None:
                    started = False
                    continue
                if not started:
                    path.moveTo(projected[0], projected[1])
                    started = True
                else:
                    path.lineTo(projected[0], projected[1])
            faded = QColor(color)
            faded.setAlpha(120 if body_id != self._selected_id else 200)
            pen = QPen(faded)
            pen.setWidthF(1.6 if body_id != self._selected_id else 2.4)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)

    def _draw_bodies(self, painter: QPainter) -> None:
        ordered = []
        for body in self._bodies:
            projected = self._project(body["pos"])
            if projected is None:
                continue
            ordered.append((projected[2], body, projected))
        ordered.sort(key=lambda item: -item[0])  # far to near

        for _depth, body, projected in ordered:
            body_id = body["id"]
            color = theme.body_color(body_id)
            selected = body_id == self._selected_id
            status = body.get("status", "ok")
            point = QPointF(projected[0], projected[1])

            # orientation triad
            matrix = quat_to_matrix(*body["quat"])
            length = self.axis_length
            if length > 0:
                origin = body["pos"]
                for axis in range(3):
                    tip = (
                        origin[0] + matrix[0][axis] * length,
                        origin[1] + matrix[1][axis] * length,
                        origin[2] + matrix[2][axis] * length,
                    )
                    projected_tip = self._project(tip)
                    if projected_tip is None:
                        continue
                    pen = QPen(AXIS_COLORS[axis])
                    pen.setWidthF(2.2 if selected else 1.5)
                    alpha = 255 if selected else 190
                    axis_color = QColor(AXIS_COLORS[axis])
                    axis_color.setAlpha(alpha)
                    pen.setColor(axis_color)
                    painter.setPen(pen)
                    painter.drawLine(point, QPointF(projected_tip[0], projected_tip[1]))

            # markers
            if self.show_markers and body.get("markers"):
                painter.setPen(Qt.NoPen)
                marker_color = QColor(color)
                marker_color.setAlpha(150)
                painter.setBrush(QBrush(marker_color))
                for marker in body["markers"]:
                    projected_marker = self._project(marker)
                    if projected_marker is not None:
                        painter.drawEllipse(
                            QPointF(projected_marker[0], projected_marker[1]), 2.0, 2.0
                        )

            # position dot
            radius = 7.0 if selected else 5.0
            if status in ("held", "held_lost"):
                painter.setBrush(QBrush(QColor(theme.WARN)))
                painter.setPen(QPen(QColor("#5a3d00"), 1.2))
            elif status == "glitch":
                painter.setBrush(QBrush(QColor(theme.ERROR)))
                painter.setPen(QPen(QColor("#5a0009"), 1.2))
            else:
                painter.setBrush(QBrush(color))
                painter.setPen(QPen(color.darker(160), 1.2))
            painter.drawEllipse(point, radius, radius)
            if selected:
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor("#ffffff"), 1.4))
                painter.drawEllipse(point, radius + 4.0, radius + 4.0)

            # label
            if self.show_labels:
                label = body.get("name") or ("ID %d" % body_id)
                painter.setPen(QColor(theme.TEXT) if selected else QColor(theme.TEXT_DIM))
                font = QFont("", 9)
                font.setBold(selected)
                painter.setFont(font)
                painter.drawText(QPointF(point.x() + radius + 3, point.y() - radius - 1),
                                 "%d %s" % (body_id, label) if body.get("name") else label)

    # ------------------------------------------------------------------ #
    # interaction
    # ------------------------------------------------------------------ #
    def _pick(self, position) -> int:
        best_id = -1
        best_distance = 16.0
        for body in self._bodies:
            projected = self._project(body["pos"])
            if projected is None:
                continue
            dx = projected[0] - position.x()
            dy = projected[1] - position.y()
            distance = math.hypot(dx, dy)
            if distance < best_distance:
                best_distance = distance
                best_id = body["id"]
        return best_id

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._last_mouse = event.pos()
        if event.button() == Qt.LeftButton:
            self._drag_mode = "orbit"
        elif event.button() in (Qt.RightButton, Qt.MiddleButton):
            self._drag_mode = "pan"
        self.setFocus(Qt.MouseFocusReason)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._last_mouse is None:
            hovered = self._pick(event.pos())
            if hovered != self._hover_id:
                self._hover_id = hovered
            return
        delta = event.pos() - self._last_mouse
        self._last_mouse = event.pos()

        if self._drag_mode == "orbit":
            self.azimuth -= delta.x() * 0.45
            self.elevation = max(-89.0, min(89.0, self.elevation + delta.y() * 0.45))
            self.auto_fit_enabled = False
            self.update()
        elif self._drag_mode == "pan":
            forward, right, up = self._camera_basis()
            scale = self.distance * 0.0016
            tx = self.target[0] + (-right[0] * delta.x() + up[0] * delta.y()) * scale
            ty = self.target[1] + (-right[1] * delta.x() + up[1] * delta.y()) * scale
            tz = self.target[2] + (-right[2] * delta.x() + up[2] * delta.y()) * scale
            self.target = (tx, ty, tz)
            self.auto_fit_enabled = False
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_mode == "orbit":
            picked = self._pick(event.pos())
            self.bodyPicked.emit(picked)
        self._drag_mode = ""
        self._last_mouse = None

    def wheelEvent(self, event: QWheelEvent) -> None:
        steps = event.angleDelta().y() / 120.0
        if steps:
            self.distance = max(0.4, min(200.0, self.distance * (0.88 ** steps)))
            self.update()

    def mouseDoubleClickEvent(self, _event: QMouseEvent) -> None:
        self.auto_fit_enabled = True
        self.auto_fit()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_R:
            self.reset_view()
            self.auto_fit_enabled = True
        elif event.key() == Qt.Key_F:
            self.auto_fit()
        else:
            super().keyPressEvent(event)
