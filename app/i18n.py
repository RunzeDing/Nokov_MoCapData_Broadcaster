"""Bilingual (简体中文 / English) user interface text.

Chinese is the *source* language: the keys of :data:`EN` are the exact Chinese
strings used in the code, and :func:`tr` looks them up when the active language
is English.  A missing entry falls back to Chinese, so an untranslated string
degrades gracefully instead of breaking the UI.

Run ``python tools\\i18n_check.py`` to list Chinese literals that are missing
from the table.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Tuple

log = logging.getLogger("nokov.i18n")

LANGUAGES: Tuple[Tuple[str, str], ...] = (
    ("zh", "中文"),
    ("en", "English"),
)
DEFAULT_LANGUAGE = "zh"

_current = DEFAULT_LANGUAGE


def normalise(code: str) -> str:
    code = (code or "").strip().lower()
    for known, _label in LANGUAGES:
        if code == known or code.startswith(known + "_") or code.startswith(known + "-"):
            return known
    return DEFAULT_LANGUAGE


def set_language(code: str) -> str:
    global _current
    resolved = normalise(code)
    if resolved != _current:
        log.info("界面语言切换为 %s", resolved)
    _current = resolved
    return _current


def get_language() -> str:
    return _current


def is_chinese() -> bool:
    return _current == "zh"


def tr(text: str) -> str:
    """Translate a Chinese UI string; unknown strings are returned unchanged."""
    if _current == "zh" or not text:
        return text
    return EN.get(text, text)


def language_label(code: str) -> str:
    for known, label in LANGUAGES:
        if known == normalise(code):
            return label
    return code


# --------------------------------------------------------------------------- #
# translation table
# --------------------------------------------------------------------------- #
EN: Dict[str, str] = {
    # ---------------------------------------------------------------- window
    "连接": "Connect",
    "广播": "Broadcast",
    "数据处理": "Processing",
    "可视化": "Visualise",
    "日志与配置": "Log & Settings",
    "与动捕服务器建立连接，查看服务器信息与刚体列表":
        "Connect to the mocap server and inspect its rigid bodies",
    "设置 UDP 目标与广播数据格式": "Configure UDP targets and the wire format",
    "刚体筛选、鲁棒性、平滑与坐标变换":
        "Body selection, robustness, smoothing and coordinate transform",
    "3D 姿态视图、实时曲线与数据表":
        "3D pose view, live plots and a data table",
    "运行日志、参数方案与启动行为":
        "Log, configuration profiles and start-up behaviour",
    "未连接": "Disconnected",
    "未广播": "Idle",
    "就绪": "Ready",
    "模拟数据源": "Simulator",
    "已连接": "Connected",
    "已连接(无数据)": "Connected (no data)",
    "广播中 %d 个目标": "Broadcasting to %d target(s)",
    "%.1f fps · %.0f 包/秒 · %d 刚体": "%.1f fps · %.0f pkt/s · %d bodies",
    "配置已重新载入": "Configuration reloaded",
    "退出": "Exit",
    "正在广播动捕数据，确定要退出吗？":
        "Motion capture data is being broadcast. Exit anyway?",
    "正在退出…": "Shutting down…",
    "按配置自动连接动捕服务器…": "Auto-connecting to the mocap server…",
    "按配置自动开始广播…": "Auto-starting the broadcast…",
    "退出清理时出错": "Error while shutting down",
    "语言": "Language",
    "界面语言": "Interface language",
    "切换界面语言（立即生效）": "Switch the interface language (applies immediately)",
    "切换后界面立即重建，正在进行的广播不会中断。":
        "The interface is rebuilt immediately; a running broadcast is not interrupted.",
    "Nokov 动捕数据广播器": "Nokov Motion Capture Broadcaster",
    "中文": "中文",
    "English": "English",

    # ------------------------------------------------------------- connection
    "动捕服务器 IP": "Mocap server IP",
    "运行 Nokov XING 服务端的电脑 IP；若就在本机，可用右侧“检测本机 IP”":
        "IP of the machine running the Nokov XING server; "
        "if it is this PC use “Detect local IP”",
    "数据接收模式": "Frame delivery mode",
    "回调模式 (SDK 主动推送，推荐)": "Callback (SDK pushes, recommended)",
    "主动读取模式 (本程序轮询)": "Polling (this program pulls)",
    "服务器时间戳单位": "Server timestamp unit",
    "自动识别 (推荐)": "Auto-detect (recommended)",
    "纳秒": "nanoseconds",
    "微秒": "microseconds",
    "毫秒": "milliseconds",
    "秒": "seconds",
    "仅影响报文中的“服务器时间戳”字段；内部计时始终使用单调时钟":
        "Only affects the “server timestamp” field of a packet; "
        "all internal timing uses a monotonic clock",
    "等待数据超时": "No-data timeout",
    " 秒": " s",
    "秒)": "s)",
    "超过该时间没有收到帧就提示“无数据”":
        "Warn about “no data” after this long without a frame",
    "读取 SDK 速度/加速度/角度": "Read SDK velocity / acceleration / angles",
    "服务器提供扩展数据时，直接使用其速度与欧拉角，比差分更准确":
        "Use the server's velocity and Euler angles when available; "
        "more accurate than differencing",
    "动捕服务器连接": "Mocap server",
    "设置服务器地址后点击“连接”，SDK 会自动开始接收数据帧。":
        "Set the server address and press Connect; the SDK starts receiving frames.",
        "断开": "Disconnect",
    "重新连接": "Reconnect",
    "检测本机 IP": "Detect local IP",
    "列出本机所有 IPv4 地址（含回环），选一个填入服务器 IP":
        "List every local IPv4 address (including loopback) and pick one",
    "本机一键连接": "Connect locally",
    "本机连接中…": "Connecting locally…",
    "动捕软件就在本机时使用：依次尝试 127.0.0.1 和本机各网卡 IP，\n自动找到能连上的那个并填入服务器 IP":
        "Use when the mocap software runs on this PC: try 127.0.0.1 and every "
        "local NIC address, then fill in whichever answers",
    "本机 IPv4：检测中…": "Local IPv4: detecting…",
    "本机 IPv4：未检测到": "Local IPv4: none found",
    "本机 IPv4：检测失败": "Local IPv4: detection failed",
    "本机 IPv4：检测失败（%r）": "Local IPv4: detection failed (%r)",
    "本机 IPv4（▶ 为当前填写的服务器地址）：":
        "Local IPv4 (▶ marks the address currently filled in): ",
    "启用模拟数据源（无硬件时演示/调试）":
        "Enable the built-in simulator (demo / debug without hardware)",
    "刚体 ": "bodies ",
    "速率 ": "rate ",
    "运行状态": "Status",
    "连接状态": "Connection",
    "SDK 版本": "SDK version",
    "服务器": "Server",
    "数据帧率": "Frame rate",
    "已接收帧": "Frames received",
    "重复帧": "Duplicate frames",
    "数据来源": "Data source",
    "服务器信息": "Server information",
    "主机名": "Host name",
    "应用程序": "Application",
    "程序版本": "Version",
    "地址": "Address",
    "帧率设置": "Configured rate",
    "标记点集合": "Marker sets",
    "骨架": "Skeletons",
    "力台": "Force plates",
    "服务器刚体列表": "Rigid bodies on the server",
    "双击一行可将其设为“仅广播该刚体”。":
        "Double-click a row to broadcast only that body.",
    "ID": "ID",
    "名称": "Name",
    "仅广播选中的刚体": "Broadcast only the selected bodies",
    "恢复为全部刚体": "Broadcast all bodies",
    "已断开与动捕服务器的连接。": "Disconnected from the mocap server.",
    "本机检测到以下 IPv4 地址，请选择动捕服务器使用的地址：\n（动捕软件在本机时，通常就是默认出口网卡；若服务器只监听回环可用 127.0.0.1）":
        "Local IPv4 addresses found. Pick the one the mocap server uses:\n"
        "(when the software runs here it is usually the default-route NIC; "
        "use 127.0.0.1 if the server only listens on loopback)",
        "已恢复为广播全部刚体。": "Restored to broadcasting all bodies.",
    "已填入本机地址 %s（%s）。": "Filled in local address %s (%s).",
    "网卡": "adapter",
    "未能枚举到本机 IPv4 地址，请检查网络适配器。":
        "Could not enumerate any local IPv4 address; check the network adapters.",
    "模拟数据源已开启，请先关闭它再连接真实服务器。":
        "The simulator is running; turn it off before connecting to a real server.",
    "未检测到可用的本机地址。": "No usable local address was found.",
    "本机自动连接中，正在依次尝试：%s …":
        "Trying local addresses in turn: %s …",
    "正在尝试 %s …（本机自动连接）": "Trying %s … (local auto-connect)",
    "本机自动连接：尝试 %s": "Local auto-connect: trying %s",
    "本机自动连接成功: %s": "Local auto-connect succeeded: %s",
    "本机自动连接成功：%s（%s）": "Local auto-connect succeeded: %s (%s)",
    "（无）": "(none)",
    "本机自动连接失败，已尝试：%s。\n最后一次错误：%s\n请确认动捕软件已启动并处于播放/采集状态；也可以手动点“检测本机 IP”选择正确网卡，或直接填写服务器的实际地址。":
        "Local auto-connect failed. Tried: %s\nLast error: %s\n"
        "Make sure the mocap software is running and playing/recording. "
        "You can also use “Detect local IP” or type the server address directly.",
    "本机自动连接失败，已尝试 %s: %s": "Local auto-connect failed, tried %s: %s",
    "模拟数据源运行中：数据不会来自真实动捕服务器。":
        "Simulator running: data does not come from a real mocap server.",
    "模拟数据源已停止。": "Simulator stopped.",
    "请先在列表中选中至少一个刚体。": "Select at least one rigid body first.",
    "已设置为仅广播刚体: %s（可在“数据处理”页修改）":
        "Broadcasting only: %s (change it on the Processing page)",
    "解析帧时出现 %d 次错误，最近一次: %s":
        "%d frame parsing error(s); the latest: %s",
    "已连接但 %.1f 秒没有收到数据帧：请确认动捕软件已开始播放/采集，或检查服务器 IP 是否正确。":
        "Connected but no frame for %.1f s: make sure the mocap software is "
        "playing/recording and that the server IP is correct.",
    "已连接 · 数据正常": "Connected · streaming",
    "已连接 · 等待数据": "Connected · waiting for data",
    "%d 个": "%d",
    "动捕服务器": "Mocap server",
    "正在尝试 %s…": "Trying %s…",

    # -------------------------------------------------------------- broadcast
    "UDP 广播目标": "UDP targets",
    "可以同时向多个地址发送；取消勾选即可临时停用某个目标。":
        "Send to several addresses at once; untick a row to disable it temporarily.",
    "启用": "On",
    "目标 IP / 主机名": "Target IP / host",
    "端口": "Port",
    "备注": "Note",
    "添加目标": "Add target",
    "删除选中": "Remove selected",
    "填入本机网卡 IP": "Use local NIC IP",
    "接收端也在本机时使用。接收端绑定 0.0.0.0 或绑定本机网卡地址都能收到。\n（原 NokovSDKClient_STQ.py 用的就是这个方式：192.168.1.123:22222）":
        "Use when the receiver is on this PC. Works whether it binds 0.0.0.0 "
        "or the NIC address.\n(This is what the original NokovSDKClient_STQ.py did: "
        "192.168.1.123:22222)",
    "填入本机回环 127.0.0.1": "Use loopback 127.0.0.1",
    "接收端也在本机、且只监听 127.0.0.1 时使用":
        "Use when the receiver runs here and only listens on 127.0.0.1",
    "发送限速": "Rate limit",
    "每帧都发": "Every frame",
    "没有刚体时也发送空包": "Send empty packets too",
    "本机绑定 IP": "Local bind IP",
    "留空 = 系统默认网卡": "empty = system default",
    "广播数据格式": "Wire format",
    "默认格式与 NokovSDKClient_STQ.py 完全一致（逐字节相同）。":
        "The default format is byte-for-byte identical to NokovSDKClient_STQ.py.",
    "广播控制": "Broadcast control",
    "开始广播": "Start broadcast",
    "停止广播": "Stop broadcast",
    "发送速率": "Send rate",
    "带宽": "Bandwidth",
    "累计包数": "Packets sent",
    "报文长度": "Packet size",
    "编码耗时": "Encode time",
    "启用目标": "Active targets",
    "发送错误": "Send errors",
    "报文结构预览": "Packet layout",
    "显示当前参数下的字节布局与预计长度。":
        "Byte layout and predicted size for the current parameters.",
    "最近发出的报文": "Last packet",
    "前 32 字节的十六进制内容。": "First 32 bytes, hexadecimal.",
    "（尚未发送）": "(nothing sent yet)",
    "格式参数": "Format parameters",
    "本机网卡": "local NIC",
    "本机回环": "loopback",
    "未检测到本机网卡地址，请检查网络连接":
        "No local NIC address found; check the network connection",
    "已添加广播目标 %s:%s（%s）": "Added target %s:%s (%s)",
    "请先添加至少一个 UDP 目标": "Add at least one UDP target first",
    "发送套接字创建失败": "Could not create the sending socket",
    "广播中 → ": "Broadcasting → ",
    "目标配置有误：": "Invalid target configuration: ",
    "第 %d 行缺少 IP": "row %d has no IP",
    "第 %d 行端口 %s 无效": "row %d has an invalid port (%s)",
    "第 %d 行的 IP 或端口不完整": "row %d has an incomplete IP or port",
    "当前刚体数 %d，预计单包 %d 字节（UDP 上限 65507）":
        "%d bodies now, about %d bytes per datagram (UDP limit 65507)",
    "字节序：%s": "Byte order: %s",
    "小端字节序": "little-endian",
    "大端字节序": "big-endian",
    "小端": "little-endian",
    "大端": "Big-endian",
    "%.0f 包/秒": "%.0f pkt/s",
    "%d 字节": "%d bytes",
    "共 %d 字节；用时 %.2f ms": "%d bytes, encoded in %.2f ms",
    "本机 IPv4：%s　—　接收端在本机时优先用“本机网卡 IP”；接收端在另一台电脑上时，请填写那台电脑的 IP。":
        "Local IPv4: %s — prefer “Use local NIC IP” when the receiver is on this "
        "PC; otherwise enter the IP of the other computer.",
    "开始广播: %s": "Broadcast started: %s",
    "已停止广播": "Broadcast stopped",

    # ------------------------------------------------------------- processing
    "刚体选择": "Body selection",
    "决定哪些刚体参与广播。默认与原脚本一致：广播所有 ID >= 0 的刚体。":
        "Which rigid bodies take part. Default matches the original script: "
        "every body with ID >= 0.",
    "最小刚体 ID": "Minimum body ID",
    "小于该 ID 的刚体不广播。原脚本使用 ID >= 0，因此默认 0（若要排除 ID 0 请填 1）":
        "Bodies below this ID are not broadcast. The original script used "
        "ID >= 0, hence the default of 0 (use 1 to exclude ID 0)",
    "最大刚体 ID": "Maximum body ID",
    "大于该 ID 的刚体不广播": "Bodies above this ID are not broadcast",
    "仅广播这些 ID": "Only these IDs",
    "例如 1,2,5-8（留空 = 全部）": "e.g. 1,2,5-8 (empty = all)",
    "白名单，优先级高于范围与黑名单": "Whitelist; takes priority over range and blacklist",
    "排除这些 ID": "Exclude these IDs",
    "例如 3,4": "e.g. 3,4",
    "要求至少有标记点": "Require markers",
    "最少标记点数": "Minimum marker count",
    "用于剔除标记点被遮挡、位姿不可信的刚体":
        "Drops bodies whose pose is unreliable because markers are occluded",
    "鲁棒性与运动学": "Robustness & kinematics",
    "异常值检测、保持策略，以及速度/角度的来源。":
        "Glitch detection, hold strategy and where velocity/angles come from.",
    "异常值阈值": "Glitch threshold",
    " mm": " mm",
    "坐标绝对值超过该值的采样视为跟踪跳变；填 0 关闭检测。原脚本为 9000 mm":
        "Samples whose coordinates exceed this are treated as tracking glitches; "
        "0 disables detection. The original script used 9000 mm",
    "异常时保持上一帧有效值": "Hold the previous valid sample on a glitch",
    "与原脚本一致：用上一帧的位置与姿态替换跳变数据":
        "Same as the original script: replace glitched data with the previous pose",
    "最多保持帧数": "Max held frames",
    "超过该帧数仍未恢复则停止广播该刚体；0 = 一直保持":
        "Stop broadcasting the body after this many held frames; 0 = hold forever",
    "刚体丢失后继续发送最后位姿": "Keep sending the last pose when a body vanishes",
    "接收端不会因为刚体短暂消失而得到残缺的包结构":
        "The receiver never sees a truncated packet because a body blinked out",
    "速度来源": "Velocity source",
    "自动（优先使用 SDK 扩展数据）": "Auto (prefer SDK extended data)",
    "仅使用 SDK 速度/加速度": "SDK velocity/acceleration only",
    "由位置差分计算": "Compute by differencing positions",
    "欧拉角来源": "Euler angle source",
    "自动（优先使用 SDK 角度）": "Auto (prefer SDK angles)",
    "仅使用 SDK 角度": "SDK angles only",
    "由四元数换算 (Z-Y-X)": "Derive from the quaternion (Z-Y-X)",
    "平滑滤波": "Smoothing",
    "抑制抖动。默认关闭，以保证与旧程序完全一致。":
        "Reduces jitter. Off by default so output matches the original script.",
    "平滑方式": "Smoothing mode",
    "不平滑（与原脚本一致）": "None (same as the original script)",
    "滑动平均 (SMA)": "Moving average (SMA)",
    "滑动中值（抑制尖刺）": "Moving median (kills spikes)",
    "指数平滑 (EMA)": "Exponential smoothing (EMA)",
    "One-Euro 自适应滤波（推荐）": "One-Euro adaptive filter (recommended)",
    "窗口长度": "Window length",
    " 帧": " frames",
    "SMA / 中值滤波使用": "Used by SMA and the moving median",
    "EMA / 姿态平滑系数": "EMA / orientation smoothing factor",
    "越小越平滑、延迟越大": "Smaller = smoother but laggier",
    "One-Euro 最小截止频率": "One-Euro min cutoff",
    " Hz": " Hz",
    "越小越平滑": "Smaller = smoother",
    "One-Euro 速度系数 β": "One-Euro speed coefficient β",
    "越大越能跟随快速运动": "Larger = follows fast motion better",
    "同时平滑姿态四元数": "Also smooth the orientation quaternion",
    "重置滤波器状态": "Reset filter state",
    "坐标系变换": "Coordinate transform",
    "在发送前对位置与姿态做整体变换。默认为恒等变换。":
        "Applies an overall transform to position and orientation before sending. "
        "Identity by default.",
    "坐标轴映射": "Axis mapping",
    "XYZ — 不改变": "XYZ — unchanged",
    "ZYX — 交换 X 与 Z": "ZYX — swap X and Z",
    "XZY — 交换 Y 与 Z": "XZY — swap Y and Z",
    "输出轴 = 输入轴按此顺序排列，例如 ZYX 表示 out_x = in_z":
        "Output axes in this order; ZYX means out_x = in_z",
    "X 轴方向": "X direction",
    "Y 轴方向": "Y direction",
    "Z 轴方向": "Z direction",
    "保持": "Keep",
    "取反": "Invert",
    "整体缩放": "Overall scale",
    "在毫米→米换算之后再乘的系数": "Multiplier applied after the mm → m conversion",
    "X 偏移": "X offset",
    "Y 偏移": "Y offset",
    "Z 偏移": "Z offset",
    " m": " m",
    "绕 Z 轴旋转": "Rotate about Z",
    " °": " °",
    "同时作用于位置与姿态": "Applies to both position and orientation",
    "当前处理摘要": "Processing summary",
    "刚体选择：%s": "Bodies: %s",
    "异常阈值：%s": "Glitch threshold: %s",
    "异常处理：%s": "On glitch: %s",
    "平滑：%s": "Smoothing: %s",
    "坐标系：%s": "Coordinates: %s",
    "关闭": "off",
    "保持上一帧": "hold previous",
    "直接透传": "pass through",
    "滑动平均(%d)": "moving average (%d)",
    "中值(%d)": "median (%d)",
    "指数(α=%.3f)": "exponential (α=%.3f)",
    "累计处理 %d 帧；检出异常 %d 次，保持 %d 次，被过滤丢弃 %d 次，当前参与广播的刚体 %d 个":
        "%d frames processed; %d glitches, %d held, %d filtered out, "
        "%d bodies currently broadcast",
    "“仅广播这些 ID”内容无法解析，请检查格式。":
        "The “Only these IDs” field could not be parsed; check its format.",
    "滤波器与缓存已重置。": "Filter state and caches were reset.",

    # -------------------------------------------------------------- visualise
    "位置": "Position",
    "速度": "Velocity",
    "加速度": "Acceleration",
    "姿态角": "Euler angles",
    "速度大小": "Speed",
    "刚体标签": "Body labels",
    "运动拖尾": "Motion trails",
    "标记点云": "Marker cloud",
    "姿态坐标轴": "Pose axes",
    "姿态轴长 ": "Axis length ",
    "拖尾 ": "Trail ",
    " 点": " points",
    "自动适配视角": "Fit view",
    "重置视角": "Reset view",
    "刚体数据": "Rigid body data",
    "实时数值与质量指标；双击不在列表中时可用上方下拉框选择。":
        "Live values and quality indicators; use the drop-down above to pick a body.",
    "曲线刚体": "Plotted body",
    " 秒窗口": " s window",
    "已选通道：%s": "Channels: %s",
    "未选择任何通道": "No channel selected",
    "该刚体暂无历史数据": "No history for this body yet",
    "刚体 %d %s": "Body %d %s",
    "等待动捕数据…\n（连接动捕服务器，或开启模拟数据源）":
        "Waiting for mocap data…\n(connect to the mocap server, or enable the simulator)",
    "左键拖动=旋转  右键/中键拖动=平移  滚轮=缩放  双击=自动适配  R=重置":
        "Drag left = orbit   drag right/middle = pan   wheel = zoom   "
        "double-click = fit   R = reset",

    # ------------------------------------------------------------------- log
    "运行日志": "Log",
    "记录连接、广播与错误信息；同时写入日志文件。":
        "Connection, broadcast and error messages; also written to a log file.",
    "最低级别": "Minimum level",
    "自动滚动": "Auto-scroll",
    "清空显示": "Clear",
    "复制全部": "Copy all",
    "打开日志文件夹": "Open log folder",
    "参数配置方案": "Configuration profiles",
    "把当前所有设置保存为方案，方便在不同项目间切换。":
        "Save every setting as a profile to switch between projects.",
    "保存为方案": "Save as profile",
    "载入选中方案": "Load selected",
    "删除选中方案": "Delete selected",
    "重载当前设置": "Reload defaults",
    "打开配置文件夹": "Open config folder",
    "启动行为": "Start-up behaviour",
    "下次启动程序时自动执行的动作。": "Actions performed automatically at the next start.",
    "启动后自动连接动捕服务器": "Connect automatically at start-up",
    "启动后自动开始广播": "Start broadcasting automatically at start-up",
    "写入日志文件": "Write a log file",
    "配置文件：%s": "Config file: %s",
    "日志文件：%s": "Log file: %s",
    "关于": "About",
    "未加载": "not loaded",
    "<b>%s</b> v%s<br>Nokov SDK: %s<br>Python: %s<br>默认广播格式与 <code>NokovSDKClient_STQ.py</code> 逐字节一致。":
        "<b>%s</b> v%s<br>Nokov SDK: %s<br>Python: %s<br>The default wire format is "
        "byte-for-byte identical to <code>NokovSDKClient_STQ.py</code>.",
    "保存方案": "Save profile",
    "方案名称：": "Profile name:",
    "默认方案": "default",
    "已保存方案 %s -> %s": "Saved profile %s -> %s",
    "已载入方案 %s": "Loaded profile %s",
    "已载入": "Loaded",
    "已恢复默认设置": "Restored the default settings",
    "提示": "Notice",
    "请先选择一个方案。": "Select a profile first.",
    "载入失败": "Load failed",
    "保存失败": "Save failed",
    "方案文件不存在或已损坏。": "The profile file is missing or damaged.",
    "方案“%s”已载入。\n如需生效到正在运行的界面，请到各页面确认参数。（连接与广播设置已即时生效）":
        "Profile “%s” loaded.\nConnection and broadcast settings apply immediately; "
        "check the other pages to confirm their parameters.",
    "删除方案": "Delete profile",
    "确定删除方案“%s”？": "Delete the profile “%s”?",
    "打开路径失败 %s: %s": "Could not open %s: %s",

    # --------------------------------------------------------------- widgets
    "数据量": "Quantity",
    "类型": "Type",
    "缩放": "Scale",
    "偏移": "Offset",
    "饱和": "Clamp",
    "添加字段": "Add field",
        "上移": "Move up",
    "下移": "Move down",
    "恢复默认": "Restore defaults",
    "每行一个字段，顺序即报文中的字节顺序。位置单位为米、速度 m/s、角度为度；缩放系数决定定点数精度（例如 int16 × 2000 表示 0.0005 m 的分辨率）。":
        "One field per row; the order is the byte order in the packet. "
        "Positions are metres, velocities m/s, angles degrees. The scale factor "
        "sets fixed-point resolution (int16 × 2000 gives 0.0005 m).",
    "例如 AA 55": "e.g. AA 55",
    "参数": "Parameters",
    "%s (%d字节)": "%s (%d bytes)",
    "状态": "Status",
    "速度 (m/s)": "Speed (m/s)",
    "标记点": "Markers",
    "误差 (mm)": "Error (mm)",
    "四元数 (x,y,z,w)": "Quaternion (x,y,z,w)",
    "异常累计": "Glitches",
    "正常": "OK",
    "保持(丢失)": "held (lost)",
    "丢失": "lost",
    "新建": "new",
    "异常": "glitch",
    "位置 X (m)": "X position (m)",
    "位置 Y (m)": "Y position (m)",
    "位置 Z (m)": "Z position (m)",
    "速度 vx (m/s)": "vx (m/s)",
    "速度 vy (m/s)": "vy (m/s)",
    "速度 vz (m/s)": "vz (m/s)",
    "加速度 ax (m/s²)": "ax (m/s²)",
    "加速度 ay (m/s²)": "ay (m/s²)",
    "加速度 az (m/s²)": "az (m/s²)",
    "横滚 (deg)": "Roll (deg)",
    "俯仰 (deg)": "Pitch (deg)",
    "偏航 (deg)": "Yaw (deg)",
    "速度大小 (m/s)": "Speed (m/s)",
    "选择刚体后显示实时曲线": "Select a rigid body to see its live traces",

    # ---------------------------------------------------------------- netinfo
    "127.0.0.1  (本机回环)": "127.0.0.1  (loopback)",
    "%s  (%s%s)": "%s  (%s%s)",
    " · 未连接": " · disconnected",
    "以太网": "Ethernet",
    "回环": "Loopback",
    "无线(WLAN)": "Wi-Fi",
    "隧道": "Tunnel",
    "虚拟网卡": "Virtual adapter",
    "本机主机名解析": "resolved from host name",
    "默认出口网卡": "default route NIC",
    "未检测到本机 IPv4 地址": "No local IPv4 address found",
        # ------------------------------------------------------- format metadata
    "STQ 标准 (14 字节/刚体)  ★默认": "STQ standard (14 bytes/body)  ★default",
    "与 NokovSDKClient_STQ.py 完全一致的格式：每刚体 14 字节 "
    "x,y,z,qx,qy,qz,qw，位置×2000、四元数×1000，int16 小端，"
    "按刚体 ID 升序拼接成单个 UDP 包。":
        "Identical to NokovSDKClient_STQ.py: 14 bytes per body "
        "(x,y,z,qx,qy,qz,qw), position × 2000, quaternion × 1000, int16 "
        "little-endian, concatenated in ascending body-ID order into one datagram.",
    "STQ 扩展 (20 字节/刚体，含速度)": "STQ extended (20 bytes/body, with velocity)",
    "在标准格式后追加 vx,vy,vz 三个 int16，共 20 字节/刚体。"
    "接收端用 v × 0.001 还原为 m/s。":
        "Appends vx,vy,vz as three int16 values, 20 bytes per body. "
        "A receiver restores m/s with v × 0.001.",
    "自定义二进制格式": "Custom binary format",
    "自由组合字段、类型、缩放、偏移、字节序与包头包尾。"
    "默认值等价于标准 STQ 14 字节格式，可在此基础上任意扩展。":
        "Combine fields, types, scaling, offsets, byte order, header and footer "
        "freely. The defaults match the standard 14-byte STQ format.",
    "位置缩放": "Position scale",
    "发送值 = 位置(米) × 该系数。接收端用 0.0005 还原时请保持 2000。":
        "Sent value = position (m) × this factor. Keep 2000 for a receiver "
        "that multiplies by 0.0005.",
    "四元数缩放": "Quaternion scale",
    "发送值 = 四元数分量 × 该系数。": "Sent value = quaternion component × this factor.",
    "发送前归一化四元数": "Normalise the quaternion before sending",
    "超出范围时饱和截断": "Saturate out-of-range values",
    "关闭后会按类型范围回绕（wrap），一般只在特殊接收端需要。":
        "When off, values wrap around the type range; rarely needed.",
    "取整方式": "Rounding",
    "截断 (与旧程序一致)": "Truncate (matches the original script)",
    "截断": "Truncate",
    "四舍五入": "Round",
    "向下取整": "Floor",
    "向上取整": "Ceil",
    "字节序": "Byte order",
    "小端 (Windows/Intel)": "Little-endian (Windows/Intel)",
        "包首加入帧号 (uint32)": "Prefix the frame number (uint32)",
    "包首加入刚体数量 (uint16)": "Prefix the body count (uint16)",
    "自定义包头 (十六进制)": "Custom header (hex)",
    "例如 AA 55。留空表示无包头。": "For example AA 55. Empty means no header.",
    "自定义包尾 (十六进制)": "Custom footer (hex)",
    "丢弃从未获得有效数据的刚体": "Drop bodies that never produced valid data",
    "数值换算": "Value conversion",
    "报文结构": "Packet structure",
    "速度缩放": "Velocity scale",
    "发送值 = 速度(m/s) × 该系数。1000 对应接收端乘 0.001。":
        "Sent value = velocity (m/s) × this factor. 1000 pairs with a receiver "
        "multiplying by 0.001.",
    "整数取整方式": "Integer rounding",
    "包头 (十六进制，可空)": "Header (hex, optional)",
    "例如 “AA 55” 或 “0xAA,0x55”": "e.g. “AA 55” or “0xAA,0x55”",
    "包尾 (十六进制，可空)": "Footer (hex, optional)",
    "报文包含帧号": "Include the frame number",
    "帧号类型": "Frame number type",
    "报文包含刚体数量": "Include the body count",
    "刚体数量类型": "Body count type",
    "报文包含时间戳": "Include a timestamp",
    "时间戳类型": "Timestamp type",
    "时间戳单位": "Timestamp unit",
    "刚体字段列表": "Per-body field list",
    "每行一个字段，从上到下的顺序就是报文中的字节顺序。":
        "One field per row; top to bottom is the byte order in the packet.",
    "刚体字段": "Body fields",

    # -------------------------------------------------------------- quantities
    "位置 X": "X position",
    "位置 Y": "Y position",
    "位置 Z": "Z position",
    "四元数 qx": "Quaternion qx",
    "四元数 qy": "Quaternion qy",
    "四元数 qz": "Quaternion qz",
    "四元数 qw": "Quaternion qw",
    "速度 vx": "Velocity vx",
    "速度 vy": "Velocity vy",
    "速度 vz": "Velocity vz",
    "加速度 ax": "Acceleration ax",
    "加速度 ay": "Acceleration ay",
    "加速度 az": "Acceleration az",
        "横滚 roll": "Roll",
    "俯仰 pitch": "Pitch",
    "偏航 yaw": "Yaw",
    "刚体 ID": "Body ID",
    "标记点数": "Marker count",
    "标记点平均误差": "Mean marker error",
    "保持帧数": "Held frames",
    "状态码": "Status code",
    "帧号": "Frame number",
    "相对时间": "Relative time",
    "服务器时间戳": "Server timestamp",
    "服务器原始时间戳": "Raw server timestamp",
    "刚体数量": "Body count",
    "延迟": "Latency",

    # --------------------------------------------------------- net errors etc.
    "权限不足或地址不可用": "Permission denied or address unavailable",
    "地址族不支持": "Address family not supported",
    "本机不存在该地址 (请检查本机 IP 设置)":
        "The address does not belong to this machine (check the local IP settings)",
    "网络不可达": "Network unreachable",
    "目标网络不可达": "Destination network unreachable",
    "连接被对端重置": "Connection reset by peer",
    "套接字未连接": "Socket not connected",
    "连接超时": "Connection timed out",
    "目标拒绝连接": "Connection refused",
    "目标主机已关闭": "Destination host is down",
    "目标主机不可达": "Destination host unreachable",
    "创建发送套接字失败: %s": "Could not create the sending socket: %s",
    "没有可用的 UDP 目标": "No usable UDP target",
    "报文长度 %d 字节超过 UDP 上限 65507，已截断到前 65507 字节；请减少刚体数量或字段。":
        "The packet is %d bytes, over the 65507-byte UDP limit; truncated to "
        "65507 bytes. Reduce the body count or field list.",

    # ------------------------------------------------------------- sdk client
    "已加载": "loaded",
    "加载 nokov_sdk.dll 失败: %s\n请确认已安装 Microsoft Visual C++ 运行库 (SDK 包内附 VC_redist.x64.exe)，并且系统为 64 位。":
        "Failed to load nokov_sdk.dll: %s\nInstall the Microsoft Visual C++ "
        "runtime (VC_redist.x64.exe ships with the SDK) and make sure Windows is 64-bit.",
    "导入 Nokov SDK 失败: %r": "Could not import the Nokov SDK: %r",
    "成功": "OK",
    "内部错误 (ErrorCode_Internal)": "Internal error (ErrorCode_Internal)",
    "外部错误 (ErrorCode_External)": "External error (ErrorCode_External)",
    "网络错误 (ErrorCode_Network)：请检查服务器 IP / 网线 / 防火墙":
        "Network error (ErrorCode_Network): check the server IP, cable and firewall",
    "其它错误 (ErrorCode_Other)": "Other error (ErrorCode_Other)",
    "无法与服务器建立连接：请确认服务器 IP 正确、动捕软件已启动、网络可达":
        "Cannot reach the server: check the server IP, that the mocap software "
        "is running, and that the network is reachable",
    "未知错误码": "unknown error code",
    "创建 SDK 客户端失败: %r": "Could not create the SDK client: %r",
    "请先填写动捕服务器 IP 地址": "Enter the mocap server IP address first",
    "调用 SDK Initialize 失败: %r": "SDK Initialize failed: %r",
    "重建 SDK 客户端失败: %r": "Could not rebuild the SDK client: %r",
    "注册数据回调失败: %r": "Could not register the data callback: %r",
    "连接失败 [%d] %s": "Connection failed [%d] %s",
    "未知": "unknown",
    "已连接 (%s模式)，等待数据…": "Connected (%s mode), waiting for data…",
    "回调": "callback",
    "主动读取": "polling",
    "已经在运行": "already running",

    # --------------------------------------------------- processing summaries
    "全部刚体": "all bodies",
    "仅 %s": "only %s",
    "排除 %s": "excluding %s",
    "标记点>=%d": "markers >= %d",
    "恒等变换": "identity",

    # ------------------------------------------------------ packet layout view
    "(空)": "(empty)",
    "包头 %s": "header %s",
    "包尾 %s": "footer %s",
    "包头 (自定义) %s": "header (custom) %s",
    "包尾 (自定义) %s": "footer (custom) %s",
    "帧号 %s": "frame number %s",
    "刚体数量 %s": "body count %s",
    "时间戳 %s (%s)": "timestamp %s (%s)",
    "帧号 uint32": "frame number uint32",
    "刚体数量 uint16": "body count uint16",
    "单位 %s": "unit %s",
    "回绕": "wraps",
    "x    = 位置 X (m) × %g": "x    = position X (m) × %g",
    "y    = 位置 Y (m) × %g": "y    = position Y (m) × %g",
    "z    = 位置 Z (m) × %g": "z    = position Z (m) × %g",
    "qx   = 四元数 x × %g": "qx   = quaternion x × %g",
    "qy   = 四元数 y × %g": "qy   = quaternion y × %g",
    "qz   = 四元数 z × %g": "qz   = quaternion z × %g",
    "qw   = 四元数 w × %g": "qw   = quaternion w × %g",
    "vx   = 速度 X (m/s) × %g": "vx   = velocity X (m/s) × %g",
    "vy   = 速度 Y (m/s) × %g": "vy   = velocity Y (m/s) × %g",
    "vz   = 速度 Z (m/s) × %g": "vz   = velocity Z (m/s) × %g",
    "        ↑ 单个刚体 14 字节；整包 = 包头 + N×14 + 包尾，按 ID 升序":
        "        ↑ 14 bytes per body; packet = header + N×14 + footer, ascending ID",
    "        ↑ 单个刚体 20 字节；整包 = 包头 + N×20 + 包尾，按 ID 升序":
        "        ↑ 20 bytes per body; packet = header + N×20 + footer, ascending ID",
    "        ↑ 单个刚体 %d 字节；整包 = 包头 + N×%d + 包尾，按 ID 升序":
        "        ↑ %d bytes per body; packet = header + N×%d + footer, ascending ID",
    "        （未配置任何刚体字段，仅发送包头/包尾）":
        "        (no per-body fields configured; only header/footer are sent)",

    # ------------------------------------------------------------ log messages
    "模拟数据": "simulator",
    "连接成功: %s": "Connected: %s",
    "连接失败: %s": "Connection failed: %s",
    "处理线程已启动": "Engine thread started",
    "处理线程已退出": "Engine thread stopped",
    "配置 UDP 目标失败: %r": "Could not configure the UDP targets: %r",
    "处理帧失败: %r": "Frame processing failed: %r",
    "处理帧失败": "Frame processing failed",
    "编码/发送失败: %r": "Encode/send failed: %r",
    "编码或发送失败": "Encode or send failed",
    "模拟数据源生成帧失败": "Simulator failed to build a frame",
    "模拟数据源已启动: %d 个刚体 @ %.0f Hz":
        "Simulator started: %d bodies @ %.0f Hz",
    "模拟数据源已停止": "Simulator stopped",
    "本次运行使用了命令行参数，配置未写回 config.json":
        "Command line overrides were used; config.json was not updated",
    "保存配置失败: %s": "Could not save the configuration: %s",
    "Nokov SDK 已加载 (%s)": "Nokov SDK loaded (%s)",
    "Nokov SDK 就绪": "Nokov SDK ready",
    "[服务器通知] type=%d value=%d %s": "[server notice] type=%d value=%d %s",
    "动捕服务器刚体列表: %s": "Rigid bodies on the server: %s",
    "动捕帧率: %d fps": "Mocap frame rate: %d fps",
    "重新连接返回 %d，重建 SDK 客户端后重试":
        "Reconnect returned %d; rebuilding the SDK client and retrying",
    "解析帧失败: %r": "Could not parse the frame: %r",
    "读取服务器描述失败: %r": "Could not read the server description: %r",
    "解析服务器描述失败: %r": "Could not parse the server description: %r",
    "读取数据描述失败: %r": "Could not read the data descriptions: %r",
    "解析数据描述失败: %r": "Could not parse the data descriptions: %r",
    "读取帧失败: %r": "Could not read a frame: %r",
    "自动识别服务器时间戳单位: %s": "Detected server timestamp unit: %s",
    "GetAdaptersAddresses 无法获取缓冲区大小":
        "GetAdaptersAddresses could not report the buffer size",
    "GetAdaptersAddresses 失败，改用回退方案: %r":
        "GetAdaptersAddresses failed, falling back: %r",
    "GetAdaptersAddresses 返回 %d": "GetAdaptersAddresses returned %d",
    "界面语言已切换为 %s": "Interface language switched to %s",
    "%s v%s 启动 (Python %s)": "%s v%s started (Python %s)",
    "%s v%s - Nokov 动捕数据广播器": "%s v%s - Nokov motion capture broadcaster",
    "配置文件: %s": "Config file: %s",
    "日志文件: %s": "Log file: %s",
    "SDK 目录: %s": "SDK directory: %s",
    "运行模式: 已打包 (frozen)": "Run mode: packaged (frozen)",
    "界面已启动": "Interface started",
    "连接结果: %s": "Connection result: %s",
        "未捕获异常:\n%s": "Unhandled exception:\n%s",
    "按 Ctrl+C 退出": "Press Ctrl+C to quit",
    "后台广播中 → %s   格式: %s": "Broadcasting in the background → %s   format: %s",
    "%.1f fps · %.0f 包/秒 · %d 刚体 · 已发 %d 包":
        "%.1f fps · %.0f pkt/s · %d bodies · %d packets sent",
    "警告: %s": "Warning: %s",
    "\n正在退出…": "\nShutting down…",
    "缺少 PySide2，无法启动图形界面：%s\n"
    "请使用随程序提供的独立 exe 版本，或先执行 pip install PySide2。":
        "PySide2 is missing, so the GUI cannot start: %s\n"
        "Use the standalone exe that ships with this project, or run pip install PySide2.",
    "目标格式应为 IP:端口，例如 192.168.1.123:22222（收到 %r）":
        "Targets look like IP:port, e.g. 192.168.1.123:22222 (got %r)",
    "未知格式 %r，可用: %s": "Unknown format %r; available: %s",
    "示例:\n"
    "  NokovBroadcaster.exe\n"
    "  NokovBroadcaster.exe --server 10.1.1.198 --target 192.168.1.123:22222 --autostart\n"
    "  NokovBroadcaster.exe --headless --server 10.1.1.198 --target 127.0.0.1:22222\n"
    "  NokovBroadcaster.exe --simulate 6 --target 127.0.0.1:22222 --autostart\n":
        "Examples:\n"
        "  NokovBroadcaster.exe\n"
        "  NokovBroadcaster.exe --server 10.1.1.198 --target 192.168.1.123:22222 --autostart\n"
        "  NokovBroadcaster.exe --headless --server 10.1.1.198 --target 127.0.0.1:22222\n"
        "  NokovBroadcaster.exe --simulate 6 --target 127.0.0.1:22222 --autostart\n",
    "动捕服务器 IP 地址": "mocap server IP address",
    "UDP 广播目标，可重复指定": "UDP target, may be given more than once",
    "广播数据格式: stq14 / stq20 / custom": "wire format: stq14 / stq20 / custom",
    "使用内置模拟数据源（可选刚体数量，默认 4）":
        "use the built-in simulator (optional body count, default 4)",
    "启动后自动连接并开始广播": "connect and start broadcasting at start-up",
    "不显示图形界面，仅后台广播": "no GUI, broadcast in the background only",
}
