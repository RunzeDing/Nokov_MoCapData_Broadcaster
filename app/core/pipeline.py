"""The per-frame processing pipeline: selection -> glitch handling -> transform -> smoothing.

Legacy compatibility
--------------------
With the default configuration (``min_body_id = -1``, ``abnormal_threshold_mm =
9000``, ``hold_last_valid = True``, identity transform, no smoothing) the output
of this pipeline is bit-for-bit what ``NokovSDKClient_STQ.py`` produced.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from .filters import BodySelector, BodyTrack
from .frames import BodyState, FrameSnapshot
from .math3d import quat_normalize, quat_to_euler_zyx_deg
from .transform import CoordinateTransform


class PipelineStats:
    """Rolling counters exposed to the GUI."""

    __slots__ = (
        "frames_in", "frames_out", "bodies_out",
        "glitches", "held", "lost", "dropped_by_filter",
    )

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.frames_in = 0
        self.frames_out = 0
        self.bodies_out = 0
        self.glitches = 0
        self.held = 0
        self.lost = 0
        self.dropped_by_filter = 0


class Pipeline:
    """Stateful frame processor.

    Not thread-safe by itself: it is owned exclusively by the engine thread.
    Configuration objects are read through a callable so the GUI can push new
    settings at any time.
    """

    def __init__(self, config) -> None:
        self._config = config
        self.transform = CoordinateTransform(config.transform)
        self.selector = BodySelector(config.filters)
        self.stats = PipelineStats()
        self._tracks: Dict[int, BodyTrack] = {}
        self._known: Dict[int, str] = {}
        self._last_glitch: Dict[int, int] = {}

        self._filter_signature = None
        self._transform_signature = None
        self._prev_ts = None
        self._apply_config(config, force=True)

    # ------------------------------------------------------------------ #
    # configuration
    # ------------------------------------------------------------------ #
    @staticmethod
    def _filter_signature_of(config) -> Tuple:
        filters = config.filters
        return (
            filters.min_body_id, filters.max_body_id,
            filters.include_ids, filters.exclude_ids,
            filters.require_markers, filters.min_markers,
            filters.abnormal_threshold_mm, filters.hold_last_valid,
            filters.max_hold_frames, filters.keep_lost_bodies,
            filters.smoothing, filters.smoothing_window, filters.smoothing_alpha,
            filters.one_euro_min_cutoff, filters.one_euro_beta,
            filters.smooth_orientation, filters.velocity_source,
            filters.euler_source,
        )

    @staticmethod
    def _transform_signature_of(config) -> Tuple:
        t = config.transform
        return (
            t.axis_map, t.sign_x, t.sign_y, t.sign_z, t.unit_scale,
            t.offset_x, t.offset_y, t.offset_z, t.yaw_deg,
        )

    def _apply_config(self, config, force: bool = False) -> None:
        self._config = config
        filter_sig = self._filter_signature_of(config)
        if force or filter_sig != self._filter_signature:
            self._filter_signature = filter_sig
            self.selector.update(config.filters)
            for track in self._tracks.values():
                track.configure_smoothing(config.filters)
        transform_sig = self._transform_signature_of(config)
        if force or transform_sig != self._transform_signature:
            self._transform_signature = transform_sig
            self.transform.update(config.transform)

    def reset(self) -> None:
        self._tracks.clear()
        self._last_glitch.clear()
        self.stats.reset()

    # ------------------------------------------------------------------ #
    # introspection for the GUI
    # ------------------------------------------------------------------ #
    @property
    def known_names(self) -> Dict[int, str]:
        return dict(self._known)

    def register_known_bodies(self, mapping: Dict[int, str]) -> None:
        """Seed the ID -> name table from the SDK data descriptions."""
        for body_id, name in (mapping or {}).items():
            self._known.setdefault(int(body_id), name or "")
            self._tracks.setdefault(int(body_id), BodyTrack(int(body_id), name or ""))
            self._tracks[int(body_id)].configure_smoothing(self._config.filters)

    def track_status(self, body_id: int) -> Optional[str]:
        track = self._tracks.get(body_id)
        if track is None:
            return None
        if track.last_seen_frame < 0:
            return "new"
        return "ok" if track.held_frames == 0 else "held"

    # ------------------------------------------------------------------ #
    # main entry point
    # ------------------------------------------------------------------ #
    def process(self, raw: Optional[FrameSnapshot]) -> Tuple[FrameSnapshot, List[int]]:
        """Filter one raw frame.

        Returns the processed frame plus the list of body IDs that were part of
        the previous frame but are missing from this one (candidates for "lost").
        """
        if raw is None:
            return FrameSnapshot(), []

        self._apply_config(self._config)
        filters = self._config.filters

        out = FrameSnapshot(raw.frame_no, raw.timestamp)
        out.timecode = raw.timecode
        out.latency = raw.latency
        out.analog = list(raw.analog)
        out.received_at = raw.received_at
        out.source = raw.source

        threshold = float(filters.abnormal_threshold_mm)
        hold_enabled = bool(filters.hold_last_valid)
        max_hold = int(filters.max_hold_frames)
        keep_lost = bool(filters.keep_lost_bodies)
        dt = self._frame_dt(raw)

        seen = set()
        lost_ids: List[int] = []

        for body_id, body in raw.bodies.items():
            track = self._tracks.get(body_id)
            if track is None:
                track = BodyTrack(body_id, body.name)
                track.configure_smoothing(filters)
                self._tracks[body_id] = track
            if body.name and self._known.get(body_id) != body.name:
                self._known[body_id] = body.name
                track.name = body.name

            if not self.selector.accepts(body):
                self.stats.dropped_by_filter += 1
                continue

            seen.add(body_id)
            track.total_frames += 1
            track.last_seen_frame = raw.frame_no
            track.last_seen_time = raw.timestamp

            # 1. glitch detection on the raw millimetre values
            glitch = (
                threshold > 0.0
                and (
                    abs(body.raw_x) > threshold
                    or abs(body.raw_y) > threshold
                    or abs(body.raw_z) > threshold
                )
            )
            if glitch:
                track.glitch_count += 1
                self.stats.glitches += 1
                self._last_glitch[body_id] = raw.frame_no

            # 2. hold-last-valid substitution
            if glitch and hold_enabled and track.has_valid:
                track.restore(body)
                track.held_frames += 1
                self.stats.held += 1
                if max_hold > 0 and track.held_frames > max_hold:
                    self.stats.lost += 1
                    lost_ids.append(body_id)
                    continue
                body.status = "held"
            else:
                if glitch:
                    body.status = "glitch" if not track.has_valid else "ok"
                else:
                    body.status = "new" if track.total_frames <= 1 else "ok"
                track.held_frames = 0

            # 3. velocity / euler bookkeeping (uses pre-transform metres)
            self._update_kinematics(body, track, raw, filters, dt)

            # 4. coordinate transform
            self.transform.apply_to_body(body)

            # 5. smoothing on the final coordinates
            self._smooth(body, track, dt)

            # 6. remember as the last known-good sample
            track.remember(body)
            out.bodies[body_id] = body

        # 7. bodies that disappeared from the frame
        for body_id, track in self._tracks.items():
            if body_id in seen:
                continue
            if track.last_seen_frame < 0:
                continue
            if body_id not in self._known and not keep_lost:
                continue
            if track.last_seen_frame == raw.frame_no:
                continue
            if not self.selector.accepts_id(body_id):
                continue
            lost_ids.append(body_id)
            if keep_lost and track.has_valid:
                ghost = BodyState(body_id, track.name)
                track.restore(ghost)
                ghost.n_markers = 0
                ghost.status = "held_lost"
                ghost.held_frames = track.held_frames
                self.transform.apply_to_body(ghost)
                out.bodies[body_id] = ghost
                self.stats.lost += 1

        self.stats.frames_in += 1
        self.stats.frames_out += 1
        self.stats.bodies_out = len(out.bodies)
        return out, lost_ids

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #
    def _frame_dt(self, raw: FrameSnapshot) -> float:
        last = self._prev_ts
        self._prev_ts = raw.timestamp
        if last is None:
            return 1.0 / 120.0
        dt = raw.timestamp - last
        if dt <= 1e-6 or dt > 1.0:
            return 1.0 / 120.0
        return dt

    def _update_kinematics(self, body: BodyState, track: BodyTrack, raw, filters, dt: float) -> None:
        source = getattr(filters, "velocity_source", "auto")
        use_sdk = body.has_extend and source in ("auto", "sdk")
        if source == "difference":
            use_sdk = False
        elif source == "sdk":
            use_sdk = body.has_extend

        # SDK extend data already carries m/s after the mm -> m conversion.
        if not use_sdk:
            if track.has_prev and dt > 1e-6:
                inv = 1.0 / dt
                body.vx = (body.x - track.prev_x) * inv
                body.vy = (body.y - track.prev_y) * inv
                body.vz = (body.z - track.prev_z) * inv
            else:
                body.vx = body.vy = body.vz = 0.0

        track.prev_x, track.prev_y, track.prev_z = body.x, body.y, body.z
        track.prev_time = raw.timestamp
        track.has_prev = True

        # Acceleration from the velocity difference.
        if track.total_frames > 1 and dt > 1e-6:
            inv = 1.0 / dt
            body.ax = (body.vx - track.prev_vx) * inv
            body.ay = (body.vy - track.prev_vy) * inv
            body.az = (body.vz - track.prev_vz) * inv
        else:
            body.ax = body.ay = body.az = 0.0
        track.prev_vx, track.prev_vy, track.prev_vz = body.vx, body.vy, body.vz

        euler_source = getattr(filters, "euler_source", "auto")
        if euler_source == "sdk" and not body.has_extend:
            body.roll, body.pitch, body.yaw = quat_to_euler_zyx_deg(
                body.qx, body.qy, body.qz, body.qw
            )
        elif euler_source == "quaternion":
            body.roll, body.pitch, body.yaw = quat_to_euler_zyx_deg(
                body.qx, body.qy, body.qz, body.qw
            )
        elif not body.has_extend:
            body.roll, body.pitch, body.yaw = quat_to_euler_zyx_deg(
                body.qx, body.qy, body.qz, body.qw
            )

    def _smooth(self, body: BodyState, track: BodyTrack, dt: float) -> None:
        smoother = track.smoother
        if smoother is not None:
            body.x, body.y, body.z = smoother.update((body.x, body.y, body.z), dt)
        if track.quat_smoother is not None:
            body.qx, body.qy, body.qz, body.qw = track.quat_smoother.update(body.quaternion)
        elif smoother is not None:
            # keep the quaternion normalised even when orientation smoothing is off
            body.qx, body.qy, body.qz, body.qw = quat_normalize(
                body.qx, body.qy, body.qz, body.qw
            )

    # -- helpers used by the GUI --------------------------------------------- #
    def glitch_recent(self, body_id: int, frame_no: int, window: int = 120) -> bool:
        last = self._last_glitch.get(body_id)
        return last is not None and (frame_no - last) <= window

    def glitch_count(self, body_id: int) -> int:
        track = self._tracks.get(body_id)
        return track.glitch_count if track is not None else 0

    def held_frames(self, body_id: int) -> int:
        track = self._tracks.get(body_id)
        return track.held_frames if track is not None else 0
