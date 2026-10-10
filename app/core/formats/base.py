"""Pluggable outbound packet formats.

Each format is an :class:`Encoder` registered in :data:`REGISTRY` and identified
by a stable string id (``stq14``, ``stq20``, ``custom``).  An encoder turns a
processed :class:`~app.core.frames.FrameSnapshot` into the exact bytes that are
put into one UDP datagram.

The registry also exposes :class:`ParamSpec` metadata so the GUI can build the
settings form for a format automatically.
"""

from __future__ import annotations

from ...i18n import get_language, tr

import math
import struct
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..frames import BodyState, FrameSnapshot
from ..math3d import quat_normalize

# --------------------------------------------------------------------------- #
# scalar types
# --------------------------------------------------------------------------- #
#: dtype -> (struct code, size in bytes, minimum, maximum).  ``None`` bounds mean
#: "floating point, no saturation".
DTYPES: Dict[str, Tuple[str, int, Optional[float], Optional[float]]] = {
    "int8": ("b", 1, -128.0, 127.0),
    "uint8": ("B", 1, 0.0, 255.0),
    "int16": ("h", 2, -32768.0, 32767.0),
    "uint16": ("H", 2, 0.0, 65535.0),
    "int32": ("i", 4, -2147483648.0, 2147483647.0),
    "uint32": ("I", 4, 0.0, 4294967295.0),
    "float32": ("f", 4, None, None),
    "float64": ("d", 8, None, None),
}

DTYPE_LABELS = {
    "int8": "int8 (1B)",
    "uint8": "uint8 (1B)",
    "int16": "int16 (2B)",
    "uint16": "uint16 (2B)",
    "int32": "int32 (4B)",
    "uint32": "uint32 (4B)",
    "float32": "float32 (4B)",
    "float64": "float64 (8B)",
}

ENDIANNESS = {"little": "<", "big": ">"}

ROUNDING_MODES = ("trunc", "round", "floor", "ceil")


# --------------------------------------------------------------------------- #
# available quantities
# --------------------------------------------------------------------------- #
class Quantity:
    __slots__ = ("key", "label", "unit", "packet_level", "getter")

    def __init__(self, key: str, label: str, unit: str, getter: Callable, packet_level: bool = False):
        self.key = key
        self.label = label
        self.unit = unit
        self.packet_level = packet_level
        self.getter = getter  # type: ignore[assignment]

    def __repr__(self) -> str:  # pragma: no cover
        return "Quantity(%s)" % self.key


def _status_code(body: BodyState) -> float:
    return {
        "ok": 0.0, "new": 0.0, "held": 1.0, "held_lost": 2.0,
        "lost": 3.0, "glitch": 4.0,
    }.get(body.status, 0.0)


def quantities() -> List[Quantity]:
    """Body-level quantities, built on demand so labels follow the language."""
    return [
        Quantity("x", tr("位置 X"), "m", lambda b, f: b.x),
        Quantity("y", tr("位置 Y"), "m", lambda b, f: b.y),
        Quantity("z", tr("位置 Z"), "m", lambda b, f: b.z),
        Quantity("qx", tr("四元数 qx"), "-", lambda b, f: b.qx),
        Quantity("qy", tr("四元数 qy"), "-", lambda b, f: b.qy),
        Quantity("qz", tr("四元数 qz"), "-", lambda b, f: b.qz),
        Quantity("qw", tr("四元数 qw"), "-", lambda b, f: b.qw),
        Quantity("vx", tr("速度 vx"), "m/s", lambda b, f: b.vx),
        Quantity("vy", tr("速度 vy"), "m/s", lambda b, f: b.vy),
        Quantity("vz", tr("速度 vz"), "m/s", lambda b, f: b.vz),
        Quantity("ax", tr("加速度 ax"), "m/s²", lambda b, f: b.ax),
        Quantity("ay", tr("加速度 ay"), "m/s²", lambda b, f: b.ay),
        Quantity("az", tr("加速度 az"), "m/s²", lambda b, f: b.az),
        Quantity("speed", tr("速度大小"), "m/s", lambda b, f: b.speed),
        Quantity("roll", tr("横滚 roll"), "°", lambda b, f: b.roll),
        Quantity("pitch", tr("俯仰 pitch"), "°", lambda b, f: b.pitch),
        Quantity("yaw", tr("偏航 yaw"), "°", lambda b, f: b.yaw),
        Quantity("id", tr("刚体 ID"), "-", lambda b, f: float(b.body_id)),
        Quantity("n_markers", tr("标记点数"), "-", lambda b, f: float(b.n_markers)),
        Quantity("mean_error", tr("标记点平均误差"), "mm", lambda b, f: b.mean_error),
        Quantity("held_frames", tr("保持帧数"), "-", lambda b, f: float(b.held_frames)),
        Quantity("status_code", tr("状态码"), "-", lambda b, f: _status_code(b)),
    ]


