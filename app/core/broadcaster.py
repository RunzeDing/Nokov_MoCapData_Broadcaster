"""UDP output with multiple targets and per-target statistics."""

from __future__ import annotations

from ..i18n import tr

import socket
import threading
import time
from typing import Dict, List, Optional, Tuple

from ..config import BroadcastConfig, BroadcastTarget

#: Winsock error code -> Chinese source description
_ERROR_NAMES = {
    10013: "权限不足或地址不可用",
    10047: "地址族不支持",
    10049: "本机不存在该地址 (请检查本机 IP 设置)",
    10050: "网络不可达",
    10051: "目标网络不可达",
    10054: "连接被对端重置",
    10057: "套接字未连接",
    10060: "连接超时",
    10061: "目标拒绝连接",
    10064: "目标主机已关闭",
    10065: "目标主机不可达",
}


def error_name(code) -> str:
    """Localised description of a Winsock error code ('' when unknown)."""
    return tr(_ERROR_NAMES.get(code, ""))


class TargetStats:
    __slots__ = ("ip", "port", "packets", "bytes", "errors", "last_error", "last_error_at")

    def __init__(self, ip: str, port: int) -> None:
        self.ip = ip
        self.port = port
        self.packets = 0
        self.bytes = 0
        self.errors = 0
        self.last_error = ""
        self.last_error_at = 0.0

    @property
    def label(self) -> str:
        return "%s:%d" % (self.ip, self.port)


class BroadcastStats:
    """Snapshot of the sending side, refreshed by :class:`UdpBroadcaster`."""

    def __init__(self) -> None:
        self.packets_sent = 0
        self.bytes_sent = 0
        self.send_errors = 0
        self.last_packet_size = 0
        self.last_packet_hex = ""
        self.last_error = ""
        self.last_send_at = 0.0
        self.rate_hz = 0.0
        self.throughput_bps = 0.0
        self._window_start = 0.0
        self._window_packets = 0
        self._window_bytes = 0

    def reset(self) -> None:
        self.__init__()


class UdpBroadcaster:
    """Owns one sending socket and fans a packet out to every enabled target."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._socket: Optional[socket.socket] = None
        self._targets: List[Tuple[str, int]] = []
        self._bind_ip = ""
        self.stats = BroadcastStats()
        self._target_stats: Dict[str, TargetStats] = {}
        self._broadcast_enabled = True
        self._resolved: Dict[str, Tuple[str, int]] = {}

    # ------------------------------------------------------------------ #
    def configure(self, config: BroadcastConfig) -> None:
        """Apply new targets / bind address, recreating the socket if needed."""
        targets: List[Tuple[str, int]] = []
        labels: Dict[str, TargetStats] = {}
        for target in config.targets:
            if not isinstance(target, BroadcastTarget) or not target.enabled:
                continue
            ip = (target.ip or "").strip()
            if not ip:
                continue
            try:
                port = int(target.port)
            except (TypeError, ValueError):
                continue
            if not 0 < port < 65536:
                continue
            key = "%s:%d" % (ip, port)
            if key in labels:
                continue
            labels[key] = TargetStats(ip, port)
            targets.append((ip, port))

        bind_ip = (config.source_ip or "").strip()
        with self._lock:
            needs_new_socket = (
                self._socket is None
                or bind_ip != self._bind_ip
            )
            self._targets = targets
            self._target_stats = labels
            if needs_new_socket:
                self._close_locked()
                self._bind_ip = bind_ip
                self._open_locked()

    def _open_locked(self) -> None:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1 << 20)
            except OSError:
                pass
            if self._bind_ip:
                sock.bind((self._bind_ip, 0))
            sock.settimeout(0.0)
            self._socket = sock
        except OSError as exc:
            self._socket = None
            self.stats.last_error = tr("创建发送套接字失败: %s") % exc

    def _close_locked(self) -> None:
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None

    def close(self) -> None:
        with self._lock:
            self._close_locked()

    # ------------------------------------------------------------------ #
    @property
    def targets(self) -> List[Tuple[str, int]]:
        with self._lock:
            return list(self._targets)

    @property
    def is_open(self) -> bool:
        with self._lock:
            return self._socket is not None

    def target_stats(self) -> List[TargetStats]:
        with self._lock:
            return list(self._target_stats.values())

    # ------------------------------------------------------------------ #
    def send(self, data: bytes) -> bool:
        """Send ``data`` to every target.  Returns True when at least one succeeded."""
        if not data:
            return False
        with self._lock:
            sock = self._socket
            targets = list(self._targets)
            stats = self.stats
            per_target = self._target_stats
        if sock is None or not targets:
            return False

        delivered = False
        now = time.monotonic()
        for ip, port in targets:
            try:
                sent = sock.sendto(data, (ip, port))
            except OSError as exc:
                code = getattr(exc, "winerror", None) or exc.errno
                message = error_name(code)
                text = "%s%s" % (exc, (" (%s)" % message) if message else "")
                entry = per_target.get("%s:%d" % (ip, port))
                if entry is not None:
                    entry.errors += 1
                    entry.last_error = text
                    entry.last_error_at = now
                stats.send_errors += 1
                stats.last_error = "%s:%d %s" % (ip, port, text)
                continue
            delivered = True
            stats.packets_sent += 1
            stats.bytes_sent += sent
            stats._window_packets += 1
            stats._window_bytes += sent
            entry = per_target.get("%s:%d" % (ip, port))
            if entry is not None:
                entry.packets += 1
                entry.bytes += sent

        stats.last_packet_size = len(data)
        stats.last_packet_hex = data[:32].hex(" ").upper()
        stats.last_send_at = now

        if stats._window_start <= 0.0:
            stats._window_start = now
        elapsed = now - stats._window_start
        if elapsed >= 0.5:
            stats.rate_hz = stats._window_packets / elapsed
            stats.throughput_bps = stats._window_bytes / elapsed
            stats._window_start = now
            stats._window_packets = 0
            stats._window_bytes = 0
        return delivered
