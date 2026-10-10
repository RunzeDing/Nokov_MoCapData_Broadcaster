"""Application bootstrap (run via ``python -m app`` or ``NokovBroadcaster.exe``).

Command line
------------
``NokovBroadcaster.exe`` with no arguments starts the full GUI.  Optional
switches make it usable from a shortcut or as a headless broadcaster::

    --server 10.1.1.198           动捕服务器 IP
    --target 192.168.1.123:22222  广播目标（可重复；给定时替换配置里的目标）
    --format stq14|stq20|custom   广播格式
    --simulate [N]                使用 N 个虚拟刚体（默认 4），不连服务器
    --autostart                   启动后自动连接并开始广播
    --headless                    不显示界面，仅后台广播（Ctrl+C 退出）

Overrides provided on the command line are applied in memory only and are not
written back to ``config.json``.
"""

from __future__ import annotations

from .i18n import tr

import argparse
import logging
import os
import sys
import traceback

# The vendor SDK prints while it is imported, and a windowed build has no
# console, so make sure sys.stdout/stderr exist before anything else runs.
from .logging_setup import ensure_std_streams

ensure_std_streams()

from .config import AppConfig, BroadcastTarget  # noqa: E402
from .logging_setup import setup_logging  # noqa: E402
from .paths import config_path, ensure_dirs, sdk_package_dir  # noqa: E402
from .version import APP_NAME, APP_TITLE, __version__  # noqa: E402

log = logging.getLogger("nokov.main")


def _install_excepthook() -> None:
    def hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logging.getLogger("nokov").critical(tr("未捕获异常:\n%s"), text)

    sys.excepthook = hook


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description=tr("%s v%s - Nokov 动捕数据广播器") % (APP_TITLE, __version__),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            tr("示例:\n"
            "  NokovBroadcaster.exe\n"
            "  NokovBroadcaster.exe --server 10.1.1.198 --target 192.168.1.123:22222 --autostart\n"
            "  NokovBroadcaster.exe --headless --server 10.1.1.198 --target 127.0.0.1:22222\n"
            "  NokovBroadcaster.exe --simulate 6 --target 127.0.0.1:22222 --autostart\n")
        ),
    )
    parser.add_argument("--server", metavar="IP", help=tr("动捕服务器 IP 地址"))
    parser.add_argument("--target", metavar="IP:PORT", action="append", default=None,
                        help=tr("UDP 广播目标，可重复指定"))
    parser.add_argument("--format", metavar="ID", default=None,
                        help=tr("广播数据格式: stq14 / stq20 / custom"))
    parser.add_argument("--simulate", metavar="N", nargs="?", const="4", default=None,
                        help=tr("使用内置模拟数据源（可选刚体数量，默认 4）"))
    parser.add_argument("--autostart", action="store_true",
                        help=tr("启动后自动连接并开始广播"))
    parser.add_argument("--headless", action="store_true",
                        help=tr("不显示图形界面，仅后台广播"))
    parser.add_argument("--version", action="version", version="%s %s" % (APP_NAME, __version__))
    return parser


def _parse_target(text: str) -> BroadcastTarget:
    ip, _, port = text.rpartition(":")
    if not ip:
        ip, port = text, "22222"
    try:
        port_number = int(port)
    except ValueError:
        raise SystemExit(tr("目标格式应为 IP:端口，例如 192.168.1.123:22222（收到 %r）") % text)
    return BroadcastTarget(ip=ip, port=port_number, enabled=True)


def apply_cli_overrides(config: AppConfig, args) -> bool:
    """Apply command line options to the in-memory config.  True if anything changed."""
    changed = False
    if args.server:
        config.network.server_ip = args.server
        changed = True
    if args.target:
        config.broadcast.targets = [_parse_target(item) for item in args.target]
        changed = True
    if args.format:
        requested = args.format.strip().lower()
        from .core.formats import REGISTRY

        if requested not in REGISTRY:
            raise SystemExit(tr("未知格式 %r，可用: %s")
                             % (args.format, ", ".join(sorted(REGISTRY))))
        config.broadcast.format_id = requested
        changed = True
    if args.autostart:
        config.ui.autoconnect = True
        config.ui.autostart_broadcast = True
        changed = True
    return changed


