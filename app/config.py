"""Application settings: dataclasses, JSON persistence and named profiles.

Every option the GUI exposes lives here so that a saved profile fully describes
the behaviour of the broadcaster.
"""

from __future__ import annotations

from .i18n import tr

import copy
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .paths import config_path, profiles_dir
from .version import CONFIG_VERSION


# --------------------------------------------------------------------------- #
# tolerant coercion helpers (config files are hand-editable)
# --------------------------------------------------------------------------- #
def as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on", "y", "是")
    return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if result != result:  # NaN
        return default
    return result


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def as_str(value: Any, default: str = "") -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return default
    return str(value)


def _clamp(value: float, low: float, high: float) -> float:
    return low if value < low else (high if value > high else value)


def parse_id_list(text: Any) -> List[int]:
    """Parse ``"1, 3, 5-8"`` into ``[1, 3, 5, 6, 7, 8]``."""
    if isinstance(text, (list, tuple)):
        out: List[int] = []
        for item in text:
            out.extend(parse_id_list(item))
        return out
    result: List[int] = []
    for chunk in as_str(text).replace(";", ",").replace("，", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk[1:]:
            head, _, tail = chunk.partition("-")
            try:
                start, stop = int(head), int(tail)
            except ValueError:
                continue
            step = 1 if stop >= start else -1
            result.extend(range(start, stop + step, step))
        else:
            try:
                result.append(int(chunk))
            except ValueError:
                continue
    return result


# --------------------------------------------------------------------------- #
# sections
# --------------------------------------------------------------------------- #
@dataclass
class NetworkConfig:
    """Where the mocap data comes from."""

    server_ip: str = "192.168.1.123"
    """IPv4 address of the machine running the Nokov XING server software."""

    receive_mode: str = "callback"
    """``callback`` (SDK pushes frames) or ``poll`` (we pull frames)."""

    timestamp_unit: str = "auto"
    """``auto`` | ``ns`` | ``us`` | ``ms`` | ``s`` - unit of ``iTimeStamp``."""

    read_extend_data: bool = True
    """Read SDK velocity / acceleration / Euler angles when the server offers them."""

    connect_timeout_s: float = 3.0
    """How long to wait for the first frame before declaring "no data"."""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "server_ip": self.server_ip,
            "receive_mode": self.receive_mode,
            "timestamp_unit": self.timestamp_unit,
            "read_extend_data": self.read_extend_data,
            "connect_timeout_s": self.connect_timeout_s,
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "NetworkConfig":
        raw = raw or {}
        return cls(
            server_ip=as_str(raw.get("server_ip"), cls.server_ip),
            receive_mode=as_str(raw.get("receive_mode"), cls.receive_mode),
            timestamp_unit=as_str(raw.get("timestamp_unit"), "auto"),
            read_extend_data=as_bool(raw.get("read_extend_data"), True),
            connect_timeout_s=as_float(raw.get("connect_timeout_s"), cls.connect_timeout_s),
        )


@dataclass
class BroadcastTarget:
    """One UDP destination."""

    ip: str = "192.168.1.123"
    port: int = 22222
    enabled: bool = True
    label: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"ip": self.ip, "port": self.port, "enabled": self.enabled, "label": self.label}

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "BroadcastTarget":
        raw = raw or {}
        return cls(
            ip=as_str(raw.get("ip"), "127.0.0.1"),
            port=as_int(raw.get("port"), 22222),
            enabled=as_bool(raw.get("enabled"), True),
            label=as_str(raw.get("label"), ""),
        )


