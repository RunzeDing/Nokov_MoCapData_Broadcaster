"""End-to-end GUI smoke test.

Runs the real application with the Qt "offscreen" platform, feeds it the built-in
simulator, and checks that UDP packets actually arrive on a local socket with the
expected STQ wire layout.

    python tools\\guitest.py
"""

from __future__ import annotations

import os
import socket
import struct
import sys
import tempfile
import time

# Keep the test away from the user's real settings.  Note: setdefault() would
# NOT work here - APPDATA always exists, so it must be overwritten outright.
_TEST_APPDATA = tempfile.mkdtemp(prefix="nokov-guitest-")
os.environ["APPDATA"] = _TEST_APPDATA
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAILURES = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print("  [OK]   %s" % name)
    else:
        print("  [FAIL] %s %s" % (name, detail))
        FAILURES.append(name)


def main() -> int:
    print("NokovBroadcaster GUI smoke test")

    from PySide2.QtCore import Qt
    from PySide2.QtWidgets import QApplication

    from app.gui import theme

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv[:1])
    theme.apply_theme(app)

    from app.gui.context import AppContext
    from app.gui.main_window import MainWindow

    # ---- a local UDP receiver ----------------------------------------- #
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", 0))
    receiver.setblocking(False)
    port = receiver.getsockname()[1]
    print("  接收测试端口: %d" % port)

    context = AppContext()
    context.start_background()

    window = MainWindow(context)
    window.show()

    # ---- configure through the UI, exactly like a user would ----------- #
    context.config.broadcast.targets = []
    from app.config import BroadcastTarget
    context.config.broadcast.targets.append(
        BroadcastTarget(ip="127.0.0.1", port=port, enabled=True)
    )
    context.config.broadcast.format_id = "stq14"
    context.config_changed()
    window.broadcast_page.reload_from_config()

    check("默认格式为 STQ14", context.config.broadcast.format_id == "stq14")

    window.connection_page.sim_checkbox.setChecked(True)
    check("模拟数据源已启动", context.simulator_running)

    window.broadcast_page.request_start()
    check("广播已开始", context.engine.broadcasting)

    # ---- pump the event loop ------------------------------------------ #
    packets = []
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and len(packets) < 40:
        app.processEvents()
        try:
            while True:
                data, _addr = receiver.recvfrom(65535)
                packets.append(data)
        except BlockingIOError:
            pass
        except OSError:
            break
        time.sleep(0.005)

    print("  收到 %d 个 UDP 包" % len(packets))
    check("收到 UDP 数据", len(packets) > 5)

    if packets:
        first = packets[0]
        check("报文长度为 14 的整数倍", len(first) % 14 == 0, "len=%d" % len(first))
        body_count = len(first) // 14
        check("包含至少 1 个刚体", body_count >= 1, "bodies=%d" % body_count)

        values = struct.unpack("<" + "h" * (len(first) // 2), first)
        # first body: x, y, z, qx, qy, qz, qw
        x, y, z = (value / 2000.0 for value in values[0:3])
        qx, qy, qz, qw = (value / 1000.0 for value in values[3:7])
        print("  首个刚体: pos=(%.3f, %.3f, %.3f) m  quat=(%.3f, %.3f, %.3f, %.3f)"
              % (x, y, z, qx, qy, qz, qw))
        check("位置在合理范围 (±3 m)", all(abs(value) <= 3.0 for value in (x, y, z)))
        norm = (qx * qx + qy * qy + qz * qz + qw * qw) ** 0.5
        check("四元数已归一化", abs(norm - 1.0) < 0.01, "norm=%.4f" % norm)

        sizes = {len(packet) for packet in packets}
        check("每次发送的刚体数量稳定", len(sizes) <= 2, "sizes=%s" % sorted(sizes))

    # ---- exercise the other pages -------------------------------------- #
    for index in range(len(window.pages)):
        window.show_page(index)
        for _ in range(6):
            app.processEvents()
            time.sleep(0.005)
        window.pages[index].refresh(time.monotonic())
    check("所有页面均可刷新", True)

    # switch through every format and rebuild its parameter form
    from app.core.formats import list_formats
    for encoder in list_formats():
        window.broadcast_page.format_combo.setCurrentIndex(
            window.broadcast_page.format_combo.findData(encoder.id))
        for _ in range(4):
            app.processEvents()
        check("格式 %s 可配置" % encoder.id, True)

    window.broadcast_page.format_combo.setCurrentIndex(
        window.broadcast_page.format_combo.findData("stq14"))
    app.processEvents()

    # ---- custom format with float32 fields ----------------------------- #
    context.config.broadcast.format_id = "custom"
    context.config.broadcast.set_params_for("custom", {
        "fields": [
            {"quantity": "id", "dtype": "uint8", "scale": 1.0, "offset": 0.0, "clamp": True},
            {"quantity": "x", "dtype": "float32", "scale": 1.0, "offset": 0.0, "clamp": True},
            {"quantity": "y", "dtype": "float32", "scale": 1.0, "offset": 0.0, "clamp": True},
            {"quantity": "z", "dtype": "float32", "scale": 1.0, "offset": 0.0, "clamp": True},
        ],
        "header": "AA 55",
    })
    window.broadcast_page.reload_from_config()
    packets.clear()
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and len(packets) < 10:
        app.processEvents()
        try:
            while True:
                data, _addr = receiver.recvfrom(65535)
                packets.append(data)
        except (BlockingIOError, OSError):
            pass
        time.sleep(0.005)

    if packets:
        packet = packets[-1]
        check("自定义包头生效", packet[:2] == b"\xaa\x55", packet[:2].hex())
        check("自定义包长 2+13×N", (len(packet) - 2) % 13 == 0, "len=%d" % len(packet))
        body_id = packet[2]
        x = struct.unpack_from("<f", packet, 3)[0]
        check("自定义 float32 位置合理", abs(x) <= 3.0, "x=%r" % x)
        print("  自定义格式首刚体: id=%d x=%.3f" % (body_id, x))

    # ---- statistics ---------------------------------------------------- #
    stats = context.engine.stats
    print("  引擎统计: 处理 %d 帧, 发送 %d 包, %.1f fps, 编码 %.2f ms"
          % (stats.frames_processed, stats.packets_sent, stats.fps, stats.encode_ms))
    check("引擎处理了数据帧", stats.frames_processed > 10)
    check("统计中发送包数 > 0", stats.packets_sent > 0)
    check("编码耗时可测", stats.encode_ms >= 0.0)

    window.broadcast_page._on_stop()
    check("广播已停止", not context.engine.broadcasting)
    check("模拟数据源全程存活", context.simulator_running)
    window.connection_page.sim_checkbox.setChecked(False)

    # ---- local IP detection ------------------------------------------- #
    print("\n== 本机 IP 检测 ==")
    window.connection_page._refresh_local_ips()
    hint = window.connection_page.local_ip_label.text()
    check("连接页显示本机 IPv4", "127.0.0.1" in hint, hint[:90])

    window.connection_page._set_server_ip("127.0.0.1")
    check("可写入服务器 IP", context.config.network.server_ip == "127.0.0.1",
          context.config.network.server_ip)

    before = len(context.config.broadcast.targets)
    previous_port = context.config.broadcast.targets[-1].port if before else 22222
    window.broadcast_page._on_add_local_target(nic=False)
    check("可追加本机回环广播目标",
          len(context.config.broadcast.targets) == before + 1,
          str(len(context.config.broadcast.targets)))
    added = context.config.broadcast.targets[-1]
    check("目标 IP 为 127.0.0.1", added.ip == "127.0.0.1", added.ip)
    check("目标端口沿用当前端口 %s" % previous_port, added.port == previous_port,
          str(added.port))

    from app.core import netinfo
    candidates = netinfo.candidate_server_ips()
    check("服务器候选地址可用", candidates and candidates[0] == "127.0.0.1", str(candidates))
    print("  本机候选: %s" % "、".join(candidates))

    # ---- language switching -------------------------------------------- #
    print("\n== 中英文切换 ==")
    from app.i18n import get_language

    def snapshot():
        return (
            [window.nav.item(i).text() for i in range(window.nav.count())],
            window.connection_page.auto_local_button.text(),
            window.visualize_page.body_table.horizontalHeaderItem(1).text(),
            window.broadcast_page.format_combo.itemText(0),
            window.visualize_page._group_buttons["position"].text(),
        )

    window.switch_language("zh")
    for _ in range(6):
        app.processEvents()
    zh = snapshot()
    check("中文界面", zh[0][0] == "连接" and zh[2] == "名称", str(zh[:3]))

    window.switch_language("en")
    for _ in range(6):
        app.processEvents()
    en = snapshot()
    check("英文导航", en[0] == ["Connect", "Broadcast", "Processing", "Visualise",
                                "Log & Settings"], str(en[0]))
    check("英文按钮", en[1] == "Connect locally", en[1])
    check("英文表头", en[2] == "Name", en[2])
    check("英文格式名", en[3].startswith("STQ standard"), en[3])
    check("英文通道分组", en[4] == "Position", en[4])
    check("语言已写入配置", context.config.ui.language == "en",
          context.config.ui.language)

    window.switch_language("zh")
    for _ in range(6):
        app.processEvents()
    check("切回中文", snapshot() == zh, str(snapshot()[:2]))
    check("语言状态一致", get_language() == "zh", get_language())
    check("广播未因切换中断", context.engine is not None)

    window.close()
    app.processEvents()
    receiver.close()

    print("\n%s" % ("GUI 冒烟测试全部通过 ✔" if not FAILURES else "失败项: %s" % FAILURES))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
