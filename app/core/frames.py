"""Frame data model shared by the SDK reader, the pipeline and the encoders."""

from __future__ import annotations

from ..i18n import tr

from typing import Dict, List, Optional, Tuple

__all__ = ["BodyState", "FrameSnapshot", "body_status_label"]

#: status code -> Chinese source label (translated on demand)
_STATUS_LABELS = {
    "ok": "正常",
    "held": "保持",
    "new": "新建",
    "lost": "丢失",
    "held_lost": "保持(丢失)",
    "glitch": "异常",
}


def body_status_label(status: str) -> str:
    """Localised label for :attr:`BodyState.status`."""
    return tr(_STATUS_LABELS.get(status, status))


class BodyState:
    """One rigid body for one frame, after mm -> m conversion.

    Instances are created per frame and per body, so the class keeps ``__slots__``
    to hold down allocation cost at high frame rates.
    """

    __slots__ = (
        "body_id", "name",
        "x", "y", "z",
        "qx", "qy", "qz", "qw",
        "vx", "vy", "vz",
        "ax", "ay", "az",
        "roll", "pitch", "yaw",
        "n_markers", "mean_error",
        "markers", "marker_ids",
        "status",
        "raw_x", "raw_y", "raw_z",
        "held_frames",
        "has_extend",
        "params",
    )

    def __init__(self, body_id: int = 0, name: str = "") -> None:
        self.body_id = body_id
        self.name = name
        self.x = self.y = self.z = 0.0
        self.qx = self.qy = self.qz = 0.0
        self.qw = 1.0
        self.vx = self.vy = self.vz = 0.0
        self.ax = self.ay = self.az = 0.0
        self.roll = self.pitch = self.yaw = 0.0
        self.n_markers = 0
        self.mean_error = 0.0
        self.markers: Tuple[Tuple[float, float, float], ...] = ()
        self.marker_ids: Tuple[int, ...] = ()
        self.status = "ok"
        self.raw_x = self.raw_y = self.raw_z = 0.0
        self.held_frames = 0
        self.has_extend = False
        self.params = 0

    # -- convenience -------------------------------------------------------- #
    @property
    def position(self) -> Tuple[float, float, float]:
        return self.x, self.y, self.z

    @property
    def quaternion(self) -> Tuple[float, float, float, float]:
        return self.qx, self.qy, self.qz, self.qw

    @property
    def velocity(self) -> Tuple[float, float, float]:
        return self.vx, self.vy, self.vz

    @property
    def speed(self) -> float:
        return (self.vx * self.vx + self.vy * self.vy + self.vz * self.vz) ** 0.5

    def copy(self) -> "BodyState":
        clone = BodyState(self.body_id, self.name)
        for slot in self.__slots__:
            setattr(clone, slot, getattr(self, slot))
        return clone

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            "BodyState(id=%d name=%r pos=(%.4f, %.4f, %.4f) status=%s)"
            % (self.body_id, self.name, self.x, self.y, self.z, self.status)
        )


class FrameSnapshot:
    """A complete motion-capture frame.

    ``timestamp`` is a monotonic local clock in seconds since the session
    started: it is uniform, never jumps backwards and is what every internal
    timing decision uses.  ``raw_timestamp`` / ``sdk_timestamp`` keep the value
    reported by the server for reference and for wire formats that want it.
    """

    __slots__ = (
        "frame_no", "timestamp", "timecode", "latency",
        "raw_timestamp", "sdk_timestamp",
        "bodies", "analog", "received_at", "source",
    )

    def __init__(self, frame_no: int = 0, timestamp: float = 0.0) -> None:
        self.frame_no = frame_no
        self.timestamp = timestamp
        self.timecode = ""
        self.latency = 0.0
        self.raw_timestamp = 0
        self.sdk_timestamp = 0.0
        self.bodies: Dict[int, BodyState] = {}
        self.analog: List[float] = []
        self.received_at = 0.0
        self.source = "sdk"

    @property
    def body_count(self) -> int:
        return len(self.bodies)

    def sorted_bodies(self) -> List[BodyState]:
        return [self.bodies[key] for key in sorted(self.bodies)]

    def copy(self) -> "FrameSnapshot":
        clone = FrameSnapshot(self.frame_no, self.timestamp)
        clone.timecode = self.timecode
        clone.latency = self.latency
        clone.raw_timestamp = self.raw_timestamp
        clone.sdk_timestamp = self.sdk_timestamp
        clone.analog = list(self.analog)
        clone.received_at = self.received_at
        clone.source = self.source
        clone.bodies = {key: body.copy() for key, body in self.bodies.items()}
        return clone

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return "FrameSnapshot(no=%d bodies=%d)" % (self.frame_no, len(self.bodies))
