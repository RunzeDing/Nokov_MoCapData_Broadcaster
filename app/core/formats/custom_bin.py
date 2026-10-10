"""Fully configurable binary format.

The packet is built as::

    [header] [frame?] [body count?] [timestamp?] [body 0] [body 1] ... [footer]

and every body record is a user-defined ordered list of fields, each with its
own source quantity, scalar type, scale factor, offset and clamping rule.  Body
records are emitted in ascending rigid-body ID order.

The defaults describe the same 14-byte record as the standard STQ format, so
"custom" is a safe starting point: switch a field to ``float32``, add markers,
reorder, or append velocity.
"""

from __future__ import annotations

from ...i18n import tr

import struct
from typing import Any, Dict, List

from ..frames import FrameSnapshot
from .base import (
    DTYPES,
    DTYPE_LABELS,
    ENDIANNESS,
    Encoder,
    EncodeContext,
    FieldSpec,
    NormalizedQuatView,
    ParamSpec,
    quantities,
    quantity_map,
    ROUNDING_MODES,
    _sorted_bodies,
    convert_value,
    parse_hex_bytes,
    register,
)

DEFAULT_FIELDS: List[Dict[str, Any]] = [
    {"quantity": "x", "dtype": "int16", "scale": 2000.0, "offset": 0.0, "clamp": True},
    {"quantity": "y", "dtype": "int16", "scale": 2000.0, "offset": 0.0, "clamp": True},
    {"quantity": "z", "dtype": "int16", "scale": 2000.0, "offset": 0.0, "clamp": True},
    {"quantity": "qx", "dtype": "int16", "scale": 1000.0, "offset": 0.0, "clamp": True},
    {"quantity": "qy", "dtype": "int16", "scale": 1000.0, "offset": 0.0, "clamp": True},
    {"quantity": "qz", "dtype": "int16", "scale": 1000.0, "offset": 0.0, "clamp": True},
    {"quantity": "qw", "dtype": "int16", "scale": 1000.0, "offset": 0.0, "clamp": True},
]

#: choices used by the GUI field editor
def body_quantity_choices():
    """Localised (key, label) pairs for the field editor."""
    return [(q.key, "%s (%s)" % (q.label, q.unit)) for q in quantities()]


def dtype_choices():
    return [(key, DTYPE_LABELS[key]) for key in DTYPES]


def as_field_specs(params: Dict[str, Any]) -> List[FieldSpec]:
    """Normalise the ``fields`` parameter into :class:`FieldSpec` objects."""
    raw = params.get("fields")
    if not isinstance(raw, list):
        raw = DEFAULT_FIELDS
    specs: List[FieldSpec] = []
    for item in raw:
        if isinstance(item, FieldSpec):
            specs.append(item)
        elif isinstance(item, dict):
            specs.append(FieldSpec.from_dict(item))
    return specs


def is_float_dtype(dtype: str) -> bool:
    return DTYPES.get(dtype, DTYPES["int16"])[2] is None


