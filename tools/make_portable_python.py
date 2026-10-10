"""Build the self-contained Python runtime that ships inside the project.

Creates ``<project>\\python\\`` - an embedded CPython 3.8 interpreter plus the
PySide2 wheels unpacked into ``Lib\\site-packages`` - so the Python version of
NokovBroadcaster runs on any Windows machine without installing anything.

    python tools\\make_portable_python.py            # use .buildcache / network
    python tools\\make_portable_python.py --keep-cache

Everything not needed by this application (Qt WebEngine, 3D, Charts, Quick,
Multimedia, ...) is deleted afterwards: 330 MB -> ~55 MB.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(PROJECT, "python")
CACHE = os.path.join(PROJECT, ".buildcache")

PYTHON_VERSION = "3.8.10"
EMBED_URL = ("https://www.python.org/ftp/python/%s/python-%s-embed-amd64.zip"
             % (PYTHON_VERSION, PYTHON_VERSION))
WHEELS = ("PySide2==5.15.2.1", "shiboken2==5.15.2.1")

#: PySide2 modules this application imports directly
KEEP_ROOTS = (
    "QtCore.pyd",
    "QtGui.pyd",
    "QtWidgets.pyd",
    "pyside2.abi3.dll",
    "shiboken2.pyd",
    "shiboken2.abi3.dll",
)

#: extra files always kept regardless of the dependency walk
KEEP_ALWAYS = {
    "msvcp140.dll",
    "msvcp140_1.dll",
    "msvcp140_2.dll",
    "msvcp140_codecvt_ids.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",
    "concrt140.dll",
    "vccorlib140.dll",
}

#: plugin files worth keeping (offscreen/minimal keep the test suite working)
KEEP_PLUGINS = {
    "platforms/qwindows.dll",
    "platforms/qoffscreen.dll",
    "platforms/qminimal.dll",
    "styles/qwindowsvistastyle.dll",
    "imageformats/qico.dll",
    "imageformats/qjpeg.dll",
    "imageformats/qgif.dll",
    "imageformats/qsvg.dll",
}

#: Qt translations used for the standard dialogs (OK / Cancel / Yes / No)
KEEP_TRANSLATIONS = {
    "qtbase_zh_CN.qm",
    "qt_zh_CN.qm",
    "qtbase_en.qm",
}

REMOVE_DIRS = (
    "include", "typesystems", "examples", "scripts", "qml", "resources",
    "glue", "lib",
)

PTH_CONTENT = "python38.zip\n.\nLib\\site-packages\nimport site\n"


def log(message: str) -> None:
    print(message, flush=True)


def download(url: str, destination: str) -> str:
    if os.path.exists(destination):
        log("  已存在缓存: %s" % os.path.basename(destination))
        return destination
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    log("  下载 %s" % url)
    with urllib.request.urlopen(url, timeout=180) as response, \
            open(destination, "wb") as handle:
        shutil.copyfileobj(response, handle)
    return destination


def fetch_wheels() -> list:
    """Return local wheel paths, downloading through pip when needed."""
    existing = [os.path.join(CACHE, name) for name in os.listdir(CACHE)
                if name.lower().endswith(".whl")] if os.path.isdir(CACHE) else []
    wanted = []
    for requirement in WHEELS:
        package = requirement.split("==")[0].lower()
        match = [path for path in existing if os.path.basename(path).lower().startswith(package)]
        if match:
            wanted.append(match[0])
    if len(wanted) == len(WHEELS):
        return wanted

    log("  通过 pip 下载轮子…")
    subprocess.run(
        [sys.executable, "-m", "pip", "download", "--no-deps", "--dest", CACHE] + list(WHEELS),
        check=True,
    )
    return [os.path.join(CACHE, name) for name in os.listdir(CACHE)
            if name.lower().endswith(".whl")]


def unpack_zip(path: str, destination: str) -> None:
    with zipfile.ZipFile(path) as archive:
        archive.extractall(destination)


def trim(site_packages: str) -> None:
    """Delete every Qt binary this application cannot reach.

    Rather than guessing, walk the PE import graph starting from the modules the
    app imports (QtCore/QtGui/QtWidgets) and keep exactly that closure.  Guessing
    is how you end up deleting ``Qt5Qml.dll``, which ``pyside2.abi3.dll`` links
    against even though this app never uses QML.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from dlldiag import PE  # noqa: E402  (local tool, not part of the app)

    pyside = os.path.join(site_packages, "PySide2")
    shiboken = os.path.join(site_packages, "shiboken2")
    if not os.path.isdir(pyside):
        raise SystemExit("未找到 PySide2：%s" % pyside)

    search_dirs = [pyside, shiboken]
    available = {}
    for directory in search_dirs:
        if not os.path.isdir(directory):
            continue
        for name in os.listdir(directory):
            if name.lower().endswith((".dll", ".pyd")):
                available.setdefault(name.lower(), os.path.join(directory, name))

    keep = set(KEEP_ALWAYS)
    queue = [name.lower() for name in KEEP_ROOTS]
    while queue:
        name = queue.pop()
        if name in keep:
            continue
        path = available.get(name)
        if path is None:
            continue
        keep.add(name)
        try:
            for imported in PE(path).imports():
                key = imported.lower()
                if key in available and key not in keep:
                    queue.append(key)
        except Exception as exc:  # pragma: no cover - malformed PE
            print("  警告: 无法解析 %s 的依赖 (%r)" % (name, exc))

    removed = 0
    removed_bytes = 0

    def drop(path: str) -> None:
        nonlocal removed, removed_bytes
        if not os.path.exists(path):
            return
        if os.path.isdir(path):
            size = sum(os.path.getsize(os.path.join(root, name))
                       for root, _dirs, files in os.walk(path) for name in files)
            shutil.rmtree(path, ignore_errors=True)
        else:
            size = os.path.getsize(path)
            try:
                os.remove(path)
            except OSError:
                return
        removed += 1
        removed_bytes += size

    # 1. binaries outside the dependency closure
    for directory in search_dirs:
        if not os.path.isdir(directory):
            continue
        for name in os.listdir(directory):
            full = os.path.join(directory, name)
            if os.path.isdir(full):
                continue
            lower = name.lower()
            if lower.endswith((".dll", ".pyd", ".lib", ".exp", ".prl", ".pyi")):
                if lower not in keep:
                    drop(full)

    # 2. bulky subdirectories
    for name in REMOVE_DIRS:
        drop(os.path.join(pyside, name))

    # 3. plugins
    plugins = os.path.join(pyside, "plugins")
    if os.path.isdir(plugins):
        for root, _dirs, files in os.walk(plugins, topdown=False):
            for name in files:
                full = os.path.join(root, name)
                relative = os.path.relpath(full, plugins).replace("\\", "/")
                if relative not in KEEP_PLUGINS:
                    drop(full)
            if not os.listdir(root):
                os.rmdir(root)

    # 4. translations
    translations = os.path.join(pyside, "translations")
    if os.path.isdir(translations):
        for name in os.listdir(translations):
            if name not in KEEP_TRANSLATIONS:
                drop(os.path.join(translations, name))

    kept = sorted(name for name in keep if name in available)
    print("  保留 %d 个 Qt 二进制: %s" % (len(kept), ", ".join(kept)))
    print("  精简: 删除 %d 项，释放 %.1f MB" % (removed, removed_bytes / 1048576))


