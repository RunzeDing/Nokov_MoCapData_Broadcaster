"""The worker thread: pull frame -> filter -> visualise data -> encode -> send."""

from __future__ import annotations

from ..i18n import tr

import logging
import threading
import time
from typing import Callable, Optional

from .broadcaster import UdpBroadcaster
from .formats import EncodeContext, get_format
from .hub import FrameHub
from .pipeline import Pipeline

log = logging.getLogger("nokov.engine")


class EngineStats:
    """Numbers the GUI polls a few times per second."""

    def __init__(self) -> None:
        self.frames_processed = 0
        self.frames_skipped_rate = 0
        self.fps = 0.0
        self.bodies = 0
        self.encode_ms = 0.0
        self.packets_sent = 0
        self.bytes_sent = 0
        self.send_errors = 0
        self.last_packet_size = 0
        self.last_packet_hex = ""
        self.last_error = ""
        self.broadcasting = False
        self.format_name = ""
        self._last_frame_time = 0.0

    def note_frame(self, now: float) -> None:
        if self._last_frame_time > 0.0:
            delta = now - self._last_frame_time
            if 1e-5 < delta < 2.0:
                instant = 1.0 / delta
                self.fps = instant if self.fps <= 0.0 else (self.fps * 0.9 + instant * 0.1)
        self._last_frame_time = now
        self.frames_processed += 1


class Engine(threading.Thread):
    """Runs for the whole application lifetime; idles when nothing arrives."""

    def __init__(self, hub: FrameHub, config_provider: Callable[[], object],
                 broadcaster: Optional[UdpBroadcaster] = None) -> None:
        super().__init__(name="nokov-engine", daemon=True)
        self._hub = hub
        self._config_provider = config_provider
        self.broadcaster = broadcaster or UdpBroadcaster()
        self.pipeline = Pipeline(config_provider())
        self.stats = EngineStats()

        self._stop_event = threading.Event()
        self._broadcast_enabled = threading.Event()
        self._last_seq = 0
        self._next_send_at = 0.0
        self._packet_index = 0
        self._last_config_signature = None

    # ------------------------------------------------------------------ #
    # control
    # ------------------------------------------------------------------ #
    def start_broadcasting(self) -> None:
        self._next_send_at = 0.0
        self._broadcast_enabled.set()
        self.stats.broadcasting = True

    def stop_broadcasting(self) -> None:
        self._broadcast_enabled.clear()
        self.stats.broadcasting = False

    @property
    def broadcasting(self) -> bool:
        return self._broadcast_enabled.is_set()

    def stop(self) -> None:
        self._stop_event.set()
        self._broadcast_enabled.clear()
        self._hub.wake()

    def shutdown(self) -> None:
        self.stop()
        if self.is_alive():
            self.join(timeout=2.0)
        self.broadcaster.close()

    def apply_broadcast_config(self) -> None:
        """Push the current target list into the socket (called on config change)."""
        try:
            self.broadcaster.configure(self._config_provider().broadcast)
        except Exception as exc:  # pragma: no cover - defensive
            log.error(tr("配置 UDP 目标失败: %r"), exc)

    def reset_pipeline(self) -> None:
        self.pipeline.reset()

    # ------------------------------------------------------------------ #
    def run(self) -> None:
        log.info(tr("处理线程已启动"))
        self.apply_broadcast_config()
        while not self._stop_event.is_set():
            seq, raw = self._hub.take_raw(self._last_seq, timeout=0.05)
            if raw is None:
                continue
            self._last_seq = seq

            config = self._config_provider()
            try:
                processed, _lost = self.pipeline.process(raw)
            except Exception as exc:  # pragma: no cover - defensive
                self.stats.last_error = tr("处理帧失败: %r") % (exc,)
                log.exception(tr("处理帧失败"))
                continue

            self._hub.publish_processed(processed)
            self._hub.record_history(processed)
            self.stats.note_frame(time.perf_counter())
            self.stats.bodies = len(processed.bodies)

            try:
                self._maybe_send(config, processed)
            except Exception as exc:  # pragma: no cover - defensive
                self.stats.last_error = tr("编码/发送失败: %r") % (exc,)
                log.exception(tr("编码或发送失败"))

        log.info(tr("处理线程已退出"))

    # ------------------------------------------------------------------ #
    def _maybe_send(self, config, processed) -> None:
        self.stats.broadcasting = self._broadcast_enabled.is_set()
        if not self._broadcast_enabled.is_set():
            return

        broadcast = config.broadcast
        if not processed.bodies and not broadcast.send_when_empty:
            return

        now = time.perf_counter()
        rate = float(broadcast.max_rate_hz or 0.0)
        if rate > 0.0:
            period = 1.0 / rate
            if self._next_send_at and now < self._next_send_at:
                self.stats.frames_skipped_rate += 1
                return
            self._next_send_at = now + period

        encoder = get_format(broadcast.format_id)
        params = encoder.normalize_params(broadcast.params_for(broadcast.format_id))
        self.stats.format_name = encoder.name

        started = time.perf_counter()
        context = EncodeContext(
            fps=self.stats.fps,
            packet_index=self._packet_index,
            now=now,
            source_ip=broadcast.source_ip or "",
        )
        data = encoder.encode(processed, params, context)
        self.stats.encode_ms = (time.perf_counter() - started) * 1000.0
        self._packet_index += 1

        if not data:
            return
        if len(data) > 65507:
            self.stats.last_error = (
                tr("报文长度 %d 字节超过 UDP 上限 65507，已截断到前 65507 字节；"
                "请减少刚体数量或字段。") % len(data)
            )
            log.warning(self.stats.last_error)
            data = data[:65507]

        delivered = self.broadcaster.send(data)
        self.stats.last_packet_size = len(data)
        self.stats.last_packet_hex = data[:32].hex(" ").upper()
        if delivered:
            self.stats.packets_sent += 1
            self.stats.bytes_sent += len(data)
            if self.stats.send_errors:
                self.stats.last_error = self.broadcaster.stats.last_error
        else:
            self.stats.send_errors += 1
            self.stats.last_error = self.broadcaster.stats.last_error or tr("没有可用的 UDP 目标")
