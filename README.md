# NokovBroadcaster

**English** · [中文](#中文文档)

A Windows GUI application that receives motion capture data from a **Nokov XING** server,
processes it, and **broadcasts it over UDP** in a wire format you control.

---

## Table of contents

- [1. Highlights](#1-highlights)
- [2. Three ways to run it](#2-three-ways-to-run-it)
- [3. First run, step by step](#3-first-run-step-by-step)
- [4. Typical workflows](#4-typical-workflows)
- [5. Command line reference](#5-command-line-reference)
- [6. What the target PC needs](#6-what-the-target-pc-needs)
- [7. Wire formats](#7-wire-formats)
- [8. Interface reference](#8-interface-reference)
- [9. Language switching](#9-language-switching)
- [10. Settings, profiles, portable mode](#10-settings-profiles-portable-mode)
- [11. Differences from the original script](#11-differences-from-the-original-script)
- [12. Building from source](#12-building-from-source)
- [13. Troubleshooting](#13-troubleshooting)
- [14. Machine-specific notes](#14-machine-specific-notes)

---

## 1. Highlights

* **Default format identical to `NokovSDKClient_STQ.py`** — verified automatically
  against the original packing routine with 40 randomised cases plus saturation,
  degenerate-quaternion and truncation edge cases (`tools/selftest.py`).
* **Nothing to install on the target PC** — the single-file exe bundles the Nokov SDK,
  the Python runtime, PySide2/Qt and the Visual C++ runtime. `run.bat` gives you the
  same zero-install experience for the Python version.
* **Live 3D pose view, time-series plots and a data table** for checking the data
  before it goes out.
* **Built-in simulator**, so you can commission a receiver with no motion capture
  hardware present.
* **Instant Chinese / English switching**, without interrupting a running broadcast.

---

## 2. Three ways to run it

| Way | How | When to use |
|:--|:--|:--|
| **Standalone exe** | Double-click `NokovBroadcaster.exe` | On site. Nothing is installed on the machine. |
| **Portable Python** | Double-click `run.bat` | You want to read or edit the code; uses the bundled `python\` folder, still zero install. |
| **Your own Python** | `python NokovBroadcaster.py` | You already have Python with PySide2. |

`run.bat` launches through `pythonw.exe`, so no console window appears. If the GUI does
not come up, run `run_debug.bat` instead: it keeps a console open and prints the error.

The exe is written to three places by the build script, all identical:
`dist\NokovBroadcaster.exe`, `NokovBroadcaster\NokovBroadcaster.exe`, and one level up
(`..\NokovBroadcaster.exe`).

---

## 3. First run, step by step

1. **Copy** either the whole `NokovBroadcaster` folder or just `NokovBroadcaster.exe`
   to the PC that runs the Nokov XING server. Double-click it.
2. **Connect page.** Fill in the mocap server IP and press **Connect**.
   * If the mocap software runs *on this PC*, just press **Connect locally** — the
     program tries `127.0.0.1` and then each of this machine's NIC addresses and fills
     in whichever one answers.
   * To pick manually, press **Detect local IP** for a list of local IPv4 addresses
     (with adapter names and link state).
   * On success the server's rigid bodies appear in the list with their IDs and names.
3. **Broadcast page.** Enter the receiver's IP and port (defaults are
   `192.168.1.123:22222`, matching the original script), then press **Start broadcast**.
   * If the receiver is on *this* PC, press **Use local NIC IP** (recommended — this is
     what the original script did) or **Use loopback 127.0.0.1**.
4. **Leave the wire format alone** unless you are also changing the receiver. The
   default already matches the old script.
5. Watch the status bar at the bottom: it shows connection state, broadcast state,
   frame rate, packets per second and body count.

If the mocap software has not been started yet you will see *"Connected · waiting for
data"* — that is normal; the Nokov server only pushes frames while it is playing or
recording.

---

## 4. Typical workflows

### Receiver on a different PC

1. On the receiver PC, note its IPv4 address.
2. On the mocap PC, add that address as a target on the **Broadcast** page.
3. Allow outbound UDP from `NokovBroadcaster.exe` in Windows Firewall if prompted.
4. Verify with `python tools\udp_monitor.py --port 22222` on the receiver PC.

### Commissioning a receiver with no hardware

1. **Connect** page → tick **Enable the built-in simulator** (pick a body count and rate).
2. **Broadcast** page → target `127.0.0.1:22222` → **Start broadcast**.
3. The receiver now sees a handful of virtual bodies orbiting; the 3D view and plots
   show the same data.

### Broadcast to two receivers at once

Add two rows on the **Broadcast** page — every enabled row gets its own copy of each
datagram. One malformed row does not stop the others; it is highlighted and counted in
the *Send errors* tile.

### Start automatically

Either tick **Connect automatically at start-up** and **Start broadcasting automatically
at start-up** on the **Log & Settings** page, or create a shortcut:

```bat
NokovBroadcaster.exe --headless --server 10.1.1.198 --target 192.168.1.123:22222 --autostart
```

`--headless` runs with no window at all (close it with Ctrl+C in the console, or
Task Manager). Command line values apply to that run only and are **not** written back
to `config.json`.

---

## 5. Command line reference

Both the exe and `NokovBroadcaster.py` accept the same options.

| Option | Meaning |
|:--|:--|
| `--server IP` | Mocap server address |
| `--target IP:PORT` | UDP target; may be repeated. Replaces the configured target list |
| `--format stq14\|stq20\|custom` | Wire format for this run |
| `--simulate [N]` | Use the built-in simulator with N bodies (default 4); no server connection |
| `--autostart` | Connect and start broadcasting immediately |
| `--headless` | No GUI; broadcast in the background |
| `--version`, `-h` | Version / help |

```bat
:: GUI, pre-filled, broadcasting immediately
NokovBroadcaster.exe --server 10.1.1.198 --target 192.168.1.123:22222 --autostart

:: Two receivers
NokovBroadcaster.exe --server 10.1.1.198 --target 192.168.1.123:22222 --target 192.168.1.50:33333

:: Background broadcaster, no window
NokovBroadcaster.exe --headless --server 10.1.1.198 --target 192.168.1.123:22222

:: No hardware: verify a receiver with 6 virtual bodies
NokovBroadcaster.exe --simulate 6 --target 127.0.0.1:22222 --autostart
```

Exit codes: `0` normal, `2` PySide2 missing, `3` could not connect in `--headless` mode.

---

## 6. What the target PC needs

**64-bit Windows 10 or 11. Nothing else.**

The exe carries everything, including the pieces people usually trip over:

| Component | Why it is bundled |
|:--|:--|
| `nokov_sdk.dll` + Python wrapper | The vendor SDK, kept at `nokov\lib\` inside the bundle |
| `python38.dll` + stdlib | The Python runtime |
| PySide2 / Qt5 | The GUI toolkit |
| `MSVCP140`, `VCRUNTIME140`, `VCRUNTIME140_1` (+5 more) | Placed at the root of the bundle, so the VC++ redistributable is **not** required |

You can re-verify this yourself at any time:

```bat
python tools\bundle_check.py
```

It unpacks the exe, **disables the System32 DLL search path**, and loads `nokov_sdk.dll`
using only files from the bundle. If that passes, nothing else is needed on the machine.

> Requires PyInstaller, so run it with your system Python, not `python\python.exe`.
> The Windows UCRT (`ucrtbase.dll`, `api-ms-win-crt-*`) is part of Windows and is not
> bundled — that is why Windows 10/11 is the floor.

---

## 7. Wire formats

Pick one on the **Broadcast** page. Each format keeps its **own parameter set**, so
switching back and forth never loses settings. The panel below the format selector
shows the exact byte layout and the predicted packet size for the current parameters.

### 7.1 `STQ standard (14 bytes/body)` — default

Identical to `NokovSDKClient_STQ.py`.

| Offset | Type | Meaning |
|-----:|:--|:--|
| 0 | int16 | `x  = position_x_metres × 2000` |
| 2 | int16 | `y  = position_y_metres × 2000` |
| 4 | int16 | `z  = position_z_metres × 2000` |
| 6 | int16 | `qx = quaternion_x × 1000` |
| 8 | int16 | `qy = quaternion_y × 1000` |
| 10 | int16 | `qz = quaternion_z × 1000` |
| 12 | int16 | `qw = quaternion_w × 1000` |

* All bodies are concatenated into **one datagram per frame**, ordered by **ascending
  body ID**, with **no header and no footer**.
* Values are truncated toward zero with `int()` and **saturated** to int16 — exactly
  what the original script did.
* The quaternion is normalised before packing.
* Little-endian (the Windows/Intel native order the original `struct.pack("hhhhhhh", …)`
  produced).

A receiver restores metres with `x * 0.0005` and the quaternion with `q * 0.001`.

Adjustable (defaults reproduce the table above — changing any of them changes the
packets, so tell the receiver side):

| Parameter | Default | Notes |
|:--|:--|:--|
| Position scale | 2000 | sent value = metres × factor |
| Quaternion scale | 1000 | |
| Normalise quaternion | on | |
| Saturate out-of-range | on | off wraps around the type range instead |
| Rounding | Truncate | Truncate / Round / Floor / Ceil |
| Byte order | Little-endian | Little / Big |
| Prefix frame number (uint32) | off | adds 4 bytes |
| Prefix body count (uint16) | off | adds 2 bytes |
| Custom header / footer (hex) | empty | for example `AA 55` |

### 7.2 `STQ extended (20 bytes/body)`

The standard record followed by `vx, vy, vz` as three int16 values — 20 bytes per body.

| Offset | Type | Meaning |
|-----:|:--|:--|
| 0..13 | int16 × 7 | as above |
| 14 | int16 | `vx = velocity_x_m_s × 1000` |
| 16 | int16 | `vy = velocity_y_m_s × 1000` |
| 18 | int16 | `vz = velocity_z_m_s × 1000` |

> The original `NokovSDKClient_STQ_test.py` wrote `vx_int = limit_to_signed_short(vx)`,
> forgetting the ×1000 its own docstring and print statement assumed — so it effectively
> transmitted zeros. This program implements the documented behaviour. Set
> **Velocity scale** to `1` if you need to reproduce the old quirk.

Velocity comes from the **Processing** page: `Auto` (use the SDK's extended data when the
server offers it, otherwise difference the positions), `SDK only`, or `Difference`.

### 7.3 `Custom binary`

Build the packet yourself:

* **Per-body field list** — add, remove, reorder. Each row has a source quantity
  (position, velocity, acceleration, roll/pitch/yaw, speed, body ID, marker count, mean
  error, status code…), a scalar type (int8 … float64), a scale, an offset and a clamp
  flag.
* **Packet level** — byte order, rounding, hex header/footer, optional frame number,
  body count and timestamp (each with a selectable type; the timestamp also has a unit).
* The defaults are the same 14 bytes as the standard format, so `custom` is a safe
  starting point for small tweaks.

Example — the layout `[header AA 55][id uint8][x,y,z float32]` gives 13 bytes per body
and a packet of `2 + 13 × N` bytes.

> UDP datagrams are limited to 65507 bytes. The program truncates and warns if a packet
> would exceed that; with the default format you can carry roughly 4600 bodies.

### Verifying what actually goes out

The **Broadcast** page shows the **last packet's first 32 bytes in hex**, live. On the
receiving side:

```bat
python tools\udp_monitor.py --port 22222
python tools\udp_monitor.py --port 22222 --format stq20
python tools\udp_monitor.py --port 22222 --format custom --fields id:uint8,x:float32,y:float32,z:float32
```

It decodes packets with the same layout rules and prints positions in metres.

---

## 8. Interface reference

Five pages, selected from the left-hand navigation.

### Connect

| Area | What it does |
|:--|:--|
| **Mocap server** | Server IP, frame delivery mode (**Callback** — the SDK pushes, recommended — or **Polling**), server timestamp unit, no-data timeout, and whether to read the SDK's velocity/acceleration/Euler data |
| **Detect local IP** | Lists every local IPv4 address with adapter name and link state |
| **Connect locally** | Tries `127.0.0.1`, the default-route NIC, then the other connected NICs, and keeps whichever answers |
| **Local IPv4 hint** | Always visible; `▶` marks the address currently configured. Refreshes every 2 s so plugging in a cable is picked up |
| **Status tiles** | Connection, SDK version, server, frame rate, frames received, duplicate frames, data source, timestamp unit |
| **Server information** | Host name, application and version, address, configured frame rate, marker sets, skeletons, force plates |
| **Rigid bodies on the server** | Double-click a row to *broadcast only that body* |
| **Simulator** | Generates virtual bodies (count and rate adjustable) for testing without hardware |

### Broadcast

| Area | What it does |
|:--|:--|
| **UDP targets** | One row per destination: enable, IP/host, port, note. Every enabled row receives each packet |
| **Use local NIC IP / Use loopback** | Adds this machine as a target, reusing the port already in the table |
| **Rate limit** | `Every frame` or a fixed Hz; optional *Send empty packets too*; optional local bind IP |
| **Wire format** | Format selector plus its generated parameter form |
| **Broadcast control** | Start/Stop, plus live tiles: send rate, bandwidth, packets sent, packet size, encode time, active targets, send errors |
| **Packet layout** | Byte-by-byte layout and predicted size for the current parameters |
| **Last packet** | First 32 bytes in hex, plus encoded size and time |

### Processing

| Area | What it does |
|:--|:--|
| **Body selection** | Minimum/maximum body ID, whitelist, blacklist, require markers, minimum marker count |
| **Robustness & kinematics** | Glitch threshold in mm, hold-previous-sample on glitch, maximum held frames, keep sending lost bodies, velocity source, Euler angle source |
| **Smoothing** | None / Moving average / Moving median / Exponential / **One-Euro adaptive**; window, coefficients, and optional quaternion smoothing |
| **Coordinate transform** | Axis mapping (`XYZ`…`ZYX`), per-axis sign, overall scale, per-axis offset in metres, rotation about Z |
| **Processing summary** | Live description of the active configuration plus running counters (frames, glitches, holds, filtered-out bodies) |

Defaults reproduce the original script exactly: `min ID = 0`, threshold `9000 mm`, hold
previous sample **on**, smoothing **off**, identity transform.

### Visualise

* **3D pose view** — perspective viewport showing body positions, orientation axes
  (RGB = XYZ), motion trails, marker cloud, ground grid and world axes.
  Body colour shows status: blue/green = OK, amber = held, red = glitch.
  * **Left drag** orbit · **right/middle drag** pan · **wheel** zoom ·
    **double-click** fit · **R** reset.
  * Toolbar: body labels, motion trails, marker cloud, pose axes (with axis length),
    trail length, **Fit view**, **Reset view**.
* **Live plots** — toggle channel groups (Position / Velocity / Acceleration / Euler
  angles / Speed) and pick the body from the drop-down or by clicking it in the 3D view.
  Adjustable time window.
* **Rigid body data** — ID, name, status, position, speed, marker count, mean marker
  error, quaternion and accumulated glitch count per body.

### Log & Settings

* **Log** — level filter, auto-scroll, clear, copy all, open the log folder.
* **Configuration profiles** — save every setting under a name, load or delete;
  stored as `%APPDATA%\NokovBroadcaster\profiles\*.json`.
* **Start-up behaviour** — interface language, connect automatically, start broadcasting
  automatically, write a log file.
* **About** — versions and the paths in use.

---

## 9. Language switching

Two ways, both **immediate**:

* The **🌐 button** in the status bar (bottom right) toggles — it shows the language you
  would switch *to*;
* **Log & Settings → Start-up behaviour → Interface language**.

The choice is saved to `config.json` and used on the next start.

Switching **rebuilds every page in place**: navigation, table headers, format names,
parameter labels, tooltips, the status bar and the packet layout preview all follow. The
engine thread, the SDK session and the UDP socket live in `AppContext`, so **a running
broadcast is not interrupted**.

---

## 10. Settings, profiles, portable mode

| Item | Location |
|:--|:--|
| Main configuration | `%APPDATA%\NokovBroadcaster\config.json` |
| Profiles | `%APPDATA%\NokovBroadcaster\profiles\*.json` |
| Log | `%APPDATA%\NokovBroadcaster\logs\nokov_broadcaster.log` (2 MB × 3, rotating) |

Most changes take effect **immediately** — the engine re-reads the configuration on every
frame, so there is no restart button.

**Portable mode:** drop an empty file named `portable.flag` next to the exe and settings
and logs move to `<exe folder>\NokovBroadcasterData\`, so the whole folder can live on a
USB stick.

---

## 11. Differences from the original script

| | Original `NokovSDKClient_STQ.py` | NokovBroadcaster |
|:--|:--|:--|
| Default packet | 14 bytes/body | **identical, byte for byte** |
| Changing parameters | edit constants, restart | edit in the GUI, live |
| Body filtering | hard-coded `body_id >= 0` | same default, plus range / whitelist / blacklist |
| Glitch handling | 9000 mm threshold, hold previous | same default, configurable, plus smoothing |
| Velocity | not sent | optional 20-byte format or any custom layout |
| Coordinates | fixed mm → m | identity by default; axis remap, scale, offset, rotation available |
| Running it | console script with prompts | GUI, or a standalone exe, or `--headless` |
| Data inspection | printed text | 3D view, plots, table, hex packet preview |

### Deliberate carry-overs

* Quaternions are normalised, positions use `× 2000` with `int()` truncation and int16
  saturation.
* Frames with a repeated frame number are ignored.
* No packet is sent when there are no rigid bodies (unless you enable *Send empty packets too*).
* Bodies are concatenated in ascending ID order.

---

## 12. Building from source

```
NokovBroadcaster\
├─ NokovBroadcaster.exe       # standalone build (build.ps1 also copies it one level up)
├─ run.bat / run_debug.bat    # launch with the bundled portable Python
├─ NokovBroadcaster.py        # source entry point
├─ NokovBroadcaster.spec      # PyInstaller specification
├─ build.ps1                  # one-command build
├─ python\                    # bundled CPython 3.8.10 + PySide2 (~67 MB)
├─ nokov\                     # vendored Nokov SDK (nokovsdk.py + lib\nokov_sdk.dll)
├─ assets\icon.ico
├─ app\
│  ├─ __main__.py             # start-up flow and command line
│  ├─ config.py               # every setting, JSON persistence, profiles
│  ├─ i18n.py                 # Chinese/English translation table
│  ├─ core\                   # GUI-independent logic
│  │  ├─ sdk_client.py        #   Nokov SDK session
│  │  ├─ hub.py               #   thread-safe frame exchange and history
│  │  ├─ pipeline.py          #   processing pipeline
│  │  ├─ filters.py           #   body selection and hold state
│  │  ├─ transform.py         #   coordinate transform
│  │  ├─ math3d.py            #   quaternions and filters (pure Python, no numpy)
│  │  ├─ netinfo.py           #   local IPv4 enumeration via Win32
│  │  ├─ engine.py            #   worker thread: frame → process → encode → send
│  │  ├─ broadcaster.py       #   multi-target UDP sender
│  │  ├─ simulator.py         #   synthetic frame source
│  │  └─ formats\             #   pluggable encoders (stq14 / stq20 / custom)
│  └─ gui\                    # PySide2 interface
└─ tools\                     # test, build and translation utilities
```

### Rebuild the portable runtime

```bat
python tools\make_portable_python.py
```

Downloads the official embedded CPython 3.8.10 and the PySide2 wheels, unpacks them into
`python\Lib\site-packages`, then deletes unused Qt modules following the **PE import
dependency closure** (WebEngine is 97 MB on its own). This takes it from 332 MB to about
67 MB. Guessing the keep-list by hand does not work: `pyside2.abi3.dll` links against
`Qt5Qml.dll` even though this application never uses QML.

### Rebuild the exe

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1 -Clean
```

Add `-Console` to build a variant that prints start-up errors to a terminal.

### Tests and utilities

```bat
python tools\selftest.py      :: core logic, byte-exact format parity, local IP enumeration
python tools\guitest.py       :: GUI + UDP round trip + language switching (uses a temp config)
python tools\exetest.py       :: end-to-end test of the built exe (--python tests the source)
python tools\bundle_check.py  :: proves the exe is self-contained
python tools\i18n_check.py    :: lists untranslated strings and duplicate keys
python tools\i18n_dedupe.py   :: removes duplicate keys from the translation table
python tools\udp_monitor.py --port 22222   :: standalone UDP receive/decode tool
```

### Adding a UI string in both languages

Keys in `app\i18n.py` are the **Chinese source text**. Wrap the string in `tr()` and add an
entry to `EN`; anything missing falls back to Chinese rather than failing.
`python tools\i18n_check.py` reports what is left.

### Adding a wire format

1. Create `app\core\formats\myformat.py`, subclass `Encoder`, implement
   `default_params` / `param_specs` / `encode` / `packet_size` / `layout_lines`.
2. Call `register(MyEncoder())` at the end of the file.
3. Add `from . import myformat` to `app\core\formats\__init__.py`.

The settings form in the GUI is generated from `param_specs()`, so no GUI code is needed.

---

## 13. Troubleshooting

| Symptom | Things to check |
|:--|:--|
| **Connected but no data** | The mocap software must be **playing or recording**; it does not push frames while idle. Also check the server IP and the no-data timeout. |
| **Cannot connect at all** | Wrong IP, wrong subnet, Windows Firewall, or the Nokov software is not running. The status tile and the log show the SDK's return code and a plain-language explanation. |
| **Failed to load `nokov_sdk.dll`** | Should not happen with the exe (the VC++ runtime is bundled). For the source/Python version, install `VC_redist.x64.exe` from the original SDK folder. |
| **Receiver gets nothing** | Is the target row ticked and enabled? Did you press **Start broadcast**? Does the status bar say *Broadcasting*? Is the receiver bound to that port? Is outbound UDP blocked? *Last packet* showing hex means the program really did send. |
| **Values look wrong** | Confirm the receiver's scale factors (position `0.0005`, quaternion `0.001`) match the format parameters, and check whether a coordinate transform is enabled. |
| **Positions jump to absurd values** | That is the classic tracking glitch; the default 9000 mm threshold holds the previous sample. Watch the *Glitches* column in the data table. |
| **Body count in the packet changes** | A body disappeared mid-run. Enable *Keep sending the last pose when a body vanishes* on the Processing page to keep the packet structure stable. |
| **Packet too large** | UDP caps at 65507 bytes. Reduce bodies or fields; the program truncates and warns. |
| **GUI does not appear** (`run.bat`) | Use `run_debug.bat` to see the error. |
| **`--headless` prints nothing** | The exe attaches to the console it was launched from; start it from `cmd`/PowerShell rather than by double-clicking. |

---

## 14. Machine-specific notes

Two pre-existing environment problems were found and fixed while building this project.
Both are reversible (backups kept beside the originals) and neither affects the packaged
exe, which carries its own runtime.

1. **PySide2 would not import.** This machine had **Python 3.8.0**, whose `python38.dll`
   is missing the `Py_CompileString` export (restored in Python 3.8.1). PySide2's
   stable-ABI extension needs it, giving
   `ImportError: DLL load failed while importing shiboken2`.
   Replaced with the **3.8.10** `python38.dll` / `python3.dll` (same minor version, ABI
   compatible):
   * `…\Python38\python38.dll.bak-3.8.0`
   * `…\Python38\python3.dll.bak-3.8.0`

2. **A stale `vcruntime140.dll` (14.12) in the Python folder** was shadowing the system
   14.50 build. Replaced with the system copy, backed up as
   `vcruntime140.dll.bak-stale-14.12`.

---
---

# 中文文档

[English](#nokovbroadcaster) · **中文**

一个带图形界面的 Windows 程序：从 **Nokov XING** 服务端接收动捕数据，处理后按你指定的
格式通过 **UDP 广播**出去。

---

## 目录

- [1. 主要特点](#1-主要特点)
- [2. 三种运行方式](#2-三种运行方式)
- [3. 首次使用步骤](#3-首次使用步骤)
- [4. 常见使用场景](#4-常见使用场景)
- [5. 命令行参数](#5-命令行参数)
- [6. 目标电脑需要什么](#6-目标电脑需要什么)
- [7. 广播数据格式](#7-广播数据格式)
- [8. 界面说明](#8-界面说明)
- [9. 中英文切换](#9-中英文切换)
- [10. 配置、方案与便携模式](#10-配置方案与便携模式)
- [11. 与旧脚本的差异](#11-与旧脚本的差异)
- [12. 从源码构建](#12-从源码构建)
- [13. 常见问题](#13-常见问题)
- [14. 本机环境修复记录](#14-本机环境修复记录)

---

## 1. 主要特点

* **默认格式与 `NokovSDKClient_STQ.py` 完全一致** —— 由 `tools/selftest.py` 自动比对
  40 组随机数据，外加饱和截断、退化四元数、截断取整等边界用例。
* **目标电脑什么都不用装** —— 单文件 exe 内置了 Nokov SDK、Python 运行时、PySide2/Qt
  以及 Visual C++ 运行库；`run.bat` 让 Python 版也有同样的零安装体验。
* **实时 3D 姿态视图、曲线和数据表格**，方便在数据发出去之前先看一眼。
* **内置模拟数据源**，没有动捕硬件也能调试接收端。
* **中英文即时切换**，不会中断正在进行的广播。

---

## 2. 三种运行方式

| 方式 | 操作 | 适用场景 |
|:--|:--|:--|
| **免安装 exe** | 双击 `NokovBroadcaster.exe` | 现场使用，目标机没装任何东西 |
| **便携 Python** | 双击 `run.bat` | 想阅读/修改代码；用文件夹里的 `python\`，同样零安装 |
| **自带 Python** | `python NokovBroadcaster.py` | 你本来就有 Python + PySide2 环境 |

`run.bat` 通过 `pythonw.exe` 启动，不弹黑窗口。如果界面没出来，改用 `run_debug.bat`，
它会保留控制台并打印错误。

打包脚本会把完全相同的 exe 写到三个位置：`dist\NokovBroadcaster.exe`、
`NokovBroadcaster\NokovBroadcaster.exe`，以及上一级目录 `..\NokovBroadcaster.exe`。

---

## 3. 首次使用步骤

1. 把整个 `NokovBroadcaster` 文件夹（或只把 `NokovBroadcaster.exe`）拷到运行 **Nokov XING
   服务端** 的电脑上，双击运行。
2. **连接** 页：填写动捕服务器 IP，点 **连接**。
   * **动捕软件就在本机？** 直接点 **「本机一键连接」** —— 程序会依次尝试 `127.0.0.1`
     和本机各网卡地址，自动填入能连上的那个。
   * 想手动挑，点 **「检测本机 IP」**，会列出本机所有 IPv4（含网卡名与连接状态）。
   * 连上后服务器的刚体 ID 与名称会出现在列表里。
3. **广播** 页：填写接收端 IP 与端口（默认 `192.168.1.123:22222`，与旧脚本一致），
   点 **「开始广播」**。
   * 接收端也在本机时，点 **「填入本机网卡 IP」**（推荐，等于旧脚本的写法）
     或 **「填入本机回环 127.0.0.1」**。
4. **不要动数据格式**，除非接收端也一起改。默认值已经和旧脚本一致。
5. 看底部状态栏：连接状态、广播状态、帧率、包/秒、刚体数量都在那里。

如果动捕软件还没开始采集，会显示 *"已连接 · 等待数据"* —— 这是正常的，
Nokov 服务端只在播放/采集时才推帧。

---

## 4. 常见使用场景

### 接收端在另一台电脑

1. 在接收端电脑上查到它的 IPv4 地址。
2. 在动捕电脑的 **广播** 页把该地址加为一个目标。
3. Windows 防火墙弹出提示时，允许 `NokovBroadcaster.exe` 的出站 UDP。
4. 在接收端电脑上用 `python tools\udp_monitor.py --port 22222` 验证。

### 没有硬件时调试接收端

1. **连接** 页 → 勾选 **「启用模拟数据源」**（可设刚体数与速率）。
2. **广播** 页 → 目标填 `127.0.0.1:22222` → **「开始广播」**。
3. 接收端会看到几个做圆周运动的虚拟刚体；3D 视图和曲线显示同样的数据。

### 同时发给两个接收端

在 **广播** 页加两行即可，每个勾选启用的目标都会收到一份完整报文。
某一行填错不会影响其它行，那行会被标红并计入 *发送错误* 统计。

### 开机自动广播

可以勾选 **日志与配置** 页的 *启动后自动连接*、*启动后自动开始广播*，也可以做快捷方式：

```bat
NokovBroadcaster.exe --headless --server 10.1.1.198 --target 192.168.1.123:22222 --autostart
```

`--headless` 完全不显示窗口（在控制台按 Ctrl+C 或从任务管理器结束）。
命令行参数只对本次运行生效，**不会写回 `config.json`**。

---

## 5. 命令行参数

exe 与 `NokovBroadcaster.py` 支持的参数完全相同。

| 参数 | 说明 |
|:--|:--|
| `--server IP` | 动捕服务器地址 |
| `--target IP:PORT` | UDP 目标，可重复指定；给了就替换配置里的目标列表 |
| `--format stq14\|stq20\|custom` | 本次运行使用的格式 |
| `--simulate [N]` | 使用内置模拟数据源（默认 4 个刚体），不连服务器 |
| `--autostart` | 启动后立即连接并广播 |
| `--headless` | 不显示界面，仅后台广播 |
| `--version`、`-h` | 版本 / 帮助 |

```bat
:: 图形界面，预填参数并立即广播
NokovBroadcaster.exe --server 10.1.1.198 --target 192.168.1.123:22222 --autostart

:: 两个接收端
NokovBroadcaster.exe --server 10.1.1.198 --target 192.168.1.123:22222 --target 192.168.1.50:33333

:: 后台广播，无窗口
NokovBroadcaster.exe --headless --server 10.1.1.198 --target 192.168.1.123:22222

:: 无硬件，用 6 个虚拟刚体验证接收端
NokovBroadcaster.exe --simulate 6 --target 127.0.0.1:22222 --autostart
```

退出码：`0` 正常，`2` 缺少 PySide2，`3` `--headless` 模式下连接失败。

---

## 6. 目标电脑需要什么

**64 位 Windows 10 / 11。其它什么都不需要。**

exe 里已经包含所有东西，包括那些最容易踩坑的部分：

| 组件 | 为什么内置 |
|:--|:--|
| `nokov_sdk.dll` + Python 封装 | 厂商 SDK，在包内保持 `nokov\lib\` 这个相对路径 |
| `python38.dll` + 标准库 | Python 运行时 |
| PySide2 / Qt5 | 界面框架 |
| `MSVCP140`、`VCRUNTIME140`、`VCRUNTIME140_1` 等 8 个 | 放在包根目录，**不需要**安装 VC++ 运行库 |

可以随时自己复检：

```bat
python tools\bundle_check.py
```

它会解包 exe，**临时屏蔽 System32 的 DLL 搜索路径**，只用包内文件加载 `nokov_sdk.dll`。
能通过就说明目标机不需要任何预装组件。

> 该脚本依赖 PyInstaller，请用系统 Python 运行，不要用 `python\python.exe`。
> Windows 的 UCRT（`ucrtbase.dll`、`api-ms-win-crt-*`）属于操作系统，没有打包，
> 这就是要求 Windows 10/11 的原因。

---

## 7. 广播数据格式

在 **广播** 页选择。每种格式**各自保存一套参数**，来回切换不会丢设置。
格式选择框下方会实时显示当前参数的逐字节布局与预计单包长度。

### 7.1 `STQ 标准 (14 字节/刚体)` —— 默认

与 `NokovSDKClient_STQ.py` 完全相同。

| 偏移 | 类型 | 含义 |
|-----:|:--|:--|
| 0 | int16 | `x  = 位置X(米) × 2000` |
| 2 | int16 | `y  = 位置Y(米) × 2000` |
| 4 | int16 | `z  = 位置Z(米) × 2000` |
| 6 | int16 | `qx = 四元数x × 1000` |
| 8 | int16 | `qy = 四元数y × 1000` |
| 10 | int16 | `qz = 四元数z × 1000` |
| 12 | int16 | `qw = 四元数w × 1000` |

* 所有刚体按 **ID 升序** 拼接成 **每帧一个 UDP 包**，**没有包头包尾**。
* 数值用 `int()` **截断取整**，超出 int16 范围时 **饱和到 ±32767/−32768** —— 与旧脚本一致。
* 四元数发送前 **归一化**。
* 小端字节序（就是旧脚本 `struct.pack("hhhhhhh", …)` 在 Windows 上的原生顺序）。

接收端用 `x * 0.0005` 还原米、`q * 0.001` 还原四元数。

可调参数（默认值就是上表；改任何一项都会改变报文，请与接收端同步确认）：

| 参数 | 默认 | 说明 |
|:--|:--|:--|
| 位置缩放 | 2000 | 发送值 = 米 × 系数 |
| 四元数缩放 | 1000 | |
| 发送前归一化四元数 | 开 | |
| 超出范围时饱和截断 | 开 | 关闭则按类型范围回绕 |
| 取整方式 | 截断 | 截断 / 四舍五入 / 向下 / 向上 |
| 字节序 | 小端 | 小端 / 大端 |
| 包首加入帧号 (uint32) | 关 | 多 4 字节 |
| 包首加入刚体数量 (uint16) | 关 | 多 2 字节 |
| 自定义包头/包尾 | 空 | 十六进制，例如 `AA 55` |

### 7.2 `STQ 扩展 (20 字节/刚体，含速度)`

在标准记录后追加 `vx, vy, vz` 三个 int16，共 20 字节/刚体。

| 偏移 | 类型 | 含义 |
|-----:|:--|:--|
| 0..13 | int16 × 7 | 同上 |
| 14 | int16 | `vx = 速度X(m/s) × 1000` |
| 16 | int16 | `vy = 速度Y(m/s) × 1000` |
| 18 | int16 | `vz = 速度Z(m/s) × 1000` |

> 原测试脚本 `NokovSDKClient_STQ_test.py` 里写的是 `vx_int = limit_to_signed_short(vx)`，
> 漏乘了它自己注释和打印逻辑都假定的 1000，所以实际发出去的几乎是 0。
> 本程序按其**文档语义**实现。如果你要复现旧脚本那个行为，把 **速度缩放改成 1** 即可。

速度来源在 **数据处理** 页选择：`自动`（服务器提供扩展数据时优先使用，否则用位置差分）、
`仅使用 SDK`、`由位置差分计算`。

### 7.3 `自定义二进制格式`

完全自己拼报文：

* **刚体字段列表** —— 可添加、删除、上下移动。每行可设置数据量（位置/速度/加速度/
  欧拉角/速度大小/ID/标记点数/误差/状态码…）、类型（int8…float64）、缩放、偏移、是否饱和。
* **报文级** —— 字节序、取整方式、十六进制包头包尾，以及可选的帧号、刚体数量、时间戳
  （各自可选类型，时间戳还有单位）。
* 默认值与标准 14 字节格式等价，可以拿它当起点做小改动。

例如布局 `[包头 AA 55][id uint8][x,y,z float32]`：每刚体 13 字节，整包 `2 + 13 × N` 字节。

> UDP 单包上限 65507 字节。超出时程序会截断并告警；默认格式大约可携带 4600 个刚体。

### 验证实际发出去的内容

**广播** 页实时显示 **最近一包前 32 字节的十六进制**。接收端这边可以：

```bat
python tools\udp_monitor.py --port 22222
python tools\udp_monitor.py --port 22222 --format stq20
python tools\udp_monitor.py --port 22222 --format custom --fields id:uint8,x:float32,y:float32,z:float32
```

它用同一套布局规则解码，并把位置换算成米打印出来。

---

## 8. 界面说明

左侧导航共五个页面。

### 连接

| 区域 | 作用 |
|:--|:--|
| **动捕服务器** | 服务器 IP、帧接收方式（**回调**——SDK 主动推送，推荐；或 **主动读取**）、服务器时间戳单位、无数据超时、是否读取 SDK 的速度/加速度/欧拉角 |
| **检测本机 IP** | 列出本机所有 IPv4，带网卡名称与连接状态 |
| **本机一键连接** | 依次尝试 `127.0.0.1`、默认出口网卡、其它已连接网卡，连上就填进去 |
| **本机 IPv4 提示** | 常驻显示，`▶` 标出当前配置的地址；每 2 秒刷新，插网线能立刻反映 |
| **状态卡片** | 连接状态、SDK 版本、服务器、帧率、已接收帧、重复帧、数据来源、时间戳单位 |
| **服务器信息** | 主机名、应用程序与版本、地址、帧率设置、标记点集合、骨架、力台 |
| **服务器刚体列表** | 双击一行即可 *仅广播该刚体* |
| **模拟数据源** | 生成虚拟刚体（数量和速率可调），没有硬件也能测试 |

### 广播

| 区域 | 作用 |
|:--|:--|
| **UDP 广播目标** | 一行一个目标：启用、IP/主机名、端口、备注。启用的每一行都会收到完整报文 |
| **填入本机网卡 IP / 回环** | 把本机加为目标，端口沿用表格里已有的 |
| **发送限速** | `每帧都发` 或指定 Hz；可选 *没有刚体时也发送空包*；可选本机绑定 IP |
| **广播数据格式** | 格式选择框 + 自动生成的参数表单 |
| **广播控制** | 开始/停止，以及实时统计：发送速率、带宽、累计包数、报文长度、编码耗时、启用目标、发送错误 |
| **报文结构预览** | 当前参数下的逐字节布局与预计长度 |
| **最近发出的报文** | 前 32 字节十六进制，以及编码长度与耗时 |

### 数据处理

| 区域 | 作用 |
|:--|:--|
| **刚体选择** | 最小/最大 ID、白名单、黑名单、要求有标记点、最少标记点数 |
| **鲁棒性与运动学** | 异常值阈值（mm）、异常时保持上一帧、最多保持帧数、丢失后继续发送、速度来源、欧拉角来源 |
| **平滑滤波** | 不平滑 / 滑动平均 / 滑动中值 / 指数平滑 / **One-Euro 自适应**；窗口、系数，可选平滑姿态四元数 |
| **坐标系变换** | 轴映射（`XYZ`…`ZYX`）、各轴取反、整体缩放、各轴偏移（米）、绕 Z 轴旋转 |
| **处理摘要** | 实时描述当前生效的配置，以及累计统计（帧数、异常、保持、被过滤丢弃） |

默认值与旧脚本一致：`最小 ID = 0`、阈值 `9000 mm`、保持上一帧 **开**、平滑 **关**、恒等变换。

### 可视化

* **3D 姿态视图** —— 透视视口，显示刚体位置、姿态坐标轴（RGB 对应 XYZ）、运动拖尾、
  标记点云、地面网格与世界坐标轴。颜色表示状态：蓝/绿 = 正常，琥珀 = 保持，红 = 异常。
  * **左键拖动** 旋转 · **右键/中键拖动** 平移 · **滚轮** 缩放 ·
    **双击** 自动适配 · **R** 重置。
  * 工具栏：刚体标签、运动拖尾、标记点云、姿态坐标轴（含轴长）、拖尾长度、
    **自动适配视角**、**重置视角**。
* **实时曲线** —— 按分组勾选通道（位置 / 速度 / 加速度 / 姿态角 / 速度大小），
  用下拉框选刚体或在 3D 视图里点选；时间窗口可调。
* **刚体数据** —— 每个刚体的 ID、名称、状态、位置、速度、标记点数、标记点平均误差、
  四元数与累计异常次数。

### 日志与配置

* **运行日志** —— 级别过滤、自动滚动、清空显示、复制全部、打开日志文件夹。
* **参数配置方案** —— 把全部设置存成具名方案，可载入 / 删除；
  存放于 `%APPDATA%\NokovBroadcaster\profiles\*.json`。
* **启动行为** —— 界面语言、启动后自动连接、启动后自动开始广播、是否写日志文件。
* **关于** —— 版本信息与当前使用的路径。

---

## 9. 中英文切换

两种方式，**都是即时生效**：

* 状态栏右下角的 **🌐 按钮** —— 点一下切换（按钮上写的是"将要切换到的语言"）；
* **日志与配置 → 启动行为 → 界面语言** 下拉框。

选择会写入 `config.json`，下次启动直接生效。

切换时会**就地重建所有页面**：导航栏、表格表头、格式名称、参数标签、工具提示、
状态栏、报文布局预览全部跟着变。引擎线程、SDK 会话和 UDP 套接字活在 `AppContext` 里，
所以 **正在进行的广播不会中断**。

---

## 10. 配置、方案与便携模式

| 内容 | 位置 |
|:--|:--|
| 主配置 | `%APPDATA%\NokovBroadcaster\config.json` |
| 方案 | `%APPDATA%\NokovBroadcaster\profiles\*.json` |
| 日志 | `%APPDATA%\NokovBroadcaster\logs\nokov_broadcaster.log`（2 MB × 3 滚动） |

大多数修改**立即生效** —— 引擎每帧都会重新读取配置，没有"重启生效"这回事。

**绿色便携模式**：在 exe 同目录放一个空的 `portable.flag` 文件，
配置与日志就会写到 `<exe 目录>\NokovBroadcasterData\`，整个文件夹可以直接拷到 U 盘里带走。

---

## 11. 与旧脚本的差异

| | 旧脚本 `NokovSDKClient_STQ.py` | NokovBroadcaster |
|:--|:--|:--|
| 默认报文 | 14 字节/刚体 | **逐字节相同** |
| 改参数 | 改源码常量后重启 | 界面即时修改 |
| 刚体过滤 | 硬编码 `body_id >= 0` | 同样默认值，另加范围 / 白名单 / 黑名单 |
| 异常处理 | 9000 mm 阈值，保持上一帧 | 同样默认值，可调，另加平滑滤波 |
| 速度 | 不发送 | 可选 20 字节格式，或自定义任意布局 |
| 坐标系 | 固定 mm → m | 默认恒等；可加轴映射、缩放、偏移、旋转 |
| 运行方式 | 控制台 + 交互输入 | 图形界面，或独立 exe，或 `--headless` |
| 数据查看 | 打印文本 | 3D 视图、曲线、表格、报文十六进制预览 |

### 有意保留的旧行为

* 四元数归一化，位置 `× 2000` 用 `int()` 截断并饱和到 int16。
* 相同帧号的重复帧会被忽略。
* 没有刚体时不发送空包（除非打开 *没有刚体时也发送空包*）。
* 刚体按 ID 升序拼接。

---

## 12. 从源码构建

```
NokovBroadcaster\
├─ NokovBroadcaster.exe       # 免安装程序（build.ps1 同时复制一份到上一级目录）
├─ run.bat / run_debug.bat    # 用内置便携 Python 启动
├─ NokovBroadcaster.py        # 源码入口
├─ NokovBroadcaster.spec      # PyInstaller 配置
├─ build.ps1                  # 一键打包
├─ python\                    # 内置 CPython 3.8.10 + PySide2（约 67 MB）
├─ nokov\                     # 内置 Nokov SDK（nokovsdk.py + lib\nokov_sdk.dll）
├─ assets\icon.ico
├─ app\
│  ├─ __main__.py             # 启动流程与命令行
│  ├─ config.py               # 全部设置项、JSON 持久化、方案
│  ├─ i18n.py                 # 中英文翻译表
│  ├─ core\                   # 与界面无关的核心逻辑
│  │  ├─ sdk_client.py        #   Nokov SDK 会话
│  │  ├─ hub.py               #   线程间帧交换与历史缓存
│  │  ├─ pipeline.py          #   处理流水线
│  │  ├─ filters.py           #   刚体筛选与保持状态
│  │  ├─ transform.py         #   坐标变换
│  │  ├─ math3d.py            #   四元数与滤波（纯 Python，无 numpy 依赖）
│  │  ├─ netinfo.py           #   本机 IPv4 枚举（Win32 API）
│  │  ├─ engine.py            #   工作线程：取帧 → 处理 → 编码 → 发送
│  │  ├─ broadcaster.py       #   多目标 UDP 发送
│  │  ├─ simulator.py         #   模拟数据源
│  │  └─ formats\             #   可插拔格式（stq14 / stq20 / custom）
│  └─ gui\                    # PySide2 界面
└─ tools\                     # 测试、打包、翻译检查等工具
```

### 重新生成便携 Python 运行时

```bat
python tools\make_portable_python.py
```

它会下载官方嵌入式 CPython 3.8.10 与 PySide2 轮子，解压到 `python\Lib\site-packages`，
然后按 **PE 导入依赖闭包** 删掉用不到的 Qt 模块（光 WebEngine 就 97 MB），
把体积从 332 MB 压到约 67 MB。手工维护"保留清单"是行不通的：
`pyside2.abi3.dll` 硬链接了 `Qt5Qml.dll`，尽管本程序完全不用 QML。

### 重新打包 exe

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1 -Clean
```

加 `-Console` 可以打一个会把启动错误打印到终端的调试版本。

### 测试与工具

```bat
python tools\selftest.py      :: 核心逻辑、格式逐字节一致性、本机网络枚举
python tools\guitest.py       :: 界面 + UDP 端到端 + 中英文切换（用临时配置，不动你的设置）
python tools\exetest.py       :: 已打包 exe 的端到端测试（--python 则测源码）
python tools\bundle_check.py  :: 证明 exe 是自包含的
python tools\i18n_check.py    :: 列出未翻译的字符串与重复键
python tools\i18n_dedupe.py   :: 清理翻译表里的重复键
python tools\udp_monitor.py --port 22222   :: 独立 UDP 接收解码工具
```

### 新增一条双语界面文字

`app\i18n.py` 里的键就是 **中文原文**。把字符串用 `tr()` 包起来，再往 `EN` 字典加一条；
缺条目会原样回退到中文，不会报错。用 `python tools\i18n_check.py` 检查遗漏。

### 增加一种广播格式

1. 新建 `app\core\formats\myformat.py`，继承 `Encoder`，实现
   `default_params` / `param_specs` / `encode` / `packet_size` / `layout_lines`。
2. 文件末尾调用 `register(MyEncoder())`。
3. 在 `app\core\formats\__init__.py` 里加 `from . import myformat`。

界面上的参数表单由 `param_specs()` 自动生成，不需要写 GUI 代码。

---

## 13. 常见问题

| 现象 | 检查什么 |
|:--|:--|
| **已连接但一直没有数据** | 动捕软件必须处于 **播放/采集** 状态，空闲时不推帧。也检查服务器 IP 与无数据超时设置。 |
| **完全连不上** | IP 或网段不对、Windows 防火墙、动捕软件没启动。状态卡片和日志会给出 SDK 返回码及中文解释。 |
| **加载 `nokov_sdk.dll` 失败** | 用 exe 不应出现（运行库已内置）。用源码/Python 版时，装一下原 SDK 目录里的 `VC_redist.x64.exe`。 |
| **接收端收不到** | 目标行勾选了吗？点过 **开始广播** 吗？状态栏显示 *广播中* 吗？接收端绑定的是那个端口吗？出站 UDP 被拦了吗？*最近发出的报文* 有十六进制就说明程序确实发出去了。 |
| **数值不对** | 确认接收端的还原系数（位置 `0.0005`、四元数 `0.001`）与格式参数一致，再看有没有开着坐标变换。 |
| **位置突然跳到离谱的值** | 典型的跟踪跳变；默认 9000 mm 阈值会保持上一帧。看数据表里的 *异常累计* 列。 |
| **包里刚体数量会变** | 有刚体中途丢失了。在数据处理页打开 *刚体丢失后继续发送最后位姿*，包结构就稳定了。 |
| **报文过大** | UDP 上限 65507 字节。减少刚体或字段；程序会截断并告警。 |
| **`run.bat` 后界面不出来** | 改用 `run_debug.bat` 看报错。 |
| **`--headless` 没有任何输出** | exe 会挂到启动它的控制台上，请从 `cmd`/PowerShell 启动，不要双击。 |

---

## 14. 本机环境修复记录

构建过程中发现并修复了两个**与代码无关**的环境问题。两处都留了备份可以回滚，
而且**都不影响打包出来的 exe**（它自带运行库）。

1. **PySide2 无法导入。** 本机是 **Python 3.8.0**，其 `python38.dll` 缺少
   `Py_CompileString` 导出（Python 3.8.1 起才恢复），而 PySide2 的稳定 ABI 扩展需要它，
   报错 `ImportError: DLL load failed while importing shiboken2`。
   已换成 **3.8.10** 的 `python38.dll` / `python3.dll`（同一小版本，ABI 兼容）：
   * `…\Python38\python38.dll.bak-3.8.0`
   * `…\Python38\python3.dll.bak-3.8.0`

2. **Python 目录里一份过旧的 `vcruntime140.dll`（14.12）** 会抢在系统 14.50 之前被加载。
   已替换为系统版本，备份为 `vcruntime140.dll.bak-stale-14.12`。
