"""Headless self-test for the broadcaster core.

Run from the project root::

    python tools\\selftest.py

Verifies in particular that the default ``stq14`` encoder is byte-for-byte
identical to the original ``NokovSDKClient_STQ.py`` packing routine.
"""

from __future__ import annotations

import os
import random
import struct
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import AppConfig, FilterConfig, TransformConfig  # noqa: E402
from app.core.formats import EncodeContext, get_format  # noqa: E402
from app.core.formats import stq14 as stq14_module  # noqa: E402,F401
from app.core.frames import BodyState, FrameSnapshot  # noqa: E402
from app.core.pipeline import Pipeline  # noqa: E402
from app.core.transform import CoordinateTransform  # noqa: E402

FAILURES = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print("  [OK]   %s" % name)
    else:
        print("  [FAIL] %s %s" % (name, detail))
        FAILURES.append(name)


# --------------------------------------------------------------------------- #
# 1. legacy parity - copy of the helper functions from NokovSDKClient_STQ.py
# --------------------------------------------------------------------------- #
def legacy_limit_to_signed_short(value):
    if value > 32767:
        return 32767
    elif value < -32768:
        return -32768
    return int(value)


def legacy_normalize_quaternion(qx, qy, qz, qw):
    norm = (qx * qx + qy * qy + qz * qz + qw * qw) ** 0.5
    if norm > 0:
        return qx / norm, qy / norm, qz / norm, qw / norm
    return 0.0, 0.0, 0.0, 1.0


def legacy_process_rigidbody(x, y, z, qx, qy, qz, qw):
    x_int = legacy_limit_to_signed_short(x * 2000)
    y_int = legacy_limit_to_signed_short(y * 2000)
    z_int = legacy_limit_to_signed_short(z * 2000)
    qx_n, qy_n, qz_n, qw_n = legacy_normalize_quaternion(qx, qy, qz, qw)
    qx_int = legacy_limit_to_signed_short(qx_n * 1000)
    qy_int = legacy_limit_to_signed_short(qy_n * 1000)
    qz_int = legacy_limit_to_signed_short(qz_n * 1000)
    qw_int = legacy_limit_to_signed_short(qw_n * 1000)
    return struct.pack("hhhhhhh", x_int, y_int, z_int, qx_int, qy_int, qz_int, qw_int)


