"""Nokov SDK session management.

This module is the only place that talks to the vendor SDK.  It

* imports the vendored ``nokov`` package (bundled next to the executable so no
  ``pip install`` is ever required),
* creates one long-lived :class:`PySDKClient` instance,
* copies each incoming frame into plain Python objects and publishes it to the
  :class:`~app.core.hub.FrameHub`,
* parses the server description and the data descriptions (rigid body names,
  frame rate, marker sets).
"""

from __future__ import annotations

from ..i18n import tr

import gc
import logging
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from ..config import NetworkConfig
from ..paths import sdk_package_dir
from .frames import BodyState, FrameSnapshot
from .hub import FrameHub

log = logging.getLogger("nokov.sdk")

SDK_IMPORT_ERROR: Optional[str] = None
nokovsdk: Any = None
_QUIET_CLIENT_CLASS: Any = None


def load_sdk() -> Tuple[bool, str]:
    """Import the vendored SDK.  Returns ``(ok, message)``.

    The vendor module prints to stdout at import time, so a windowed build with
    no console must have ``sys.stdout`` replaced before this runs (see
    :mod:`app.logging_setup`).
    """
    global nokovsdk, SDK_IMPORT_ERROR
    if nokovsdk is not None:
        return True, tr("已加载")
    if SDK_IMPORT_ERROR is not None:
        return False, SDK_IMPORT_ERROR

    package_dir = sdk_package_dir()
    if package_dir not in sys.path:
        sys.path.insert(0, package_dir)
    try:
        import nokov.nokovsdk as module  # type: ignore
        nokovsdk = module
        version = module.PySDKClient.__module__
        log.info(tr("Nokov SDK 已加载 (%s)"), version)
        return True, tr("已加载")
    except OSError as exc:
        SDK_IMPORT_ERROR = (
            tr("加载 nokov_sdk.dll 失败: %s\n"
            "请确认已安装 Microsoft Visual C++ 运行库 (SDK 包内附 VC_redist.x64.exe)，"
            "并且系统为 64 位。") % exc
        )
    except Exception as exc:  # pragma: no cover - defensive
        SDK_IMPORT_ERROR = tr("导入 Nokov SDK 失败: %r") % (exc,)
    log.error(SDK_IMPORT_ERROR)
    return False, SDK_IMPORT_ERROR


#: initialize() return codes -> Chinese source text
_INIT_ERROR_TEXT = {
    0: "成功",
    1: "内部错误 (ErrorCode_Internal)",
    2: "外部错误 (ErrorCode_External)",
    3: "网络错误 (ErrorCode_Network)：请检查服务器 IP / 网线 / 防火墙",
    4: "其它错误 (ErrorCode_Other)",
}

#: extra codes the vendor DLL can return that are not in its own ErrorCode enum
_EXTRA_ERROR_TEXT = {
    15: "无法与服务器建立连接：请确认服务器 IP 正确、动捕软件已启动、网络可达",
    16: "连接超时",
}


def describe_init_error(code: int) -> str:
    """Localised explanation of an ``Initialize`` return code."""
    text = _INIT_ERROR_TEXT.get(code) or _EXTRA_ERROR_TEXT.get(code) or "未知错误码"
    return tr(text)


def client_class():
    """Return a ``PySDKClient`` subclass whose ``__del__`` is neutralised.

    The vendor class keeps its handle in a **class** attribute and destroys it
    from ``__del__``.  Destroying explicitly and then letting ``__del__`` run
    calls ``DestroyClient`` twice on the same pointer, which Windows reports as
    ``STATUS_HEAP_CORRUPTION`` (0xC0000374) while the process exits.  We therefore
    take full ownership of the lifetime and destroy the client exactly once, in
    :meth:`MocapSession._destroy_client`.
    """
    global _QUIET_CLIENT_CLASS
    if _QUIET_CLIENT_CLASS is None:
        class _QuietSDKClient(nokovsdk.PySDKClient):  # type: ignore[misc]
            def __del__(self) -> None:  # noqa: D401 - deliberately a no-op
                pass

        _QUIET_CLIENT_CLASS = _QuietSDKClient
    return _QUIET_CLIENT_CLASS

