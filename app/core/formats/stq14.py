"""Default output format: the classic 14-byte-per-body STQ rigid body record.

Layout (per rigid body, concatenated in ascending body-ID order, one UDP
datagram per mocap frame, no header):

======  ======  =============================================
offset  type    meaning
======  ======  =============================================
0       int16   x  = position_x_metres * 2000
2       int16   y  = position_y_metres * 2000
4       int16   z  = position_z_metres * 2000
6       int16   qx = quaternion_x * 1000
8       int16   qy = quaternion_y * 1000
10      int16   qz = quaternion_z * 1000
12      int16   qw = quaternion_w * 1000
======  ======  =============================================

This is byte-for-byte identical to what ``NokovSDKClient_STQ.py`` sent: values
are truncated toward zero (``int()``) and saturated to the int16 range, and the
quaternion is normalised first.
"""

from __future__ import annotations

from ...i18n import tr

import struct
from typing import Any, Dict, List

from ..frames import FrameSnapshot
from ..math3d import quat_normalize
from .base import (
    ENDIANNESS,
    Encoder,
    EncodeContext,
    ParamSpec,
    ROUNDING_MODES,
    _sorted_bodies,
    convert_value,
    parse_hex_bytes,
    register,
)


class Stq14Encoder(Encoder):
    id = "stq14"
    legacy = True

    @property
    def name(self) -> str:
        return tr("STQ 标准 (14 字节/刚体)  ★默认")

    @property
    def description(self) -> str:
        return tr(
            "与 NokovSDKClient_STQ.py 完全一致的格式：每刚体 14 字节 "
            "x,y,z,qx,qy,qz,qw，位置×2000、四元数×1000，int16 小端，"
            "按刚体 ID 升序拼接成单个 UDP 包。"
        )

    def default_params(self) -> Dict[str, Any]:
        return {
            "position_scale": 2000.0,
            "quaternion_scale": 1000.0,
            "normalize_quaternion": True,
            "clamp": True,
            "rounding": "trunc",
            "endianness": "little",
            "include_frame": False,
            "include_body_count": False,
            "header": "",
            "footer": "",
            "drop_uninitialised": False,
        }

    def param_specs(self) -> List[ParamSpec]:
        return [
            ParamSpec("position_scale", tr("位置缩放"), "float", 2000.0, 0.001, 1000000.0,
                      decimals=3, group=tr("数值换算"),
                      help=tr("发送值 = 位置(米) × 该系数。接收端用 0.0005 还原时请保持 2000。")),
            ParamSpec("quaternion_scale", tr("四元数缩放"), "float", 1000.0, 0.001, 1000000.0,
                      decimals=3, group=tr("数值换算"),
                      help=tr("发送值 = 四元数分量 × 该系数。")),
            ParamSpec("normalize_quaternion", tr("发送前归一化四元数"), "bool", True, group=tr("数值换算")),
            ParamSpec("clamp", tr("超出范围时饱和截断"), "bool", True, group=tr("数值换算"),
                      help=tr("关闭后会按类型范围回绕（wrap），一般只在特殊接收端需要。")),
            ParamSpec("rounding", tr("取整方式"), "choice", "trunc",
                      choices=[("trunc", tr("截断 (与旧程序一致)")), ("round", tr("四舍五入")),
                               ("floor", tr("向下取整")), ("ceil", tr("向上取整"))],
                      group=tr("数值换算")),
            ParamSpec("endianness", tr("字节序"), "choice", "little",
                      choices=[("little", tr("小端 (Windows/Intel)")), ("big", tr("大端"))],
                      group=tr("报文结构")),
            ParamSpec("include_frame", tr("包首加入帧号 (uint32)"), "bool", False, group=tr("报文结构")),
            ParamSpec("include_body_count", tr("包首加入刚体数量 (uint16)"), "bool", False,
                      group=tr("报文结构")),
            ParamSpec("header", tr("自定义包头 (十六进制)"), "hex", "", group=tr("报文结构"),
                      help=tr("例如 AA 55。留空表示无包头。")),
            ParamSpec("footer", tr("自定义包尾 (十六进制)"), "hex", "", group=tr("报文结构")),
            ParamSpec("drop_uninitialised", tr("丢弃从未获得有效数据的刚体"), "bool", False,
                      group=tr("报文结构")),
        ]

    # ------------------------------------------------------------------ #
    def _header_bytes(self, params: Dict[str, Any], frame: FrameSnapshot, prefix: str) -> bytes:
        out = bytearray()
        out += parse_hex_bytes(params.get("header", ""))
        if params.get("include_frame"):
            out += struct.pack(prefix + "I", int(frame.frame_no) & 0xFFFFFFFF)
        if params.get("include_body_count"):
            count = min(len(frame.bodies), 0xFFFF)
            out += struct.pack(prefix + "H", count)
        return bytes(out)

    def encode(self, frame: FrameSnapshot, params: Dict[str, Any], ctx: EncodeContext) -> bytes:
        p = self.normalize_params(params)
        prefix = ENDIANNESS.get(str(p.get("endianness", "little")), "<")
        pos_scale = float(p.get("position_scale", 2000.0))
        quat_scale = float(p.get("quaternion_scale", 1000.0))
        normalize = bool(p.get("normalize_quaternion", True))
        clamp = bool(p.get("clamp", True))
        rounding = str(p.get("rounding", "trunc"))
        if rounding not in ROUNDING_MODES:
            rounding = "trunc"
        drop_uninit = bool(p.get("drop_uninitialised", False))

        out = bytearray()
        out += self._header_bytes(p, frame, prefix)

        packer = struct.Struct(prefix + "hhhhhhh")
        for body in _sorted_bodies(frame):
            if drop_uninit and body.status in ("new",):
                continue
            if normalize:
                qx, qy, qz, qw = quat_normalize(body.qx, body.qy, body.qz, body.qw)
            else:
                qx, qy, qz, qw = body.qx, body.qy, body.qz, body.qw
            out += packer.pack(
                convert_value(body.x, "int16", pos_scale, 0.0, clamp, rounding),
                convert_value(body.y, "int16", pos_scale, 0.0, clamp, rounding),
                convert_value(body.z, "int16", pos_scale, 0.0, clamp, rounding),
                convert_value(qx, "int16", quat_scale, 0.0, clamp, rounding),
                convert_value(qy, "int16", quat_scale, 0.0, clamp, rounding),
                convert_value(qz, "int16", quat_scale, 0.0, clamp, rounding),
                convert_value(qw, "int16", quat_scale, 0.0, clamp, rounding),
            )
        out += parse_hex_bytes(p.get("footer", ""))
        return bytes(out)

    def packet_size(self, params: Dict[str, Any], body_count: int) -> int:
        p = self.normalize_params(params)
        size = len(parse_hex_bytes(p.get("header", ""))) + len(parse_hex_bytes(p.get("footer", "")))
        if p.get("include_frame"):
            size += 4
        if p.get("include_body_count"):
            size += 2
        return size + 14 * body_count

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
            add(len(header), tr("包头 (自定义) %s") % header.hex(" ").upper())
        if p.get("include_frame"):
            add(4, tr("帧号 uint32"))
        if p.get("include_body_count"):
            add(2, tr("刚体数量 uint16"))

        pos_scale = float(p.get("position_scale", 2000.0))
        quat_scale = float(p.get("quaternion_scale", 1000.0))
        add(2, tr("x    = 位置 X (m) × %g") % pos_scale)
        add(2, tr("y    = 位置 Y (m) × %g") % pos_scale)
        add(2, tr("z    = 位置 Z (m) × %g") % pos_scale)
        add(2, tr("qx   = 四元数 x × %g") % quat_scale)
        add(2, tr("qy   = 四元数 y × %g") % quat_scale)
        add(2, tr("qz   = 四元数 z × %g") % quat_scale)
        add(2, tr("qw   = 四元数 w × %g") % quat_scale)
        lines.append(tr("        ↑ 单个刚体 14 字节；整包 = 包头 + N×14 + 包尾，按 ID 升序"))

        footer = parse_hex_bytes(p.get("footer", ""))
        if footer:
            add(len(footer), tr("包尾 (自定义) %s") % footer.hex(" ").upper())
        return lines


register(Stq14Encoder())
