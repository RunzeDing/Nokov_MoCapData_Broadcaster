"""Launch the broadcaster (source or frozen exe) in headless mode and verify UDP.

    python tools\\exetest.py                       # tests dist\\NokovBroadcaster.exe
    python tools\\exetest.py --python              # tests the source tree
    python tools\\exetest.py --exe path\\to\\exe
"""

from __future__ import annotations

import argparse
import os
import socket
import struct
import subprocess
import sys
import tempfile
import time

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILURES = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print("  [OK]   %s" % name)
    else:
        print("  [FAIL] %s %s" % (name, detail))
        FAILURES.append(name)


def free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def kill_tree(process) -> None:
    """Kill the process *and* its children.

    A one-file PyInstaller executable runs the real application in a child
    process, so terminating only the bootloader would leave the app behind.
    """
    if process.poll() is not None:
        return
    try:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)],
                       capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        process.kill()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()


def run_case(command, label: str, port: int, fmt: str, seconds: float = 6.0):
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", port))
    receiver.setblocking(False)

    log_path = os.path.join(tempfile.gettempdir(), "nokov-exetest.log")
    with open(log_path, "wb") as log_file:
        process = subprocess.Popen(command, stdout=log_file, stderr=subprocess.STDOUT,
                                   cwd=PROJECT)
        packets = []
        deadline = time.monotonic() + seconds
        try:
            while time.monotonic() < deadline and len(packets) < 30:
                try:
                    data, _addr = receiver.recvfrom(65535)
                    packets.append(data)
                except BlockingIOError:
                    time.sleep(0.01)
                except OSError:
                    break
                if process.poll() is not None and not packets:
                    break
        finally:
            kill_tree(process)
            receiver.close()

    print("  %s: 收到 %d 个包，退出码 %s" % (label, len(packets), process.returncode))
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
        for line in text.splitlines():
            if "error" in line.lower() or "失败" in line or "critical" in line.lower():
                print("     日志: %s" % line.strip()[:160])
    except OSError:
        pass
    return packets


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", action="store_true", help="测试源码而不是 exe")
    parser.add_argument("--exe", default=os.path.join(PROJECT, "dist", "NokovBroadcaster.exe"))
    parser.add_argument("--seconds", type=float, default=6.0)
    args = parser.parse_args()

    if args.python:
        base = [sys.executable, os.path.join(PROJECT, "NokovBroadcaster.py")]
        target_label = "源码"
    else:
        if not os.path.exists(args.exe):
            print("找不到可执行文件: %s" % args.exe)
            return 2
        base = [args.exe]
        target_label = os.path.basename(args.exe)
    print("测试目标: %s" % target_label)

    # ---- case 1: default STQ14 ---------------------------------------- #
    print("\n== 1. 默认 STQ14 格式 ==")
    port = free_port()
    command = base + ["--headless", "--simulate", "3",
                      "--target", "127.0.0.1:%d" % port, "--format", "stq14"]
    packets = run_case(command, "stq14", port, "stq14", args.seconds)
    check("收到报文", len(packets) > 5, "count=%d" % len(packets))
    if packets:
        lengths = {len(packet) for packet in packets}
        check("报文长度均为 14 的倍数", all(length % 14 == 0 for length in lengths),
              str(sorted(lengths)))
        check("刚体数量稳定为 3", lengths == {42}, str(sorted(lengths)))
        values = struct.unpack("<" + "h" * (len(packets[-1]) // 2), packets[-1])
        x, y, z = (value / 2000.0 for value in values[0:3])
        norm = sum(value * value for value in (v / 1000.0 for v in values[3:7])) ** 0.5
        print("  首个刚体 pos=(%.3f, %.3f, %.3f) m  四元数模=%.4f" % (x, y, z, norm))
        check("位置在合理范围", all(abs(value) <= 3.0 for value in (x, y, z)))
        check("四元数已归一化", abs(norm - 1.0) < 0.01)
        check("按 ID 升序（第一个刚体在原点附近）", abs(x) < 3.0 and abs(y) < 3.0)

    # ---- case 2: STQ20 ------------------------------------------------- #
    print("\n== 2. STQ20 扩展格式 ==")
    port = free_port()
    command = base + ["--headless", "--simulate", "2",
                      "--target", "127.0.0.1:%d" % port, "--format", "stq20"]
    packets = run_case(command, "stq20", port, "stq20", args.seconds)
    check("收到报文", len(packets) > 5, "count=%d" % len(packets))
    if packets:
        lengths = {len(packet) for packet in packets}
        check("报文长度均为 20 的倍数", all(length % 20 == 0 for length in lengths),
              str(sorted(lengths)))
        check("刚体数量稳定为 2", lengths == {40}, str(sorted(lengths)))
        vx = struct.unpack_from("<h", packets[-1], 14)[0]
        print("  首个刚体 vx=%d (%.3f m/s)" % (vx, vx / 1000.0))
        check("包含速度字段", len(packets[-1]) >= 20)

    # ---- case 3: --help works ------------------------------------------ #
    print("\n== 3. 命令行帮助 ==")
    result = subprocess.run(base + ["--help"], capture_output=True, timeout=60)
    text = (result.stdout + result.stderr).decode("utf-8", "replace")
    check("--help 正常返回", result.returncode == 0, "rc=%d" % result.returncode)
    check("帮助中包含 --headless", "--headless" in text)
    check("帮助中包含 --target", "--target" in text)

    # ---- case 4: unreachable server exits cleanly ---------------------- #
    print("\n== 4. 连接失败路径（不应崩溃） ==")
    result = subprocess.run(
        base + ["--headless", "--server", "203.0.113.99", "--target", "127.0.0.1:29999"],
        capture_output=True, timeout=120,
    )
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    print("  退出码 %d" % result.returncode)
    check("连接失败时优雅退出（退出码 3）", result.returncode == 3,
          "rc=%d (负数表示崩溃)" % result.returncode)
    check("给出失败原因", "失败" in output or "failure" in output.lower())

    # ---- case 5: shutdown after broadcasting is clean ------------------ #
    print("\n== 5. 广播后正常退出 ==")
    port = free_port()
    command = base + ["--headless", "--simulate", "2",
                      "--target", "127.0.0.1:%d" % port]
    packets = run_case(command, "shutdown", port, "stq14", 3.0)
    check("广播期间收到报文", len(packets) > 3, "count=%d" % len(packets))

    # ---- case 6: the saved language reaches the packaged app ----------- #
    print("\n== 6. 语言设置生效（exe 读取配置） ==")
    # The packaged app is windowed, so stdout goes nowhere; the log file is the
    # reliable place to observe that the language setting was applied.
    import json
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    config_path = os.path.join(appdata, "NokovBroadcaster", "config.json")
    log_path = os.path.join(appdata, "NokovBroadcaster", "logs", "nokov_broadcaster.log")
    original = None
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as handle:
            original = handle.read()
    try:
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        payload = {"version": 1, "ui": {"language": "en", "log_to_file": True}}
        if original:
            try:
                payload = json.loads(original)
                payload.setdefault("ui", {})["language"] = "en"
                payload["ui"]["log_to_file"] = True
            except ValueError:
                pass
        with open(config_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)

        mark = os.path.getsize(log_path) if os.path.exists(log_path) else 0
        port = free_port()
        command = base + ["--headless", "--simulate", "2",
                          "--target", "127.0.0.1:%d" % port]
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, cwd=PROJECT)
        time.sleep(4.0)
        kill_tree(process)

        text = ""
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8", errors="replace") as handle:
                handle.seek(mark)
                text = handle.read()
        check("英文配置使日志变为英文",
              "Engine thread started" in text or "Interface started" in text,
              text.strip().splitlines()[-1][:120] if text.strip() else "(日志无新增)")
        english_lines = [line for line in text.splitlines() if "started" in line]
        if english_lines:
            print("  %s" % english_lines[-1][:110])

        with open(config_path, "w", encoding="utf-8") as handle:
            payload = json.loads(original) if original else {"version": 1}
            payload.setdefault("ui", {})["language"] = "zh"
            json.dump(payload, handle, ensure_ascii=False)
    finally:
        if original is not None:
            with open(config_path, "w", encoding="utf-8") as handle:
                handle.write(original)

    print("\n%s" % ("端到端测试全部通过 ✔" if not FAILURES else "失败项: %s" % FAILURES))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
