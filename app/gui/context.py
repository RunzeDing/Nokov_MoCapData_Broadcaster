"""Shared application state handed to every page."""

from __future__ import annotations

from ..i18n import tr

import logging
import time
from typing import Optional

from PySide2.QtCore import QObject, Signal

from ..config import AppConfig
from ..core.broadcaster import UdpBroadcaster
from ..core.engine import Engine
from ..core.hub import FrameHub
from ..core.sdk_client import MocapSession
from ..core.simulator import SimulatedSource
from ..logging_setup import BRIDGE, QtLogBridge

log = logging.getLogger("nokov.app")


class AppContext(QObject):
    """Owns the long-lived objects: config, hub, engine, SDK session, simulator."""

    #: Emitted when the whole configuration was replaced (profile load / reset)
    #: so every page can re-read its widgets.
    configReloaded = Signal()

    #: Emitted when a page asks for a different interface language.
    languageChangeRequested = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.config = AppConfig.load()
        self.hub = FrameHub(
            trail_length=self.config.ui.trail_length,
            series_capacity=self.config.ui.plot_points,
        )
        self.broadcaster = UdpBroadcaster()
        self.engine = Engine(self.hub, self.config_provider, self.broadcaster)
        self.session = MocapSession(self.hub)
        self.simulator: Optional[SimulatedSource] = None
        self.log_bridge: QtLogBridge = BRIDGE
        self.started_at = time.monotonic()

        #: set to False when command line overrides were applied, so the GUI
        #: never writes throw-away settings back to config.json
        self.persist_config = True

        #: last packet actually put on the wire (for the preview panel)
        self.last_packet: bytes = b""
        self.last_packet_time = 0.0

    # ------------------------------------------------------------------ #
    def config_provider(self) -> AppConfig:
        return self.config

    # ------------------------------------------------------------------ #
    def start_background(self) -> None:
        self.engine.apply_broadcast_config()
        self.engine.start()

    def shutdown(self) -> None:
        self.stop_simulator()
        if self.session.is_running:
            self.session.disconnect()
        self.engine.shutdown()
        self.session.shutdown()
        if not self.persist_config:
            log.info(tr("本次运行使用了命令行参数，配置未写回 config.json"))
            return
        try:
            self.config.save()
        except OSError as exc:
            log.warning(tr("保存配置失败: %s"), exc)

    # ------------------------------------------------------------------ #
    # config plumbing
    # ------------------------------------------------------------------ #
    def config_changed(self) -> None:
        """Called by any page after it modified :attr:`config`."""
        self.hub.set_limits(self.config.ui.trail_length, self.config.ui.plot_points)
        self.engine.apply_broadcast_config()
        self.session.capture_markers = bool(self.config.ui.show_markers)

    def save_config(self) -> str:
        return self.config.save()

    def request_pages_reload(self) -> None:
        """Ask every page to re-read the configuration into its widgets."""
        self.configReloaded.emit()

    # ------------------------------------------------------------------ #
    # data sources
    # ------------------------------------------------------------------ #
    def start_simulator(self, body_count: int = 4, rate_hz: float = 120.0) -> None:
        self.stop_simulator()
        self.simulator = SimulatedSource(self.hub, body_count=body_count, rate_hz=rate_hz,
                                         noise_mm=1.5, glitch_every=500)
        self.simulator.start()
        log.info(tr("模拟数据源已启动: %d 个刚体 @ %.0f Hz"), body_count, rate_hz)

    def stop_simulator(self) -> None:
        if self.simulator is not None:
            self.simulator.stop()
            self.simulator.join(timeout=1.0)
            self.simulator = None
            log.info(tr("模拟数据源已停止"))

    @property
    def simulator_running(self) -> bool:
        return self.simulator is not None and self.simulator.is_alive()
