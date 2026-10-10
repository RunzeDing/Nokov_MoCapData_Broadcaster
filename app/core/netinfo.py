"""Local IPv4 discovery, with no third-party dependencies.

Uses the Win32 ``GetAdaptersAddresses`` API directly through ctypes, so it works
in the frozen executable and reports the adapter's friendly name (``以太网``,
``WLAN`` …) and whether the link is actually up.  Falls back to the classic
"UDP connect" trick when the API is unavailable.
"""

from __future__ import annotations

from ..i18n import tr

import ctypes
import logging
import socket
from ctypes import wintypes
from typing import List, NamedTuple, Optional

log = logging.getLogger("nokov.net")

AF_UNSPEC = 0
AF_INET = 2

GAA_FLAG_SKIP_ANYCAST = 0x0002
GAA_FLAG_SKIP_MULTICAST = 0x0004
GAA_FLAG_SKIP_DNS_SERVER = 0x0008

ERROR_BUFFER_OVERFLOW = 111
ERROR_SUCCESS = 0

IF_OPER_STATUS_UP = 1
IF_TYPE_SOFTWARE_LOOPBACK = 24

#: ifType values worth naming; anything else is shown as "网卡"
_IF_TYPE_NAMES = {
    6: "以太网",
    23: "PPP",
    24: "回环",
    71: "无线(WLAN)",
    131: "隧道",
    237: "虚拟网卡",
    243: "WLAN",
}


def if_type_name(code: int) -> str:
    """Localised adapter type name."""
    return tr(_IF_TYPE_NAMES.get(code, "网卡"))


class AdapterAddress(NamedTuple):
    """One IPv4 address bound to one adapter."""

    ip: str
    name: str
    description: str
    is_up: bool
    is_loopback: bool
    if_type: int

    @property
    def label(self) -> str:
        if self.is_loopback:
            return tr("127.0.0.1  (本机回环)")
        kind = if_type_name(self.if_type)
        state = "" if self.is_up else tr(" · 未连接")
        name = self.name or self.description or kind
        return "%s  (%s%s)" % (self.ip, name, state)

    @property
    def usable(self) -> bool:
        return self.is_up and not self.is_loopback and not self.ip.startswith("169.254.")


# --------------------------------------------------------------------------- #
# Win32 structures
# --------------------------------------------------------------------------- #
class _SOCKET_ADDRESS(ctypes.Structure):
    _fields_ = [("lpSockaddr", ctypes.c_void_p), ("iSockaddrLength", ctypes.c_int)]


class _SOCKADDR_IN(ctypes.Structure):
    _fields_ = [
        ("sin_family", ctypes.c_ushort),
        ("sin_port", ctypes.c_ushort),
        ("sin_addr", ctypes.c_ubyte * 4),
        ("sin_zero", ctypes.c_char * 8),
    ]


class _LengthIndex(ctypes.Structure):
    _fields_ = [("Length", wintypes.ULONG), ("IfIndex", wintypes.DWORD)]


class _LengthFlags(ctypes.Structure):
    _fields_ = [("Length", wintypes.ULONG), ("Flags", wintypes.DWORD)]


class _AdapterHead(ctypes.Union):
    _fields_ = [("Alignment", ctypes.c_ulonglong), ("parts", _LengthIndex)]


class _UnicastHead(ctypes.Union):
    _fields_ = [("Alignment", ctypes.c_ulonglong), ("parts", _LengthFlags)]


class _IP_ADAPTER_UNICAST_ADDRESS(ctypes.Structure):
    pass


_IP_ADAPTER_UNICAST_ADDRESS._fields_ = [
    ("head", _UnicastHead),
    ("Next", ctypes.POINTER(_IP_ADAPTER_UNICAST_ADDRESS)),
    ("Address", _SOCKET_ADDRESS),
    ("PrefixOrigin", ctypes.c_int),
    ("SuffixOrigin", ctypes.c_int),
    ("DadState", ctypes.c_int),
    ("ValidLifetime", wintypes.ULONG),
    ("PreferredLifetime", wintypes.ULONG),
    ("LeaseLifetime", wintypes.ULONG),
    ("OnLinkPrefixLength", ctypes.c_ubyte),
]


