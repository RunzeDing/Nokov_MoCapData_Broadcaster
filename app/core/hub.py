"""Thread-safe exchange of frames between the SDK reader, engine and GUI.

Design notes
------------
The Nokov SDK calls us back on a native thread that we do not control.  Rather
than emitting Qt signals from that thread, the callback simply *publishes* the
raw frame here and the engine thread picks it up.  The GUI never touches the SDK
thread directly, which keeps shutdown deterministic.

Frames handed out by this hub are treated as immutable: producers create a new
:class:`~app.core.frames.FrameSnapshot` for every frame and never mutate one
after publishing (encoders use :class:`NormalizedQuatView` instead of editing
bodies in place), so readers can use them without copying.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Deque, Dict, List, Optional, Sequence, Tuple

from .frames import FrameSnapshot

#: Values recorded for every body in the rolling time-series history.
SERIES_FIELDS = (
    "x", "y", "z",
    "vx", "vy", "vz",
    "ax", "ay", "az",
    "roll", "pitch", "yaw",
    "speed",
)
SERIES_INDEX = {name: index + 1 for index, name in enumerate(SERIES_FIELDS)}
#: sample layout: (t, x, y, z, vx, vy, vz, ax, ay, az, roll, pitch, yaw, speed)
SERIES_LENGTH = len(SERIES_FIELDS) + 1


class FrameHub:
    """Single-slot latest-frame buffers plus bounded per-body history."""

    def __init__(self, trail_length: int = 120, series_capacity: int = 1500) -> None:
        self._lock = threading.Lock()
        self._raw: Optional[FrameSnapshot] = None
        self._raw_seq = 0
        self._processed: Optional[FrameSnapshot] = None
        self._processed_seq = 0
        self._new_raw = threading.Event()

        self._trail_length = max(2, int(trail_length))
        self._series_capacity = max(16, int(series_capacity))
        self._trails: Dict[int, Deque[Tuple[float, float, float]]] = {}
        self._series: Dict[int, Deque[Tuple[float, ...]]] = {}
        self._names: Dict[int, str] = {}
        self._known_ids: List[int] = []

    # ------------------------------------------------------------------ #
    # producer: SDK reader thread
    # ------------------------------------------------------------------ #
    def publish_raw(self, frame: Optional[FrameSnapshot]) -> None:
        with self._lock:
            self._raw = frame
            self._raw_seq += 1
        self._new_raw.set()

    # ------------------------------------------------------------------ #
    # consumer: engine thread
    # ------------------------------------------------------------------ #
    def take_raw(self, last_seq: int, timeout: float = 0.05):
        """Block briefly for a frame newer than ``last_seq``."""
        self._new_raw.wait(timeout)
        with self._lock:
            if self._raw is None or self._raw_seq == last_seq:
                return last_seq, None
            self._new_raw.clear()
            return self._raw_seq, self._raw

    def publish_processed(self, frame: Optional[FrameSnapshot]) -> None:
        with self._lock:
            self._processed = frame
            self._processed_seq += 1

    def record_history(self, frame: FrameSnapshot) -> None:
        """Append the processed frame to the trail / series ring buffers."""
        if frame is None or not frame.bodies:
            return
        timestamp = frame.timestamp
        with self._lock:
            for body_id, body in frame.bodies.items():
                trail = self._trails.get(body_id)
                if trail is None:
                    trail = deque(maxlen=self._trail_length)
                    self._trails[body_id] = trail
                trail.append((body.x, body.y, body.z))

                series = self._series.get(body_id)
                if series is None:
                    series = deque(maxlen=self._series_capacity)
                    self._series[body_id] = series
                series.append((
                    timestamp,
                    body.x, body.y, body.z,
                    body.vx, body.vy, body.vz,
                    body.ax, body.ay, body.az,
                    body.roll, body.pitch, body.yaw,
                    body.speed,
                ))
                if body.name:
                    self._names[body_id] = body.name
            self._known_ids = sorted(self._series)

    # ------------------------------------------------------------------ #
    # reader: GUI thread
    # ------------------------------------------------------------------ #
    def latest_processed(self):
        with self._lock:
            return self._processed_seq, self._processed

    def latest_raw(self):
        with self._lock:
            return self._raw_seq, self._raw

    def trail(self, body_id: int) -> List[Tuple[float, float, float]]:
        with self._lock:
            trail = self._trails.get(body_id)
            return list(trail) if trail else []

    def trails_snapshot(self, body_ids: Optional[Sequence[int]] = None,
                        max_bodies: int = 0) -> Dict[int, List[Tuple[float, float, float]]]:
        with self._lock:
            keys = list(body_ids) if body_ids is not None else list(self._trails)
            if max_bodies > 0:
                keys = keys[:max_bodies]
            return {key: list(self._trails[key]) for key in keys if key in self._trails}

    def series_snapshot(self, body_id: int) -> List[Tuple[float, ...]]:
        with self._lock:
            series = self._series.get(body_id)
            return list(series) if series else []

    def known_ids(self) -> List[int]:
        with self._lock:
            return list(self._known_ids)

    def body_name(self, body_id: int) -> str:
        with self._lock:
            return self._names.get(body_id, "")

    def set_body_names(self, mapping: Dict[int, str]) -> None:
        with self._lock:
            for body_id, name in (mapping or {}).items():
                if name:
                    self._names[int(body_id)] = name

    def set_limits(self, trail_length: int, series_capacity: int) -> None:
        with self._lock:
            trail_length = max(2, int(trail_length))
            series_capacity = max(16, int(series_capacity))
            if trail_length != self._trail_length:
                self._trail_length = trail_length
                for body_id, trail in self._trails.items():
                    self._trails[body_id] = deque(trail, maxlen=trail_length)
            if series_capacity != self._series_capacity:
                self._series_capacity = series_capacity
                for body_id, series in self._series.items():
                    self._series[body_id] = deque(series, maxlen=series_capacity)

    # ------------------------------------------------------------------ #
    def reset(self) -> None:
        with self._lock:
            self._raw = None
            self._processed = None
            self._raw_seq = 0
            self._processed_seq = 0
            self._trails.clear()
            self._series.clear()
            self._known_ids = []
        self._new_raw.clear()

    def wake(self) -> None:
        self._new_raw.set()