def test_legacy_parity() -> None:
    print("\n== 1. STQ14 与旧脚本逐字节一致性 ==")
    encoder = get_format("stq14")
    params = encoder.normalize_params({})
    ctx = EncodeContext()
    rng = random.Random(20240607)

    for trial in range(40):
        frame = FrameSnapshot(frame_no=1000 + trial, timestamp=trial * 0.008)
        expected = b""
        ids = sorted(rng.sample(range(0, 60), rng.randint(1, 12)))
        for body_id in ids:
            # include nasty values: saturating positions, degenerate quaternions
            x = rng.choice([
                rng.uniform(-3.0, 3.0),
                rng.uniform(-40.0, 40.0),      # saturates
                rng.uniform(-0.001, 0.001),
            ])
            y = rng.uniform(-3.0, 3.0)
            z = rng.uniform(-3.0, 3.0)
            if trial % 7 == 0:
                qx = qy = qz = qw = 0.0        # degenerate quaternion
            else:
                qx, qy, qz, qw = (rng.uniform(-1, 1) for _ in range(4))
            body = BodyState(body_id)
            body.x, body.y, body.z = x, y, z
            body.qx, body.qy, body.qz, body.qw = qx, qy, qz, qw
            frame.bodies[body_id] = body
            expected += legacy_process_rigidbody(x, y, z, qx, qy, qz, qw)

        actual = encoder.encode(frame, params, ctx)
        if actual != expected:
            check("trial %d" % trial, False,
                  "\n    expected %s\n    actual   %s" % (expected.hex(), actual.hex()))
            return
    check("40 组随机数据逐字节一致", True)

    # explicit edge cases
    cases = [
        (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0),
        (16.3835, -16.3835, 16.384, -16.384, 1.0, 0.0, 0.0),
        (100.0, -100.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        (0.00049, -0.00049, 0.0, 0.5, 0.5, 0.5, 0.5),
    ]
    for case in cases:
        x, y, z, qx, qy, qz, qw = case
        frame = FrameSnapshot(frame_no=1)
        body = BodyState(0)
        body.x, body.y, body.z = x, y, z
        body.qx, body.qy, body.qz, body.qw = qx, qy, qz, qw
        frame.bodies[0] = body
        expected = legacy_process_rigidbody(x, y, z, qx, qy, qz, qw)
        actual = encoder.encode(frame, params, ctx)
        check("边界值 %s" % (case,), actual == expected,
              "expected %s got %s" % (expected.hex(), actual.hex()))

    check("包大小 14×N", encoder.packet_size(params, 5) == 70)


# --------------------------------------------------------------------------- #
# 2. pipeline legacy behaviour: glitch hold
# --------------------------------------------------------------------------- #
def test_pipeline_hold() -> None:
    print("\n== 2. 异常值保持 (与旧脚本一致的鲁棒性逻辑) ==")
    config = AppConfig()
    config.filters = FilterConfig(min_body_id=0, abnormal_threshold_mm=9000.0,
                                  hold_last_valid=True)
    pipeline = Pipeline(config)

    def raw_frame(frame_no: int, x_mm: float, y_mm: float, z_mm: float):
        frame = FrameSnapshot(frame_no=frame_no, timestamp=frame_no / 120.0)
        body = BodyState(3, "hand")
        body.raw_x, body.raw_y, body.raw_z = x_mm, y_mm, z_mm
        body.x, body.y, body.z = x_mm / 1000.0, y_mm / 1000.0, z_mm / 1000.0
        body.qx, body.qy, body.qz, body.qw = 0.0, 0.0, 0.0, 1.0
        frame.bodies[3] = body
        return frame

    out, _ = pipeline.process(raw_frame(1, 100.0, 200.0, 300.0))
    check("正常帧通过", abs(out.bodies[3].x - 0.1) < 1e-9)
    check("状态为新建", out.bodies[3].status == "new", out.bodies[3].status)

    out, _ = pipeline.process(raw_frame(2, 150.0, 200.0, 300.0))
    check("第二帧正常", abs(out.bodies[3].x - 0.15) < 1e-9)

    out, _ = pipeline.process(raw_frame(3, 99999.0, 200.0, 300.0))
    check("异常值被替换为上一步", abs(out.bodies[3].x - 0.15) < 1e-9,
          "got %r" % out.bodies[3].x)
    check("状态标记为保持", out.bodies[3].status == "held", out.bodies[3].status)

    out, _ = pipeline.process(raw_frame(4, 250.0, 200.0, 300.0))
    check("恢复正常", abs(out.bodies[3].x - 0.25) < 1e-9)

    # negative / zero body IDs
    config2 = AppConfig()
    config2.filters = FilterConfig(min_body_id=0, hold_last_valid=False)
    p2 = Pipeline(config2)
    frame = FrameSnapshot(frame_no=1, timestamp=0.0)
    for body_id in (-1, 0, 7):
        body = BodyState(body_id)
        body.x = body.y = body.z = 0.01
        frame.bodies[body_id] = body
    out, _ = p2.process(frame)
    check("ID<0 被过滤 (与旧脚本 if body_id >= 0 一致)", sorted(out.bodies) == [0, 7],
          str(sorted(out.bodies)))


# --------------------------------------------------------------------------- #
# 3. transform
# --------------------------------------------------------------------------- #
def test_transform() -> None:
    print("\n== 3. 坐标变换 ==")
    identity = CoordinateTransform(TransformConfig())
    check("默认变换为恒等", identity.is_identity)
    check("恒等位置不变", identity.position(1.5, -2.5, 3.5) == (1.5, -2.5, 3.5))

    config = TransformConfig(axis_map="ZYX", sign_z=-1, offset_x=1.0, unit_scale=2.0)
    transform = CoordinateTransform(config)
    x, y, z = transform.position(1.0, 2.0, 3.0)
    # out_x = in_z * 1 * 2 = 6, then +offset 1 -> 7
    # out_y = in_y * 1 * 2 = 4
    # out_z = in_x * -1 * 2 = -2
    check("映射数值 x", abs(x - 7.0) < 1e-9, str(x))
    check("映射数值 y", abs(y - 4.0) < 1e-9, str(y))
    check("映射数值 z", abs(z + 2.0) < 1e-9, str(z))

    yaw = CoordinateTransform(TransformConfig(yaw_deg=90.0))
    x, y, z = yaw.position(1.0, 0.0, 0.0)
    check("绕 Z 轴旋转 90°", abs(x) < 1e-9 and abs(y - 1.0) < 1e-9, str((x, y, z)))


# --------------------------------------------------------------------------- #
# 4. other formats
# --------------------------------------------------------------------------- #
def test_formats() -> None:
    print("\n== 4. 其它格式 ==")
    frame = FrameSnapshot(frame_no=42, timestamp=1.5)
    body = BodyState(1, "rb1")
    body.x, body.y, body.z = 0.1, 0.2, 0.3
    body.qx, body.qy, body.qz, body.qw = 0.0, 0.0, 0.0, 1.0
    body.vx, body.vy, body.vz = 0.5, -0.25, 0.0
    frame.bodies[1] = body

    ctx = EncodeContext()
    stq14 = get_format("stq14")
    custom = get_format("custom")
    a = stq14.encode(frame, stq14.normalize_params({}), ctx)
    b = custom.encode(frame, custom.normalize_params({}), ctx)
    check("自定义格式默认值 == STQ14", a == b, "%s vs %s" % (a.hex(), b.hex()))

    stq20 = get_format("stq20")
    c = stq20.encode(frame, stq20.normalize_params({}), ctx)
    check("STQ20 长度 20", len(c) == 20, str(len(c)))
    check("STQ20 前 14 字节与 STQ14 一致", c[:14] == a)
    vx = struct.unpack_from("<h", c, 14)[0]
    check("STQ20 速度缩放 1000", vx == 500, str(vx))

    linear = stq20.normalize_params({"velocity_scale": 1.0})
    d = stq20.encode(frame, linear, ctx)
    check("STQ20 velocity_scale=1 复现旧测试脚本", struct.unpack_from("<h", d, 14)[0] == 0)

    # custom: float32 + header
    params = custom.normalize_params({
        "header": "AA 55",
        "fields": [
            {"quantity": "id", "dtype": "uint8", "scale": 1, "offset": 0, "clamp": True},
            {"quantity": "x", "dtype": "float32", "scale": 1, "offset": 0, "clamp": True},
            {"quantity": "speed", "dtype": "float32", "scale": 1, "offset": 0, "clamp": True},
        ],
    })
    data = custom.encode(frame, params, ctx)
    check("自定义包头", data[:2] == b"\xaa\x55", data[:2].hex())
    check("自定义包长", len(data) == 2 + 1 + 4 + 4, str(len(data)))
    check("自定义 float32 位置", abs(struct.unpack_from("<f", data, 3)[0] - 0.1) < 1e-6)
    check("packet_size 预测一致", custom.packet_size(params, len(frame.bodies)) == len(data))

    check("STQ14 packet_size 预测", stq14.packet_size(stq14.normalize_params({}), 3) == 42)
    check("布局说明非空", len(stq14.layout_lines(stq14.normalize_params({}))) > 5)


# --------------------------------------------------------------------------- #
# 5. smoothing
# --------------------------------------------------------------------------- #
def test_smoothing() -> None:
    print("\n== 5. 平滑滤波 ==")
    for mode in ("sma", "median", "ema", "one_euro"):
        config = AppConfig()
        config.filters = FilterConfig(smoothing=mode, smoothing_window=5,
                                      hold_last_valid=False)
        pipeline = Pipeline(config)
        jump_value = None
        tail_values = []
        for index in range(60):
            frame = FrameSnapshot(frame_no=index, timestamp=index / 120.0)
            body = BodyState(1)
            # square wave: the smoother must not follow the jump instantly
            target = 1.0 if index >= 30 else 0.0
            body.raw_x = body.x = target
            body.raw_y = body.y = 0.0
            body.raw_z = body.z = 0.0
            body.qw = 1.0
            frame.bodies[1] = body
            out, _ = pipeline.process(frame)
            value = out.bodies[1].x
            if index == 30:
                jump_value = value
            if index >= 55:
                tail_values.append(value)
        check("%s 跳变不瞬跟" % mode, jump_value is not None and 0.0 <= jump_value < 1.0,
              "jump=%r" % jump_value)
        # EMA and one-euro converge asymptotically rather than exactly
        tolerance = 1e-4 if mode in ("sma", "median") else 0.05
        check("%s 稳态收敛到目标" % mode,
              bool(tail_values) and abs(tail_values[-1] - 1.0) < tolerance,
              "tail=%r" % (tail_values[-1] if tail_values else None))


def test_netinfo() -> None:
    print("\n== 6. 本机网络地址检测 ==")
    from app.core import netinfo

    entries = netinfo.list_local_ipv4()
    check("枚举到本机 IPv4 地址", len(entries) >= 1, "count=%d" % len(entries))
    check("包含回环 127.0.0.1", any(item.ip == "127.0.0.1" for item in entries))

    primary = netinfo.primary_ipv4()
    check("能给出主要网卡 IP", bool(primary), primary)
    print("  主要网卡 IP: %s" % primary)
    for item in entries[:6]:
        print("    %s" % item.label)

    candidates = netinfo.candidate_server_ips()
    check("候选地址以回环开头", candidates and candidates[0] == "127.0.0.1", str(candidates))
    check("候选地址不重复", len(candidates) == len(set(candidates)), str(candidates))
    check("候选地址排除链路本地 169.254.x",
          all(not ip.startswith("169.254.") for ip in candidates), str(candidates))
    check("候选地址数量合理 (<=4)", len(candidates) <= 4, str(candidates))

    targets = netinfo.local_target_ips()
    check("广播目标候选含回环", any(item.ip == "127.0.0.1" for item in targets))

    # usable flag semantics
    loop = [item for item in entries if item.is_loopback][0]
    check("回环地址标记为不可作为服务器候选", not loop.usable)


def main() -> int:
    print("NokovBroadcaster core self-test")
    test_legacy_parity()
    test_pipeline_hold()
    test_transform()
    test_formats()
    test_smoothing()
    test_netinfo()
    print("\n%s" % ("全部通过 ✔" if not FAILURES else "失败项: %s" % FAILURES))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
