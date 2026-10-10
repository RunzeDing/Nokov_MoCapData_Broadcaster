"""Application metadata shared by the GUI, the log and the packaging scripts."""

from __future__ import annotations

APP_NAME = "NokovBroadcaster"
#: Chinese source text; wrap with ``tr(APP_TITLE)`` at display sites
APP_TITLE = "Nokov 动捕数据广播器"
APP_ORG = "NokovClient"

__version__ = "2.0.0"

#: Bumped whenever the on-disk settings layout changes in a breaking way.
CONFIG_VERSION = 1

#: The classic single-datagram STQ layout used by NokovSDKClient_STQ.py.
LEGACY_SCRIPT = "NokovSDKClient_STQ.py"
