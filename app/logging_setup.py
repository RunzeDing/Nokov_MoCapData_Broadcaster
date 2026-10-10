"""Logging configuration shared by the console, the log file and the GUI page.

A windowed (``--noconsole``) PyInstaller build has ``sys.stdout is None``, and
the vendor SDK prints during import, so :func:`ensure_std_streams` must run
before ``nokov.nokovsdk`` is imported.
"""

from __future__ import annotations

from .i18n import tr

import collections
import logging
import logging.handlers
import os
import sys
import threading
import time
from typing import Deque, List, NamedTuple, Optional

from .paths import log_dir
from .version import APP_NAME, __version__

MAX_ENTRIES = 4000


class LogEntry(NamedTuple):
    seq: int
    time_text: str
    level: str
    logger: str
    message: str

    @property
    def is_problem(self) -> bool:
        return self.level in ("WARNING", "ERROR", "CRITICAL")


class _NullStream:
    """Minimal text sink used when a windowed build has no console."""

    encoding = "utf-8"

    def write(self, text: str) -> int:
        return len(text)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False

    def reconfigure(self, **_kwargs) -> None:
        pass


def _attach_parent_console() -> None:
    """Reconnect stdout/stderr to the console that launched us, if there is one.

    A windowed (``--noconsole``) PyInstaller build has no standard handles, so
    ``--headless`` and ``--help`` would print into nothing when started from a
    terminal.  Attaching to the parent console makes them visible, while a plain
    double-click (no console to attach to) keeps the silent behaviour.
    """
    if os.name != "nt":
        return
    try:
        import ctypes

        ATTACH_PARENT_PROCESS = -1
        if not ctypes.windll.kernel32.AttachConsole(ATTACH_PARENT_PROCESS):
            return
        for name in ("stdout", "stderr"):
            try:
                setattr(sys, name, open("CONOUT$", "w", encoding="utf-8",
                                        buffering=1, errors="replace"))
            except OSError:
                continue
        try:
            sys.stdin = open("CONIN$", "r", encoding="utf-8", errors="replace")
        except (OSError, AttributeError):
            pass
    except Exception:  # pragma: no cover - never fail because of a console
        pass


def ensure_std_streams() -> None:
    """Guarantee that ``sys.stdout`` / ``sys.stderr`` exist and accept UTF-8."""
    if sys.stdout is None or sys.stderr is None:
        _attach_parent_console()
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            setattr(sys, name, _NullStream())
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            setattr(sys, name, _NullStream())


class QtLogBridge(logging.Handler):
    """Keeps recent records in memory so the GUI can poll them safely.

    Polling (rather than emitting Qt signals from arbitrary threads) keeps the
    log path free of Qt threading assumptions.
    """

    def __init__(self, capacity: int = MAX_ENTRIES) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._entries: Deque[LogEntry] = collections.deque(maxlen=capacity)
        self._seq = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
            if record.exc_info:
                message += "\n" + self.format(record)
        except Exception:  # pragma: no cover - never break logging
            return
        with self._lock:
            self._seq += 1
            self._entries.append(LogEntry(
                seq=self._seq,
                time_text=time.strftime("%H:%M:%S", time.localtime(record.created)),
                level=record.levelname,
                logger=record.name,
                message=message,
            ))

    def tail(self, after_seq: int = 0) -> List[LogEntry]:
        with self._lock:
            return [entry for entry in self._entries if entry.seq > after_seq]

    def latest_seq(self) -> int:
        with self._lock:
            return self._seq

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


BRIDGE = QtLogBridge()


class _Formatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record.short_name = record.name.replace("nokov.", "")
        return super().format(record)


def setup_logging(level: str = "INFO", to_file: bool = True,
                  console: bool = True) -> Optional[str]:
    """Configure the root logger.  Returns the log file path when writing one."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    numeric = getattr(logging, (level or "INFO").upper(), logging.INFO)
    root.setLevel(numeric)

    formatter = _Formatter(
        fmt="%(asctime)s %(levelname)-7s [%(short_name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    BRIDGE.setFormatter(formatter)
    BRIDGE.setLevel(numeric)
    root.addHandler(BRIDGE)

    log_path: Optional[str] = None
    if to_file:
        try:
            log_path = os.path.join(log_dir(), "nokov_broadcaster.log")
            file_handler = logging.handlers.RotatingFileHandler(
                log_path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(numeric)
            root.addHandler(file_handler)
        except OSError:
            log_path = None

    if console and not getattr(sys, "frozen", False):
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        stream_handler.setLevel(numeric)
        root.addHandler(stream_handler)

    logging.getLogger("nokov").info(
        tr("%s v%s 启动 (Python %s)"), APP_NAME, __version__,
        ".".join(str(part) for part in sys.version_info[:3]),
    )
    return log_path
