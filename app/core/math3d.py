"""Small pure-python 3D maths helpers.

Deliberately free of numpy/scipy so the frozen executable stays small and the
per-frame path stays allocation-light.
"""

from __future__ import annotations

import math
from typing import Tuple

__all__ = [
    "quat_normalize",
    "quat_multiply",
    "quat_from_axis_angle",
    "quat_from_yaw",
    "quat_to_matrix",
    "quat_from_matrix",
    "quat_to_euler_zyx_deg",
    "mat3_multiply",
    "mat3_transpose",
    "quat_nlerp",
    "QuatLowPass",
    "Vec3Smoother",
]


def quat_normalize(qx: float, qy: float, qz: float, qw: float) -> Tuple[float, float, float, float]:
    """Return a unit quaternion; identity when the input is degenerate."""
    norm = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
    if norm <= 1e-12:
        return 0.0, 0.0, 0.0, 1.0
    return qx / norm, qy / norm, qz / norm, qw / norm


def quat_multiply(
    ax: float, ay: float, az: float, aw: float,
    bx: float, by: float, bz: float, bw: float,
) -> Tuple[float, float, float, float]:
    """Hamilton product ``a * b``."""
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def quat_from_axis_angle(ax: float, ay: float, az: float, angle_rad: float):
    norm = math.sqrt(ax * ax + ay * ay + az * az)
    if norm <= 1e-12:
        return 0.0, 0.0, 0.0, 1.0
    half = angle_rad * 0.5
    s = math.sin(half) / norm
    return ax * s, ay * s, az * s, math.cos(half)


def quat_from_yaw(yaw_rad: float):
    """Rotation about the world +Z axis."""
    return quat_from_axis_angle(0.0, 0.0, 1.0, yaw_rad)


def quat_to_matrix(qx: float, qy: float, qz: float, qw: float):
    """Return a row-major 3x3 tuple-of-tuples rotation matrix."""
    xx, yy, zz = qx * qx, qy * qy, qz * qz
    xy, xz, yz = qx * qy, qx * qz, qy * qz
    wx, wy, wz = qw * qx, qw * qy, qw * qz
    return (
        (1.0 - 2.0 * (yy + zz), 2.0 * (xy - wz), 2.0 * (xz + wy)),
        (2.0 * (xy + wz), 1.0 - 2.0 * (xx + zz), 2.0 * (yz - wx)),
        (2.0 * (xz - wy), 2.0 * (yz + wx), 1.0 - 2.0 * (xx + yy)),
    )


def quat_from_matrix(m):
    """Extract a unit quaternion from a row-major 3x3 rotation matrix.

    Uses the trace / largest-diagonal branch (Shepperd's method) so that it stays
    numerically stable for all rotations.
    """
    m00, m01, m02 = m[0]
    m10, m11, m12 = m[1]
    m20, m21, m22 = m[2]
    trace = m00 + m11 + m22
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        qw = 0.25 * s
        qx = (m21 - m12) / s
        qy = (m02 - m20) / s
        qz = (m10 - m01) / s
    elif m00 > m11 and m00 > m22:
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2.0
        qw = (m21 - m12) / s
        qx = 0.25 * s
        qy = (m01 + m10) / s
        qz = (m02 + m20) / s
    elif m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2.0
        qw = (m02 - m20) / s
        qx = (m01 + m10) / s
        qy = 0.25 * s
        qz = (m12 + m21) / s
    else:
        s = math.sqrt(1.0 + m22 - m00 - m11) * 2.0
        qw = (m10 - m01) / s
        qx = (m02 + m20) / s
        qy = (m12 + m21) / s
        qz = 0.25 * s
    return quat_normalize(qx, qy, qz, qw)


def mat3_multiply(a, b):
    """Row-major 3x3 matrix product ``a * b``."""
    return tuple(
        tuple(
            a[row][0] * b[0][col] + a[row][1] * b[1][col] + a[row][2] * b[2][col]
            for col in range(3)
        )
        for row in range(3)
    )


def mat3_transpose(m):
    return (
        (m[0][0], m[1][0], m[2][0]),
        (m[0][1], m[1][1], m[2][1]),
        (m[0][2], m[1][2], m[2][2]),
    )


def quat_to_euler_zyx_deg(qx: float, qy: float, qz: float, qw: float):
    """Roll/pitch/yaw in degrees using the Z-Y-X (yaw-pitch-roll) convention.

    Matches the usual motion-capture convention: roll about X, pitch about Y,
    yaw about Z, applied as ``R = Rz(yaw) * Ry(pitch) * Rx(roll)``.
    """
    qx, qy, qz, qw = quat_normalize(qx, qy, qz, qw)
    sinr_cosp = 2.0 * (qw * qx + qy * qz)
    cosr_cosp = 1.0 - 2.0 * (qx * qx + qy * qy)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    sinp = 2.0 * (qw * qy - qz * qx)
    if sinp >= 1.0:
        pitch = math.pi * 0.5
    elif sinp <= -1.0:
        pitch = -math.pi * 0.5
    else:
        pitch = math.asin(sinp)

    siny_cosp = 2.0 * (qw * qz + qx * qy)
    cosy_cosp = 1.0 - 2.0 * (qy * qy + qz * qz)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    scale = 180.0 / math.pi
    return roll * scale, pitch * scale, yaw * scale