class _IP_ADAPTER_ADDRESSES(ctypes.Structure):
    pass


_IP_ADAPTER_ADDRESSES._fields_ = [
    ("head", _AdapterHead),
    ("Next", ctypes.POINTER(_IP_ADAPTER_ADDRESSES)),
    ("AdapterName", ctypes.c_char_p),
    ("FirstUnicastAddress", ctypes.POINTER(_IP_ADAPTER_UNICAST_ADDRESS)),
    ("FirstAnycastAddress", ctypes.c_void_p),
    ("FirstMulticastAddress", ctypes.c_void_p),
    ("FirstDnsServerAddress", ctypes.c_void_p),
    ("DnsSuffix", ctypes.c_wchar_p),
    ("Description", ctypes.c_wchar_p),
    ("FriendlyName", ctypes.c_wchar_p),
    ("PhysicalAddress", ctypes.c_ubyte * 8),
    ("PhysicalAddressLength", wintypes.DWORD),
    ("Flags", wintypes.DWORD),
    ("Mtu", wintypes.DWORD),
    ("IfType", wintypes.DWORD),
    ("OperStatus", ctypes.c_int),
    ("Ipv6IfIndex", wintypes.DWORD),
    ("ZoneIndices", wintypes.DWORD * 16),
    ("FirstPrefix", ctypes.c_void_p),
    ("TransmitLinkSpeed", ctypes.c_ulonglong),
    ("ReceiveLinkSpeed", ctypes.c_ulonglong),
]


def _sockaddr_to_ip(address: _SOCKET_ADDRESS) -> Optional[str]:
    if not address.lpSockaddr:
        return None
    try:
        sockaddr = ctypes.cast(address.lpSockaddr, ctypes.POINTER(_SOCKADDR_IN)).contents
    except (ValueError, OSError):
        return None
    if sockaddr.sin_family != AF_INET:
        return None
    return ".".join(str(part) for part in sockaddr.sin_addr)


def _query_adapters() -> List[AdapterAddress]:
    """Raw ``GetAdaptersAddresses`` query."""
    iphlpapi = ctypes.WinDLL("iphlpapi")
    iphlpapi.GetAdaptersAddresses.argtypes = [
        wintypes.ULONG, wintypes.ULONG, ctypes.c_void_p,
        ctypes.POINTER(_IP_ADAPTER_ADDRESSES), ctypes.POINTER(wintypes.ULONG),
    ]
    iphlpapi.GetAdaptersAddresses.restype = wintypes.ULONG

    flags = (GAA_FLAG_SKIP_ANYCAST | GAA_FLAG_SKIP_MULTICAST | GAA_FLAG_SKIP_DNS_SERVER)
    size = wintypes.ULONG(16 * 1024)
    buffer = ctypes.create_string_buffer(size.value)
    for _attempt in range(6):
        result = iphlpapi.GetAdaptersAddresses(
            AF_INET, flags, None,
            ctypes.cast(buffer, ctypes.POINTER(_IP_ADAPTER_ADDRESSES)),
            ctypes.byref(size),
        )
        if result == ERROR_BUFFER_OVERFLOW:
            buffer = ctypes.create_string_buffer(size.value)
            continue
        if result != ERROR_SUCCESS:
            raise OSError(tr("GetAdaptersAddresses 返回 %d") % result)
        break
    else:
        raise OSError(tr("GetAdaptersAddresses 无法获取缓冲区大小"))

    found: List[AdapterAddress] = []
    current = ctypes.cast(buffer, ctypes.POINTER(_IP_ADAPTER_ADDRESSES))
    while current:
        adapter = current.contents
        is_up = adapter.OperStatus == IF_OPER_STATUS_UP
        if_type = int(adapter.IfType)
        name = adapter.FriendlyName or ""
        description = adapter.Description or ""
        unicast = adapter.FirstUnicastAddress
        while unicast:
            entry = unicast.contents
            ip = _sockaddr_to_ip(entry.Address)
            if ip:
                found.append(AdapterAddress(
                    ip=ip,
                    name=name,
                    description=description,
                    is_up=is_up,
                    is_loopback=(if_type == IF_TYPE_SOFTWARE_LOOPBACK or ip.startswith("127.")),
                    if_type=if_type,
                ))
            unicast = entry.Next
        current = adapter.Next

    # de-duplicate while keeping order
    seen = set()
    unique: List[AdapterAddress] = []
    for item in found:
        if item.ip in seen:
            continue
        seen.add(item.ip)
        unique.append(item)
    return unique


