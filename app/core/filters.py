"""Per-body filter state: validity tracking, hold-last-valid and smoothing."""

from __future__ import annotations

from ..i18n import tr

from typing import Dict, Optional, Set, Tuple

from .frames import BodyState
from .math3d import QuatLowPass, Vec3Smoother

__all__ = ["BodyTrack", "BodySelector"]


class BodyTrack:
    """Everything the pipeline remembers about one rigid body between frames."""

    __slots__ = (
        "body_id", "name",
        "valid_x", "valid_y", "valid_z",
        "valid_qx", "valid_qy", "valid_qz", "valid_qw",
        "valid_vx", "valid_vy", "valid_vz",
        "valid_roll", "valid_pitch", "valid_yaw",
        "valid_raw_x", "valid_raw_y", "valid_raw_z",
        "has_valid",
        "held_frames",
        "last_seen_frame",
        "last_seen_time",
        "smoother", "quat_smoother",
        "prev_x", "prev_y", "prev_z", "prev_time",
        "prev_vx", "prev_vy", "prev_vz",
        "has_prev",
        "glitch_count",
        "total_frames",
    )

    def __init__(self, body_id: int, name: str = "") -> None:
        self.body_id = body_id
        self.name = name
        self.valid_x = self.valid_y = self.valid_z = 0.0
        self.valid_qx = self.valid_qy = self.valid_qz = 0.0
        self.valid_qw = 1.0
        self.valid_vx = self.valid_vy = self.valid_vz = 0.0
        self.valid_roll = self.valid_pitch = self.valid_yaw = 0.0
        self.valid_raw_x = self.valid_raw_y = self.valid_raw_z = 0.0
        self.has_valid = False
        self.held_frames = 0
        self.last_seen_frame = -1
        self.last_seen_time = 0.0
        self.smoother: Optional[Vec3Smoother] = None
        self.quat_smoother: Optional[QuatLowPass] = None
        self.prev_x = self.prev_y = self.prev_z = 0.0
        self.prev_time = 0.0
        self.prev_vx = self.prev_vy = self.prev_vz = 0.0
        self.has_prev = False
        self.glitch_count = 0
        self.total_frames = 0

    # -- cache ------------------------------------------------------------- #
    def remember(self, body: BodyState) -> None:
        self.valid_x, self.valid_y, self.valid_z = body.x, body.y, body.z
        self.valid_qx, self.valid_qy, self.valid_qz, self.valid_qw = body.quaternion
        self.valid_vx, self.valid_vy, self.valid_vz = body.velocity
        self.valid_roll, self.valid_pitch, self.valid_yaw = (
            body.roll, body.pitch, body.yaw,
        )
        self.valid_raw_x, self.valid_raw_y, self.valid_raw_z = (
            body.raw_x, body.raw_y, body.raw_z,
        )
        self.has_valid = True
        self.held_frames = 0

    def restore(self, body: BodyState) -> None:
        """Overwrite ``body`` with the last known-good sample."""
        body.x, body.y, body.z = self.valid_x, self.valid_y, self.valid_z
        body.qx, body.qy, body.qz, body.qw = (
            self.valid_qx, self.valid_qy, self.valid_qz, self.valid_qw,
        )
        body.vx, body.vy, body.vz = self.valid_vx, self.valid_vy, self.valid_vz
        body.roll, body.pitch, body.yaw = self.valid_roll, self.valid_pitch, self.valid_yaw
        body.raw_x, body.raw_y, body.raw_z = (
            self.valid_raw_x, self.valid_raw_y, self.valid_raw_z,
        )

    def reset_smoothing(self) -> None:
        if self.smoother is not None:
            self.smoother.reset()
        if self.quat_smoother is not None:
            self.quat_smoother.reset()
        self.has_prev = False

    def configure_smoothing(self, config) -> None:
        mode = getattr(config, "smoothing", "none")
        window = int(getattr(config, "smoothing_window", 5))
        alpha = float(getattr(config, "smoothing_alpha", 0.35))
        min_cutoff = float(getattr(config, "one_euro_min_cutoff", 1.0))
        beta = float(getattr(config, "one_euro_beta", 0.05))

        if mode in ("none", "", None):
            self.smoother = None
        else:
            if (
                self.smoother is None
                or self.smoother.mode != mode
                or self.smoother.window != max(1, window)
                or abs(self.smoother.alpha - alpha) > 1e-9
                or abs(self.smoother.min_cutoff - min_cutoff) > 1e-9
                or abs(self.smoother.beta - beta) > 1e-9
            ):
                self.smoother = Vec3Smoother(mode, window, alpha, min_cutoff, beta)

        if getattr(config, "smooth_orientation", False):
            if self.quat_smoother is None or abs(self.quat_smoother.alpha - alpha) > 1e-9:
                self.quat_smoother = QuatLowPass(alpha)
        else:
            self.quat_smoother = None


class BodySelector:
    """Fast membership test for the include/exclude/range body filters."""

    def __init__(self, config=None) -> None:
        self.enabled = False
        self.min_id = -1
        self.max_id = 2147483647
        self.include: Optional[Set[int]] = None
        self.exclude: Set[int] = set()
        self.require_markers = False
        self.min_markers = 0
        if config is not None:
            self.update(config)

    def update(self, config) -> None:
        from ..config import parse_id_list  # local import avoids a cycle

        self.min_id = int(getattr(config, "min_body_id", -1))
        self.max_id = int(getattr(config, "max_body_id", 2147483647))
        include_raw = parse_id_list(getattr(config, "include_ids", ""))
        exclude_raw = parse_id_list(getattr(config, "exclude_ids", ""))
        self.include = set(include_raw) if include_raw else None
        self.exclude = set(exclude_raw)
        self.require_markers = bool(getattr(config, "require_markers", False))
        self.min_markers = int(getattr(config, "min_markers", 0))
        self.enabled = (
            self.min_id > -1
            or self.max_id < 2147483647
            or self.include is not None
            or bool(self.exclude)
            or self.require_markers
            or self.min_markers > 0
        )

    def accepts(self, body: BodyState) -> bool:
        if not self.accepts_id(body.body_id):
            return False
        if self.require_markers or self.min_markers > 0:
            minimum = self.min_markers if self.min_markers > 0 else 1
            if body.n_markers < minimum:
                return False
        return True

    def accepts_id(self, body_id: int) -> bool:
        if body_id < self.min_id or body_id > self.max_id:
            return False
        if self.include is not None and body_id not in self.include:
            return False
        if body_id in self.exclude:
            return False
        return True

    def describe(self) -> str:
        if not self.enabled:
            return tr("全部刚体")
        parts = []
        if self.min_id > -1 or self.max_id < 2147483647:
            parts.append("ID %d..%d" % (self.min_id, self.max_id))
        if self.include is not None:
            parts.append(tr("仅 %s") % ",".join(str(i) for i in sorted(self.include)))
        if self.exclude:
            parts.append(tr("排除 %s") % ",".join(str(i) for i in sorted(self.exclude)))
        if self.require_markers or self.min_markers > 0:
            parts.append(tr("标记点>=%d") % (self.min_markers if self.min_markers > 0 else 1))
        return "；".join(parts)