def packet_quantities() -> List[Quantity]:
    """Frame-level quantities, built on demand so labels follow the language."""
    return [
        Quantity("frame", tr("帧号"), "-", lambda b, f: float(f.frame_no), True),
        Quantity("timestamp", tr("相对时间"), "s", lambda b, f: float(f.timestamp), True),
        Quantity("sdk_timestamp", tr("服务器时间戳"), "s",
                 lambda b, f: float(f.sdk_timestamp), True),
        Quantity("raw_timestamp", tr("服务器原始时间戳"), "-",
                 lambda b, f: float(f.raw_timestamp), True),
        Quantity("body_count", tr("刚体数量"), "-", lambda b, f: float(len(f.bodies)), True),
        Quantity("latency", tr("延迟"), "ms", lambda b, f: float(f.latency), True),
    ]


# The maps are rebuilt whenever the language changes; they are consulted on hot
# paths (every encoded frame) so caching by language keeps that cheap.
_quantity_cache = (None, {})
_packet_quantity_cache = (None, {})


def quantity_map() -> Dict[str, Quantity]:
    global _quantity_cache
    language = get_language()
    if _quantity_cache[0] != language:
        _quantity_cache = (language, {q.key: q for q in quantities()})
    return _quantity_cache[1]


def packet_quantity_map() -> Dict[str, Quantity]:
    global _packet_quantity_cache
    language = get_language()
    if _packet_quantity_cache[0] != language:
        _packet_quantity_cache = (language, {q.key: q for q in packet_quantities()})
    return _packet_quantity_cache[1]


# --------------------------------------------------------------------------- #
# parameters
# --------------------------------------------------------------------------- #
class ParamSpec:
    """Describes one adjustable option so the GUI can build a widget for it."""

    __slots__ = (
        "key", "label", "kind", "default", "minimum", "maximum",
        "decimals", "step", "choices", "help", "suffix", "group",
    )

    def __init__(
        self,
        key: str,
        label: str,
        kind: str = "float",
        default: Any = None,
        minimum: Optional[float] = None,
        maximum: Optional[float] = None,
        decimals: int = 3,
        step: Optional[float] = None,
        choices: Optional[List[Tuple[str, str]]] = None,
        help: str = "",
        suffix: str = "",
        group: str = "",
    ) -> None:
        self.key = key
        self.label = label
        self.kind = kind  # bool|int|float|str|choice|hex|fieldlist|readonly
        self.default = default
        self.minimum = minimum
        self.maximum = maximum
        self.decimals = decimals
        self.step = step
        self.choices = choices or []
        self.help = help
        self.suffix = suffix
        self.group = group


class FieldSpec:
    """One value inside a body record of the custom binary format."""

    __slots__ = ("quantity", "dtype", "scale", "offset", "clamp")

    def __init__(
        self,
        quantity: str = "x",
        dtype: str = "int16",
        scale: float = 1.0,
        offset: float = 0.0,
        clamp: bool = True,
    ) -> None:
        self.quantity = quantity
        self.dtype = dtype if dtype in DTYPES else "int16"
        self.scale = float(scale)
        self.offset = float(offset)
        self.clamp = bool(clamp)

    @property
    def size(self) -> int:
        return DTYPES[self.dtype][1]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quantity": self.quantity,
            "dtype": self.dtype,
            "scale": self.scale,
            "offset": self.offset,
            "clamp": self.clamp,
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "FieldSpec":
        raw = raw or {}
        try:
            scale = float(raw.get("scale", 1.0))
        except (TypeError, ValueError):
            scale = 1.0
        try:
            offset = float(raw.get("offset", 0.0))
        except (TypeError, ValueError):
            offset = 0.0
        quantity = raw.get("quantity", "x")
        if quantity not in quantity_map():
            quantity = "x"
        return cls(
            quantity=quantity,
            dtype=raw.get("dtype", "int16"),
            scale=scale,
            offset=offset,
            clamp=bool(raw.get("clamp", True)),
        )


# --------------------------------------------------------------------------- #
# value conversion
# --------------------------------------------------------------------------- #
def _apply_rounding(value: float, mode: str) -> int:
    if mode == "round":
        # half away from zero, unlike python's banker's rounding
        return int(math.floor(value + 0.5)) if value >= 0 else int(math.ceil(value - 0.5))
    if mode == "floor":
        return int(math.floor(value))
    if mode == "ceil":
        return int(math.ceil(value))
    return int(value)  # truncate toward zero - the legacy behaviour


def convert_value(value: float, dtype: str, scale: float = 1.0, offset: float = 0.0,
                  clamp: bool = True, rounding: str = "trunc"):
    """Scale, offset, round and saturate one quantity for the wire."""
    code, _size, low, high = DTYPES[dtype]
    if value is None:
        value = 0.0
    try:
        scaled = float(value) * scale + offset
    except (TypeError, ValueError):
        scaled = 0.0
    if not math.isfinite(scaled):
        scaled = 0.0

    if low is None:  # floating point
        return float(scaled)

    as_int = _apply_rounding(scaled, rounding)
    if clamp:
        if as_int < low:
            as_int = int(low)
        elif as_int > high:
            as_int = int(high)
    else:
        # wrap into range so the packet stays parseable
        span = int(high - low) + 1
        as_int = int(low) + ((as_int - int(low)) % span)
    return as_int