def _fallback_addresses() -> List[AdapterAddress]:
    """Hostname lookup plus the "connect a UDP socket" trick."""
    addresses: List[AdapterAddress] = []
    try:
        _host, _aliases, ips = socket.gethostbyname_ex(socket.gethostname())
        for ip in ips:
            addresses.append(AdapterAddress(ip, tr("本机主机名解析"), "", True, False, 0))
    except OSError:
        pass

    primary = socket_ipv4()
    if primary and primary not in {item.ip for item in addresses}:
        addresses.append(AdapterAddress(primary, tr("默认出口网卡"), "", True, False, 0))

    return addresses


def list_local_ipv4(include_loopback: bool = True) -> List[AdapterAddress]:
    """Every IPv4 address of this machine, most useful first."""
    try:
        adapters = _query_adapters()
    except Exception as exc:  # pragma: no cover - only on exotic systems
        log.debug(tr("GetAdaptersAddresses 失败，改用回退方案: %r"), exc)
        adapters = _fallback_addresses()

    loopback = [item for item in adapters if item.is_loopback]
    up = [item for item in adapters if item.usable]
    down = [item for item in adapters if not item.usable and not item.is_loopback]

    result: List[AdapterAddress] = []
    if include_loopback:
        result.append(AdapterAddress("127.0.0.1", tr("本机回环"), "loopback", True, True,
                                     IF_TYPE_SOFTWARE_LOOPBACK))
    result.extend(up)
    result.extend(down)
    if include_loopback and not loopback:
        pass  # the synthetic loopback entry above is enough
    return result


def socket_ipv4() -> str:
    """Best guess at the address used for outbound traffic (no packets sent)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 53))
        return sock.getsockname()[0]
    except OSError:
        return ""
    finally:
        sock.close()


def primary_ipv4() -> str:
    """The LAN address most likely to be reachable from another machine."""
    preferred = socket_ipv4()
    adapters = list_local_ipv4(include_loopback=False)
    usable = [item for item in adapters if item.usable]
    for item in usable:
        if item.ip == preferred:
            return item.ip
    if usable:
        return usable[0].ip
    return preferred or "127.0.0.1"


def candidate_server_ips() -> List[str]:
    """Ordered candidates for "the Nokov server runs on this machine".

    Loopback first, then the default-route NIC, then the other connected NICs.
    Link-local (169.254.x) and disconnected adapters are ignored: probing them
    only wastes time because the server can never be listening there.
    """
    usable = [item.ip for item in list_local_ipv4(include_loopback=False) if item.usable]
    candidates = ["127.0.0.1"]
    preferred = socket_ipv4()
    if preferred and preferred in usable:
        candidates.append(preferred)
    for ip in usable:
        if ip not in candidates:
            candidates.append(ip)
    return candidates


def local_target_ips() -> List[AdapterAddress]:
    """Addresses a receiver on this machine could be reached at."""
    result = [AdapterAddress("127.0.0.1", tr("本机回环"), "loopback", True, True,
                             IF_TYPE_SOFTWARE_LOOPBACK)]
    result.extend(item for item in list_local_ipv4(include_loopback=False) if item.usable)
    return result


def describe_local_ips() -> str:
    entries = list_local_ipv4()
    if not entries:
        return tr("未检测到本机 IPv4 地址")
    return "；".join(item.label for item in entries)