@dataclass
class BroadcastConfig:
    targets: List[BroadcastTarget] = field(
        default_factory=lambda: [BroadcastTarget(ip="192.168.1.123", port=22222)]
    )
    format_id: str = "stq14"
    format_params: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    """``{format_id: {parameter: value}}`` - each format keeps its own settings."""
    max_rate_hz: float = 0.0
    """0 = forward every received frame.  Otherwise throttle to this rate."""

    send_when_empty: bool = False
    """Send a packet even when no rigid body passed the filter."""

    source_ip: str = ""
    """Optional bind address for the sending socket (empty = OS default)."""

    def params_for(self, format_id: str) -> Dict[str, Any]:
        params = self.format_params.get(format_id)
        return dict(params) if isinstance(params, dict) else {}

    def set_params_for(self, format_id: str, params: Dict[str, Any]) -> None:
        self.format_params[format_id] = dict(params)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "targets": [t.to_dict() for t in self.targets],
            "format_id": self.format_id,
            "format_params": copy.deepcopy(self.format_params),
            "max_rate_hz": self.max_rate_hz,
            "send_when_empty": self.send_when_empty,
            "source_ip": self.source_ip,
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "BroadcastConfig":
        raw = raw or {}
        targets_raw = raw.get("targets")
        if isinstance(targets_raw, list) and targets_raw:
            targets = [BroadcastTarget.from_dict(t) for t in targets_raw]
        else:
            targets = [BroadcastTarget(ip="192.168.1.123", port=22222)]
        params = raw.get("format_params")
        format_params: Dict[str, Dict[str, Any]] = {}
        format_id = as_str(raw.get("format_id"), "stq14")
        if isinstance(params, dict):
            if params and all(isinstance(value, dict) for value in params.values()):
                format_params = {str(key): dict(value) for key, value in params.items()}
            elif params:
                # migrate the pre-2.0 flat layout
                format_params = {format_id: dict(params)}
        return cls(
            targets=targets,
            format_id=format_id,
            format_params=format_params,
            max_rate_hz=as_float(raw.get("max_rate_hz"), 0.0),
            send_when_empty=as_bool(raw.get("send_when_empty"), False),
            source_ip=as_str(raw.get("source_ip"), ""),
        )


@dataclass
class FilterConfig:
    """Robustness / body-selection settings applied before encoding."""

    min_body_id: int = 0
    """Bodies with an ID below this are dropped.

    The original ``NokovSDKClient_STQ.py`` used ``if body_id >= 0`` (its comment
    claimed ``>= 1``), so ``0`` reproduces the legacy behaviour exactly.
    """

    max_body_id: int = 2147483647
    include_ids: str = ""
    """Optional whitelist, e.g. ``"1,2,5"``.  Empty = all."""

    exclude_ids: str = ""

    abnormal_threshold_mm: float = 9000.0
    """Positions beyond +/- this magnitude (mm) are treated as tracking glitches."""

    hold_last_valid: bool = True
    """Replace glitched samples with the last good sample."""

    max_hold_frames: int = 0
    """0 = hold forever.  Otherwise mark the body "lost" after N held frames."""

    keep_lost_bodies: bool = False
    """Keep broadcasting a body that vanished from the frame (last known pose)."""

    require_markers: bool = False
    min_markers: int = 0

    smoothing: str = "none"
    """``none`` | ``sma`` | ``median`` | ``ema`` | ``one_euro``"""

    smoothing_window: int = 5
    smoothing_alpha: float = 0.35
    one_euro_min_cutoff: float = 1.0
    one_euro_beta: float = 0.05
    smooth_orientation: bool = False

    velocity_source: str = "auto"
    """``auto`` (SDK extend data when present) | ``sdk`` | ``difference``."""

    euler_source: str = "auto"
    """``auto`` | ``sdk`` | ``quaternion`` - where roll/pitch/yaw come from."""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "min_body_id": self.min_body_id,
            "max_body_id": self.max_body_id,
            "include_ids": self.include_ids,
            "exclude_ids": self.exclude_ids,
            "abnormal_threshold_mm": self.abnormal_threshold_mm,
            "hold_last_valid": self.hold_last_valid,
            "max_hold_frames": self.max_hold_frames,
            "keep_lost_bodies": self.keep_lost_bodies,
            "require_markers": self.require_markers,
            "min_markers": self.min_markers,
            "smoothing": self.smoothing,
            "smoothing_window": self.smoothing_window,
            "smoothing_alpha": self.smoothing_alpha,
            "one_euro_min_cutoff": self.one_euro_min_cutoff,
            "one_euro_beta": self.one_euro_beta,
            "smooth_orientation": self.smooth_orientation,
            "velocity_source": self.velocity_source,
            "euler_source": self.euler_source,
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "FilterConfig":
        raw = raw or {}
        return cls(
            min_body_id=as_int(raw.get("min_body_id"), 0),
            max_body_id=as_int(raw.get("max_body_id"), 2147483647),
            include_ids=as_str(raw.get("include_ids"), ""),
            exclude_ids=as_str(raw.get("exclude_ids"), ""),
            abnormal_threshold_mm=as_float(raw.get("abnormal_threshold_mm"), 9000.0),
            hold_last_valid=as_bool(raw.get("hold_last_valid"), True),
            max_hold_frames=max(0, as_int(raw.get("max_hold_frames"), 0)),
            keep_lost_bodies=as_bool(raw.get("keep_lost_bodies"), False),
            require_markers=as_bool(raw.get("require_markers"), False),
            min_markers=max(0, as_int(raw.get("min_markers"), 0)),
            smoothing=as_str(raw.get("smoothing"), "none"),
            smoothing_window=max(1, as_int(raw.get("smoothing_window"), 5)),
            smoothing_alpha=_clamp(as_float(raw.get("smoothing_alpha"), 0.35), 0.001, 1.0),
            one_euro_min_cutoff=max(1e-4, as_float(raw.get("one_euro_min_cutoff"), 1.0)),
            one_euro_beta=max(0.0, as_float(raw.get("one_euro_beta"), 0.05)),
            smooth_orientation=as_bool(raw.get("smooth_orientation"), False),
            velocity_source=as_str(raw.get("velocity_source"), "auto"),
            euler_source=as_str(raw.get("euler_source"), "auto"),
        )