def pack_value(value, dtype: str, prefix: str) -> bytes:
    code = DTYPES[dtype][0]
    return struct.pack(prefix + code, value)


# --------------------------------------------------------------------------- #
# encoder base
# --------------------------------------------------------------------------- #
class NormalizedQuatView:
    """Read-only proxy exposing a body whose quaternion is optionally normalised.

    Encoders use this instead of mutating the shared :class:`BodyState` so the
    GUI can keep reading the same frame from another thread.
    """

    __slots__ = ("_body", "qx", "qy", "qz", "qw")

    def __init__(self, body: BodyState, normalize: bool = True) -> None:
        self._body = body
        if normalize:
            self.qx, self.qy, self.qz, self.qw = quat_normalize(
                body.qx, body.qy, body.qz, body.qw
            )
        else:
            self.qx, self.qy, self.qz, self.qw = body.qx, body.qy, body.qz, body.qw

    def __getattr__(self, name):
        return getattr(self._body, name)


class EncodeContext:
    """Extra information an encoder may need about the current run."""

    __slots__ = ("fps", "packet_index", "now", "source_ip")

    def __init__(self, fps: float = 0.0, packet_index: int = 0, now: float = 0.0,
                 source_ip: str = "") -> None:
        self.fps = fps
        self.packet_index = packet_index
        self.now = now
        self.source_ip = source_ip


class Encoder:
    """Base class for every output format."""

    id = "base"
    name = "Base"
    description = ""
    legacy = False

    def default_params(self) -> Dict[str, Any]:
        return {}

    def param_specs(self) -> List[ParamSpec]:
        return []

    def normalize_params(self, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Merge user values over the defaults, dropping unknown keys."""
        merged = dict(self.default_params())
        for spec in self.param_specs():
            if params and spec.key in params:
                merged[spec.key] = params[spec.key]
        return merged

    def encode(self, frame: FrameSnapshot, params: Dict[str, Any], ctx: EncodeContext) -> bytes:
        raise NotImplementedError

    def packet_size(self, params: Dict[str, Any], body_count: int) -> int:
        """Predicted datagram size for the given body count."""
        return 0

    def layout_lines(self, params: Dict[str, Any]) -> List[str]:
        """Human readable byte layout for the preview panel."""
        return []


# --------------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------------- #
REGISTRY: Dict[str, Encoder] = {}
_ORDER: List[str] = []


def register(encoder: Encoder) -> Encoder:
    if encoder.id not in REGISTRY:
        _ORDER.append(encoder.id)
    REGISTRY[encoder.id] = encoder
    return encoder


def get_format(format_id: str) -> Encoder:
    if format_id in REGISTRY:
        return REGISTRY[format_id]
    if _ORDER:
        return REGISTRY[_ORDER[0]]
    raise KeyError("no output formats registered")


def list_formats() -> List[Encoder]:
    return [REGISTRY[key] for key in _ORDER]


def hex_dump(data: bytes, limit: int = 64) -> str:
    """Compact hex preview used by the GUI."""
    if not data:
        return tr("(空)")
    shown = data[:limit]
    text = " ".join("%02X" % byte for byte in shown)
    if len(data) > limit:
        text += " ..."
    return text


def parse_hex_bytes(text: Any) -> bytes:
    """Parse ``"AA BB"`` / ``"AABB"`` / ``"0xAA,0xBB"`` into bytes.

    Invalid input yields an empty result rather than raising, so a half-typed
    field in the GUI never breaks the send loop.
    """
    if isinstance(text, (bytes, bytearray)):
        return bytes(text)
    if not isinstance(text, str):
        return b""
    cleaned = (
        text.replace("0x", " ").replace("0X", " ")
        .replace(",", " ").replace(";", " ").replace(":", " ")
        .replace("-", " ").replace("\n", " ").replace("\t", " ")
    )
    tokens = [token for token in cleaned.split(" ") if token]
    if len(tokens) == 1:
        token = tokens[0]
        if len(token) % 2:
            return b""
        try:
            return bytes.fromhex(token)
        except ValueError:
            return b""
    out = bytearray()
    for token in tokens:
        try:
            value = int(token, 16)
        except ValueError:
            return b""
        if not 0 <= value <= 255:
            return b""
        out.append(value)
    return bytes(out)


def hex_byte_count(text: Any) -> int:
    return len(parse_hex_bytes(text))


def _sorted_bodies(frame: FrameSnapshot) -> List[BodyState]:
    return [frame.bodies[key] for key in sorted(frame.bodies)]
