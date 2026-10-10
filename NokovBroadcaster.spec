# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification for NokovBroadcaster.

Build with::

    powershell -ExecutionPolicy Bypass -File build.ps1

Set ``NB_CONSOLE=1`` in the environment to build a console variant that prints
startup errors to a terminal (handy when troubleshooting a machine that has no
log file yet).
"""

import os
import sys

from PyInstaller.utils.hooks import collect_submodules, get_package_paths

PROJECT_DIR = os.path.abspath(os.path.join(SPECPATH))
ASSETS_DIR = os.path.join(PROJECT_DIR, "assets")
NOKOV_DIR = os.path.join(PROJECT_DIR, "nokov")

CONSOLE = os.environ.get("NB_CONSOLE", "") == "1"

# --------------------------------------------------------------------------- #
# bundled data
# --------------------------------------------------------------------------- #
datas = []
icon_path = os.path.join(ASSETS_DIR, "icon.ico")
if os.path.exists(icon_path):
    datas.append((icon_path, "assets"))

# The vendor SDK loads its native library relative to nokov/nokovsdk.py, so the
# DLL has to keep that exact relative location inside the bundle.
sdk_dll = os.path.join(NOKOV_DIR, "lib", "nokov_sdk.dll")
if not os.path.exists(sdk_dll):
    raise SystemExit(
        "找不到 Nokov SDK: %s\n请确认 nokov\\lib\\nokov_sdk.dll 存在。" % sdk_dll
    )
datas.append((sdk_dll, os.path.join("nokov", "lib")))

# --------------------------------------------------------------------------- #
# Visual C++ runtime, copied to the *root* of the bundle.
#
# nokov_sdk.dll imports MSVCP140 / VCRUNTIME140 / VCRUNTIME140_1.  PyInstaller
# normally only ships VCRUNTIME140.dll at the root and leaves MSVCP140.dll
# inside PySide2\ / shiboken2\, which happens to work here only because PySide2
# is imported first.  Putting a consistent set at the root makes the SDK load
# unconditionally, so the target machine does not need the VC++ redistributable
# installed.  (The Windows UCRT itself is part of Windows 10/11.)
# --------------------------------------------------------------------------- #
CRT_NAMES = (
    "MSVCP140.dll",
    "MSVCP140_1.dll",
    "MSVCP140_2.dll",
    "MSVCP140_codecvt_ids.dll",
    "VCRUNTIME140.dll",
    "VCRUNTIME140_1.dll",
    "concrt140.dll",
    "vccorlib140.dll",
)
try:
    # get_package_paths returns (base_dir, package_dir); we want the package dir
    _shiboken_dir = get_package_paths("shiboken2")[1]
except Exception:  # pragma: no cover - very old/new PyInstaller
    _shiboken_dir = os.path.join(os.path.dirname(sys.executable), "Lib", "site-packages",
                                 "shiboken2")

binaries = []
for _name in CRT_NAMES:
    _path = os.path.join(_shiboken_dir, _name)
    if os.path.exists(_path):
        binaries.append((_path, "."))
    else:
        print("WARNING: 未找到 CRT 运行库 %s（位于 %s），目标机可能需要安装 VC++ 运行库"
              % (_name, _shiboken_dir))
print("已内置 %d 个 C++ 运行库到 exe 根目录: %s"
      % (len(binaries), ", ".join(os.path.basename(path) for path, _dest in binaries)))

hiddenimports = ["nokov.nokovsdk"]

# --------------------------------------------------------------------------- #
# keep the bundle small: none of these Qt modules are used by the GUI
# --------------------------------------------------------------------------- #
EXCLUDED_QT = [
    "PySide2.Qt3DAnimation", "PySide2.Qt3DCore", "PySide2.Qt3DExtras",
    "PySide2.Qt3DInput", "PySide2.Qt3DLogic", "PySide2.Qt3DRender",
    "PySide2.QtBluetooth", "PySide2.QtCharts", "PySide2.QtDataVisualization",
    "PySide2.QtDesigner", "PySide2.QtHelp", "PySide2.QtLocation",
    "PySide2.QtMultimedia", "PySide2.QtMultimediaWidgets", "PySide2.QtNfc",
    "PySide2.QtOpenGL", "PySide2.QtPositioning", "PySide2.QtPrintSupport",
    "PySide2.QtQml", "PySide2.QtQuick", "PySide2.QtQuickControls2",
    "PySide2.QtQuickWidgets", "PySide2.QtRemoteObjects", "PySide2.QtScript",
    "PySide2.QtScriptTools", "PySide2.QtScxml", "PySide2.QtSensors",
    "PySide2.QtSerialPort", "PySide2.QtSql", "PySide2.QtStateMachine",
    "PySide2.QtSvg", "PySide2.QtTest", "PySide2.QtTextToSpeech",
    "PySide2.QtUiTools", "PySide2.QtWebChannel", "PySide2.QtWebEngine",
    "PySide2.QtWebEngineCore", "PySide2.QtWebEngineWidgets", "PySide2.QtWebSockets",
    "PySide2.QtWinExtras", "PySide2.QtXml", "PySide2.QtXmlPatterns",
    "PySide2.QtNetworkAuth", "PySide2.QtConcurrent",
]

excludes = EXCLUDED_QT + [
    # the broadcaster is deliberately dependency-free apart from PySide2
    "numpy", "scipy", "matplotlib", "pandas", "PIL", "cv2",
    "tkinter", "test", "unittest", "pydoc_data", "lib2to3",
    "IPython", "notebook", "setuptools", "pip", "wheel",
    "PyInstaller", "pytest", "sqlite3", "pdb", "doctest",
]

a = Analysis(
    [os.path.join(PROJECT_DIR, "NokovBroadcaster.py")],
    pathex=[PROJECT_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="NokovBroadcaster",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=CONSOLE,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path if os.path.exists(icon_path) else None,
)