def copy_crt(python_dir: str, site_packages: str) -> int:
    """Make sure the CRT sits next to python.exe so Qt / the SDK load anywhere."""
    source = os.path.join(site_packages, "shiboken2")
    names = ("MSVCP140.dll", "MSVCP140_1.dll", "MSVCP140_2.dll",
             "MSVCP140_codecvt_ids.dll", "VCRUNTIME140.dll", "VCRUNTIME140_1.dll",
             "concrt140.dll", "vccorlib140.dll")
    copied = 0
    for name in names:
        path = os.path.join(source, name)
        if os.path.exists(path):
            shutil.copy2(path, os.path.join(python_dir, name))
            copied += 1
    return copied


def verify(python_exe: str) -> bool:
    code = (
        "import sys, PySide2;"
        "from PySide2 import QtCore, QtGui, QtWidgets;"
        "print('  Python %s / PySide2 %s / Qt %s' % ("
        "sys.version.split()[0], PySide2.__version__, QtCore.qVersion()))"
    )
    result = subprocess.run([python_exe, "-c", code], capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    sys.stdout.write(result.stdout)
    if result.returncode != 0:
        sys.stdout.write(result.stderr)
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="构建内置便携 Python 运行环境")
    parser.add_argument("--keep-cache", action="store_true",
                        help="构建完成后保留 .buildcache（默认保留，方便重新构建）")
    args = parser.parse_args()

    os.makedirs(CACHE, exist_ok=True)
    log("== 1. 准备嵌入式 Python %s ==" % PYTHON_VERSION)
    embed_zip = download(EMBED_URL, os.path.join(CACHE,
                                                 "python-%s-embed-amd64.zip" % PYTHON_VERSION))

    log("== 2. 准备 PySide2 轮子 ==")
    wheels = fetch_wheels()
    for path in wheels:
        log("  %s" % os.path.basename(path))

    log("== 3. 展开到 %s ==" % TARGET)
    if os.path.isdir(TARGET):
        shutil.rmtree(TARGET, ignore_errors=True)
    os.makedirs(TARGET)
    unpack_zip(embed_zip, TARGET)

    site_packages = os.path.join(TARGET, "Lib", "site-packages")
    os.makedirs(site_packages, exist_ok=True)
    for path in wheels:
        unpack_zip(path, site_packages)

    log("== 4. 配置 python38._pth ==")
    with open(os.path.join(TARGET, "python38._pth"), "w", encoding="utf-8") as handle:
        handle.write(PTH_CONTENT)

    log("== 5. 精简无用 Qt 模块 ==")
    trim(site_packages)

    log("== 6. 复制 C++ 运行库 ==")
    log("  已复制 %d 个 DLL" % copy_crt(TARGET, site_packages))

    size = sum(os.path.getsize(os.path.join(root, name))
               for root, _dirs, files in os.walk(TARGET) for name in files)
    log("== 7. 验证 ==")
    ok = verify(os.path.join(TARGET, "python.exe"))
    log("")
    log("便携运行时: %s  (%.1f MB)" % (TARGET, size / 1048576))
    log("结果: %s" % ("成功 ✔" if ok else "失败 ✘"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
