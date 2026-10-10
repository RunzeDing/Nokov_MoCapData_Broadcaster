"""Coordinate-frame handling: axis remap, signs, scaling, offsets and yaw.

The transform is expressed as a 3x3 matrix ``M`` (a signed axis permutation).

* Position:   ``p' = Rz(yaw) * (M * (p_m * unit_scale)) + offset``
* Orientation (proper maps): ``R' = Rz(yaw) * M * R * M^T``
"""

from __future__ import annotations

from ..i18n import tr

import math
from typing import Tuple

from .math3d import (
    mat3_multiply,
    mat3_transpose,
    quat_from_matrix,
    quat_from_yaw,
    quat_multiply,
    quat_to_matrix,
)
from .frames import BodyState

_AXIS_INDEX = {"X": 0, "Y": 1, "Z": 2}


def build_axis_matrix(axis_map: str, sign_x: int, sign_y: int, sign_z: int):
    """Build ``M`` such that ``out[k] = sign[k] * in[axis_map[k]]``."""
    axis_map = (axis_map or "XYZ").upper()
    if sorted(axis_map) != ["X", "Y", "Z"]:
        axis_map = "XYZ"
    signs = (sign_x, sign_y, sign_z)
    rows = []
    for out_axis, letter in enumerate(axis_map):
        row = [0.0, 0.0, 0.0]
        row[_AXIS_INDEX[letter]] = float(signs[out_axis])
        rows.append(tuple(row))
    return tuple(rows)


def matrix_determinant(m) -> float:
    return (
        m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
        - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
        + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
    )


class CoordinateTransform:
    """Callable, pre-computed transform driven by :class:`TransformConfig`."""

    def __init__(self, config=None) -> None:
        self._matrix = None
        self._matrix_t = None
        self._identity = True
        self._det = 1.0
        self.unit_scale = 1.0
        self.offset = (0.0, 0.0, 0.0)
        self.yaw_rad = 0.0
        self._yaw_q = (0.0, 0.0, 0.0, 1.0)
        if config is not None:
            self.update(config)

    # ------------------------------------------------------------------ #
    def update(self, config) -> None:
        axis_map = getattr(config, "axis_map", "XYZ")
        self._matrix = build_axis_matrix(
            axis_map,
            int(getattr(config, "sign_x", 1)),
            int(getattr(config, "sign_y", 1)),
            int(getattr(config, "sign_z", 1)),
        )
        self._matrix_t = mat3_transpose(self._matrix)
        self._det = matrix_determinant(self._matrix)
        self.unit_scale = float(getattr(config, "unit_scale", 1.0) or 1.0)
        self.offset = (
            float(getattr(config, "offset_x", 0.0) or 0.0),
            float(getattr(config, "offset_y", 0.0) or 0.0),
            float(getattr(config, "offset_z", 0.0) or 0.0),
        )
        self.yaw_rad = math.radians(float(getattr(config, "yaw_deg", 0.0) or 0.0))
        self._yaw_q = quat_from_yaw(self.yaw_rad)
        self._identity = (
            self._matrix == ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
            and self.unit_scale == 1.0
            and self.offset == (0.0, 0.0, 0.0)
            and abs(self.yaw_rad) < 1e-12
        )

    @property
    def is_identity(self) -> bool:
        return self._identity

    @property
    def is_proper(self) -> bool:
        """False when the axis map mirrors the frame (odd number of flips)."""
        return self._det > 0.0

    # ------------------------------------------------------------------ #
    def position(self, x_m: float, y_m: float, z_m: float) -> Tuple[float, float, float]:
        if self._identity:
            return x_m, y_m, z_m
        m = self._matrix
        scale = self.unit_scale
        x = (m[0][0] * x_m + m[0][1] * y_m + m[0][2] * z_m) * scale
        y = (m[1][0] * x_m + m[1][1] * y_m + m[1][2] * z_m) * scale
        z = (m[2][0] * x_m + m[2][1] * y_m + m[2][2] * z_m) * scale
        if self.yaw_rad:
            cos_a = math.cos(self.yaw_rad)
            sin_a = math.sin(self.yaw_rad)
            x, y = x * cos_a - y * sin_a, x * sin_a + y * cos_a
        ox, oy, oz = self.offset
        return x + ox, y + oy, z + oz

    def orientation(self, qx: float, qy: float, qz: float, qw: float):
        """Rotate the body frame with the same matrix and optional yaw."""
        if self._identity:
            return qx, qy, qz, qw
        if abs(self.yaw_rad) < 1e-12 and self._matrix == (
            (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
        ):
            return qx, qy, qz, qw
        rotation = quat_to_matrix(qx, qy, qz, qw)
        # R' = M * R * M^T  (a similarity transform by the axis permutation)
        rotated = mat3_multiply(mat3_multiply(self._matrix, rotation), self._matrix_t)
        qx2, qy2, qz2, qw2 = quat_from_matrix(rotated)
        if self.yaw_rad:
            qx2, qy2, qz2, qw2 = quat_multiply(
                self._yaw_q[0], self._yaw_q[1], self._yaw_q[2], self._yaw_q[3],
                qx2, qy2, qz2, qw2,
            )
        return qx2, qy2, qz2, qw2

    def vector(self, vx: float, vy: float, vz: float) -> Tuple[float, float, float]:
        """Transform a direction (no offset, no yaw)."""
        if self._identity:
            return vx, vy, vz
        m = self._matrix
        scale = self.unit_scale
        return (
            (m[0][0] * vx + m[0][1] * vy + m[0][2] * vz) * scale,
            (m[1][0] * vx + m[1][1] * vy + m[1][2] * vz) * scale,
            (m[2][0] * vx + m[2][1] * vy + m[2][2] * vz) * scale,
        )

    def apply_to_body(self, body: BodyState) -> None:
        """In-place transform of a body's position, orientation and velocity."""
        if self._identity:
            return
        body.x, body.y, body.z = self.position(body.x, body.y, body.z)
        body.qx, body.qy, body.qz, body.qw = self.orientation(
            body.qx, body.qy, body.qz, body.qw
        )
        if body.vx or body.vy or body.vz:
            body.vx, body.vy, body.vz = self.vector(body.vx, body.vy, body.vz)
        if body.ax or body.ay or body.az:
            body.ax, body.ay, body.az = self.vector(body.ax, body.ay, body.az)


def describe_transform(config) -> str:
    """Short human-readable summary used by the UI and logs."""
    matrix = build_axis_matrix(
        getattr(config, "axis_map", "XYZ"),
        int(getattr(config, "sign_x", 1)),
        int(getattr(config, "sign_y", 1)),
        int(getattr(config, "sign_z", 1)),
    )
    labels = ["X", "Y", "Z"]
    parts = []
    for row_index, row in enumerate(matrix):
        for col_index, value in enumerate(row):
            if value:
                parts.append(
                    "%s' = %s%s"
                    % (labels[row_index], "-" if value < 0 else "", labels[col_index])
                )
    if abs(float(getattr(config, "unit_scale", 1.0)) - 1.0) > 1e-12:
        parts.append("x%.4g" % float(getattr(config, "unit_scale")))
    yaw = float(getattr(config, "yaw_deg", 0.0) or 0.0)
    if abs(yaw) > 1e-12:
        parts.append("yaw %.2f°" % yaw)
    return ", ".join(parts) if parts else tr("恒等变换")