@dataclass
class TransformConfig:
    """Coordinate frame handling applied to every incoming rigid body."""

    axis_map: str = "XYZ"
    """Output axis order, e.g. ``ZYX`` means out_x = in_z, out_y = in_y, out_z = in_x."""

    sign_x: int = 1
    sign_y: int = 1
    sign_z: int = 1

    unit_scale: float = 1.0
    """Extra multiplier applied after mm -> m conversion."""

    offset_x: float = 0.0
    offset_y: float = 0.0
    offset_z: float = 0.0
    """Offset in metres added after scaling."""

    yaw_deg: float = 0.0
    """Rotate the whole volume about the world Z axis (also rotates orientation)."""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "axis_map": self.axis_map,
            "sign_x": self.sign_x,
            "sign_y": self.sign_y,
            "sign_z": self.sign_z,
            "unit_scale": self.unit_scale,
            "offset_x": self.offset_x,
            "offset_y": self.offset_y,
            "offset_z": self.offset_z,
            "yaw_deg": self.yaw_deg,
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "TransformConfig":
        raw = raw or {}
        axis_map = as_str(raw.get("axis_map"), "XYZ").upper()
        if sorted(axis_map) != ["X", "Y", "Z"]:
            axis_map = "XYZ"
        return cls(
            axis_map=axis_map,
            sign_x=-1 if as_int(raw.get("sign_x"), 1) < 0 else 1,
            sign_y=-1 if as_int(raw.get("sign_y"), 1) < 0 else 1,
            sign_z=-1 if as_int(raw.get("sign_z"), 1) < 0 else 1,
            unit_scale=as_float(raw.get("unit_scale"), 1.0),
            offset_x=as_float(raw.get("offset_x"), 0.0),
            offset_y=as_float(raw.get("offset_y"), 0.0),
            offset_z=as_float(raw.get("offset_z"), 0.0),
            yaw_deg=as_float(raw.get("yaw_deg"), 0.0),
        )