#: iTimeStamp -> seconds multipliers tried by the auto detector, in order.
_TIMESTAMP_SCALES = (
    ("ns", 1e-9),
    ("us", 1e-6),
    ("ms", 1e-3),
    ("s", 1.0),
)


class SessionInfo:
    """Everything we learned about the server we are (or were) connected to."""

    def __init__(self) -> None:
        self.sdk_version = ""
        self.server_name = ""
        self.server_address = ""
        self.server_app = ""
        self.server_app_version = ""
        self.frame_rate = 0
        self.rigid_bodies: Dict[int, str] = {}
        self.marker_sets: List[str] = []
        self.skeletons: List[str] = []
        self.analog_channels: List[str] = []
        self.force_plates = 0
        self.timestamp_unit = "auto"

    def rigid_body_names(self) -> Dict[int, str]:
        return dict(self.rigid_bodies)


class MocapSession:
    """Owns the SDK client and, while connected, the frame-producing thread."""

    def __init__(self, hub: FrameHub) -> None:
        self._hub = hub
        self._client: Any = None
        self._lock = threading.RLock()
        self._running = False
        self._poll_thread: Optional[threading.Thread] = None
        self._network = NetworkConfig()
        self.info = SessionInfo()

        self._last_frame_no: Optional[int] = None
        self._ts_scale: Optional[float] = None
        self._prev_raw_ts: Optional[int] = None
        self._perf_base = time.perf_counter()
        self._ts_samples = 0

        self.frames_received = 0
        self.duplicate_frames = 0
        self.build_errors = 0
        self.last_error = ""
        self.connected_at = 0.0
        self.last_frame_at = 0.0
        self._connect_count = 0

        #: toggled by the GUI; capturing markers costs extra per-frame work
        self.capture_markers = False

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #
    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def client(self):
        return self._client

    def connect(self, network: NetworkConfig) -> Tuple[bool, str]:
        """Initialise the SDK and start receiving frames."""
        with self._lock:
            if self._running:
                return True, tr("已经在运行")
            ok, message = load_sdk()
            if not ok:
                return False, message

            self._network = network
            self._reset_frame_state()
            self.info = SessionInfo()

            if self._client is None:
                try:
                    # NOTE: PySDKClient stores its handle as a *class* attribute,
                    # so creating a second instance while an old one is still
                    # alive would corrupt the first.  We therefore create exactly
                    # one client for the whole application lifetime and only
                    # Initialise/Uninitialize it.  See client_class().
                    self._client = client_class()()
                except Exception as exc:
                    return False, tr("创建 SDK 客户端失败: %r") % (exc,)

            try:
                version = self._client.PyNokovVersion()
                self.info.sdk_version = "%d.%d.%d.%d" % (
                    version[0], version[1], version[2], version[3],
                )
            except Exception:
                self.info.sdk_version = tr("未知")

            self._client.PySetVerbosityLevel(0)
            self._client.PySetMessageCallback(_sdk_message)
            self._client.PySetNotifyMsgCallback(_sdk_notify, None)

            server_ip = (network.server_ip or "").strip()
            if not server_ip:
                return False, tr("请先填写动捕服务器 IP 地址")
            try:
                ret = self._client.Initialize(server_ip.encode("utf-8"))
            except Exception as exc:
                return False, tr("调用 SDK Initialize 失败: %r") % (exc,)

            if ret != 0 and self._connect_count > 0:
                # The SDK client does not always survive an Uninitialize ->
                # Initialize cycle; rebuild it once and retry.
                log.info(tr("重新连接返回 %d，重建 SDK 客户端后重试"), ret)
                self._destroy_client()
                try:
                    self._client = client_class()()
                    self._client.PySetVerbosityLevel(0)
                    self._client.PySetMessageCallback(_sdk_message)
                    self._client.PySetNotifyMsgCallback(_sdk_notify, None)
                    ret = self._client.Initialize(server_ip.encode("utf-8"))
                except Exception as exc:
                    return False, tr("重建 SDK 客户端失败: %r") % (exc,)

            self._connect_count += 1
            if ret != 0:
                return False, tr("连接失败 [%d] %s") % (ret, describe_init_error(ret))

            self._read_server_description()
            self._read_data_descriptions()

            self._running = True
            if (network.receive_mode or "callback").lower() == "poll":
                self._poll_thread = threading.Thread(
                    target=self._poll_loop, name="nokov-poll", daemon=True
                )
                self._poll_thread.start()
            else:
                try:
                    self._client.PySetDataCallback(self._on_data, None)
                except Exception as exc:
                    self._running = False
                    return False, tr("注册数据回调失败: %r") % (exc,)

            self.connected_at = time.monotonic()
            self.last_frame_at = 0.0
            mode = tr("主动读取") if (network.receive_mode or "").lower() == "poll" else tr("回调")
            return True, tr("已连接 (%s模式)，等待数据…") % mode

    def disconnect(self) -> None:
        with self._lock:
            was_running = self._running
            self._running = False
            if self._poll_thread is not None:
                self._poll_thread.join(timeout=1.0)
                self._poll_thread = None
            if self._client is not None and was_running:
                try:
                    self._client._PySDKClient__Uninitialize()  # type: ignore[attr-defined]
                except Exception:
                    try:
                        self._client.Uninitialize()
                    except Exception:
                        pass
            self._hub.wake()

    def _destroy_client(self) -> None:
        """Release the SDK client exactly once, at application exit.

        ``client_class()`` disabled the vendor ``__del__`` so this is the only
        place that calls ``DestroyClient``; calling it twice corrupts the heap.
        """
        client = self._client
        self._client = None
        if client is None:
            return
        try:
            client._PySDKClient__Uninitialize()  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            client._PySDKClient__DestroyClient()  # type: ignore[attr-defined]
        except Exception:
            pass
        del client
        gc.collect()

    def shutdown(self) -> None:
        self.disconnect()
        self._destroy_client()

    # ------------------------------------------------------------------ #
    # frame production
    # ------------------------------------------------------------------ #
    def _reset_frame_state(self) -> None:
        self._last_frame_no = None
        self._prev_raw_ts = None
        self._ts_samples = 0
        self._perf_base = time.perf_counter()
        unit = (self._network.timestamp_unit or "auto").lower()
        self._ts_scale = None
        if unit != "auto":
            for name, scale in _TIMESTAMP_SCALES:
                if name == unit:
                    self._ts_scale = scale
                    break

    def _poll_loop(self) -> None:
        client = self._client
        while self._running:
            frame = None
            try:
                frame = client.PyGetLastFrameOfMocapData()
            except Exception as exc:  # pragma: no cover - defensive
                self.last_error = tr("读取帧失败: %r") % (exc,)
                time.sleep(0.05)
                continue
            if not frame:
                time.sleep(0.001)
                continue
            try:
                self._handle_frame(frame)
            finally:
                try:
                    client.PyNokovFreeFrame(frame)
                except Exception:
                    pass

    # ctypes callback signature: (POINTER(FrameOfMocapData), c_void_p)
    def _on_data(self, pFrameOfMocapData, pUserData) -> None:
        if not self._running:
            return
        try:
            self._handle_frame(pFrameOfMocapData)
        except Exception as exc:  # pragma: no cover - defensive
            self.build_errors += 1
            self.last_error = tr("解析帧失败: %r") % (exc,)

    def _handle_frame(self, pFrame) -> None:
        if pFrame is None:
            return
        frame = self._build_frame(pFrame)
        if frame is not None:
            self.frames_received += 1
            self.last_frame_at = time.monotonic()
            self._hub.publish_raw(frame)

    # ------------------------------------------------------------------ #
    def _timestamp_seconds(self, raw_ts: int) -> float:
        """Best-effort conversion of the server timestamp to seconds.

        Only used for the informational ``sdk_timestamp`` field: all internal
        timing uses the monotonic clock (see :meth:`_monotonic_seconds`).
        """
        if self._ts_scale is None:
            if self._prev_raw_ts is not None:
                delta = raw_ts - self._prev_raw_ts
                if delta > 0:
                    for name, scale in _TIMESTAMP_SCALES:
                        seconds = delta * scale
                        if 0.0002 <= seconds <= 0.5:
                            self._ts_scale = scale
                            self.info.timestamp_unit = name
                            log.info(tr("自动识别服务器时间戳单位: %s"), name)
                            break
            self._prev_raw_ts = raw_ts
            if self._ts_scale is None:
                return 0.0
        return float(raw_ts) * self._ts_scale

    def _monotonic_seconds(self) -> float:
        return time.perf_counter() - self._perf_base

    def _build_frame(self, pFrame) -> Optional[FrameSnapshot]:
        frame_data = pFrame.contents
        frame_no = int(frame_data.iFrame)

        # Legacy behaviour: ignore repeated frame numbers.
        if self._last_frame_no is not None and frame_no == self._last_frame_no:
            self.duplicate_frames += 1
            return None
        self._last_frame_no = frame_no

        raw_ts = int(frame_data.iTimeStamp)
        snapshot = FrameSnapshot(frame_no, self._monotonic_seconds())
        snapshot.raw_timestamp = raw_ts
        snapshot.sdk_timestamp = self._timestamp_seconds(raw_ts)
        snapshot.received_at = time.monotonic()
        snapshot.latency = float(getattr(frame_data, "fLatency", 0.0) or 0.0)

        # --- extended (velocity / acceleration / euler) data --------------- #
        extend = None
        if self._network.read_extend_data:
            extend = self._find_rigid_body_extend(frame_data)

        count = int(frame_data.nRigidBodies)
        if count < 0:
            count = 0
        max_bodies = len(frame_data.RigidBodies)
        if count > max_bodies:
            count = max_bodies

        for index in range(count):
            body = frame_data.RigidBodies[index]
            state = BodyState(int(body.ID), self.info.rigid_bodies.get(int(body.ID), ""))
            state.raw_x = float(body.x)
            state.raw_y = float(body.y)
            state.raw_z = float(body.z)
            state.x = state.raw_x / 1000.0
            state.y = state.raw_y / 1000.0
            state.z = state.raw_z / 1000.0
            state.qx = float(body.qx)
            state.qy = float(body.qy)
            state.qz = float(body.qz)
            state.qw = float(body.qw)
            state.n_markers = int(body.nMarkers)
            state.mean_error = float(body.MeanError)
            state.params = int(body.params)

            if extend is not None and index < extend.number:
                ext = extend.ExtendDataUnion.RigidBodyExtendData[index]
                state.has_extend = True
                # SDK reports velocities in mm/s and angles in degrees
                state.vx = float(ext.xVel) / 1000.0
                state.vy = float(ext.yVel) / 1000.0
                state.vz = float(ext.zVel) / 1000.0
                state.ax = float(ext.xAvel) / 1000.0
                state.ay = float(ext.yAvel) / 1000.0
                state.az = float(ext.zAvel) / 1000.0
                state.roll = float(ext.roll)
                state.pitch = float(ext.pitch)
                state.yaw = float(ext.yaw)

            if self.capture_markers and state.n_markers > 0:
                markers = []
                marker_ids = []
                try:
                    for marker_index in range(min(state.n_markers, 32)):
                        marker = body.Markers[marker_index]
                        markers.append((float(marker[0]), float(marker[1]), float(marker[2])))
                        marker_ids.append(int(body.MarkerIDs[marker_index]))
                except Exception:
                    pass
                state.markers = tuple(markers)
                state.marker_ids = tuple(marker_ids)

            snapshot.bodies[state.body_id] = state

        # --- analog ------------------------------------------------------- #
        analog_count = int(frame_data.nAnalogdatas)
        if analog_count > 0:
            analog_count = min(analog_count, len(frame_data.Analogdata))
            snapshot.analog = [float(frame_data.Analogdata[i]) for i in range(analog_count)]

        return snapshot

    @staticmethod
    def _find_rigid_body_extend(frame_data):
        try:
            extend_data = frame_data.FrameExtendData
            wanted = nokovsdk.ExtendDataType.ExtendDataRigidBody.value
            for index in range(int(extend_data.nExtendDataNum)):
                item = extend_data.extendData[index]
                if item.type == wanted:
                    return item
        except Exception:
            return None
        return None

    # ------------------------------------------------------------------ #
    # descriptions
    # ------------------------------------------------------------------ #
    def _read_server_description(self) -> None:
        client = self._client
        try:
            description = nokovsdk.ServerDescription()
            client.PyGetServerDescription(description)
        except Exception as exc:
            log.debug(tr("读取服务器描述失败: %r"), exc)
            return
        try:
            self.info.server_name = _decode(description.szHostComputerName)
            self.info.server_app = _decode(description.szHostApp)
            address = description.HostComputerAddress
            self.info.server_address = ".".join(str(int(part)) for part in address)
            version = description.HostAppVersion
            self.info.server_app_version = "%d.%d.%d.%d" % (
                version[0], version[1], version[2], version[3],
            )
        except Exception as exc:
            log.debug(tr("解析服务器描述失败: %r"), exc)

    def _read_data_descriptions(self) -> None:
        client = self._client
        try:
            pointer = nokovsdk.POINTER(nokovsdk.DataDescriptions)()
            client.PyGetDataDescriptions(pointer)
        except Exception as exc:
            log.debug(tr("读取数据描述失败: %r"), exc)
            return
        if not pointer:
            return
        try:
            definitions = pointer.contents
            count = int(definitions.nDataDescriptions)
            for index in range(count):
                definition = definitions.arrDataDescriptions[index]
                self._parse_description(definition)
        except Exception as exc:
            log.debug(tr("解析数据描述失败: %r"), exc)

        if self.info.rigid_bodies:
            log.info(tr("动捕服务器刚体列表: %s"), self.info.rigid_bodies)
        if self.info.frame_rate:
            log.info(tr("动捕帧率: %d fps"), self.info.frame_rate)

    def _parse_description(self, definition) -> None:
        kind = int(definition.type)
        descriptors = nokovsdk.DataDescriptors
        if kind == descriptors.Descriptor_RigidBody.value:
            rigid = definition.Data.RigidBodyDescription.contents
            body_id = int(rigid.ID)
            self.info.rigid_bodies[body_id] = _decode(rigid.szName)
        elif kind == descriptors.Descriptor_MarkerSet.value:
            marker_set = definition.Data.MarkerSetDescription.contents
            name = _decode(marker_set.szName)
            self.info.marker_sets.append(name)
        elif kind == descriptors.Descriptor_Skeleton.value:
            skeleton = definition.Data.SkeletonDescription.contents
            self.info.skeletons.append(_decode(skeleton.szName))
        elif kind == descriptors.Descriptor_ForcePlate.value:
            plate = definition.Data.ForcePlateDescription.contents
            self.info.force_plates += 1
            for channel in range(int(plate.nChannels)):
                self.info.analog_channels.append(_decode(plate.szChannelNames[channel]))
        elif kind == descriptors.Descriptor_Param.value:
            param = definition.Data.DataParam.contents
            self.info.frame_rate = int(param.nFrameRate)


def _decode(value) -> str:
    """Decode a ctypes char buffer / char pointer into ``str``."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        raw = value
    else:
        raw = bytes(value)
    return raw.split(b"\x00", 1)[0].decode("utf-8", "replace").strip()


# --- SDK log bridges -------------------------------------------------------- #
def _sdk_message(level, message) -> None:
    try:
        import ctypes

        text = ctypes.cast(message, ctypes.c_char_p).value
        text = text.decode("utf-8", "replace") if text else ""
    except Exception:
        text = str(message)
    text = text.strip()
    if not text:
        return
    if level <= 1:
        log.error("[SDK] %s", text)
    elif level == 2:
        log.warning("[SDK] %s", text)
    else:
        log.debug("[SDK] %s", text)


def _sdk_notify(pNotify, userData) -> None:
    try:
        notify = pNotify.contents
        text = _decode(notify.sMsg)
        log.info(tr("[服务器通知] type=%d value=%d %s"), notify.nType, notify.nValue, text)
    except Exception:
        pass
