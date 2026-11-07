"""Mandatory Linux Landlock TCP-port restriction for existing role processes.

The systemd cgroup still owns IP-address enforcement. Landlock adds exact TCP
ports, so an unrelated wildcard listener on a different port is not reachable
through an otherwise allowed role IP. No firewall service, privileged helper,
provider call, configuration store, retry, or daemon is added.

Apply in the single-threaded CLI before secrets, sockets, or child processes.
Restrictions are inherited by subsequent threads/children and cannot be undone.
This handles TCP only, not UDP or Unix-domain IPC; never claim otherwise.
API reference: https://docs.kernel.org/userspace-api/landlock.html
"""
from __future__ import annotations

import ctypes
import os
import platform
import socket
import stat
import sys

from .egress import ROLE_PROXY_PORT
from .errors import RuntimeRefusal
from .profile import RuntimeProfile

_CREATE = 444
_ADD = 445
_RESTRICT = 446
_VERSION = 1
_NET_PORT = 2
_BIND_TCP = 1 << 0
_CONNECT_TCP = 1 << 1
_PR_SET_NO_NEW_PRIVS = 38


class _Ruleset(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64),
                ("handled_access_net", ctypes.c_uint64)]


class _PortRule(ctypes.Structure):
    _fields_ = [("allowed_access", ctypes.c_uint64),
                ("port", ctypes.c_uint64)]


def role_tcp_ports(profile: RuntimeProfile) -> tuple[frozenset[int], frozenset[int]]:
    if type(profile) is not RuntimeProfile or profile.role not in ROLE_PROXY_PORT:
        raise RuntimeRefusal("ROLE_TCP_PROFILE_UNQUALIFIED")
    ports = (profile.gateway_port, profile.backend_port, ROLE_PROXY_PORT[profile.role])
    if (any(type(port) is not int or not 1024 <= port <= 65535 for port in ports)
            or len(set(ports)) != 3):
        raise RuntimeRefusal("ROLE_TCP_FIXED_PORTS_REQUIRED")
    return frozenset(ports[:2]), frozenset(ports)


def _libc():
    if (sys.platform != "linux" or ctypes.sizeof(ctypes.c_void_p) != 8
            or platform.machine().lower() not in {"x86_64", "aarch64"}):
        raise RuntimeRefusal("ROLE_TCP_LANDLOCK_PLATFORM_UNSUPPORTED")
    try:
        lib = ctypes.CDLL(None, use_errno=True)
        lib.syscall.restype = ctypes.c_long
        lib.prctl.restype = ctypes.c_int
    except (OSError, AttributeError):
        raise RuntimeRefusal("ROLE_TCP_LANDLOCK_UNAVAILABLE") from None
    return lib


def _is_unix_socket(fd: int) -> bool:
    # systemd normally provides stdout/stderr as AF_UNIX journal sockets.
    # They are not preconnected Internet sockets and must remain usable.
    duplicate = os.dup(fd)
    try:
        sock = socket.socket(fileno=duplicate)
    except OSError:
        os.close(duplicate)
        raise
    with sock:
        return sock.family == socket.AF_UNIX


def _single_thread_without_sockets() -> None:
    try:
        if len(os.listdir("/proc/self/task")) != 1:
            raise RuntimeRefusal("ROLE_TCP_LATE_SANDBOX_REFUSED")
        # Landlock does not retrofit restrictions onto existing network sockets.
        # Refuse activation rather than accidentally inheriting one.
        for value in os.listdir("/proc/self/fd"):
            try:
                info = os.fstat(int(value))
            except OSError:
                continue  # the directory enumeration descriptor is now closed
            if stat.S_ISSOCK(info.st_mode) and not _is_unix_socket(int(value)):
                raise RuntimeRefusal("ROLE_TCP_INHERITED_SOCKET_REFUSED")
    except (OSError, ValueError):
        raise RuntimeRefusal("ROLE_TCP_PROCESS_INSPECTION_FAILED") from None


def apply_tcp_port_policy(bind_ports: frozenset[int], connect_ports: frozenset[int]) -> None:
    """Irreversibly restrict this process; only invoke from a fresh child/CLI.

    ABI < 4, disabled Landlock, failed rule insertion, or failed attachment
    aborts. A success is kernel TCP policy attachment, not cgroup/IP, TLS,
    provider, billing, Slack, or full application acceptance.
    """
    if (type(bind_ports) is not frozenset or type(connect_ports) is not frozenset
            or not bind_ports or not connect_ports
            or len(bind_ports | connect_ports) > 3
            or any(type(p) is not int or not 1024 <= p <= 65535
                   for p in bind_ports | connect_ports)):
        raise RuntimeRefusal("ROLE_TCP_PORT_POLICY_INVALID")
    lib = _libc()
    _single_thread_without_sockets()
    abi = lib.syscall(ctypes.c_long(_CREATE), ctypes.c_void_p(), ctypes.c_size_t(0),
                      ctypes.c_uint(_VERSION))
    if abi < 4:
        raise RuntimeRefusal("ROLE_TCP_LANDLOCK_ABI_UNAVAILABLE")
    attr = _Ruleset(0, _BIND_TCP | _CONNECT_TCP)
    fd = lib.syscall(ctypes.c_long(_CREATE), ctypes.byref(attr),
                     ctypes.c_size_t(ctypes.sizeof(attr)), ctypes.c_uint(0))
    if fd < 0:
        raise RuntimeRefusal("ROLE_TCP_LANDLOCK_CREATE_FAILED")
    try:
        for port in sorted(bind_ports | connect_ports):
            rights = (_BIND_TCP if port in bind_ports else 0)
            rights |= (_CONNECT_TCP if port in connect_ports else 0)
            rule = _PortRule(rights, port)
            if lib.syscall(ctypes.c_long(_ADD), ctypes.c_int(fd), ctypes.c_int(_NET_PORT),
                           ctypes.byref(rule), ctypes.c_uint(0)) != 0:
                raise RuntimeRefusal("ROLE_TCP_LANDLOCK_RULE_FAILED")
        if lib.prctl(ctypes.c_int(_PR_SET_NO_NEW_PRIVS), ctypes.c_ulong(1),
                     ctypes.c_ulong(0), ctypes.c_ulong(0), ctypes.c_ulong(0)) != 0:
            raise RuntimeRefusal("ROLE_TCP_NO_NEW_PRIVS_FAILED")
        if lib.syscall(ctypes.c_long(_RESTRICT), ctypes.c_int(fd), ctypes.c_uint(0)) != 0:
            raise RuntimeRefusal("ROLE_TCP_LANDLOCK_ATTACH_FAILED")
    finally:
        os.close(fd)


def enforce_role_tcp_ports(profile: RuntimeProfile) -> None:
    apply_tcp_port_policy(*role_tcp_ports(profile))