def quat_nlerp(a, b, t: float):
    """Normalised linear interpolation taking the shortest arc."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    dot = ax * bx + ay * by + az * bz + aw * bw
    if dot < 0.0:
        bx, by, bz, bw = -bx, -by, -bz, -bw
    return quat_normalize(
        ax + (bx - ax) * t,
        ay + (by - ay) * t,
        az + (bz - az) * t,
        aw + (bw - aw) * t,
    )


class QuatLowPass:
    """Exponential smoothing for a quaternion stream (per body)."""

    def __init__(self, alpha: float = 0.35) -> None:
        self.alpha = alpha
        self.value = None

    def reset(self) -> None:
        self.value = None

    def update(self, q):
        if self.value is None:
            self.value = quat_normalize(*q)
        else:
            self.value = quat_nlerp(self.value, q, self.alpha)
        return self.value


class Vec3Smoother:
    """Sliding-window / exponential smoothing for a 3-vector.

    ``mode`` is one of ``sma`` (moving average), ``median``, ``ema`` or
    ``one_euro``.  ``none`` disables smoothing entirely.
    """

    def __init__(self, mode: str = "none", window: int = 5, alpha: float = 0.35,
                 min_cutoff: float = 1.0, beta: float = 0.05) -> None:
        self.mode = mode
        self.window = max(1, int(window))
        self.alpha = alpha
        self.min_cutoff = min_cutoff
        self.beta = beta
        self._buffer = []
        self._ema = None
        self._oe = None  # (x_prev, dx_prev) per axis

    def reset(self) -> None:
        self._buffer = []
        self._ema = None
        self._oe = None

    # -- individual filters ------------------------------------------------ #
    def _sma_filter(self, value):
        self._buffer.append(value)
        if len(self._buffer) > self.window:
            del self._buffer[0]
        count = len(self._buffer)
        return (
            sum(v[0] for v in self._buffer) / count,
            sum(v[1] for v in self._buffer) / count,
            sum(v[2] for v in self._buffer) / count,
        )

    def _median_filter(self, value):
        self._buffer.append(value)
        if len(self._buffer) > self.window:
            del self._buffer[0]
        count = len(self._buffer)
        half = count // 2
        out = []
        for axis in range(3):
            column = sorted(v[axis] for v in self._buffer)
            out.append(column[half] if count % 2 else 0.5 * (column[half - 1] + column[half]))
        return out[0], out[1], out[2]

    def _ema_filter(self, value):
        if self._ema is None:
            self._ema = list(value)
        else:
            a = self.alpha
            self._ema = [self._ema[i] + a * (value[i] - self._ema[i]) for i in range(3)]
        return self._ema[0], self._ema[1], self._ema[2]

    def _one_euro_filter(self, value, dt: float):
        # 1euro filter (Casiez et al. 2012), applied per axis.
        if dt <= 1e-6:
            dt = 1.0 / 120.0
        if self._oe is None:
            self._oe = [(value[i], 0.0) for i in range(3)]
            return value

        out = []
        for i in range(3):
            x_prev, dx_prev = self._oe[i]
            dx = (value[i] - x_prev) / dt
            # low-pass the derivative
            alpha_d = self._smoothing_factor(1.0, dt)
            dx_hat = dx_prev + alpha_d * (dx - dx_prev)
            cutoff = self.min_cutoff + self.beta * abs(dx_hat)
            alpha = self._smoothing_factor(cutoff, dt)
            x_hat = x_prev + alpha * (value[i] - x_prev)
            self._oe[i] = (x_hat, dx_hat)
            out.append(x_hat)
        return out[0], out[1], out[2]

    @staticmethod
    def _smoothing_factor(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2.0 * math.pi * max(cutoff, 1e-6))
        return 1.0 / (1.0 + tau / dt)

    # -- public ------------------------------------------------------------ #
    def update(self, value, dt: float = 1.0 / 120.0):
        mode = self.mode
        if mode in ("none", "", None):
            return value
        if mode == "sma":
            return self._sma_filter(value)
        if mode == "median":
            return self._median_filter(value)
        if mode == "ema":
            return self._ema_filter(value)
        if mode == "one_euro":
            return self._one_euro_filter(value, dt)
        return value