class CustomBinaryEncoder(Encoder):
    id = "custom"

    @property
    def name(self) -> str:
        return tr("自定义二进制格式")

    @property
    def description(self) -> str:
        return tr(
            "自由组合字段、类型、缩放、偏移、字节序与包头包尾。"
            "默认值等价于标准 STQ 14 字节格式，可在此基础上任意扩展。"
        )

    def default_params(self) -> Dict[str, Any]:
        return {
            "endianness": "little",
            "rounding": "trunc",
            "header": "",
            "footer": "",
            "include_frame": False,
            "frame_dtype": "uint32",
            "include_body_count": False,
            "count_dtype": "uint16",
            "include_timestamp": False,
            "timestamp_dtype": "float32",
            "timestamp_unit": "s",
            "normalize_quaternion": True,
            "fields": [dict(item) for item in DEFAULT_FIELDS],
        }

    def param_specs(self) -> List[ParamSpec]:
        int_dtypes = [
            ("uint8", DTYPE_LABELS["uint8"]), ("uint16", DTYPE_LABELS["uint16"]),
            ("uint32", DTYPE_LABELS["uint32"]), ("int32", DTYPE_LABELS["int32"]),
        ]
        return [
            ParamSpec("endianness", tr("字节序"), "choice", "little",
                      choices=[("little", tr("小端 (Windows/Intel)")), ("big", tr("大端"))],
                      group=tr("报文结构")),
            ParamSpec("rounding", tr("整数取整方式"), "choice", "trunc",
                      choices=[("trunc", tr("截断")), ("round", tr("四舍五入")),
                               ("floor", tr("向下取整")), ("ceil", tr("向上取整"))],
                      group=tr("报文结构")),
            ParamSpec("header", tr("包头 (十六进制，可空)"), "hex", "", group=tr("报文结构"),
                      help=tr("例如 “AA 55” 或 “0xAA,0x55”")),
            ParamSpec("footer", tr("包尾 (十六进制，可空)"), "hex", "", group=tr("报文结构")),
            ParamSpec("include_frame", tr("报文包含帧号"), "bool", False, group=tr("报文结构")),
            ParamSpec("frame_dtype", tr("帧号类型"), "choice", "uint32",
                      choices=int_dtypes + [("float64", DTYPE_LABELS["float64"])],
                      group=tr("报文结构")),
            ParamSpec("include_body_count", tr("报文包含刚体数量"), "bool", False, group=tr("报文结构")),
            ParamSpec("count_dtype", tr("刚体数量类型"), "choice", "uint16",
                      choices=int_dtypes, group=tr("报文结构")),
            ParamSpec("include_timestamp", tr("报文包含时间戳"), "bool", False, group=tr("报文结构")),
            ParamSpec("timestamp_dtype", tr("时间戳类型"), "choice", "float32",
                      choices=[("float32", DTYPE_LABELS["float32"]),
                               ("float64", DTYPE_LABELS["float64"]),
                               ("uint32", DTYPE_LABELS["uint32"]),
                               ("int32", DTYPE_LABELS["int32"])],
                      group=tr("报文结构")),
            ParamSpec("timestamp_unit", tr("时间戳单位"), "choice", "s",
                      choices=[("s", tr("秒")), ("ms", tr("毫秒")), ("us", tr("微秒"))],
                      group=tr("报文结构")),
            ParamSpec("normalize_quaternion", tr("发送前归一化四元数"), "bool", True,
                      group=tr("数值换算")),
            ParamSpec("fields", tr("刚体字段列表"), "fieldlist",
                      [dict(item) for item in DEFAULT_FIELDS],
                      choices=body_quantity_choices(), group=tr("刚体字段"),
                      help=tr("每行一个字段，从上到下的顺序就是报文中的字节顺序。")),
        ]

    # ------------------------------------------------------------------ #
    def _pack_scalar(self, value: float, dtype: str, prefix: str) -> bytes:
        code = DTYPES.get(dtype, DTYPES["int16"])[0]
        if is_float_dtype(dtype):
            return struct.pack(prefix + code, float(value))
        return struct.pack(prefix + code, int(value))

    def _timestamp_value(self, frame: FrameSnapshot, params: Dict[str, Any]) -> float:
        unit = str(params.get("timestamp_unit", "s"))
        value = float(frame.timestamp)
        if unit == "ms":
            value *= 1000.0
        elif unit == "us":
            value *= 1_000_000.0
        return value

    def encode(self, frame: FrameSnapshot, params: Dict[str, Any], ctx: EncodeContext) -> bytes:
        p = self.normalize_params(params)
        prefix = ENDIANNESS.get(str(p.get("endianness", "little")), "<")
        rounding = str(p.get("rounding", "trunc"))
        if rounding not in ROUNDING_MODES:
            rounding = "trunc"
        normalize = bool(p.get("normalize_quaternion", True))
        fields = as_field_specs(p)

        out = bytearray()
        out += parse_hex_bytes(p.get("header", ""))
        if p.get("include_frame"):
            out += self._pack_scalar(
                float(frame.frame_no), str(p.get("frame_dtype", "uint32")), prefix
            )
        if p.get("include_body_count"):
            out += self._pack_scalar(
                float(len(frame.bodies)), str(p.get("count_dtype", "uint16")), prefix
            )
        if p.get("include_timestamp"):
            out += self._pack_scalar(
                self._timestamp_value(frame, p),
                str(p.get("timestamp_dtype", "float32")), prefix,
            )

        # Resolve everything that does not change per body, once per packet.
        compiled = []
        for field in fields:
            quantity = quantity_map().get(field.quantity)
            if quantity is None:
                continue
            compiled.append((
                quantity.getter, field.dtype, field.scale, field.offset,
                field.clamp, is_float_dtype(field.dtype), DTYPES[field.dtype][0],
            ))

        for body in _sorted_bodies(frame):
            view = NormalizedQuatView(body, normalize)
            for getter, dtype, scale, offset, clamp, is_float, code in compiled:
                raw = getter(view, frame)
                if is_float:
                    value = float(raw) * scale + offset
                    if value != value or value in (float("inf"), float("-inf")):
                        value = 0.0
                    out += struct.pack(prefix + code, value)
                else:
                    out += struct.pack(
                        prefix + code,
                        convert_value(raw, dtype, scale, offset, clamp, rounding),
                    )

        out += parse_hex_bytes(p.get("footer", ""))
        return bytes(out)

    def packet_size(self, params: Dict[str, Any], body_count: int) -> int:
        p = self.normalize_params(params)
        size = len(parse_hex_bytes(p.get("header", ""))) + len(parse_hex_bytes(p.get("footer", "")))
        if p.get("include_frame"):
            size += DTYPES.get(str(p.get("frame_dtype")), DTYPES["uint32"])[1]
        if p.get("include_body_count"):
            size += DTYPES.get(str(p.get("count_dtype")), DTYPES["uint16"])[1]
        if p.get("include_timestamp"):
            size += DTYPES.get(str(p.get("timestamp_dtype")), DTYPES["float32"])[1]
        per_body = sum(field.size for field in as_field_specs(p))
        return size + per_body * body_count

    def layout_lines(self, params: Dict[str, Any]) -> List[str]:
        p = self.normalize_params(params)
        lines: List[str] = []
        offset = 0

        def add(size: int, text: str) -> None:
            nonlocal offset
            lines.append("%4d .. %-4d  %s" % (offset, offset + size - 1, text))
            offset += size

        header = parse_hex_bytes(p.get("header", ""))
        if header:
            add(len(header), tr("包头 %s") % header.hex(" ").upper())
        if p.get("include_frame"):
            add(DTYPES.get(str(p.get("frame_dtype")), DTYPES["uint32"])[1],
                tr("帧号 %s") % p.get("frame_dtype", "uint32"))
        if p.get("include_body_count"):
            add(DTYPES.get(str(p.get("count_dtype")), DTYPES["uint16"])[1],
                tr("刚体数量 %s") % p.get("count_dtype", "uint16"))
        if p.get("include_timestamp"):
            add(DTYPES.get(str(p.get("timestamp_dtype")), DTYPES["float32"])[1],
                tr("时间戳 %s (%s)") % (p.get("timestamp_dtype", "float32"),
                                    p.get("timestamp_unit", "s")))

        fields = as_field_specs(p)
        body_start = offset
        if not fields:
            lines.append(tr("        （未配置任何刚体字段，仅发送包头/包尾）"))
        for field in fields:
            quantity = quantity_map().get(field.quantity)
            label = quantity.label if quantity else field.quantity
            unit = quantity.unit if quantity else ""
            extras = []
            if field.scale != 1.0:
                extras.append("×%g" % field.scale)
            if field.offset != 0.0:
                extras.append("%+g" % field.offset)
            if unit and unit != "-":
                extras.append(tr("单位 %s") % unit)
            if not field.clamp:
                extras.append(tr("回绕"))
            add(field.size, "%-12s %-8s %s" % (field.quantity, field.dtype, " ".join(extras)))
        if fields:
            per_body = offset - body_start
            lines.append(tr("        ↑ 单个刚体 %d 字节；整包 = 包头 + N×%d + 包尾，按 ID 升序")
                         % (per_body, per_body))

        footer = parse_hex_bytes(p.get("footer", ""))
        if footer:
            add(len(footer), tr("包尾 %s") % footer.hex(" ").upper())
        return lines


register(CustomBinaryEncoder())
