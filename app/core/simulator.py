"""Synthetic frame source.

Lets the whole application - filtering, visualisation, encoding and UDP output -
be exercised without a motion capture server.  Useful for commissioning a
receiver, demoing the tool, or checking a custom wire format.
"""

from __future__ import annotations

from ..i18n import tr

import math
import random
import threading
import time
import logging
from typing import List, Optional

from .frames import BodyState, FrameSnapshot
from .hub import FrameHub
from .math3d import quat_from_yaw

log = logging.getLogger("nokov.simulator")


class SimulatedSource(threading.Thread):
    """Publishes fake rigid bodies at a fixed rate."""

    def __init__(self, hub: FrameHub, body_count: int = 4, rate_hz: float = 120.0,
                 noise_mm: float = 1.5, glitch_every: int = 0) -> None:
        super().__init__(name="nokov-simulator", daemon=True)
        self._hub = hub
        self.body_count = max(1, int(body_count))
        self.rate_hz = max(1.0, float(rate_hz))
        self.noise_mm = max(0.0, float(noise_mm))
        self.glitch_every = max(0, int(glitch_every))
        self._stop_event = threading.Event()
        self._random = random.Random(12345)
        self._frame_no = 0
        self._started_at = 0.0
        self._layout_lock = threading.Lock()
        self._radius: List[float] = []
        self._phase: List[float] = []
        self._height: List[float] = []
        self._build_layout()

    def _build_layout(self) -> None:
        """(Re)create the per-body motion parameters for ``body_count`` bodies."""
        self._radius = []
        self._phase = []
        self._height = []
        count = max(1, int(self.body_count))
        for index in range(count):
            self._radius.append(0.35 + 0.28 * (index % 4))
            self._phase.append(index * (2.0 * math.pi / count))
            self._height.append(0.25 + 0.35 * (index % 3))

    def set_body_count(self, count: int) -> None:
        """Change how many simulated bodies are produced (thread safe)."""
        count = max(1, int(count))
        with self._layout_lock:
            if count == self.body_count:
                return
            self.body_count = count
            self._build_layout()

    def set_rate(self, rate_hz: float) -> None:
        self.rate_hz = max(1.0, float(rate_hz))

    # ------------------------------------------------------------------ #
    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        self._started_at = time.perf_counter()
        next_at = self._started_at
        while not self._stop_event.is_set():
            now = time.perf_counter()
            period = 1.0 / max(1.0, self.rate_hz)
            if now < next_at:
                self._stop_event.wait(min(0.02, next_at - now))
                continue
            next_at += period
            if next_at < now - 0.25:  # we fell far behind; resynchronise
                next_at = now + period
            try:
                self._publish(now - self._started_at)
            except Exception:  # keep the source alive no matter what
                log.exception(tr("模拟数据源生成帧失败"))
                self._stop_event.wait(0.05)

    def _publish(self, t: float) -> None:
        self._frame_no += 1
        snapshot = FrameSnapshot(self._frame_no, t)
        snapshot.source = "simulator"
        snapshot.sdk_timestamp = t
        snapshot.raw_timestamp = int(t * 1e6)
        snapshot.latency = 1.2

        with self._layout_lock:
            count = min(self.body_count, len(self._phase),
                        len(self._radius), len(self._height))
            phases = list(self._phase[:count])
            radii = list(self._radius[:count])
            heights = list(self._height[:count])

        for index in range(count):
            body_id = index + 1
            body = BodyState(body_id, "SIM_%02d" % body_id)
            angle = phases[index] + t * (0.7 + 0.15 * index)
            radius = radii[index]
            x = radius * math.cos(angle)
            y = radius * math.sin(angle)
            z = heights[index] + 0.12 * math.sin(t * 1.6 + index)

            noise = self.noise_mm / 1000.0
            body.raw_x = (x + self._random.gauss(0.0, noise)) * 1000.0
            body.raw_y = (y + self._random.gauss(0.0, noise)) * 1000.0
            body.raw_z = (z + self._random.gauss(0.0, noise)) * 1000.0

            if self.glitch_every and self._frame_no % self.glitch_every == 0 and index == 0:
                body.raw_x = 99999.0  # deliberately out of range

            body.x = body.raw_x / 1000.0
            body.y = body.raw_y / 1000.0
            body.z = body.raw_z / 1000.0
            body.qx, body.qy, body.qz, body.qw = quat_from_yaw(angle)
            body.n_markers = 4
            body.mean_error = 0.35
            body.has_extend = False
            snapshot.bodies[body_id] = body

        self._hub.publish_raw(snapshot)
