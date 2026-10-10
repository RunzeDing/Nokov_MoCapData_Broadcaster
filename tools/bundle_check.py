"""Verify that a built NokovBroadcaster.exe really is self-contained.

What it checks
--------------
1. Unpacks the one-file archive into a temporary directory (exactly what the
   bootloader does at start-up).
2. Confirms the bundled Nokov SDK and the C++ runtime it needs are present.
3. **Isolation test**: disables the System32 search path for the duration of the
   load and tries to load ``nokov\\lib\\nokov_sdk.dll`` using only the unpacked
   directory.  If it loads, the SDK genuinely does not need anything that is
   only installed on the build machine (VC++ redistributable, Python, ...).

    python tools\\bundle_check.py [path\\to\\NokovBroadcaster.exe]
"""

from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile

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


def unpack(exe: str, destination: str):
    """Extract every binary/data entry of the one-file archive."""
    from PyInstaller.archive.readers import CArchiveReader

    reader = CArchiveReader(exe)
    extracted = []
    for key in reader.toc:
        _dpos, _dlen, _ulen, _flag, typcd, name = key
        if typcd not in ("b", "x"):
            # 'z' is the embedded PYZ, 's'/'m' are bootstrap scripts/modules
            continue
        result = reader.extract(name)
        # PyInstaller returns (ispkg, contents)
        payload = result[1] if isinstance(result, tuple) else result
        if not isinstance(payload, (bytes, bytearray)):
            continue
        target = os.path.join(destination, name)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as handle:
            handle.write(payload)
        extracted.append(name)
    return extracted


# --------------------------------------------------------------------------- #
# the isolation test runs in a fresh interpreter so DLL directory state is clean
# --------------------------------------------------------------------------- #
ISOLATION_SCRIPT = r'''
import ctypes, os, sys

root = sys.argv[1]
dll = sys.argv[2]

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.SetDefaultDllDirectories.argtypes = [ctypes.c_uint]
k32.AddDllDirectory.argtypes = [ctypes.c_wchar_p]
k32.LoadLibraryExW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_uint]
k32.LoadLibraryExW.restype = ctypes.c_void_p
k32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
k32.GetModuleHandleW.restype = ctypes.c_void_p

LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR = 0x00000100
LOAD_LIBRARY_SEARCH_USER_DIRS     = 0x00000400

# Only the DLL's own directory and our explicit user directories are searched;
# System32 and PATH are excluded on purpose.
k32.SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_USER_DIRS)
k32.AddDllDirectory(root)
k32.AddDllDirectory(os.path.join(root, "PySide2"))

# The Windows UCRT is part of the OS (api-ms-win-crt-* forward to ucrtbase.dll)
# and is already loaded in this process, so it needs no special handling.
handle = k32.LoadLibraryExW(dll, None,
                            LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_USER_DIRS)
if not handle:
    print("FAIL %d" % ctypes.get_last_error())
    sys.exit(1)

# prove it is the copy from the bundle, not something from System32
import ctypes.wintypes as wt
buf = ctypes.create_unicode_buffer(1024)
k32.GetModuleFileNameW = ctypes.WinDLL("kernel32").GetModuleFileNameW
k32.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint]
k32.GetModuleFileNameW(handle, buf, 1024)
print("OK %s" % buf.value)
'''


def main() -> int:
    exe = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        PROJECT, "dist", "NokovBroadcaster.exe")
    if not os.path.exists(exe):
        print("找不到 exe: %s" % exe)
        return 2
    print("检查目标: %s (%.1f MB)" % (exe, os.path.getsize(exe) / 1048576))

    work = tempfile.mkdtemp(prefix="nokov-bundle-")
    try:
        print("\n== 1. 解包归档 ==")
        names = unpack(exe, work)
        print("  解出 %d 个二进制/数据文件" % len(names))

        lowered = {name.replace("/", "\\").lower(): name for name in names}

        print("\n== 2. Nokov SDK 与其运行库 ==")
        sdk_rel = "nokov\\lib\\nokov_sdk.dll"
        check("包含 nokov_sdk.dll", sdk_rel in lowered, sdk_rel)
        for needed in ("msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll"):
            present = needed in lowered
            check("包含 %s" % needed, present,
                  "缺少 %s —— 目标机可能必须安装 VC++ 运行库" % needed)
        check("包含 Python 解释器 (python38.dll)", "python38.dll" in lowered)

        print("\n== 3. 不依赖系统搜索路径的加载测试 ==")
        print("  (临时禁用 System32 搜索目录，只用解包出来的文件加载 SDK)")
        script = os.path.join(work, "_isolation.py")
        with open(script, "w", encoding="utf-8") as handle:
            handle.write(ISOLATION_SCRIPT)
        sdk_path = os.path.join(work, sdk_rel)
        result = subprocess.run([sys.executable, script, work, sdk_path],
                                capture_output=True, timeout=180)
        output = (result.stdout + result.stderr).decode("utf-8", "replace").strip()
        print("  %s" % output.replace("\n", "\n  "))
        loaded_from_bundle = output.startswith("OK") and work.lower() in output.lower()
        check("SDK 可在隔离环境下加载（不需要本机 VC++ 运行库/Python）",
              loaded_from_bundle, output)

        print("\n== 4. 体积占用前 8 名 ==")
        sizes = []
        for name in names:
            path = os.path.join(work, name)
            if os.path.exists(path):
                sizes.append((os.path.getsize(path), name))
        for size, name in sorted(sizes, reverse=True)[:8]:
            print("  %8.2f MB  %s" % (size / 1048576, name))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print("\n%s" % ("自包含性检查全部通过 ✔" if not FAILURES else "失败项: %s" % FAILURES))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
