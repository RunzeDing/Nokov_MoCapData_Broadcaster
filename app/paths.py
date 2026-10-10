"""Filesystem locations for source runs and for frozen (PyInstaller) runs.

Two layouts are supported:

* **installed/portable-free** - settings live in ``%APPDATA%\\NokovBroadcaster``.
* **portable** - drop an empty ``portable.flag`` next to the executable and all
  settings/logs are written to ``<exe dir>\\NokovBroadcasterData`` instead, so the
  whole thing can live on a USB stick.
"""

from __future__ import annotations

import os
import sys

from .version import APP_NAME

PORTABLE_FLAG = "portable.flag"
_DATA_SUBDIR = APP_NAME + "Data"


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def project_root() -> str:
    """Directory of the ``app`` package's parent (source tree root)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def bundle_dir() -> str:
    """Read-only resource root (``sys._MEIPASS`` when frozen)."""
    if is_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    return project_root()


def exe_dir() -> str:
    """Directory containing the executable (or the source tree when not frozen)."""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return project_root()


def is_portable() -> bool:
    return os.path.exists(os.path.join(exe_dir(), PORTABLE_FLAG))


def data_dir() -> str:
    """Writable directory for settings, profiles and logs."""
    if is_portable():
        path = os.path.join(exe_dir(), _DATA_SUBDIR)
    else:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def log_dir() -> str:
    path = os.path.join(data_dir(), "logs")
    os.makedirs(path, exist_ok=True)
    return path


def profiles_dir() -> str:
    path = os.path.join(data_dir(), "profiles")
    os.makedirs(path, exist_ok=True)
    return path


def config_path() -> str:
    return os.path.join(data_dir(), "config.json")


def sdk_package_dir() -> str:
    """Directory that must be importable so ``import nokov.nokovsdk`` works."""
    if is_frozen():
        return bundle_dir()
    return project_root()


def ensure_dirs() -> None:
    data_dir()
    log_dir()
    profiles_dir()