def _run_headless(context, args, app) -> int:
    """Background broadcaster with no GUI (for autostart / service-like use)."""
    import time

    if args.simulate:
        context.start_simulator(int(args.simulate or 4))
    else:
        ok, message = context.session.connect(context.config.network)
        log.info(tr("连接结果: %s"), message)
        if not ok:
            print(tr("连接失败: %s") % message, file=sys.stderr)
            context.shutdown()
            return 3

    if args.simulate or args.autostart or not context.session.is_running:
        context.engine.start_broadcasting()

    targets = ", ".join("%s:%d" % item for item in context.engine.broadcaster.targets)
    print(tr("后台广播中 → %s   格式: %s") % (targets, context.config.broadcast.format_id))
    print(tr("按 Ctrl+C 退出"))

    try:
        last_report = 0.0
        while True:
            app.processEvents()
            time.sleep(0.1)
            now = time.monotonic()
            if now - last_report >= 2.0:
                last_report = now
                stats = context.engine.stats
                rate = context.engine.broadcaster.stats.rate_hz
                print(tr("%.1f fps · %.0f 包/秒 · %d 刚体 · 已发 %d 包")
                      % (stats.fps, rate, stats.bodies, stats.packets_sent))
                if stats.last_error:
                    print(tr("警告: %s") % stats.last_error)
    except KeyboardInterrupt:
        print(tr("\n正在退出…"))
    finally:
        context.shutdown()
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)

    ensure_dirs()
    config = AppConfig.load()

    # Apply the saved language before any GUI module is imported, so module-level
    # widget descriptions are built in the right language.
    from .i18n import set_language

    set_language(config.ui.language)

    console = args.headless or not getattr(sys, "frozen", False)
    log_path = setup_logging(config.ui.log_level, config.ui.log_to_file, console=console)
    _install_excepthook()

    log.info("=" * 60)
    log.info("%s v%s", APP_NAME, __version__)
    log.info(tr("配置文件: %s"), config_path())
    if log_path:
        log.info(tr("日志文件: %s"), log_path)
    log.info(tr("SDK 目录: %s"), sdk_package_dir())
    if getattr(sys, "frozen", False):
        log.info(tr("运行模式: 已打包 (frozen)"))

    # Load the vendor SDK up front so a missing DLL / VC runtime shows up in the
    # log immediately instead of the first time the user presses "连接".
    from .core.sdk_client import load_sdk

    ok, sdk_message = load_sdk()
    if ok:
        log.info(tr("Nokov SDK 就绪"))
    else:
        log.error(sdk_message)

    cli_changed = apply_cli_overrides(config, args)

    try:
        from PySide2.QtCore import Qt
        from PySide2.QtGui import QIcon
        from PySide2.QtWidgets import QApplication
    except ImportError as exc:
        message = (tr("缺少 PySide2，无法启动图形界面：%s\n"
                   "请使用随程序提供的独立 exe 版本，或先执行 pip install PySide2。") % exc)
        log.error(message)
        print(message, file=sys.stderr)
        return 2

    from .gui.context import AppContext

    def make_context() -> "AppContext":
        context = AppContext()
        context.config.apply_from(config)
        context.persist_config = not cli_changed
        context.start_background()
        return context

    if args.headless:
        from PySide2.QtCore import QCoreApplication

        qapp = QCoreApplication(sys.argv[:1])
        qapp.setApplicationName(APP_NAME)
        qapp.setApplicationVersion(__version__)
        return _run_headless(make_context(), args, qapp)

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_TITLE)
    app.setApplicationVersion(__version__)

    from .gui import theme
    theme.apply_theme(app)

    icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "assets", "icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    from .gui.main_window import MainWindow

    context = make_context()
    window = MainWindow(context)
    window.show()

    if args.simulate:
        window.connection_page.sim_bodies.setValue(max(1, int(args.simulate or 4)))
        window.connection_page.sim_checkbox.setChecked(True)
        context.config.ui.autoconnect = False
    window.autostart()

    log.info(tr("界面已启动"))
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