@dataclass
class UiConfig:
    language: str = "zh"
    """``zh`` or ``en`` - the interface language."""

    autoconnect: bool = False
    autostart_broadcast: bool = False
    trail_length: int = 120
    plot_window_s: float = 5.0
    plot_points: int = 1500
    refresh_hz: int = 60
    axis_length_m: float = 0.15
    show_labels: bool = True
    show_trails: bool = True
    show_markers: bool = False
    max_draw_bodies: int = 64
    table_hz: int = 15
    log_to_file: bool = True
    log_level: str = "INFO"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "language": self.language,
            "autoconnect": self.autoconnect,
            "autostart_broadcast": self.autostart_broadcast,
            "trail_length": self.trail_length,
            "plot_window_s": self.plot_window_s,
            "plot_points": self.plot_points,
            "refresh_hz": self.refresh_hz,
            "axis_length_m": self.axis_length_m,
            "show_labels": self.show_labels,
            "show_trails": self.show_trails,
            "show_markers": self.show_markers,
            "max_draw_bodies": self.max_draw_bodies,
            "table_hz": self.table_hz,
            "log_to_file": self.log_to_file,
            "log_level": self.log_level,
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "UiConfig":
        raw = raw or {}
        return cls(
            language=as_str(raw.get("language"), "zh"),
            autoconnect=as_bool(raw.get("autoconnect"), False),
            autostart_broadcast=as_bool(raw.get("autostart_broadcast"), False),
            trail_length=max(2, as_int(raw.get("trail_length"), 120)),
            plot_window_s=max(0.5, as_float(raw.get("plot_window_s"), 5.0)),
            plot_points=max(120, as_int(raw.get("plot_points"), 1500)),
            refresh_hz=max(5, min(144, as_int(raw.get("refresh_hz"), 60))),
            axis_length_m=max(0.0, as_float(raw.get("axis_length_m"), 0.15)),
            show_labels=as_bool(raw.get("show_labels"), True),
            show_trails=as_bool(raw.get("show_trails"), True),
            show_markers=as_bool(raw.get("show_markers"), False),
            max_draw_bodies=max(1, as_int(raw.get("max_draw_bodies"), 64)),
            table_hz=max(1, min(60, as_int(raw.get("table_hz"), 15))),
            log_to_file=as_bool(raw.get("log_to_file"), True),
            log_level=as_str(raw.get("log_level"), "INFO").upper(),
        )


@dataclass
class AppConfig:
    network: NetworkConfig = field(default_factory=NetworkConfig)
    broadcast: BroadcastConfig = field(default_factory=BroadcastConfig)
    filters: FilterConfig = field(default_factory=FilterConfig)
    transform: TransformConfig = field(default_factory=TransformConfig)
    ui: UiConfig = field(default_factory=UiConfig)
    version: int = CONFIG_VERSION

    # -- serialisation ----------------------------------------------------- #
    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": CONFIG_VERSION,
            "network": self.network.to_dict(),
            "broadcast": self.broadcast.to_dict(),
            "filters": self.filters.to_dict(),
            "transform": self.transform.to_dict(),
            "ui": self.ui.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "AppConfig":
        raw = raw or {}
        return cls(
            network=NetworkConfig.from_dict(raw.get("network")),
            broadcast=BroadcastConfig.from_dict(raw.get("broadcast")),
            filters=FilterConfig.from_dict(raw.get("filters")),
            transform=TransformConfig.from_dict(raw.get("transform")),
            ui=UiConfig.from_dict(raw.get("ui")),
        )

    def clone(self) -> "AppConfig":
        return AppConfig.from_dict(copy.deepcopy(self.to_dict()))

    def apply_from(self, other: "AppConfig") -> None:
        """Copy every section from ``other`` into ``self`` (keeps identity)."""
        fresh = other.clone()
        self.network = fresh.network
        self.broadcast = fresh.broadcast
        self.filters = fresh.filters
        self.transform = fresh.transform
        self.ui = fresh.ui

    # -- disk -------------------------------------------------------------- #
    def save(self, path: Optional[str] = None) -> str:
        path = path or config_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
        return path

    @classmethod
    def load(cls, path: Optional[str] = None) -> "AppConfig":
        path = path or config_path()
        try:
            with open(path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, ValueError):
            return cls()
        if not isinstance(raw, dict):
            return cls()
        return cls.from_dict(raw)


# --------------------------------------------------------------------------- #
# named profiles
# --------------------------------------------------------------------------- #
def profile_path(name: str) -> str:
    safe = "".join(ch for ch in name if ch not in '\\/:*?"<>|').strip()
    if not safe:
        safe = "profile"
    return os.path.join(profiles_dir(), safe + ".json")


def save_profile(name: str, config: AppConfig) -> str:
    return config.save(profile_path(name))


def load_profile(name: str) -> Optional[AppConfig]:
    path = profile_path(name)
    if not os.path.exists(path):
        return None
    return AppConfig.load(path)


def list_profiles() -> List[str]:
    try:
        names = [
            os.path.splitext(entry)[0]
            for entry in os.listdir(profiles_dir())
            if entry.lower().endswith(".json")
        ]
    except OSError:
        return []
    return sorted(names)


def delete_profile(name: str) -> bool:
    path = profile_path(name)
    try:
        os.remove(path)
        return True
    except OSError:
        return False
