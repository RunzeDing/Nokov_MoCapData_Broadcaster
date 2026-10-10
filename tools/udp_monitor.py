"""Standalone UDP receiver for verifying what NokovBroadcaster actually sends.

Usage::

    python tools\\udp_monitor.py --port 22222
    python tools\\udp_monitor.py --port 22222 --format stq20
    python tools\\udp_monitor.py --port 22222 --format custom --fields id:uint8,x:float32,y:float32,z:float32

Useful for commissioning a receiver: it decodes the packet with the same layout
rules the broadcaster uses and prints positions in metres.
"""

from __future__ import annotations

import argparse
import os
import socket
import struct
import sys
import time
from typing import List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TYPE_CODES = {
    "int8": "b", "uint8": "B", "int16": "h", "uint16": "H",
    "int32": "i", "uint32": "I", "float32": "f", "float64": "d",
}
TYPE_SIZES = {
    "int8": 1, "uint8": 1, "int16": 2, "uint16": 2,
    "int32": 4, "uint32": 4, "float32": 4, "float64": 8,
}


def parse_layout(text: str) -> List[Tuple[str, str]]:
    """Parse ``"id:uint8,x:float32"`` into ``[("id", "uint8"), ...]``."""
    layout = []
    for chunk in (text or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        name, _, dtype = chunk.partition(":")
        dtype = dtype.strip() or "int16"
        if dtype not in TYPE_CODES:
            raise SystemExit("未知类型: %s" % dtype)
        layout.append((name.strip(), dtype))
    return layout


def decode(data: bytes, layout: List[Tuple[str, str]], prefix: str = "<"):
    size = sum(TYPE_SIZES[dtype] for _name, dtype in layout)
    if size == 0 or len(data) % size:
        return None
    fmt = prefix + "".join(TYPE_CODES[dtype] for _name, dtype in layout)
    records = []
    for offset in range(0, len(data), size):
        records.append(struct.unpack_from(fmt, data, offset))
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="NokovBroadcaster UDP 接收自检工具")
    parser.add_argument("--port", type=int, default=22222, help="监听端口，默认 22222")
    parser.add_argument("--host", default="0.0.0.0", help="绑定地址，默认 0.0.0.0")
    parser.add_argument("--format", default="stq14",
                        choices=["stq14", "stq20", "custom"],
                        help="按照哪种格式解析")
    parser.add_argument("--fields", default="",
                        help="custom 格式的字段定义，例如 id:uint8,x:float32,y:float32,z:float32")
    parser.add_argument("--count", type=int, default=0, help="收够多少个包后退出，0 = 一直收")
    args = parser.parse_args()

    if args.format == "stq14":
        layout = [(name, "int16") for name in ("x", "y", "z", "qx", "qy", "qz", "qw")]
        scales = {"x": 1 / 2000.0, "y": 1 / 2000.0, "z": 1 / 2000.0,
                  "qx": 0.001, "qy": 0.001, "qz": 0.001, "qw": 0.001}
        record_size = 14
    elif args.format == "stq20":
        layout = [(name, "int16") for name in
                  ("x", "y", "z", "qx", "qy", "qz", "qw", "vx", "vy", "vz")]
        scales = {"x": 1 / 2000.0, "y": 1 / 2000.0, "z": 1 / 2000.0,
                  "qx": 0.001, "qy": 0.001, "qz": 0.001, "qw": 0.001,
                  "vx": 0.001, "vy": 0.001, "vz": 0.001}
        record_size = 20
    else:
        layout = parse_layout(args.fields) or [("id", "uint8"), ("x", "float32"),
                                               ("y", "float32"), ("z", "float32")]
        scales = {}
        record_size = sum(TYPE_SIZES[dtype] for _name, dtype in layout)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
    except OSError:
        pass
    sock.bind((args.host, args.port))

    print("监听 %s:%d ，按 %s 格式解析（每刚体 %d 字节）"
          % (args.host, args.port, args.format, record_size))
    print("字段: %s" % ", ".join("%s:%s" % item for item in layout))
    print("按 Ctrl+C 退出\n")

    received = 0
    started = time.monotonic()
    stats: List[int] = []
    try:
        while True:
            data, address = sock.recvfrom(65535)
            received += 1
            stats.append(len(data))
            elapsed = time.monotonic() - started
            print("包 #%d  来自 %s:%d  长度 %d 字节  平均 %.0f 包/秒  刚体数 %d"
                  % (received, address[0], address[1], len(data),
                     received / max(1e-6, elapsed), len(data) // record_size))
            if received <= 3 and (len(data) % record_size == 0):
                records = decode(data, layout)
                for index, record in enumerate((records or [])[:4]):
                    parts = []
                    for (name, _dtype), value in zip(layout, record):
                        scale = scales.get(name)
                        parts.append("%s=%s" % (name, ("%.4f" % (value * scale))
                                                if scale else str(value)))
                    print("    刚体[%d] %s" % (index, "  ".join(parts)))
            if args.count and received >= args.count:
                break
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()

    if stats:
        print("\n共接收 %d 个包；长度 min=%d max=%d；用时 %.1f 秒"
              % (received, min(stats), max(stats), time.monotonic() - started))
    return 0


if __name__ == "__main__":
    sys.exit(main())
