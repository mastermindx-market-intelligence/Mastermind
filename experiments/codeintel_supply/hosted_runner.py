"""Deterministic hosted forge and network-sealed Z0 execution boundary.

Only the reviewed manual workflow calls the mutating commands in this module.
All dispatch values are reduced to one closed request identity; callers cannot
select a repository, URL, module, executable, command, path, or argv suffix.
"""

from __future__ import annotations

import argparse
import dataclasses
import enum
import errno
import fcntl
import gzip
import hashlib
import io
import json
import os
import platform
import re
import resource
import selectors
import shutil
import signal
import socket
import socketserver
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import zipfile
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any, Final
from urllib.parse import urljoin, urlparse

try:  # Support both ``python -m`` and the workflow's absolute script entry.
    from . import toolchain_lock as locks
except ImportError:  # pragma: no cover - exercised by the hosted workflow
    import toolchain_lock as locks  # type: ignore[no-redef]


RECEIPT_SCHEMA_VERSION: Final = "mastermind.codeintel_experiment_bundle.v1"
BUNDLE_MANIFEST_SCHEMA_VERSION: Final = "mastermind.codeintel_bundle_manifest.v1"
PHASE_P_PROVENANCE_SCHEMA_VERSION: Final = "mastermind.codeintel_phase_p_provenance.v1"
Z0_OPERATION_KEY: Final = locks.Z0_OPERATION_KEY
FIXED_REPOSITORY: Final = "mastermindx-market-intelligence/Mastermind"
FIXED_CONSUMER_MODULE: Final = "experiments.code_discovery.z0_runner"
FIXED_CONSUMER_BRANCH: Final = "codeintel-z0-consumer"
FIXED_WORKFLOW_PATH: Final = ".github/workflows/codeintel-experiment-bundle.yml"
HOST_USERNS_SYSCTL_PATH: Final = Path(
    "/proc/sys/kernel/apparmor_restrict_unprivileged_userns"
)
HOST_USERNS_SYSCTL_KEY: Final = "kernel.apparmor_restrict_unprivileged_userns"
HOST_USERNS_ACTIVE_VALUE: Final = 0
HOST_USERNS_SCOPE: Final = "single_use_github_hosted_ubuntu_24_04_x64"

_SHA1_RE: Final = re.compile(r"[0-9a-f]{40}\Z")
_SHA256_RE: Final = re.compile(r"[0-9a-f]{64}\Z")
_OPERATION_RE: Final = re.compile(r"[a-z0-9][a-z0-9-]{0,127}\Z")
_SAFE_BUNDLE_PART_RE: Final = re.compile(r"[A-Za-z0-9._+-]{1,128}\Z")
_CONNECT_HOST_RE: Final = re.compile(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?\Z")
_CONNECT_HEADER_MAX_BYTES: Final = 16_384
_PHASE_P_PROXY_PORT: Final = 47_853
_PHASE_P_GATE_ENV: Final = "CODEINTEL_PHASE_P_GATE_SOCKET"
_PHASE_P_LANDLOCK_MIN_ABI: Final = locks.PHASE_P_LANDLOCK_MIN_ABI
_PHASE_P_BOUNDARY_READY: Final = locks.PHASE_P_BOUNDARY_RECEIPT.encode("ascii") + b"\n"
_PHASE_P_BOUNDARY_BOOTSTRAP: Final = r"""
import ctypes
import fcntl
import os
import signal
import socket
import stat
import struct
import sys
import threading

LANDLOCK_CREATE_RULESET_VERSION = 1
LANDLOCK_ACCESS_NET_BIND_TCP = 1 << 0
LANDLOCK_ACCESS_NET_CONNECT_TCP = 1 << 1
LANDLOCK_RULE_NET_PORT = 2
PR_SET_NO_NEW_PRIVS = 38
PR_SET_PDEATHSIG = 1
PR_GET_DUMPABLE = 3
PR_SET_DUMPABLE = 4
PR_CAPBSET_DROP = 24
PR_CAP_AMBIENT = 47
PR_CAP_AMBIENT_CLEAR_ALL = 4
SECCOMP_SET_MODE_FILTER = 1
AUDIT_ARCH_X86_64 = 0xC000003E
X32_SYSCALL_BIT = 0x40000000
NR_SOCKET = 41
NR_SENDTO = 44
NR_SENDMSG = 46
NR_CLONE = 56
NR_SOCKETPAIR = 53
NR_PTRACE = 101
NR_SETPGID = 109
NR_SETSID = 112
NR_CAPSET = 126
NR_PIVOT_ROOT = 155
NR_PRCTL = 157
NR_MOUNT = 165
NR_UMOUNT2 = 166
NR_UNSHARE = 272
NR_SENDMMSG = 307
NR_SETNS = 308
NR_PROCESS_VM_READV = 310
NR_PROCESS_VM_WRITEV = 311
NR_SECCOMP = 317
NR_BPF = 321
NR_IO_URING_SETUP = 425
NR_IO_URING_ENTER = 426
NR_IO_URING_REGISTER = 427
NR_OPEN_TREE = 428
NR_MOVE_MOUNT = 429
NR_FSOPEN = 430
NR_FSCONFIG = 431
NR_FSMOUNT = 432
NR_FSPICK = 433
NR_CLONE3 = 435
NR_PIDFD_GETFD = 438
NR_MOUNT_SETATTR = 442
NR_LANDLOCK_CREATE_RULESET = 444
NR_LANDLOCK_ADD_RULE = 445
NR_LANDLOCK_RESTRICT_SELF = 446
BPF_LD_W_ABS = 0x20
BPF_JMP_JEQ_K = 0x15
BPF_JMP_JSET_K = 0x45
BPF_ALU_AND_K = 0x54
BPF_RET_K = 0x06
SECCOMP_RET_KILL_PROCESS = 0x80000000
SECCOMP_RET_ERRNO = 0x00050000
SECCOMP_RET_ALLOW = 0x7FFF0000
EPERM = 1
ENOSYS = 38
AF_INET = 2
SOCK_STREAM = 1
SOCK_NONBLOCK = 0x800
SOCK_CLOEXEC = 0x80000
SOCKET_BASE_MASK = (~(SOCK_NONBLOCK | SOCK_CLOEXEC)) & 0xFFFFFFFF
IPPROTO_TCP = 6
MSG_FASTOPEN = 0x20000000
CLONE_NAMESPACE_MASK = (
    0x00020000
    | 0x02000000
    | 0x04000000
    | 0x08000000
    | 0x10000000
    | 0x20000000
    | 0x40000000
)
LINUX_CAPABILITY_VERSION_3 = 0x20080522
SIOCGIFFLAGS = 0x8913
SIOCSIFFLAGS = 0x8914
IFF_UP = 0x1
MS_RDONLY = 0x1
MS_NOSUID = 0x2
MS_NODEV = 0x4
MS_NOEXEC = 0x8
MS_REMOUNT = 0x20
MS_BIND = 0x1000
MS_REC = 0x4000
MS_PRIVATE = 0x40000
ST_RDONLY = 0x1


class RulesetAttr(ctypes.Structure):
    _fields_ = [
        ("handled_access_fs", ctypes.c_uint64),
        ("handled_access_net", ctypes.c_uint64),
    ]


class NetPortAttr(ctypes.Structure):
    _fields_ = [
        ("allowed_access", ctypes.c_uint64),
        ("port", ctypes.c_uint64),
    ]


class CapHeader(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_uint32),
        ("pid", ctypes.c_int),
    ]


class CapData(ctypes.Structure):
    _fields_ = [
        ("effective", ctypes.c_uint32),
        ("permitted", ctypes.c_uint32),
        ("inheritable", ctypes.c_uint32),
    ]


class SockFilter(ctypes.Structure):
    _fields_ = [
        ("code", ctypes.c_ushort),
        ("jt", ctypes.c_ubyte),
        ("jf", ctypes.c_ubyte),
        ("k", ctypes.c_uint32),
    ]


class SockFprog(ctypes.Structure):
    _fields_ = [
        ("len", ctypes.c_ushort),
        ("filter", ctypes.POINTER(SockFilter)),
    ]


status_fd = -1


def fail_closed():
    try:
        if status_fd >= 0:
            os.close(status_fd)
    except OSError:
        pass
    os._exit(125)


def require_zero_capabilities(libc):
    if libc.prctl(PR_SET_DUMPABLE, 0, 0, 0, 0) != 0:
        fail_closed()
    if libc.prctl(PR_GET_DUMPABLE, 0, 0, 0, 0) != 0:
        fail_closed()
    if libc.prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_CLEAR_ALL, 0, 0, 0) != 0:
        fail_closed()
    try:
        with open("/proc/sys/kernel/cap_last_cap", encoding="ascii") as source:
            cap_last_cap = int(source.read().strip())
    except (OSError, ValueError):
        fail_closed()
    if not 0 <= cap_last_cap <= 63:
        fail_closed()
    for capability in range(cap_last_cap + 1):
        if libc.prctl(PR_CAPBSET_DROP, capability, 0, 0, 0) != 0:
            fail_closed()
    header = CapHeader(LINUX_CAPABILITY_VERSION_3, 0)
    data = (CapData * 2)(CapData(0, 0, 0), CapData(0, 0, 0))
    if libc.syscall(NR_CAPSET, ctypes.byref(header), ctypes.byref(data)) != 0:
        fail_closed()
    if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        fail_closed()
    capability_fields = {}
    identity_fields = {}
    no_new_privs = None
    with open("/proc/self/status", encoding="ascii") as source:
        for line in source:
            if line.startswith(("CapInh:", "CapPrm:", "CapEff:", "CapBnd:", "CapAmb:")):
                key, value = line.split(":", 1)
                capability_fields[key] = int(value.strip(), 16)
            elif line.startswith(("Uid:", "Gid:")):
                key, value = line.split(":", 1)
                identity_fields[key] = tuple(int(part) for part in value.split())
            elif line.startswith("NoNewPrivs:"):
                no_new_privs = line.split(":", 1)[1].strip()
    if capability_fields != {
        "CapInh": 0,
        "CapPrm": 0,
        "CapEff": 0,
        "CapBnd": 0,
        "CapAmb": 0,
    }:
        fail_closed()
    if (
        identity_fields.get("Uid") != (os.getuid(),) * 4
        or identity_fields.get("Gid") != (os.getgid(),) * 4
        or len(set(os.getresuid())) != 1
        or len(set(os.getresgid())) != 1
        or no_new_privs != "1"
    ):
        fail_closed()


def configure_and_verify_loopback():
    control = socket.socket(socket.AF_INET, socket.SOCK_DGRAM | socket.SOCK_CLOEXEC)
    try:
        interface = bytearray(struct.pack("16sH22x", b"lo", 0))
        fcntl.ioctl(control.fileno(), SIOCGIFFLAGS, interface, True)
        flags = struct.unpack_from("H", interface, 16)[0]
        struct.pack_into("H", interface, 16, flags | IFF_UP)
        fcntl.ioctl(control.fileno(), SIOCSIFFLAGS, interface, True)
    finally:
        control.close()
    if [name for _index, name in socket.if_nameindex()] != ["lo"]:
        fail_closed()
    with open("/proc/net/route", encoding="ascii") as source:
        ipv4_rows = source.read().splitlines()[1:]
    if any(row.split()[0] != "lo" for row in ipv4_rows if row.split()):
        fail_closed()
    with open("/proc/net/ipv6_route", encoding="ascii") as source:
        ipv6_rows = source.read().splitlines()
    if any(row.split()[-1] != "lo" for row in ipv6_rows if row.split()):
        fail_closed()


def freeze_gate_mount(libc, gate_path):
    gate_parent = os.path.dirname(gate_path)
    before_gate = os.lstat(gate_path)
    before_parent = os.lstat(gate_parent)
    libc.mount.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_ulong,
        ctypes.c_void_p,
    ]
    libc.mount.restype = ctypes.c_int
    if libc.mount(None, b"/", None, MS_REC | MS_PRIVATE, None) != 0:
        fail_closed()
    encoded_parent = os.fsencode(gate_parent)
    if libc.mount(encoded_parent, encoded_parent, None, MS_BIND, None) != 0:
        fail_closed()
    if libc.mount(
        None,
        encoded_parent,
        None,
        MS_BIND | MS_REMOUNT | MS_RDONLY | MS_NOSUID | MS_NODEV | MS_NOEXEC,
        None,
    ) != 0:
        fail_closed()
    after_gate = os.lstat(gate_path)
    after_parent = os.lstat(gate_parent)
    if (
        (after_gate.st_dev, after_gate.st_ino)
        != (before_gate.st_dev, before_gate.st_ino)
        or (after_parent.st_dev, after_parent.st_ino)
        != (before_parent.st_dev, before_parent.st_ino)
        or not os.statvfs(gate_parent).f_flag & ST_RDONLY
    ):
        fail_closed()


def apply_landlock(libc, proxy_port):
    abi = libc.syscall(
        NR_LANDLOCK_CREATE_RULESET,
        ctypes.c_void_p(),
        ctypes.c_size_t(0),
        ctypes.c_uint(LANDLOCK_CREATE_RULESET_VERSION),
    )
    if abi < 4:
        fail_closed()

    ruleset_attr = RulesetAttr(
        0, LANDLOCK_ACCESS_NET_BIND_TCP | LANDLOCK_ACCESS_NET_CONNECT_TCP
    )
    ruleset_fd = libc.syscall(
        NR_LANDLOCK_CREATE_RULESET,
        ctypes.byref(ruleset_attr),
        ctypes.sizeof(ruleset_attr),
        0,
    )
    if ruleset_fd < 0:
        fail_closed()
    try:
        proxy_rule = NetPortAttr(LANDLOCK_ACCESS_NET_CONNECT_TCP, proxy_port)
        if libc.syscall(
            NR_LANDLOCK_ADD_RULE,
            ruleset_fd,
            LANDLOCK_RULE_NET_PORT,
            ctypes.byref(proxy_rule),
            0,
        ) != 0:
            fail_closed()
        if libc.syscall(NR_LANDLOCK_RESTRICT_SELF, ruleset_fd, 0) != 0:
            fail_closed()
    finally:
        os.close(ruleset_fd)


def apply_seccomp(libc):
    instructions = []
    labels = {}

    def label(name):
        labels[name] = len(instructions)

    def statement(code, value):
        instructions.append(("statement", code, value))

    def jump(code, value, true_label, false_label):
        instructions.append(("jump", code, value, true_label, false_label))

    statement(BPF_LD_W_ABS, 4)
    jump(BPF_JMP_JEQ_K, AUDIT_ARCH_X86_64, "load_number", "kill")
    label("load_number")
    statement(BPF_LD_W_ABS, 0)
    jump(BPF_JMP_JSET_K, X32_SYSCALL_BIT, "kill", "check_socket")
    label("check_socket")
    jump(BPF_JMP_JEQ_K, NR_SOCKET, "socket_domain", "check_socketpair")
    label("check_socketpair")
    jump(BPF_JMP_JEQ_K, NR_SOCKETPAIR, "deny", "check_clone")
    label("check_clone")
    jump(BPF_JMP_JEQ_K, NR_CLONE, "clone_flags", "check_clone3")
    label("check_clone3")
    jump(BPF_JMP_JEQ_K, NR_CLONE3, "not_supported", "check_io_setup")
    label("check_io_setup")
    jump(BPF_JMP_JEQ_K, NR_IO_URING_SETUP, "deny", "check_io_enter")
    label("check_io_enter")
    jump(BPF_JMP_JEQ_K, NR_IO_URING_ENTER, "deny", "check_io_register")
    label("check_io_register")
    jump(BPF_JMP_JEQ_K, NR_IO_URING_REGISTER, "deny", "check_setns")
    label("check_setns")
    jump(BPF_JMP_JEQ_K, NR_SETNS, "deny", "check_unshare")
    label("check_unshare")
    jump(BPF_JMP_JEQ_K, NR_UNSHARE, "deny", "check_setpgid")
    label("check_setpgid")
    jump(BPF_JMP_JEQ_K, NR_SETPGID, "deny", "check_setsid")
    label("check_setsid")
    jump(BPF_JMP_JEQ_K, NR_SETSID, "deny", "check_mount")
    label("check_mount")
    jump(BPF_JMP_JEQ_K, NR_MOUNT, "deny", "check_umount")
    label("check_umount")
    jump(BPF_JMP_JEQ_K, NR_UMOUNT2, "deny", "check_pivot_root")
    label("check_pivot_root")
    jump(BPF_JMP_JEQ_K, NR_PIVOT_ROOT, "deny", "check_open_tree")
    label("check_open_tree")
    jump(BPF_JMP_JEQ_K, NR_OPEN_TREE, "deny", "check_move_mount")
    label("check_move_mount")
    jump(BPF_JMP_JEQ_K, NR_MOVE_MOUNT, "deny", "check_fsopen")
    label("check_fsopen")
    jump(BPF_JMP_JEQ_K, NR_FSOPEN, "deny", "check_fsconfig")
    label("check_fsconfig")
    jump(BPF_JMP_JEQ_K, NR_FSCONFIG, "deny", "check_fsmount")
    label("check_fsmount")
    jump(BPF_JMP_JEQ_K, NR_FSMOUNT, "deny", "check_fspick")
    label("check_fspick")
    jump(BPF_JMP_JEQ_K, NR_FSPICK, "deny", "check_mount_setattr")
    label("check_mount_setattr")
    jump(BPF_JMP_JEQ_K, NR_MOUNT_SETATTR, "deny", "check_prctl")
    label("check_prctl")
    jump(BPF_JMP_JEQ_K, NR_PRCTL, "prctl_option", "check_capset")
    label("check_capset")
    jump(BPF_JMP_JEQ_K, NR_CAPSET, "deny", "check_pidfd_getfd")
    label("check_pidfd_getfd")
    jump(BPF_JMP_JEQ_K, NR_PIDFD_GETFD, "deny", "check_process_vm_readv")
    label("check_process_vm_readv")
    jump(BPF_JMP_JEQ_K, NR_PROCESS_VM_READV, "deny", "check_process_vm_writev")
    label("check_process_vm_writev")
    jump(BPF_JMP_JEQ_K, NR_PROCESS_VM_WRITEV, "deny", "check_ptrace")
    label("check_ptrace")
    jump(BPF_JMP_JEQ_K, NR_PTRACE, "deny", "check_bpf")
    label("check_bpf")
    jump(BPF_JMP_JEQ_K, NR_BPF, "deny", "check_sendto")
    label("check_sendto")
    jump(BPF_JMP_JEQ_K, NR_SENDTO, "sendto_flags", "check_sendmsg")
    label("check_sendmsg")
    jump(BPF_JMP_JEQ_K, NR_SENDMSG, "sendmsg_flags", "check_sendmmsg")
    label("check_sendmmsg")
    jump(BPF_JMP_JEQ_K, NR_SENDMMSG, "sendmmsg_flags", "allow")

    label("socket_domain")
    statement(BPF_LD_W_ABS, 16)
    jump(BPF_JMP_JEQ_K, AF_INET, "socket_type", "deny")
    label("socket_type")
    statement(BPF_LD_W_ABS, 24)
    statement(BPF_ALU_AND_K, SOCKET_BASE_MASK)
    jump(BPF_JMP_JEQ_K, SOCK_STREAM, "socket_protocol", "deny")
    label("socket_protocol")
    statement(BPF_LD_W_ABS, 32)
    jump(BPF_JMP_JEQ_K, 0, "allow", "socket_protocol_tcp")
    label("socket_protocol_tcp")
    jump(BPF_JMP_JEQ_K, IPPROTO_TCP, "allow", "deny")

    label("clone_flags")
    statement(BPF_LD_W_ABS, 16)
    jump(BPF_JMP_JSET_K, CLONE_NAMESPACE_MASK, "deny", "allow")
    label("prctl_option")
    statement(BPF_LD_W_ABS, 16)
    jump(BPF_JMP_JEQ_K, PR_SET_PDEATHSIG, "deny", "allow")

    label("sendto_flags")
    statement(BPF_LD_W_ABS, 40)
    jump(BPF_JMP_JSET_K, MSG_FASTOPEN, "deny", "allow")
    label("sendmsg_flags")
    statement(BPF_LD_W_ABS, 32)
    jump(BPF_JMP_JSET_K, MSG_FASTOPEN, "deny", "allow")
    label("sendmmsg_flags")
    statement(BPF_LD_W_ABS, 40)
    jump(BPF_JMP_JSET_K, MSG_FASTOPEN, "deny", "allow")

    label("allow")
    statement(BPF_RET_K, SECCOMP_RET_ALLOW)
    label("deny")
    statement(BPF_RET_K, SECCOMP_RET_ERRNO | EPERM)
    label("not_supported")
    statement(BPF_RET_K, SECCOMP_RET_ERRNO | ENOSYS)
    label("kill")
    statement(BPF_RET_K, SECCOMP_RET_KILL_PROCESS)

    filters = []
    for index, instruction in enumerate(instructions):
        if instruction[0] == "statement":
            _kind, code, value = instruction
            filters.append(SockFilter(code, 0, 0, value))
            continue
        _kind, code, value, true_label, false_label = instruction
        true_offset = labels[true_label] - index - 1
        false_offset = labels[false_label] - index - 1
        if not 0 <= true_offset <= 255 or not 0 <= false_offset <= 255:
            fail_closed()
        filters.append(SockFilter(code, true_offset, false_offset, value))
    filter_array = (SockFilter * len(filters))(*filters)
    program = SockFprog(len(filter_array), filter_array)
    if libc.syscall(
        NR_SECCOMP,
        SECCOMP_SET_MODE_FILTER,
        0,
        ctypes.byref(program),
    ) != 0:
        fail_closed()


def close_client_descriptors(keep_fd):
    for descriptor in (0, 1, 2):
        if stat.S_ISSOCK(os.fstat(descriptor).st_mode):
            fail_closed()
    if not stat.S_ISFIFO(os.fstat(keep_fd).st_mode):
        fail_closed()
    for name in os.listdir("/proc/self/fd"):
        descriptor = int(name)
        if descriptor <= 2 or descriptor == keep_fd:
            continue
        try:
            os.close(descriptor)
        except OSError:
            pass


def relay_connection(client, gate_path, active, active_lock):
    upstream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM | socket.SOCK_CLOEXEC)

    def pump(source, destination):
        try:
            while True:
                block = source.recv(65536)
                if not block:
                    return
                destination.sendall(block)
        except OSError:
            return
        finally:
            try:
                destination.shutdown(socket.SHUT_WR)
            except OSError:
                pass

    try:
        upstream.settimeout(5)
        upstream.connect(gate_path)
        client.settimeout(None)
        upstream.settimeout(None)
        with active_lock:
            active.update((client, upstream))
        request_pump = threading.Thread(
            target=pump,
            args=(client, upstream),
            daemon=True,
        )
        request_pump.start()
        pump(upstream, client)
        request_pump.join(timeout=1)
    except OSError:
        return
    finally:
        with active_lock:
            active.discard(client)
            active.discard(upstream)
        for connection in (client, upstream):
            try:
                connection.close()
            except OSError:
                pass


try:
    status_fd = int(sys.argv[1])
    proxy_port = int(sys.argv[2])
    gate_path = sys.argv[3]
    executable = sys.argv[4]
    command = sys.argv[4:]
    if (
        sys.platform != "linux"
        or os.uname().machine.lower() not in {"x86_64", "amd64"}
        or os.geteuid() == 0
        or not 1024 < proxy_port <= 65535
        or proxy_port == 443
        or not os.path.isabs(gate_path)
        or len(os.fsencode(gate_path)) > 100
        or not executable.startswith("/")
        or not command
    ):
        fail_closed()
    gate_metadata = os.lstat(gate_path)
    gate_parent = os.path.dirname(gate_path)
    parent_metadata = os.lstat(gate_parent)
    if (
        not stat.S_ISSOCK(gate_metadata.st_mode)
        or not stat.S_ISDIR(parent_metadata.st_mode)
        or stat.S_ISLNK(parent_metadata.st_mode)
        or parent_metadata.st_uid != os.getuid()
        or parent_metadata.st_mode & 0o077
    ):
        fail_closed()

    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    freeze_gate_mount(libc, gate_path)
    configure_and_verify_loopback()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM | socket.SOCK_CLOEXEC)
    listener.bind(("127.0.0.1", proxy_port))
    listener.listen(64)
    if listener.getsockname() != ("127.0.0.1", proxy_port):
        fail_closed()
    require_zero_capabilities(libc)

    supervisor_pid = os.getpid()
    client_pid = os.fork()
    if client_pid == 0:
        listener.close()
        if libc.prctl(PR_SET_PDEATHSIG, signal.SIGKILL, 0, 0, 0) != 0:
            fail_closed()
        if os.getppid() != supervisor_pid:
            fail_closed()
        close_client_descriptors(status_fd)
        apply_landlock(libc, proxy_port)
        apply_seccomp(libc)
        os.write(status_fd, b"CODEINTEL_PHASE_P_BOUNDARY_V1\n")
        os.close(status_fd)
        status_fd = -1
        os.execve(executable, command, os.environ)

    os.close(status_fd)
    status_fd = -1
    listener.settimeout(0.05)
    active = set()
    active_lock = threading.Lock()
    relay_threads = []
    client_status = None
    while client_status is None:
        waited_pid, waited_status = os.waitpid(client_pid, os.WNOHANG)
        if waited_pid == client_pid:
            client_status = waited_status
            break
        try:
            connection, _address = listener.accept()
        except TimeoutError:
            continue
        connection.set_inheritable(False)
        relay = threading.Thread(
            target=relay_connection,
            args=(connection, gate_path, active, active_lock),
            daemon=True,
        )
        relay.start()
        relay_threads.append(relay)
    listener.close()
    with active_lock:
        active_snapshot = tuple(active)
    for connection in active_snapshot:
        try:
            connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        connection.close()
    for relay in relay_threads:
        relay.join(timeout=1)
    if os.WIFEXITED(client_status):
        os._exit(os.WEXITSTATUS(client_status))
    if os.WIFSIGNALED(client_status):
        os._exit(128 + os.WTERMSIG(client_status))
    fail_closed()
except BaseException:
    fail_closed()
"""
_SECRET_TEXT_PATTERNS: Final = (
    re.compile(r"(?i)authorization\s*:\s*(?:bearer|basic)\s+\S+"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"),
    re.compile(r"\$\{\{\s*secrets\.", re.IGNORECASE),
    re.compile(r"\b(?:GITHUB|ACTIONS)_\w*TOKEN\b"),
)
_PRIVATE_PATH_PATTERNS: Final = (
    re.compile(r"(?:^|[\s'\"])/Users/[^\s'\"]+"),
    re.compile(r"(?:^|[\s'\"])/home/runner/(?:work|_work)/[^\s'\"]+"),
    re.compile(r"(?:^|[\s'\"])/private/(?:tmp|var)/[^\s'\"]+"),
)
_FORBIDDEN_KEY_RE: Final = re.compile(
    r"(?:^|_)(?:authorization|cookie|credential|password|private_key|token|secret)(?:_|$)",
    re.IGNORECASE,
)
_ALLOWED_CONSUMER_PREFIXES: Final = (
    "experiments/code_discovery/",
    "tests/code_discovery/",
    "tests/fixtures/code_discovery/",
)
_ALLOWED_CONSUMER_EXACT: Final = frozenset(
    {
        "research/code_intelligence_fabric/Z0_GLOBAL_DISCOVERY_FALSIFIER_RESULT.md",
        "research/code_intelligence_fabric/z0-path-policy.json",
        "research/code_intelligence_fabric/z0-result.schema.json",
    }
)
_REQUIRED_BUNDLE_FILES: Final = frozenset(
    {
        "bin/zoekt-git-index",
        "bin/zoekt-webserver",
        "meta/NOTICE.txt",
        "meta/provenance.json",
        "meta/sbom.json",
        "meta/toolchain-lock.json",
    }
)
_RECEIPT_STATE_PAIRS: Final = frozenset(
    {
        ("COMPLETED", "APPLIED"),
        ("REFUSED", "NOT_APPLIED"),
        ("RECONCILIATION_REQUIRED", "EFFECT_UNKNOWN"),
    }
)
_Z0_RESULT_FIELDS: Final = frozenset(
    {
        "schema_version",
        "decision",
        "generated_at",
        "manifest_digest",
        "path_policy_digest",
        "tool_schema_digest",
        "zoekt_source_commit",
        "binary_digests",
        "repository_statuses",
        "resource_observations",
    }
)
_Z0_STATUS_FIELDS: Final = frozenset(
    {
        "repository_id",
        "ref_label",
        "indexed_commit_sha",
        "source_tree_digest",
        "shard_namespace",
        "health",
        "coverage",
        "generated_at",
        "observed_at",
        "freshness_seconds",
    }
)
_Z0_NON_ACCEPTANCE_DECISION: Final = "ZOEKT_REQUIRES_ARCHITECTURE_REVISION"
_CONSUMER_BOOTSTRAP: Final = (
    "import runpy,sys;"
    "sys.path.insert(0,sys.argv.pop(1));"
    "runpy.run_module('experiments.code_discovery.z0_runner',run_name='__main__')"
)


class HostedRunnerError(RuntimeError):
    """A typed fail-closed runner refusal."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.host_userns_policy_evidence: Mapping[str, object] | None = None


@dataclass
class HostUsernsPolicyEvidence:
    """Non-secret evidence for one bounded host-policy window."""

    scope: str
    original_value: int
    active_value: int | None
    control_key: str = HOST_USERNS_SYSCTL_KEY
    control_path: str = os.fspath(HOST_USERNS_SYSCTL_PATH)
    mutation_performed: bool | None = None
    active_readback_verified: bool = False
    restored_value: int | None = None
    restore_readback_verified: bool = False
    normal_exit_requires_exact_restore: bool = True
    abrupt_termination_cleanup: str = "github_hosted_vm_decommission"


def _host_userns_policy_base_evidence() -> dict[str, object]:
    return {
        "scope": HOST_USERNS_SCOPE,
        "control_key": HOST_USERNS_SYSCTL_KEY,
        "control_path": os.fspath(HOST_USERNS_SYSCTL_PATH),
        "abrupt_termination_cleanup": "github_hosted_vm_decommission",
    }


def _host_userns_policy_failure_evidence(
    evidence: HostUsernsPolicyEvidence | None,
) -> dict[str, object]:
    """Return only bounded policy facts known when a window failed."""

    payload = _host_userns_policy_base_evidence()
    if evidence is None:
        payload["active_readback_verified"] = False
        payload["restore_readback_verified"] = False
        return payload
    if type(evidence.original_value) is int and evidence.original_value in {0, 1}:
        payload["original_value"] = evidence.original_value
    if type(evidence.active_value) is int and evidence.active_value in {0, 1}:
        payload["active_value"] = evidence.active_value
    if isinstance(evidence.mutation_performed, bool):
        payload["mutation_performed"] = evidence.mutation_performed
    payload["active_readback_verified"] = evidence.active_readback_verified is True
    if type(evidence.restored_value) is int and evidence.restored_value in {0, 1}:
        payload["restored_value"] = evidence.restored_value
    payload["restore_readback_verified"] = evidence.restore_readback_verified is True
    return payload


def _host_userns_policy_success_evidence(
    evidence: HostUsernsPolicyEvidence,
) -> dict[str, object]:
    """Require a complete exact restore before publishing host-policy success."""

    expected_mutation = evidence.original_value != HOST_USERNS_ACTIVE_VALUE
    if (
        evidence.scope != HOST_USERNS_SCOPE
        or evidence.control_key != HOST_USERNS_SYSCTL_KEY
        or evidence.control_path != os.fspath(HOST_USERNS_SYSCTL_PATH)
        or type(evidence.original_value) is not int
        or evidence.original_value not in {0, 1}
        or type(evidence.active_value) is not int
        or evidence.active_value != HOST_USERNS_ACTIVE_VALUE
        or evidence.mutation_performed is not expected_mutation
        or evidence.active_readback_verified is not True
        or type(evidence.restored_value) is not int
        or evidence.restored_value != evidence.original_value
        or evidence.restore_readback_verified is not True
        or evidence.abrupt_termination_cleanup != "github_hosted_vm_decommission"
    ):
        raise HostedRunnerError(
            "RECEIPT_INVALID", "host user-namespace policy evidence is incomplete"
        )
    return {
        "scope": evidence.scope,
        "control_key": evidence.control_key,
        "control_path": evidence.control_path,
        "original_value": evidence.original_value,
        "active_value": evidence.active_value,
        "mutation_performed": evidence.mutation_performed,
        "active_readback_verified": True,
        "restored_value": evidence.restored_value,
        "restore_readback_verified": True,
        "abrupt_termination_cleanup": evidence.abrupt_termination_cleanup,
    }


def is_exact_github_hosted_userns_runner(environment: Mapping[str, str]) -> bool:
    """Admit only the disposable GitHub-hosted Ubuntu 24.04 x64 image."""

    return (
        environment.get("GITHUB_ACTIONS") == "true"
        and environment.get("RUNNER_ENVIRONMENT") == "github-hosted"
        and environment.get("RUNNER_OS") == "Linux"
        and environment.get("RUNNER_ARCH") == "X64"
        and environment.get("ImageOS") == "ubuntu24"
        and bool(environment.get("RUNNER_TEMP"))
    )


@contextmanager
def _host_userns_policy_lock(environment: Mapping[str, str]) -> Iterator[None]:
    """Serialize the process-global sysctl transition within one runner VM."""

    runner_temp = Path(environment["RUNNER_TEMP"])
    try:
        parent = runner_temp.resolve(strict=True)
        parent_metadata = parent.lstat()
    except OSError as error:
        raise HostedRunnerError(
            "HOST_USERNS_POLICY_UNAVAILABLE", "runner temp is unavailable"
        ) from error
    if (
        stat.S_ISLNK(parent_metadata.st_mode)
        or not stat.S_ISDIR(parent_metadata.st_mode)
        or parent_metadata.st_uid != os.getuid()
    ):
        raise HostedRunnerError(
            "HOST_USERNS_POLICY_UNAVAILABLE", "runner temp identity is unsafe"
        )
    lock_path = parent / "codeintel-userns-policy.v1.lock"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        descriptor = os.open(lock_path, flags, 0o600)
        os.fchmod(descriptor, 0o600)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_mode & 0o077
        ):
            raise HostedRunnerError(
                "HOST_USERNS_POLICY_UNAVAILABLE", "policy lock identity is unsafe"
            )
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    except HostedRunnerError:
        raise
    except OSError as error:
        raise HostedRunnerError(
            "HOST_USERNS_POLICY_UNAVAILABLE", "policy lock could not be acquired"
        ) from error
    finally:
        if descriptor >= 0:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)


def _read_host_userns_policy() -> int:
    """Read the one admitted AppArmor user-namespace sysctl without links."""

    descriptor = -1
    try:
        descriptor = os.open(
            HOST_USERNS_SYSCTL_PATH,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise HostedRunnerError(
                "HOST_USERNS_POLICY_UNAVAILABLE", "policy path is not a regular file"
            )
        body = os.read(descriptor, 16)
        if os.read(descriptor, 1):
            raise HostedRunnerError(
                "HOST_USERNS_POLICY_UNAVAILABLE", "policy value is oversized"
            )
    except HostedRunnerError:
        raise
    except OSError as error:
        raise HostedRunnerError(
            "HOST_USERNS_POLICY_UNAVAILABLE", "policy value is unreadable"
        ) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if body not in {b"0\n", b"1\n", b"0", b"1"}:
        raise HostedRunnerError(
            "HOST_USERNS_POLICY_UNAVAILABLE", "policy value is not exactly zero or one"
        )
    return int(body.strip())


def _write_host_userns_policy(value: int, *, restoration: bool) -> None:
    """Write only the fixed sysctl key through noninteractive sudo."""

    if type(value) is not int or value not in {0, 1}:
        raise HostedRunnerError(
            (
                "HOST_USERNS_POLICY_RESTORE_FAILED"
                if restoration
                else "HOST_USERNS_POLICY_UNAVAILABLE"
            ),
            "policy target is not exactly zero or one",
        )
    code = (
        "HOST_USERNS_POLICY_RESTORE_FAILED"
        if restoration
        else "HOST_USERNS_POLICY_UNAVAILABLE"
    )
    try:
        completed = subprocess.run(
            [
                "/usr/bin/sudo",
                "-n",
                "/usr/sbin/sysctl",
                "-w",
                f"{HOST_USERNS_SYSCTL_KEY}={value}",
            ],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            close_fds=True,
            env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise HostedRunnerError(
            code, "fixed noninteractive sysctl write failed"
        ) from error
    if completed.returncode != 0:
        raise HostedRunnerError(code, "fixed noninteractive sysctl write was refused")


@contextmanager
def github_hosted_userns_policy_window(
    environment: Mapping[str, str] | None = None,
) -> Iterator[HostUsernsPolicyEvidence]:
    """Temporarily admit namespace capabilities, then prove exact restoration."""

    candidate = dict(os.environ if environment is None else environment)
    evidence: HostUsernsPolicyEvidence | None = None
    try:
        if not is_exact_github_hosted_userns_runner(candidate):
            raise HostedRunnerError(
                "HOST_USERNS_POLICY_UNAVAILABLE",
                "only the exact disposable GitHub-hosted Ubuntu 24.04 x64 runner is admitted",
            )
        with _host_userns_policy_lock(candidate):
            original = _read_host_userns_policy()
            if type(original) is not int or original not in {0, 1}:
                raise HostedRunnerError(
                    "HOST_USERNS_POLICY_UNAVAILABLE",
                    "policy original is not exactly zero or one",
                )
            evidence = HostUsernsPolicyEvidence(
                scope=HOST_USERNS_SCOPE,
                original_value=original,
                active_value=None,
            )
            activation_attempted = False
            try:
                if original != HOST_USERNS_ACTIVE_VALUE:
                    activation_attempted = True
                    _write_host_userns_policy(
                        HOST_USERNS_ACTIVE_VALUE, restoration=False
                    )
                    evidence.mutation_performed = True
                else:
                    evidence.mutation_performed = False
                active_value = _read_host_userns_policy()
                if type(active_value) is int and active_value in {0, 1}:
                    evidence.active_value = active_value
                if active_value != HOST_USERNS_ACTIVE_VALUE:
                    raise HostedRunnerError(
                        "HOST_USERNS_POLICY_UNAVAILABLE",
                        "policy active-value readback differs",
                    )
                evidence.active_readback_verified = True
                yield evidence
            finally:
                try:
                    if activation_attempted:
                        _write_host_userns_policy(original, restoration=True)
                    restored_value = _read_host_userns_policy()
                    if type(restored_value) is not int or restored_value != original:
                        raise HostedRunnerError(
                            "HOST_USERNS_POLICY_RESTORE_FAILED",
                            "policy restored-value readback differs",
                        )
                    evidence.restored_value = restored_value
                    evidence.restore_readback_verified = True
                except HostedRunnerError as error:
                    if error.code == "HOST_USERNS_POLICY_RESTORE_FAILED":
                        raise
                    raise HostedRunnerError(
                        "HOST_USERNS_POLICY_RESTORE_FAILED",
                        "exact original policy could not be restored",
                    ) from error
    except HostedRunnerError as error:
        error.host_userns_policy_evidence = _host_userns_policy_failure_evidence(
            evidence
        )
        raise


class _PhasePProxyServer(socketserver.ThreadingUnixStreamServer):
    """Pathname-socket CONNECT gate in the parent network namespace."""

    allow_reuse_address = False
    daemon_threads = True
    block_on_close = False
    request_queue_size = 64

    def handle_error(self, request: object, client_address: object) -> None:
        del request, client_address


class _PhasePProxyHandler(socketserver.BaseRequestHandler):
    """Forward TLS only when the CONNECT authority is pinned by the lock."""

    def handle(self) -> None:
        client = self.request
        try:
            client.settimeout(15)
            header = bytearray()
            while b"\r\n\r\n" not in header:
                block = client.recv(4096)
                if not block:
                    return
                header.extend(block)
                if len(header) > _CONNECT_HEADER_MAX_BYTES:
                    _send_proxy_response(client, "431 Request Header Fields Too Large")
                    return
            raw_header, pending = bytes(header).split(b"\r\n\r\n", 1)
            request_line = raw_header.split(b"\r\n", 1)[0].decode("ascii")
            method, authority, version = request_line.split(" ")
            if method != "CONNECT" or version not in {"HTTP/1.0", "HTTP/1.1"}:
                _send_proxy_response(client, "405 Method Not Allowed")
                return
            if authority.count(":") != 1:
                _send_proxy_response(client, "403 Forbidden")
                return
            host, port = authority.rsplit(":", 1)
            host = host.lower()
            if (
                port != "443"
                or _CONNECT_HOST_RE.fullmatch(host) is None
                or not _acquisition_host_allowed(host)
            ):
                _send_proxy_response(client, "403 Forbidden")
                return
            try:
                upstream = socket.create_connection((host, 443), timeout=30)
            except OSError:
                _send_proxy_response(client, "502 Bad Gateway")
                return
            with upstream:
                client.settimeout(None)
                upstream.settimeout(None)
                _send_proxy_response(client, "200 Connection Established")
                if pending:
                    upstream.sendall(pending)
                _relay_proxy_tunnel(client, upstream)
        except (OSError, UnicodeDecodeError, ValueError):
            return


def _send_proxy_response(connection: socket.socket, status: str) -> None:
    if status == "200 Connection Established":
        response = f"HTTP/1.1 {status}\r\n\r\n"
    else:
        response = (
            f"HTTP/1.1 {status}\r\nConnection: close\r\nContent-Length: 0\r\n\r\n"
        )
    connection.sendall(response.encode("ascii"))


def _relay_proxy_tunnel(client: socket.socket, upstream: socket.socket) -> None:
    selector = selectors.DefaultSelector()
    try:
        selector.register(client, selectors.EVENT_READ, upstream)
        selector.register(upstream, selectors.EVENT_READ, client)
        while True:
            events = selector.select(timeout=900)
            if not events:
                return
            for key, _mask in events:
                source = key.fileobj
                destination = key.data
                block = source.recv(65_536)
                if not block:
                    return
                destination.sendall(block)
    finally:
        selector.close()


def _acquisition_host_allowed(host: str) -> bool:
    """Match one exact host or a strict subdomain of one reviewed suffix."""

    if not isinstance(host, str) or host != host.lower():
        return False
    if _CONNECT_HOST_RE.fullmatch(host) is None:
        return False
    return host in locks.ALLOWED_HOSTS or any(
        host.endswith(f".{suffix}") for suffix in locks.ALLOWED_HOST_SUFFIXES
    )


def _phase_p_client_environment(
    proxy_url: str,
    home: Path,
    *,
    gate_socket: Path | None = None,
) -> dict[str, str]:
    """Return a closed subprocess environment that cannot bypass the proxy."""

    try:
        parsed = urlparse(proxy_url)
        port = parsed.port
    except ValueError as error:
        raise HostedRunnerError(
            "ACQUISITION_ALLOWLIST_UNAVAILABLE", "proxy URL is malformed"
        ) from error
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or port is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise HostedRunnerError(
            "ACQUISITION_ALLOWLIST_UNAVAILABLE", "proxy URL is not loopback-only"
        )
    environment = {
        "ALL_PROXY": proxy_url,
        "HTTP_PROXY": proxy_url,
        "HTTPS_PROXY": proxy_url,
        "HOME": os.fspath(Path(home).resolve()),
        "LANG": "C",
        "LC_ALL": "C",
        "NO_PROXY": "",
        "PATH": "/usr/bin:/bin",
        "TZ": "UTC",
        "all_proxy": proxy_url,
        "http_proxy": proxy_url,
        "https_proxy": proxy_url,
        "no_proxy": "",
        _PHASE_P_GATE_ENV: os.fspath(
            Path(gate_socket if gate_socket is not None else home / "gate.sock")
        ),
    }
    return environment


def _validated_phase_p_client_environment(
    network_environment: Mapping[str, str],
) -> dict[str, str]:
    """Reject any missing, changed, or ambient field at a network client seam."""

    try:
        proxy_url = network_environment["HTTPS_PROXY"]
        home = Path(network_environment["HOME"])
        gate_socket = Path(network_environment[_PHASE_P_GATE_ENV])
    except (KeyError, TypeError, ValueError) as error:
        raise HostedRunnerError(
            "ACQUISITION_ALLOWLIST_UNAVAILABLE", "client environment is incomplete"
        ) from error
    if not isinstance(proxy_url, str):
        raise HostedRunnerError(
            "ACQUISITION_ALLOWLIST_UNAVAILABLE", "client proxy is malformed"
        )
    expected = _phase_p_client_environment(proxy_url, home, gate_socket=gate_socket)
    if dict(network_environment) != expected:
        raise HostedRunnerError(
            "ACQUISITION_ALLOWLIST_UNAVAILABLE", "client environment is not closed"
        )
    return expected


def _phase_p_proxy_port(network_environment: Mapping[str, str]) -> int:
    """Return the exact unprivileged loopback proxy port or refuse closed."""

    environment = _validated_phase_p_client_environment(network_environment)
    try:
        port = urlparse(environment["HTTPS_PROXY"]).port
    except ValueError as error:  # pragma: no cover - validated above, defense in depth
        raise HostedRunnerError(
            "ACQUISITION_ALLOWLIST_UNAVAILABLE", "proxy port is malformed"
        ) from error
    if port is None or not 1024 < port <= 65_535 or port == 443:
        raise HostedRunnerError(
            "ACQUISITION_ALLOWLIST_UNAVAILABLE",
            "proxy port cannot anchor the process egress boundary",
        )
    return port


def _phase_p_gate_socket(network_environment: Mapping[str, str]) -> Path:
    """Return the live parent-namespace Unix gate after exact inode checks."""

    environment = _validated_phase_p_client_environment(network_environment)
    gate = Path(environment[_PHASE_P_GATE_ENV])
    if not gate.is_absolute() or len(os.fsencode(gate)) > 100:
        raise HostedRunnerError(
            "ACQUISITION_ALLOWLIST_UNAVAILABLE", "gate socket path is unsafe"
        )
    try:
        metadata = gate.lstat()
        parent_metadata = gate.parent.lstat()
    except OSError as error:
        raise HostedRunnerError(
            "ACQUISITION_ALLOWLIST_UNAVAILABLE", "gate socket is unavailable"
        ) from error
    if (
        not stat.S_ISSOCK(metadata.st_mode)
        or not stat.S_ISDIR(parent_metadata.st_mode)
        or stat.S_ISLNK(parent_metadata.st_mode)
        or parent_metadata.st_uid != os.getuid()
        or parent_metadata.st_mode & 0o077
    ):
        raise HostedRunnerError(
            "ACQUISITION_ALLOWLIST_UNAVAILABLE", "gate socket identity is unsafe"
        )
    return gate


def _validated_phase_p_process_environment(
    environment: Mapping[str, str],
    network_environment: Mapping[str, str],
) -> dict[str, str]:
    """Keep every proxy field identical while permitting fixed tool settings."""

    network = _validated_phase_p_client_environment(network_environment)
    try:
        candidate = dict(environment)
    except (TypeError, ValueError) as error:
        raise HostedRunnerError(
            "ACQUISITION_ALLOWLIST_UNAVAILABLE", "process environment is malformed"
        ) from error
    if any(
        not isinstance(key, str)
        or not isinstance(value, str)
        or not key
        or "\x00" in key
        or "=" in key
        or "\x00" in value
        for key, value in candidate.items()
    ):
        raise HostedRunnerError(
            "ACQUISITION_ALLOWLIST_UNAVAILABLE", "process environment is malformed"
        )
    if any(candidate.get(key) != value for key, value in network.items()):
        raise HostedRunnerError(
            "ACQUISITION_ALLOWLIST_UNAVAILABLE",
            "process environment changed the network boundary",
        )
    allowed_proxy_keys = frozenset(network)
    for key in candidate:
        normalized = key.lower()
        if (
            normalized.endswith("_proxy")
            or normalized in {"all_proxy", "http_proxy", "https_proxy", "no_proxy"}
        ) and key not in allowed_proxy_keys:
            raise HostedRunnerError(
                "ACQUISITION_ALLOWLIST_UNAVAILABLE",
                "process environment adds an alternate proxy control",
            )
    return candidate


def _invoke_phase_p_boundary(
    command: Sequence[str], **kwargs: Any
) -> subprocess.CompletedProcess[Any]:
    """Run one isolated wrapper and kill every residual member of its process group."""

    timeout = kwargs.pop("timeout")
    check = kwargs.pop("check")
    if check is not False:  # pragma: no cover - private caller invariant
        raise AssertionError("boundary wrapper must return its exact status")
    process = subprocess.Popen(command, **kwargs)

    def kill_group() -> None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    try:
        try:
            stdout_data, stderr_data = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as error:
            kill_group()
            try:
                process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                for stream in (process.stdout, process.stderr):
                    if stream is not None:
                        stream.close()
            raise error
    finally:
        # The target cannot create a new session or process group after seccomp.
        # Kill any forked descendant left after its tracked leader terminates.
        kill_group()
    assert process.returncode is not None
    return subprocess.CompletedProcess(
        command,
        process.returncode,
        stdout=stdout_data,
        stderr=stderr_data,
    )


def _run_phase_p_process(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    network_environment: Mapping[str, str],
    timeout: float,
    text: bool,
    stdout: int | io.BufferedWriter = subprocess.PIPE,
) -> subprocess.CompletedProcess[Any]:
    """Run one client after a child-only kernel TCP/datagram boundary is live."""

    if (
        not argv
        or any(not isinstance(value, str) or "\x00" in value for value in argv)
        or not Path(argv[0]).is_absolute()
    ):
        raise HostedRunnerError("INVALID_ARGV", "phase P subprocess argv is malformed")
    process_environment = _validated_phase_p_process_environment(
        env, network_environment
    )
    proxy_port = _phase_p_proxy_port(network_environment)
    gate_socket = _phase_p_gate_socket(network_environment)
    process_environment.pop(_PHASE_P_GATE_ENV)
    status_read, status_write = os.pipe()
    os.set_blocking(status_read, False)
    completed: subprocess.CompletedProcess[Any] | None = None
    caught: OSError | subprocess.TimeoutExpired | None = None
    try:
        try:
            completed = _invoke_phase_p_boundary(
                [
                    "/usr/bin/unshare",
                    "--user",
                    "--map-current-user",
                    "--keep-caps",
                    "--mount",
                    "--net",
                    "--",
                    "/usr/bin/python3",
                    "-I",
                    "-S",
                    "-c",
                    _PHASE_P_BOUNDARY_BOOTSTRAP,
                    str(status_write),
                    str(proxy_port),
                    os.fspath(gate_socket),
                    *argv,
                ],
                cwd=os.fspath(cwd),
                env=process_environment,
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=subprocess.PIPE,
                text=text,
                timeout=timeout,
                close_fds=True,
                pass_fds=(status_write,),
                start_new_session=True,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            caught = error
    finally:
        os.close(status_write)
        try:
            try:
                boundary_status = os.read(status_read, 256)
            except BlockingIOError:
                boundary_status = b""
        finally:
            os.close(status_read)
    if boundary_status != _PHASE_P_BOUNDARY_READY:
        raise HostedRunnerError(
            "ACQUISITION_ALLOWLIST_UNAVAILABLE",
            "kernel process egress boundary could not be established",
        ) from caught
    if caught is not None:
        raise HostedRunnerError("SUBPROCESS_FAILED", Path(argv[0]).name) from caught
    assert completed is not None
    return completed


def _run_phase_p_checked(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    network_environment: Mapping[str, str],
    timeout: float = 60,
) -> subprocess.CompletedProcess[str]:
    """Run a fixed Phase-P network client and return bounded text."""

    completed = _run_phase_p_process(
        argv,
        cwd=cwd,
        env=env,
        network_environment=network_environment,
        timeout=timeout,
        text=True,
    )
    if completed.returncode != 0:
        detail = _bounded_redacted(completed.stderr or completed.stdout, 2048)
        raise HostedRunnerError(
            "SUBPROCESS_FAILED",
            f"{Path(argv[0]).name} exited {completed.returncode}: {detail}",
        )
    return completed


@contextmanager
def _phase_p_allowlist_proxy(home: Path) -> Iterator[dict[str, str]]:
    """Yield a scrubbed environment backed by a parent-namespace CONNECT gate."""

    network_home = _fresh_directory(home, "ACQUISITION_ALLOWLIST_UNAVAILABLE")
    (network_home / "gh").mkdir(mode=0o700)
    gate_directory: Path | None = None
    try:
        gate_directory = Path(tempfile.mkdtemp(prefix="ci-p-", dir="/tmp"))
        os.chmod(gate_directory, 0o700)
        gate_socket = gate_directory / "gate.sock"
        server = _PhasePProxyServer(os.fspath(gate_socket), _PhasePProxyHandler)
    except OSError as error:
        if gate_directory is not None:
            shutil.rmtree(gate_directory, ignore_errors=True)
        raise HostedRunnerError(
            "ACQUISITION_ALLOWLIST_UNAVAILABLE", "parent CONNECT gate could not bind"
        ) from error
    thread = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.05},
        name="codeintel-phase-p-allowlist",
        daemon=True,
    )
    started = False
    try:
        thread.start()
        started = True
        if server.server_address != os.fspath(gate_socket):
            raise HostedRunnerError(
                "ACQUISITION_ALLOWLIST_UNAVAILABLE", "parent gate identity differs"
            )
        yield _phase_p_client_environment(
            f"http://127.0.0.1:{_PHASE_P_PROXY_PORT}",
            network_home,
            gate_socket=gate_socket,
        )
    finally:
        if started:
            server.shutdown()
        server.server_close()
        if started:
            thread.join(timeout=5)
        if gate_directory is not None:
            shutil.rmtree(gate_directory, ignore_errors=True)


def _github_client_environment(
    network_environment: Mapping[str, str],
) -> dict[str, str]:
    """Add only the workflow token and fixed gh configuration to the closed env."""

    environment = _validated_phase_p_client_environment(network_environment)
    environment.update(
        {
            "GH_CONFIG_DIR": os.fspath(Path(environment["HOME"]) / "gh"),
            "GH_HOST": "github.com",
            "GH_PROMPT_DISABLED": "1",
        }
    )
    token = os.environ.get("GH_TOKEN")
    if token:
        environment["GH_TOKEN"] = token
    return environment


@dataclass(frozen=True)
class ExperimentRequest:
    """The complete normalized identity of one fixed Z0 experiment request."""

    operation_key: str
    consumer_sha: str
    consumer_tree_sha: str
    forge_sha: str
    forge_tree_sha: str
    lock_sha256: str
    workflow_sha256: str
    mode: str = "Z0"
    repository: str = FIXED_REPOSITORY

    @classmethod
    def from_values(
        cls,
        *,
        operation_key: str,
        consumer_sha: str,
        consumer_tree_sha: str,
        forge_sha: str,
        forge_tree_sha: str,
        lock_sha256: str,
        workflow_sha256: str,
    ) -> ExperimentRequest:
        if (
            operation_key != Z0_OPERATION_KEY
            or _OPERATION_RE.fullmatch(operation_key) is None
        ):
            raise HostedRunnerError(
                "INVALID_REQUEST", "operation_key is not the fixed Z0 key"
            )
        for label, value, pattern in (
            ("consumer_sha", consumer_sha, _SHA1_RE),
            ("consumer_tree_sha", consumer_tree_sha, _SHA1_RE),
            ("forge_sha", forge_sha, _SHA1_RE),
            ("forge_tree_sha", forge_tree_sha, _SHA1_RE),
            ("lock_sha256", lock_sha256, _SHA256_RE),
            ("workflow_sha256", workflow_sha256, _SHA256_RE),
        ):
            if not isinstance(value, str) or pattern.fullmatch(value) is None:
                raise HostedRunnerError(
                    "INVALID_REQUEST", f"{label} must be an exact digest"
                )
        return cls(
            operation_key=operation_key,
            consumer_sha=consumer_sha,
            consumer_tree_sha=consumer_tree_sha,
            forge_sha=forge_sha,
            forge_tree_sha=forge_tree_sha,
            lock_sha256=lock_sha256,
            workflow_sha256=workflow_sha256,
        )

    @property
    def payload(self) -> dict[str, str]:
        return {
            "consumer_sha": self.consumer_sha,
            "consumer_tree_sha": self.consumer_tree_sha,
            "forge_sha": self.forge_sha,
            "forge_tree_sha": self.forge_tree_sha,
            "lock_sha256": self.lock_sha256,
            "mode": self.mode,
            "operation_key": self.operation_key,
            "repository": self.repository,
            "workflow_sha256": self.workflow_sha256,
        }

    @property
    def canonical_bytes(self) -> bytes:
        return locks.canonical_json_bytes(self.payload)

    @property
    def digest(self) -> str:
        return locks.sha256_bytes(self.canonical_bytes)


@dataclass(frozen=True)
class ConsumerIdentity:
    commit_sha: str
    tree_sha: str
    repository: str
    branch: str


@dataclass(frozen=True)
class ConsumerSealRoot:
    role: str
    path: Path
    path_sha256: str
    device: int
    inode: int
    seal_id: str


@dataclass(frozen=True)
class ConsumerGitSealLayout:
    roots: tuple[ConsumerSealRoot, ...]

    @property
    def unique_roots(self) -> tuple[ConsumerSealRoot, ...]:
        observed: set[str] = set()
        unique: list[ConsumerSealRoot] = []
        for row in self.roots:
            if row.seal_id not in observed:
                observed.add(row.seal_id)
                unique.append(row)
        return tuple(unique)


@dataclass(frozen=True)
class BundleIdentity:
    path: Path
    name: str
    sha256: str
    size: int
    manifest_sha256: str


@dataclass(frozen=True)
class VerifiedBundle:
    path: Path
    sha256: str
    size: int
    manifest: Mapping[str, Any]
    manifest_sha256: str


class ReplayDisposition(enum.Enum):
    PROCEED = "PROCEED"
    RETURN_PRIOR = "RETURN_PRIOR"


@dataclass(frozen=True)
class ReplayResolution:
    disposition: ReplayDisposition
    receipt: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class NetworkSealProof:
    interfaces: tuple[str, ...]
    non_loopback_routes: tuple[str, ...]
    outbound_probe: str
    denial_errno: int | None


@dataclass(frozen=True)
class LaunchEvidence:
    returncode: int
    pid: int
    process_group: int
    stdout_sha256: str
    stderr_sha256: str
    stdout_bytes: int
    stderr_bytes: int
    user_seconds: float
    system_seconds: float
    max_rss_kib: int


@dataclass(frozen=True)
class CleanupEvidence:
    process_group_dead: bool
    unexpected_residue: tuple[str, ...]


def run_checked(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
    timeout: float = 60,
) -> subprocess.CompletedProcess[str]:
    """Run a fixed argv without shell interpretation and return bounded text."""

    if not argv or any(not isinstance(value, str) or "\x00" in value for value in argv):
        raise HostedRunnerError("INVALID_ARGV", "subprocess argv is malformed")
    try:
        completed = subprocess.run(
            list(argv),
            cwd=os.fspath(cwd),
            env=dict(env) if env is not None else None,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise HostedRunnerError("SUBPROCESS_FAILED", Path(argv[0]).name) from error
    if completed.returncode != 0:
        detail = _bounded_redacted(completed.stderr or completed.stdout, 2048)
        raise HostedRunnerError(
            "SUBPROCESS_FAILED",
            f"{Path(argv[0]).name} exited {completed.returncode}: {detail}",
        )
    return completed


def git_stdout(root: Path, *arguments: str) -> str:
    try:
        return _git_bytes(root, *arguments).decode("utf-8").strip()
    except UnicodeDecodeError as error:
        raise HostedRunnerError(
            "GIT_INSPECTION_FAILED", "Git returned non-UTF-8 identity bytes"
        ) from error


def verify_consumer_checkout(
    consumer_root: Path, expected_sha: str, expected_tree_sha: str
) -> ConsumerIdentity:
    """Re-derive exact consumer identity from a clean same-repository checkout."""

    if (
        _SHA1_RE.fullmatch(expected_sha) is None
        or _SHA1_RE.fullmatch(expected_tree_sha) is None
    ):
        raise HostedRunnerError("CONSUMER_MISMATCH", "expected identity is not exact")
    root = _real_directory(consumer_root, "CONSUMER_MISMATCH")
    remote = git_stdout(root, "remote", "get-url", "origin")
    repository = _normalize_github_remote(remote)
    if repository != FIXED_REPOSITORY:
        raise HostedRunnerError(
            "CONSUMER_REPOSITORY_MISMATCH",
            "consumer origin is not the fixed repository",
        )
    if git_stdout(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise HostedRunnerError(
            "CONSUMER_DIRTY", "consumer checkout has uncommitted bytes"
        )
    head = git_stdout(root, "rev-parse", "--verify", "HEAD")
    tree = git_stdout(root, "rev-parse", "--verify", "HEAD^{tree}")
    if head != expected_sha or tree != expected_tree_sha:
        raise HostedRunnerError("CONSUMER_MISMATCH", "consumer HEAD/tree differs")
    try:
        branch = git_stdout(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    except HostedRunnerError:
        branch = "DETACHED"
    for raw in _git_bytes(root, "ls-files", "-s", "-z").split(b"\0"):
        if not raw:
            continue
        try:
            header, raw_path = raw.split(b"\t", 1)
            mode, object_id, stage = header.decode("ascii").split(" ")
            path = raw_path.decode("utf-8")
        except (UnicodeDecodeError, ValueError) as error:
            raise HostedRunnerError(
                "CONSUMER_CENSUS_INVALID", "malformed Git index"
            ) from error
        if (
            mode not in {"100644", "100755", "120000", "160000"}
            or stage != "0"
            or _SHA1_RE.fullmatch(object_id) is None
        ):
            raise HostedRunnerError(
                "CONSUMER_CENSUS_INVALID", f"consumer index row is invalid for {path}"
            )
    return ConsumerIdentity(head, tree, repository, branch)


def _closed_git_directory(root: Path, *arguments: str) -> Path:
    raw = _git_bytes(root, "rev-parse", *arguments)
    if not raw.endswith(b"\n") or raw.count(b"\n") != 1 or b"\r" in raw:
        raise HostedRunnerError(
            "CONSUMER_GIT_METADATA_UNSAFE", "Git metadata path is ambiguous"
        )
    try:
        text = raw[:-1].decode("utf-8")
    except UnicodeDecodeError as error:
        raise HostedRunnerError(
            "CONSUMER_GIT_METADATA_UNSAFE", "Git metadata path is not UTF-8"
        ) from error
    candidate = Path(text)
    if not candidate.is_absolute() or "\x00" in text:
        raise HostedRunnerError(
            "CONSUMER_GIT_METADATA_UNSAFE", "Git metadata path is not absolute"
        )
    resolved = _real_directory(candidate, "CONSUMER_GIT_METADATA_UNSAFE")
    if candidate != resolved:
        raise HostedRunnerError(
            "CONSUMER_GIT_METADATA_UNSAFE",
            "Git metadata path contains a symlink or noncanonical component",
        )
    return resolved


def _consumer_git_seal_layout(consumer_root: Path) -> ConsumerGitSealLayout:
    """Resolve the source, per-worktree Git dir, and shared Git dir exactly."""

    source = _real_directory(consumer_root, "CONSUMER_MOUNT_SEAL_UNSAFE")
    git_dir = _closed_git_directory(source, "--absolute-git-dir")
    common_dir = _closed_git_directory(
        source, "--path-format=absolute", "--git-common-dir"
    )
    dot_git = source / ".git"
    try:
        dot_git_metadata = dot_git.lstat()
    except OSError as error:
        raise HostedRunnerError(
            "CONSUMER_GIT_METADATA_UNSAFE", ".git entry is unavailable"
        ) from error
    if stat.S_ISLNK(dot_git_metadata.st_mode):
        raise HostedRunnerError(
            "CONSUMER_GIT_METADATA_UNSAFE", ".git entry must not be a symlink"
        )
    if stat.S_ISDIR(dot_git_metadata.st_mode):
        if dot_git.resolve() != git_dir or common_dir != git_dir:
            raise HostedRunnerError(
                "CONSUMER_GIT_METADATA_UNSAFE",
                "normal checkout Git metadata identity differs",
            )
    elif stat.S_ISREG(dot_git_metadata.st_mode):
        if dot_git_metadata.st_size > 4096:
            raise HostedRunnerError(
                "CONSUMER_GIT_METADATA_UNSAFE", "linked-worktree .git file is oversized"
            )
        try:
            body = dot_git.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise HostedRunnerError(
                "CONSUMER_GIT_METADATA_UNSAFE",
                "linked-worktree .git file is unreadable",
            ) from error
        if (
            not body.endswith("\n")
            or body.count("\n") != 1
            or not body.startswith("gitdir: ")
        ):
            raise HostedRunnerError(
                "CONSUMER_GIT_METADATA_UNSAFE",
                "linked-worktree .git file is ambiguous",
            )
        pointer = Path(body.removeprefix("gitdir: ").removesuffix("\n"))
        if not pointer.is_absolute():
            pointer = source / pointer
        if pointer.resolve() != git_dir:
            raise HostedRunnerError(
                "CONSUMER_GIT_METADATA_UNSAFE",
                "linked-worktree Git directory identity differs",
            )
        try:
            git_dir.relative_to(common_dir)
        except ValueError as error:
            raise HostedRunnerError(
                "CONSUMER_GIT_METADATA_UNSAFE",
                "linked-worktree Git directory escapes its common directory",
            ) from error
    else:
        raise HostedRunnerError(
            "CONSUMER_GIT_METADATA_UNSAFE", ".git entry has an unsafe type"
        )

    role_paths = (
        ("consumer_source", source),
        ("git_worktree_dir", git_dir),
        ("git_common_dir", common_dir),
    )
    identities: dict[tuple[int, int], str] = {}
    roots: list[ConsumerSealRoot] = []
    for role, path in role_paths:
        try:
            metadata = path.lstat()
        except OSError as error:  # pragma: no cover - closed helper already checked
            raise HostedRunnerError(
                "CONSUMER_GIT_METADATA_UNSAFE", f"{role} is unavailable"
            ) from error
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise HostedRunnerError(
                "CONSUMER_GIT_METADATA_UNSAFE", f"{role} is not a real directory"
            )
        object_id = (metadata.st_dev, metadata.st_ino)
        seal_id = identities.setdefault(object_id, f"seal-{len(identities)}")
        roots.append(
            ConsumerSealRoot(
                role=role,
                path=path,
                path_sha256=locks.sha256_bytes(os.fsencode(path)),
                device=metadata.st_dev,
                inode=metadata.st_ino,
                seal_id=seal_id,
            )
        )
    return ConsumerGitSealLayout(tuple(roots))


def _verify_consumer_git_seal(consumer_root: Path) -> Mapping[str, object]:
    """Re-derive every mounted identity and emit path-free receipt evidence."""

    layout = _consumer_git_seal_layout(consumer_root)
    for row in layout.unique_roots:
        metadata = row.path.lstat()
        if (metadata.st_dev, metadata.st_ino) != (row.device, row.inode):
            raise HostedRunnerError(
                "CONSUMER_MOUNT_SEAL_UNAVAILABLE",
                f"{row.role} device/inode changed",
            )
        if not os.statvfs(row.path).f_flag & os.ST_RDONLY:
            raise HostedRunnerError(
                "CONSUMER_MOUNT_SEAL_UNAVAILABLE",
                f"{row.role} is not read-only",
            )
    evidence: dict[str, object] = {
        "mount_namespace_private": True,
        "requested_mount_options": ["ro", "nosuid", "nodev", "noexec"],
        "unique_mount_count": len(layout.unique_roots),
        "namespace_exit_discards_mounts": True,
        "roots": [
            {
                "role": row.role,
                "seal_id": row.seal_id,
                "path_sha256": row.path_sha256,
                "device": row.device,
                "inode": row.inode,
                "device_inode_verified": True,
                "read_only_verified": True,
            }
            for row in layout.roots
        ],
    }
    assert_secret_free(evidence)
    return evidence


def validate_consumer_paths(paths: Iterable[str]) -> tuple[str, ...]:
    """Validate the effective diff against the frozen Z0 source ceiling."""

    normalized: list[str] = []
    for value in paths:
        if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
            raise HostedRunnerError("CONSUMER_PATH_VIOLATION", "invalid changed path")
        candidate = PurePosixPath(value)
        if candidate.is_absolute() or any(
            part in {"", ".", ".."} for part in candidate.parts
        ):
            raise HostedRunnerError("CONSUMER_PATH_VIOLATION", value)
        canonical = candidate.as_posix()
        if not (
            canonical in _ALLOWED_CONSUMER_EXACT
            or any(
                canonical.startswith(prefix) for prefix in _ALLOWED_CONSUMER_PREFIXES
            )
        ):
            raise HostedRunnerError("CONSUMER_PATH_VIOLATION", canonical)
        normalized.append(canonical)
    if not normalized:
        raise HostedRunnerError("CONSUMER_PATH_VIOLATION", "consumer diff is empty")
    if len(set(normalized)) != len(normalized):
        raise HostedRunnerError(
            "CONSUMER_PATH_VIOLATION", "consumer diff has duplicates"
        )
    if "experiments/code_discovery/z0_runner.py" not in normalized:
        raise HostedRunnerError("CONSUMER_PATH_VIOLATION", "fixed Z0 runner is absent")
    return tuple(sorted(normalized))


def consumer_effective_paths(
    repository_root: Path, *, consumer_sha: str, forge_sha: str
) -> tuple[str, tuple[str, ...]]:
    """Derive the merge-base path census for the exact same-repository consumer."""

    root = _real_directory(repository_root, "CONSUMER_MISMATCH")
    for value in (consumer_sha, forge_sha):
        if _SHA1_RE.fullmatch(value) is None:
            raise HostedRunnerError("CONSUMER_MISMATCH", "commit identity is not exact")
        git_stdout(root, "cat-file", "-e", f"{value}^{{commit}}")
    base = git_stdout(root, "merge-base", consumer_sha, forge_sha)
    if _SHA1_RE.fullmatch(base) is None:
        raise HostedRunnerError("CONSUMER_MISMATCH", "merge-base is ambiguous")
    raw = _git_bytes(
        root,
        "diff",
        "--no-renames",
        "--name-only",
        "--diff-filter=ACDMRTUXB",
        "-z",
        base,
        consumer_sha,
    )
    try:
        paths = [item.decode("utf-8") for item in raw.split(b"\0") if item]
    except UnicodeDecodeError as error:
        raise HostedRunnerError(
            "CONSUMER_PATH_VIOLATION", "non-UTF-8 changed path"
        ) from error
    validated = validate_consumer_paths(paths)
    tree_rows = _git_bytes(root, "ls-tree", "-z", consumer_sha, "--", *validated)
    observed: set[str] = set()
    for raw in tree_rows.split(b"\0"):
        if not raw:
            continue
        try:
            header, raw_path = raw.split(b"\t", 1)
            mode, kind, object_id = header.decode("ascii").split(" ")
            path = raw_path.decode("utf-8")
        except (UnicodeDecodeError, ValueError) as error:
            raise HostedRunnerError(
                "CONSUMER_CENSUS_INVALID", "malformed consumer tree row"
            ) from error
        if (
            mode not in {"100644", "100755"}
            or kind != "blob"
            or _SHA1_RE.fullmatch(object_id) is None
            or path not in validated
            or path in observed
        ):
            raise HostedRunnerError(
                "CONSUMER_FILE_UNSAFE", f"changed consumer path is not regular: {path}"
            )
        observed.add(path)
    if observed != set(validated):
        raise HostedRunnerError(
            "CONSUMER_FILE_UNSAFE",
            "changed consumer paths are absent from the exact tree",
        )
    return base, validated


def selected_source_digest(
    root: Path, *, includes: Sequence[str], excludes: Sequence[str]
) -> str:
    """Mirror the protected Z0 consumer's selected regular-file digest."""

    source_root = _real_directory(root, "CONSUMER_MISMATCH")
    rows: list[tuple[str, bytes]] = []
    raw = _git_bytes(source_root, "ls-files", "-s", "-z")
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        header, raw_path = entry.split(b"\t", 1)
        mode, object_id, stage = header.decode("ascii").split(" ")
        relative = raw_path.decode("utf-8")
        path = PurePosixPath(relative)
        selected = any(path.match(rule) for rule in includes)
        omitted = any(path.match(rule) for rule in excludes)
        if selected and omitted:
            raise HostedRunnerError(
                "CONSUMER_PATH_VIOLATION", f"overlapping rule for {relative}"
            )
        if selected:
            if (
                mode not in {"100644", "100755"}
                or stage != "0"
                or _SHA1_RE.fullmatch(object_id) is None
            ):
                raise HostedRunnerError("CONSUMER_FILE_UNSAFE", relative)
            file_path = source_root / relative
            metadata = file_path.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                raise HostedRunnerError("CONSUMER_FILE_UNSAFE", relative)
            body = file_path.read_bytes()
            if locks.git_blob_sha1(body) != object_id:
                raise HostedRunnerError(
                    "CONSUMER_FILE_UNSAFE", f"working bytes differ from Git blob: {relative}"
                )
            rows.append((relative, hashlib.sha256(body).digest()))
    if not rows:
        raise HostedRunnerError(
            "CONSUMER_PATH_VIOLATION", "index rules select no files"
        )
    digest = hashlib.sha256()
    for relative, content_digest in sorted(rows):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content_digest)
        digest.update(b"\0")
    return digest.hexdigest()


def create_content_addressed_bundle(
    payload_root: Path, output_directory: Path, *, context: Mapping[str, object]
) -> BundleIdentity:
    """Create canonical gzip/tar bytes and name them by their complete SHA-256."""

    root = _real_directory(payload_root, "BUNDLE_PAYLOAD_UNSAFE")
    files = _bundle_payload_census(root)
    missing = _REQUIRED_BUNDLE_FILES - {path for path, _file, _mode in files}
    if missing:
        raise HostedRunnerError(
            "BUNDLE_PAYLOAD_INCOMPLETE", f"missing {sorted(missing)}"
        )
    assert_secret_free(context)
    manifest_files = [
        {
            "path": relative,
            "role": _bundle_role(relative),
            "mode": f"{mode:04o}",
            "size": file_path.stat().st_size,
            "sha256": locks.sha256_file(file_path, max_bytes=locks.GO_ARCHIVE_SIZE * 2),
        }
        for relative, file_path, mode in files
    ]
    manifest = {
        "schema_version": BUNDLE_MANIFEST_SCHEMA_VERSION,
        "mode": "Z0",
        "context": dict(context),
        "files": manifest_files,
    }
    assert_secret_free(manifest)
    manifest_bytes = locks.canonical_json_bytes(manifest) + b"\n"
    manifest_sha256 = locks.sha256_bytes(manifest_bytes)

    output = _ensure_output_directory(output_directory)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".codeintel-z0-", dir=output)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with temporary.open("wb") as raw_output:
            with gzip.GzipFile(
                filename="", fileobj=raw_output, mode="wb", compresslevel=9, mtime=0
            ) as compressed:
                with tarfile.open(
                    fileobj=compressed, mode="w", format=tarfile.GNU_FORMAT
                ) as archive:
                    directory_names = {
                        str(parent)
                        for relative, _file, _mode in files
                        for parent in PurePosixPath(relative).parents
                        if str(parent) != "."
                    }
                    for directory in sorted(directory_names):
                        _add_tar_directory(archive, directory)
                    for relative, file_path, mode in files:
                        _add_tar_file(archive, relative, file_path, mode)
                    _add_tar_bytes(archive, "manifest.json", manifest_bytes, 0o644)
        size = temporary.stat().st_size
        if size > 268_435_456:
            raise HostedRunnerError("BUNDLE_TOO_LARGE", str(size))
        digest = locks.sha256_file(temporary, max_bytes=268_435_456)
        name = f"codeintel-z0-{digest}.tar.gz"
        target = output / name
        if target.exists() or target.is_symlink():
            if (
                target.is_symlink()
                or not target.is_file()
                or locks.sha256_file(target, max_bytes=268_435_456) != digest
            ):
                raise HostedRunnerError("BUNDLE_OUTPUT_CONFLICT", name)
            temporary.unlink()
        else:
            os.replace(temporary, target)
        verified = verify_bundle(target, expected_sha256=digest)
        if verified.manifest_sha256 != manifest_sha256:
            raise HostedRunnerError("BUNDLE_MANIFEST_MISMATCH", name)
        return BundleIdentity(target, name, digest, size, manifest_sha256)
    finally:
        temporary.unlink(missing_ok=True)


def verify_bundle(bundle_path: Path, *, expected_sha256: str) -> VerifiedBundle:
    """Reverify complete archive bytes, member safety, manifest, roles and payload hashes."""

    if _SHA256_RE.fullmatch(expected_sha256) is None:
        raise HostedRunnerError(
            "BUNDLE_DIGEST_MISMATCH", "expected digest is not exact"
        )
    path = Path(bundle_path)
    try:
        metadata = path.lstat()
    except OSError as error:
        raise HostedRunnerError("BUNDLE_UNAVAILABLE", path.name) from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise HostedRunnerError("BUNDLE_UNSAFE", path.name)
    if metadata.st_size > 268_435_456:
        raise HostedRunnerError("BUNDLE_TOO_LARGE", path.name)
    observed_sha256 = locks.sha256_file(path, max_bytes=268_435_456)
    if observed_sha256 != expected_sha256:
        raise HostedRunnerError("BUNDLE_DIGEST_MISMATCH", path.name)
    try:
        with path.open("rb") as source:
            if source.read(2) != b"\x1f\x8b":
                raise HostedRunnerError("BUNDLE_UNSAFE", "bundle is not gzip")
        with tarfile.open(path, mode="r:gz") as archive:
            members = archive.getmembers()
            _validate_bundle_members(members)
            manifest_member = next(
                member for member in members if member.name == "manifest.json"
            )
            if manifest_member.size > 1_048_576:
                raise HostedRunnerError(
                    "BUNDLE_MANIFEST_INVALID", "manifest is oversized"
                )
            extracted = archive.extractfile(manifest_member)
            if extracted is None:
                raise HostedRunnerError(
                    "BUNDLE_MANIFEST_INVALID", "manifest unavailable"
                )
            manifest_bytes = extracted.read(1_048_577)
            if len(manifest_bytes) > 1_048_576:
                raise HostedRunnerError(
                    "BUNDLE_MANIFEST_INVALID", "manifest is oversized"
                )
            try:
                manifest = json.loads(manifest_bytes)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise HostedRunnerError(
                    "BUNDLE_MANIFEST_INVALID", "manifest is not JSON"
                ) from error
            _validate_bundle_manifest(manifest)
            expected_rows = {row["path"]: row for row in manifest["files"]}
            actual_files = {
                member.name: member
                for member in members
                if member.isfile() and member.name != "manifest.json"
            }
            if set(expected_rows) != set(actual_files):
                raise HostedRunnerError(
                    "BUNDLE_MANIFEST_MISMATCH", "member census differs"
                )
            for relative, row in expected_rows.items():
                member = actual_files[relative]
                if (
                    member.size != row["size"]
                    or f"{member.mode & 0o777:04o}" != row["mode"]
                ):
                    raise HostedRunnerError("BUNDLE_MANIFEST_MISMATCH", relative)
                body_stream = archive.extractfile(member)
                if body_stream is None:
                    raise HostedRunnerError("BUNDLE_MANIFEST_MISMATCH", relative)
                digest = hashlib.sha256()
                remaining = member.size
                while remaining:
                    block = body_stream.read(min(1024 * 1024, remaining))
                    if not block:
                        raise HostedRunnerError("BUNDLE_TRUNCATED", relative)
                    digest.update(block)
                    remaining -= len(block)
                if body_stream.read(1) or digest.hexdigest() != row["sha256"]:
                    raise HostedRunnerError("BUNDLE_PAYLOAD_MISMATCH", relative)
    except HostedRunnerError:
        raise
    except (OSError, tarfile.TarError) as error:
        raise HostedRunnerError("BUNDLE_UNSAFE", "bundle cannot be parsed") from error
    return VerifiedBundle(
        path=path,
        sha256=observed_sha256,
        size=metadata.st_size,
        manifest=manifest,
        manifest_sha256=locks.sha256_bytes(manifest_bytes),
    )


def extract_verified_bundle(
    bundle: VerifiedBundle, destination: Path
) -> Mapping[str, Path]:
    """Extract a previously verified bundle without overwrite or link following."""

    root = Path(destination)
    if root.exists() or root.is_symlink():
        raise HostedRunnerError(
            "BUNDLE_DESTINATION_UNSAFE", "destination must be absent"
        )
    root.mkdir(parents=True, mode=0o700)
    paths: dict[str, Path] = {}
    with tarfile.open(bundle.path, mode="r:gz") as archive:
        for row in bundle.manifest["files"]:
            relative = row["path"]
            target = root.joinpath(*PurePosixPath(relative).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() or target.is_symlink():
                raise HostedRunnerError("BUNDLE_DESTINATION_UNSAFE", relative)
            member = archive.getmember(relative)
            source = archive.extractfile(member)
            if source is None:
                raise HostedRunnerError("BUNDLE_TRUNCATED", relative)
            descriptor = os.open(
                target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, int(row["mode"], 8)
            )
            try:
                with os.fdopen(descriptor, "wb", closefd=False) as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
            finally:
                os.close(descriptor)
            os.chmod(target, int(row["mode"], 8))
            paths[relative] = target
    return paths


def write_semantic_receipt(
    path: Path,
    *,
    request: ExperimentRequest,
    status: str,
    effect: str,
    evidence: Mapping[str, object],
) -> Mapping[str, Any]:
    """Atomically persist a self-digested, secret-free semantic receipt."""

    _validate_receipt_state(status, effect)
    unsigned: dict[str, object] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "mode": "Z0",
        "operation_key": request.operation_key,
        "request": request.payload,
        "request_digest": request.digest,
        "status": status,
        "effect": effect,
        "evidence": dict(evidence),
    }
    assert_secret_free(unsigned)
    payload = dict(unsigned)
    payload["semantic_digest"] = locks.sha256_bytes(
        locks.canonical_json_bytes(unsigned)
    )
    body = locks.canonical_json_bytes(payload) + b"\n"
    if len(body) > 1_048_576:
        raise HostedRunnerError("RECEIPT_TOO_LARGE", str(len(body)))
    _atomic_write_new_or_identical(Path(path), body, mode=0o600)
    return payload


def write_network_seal_boundary_receipt(
    request: ExperimentRequest,
    path: Path,
    *,
    effect_unknown: bool,
    host_userns_policy: HostUsernsPolicyEvidence | None = None,
) -> Mapping[str, Any]:
    """Record a namespace-boundary refusal or conservative unknown effect."""

    if not isinstance(effect_unknown, bool):
        raise HostedRunnerError("RECEIPT_INVALID", "boundary state is not boolean")
    launch_evidence: dict[str, object] = (
        {"consumer_launch_state": "UNKNOWN"}
        if effect_unknown
        else {"consumer_launched": False}
    )
    evidence: dict[str, object] = {
        "failure": {
            "code": (
                "NETWORK_SEAL_EFFECT_UNKNOWN"
                if effect_unknown
                else "NETWORK_SEAL_UNAVAILABLE"
            ),
            "detail": (
                "sealed child ended without a durable receipt"
                if effect_unknown
                else "user and network namespace probe failed"
            ),
        },
        **launch_evidence,
        "runner": _runner_confounds(),
    }
    if host_userns_policy is not None:
        evidence["host_userns_policy"] = _host_userns_policy_success_evidence(
            host_userns_policy
        )
    return write_semantic_receipt(
        path,
        request=request,
        status="RECONCILIATION_REQUIRED" if effect_unknown else "REFUSED",
        effect="EFFECT_UNKNOWN" if effect_unknown else "NOT_APPLIED",
        evidence=evidence,
    )


def write_phase_e_seal_refusal(
    request: ExperimentRequest, path: Path
) -> Mapping[str, Any]:
    """Record a proven pre-consumer source or Git-metadata seal refusal."""

    return write_semantic_receipt(
        path,
        request=request,
        status="REFUSED",
        effect="NOT_APPLIED",
        evidence={
            "failure": {
                "code": "CONSUMER_MOUNT_SEAL_UNAVAILABLE",
                "detail": "source or Git metadata read-only seal failed before launch",
            },
            "consumer_launched": False,
            "phase": "E",
            "runner": _runner_confounds(),
        },
    )


def load_semantic_receipt(path: Path) -> Mapping[str, Any]:
    """Read and validate a receipt before any replay decision."""

    candidate = Path(path)
    try:
        metadata = candidate.lstat()
    except OSError as error:
        raise HostedRunnerError("RECEIPT_UNAVAILABLE", candidate.name) from error
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size > 1_048_576
    ):
        raise HostedRunnerError("RECEIPT_UNSAFE", candidate.name)
    try:
        payload = json.loads(candidate.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HostedRunnerError("RECEIPT_INVALID", candidate.name) from error
    if not isinstance(payload, Mapping):
        raise HostedRunnerError("RECEIPT_INVALID", "receipt is not an object")
    expected_fields = {
        "schema_version",
        "mode",
        "operation_key",
        "request",
        "request_digest",
        "status",
        "effect",
        "evidence",
        "semantic_digest",
    }
    if set(payload) != expected_fields:
        raise HostedRunnerError("RECEIPT_INVALID", "receipt fields differ")
    if (
        payload.get("schema_version") != RECEIPT_SCHEMA_VERSION
        or payload.get("mode") != "Z0"
        or payload.get("operation_key") != Z0_OPERATION_KEY
    ):
        raise HostedRunnerError("RECEIPT_INVALID", "receipt identity differs")
    unsigned = {
        key: value for key, value in payload.items() if key != "semantic_digest"
    }
    observed_digest = locks.sha256_bytes(locks.canonical_json_bytes(unsigned))
    if payload.get("semantic_digest") != observed_digest:
        raise HostedRunnerError("RECEIPT_DIGEST_MISMATCH", candidate.name)
    _validate_receipt_state(payload.get("status"), payload.get("effect"))
    if not isinstance(payload.get("evidence"), Mapping):
        raise HostedRunnerError("RECEIPT_INVALID", "receipt evidence is not an object")
    request_payload = payload.get("request")
    if not isinstance(request_payload, Mapping):
        raise HostedRunnerError("RECEIPT_INVALID", "request is absent")
    try:
        reconstructed = ExperimentRequest.from_values(
            operation_key=str(request_payload["operation_key"]),
            consumer_sha=str(request_payload["consumer_sha"]),
            consumer_tree_sha=str(request_payload["consumer_tree_sha"]),
            forge_sha=str(request_payload["forge_sha"]),
            forge_tree_sha=str(request_payload["forge_tree_sha"]),
            lock_sha256=str(request_payload["lock_sha256"]),
            workflow_sha256=str(request_payload["workflow_sha256"]),
        )
    except (KeyError, HostedRunnerError) as error:
        raise HostedRunnerError(
            "RECEIPT_INVALID", "request cannot be reconstructed"
        ) from error
    if (
        request_payload != reconstructed.payload
        or payload.get("request_digest") != reconstructed.digest
    ):
        raise HostedRunnerError("RECEIPT_INVALID", "request identity is inconsistent")
    assert_secret_free(payload)
    return dict(payload)


def reconcile_receipt(path: Path, request: ExperimentRequest) -> ReplayResolution:
    """Return an identical completed result, conflict on drift, or hold unknown effects."""

    candidate = Path(path)
    if not candidate.exists() and not candidate.is_symlink():
        return ReplayResolution(ReplayDisposition.PROCEED)
    receipt = load_semantic_receipt(candidate)
    if receipt["operation_key"] != request.operation_key:
        raise HostedRunnerError("REQUEST_CONFLICT", "operation key is already occupied")
    if (
        receipt["request_digest"] != request.digest
        or receipt["request"] != request.payload
    ):
        raise HostedRunnerError("REQUEST_CONFLICT", "normalized request changed")
    if receipt["effect"] == "EFFECT_UNKNOWN":
        raise HostedRunnerError(
            "EFFECT_UNKNOWN_REPLAY_BLOCKED", "canonical effect must be reconciled first"
        )
    if (receipt["status"], receipt["effect"]) in {
        ("COMPLETED", "APPLIED"),
        ("REFUSED", "NOT_APPLIED"),
    }:
        return ReplayResolution(ReplayDisposition.RETURN_PRIOR, receipt)
    raise HostedRunnerError(
        "REPLAY_BLOCKED", "prior request is not terminally replayable"
    )


def workflow_run_name(request: ExperimentRequest) -> str:
    """Return the exact run-name contract also embedded in the workflow."""

    return (
        f"codeintel-z0|op={request.operation_key}|consumer={request.consumer_sha}|"
        f"tree={request.consumer_tree_sha}|forge={request.forge_sha}"
    )


def operation_artifact_name() -> str:
    digest = hashlib.sha256(Z0_OPERATION_KEY.encode("ascii")).hexdigest()
    return f"codeintel-z0-operation-{digest}"


def reconcile_prior_runs(
    request: ExperimentRequest,
    *,
    current_run_id: int,
    destination: Path,
    github_output: Path | None = None,
) -> ReplayResolution:
    """Reconcile prior runs through the same deny-by-default Phase-P proxy."""

    with tempfile.TemporaryDirectory(prefix="codeintel-replay-network-") as temporary:
        with _phase_p_allowlist_proxy(Path(temporary) / "home") as network_environment:
            return _reconcile_prior_runs_allowlisted(
                request,
                current_run_id=current_run_id,
                destination=destination,
                github_output=github_output,
                network_environment=network_environment,
            )


def _reconcile_prior_runs_allowlisted(
    request: ExperimentRequest,
    *,
    current_run_id: int,
    destination: Path,
    github_output: Path | None,
    network_environment: Mapping[str, str],
) -> ReplayResolution:
    """Perform the bounded GitHub census with effective-host enforcement."""

    if current_run_id <= 0:
        raise HostedRunnerError("REPLAY_LOOKUP_INVALID", "current run id is invalid")
    expected_title = workflow_run_name(request)
    operation_prefix = f"codeintel-z0|op={request.operation_key}|"
    raw_runs = _gh_paginated_rows(
        "repos/mastermindx-market-intelligence/Mastermind/actions/workflows/"
        "codeintel-experiment-bundle.yml/runs?event=workflow_dispatch",
        field="workflow_runs",
        max_rows=10_000,
        network_environment=network_environment,
    )
    matching_runs: list[Mapping[str, Any]] = []
    for raw_run in raw_runs:
        if not isinstance(raw_run, Mapping):
            raise HostedRunnerError(
                "REPLAY_LOOKUP_INVALID", "workflow run row malformed"
            )
        run_id = raw_run.get("id")
        if run_id == current_run_id:
            continue
        title = raw_run.get("display_title")
        if not isinstance(title, str) or not title.startswith(operation_prefix):
            continue
        if title != expected_title:
            raise HostedRunnerError(
                "REQUEST_CONFLICT",
                "the fixed operation already has changed normalized input",
            )
        matching_runs.append(raw_run)
    if not matching_runs:
        resolution = ReplayResolution(ReplayDisposition.PROCEED)
        if github_output is not None:
            _append_github_outputs(
                github_output, {"disposition": resolution.disposition.value}
            )
        return resolution

    receipts: list[tuple[bytes, Mapping[str, Any]]] = []
    for raw_run in matching_runs:
        run_id = raw_run.get("id")
        if not isinstance(run_id, int) or run_id <= 0:
            raise HostedRunnerError("REPLAY_LOOKUP_INVALID", "prior run id malformed")
        status = raw_run.get("status")
        if status != "completed":
            raise HostedRunnerError(
                "EFFECT_UNKNOWN_REPLAY_BLOCKED", f"prior run {run_id} is {status}"
            )
        artifacts = _gh_paginated_rows(
            f"repos/{FIXED_REPOSITORY}/actions/runs/{run_id}/artifacts",
            field="artifacts",
            max_rows=1_000,
            network_environment=network_environment,
        )
        candidates = [
            artifact
            for artifact in artifacts
            if isinstance(artifact, Mapping)
            and artifact.get("name") == operation_artifact_name()
            and artifact.get("expired") is False
        ]
        if len(candidates) != 1:
            raise HostedRunnerError(
                "EFFECT_UNKNOWN_REPLAY_BLOCKED",
                f"prior run {run_id} has no unique durable semantic receipt",
            )
        artifact_size = candidates[0].get("size_in_bytes")
        if (
            isinstance(artifact_size, bool)
            or not isinstance(artifact_size, int)
            or not 0 < artifact_size <= 4_194_304
        ):
            raise HostedRunnerError(
                "REPLAY_LOOKUP_INVALID", "receipt artifact size is unsafe"
            )
        artifact_id = candidates[0].get("id")
        if not isinstance(artifact_id, int) or artifact_id <= 0:
            raise HostedRunnerError("REPLAY_LOOKUP_INVALID", "artifact id malformed")
        with tempfile.TemporaryDirectory(prefix="codeintel-prior-") as temporary:
            zip_path = Path(temporary) / "receipt.zip"
            _gh_download_artifact(
                artifact_id,
                zip_path,
                network_environment=network_environment,
            )
            receipt_bytes = _read_receipt_from_artifact_zip(zip_path)
            receipt_path = Path(temporary) / "semantic-receipt.json"
            receipt_path.write_bytes(receipt_bytes)
            receipt = load_semantic_receipt(receipt_path)
            resolution = reconcile_receipt(receipt_path, request)
            if resolution.disposition is not ReplayDisposition.RETURN_PRIOR:
                raise HostedRunnerError(
                    "REPLAY_LOOKUP_INVALID", "prior artifact is not terminal"
                )
            receipts.append((receipt_bytes, receipt))
    first_bytes, first_receipt = receipts[0]
    if any(body != first_bytes for body, _receipt in receipts[1:]):
        raise HostedRunnerError(
            "EFFECT_UNKNOWN_REPLAY_BLOCKED", "prior semantic receipts disagree"
        )
    output = Path(destination)
    _atomic_write_new_or_identical(output, first_bytes, mode=0o600)
    if github_output is not None:
        if first_receipt["status"] == "REFUSED":
            returncode = 1
        else:
            observed_returncode = (
                first_receipt.get("evidence", {}).get("launch", {}).get("returncode", 0)
            )
            if isinstance(observed_returncode, bool) or not isinstance(
                observed_returncode, int
            ):
                raise HostedRunnerError("RECEIPT_INVALID", "return code is malformed")
            returncode = 0 if observed_returncode == 0 else 1
        _append_github_outputs(
            github_output,
            {
                "disposition": ReplayDisposition.RETURN_PRIOR.value,
                "prior_returncode": str(returncode),
            },
        )
    return ReplayResolution(ReplayDisposition.RETURN_PRIOR, first_receipt)


def _gh_download_artifact(
    artifact_id: int,
    destination: Path,
    *,
    network_environment: Mapping[str, str],
) -> None:
    try:
        with destination.open("xb") as output:
            completed = _run_phase_p_process(
                [
                    "/usr/bin/gh",
                    "api",
                    "-H",
                    "Accept: application/vnd.github+json",
                    f"repos/{FIXED_REPOSITORY}/actions/artifacts/{artifact_id}/zip",
                ],
                cwd=Path.cwd(),
                env=_github_client_environment(network_environment),
                network_environment=network_environment,
                timeout=60,
                stdout=output,
                text=False,
            )
    except OSError as error:
        raise HostedRunnerError(
            "REPLAY_LOOKUP_INVALID", "artifact download failed"
        ) from error
    if completed.returncode != 0:
        detail = _bounded_redacted(
            completed.stderr.decode("utf-8", errors="replace"), 1024
        )
        raise HostedRunnerError(
            "REPLAY_LOOKUP_INVALID", f"artifact download rejected: {detail}"
        )
    if destination.stat().st_size > 4_194_304:
        raise HostedRunnerError(
            "REPLAY_LOOKUP_INVALID", "receipt artifact is oversized"
        )


def _read_receipt_from_artifact_zip(path: Path) -> bytes:
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) != 1:
                raise HostedRunnerError(
                    "REPLAY_LOOKUP_INVALID", "receipt artifact member census differs"
                )
            info = infos[0]
            mode = (info.external_attr >> 16) & 0o170000
            if (
                info.filename != "semantic-receipt.json"
                or info.is_dir()
                or mode == stat.S_IFLNK
                or info.file_size > 1_048_576
            ):
                raise HostedRunnerError(
                    "REPLAY_LOOKUP_INVALID", "receipt artifact member is unsafe"
                )
            body = archive.read(info)
    except HostedRunnerError:
        raise
    except (OSError, zipfile.BadZipFile, KeyError) as error:
        raise HostedRunnerError(
            "REPLAY_LOOKUP_INVALID", "receipt artifact is invalid"
        ) from error
    if len(body) > 1_048_576:
        raise HostedRunnerError("REPLAY_LOOKUP_INVALID", "receipt is oversized")
    return body


def sanitized_consumer_environment(scratch_root: Path) -> dict[str, str]:
    """Construct the complete credential-free environment inherited by candidate processes."""

    root = Path(scratch_root)
    if root.exists() or root.is_symlink():
        root = _real_directory(root, "SCRATCH_UNSAFE")
    else:
        root.mkdir(parents=True, mode=0o700)
    home = root / "home"
    temporary = root / "tmp"
    home.mkdir(mode=0o700, exist_ok=True)
    temporary.mkdir(mode=0o700, exist_ok=True)
    return {
        "HOME": os.fspath(home.resolve()),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/bin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "TMPDIR": os.fspath(temporary.resolve()),
        "TZ": "UTC",
    }


def assert_secret_free(value: object) -> None:
    """Reject credential-like fields/values and private absolute workspace paths."""

    def visit(item: object, *, key: str | None = None) -> None:
        if key is not None and key != "secret_free" and _FORBIDDEN_KEY_RE.search(key):
            raise HostedRunnerError("SECRET_BEARING_OUTPUT", f"forbidden field {key}")
        if isinstance(item, Mapping):
            for child_key, child in item.items():
                if not isinstance(child_key, str):
                    raise HostedRunnerError(
                        "SECRET_BEARING_OUTPUT", "non-text metadata key"
                    )
                visit(child, key=child_key)
        elif isinstance(item, Sequence) and not isinstance(
            item, (str, bytes, bytearray)
        ):
            for child in item:
                visit(child)
        elif isinstance(item, str):
            if any(pattern.search(item) for pattern in _SECRET_TEXT_PATTERNS):
                raise HostedRunnerError("SECRET_BEARING_OUTPUT", "credential-like text")
            if any(pattern.search(item) for pattern in _PRIVATE_PATH_PATTERNS):
                raise HostedRunnerError(
                    "SECRET_BEARING_OUTPUT", "private absolute path"
                )
        elif isinstance(item, bytes):
            text = item.decode("utf-8", errors="ignore")
            if any(pattern.search(text) for pattern in _SECRET_TEXT_PATTERNS):
                raise HostedRunnerError(
                    "SECRET_BEARING_OUTPUT", "credential-like bytes"
                )
            if any(pattern.search(text) for pattern in _PRIVATE_PATH_PATTERNS):
                raise HostedRunnerError(
                    "SECRET_BEARING_OUTPUT", "private absolute path"
                )

    visit(value)


def fixed_consumer_argv(
    *,
    python_executable: Path,
    consumer_root: Path,
    manifest: Path,
    path_policy: Path,
    indexer: Path,
    indexer_sha256: str,
    webserver: Path,
    webserver_sha256: str,
    shard_root: Path,
    log_root: Path,
    result: Path,
    report: Path,
) -> list[str]:
    """Return the one repository-owned consumer module and complete fixed argv."""

    for label, digest in (
        ("indexer", indexer_sha256),
        ("webserver", webserver_sha256),
    ):
        if _SHA256_RE.fullmatch(digest) is None:
            raise HostedRunnerError("INVALID_REQUEST", f"{label} digest is not exact")
    values = [
        python_executable,
        consumer_root,
        manifest,
        path_policy,
        indexer,
        webserver,
        shard_root,
        log_root,
        result,
        report,
    ]
    if any(not Path(value).is_absolute() for value in values):
        raise HostedRunnerError(
            "INVALID_REQUEST", "consumer paths must be host-owned absolutes"
        )
    return [
        os.fspath(python_executable),
        "-I",
        "-c",
        _CONSUMER_BOOTSTRAP,
        os.fspath(consumer_root),
        "--manifest",
        os.fspath(manifest),
        "--path-policy",
        os.fspath(path_policy),
        "--indexer",
        os.fspath(indexer),
        "--indexer-sha256",
        indexer_sha256,
        "--webserver",
        os.fspath(webserver),
        "--webserver-sha256",
        webserver_sha256,
        "--shard-root",
        os.fspath(shard_root),
        "--log-root",
        os.fspath(log_root),
        "--result",
        os.fspath(result),
        "--report",
        os.fspath(report),
        "--startup-timeout-seconds",
        "10",
    ]


def observe_network_seal() -> NetworkSealProof:
    """Prove the caller is in a loopback-only namespace and outbound connect is denied."""

    try:
        interfaces = tuple(sorted(name for _index, name in socket.if_nameindex()))
    except OSError as error:
        raise HostedRunnerError(
            "NETWORK_SEAL_UNAVAILABLE", "interface census failed"
        ) from error
    routes: list[str] = []
    route_file = Path("/proc/net/route")
    try:
        rows = route_file.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise HostedRunnerError(
            "NETWORK_SEAL_UNAVAILABLE", "Linux route table unavailable"
        ) from error
    for row in rows[1:]:
        fields = row.split()
        if fields and fields[0] != "lo":
            routes.append(row)
    denial: int | None = None
    probe_state = "CONNECTED"
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.settimeout(1.0)
    try:
        probe.connect(("1.1.1.1", 443))
    except OSError as error:
        denial = error.errno
        if denial in {
            errno.ENETUNREACH,
            errno.EHOSTUNREACH,
            errno.ENETDOWN,
            errno.EACCES,
        }:
            probe_state = "DENIED"
        else:
            probe_state = f"INCONCLUSIVE_ERRNO_{denial}"
    finally:
        probe.close()
    return NetworkSealProof(interfaces, tuple(routes), probe_state, denial)


def prove_then_launch(
    *,
    probe: Callable[[], NetworkSealProof],
    launch: Callable[[], LaunchEvidence],
) -> tuple[NetworkSealProof, LaunchEvidence]:
    """Enforce the causality edge: successful denial proof strictly precedes launch."""

    proof = probe()
    if (
        proof.interfaces != ("lo",)
        or proof.non_loopback_routes
        or proof.outbound_probe != "DENIED"
        or proof.denial_errno
        not in {errno.ENETUNREACH, errno.EHOSTUNREACH, errno.ENETDOWN, errno.EACCES}
    ):
        raise HostedRunnerError(
            "NETWORK_SEAL_UNAVAILABLE", "loopback-only outbound denial was not proven"
        )
    return proof, launch()


def validate_cleanup(evidence: CleanupEvidence) -> bool:
    if not evidence.process_group_dead or evidence.unexpected_residue:
        raise HostedRunnerError(
            "CLEANUP_LEAK", "candidate process or scratch residue remains"
        )
    return True


def load_request(path: Path) -> ExperimentRequest:
    """Load a canonical request file and rederive every normalized field."""

    candidate = Path(path)
    try:
        metadata = candidate.lstat()
        raw = candidate.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HostedRunnerError(
            "INVALID_REQUEST", "request file is unavailable"
        ) from error
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size > 65_536
        or not isinstance(value, Mapping)
    ):
        raise HostedRunnerError("INVALID_REQUEST", "request file is unsafe")
    expected_fields = {
        "consumer_sha",
        "consumer_tree_sha",
        "forge_sha",
        "forge_tree_sha",
        "lock_sha256",
        "mode",
        "operation_key",
        "repository",
        "workflow_sha256",
    }
    if set(value) != expected_fields:
        raise HostedRunnerError("INVALID_REQUEST", "request fields differ")
    request = ExperimentRequest.from_values(
        operation_key=str(value["operation_key"]),
        consumer_sha=str(value["consumer_sha"]),
        consumer_tree_sha=str(value["consumer_tree_sha"]),
        forge_sha=str(value["forge_sha"]),
        forge_tree_sha=str(value["forge_tree_sha"]),
        lock_sha256=str(value["lock_sha256"]),
        workflow_sha256=str(value["workflow_sha256"]),
    )
    if value != request.payload or raw != request.canonical_bytes + b"\n":
        raise HostedRunnerError("INVALID_REQUEST", "request is not canonical")
    return request


def derive_request(
    forge_root: Path,
    *,
    operation_key: str,
    consumer_sha: str,
    consumer_tree_sha: str,
) -> ExperimentRequest:
    """Derive forge, lock, and workflow identity rather than trusting the caller."""

    root = _real_directory(forge_root, "FORGE_SOURCE_MISMATCH")
    if git_stdout(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise HostedRunnerError("FORGE_SOURCE_DIRTY", "forge checkout is not clean")
    forge_sha = git_stdout(root, "rev-parse", "--verify", "HEAD")
    forge_tree = git_stdout(root, "rev-parse", "--verify", "HEAD^{tree}")
    lock_path = (
        root
        / "research/code_intelligence_fabric/codeintel-experiment-toolchain-lock.v1.json"
    )
    schema_path = (
        root
        / "research/code_intelligence_fabric/codeintel-experiment-toolchain-lock.schema.json"
    )
    lock = locks.load_toolchain_lock(lock_path, schema_path=schema_path)
    workflow_path = root / FIXED_WORKFLOW_PATH
    _validate_workflow_action_pins(workflow_path, lock)
    workflow_sha256 = locks.sha256_file(workflow_path, max_bytes=1_048_576)
    return ExperimentRequest.from_values(
        operation_key=operation_key,
        consumer_sha=consumer_sha,
        consumer_tree_sha=consumer_tree_sha,
        forge_sha=forge_sha,
        forge_tree_sha=forge_tree,
        lock_sha256=lock.sha256,
        workflow_sha256=workflow_sha256,
    )


def prepare_phase_p(
    forge_root: Path,
    request: ExperimentRequest,
    *,
    scratch_root: Path,
    output_directory: Path,
    github_output: Path | None = None,
) -> Mapping[str, Any]:
    """Acquire, verify, repeat-build, inventory, and bundle the exact Z0 toolchain."""

    root = _real_directory(forge_root, "FORGE_SOURCE_MISMATCH")
    derived = derive_request(
        root,
        operation_key=request.operation_key,
        consumer_sha=request.consumer_sha,
        consumer_tree_sha=request.consumer_tree_sha,
    )
    if derived != request:
        raise HostedRunnerError("REQUEST_CONFLICT", "forge request identity moved")
    lock_path = (
        root
        / "research/code_intelligence_fabric/codeintel-experiment-toolchain-lock.v1.json"
    )
    schema_path = (
        root
        / "research/code_intelligence_fabric/codeintel-experiment-toolchain-lock.schema.json"
    )
    lock = locks.load_toolchain_lock(lock_path, schema_path=schema_path)
    scratch = _fresh_directory(scratch_root, "SCRATCH_CONFLICT")
    output = _ensure_output_directory(output_directory)
    downloads = scratch / "downloads"
    extracted = scratch / "extracted"
    source = scratch / "zoekt-source"
    builds = scratch / "builds"
    payload = scratch / "payload"
    for directory in (downloads, extracted, builds, payload / "bin", payload / "meta"):
        directory.mkdir(parents=True, mode=0o700)

    with _phase_p_allowlist_proxy(scratch / "network-home") as network_environment:
        go_archive = downloads / locks.GO_ARCHIVE_FILENAME
        effective_url = _download_exact_go_archive(
            go_archive, network_environment=network_environment
        )
        limits = lock.payload["limits"]
        locks.safe_extract_tar(
            go_archive,
            extracted,
            expected_sha256=locks.GO_ARCHIVE_SHA256,
            expected_size=locks.GO_ARCHIVE_SIZE,
            expected_top_level="go",
            max_archive_bytes=int(limits["archive_bytes"]),
            max_member_bytes=int(limits["archive_member_bytes"]),
            max_total_bytes=int(limits["archive_total_bytes"]),
        )
        go_root = extracted / "go"
        go_binary = go_root / "bin/go"
        _verify_go_distribution(
            go_root,
            go_binary,
            network_environment=network_environment,
        )
        go_source_metadata = _verify_go_source_metadata(
            network_environment=network_environment
        )

        _checkout_exact_zoekt(source, network_environment=network_environment)
        source_before = locks.verify_zoekt_source(source, lock)
        build = _repeat_build_zoekt(
            source,
            go_binary=go_binary,
            scratch=builds,
            payload_bin=payload / "bin",
            network_environment=network_environment,
        )
        source_after = locks.verify_zoekt_source(source, lock)
        if source_before != source_after:
            raise HostedRunnerError(
                "SOURCE_DRIFT", "Zoekt identity changed during build"
            )

    module_inventory = build["modules"]
    main_module = next(
        str(row["path"]) for row in module_inventory if bool(row["main"])
    )
    sbom = {
        "schema_version": "mastermind.codeintel_go_module_inventory.v1",
        "main_module": main_module,
        "go_version": locks.GO_VERSION,
        "go_mod_blob_sha1": locks.ZOEKT_GO_MOD_BLOB,
        "go_sum_blob_sha1": locks.ZOEKT_GO_SUM_BLOB,
        "modules": module_inventory,
    }
    assert_secret_free(sbom)
    sbom_bytes = locks.canonical_json_bytes(sbom) + b"\n"
    (payload / "meta/sbom.json").write_bytes(sbom_bytes)

    notice = (
        "Mastermind CodeIntel Z0 disposable experiment bundle\n"
        f"Zoekt {locks.ZOEKT_COMMIT} — Apache-2.0; exact LICENSE follows.\n"
        f"Go {locks.GO_VERSION} ({locks.GO_SOURCE_COMMIT}) — BSD-3-Clause; exact "
        "LICENSE follows.\n"
        "Universal Ctags: DISABLED; no Ctags bytes are present.\n\n"
        "===== ZOEKT LICENSE =====\n"
    ).encode("utf-8")
    notice += (source / "LICENSE").read_bytes()
    notice += b"\n===== GO LICENSE =====\n"
    notice += (go_root / "LICENSE").read_bytes()
    (payload / "meta/NOTICE.txt").write_bytes(notice)
    shutil.copyfile(lock_path, payload / "meta/toolchain-lock.json")

    provenance = {
        "schema_version": PHASE_P_PROVENANCE_SCHEMA_VERSION,
        "request_digest": request.digest,
        "lock_sha256": lock.sha256,
        "build_recipe_sha256": lock.build_recipe_sha256,
        "phase": "P",
        "network": {
            "state": "SUBPROCESS_EGRESS_FRESH_NETNS_PROXY_ALLOWLISTED",
            "enforcement": lock.payload["acquisition"]["network_enforcement"],
            "network_namespace": lock.payload["acquisition"]["network_namespace"],
            "gate_mount": lock.payload["acquisition"]["gate_mount"],
            "relay_endpoint": lock.payload["acquisition"]["relay_endpoint"],
            "parent_gate_transport": lock.payload["acquisition"][
                "parent_gate_transport"
            ],
            "client_socket_policy": lock.payload["acquisition"]["client_socket_policy"],
            "minimum_landlock_abi": _PHASE_P_LANDLOCK_MIN_ABI,
            "boundary_receipt": _PHASE_P_BOUNDARY_READY.decode("ascii").strip(),
            "host_userns_policy": lock.payload["acquisition"]["host_userns_policy"],
            "landlock_role": "DEFENSE_IN_DEPTH_PORT_FILTER",
            "direct_tcp_connect_policy": (
                "ONLY_FIXED_RELAY_LISTENER_EXISTS_IN_FRESH_NAMESPACE"
            ),
            "parent_gate_descriptor_inherited_by_client": False,
            "process_group_cleanup": "SIGKILL_AFTER_EXIT_OR_TIMEOUT",
            "allowed_hosts": list(locks.ALLOWED_HOSTS),
            "allowed_host_suffixes": list(locks.ALLOWED_HOST_SUFFIXES),
            "ambient_network_configuration_inherited": False,
            "go_archive_effective_host": urlparse(effective_url).hostname,
        },
        "runner": _runner_confounds(),
        "actions": lock.payload["actions"],
        "host_utility_confounds": list(locks.HOST_UTILITY_CONFOUNDS),
        "go": {
            "version": locks.GO_VERSION,
            "archive_filename": locks.GO_ARCHIVE_FILENAME,
            "archive_sha256": locks.GO_ARCHIVE_SHA256,
            "archive_size": locks.GO_ARCHIVE_SIZE,
            "source": go_source_metadata,
            "license_blob_sha1": locks.GO_LICENSE_BLOB,
            "license_sha256": locks.GO_LICENSE_SHA256,
        },
        "zoekt": {
            **dataclasses.asdict(source_before),
            "go_mod_sha256": locks.ZOEKT_GO_MOD_SHA256,
            "go_sum_sha256": locks.ZOEKT_GO_SUM_SHA256,
            "license_sha256": locks.ZOEKT_LICENSE_SHA256,
        },
        "module_inventory_sha256": locks.sha256_bytes(sbom_bytes),
        "binaries": build["binaries"],
        "source_before": dataclasses.asdict(source_before),
        "source_after": dataclasses.asdict(source_after),
        "universal_ctags": {
            "enabled": False,
            "observation": "NO_CTAGS_BYTES_BUNDLED_OR_RESOLVED",
        },
    }
    assert_secret_free(provenance)
    provenance_bytes = locks.canonical_json_bytes(provenance) + b"\n"
    (payload / "meta/provenance.json").write_bytes(provenance_bytes)

    bundle = create_content_addressed_bundle(
        payload,
        output,
        context={
            "request_digest": request.digest,
            "lock_sha256": lock.sha256,
            "build_recipe_sha256": lock.build_recipe_sha256,
            "module_inventory_sha256": locks.sha256_bytes(sbom_bytes),
            "provenance_sha256": locks.sha256_bytes(provenance_bytes),
        },
    )
    result = {
        "schema_version": "mastermind.codeintel_phase_p_result.v1",
        "request_digest": request.digest,
        "bundle_name": bundle.name,
        "bundle_sha256": bundle.sha256,
        "bundle_size": bundle.size,
        "manifest_sha256": bundle.manifest_sha256,
        "lock_sha256": lock.sha256,
        "build_recipe_sha256": lock.build_recipe_sha256,
        "module_inventory_sha256": locks.sha256_bytes(sbom_bytes),
        "provenance_sha256": locks.sha256_bytes(provenance_bytes),
        "binary_digests": {
            name: row["sha256"] for name, row in build["binaries"].items()
        },
    }
    assert_secret_free(result)
    result_path = output / "phase-p-result.json"
    _atomic_write_new_or_identical(
        result_path, locks.canonical_json_bytes(result) + b"\n", mode=0o600
    )
    if github_output is not None:
        _append_github_outputs(
            github_output,
            {
                "bundle_name": bundle.name,
                "bundle_sha256": bundle.sha256,
                "manifest_sha256": bundle.manifest_sha256,
            },
        )
    return result


def prepare_phase_p_or_record_refusal(
    forge_root: Path,
    request: ExperimentRequest,
    *,
    scratch_root: Path,
    output_directory: Path,
    github_output: Path,
    receipt_path: Path,
) -> Mapping[str, Any]:
    """Run Phase P or durably preserve its known pre-consumer refusal."""

    try:
        return prepare_phase_p(
            forge_root,
            request,
            scratch_root=scratch_root,
            output_directory=output_directory,
            github_output=github_output,
        )
    except (HostedRunnerError, locks.ToolchainLockError) as error:
        _write_phase_p_refusal(
            request,
            receipt_path,
            code=getattr(error, "code", "PHASE_P_FAILED"),
            detail=_bounded_redacted(getattr(error, "detail", str(error)), 512),
        )
        raise
    except OSError as cause:
        error = HostedRunnerError(
            "PHASE_P_IO_FAILED", "Phase P filesystem operation failed"
        )
        _write_phase_p_refusal(
            request,
            receipt_path,
            code=error.code,
            detail=error.detail,
        )
        raise error from cause


def _write_phase_p_refusal(
    request: ExperimentRequest,
    receipt_path: Path,
    *,
    code: str,
    detail: str,
    host_userns_policy: HostUsernsPolicyEvidence | None = None,
) -> None:
    evidence: dict[str, object] = {
        "failure": {"code": code, "detail": detail},
        "phase": "P",
        "consumer_launched": False,
        "runner": _runner_confounds(),
    }
    if host_userns_policy is not None:
        evidence["host_userns_policy"] = _host_userns_policy_success_evidence(
            host_userns_policy
        )
    write_semantic_receipt(
        receipt_path,
        request=request,
        status="REFUSED",
        effect="NOT_APPLIED",
        evidence=evidence,
    )


def run_phase_e(
    forge_root: Path,
    consumer_root: Path,
    request: ExperimentRequest,
    *,
    bundle_path: Path,
    bundle_sha256: str,
    scratch_root: Path,
    result_directory: Path,
    receipt_path: Path,
) -> Mapping[str, Any]:
    """Reverify exact inputs, prove the seal, and invoke only the fixed Z0 module."""

    forge = _real_directory(forge_root, "FORGE_SOURCE_MISMATCH")
    derived = derive_request(
        forge,
        operation_key=request.operation_key,
        consumer_sha=request.consumer_sha,
        consumer_tree_sha=request.consumer_tree_sha,
    )
    if derived != request:
        raise HostedRunnerError("REQUEST_CONFLICT", "forge request identity moved")
    lock_path = (
        forge
        / "research/code_intelligence_fabric/codeintel-experiment-toolchain-lock.v1.json"
    )
    schema_path = (
        forge
        / "research/code_intelligence_fabric/codeintel-experiment-toolchain-lock.schema.json"
    )
    lock = locks.load_toolchain_lock(lock_path, schema_path=schema_path)
    if lock.sha256 != request.lock_sha256:
        raise HostedRunnerError("REQUEST_CONFLICT", "lock bytes moved")
    expected_name = f"codeintel-z0-{bundle_sha256}.tar.gz"
    if Path(bundle_path).name != expected_name:
        raise HostedRunnerError(
            "BUNDLE_SUBSTITUTION", "bundle name does not bind complete bytes"
        )
    verified_before = verify_bundle(bundle_path, expected_sha256=bundle_sha256)

    consumer = verify_consumer_checkout(
        consumer_root, request.consumer_sha, request.consumer_tree_sha
    )
    git_metadata_seal = _verify_consumer_git_seal(consumer_root)
    merge_base, changed_paths = consumer_effective_paths(
        consumer_root,
        consumer_sha=request.consumer_sha,
        forge_sha=request.forge_sha,
    )
    consumer_policy = lock.payload["consumer"]
    includes = tuple(consumer_policy["index_includes"])
    excludes = tuple(consumer_policy["index_excludes"])
    source_before = selected_source_digest(
        consumer_root, includes=includes, excludes=excludes
    )
    scratch = _fresh_directory(scratch_root, "SCRATCH_CONFLICT")
    outputs = _ensure_output_directory(result_directory)
    extracted = extract_verified_bundle(verified_before, scratch / "bundle")
    indexer = _verified_executable(
        extracted["bin/zoekt-git-index"],
        expected_sha256=_manifest_file_digest(
            verified_before.manifest, "bin/zoekt-git-index"
        ),
    )
    webserver = _verified_executable(
        extracted["bin/zoekt-webserver"],
        expected_sha256=_manifest_file_digest(
            verified_before.manifest, "bin/zoekt-webserver"
        ),
    )
    binary_before = {
        "zoekt-git-index": locks.sha256_file(indexer, max_bytes=100_663_296),
        "zoekt-webserver": locks.sha256_file(webserver, max_bytes=100_663_296),
    }

    input_root = scratch / "input"
    input_root.mkdir(mode=0o700)
    path_policy = (Path(consumer_root) / str(consumer_policy["path_policy"])).resolve()
    _require_within_root(path_policy, Path(consumer_root))
    _regular_file(path_policy, "CONSUMER_PATH_POLICY_UNSAFE", max_bytes=1_048_576)
    manifest = input_root / "manifest.json"
    manifest_payload = {
        "schema_version": "mastermind.codeintel_index_manifest.v1",
        "repositories": [
            {
                "repository_id": "mastermind",
                "repository_name": FIXED_REPOSITORY,
                "source_snapshot_root": os.fspath(Path(consumer_root).resolve()),
                "ref_label": FIXED_CONSUMER_BRANCH,
                "commit_sha": request.consumer_sha,
                "included_prefixes": list(includes),
                "excluded_globs": list(excludes),
                "source_tree_digest": source_before,
            }
        ],
    }
    manifest.write_bytes(locks.canonical_json_bytes(manifest_payload) + b"\n")
    os.chmod(manifest, 0o600)

    shard_root = scratch / "shards"
    log_root = scratch / "logs"
    environment_root = scratch / "consumer-environment"
    result_path = outputs / "z0-result.json"
    report_path = outputs / "z0-report.md"
    argv = fixed_consumer_argv(
        python_executable=Path(sys.executable).resolve(),
        consumer_root=Path(consumer_root).resolve(),
        manifest=manifest.resolve(),
        path_policy=path_policy,
        indexer=indexer,
        indexer_sha256=binary_before["zoekt-git-index"],
        webserver=webserver,
        webserver_sha256=binary_before["zoekt-webserver"],
        shard_root=shard_root.resolve(),
        log_root=log_root.resolve(),
        result=result_path.resolve(),
        report=report_path.resolve(),
    )
    environment = sanitized_consumer_environment(environment_root)
    proof: NetworkSealProof | None = None
    launch: LaunchEvidence | None = None
    launched = False
    try:

        def launch_fixed() -> LaunchEvidence:
            nonlocal launched
            launched = True
            return _launch_fixed_consumer(
                argv,
                cwd=Path(consumer_root).resolve(),
                env=environment,
                timeout_seconds=int(lock.payload["limits"]["consumer_seconds"]),
                log_limit=int(lock.payload["limits"]["log_bytes_each"]),
            )

        proof, launch = prove_then_launch(
            probe=observe_network_seal,
            launch=launch_fixed,
        )
        source_after = selected_source_digest(
            consumer_root, includes=includes, excludes=excludes
        )
        binary_after = {
            "zoekt-git-index": locks.sha256_file(indexer, max_bytes=100_663_296),
            "zoekt-webserver": locks.sha256_file(webserver, max_bytes=100_663_296),
        }
        verified_after = verify_bundle(bundle_path, expected_sha256=bundle_sha256)
        if (
            source_after != source_before
            or binary_after != binary_before
            or verified_after.manifest_sha256 != verified_before.manifest_sha256
        ):
            raise HostedRunnerError(
                "POST_LAUNCH_IDENTITY_DRIFT", "source, binary, or bundle bytes moved"
            )
        cleanup = _cleanup_candidate_scratch(
            process_group=launch.process_group,
            shard_root=shard_root,
            log_root=log_root,
        )
        validate_cleanup(cleanup)
        if launch.returncode == 0:
            artifacts = _validate_success_artifacts(
                output=outputs,
                request=request,
                manifest_payload=manifest_payload,
                path_policy=path_policy,
                source_digest=source_before,
                binary_digests=binary_before,
                expected_tool_schema_digest=str(
                    consumer_policy["tool_schema_digest"]
                ),
            )
        else:
            artifacts = _result_artifact_census(outputs)
        evidence = {
            "forge": {
                "commit_sha": request.forge_sha,
                "tree_sha": request.forge_tree_sha,
                "workflow_sha256": request.workflow_sha256,
                "lock_sha256": request.lock_sha256,
            },
            "consumer": {
                **dataclasses.asdict(consumer),
                "merge_base": merge_base,
                "changed_paths": list(changed_paths),
                "source_digest_before": source_before,
                "source_digest_after": source_after,
            },
            "bundle": {
                "name": expected_name,
                "sha256_before": verified_before.sha256,
                "sha256_after": verified_after.sha256,
                "manifest_sha256_before": verified_before.manifest_sha256,
                "manifest_sha256_after": verified_after.manifest_sha256,
                "binary_digests_before": binary_before,
                "binary_digests_after": binary_after,
            },
            "network_seal": dataclasses.asdict(proof),
            "git_metadata_seal": git_metadata_seal,
            "consumer_invocation": {
                "role": "Z0_DISPOSABLE_FALSIFIER",
                "module": FIXED_CONSUMER_MODULE,
                "argv_contract": [
                    "python3",
                    "-I",
                    "-c",
                    "FIXED_BOOTSTRAP",
                    "CONSUMER_ROOT",
                    "--manifest",
                    "HOST_MANIFEST",
                    "--path-policy",
                    "FIXED_Z0_PATH_POLICY",
                    "--indexer",
                    "BUNDLE_ZOEKT_GIT_INDEX",
                    "--indexer-sha256",
                    "PINNED_SHA256",
                    "--webserver",
                    "BUNDLE_ZOEKT_WEBSERVER",
                    "--webserver-sha256",
                    "PINNED_SHA256",
                    "--shard-root",
                    "BOUNDED_SCRATCH",
                    "--log-root",
                    "BOUNDED_SCRATCH",
                    "--result",
                    "RESULT_JSON",
                    "--report",
                    "RESULT_MARKDOWN",
                    "--startup-timeout-seconds",
                    "10",
                ],
                "environment_keys": sorted(environment),
                "sensitive_environment_inherited": False,
            },
            "launch": dataclasses.asdict(launch),
            "artifacts": artifacts,
            "cleanup": dataclasses.asdict(cleanup),
            "failures": [],
            "truncation": {
                "stdout": False,
                "stderr": False,
                "limit_bytes_each": int(lock.payload["limits"]["log_bytes_each"]),
            },
            "runner": _runner_confounds(),
        }
        receipt = write_semantic_receipt(
            receipt_path,
            request=request,
            status="COMPLETED",
            effect="APPLIED",
            evidence=evidence,
        )
        if launch.returncode != 0:
            raise HostedRunnerError(
                "CONSUMER_RETURNED_NONZERO", f"known return code {launch.returncode}"
            )
        return receipt
    except HostedRunnerError as error:
        if not Path(receipt_path).exists():
            if launched:
                status = "RECONCILIATION_REQUIRED"
                effect = "EFFECT_UNKNOWN"
            else:
                status = "REFUSED"
                effect = "NOT_APPLIED"
            failure_evidence: dict[str, object] = {
                "failure": {
                    "code": error.code,
                    "detail": _bounded_redacted(error.detail, 512),
                },
                "consumer_launch_state": (
                    "COMPLETED_PROCESS"
                    if launch is not None
                    else "ATTEMPTED_UNKNOWN" if launched else "NOT_LAUNCHED"
                ),
                "network_seal": (
                    dataclasses.asdict(proof) if proof is not None else None
                ),
                "runner": _runner_confounds(),
            }
            if launch is not None:
                failure_evidence["launch"] = dataclasses.asdict(launch)
                try:
                    failure_cleanup = _cleanup_candidate_scratch(
                        process_group=launch.process_group,
                        shard_root=shard_root,
                        log_root=log_root,
                    )
                    failure_evidence["cleanup"] = dataclasses.asdict(failure_cleanup)
                except HostedRunnerError as cleanup_error:
                    failure_evidence["cleanup"] = {
                        "state": "FAILED",
                        "code": cleanup_error.code,
                    }
            write_semantic_receipt(
                receipt_path,
                request=request,
                status=status,
                effect=effect,
                evidence=failure_evidence,
            )
        raise


def _download_exact_go_archive(
    destination: Path, *, network_environment: Mapping[str, str]
) -> str:
    client_environment = _validated_phase_p_client_environment(network_environment)
    target = Path(destination)
    parent = _real_directory(target.parent, "DOWNLOAD_DESTINATION_UNSAFE")
    if target.exists() or target.is_symlink():
        raise HostedRunnerError(
            "DOWNLOAD_DESTINATION_UNSAFE", "Go archive destination is occupied"
        )
    current_url = _validated_acquisition_url(locks.GO_ARCHIVE_URL)
    proxy_url = client_environment.get("HTTPS_PROXY")
    if not isinstance(proxy_url, str):
        raise HostedRunnerError(
            "ACQUISITION_ALLOWLIST_UNAVAILABLE", "curl proxy is absent"
        )
    visited: set[str] = set()
    for _hop in range(5):
        if current_url in visited:
            raise HostedRunnerError(
                "ACQUISITION_REDIRECT_FORBIDDEN", "Go archive redirect cycle"
            )
        visited.add(current_url)
        completed = _run_phase_p_checked(
            [
                "/usr/bin/curl",
                "--disable",
                "--proxy",
                proxy_url,
                "--noproxy",
                "",
                "--fail",
                "--silent",
                "--show-error",
                "--max-redirs",
                "0",
                "--proto",
                "=https",
                "--tlsv1.2",
                "--connect-timeout",
                "30",
                "--max-time",
                "300",
                "--output",
                os.fspath(target),
                "--write-out",
                "%{http_code}\n%{url_effective}\n%{redirect_url}\n",
                current_url,
            ],
            cwd=parent,
            env=client_environment,
            network_environment=network_environment,
            timeout=330,
        )
        fields = completed.stdout.splitlines()
        if len(fields) != 3 or re.fullmatch(r"[0-9]{3}", fields[0]) is None:
            raise HostedRunnerError(
                "ACQUISITION_RESPONSE_INVALID", "Go archive response is malformed"
            )
        status, effective_url, redirect_url = fields
        if effective_url != current_url:
            raise HostedRunnerError(
                "ACQUISITION_REDIRECT_FORBIDDEN", "curl changed the validated URL"
            )
        if status == "200":
            if redirect_url:
                raise HostedRunnerError(
                    "ACQUISITION_RESPONSE_INVALID", "successful response redirects"
                )
            break
        if status.startswith("3") and redirect_url:
            target.unlink(missing_ok=True)
            current_url = _validated_acquisition_url(urljoin(current_url, redirect_url))
            continue
        raise HostedRunnerError(
            "ACQUISITION_RESPONSE_INVALID", f"Go archive returned HTTP {status}"
        )
    else:
        raise HostedRunnerError(
            "ACQUISITION_REDIRECT_FORBIDDEN", "Go archive redirect ceiling exceeded"
        )
    if target.stat().st_size != locks.GO_ARCHIVE_SIZE:
        raise HostedRunnerError("ARCHIVE_SIZE_MISMATCH", locks.GO_ARCHIVE_FILENAME)
    if locks.sha256_file(target, max_bytes=134_217_728) != locks.GO_ARCHIVE_SHA256:
        raise HostedRunnerError("ARCHIVE_DIGEST_MISMATCH", locks.GO_ARCHIVE_FILENAME)
    return current_url


def _validated_acquisition_url(value: str) -> str:
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError as error:
        raise HostedRunnerError(
            "ACQUISITION_REDIRECT_FORBIDDEN", "Go archive URL is malformed"
        ) from error
    if (
        parsed.scheme != "https"
        or parsed.hostname not in locks.ALLOWED_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or not parsed.path.startswith("/")
        or parsed.query
        or parsed.fragment
    ):
        raise HostedRunnerError(
            "ACQUISITION_REDIRECT_FORBIDDEN", "Go archive left the allowlist"
        )
    return value


def _verify_go_distribution(
    go_root: Path,
    go_binary: Path,
    *,
    network_environment: Mapping[str, str],
) -> None:
    root = _real_directory(go_root, "GO_ARCHIVE_INVALID")
    binary = _verified_executable(go_binary, expected_sha256=None)
    version_environment = {
        **_validated_phase_p_client_environment(network_environment),
        "GOTOOLCHAIN": "local",
    }
    version = _run_phase_p_checked(
        [os.fspath(binary), "version"],
        cwd=root,
        env=version_environment,
        network_environment=network_environment,
        timeout=30,
    ).stdout.strip()
    if version != f"go version go{locks.GO_VERSION} linux/amd64":
        raise HostedRunnerError("GO_VERSION_MISMATCH", version)
    version_file = root / "VERSION"
    if (
        version_file.read_text(encoding="utf-8").splitlines()[0]
        != f"go{locks.GO_VERSION}"
    ):
        raise HostedRunnerError("GO_VERSION_MISMATCH", "VERSION file differs")
    license_bytes = (root / "LICENSE").read_bytes()
    if (
        locks.git_blob_sha1(license_bytes) != locks.GO_LICENSE_BLOB
        or locks.sha256_bytes(license_bytes) != locks.GO_LICENSE_SHA256
    ):
        raise HostedRunnerError("GO_LICENSE_MISMATCH", "archive license differs")


def _verify_go_source_metadata(
    *, network_environment: Mapping[str, str]
) -> Mapping[str, str]:
    tag = _gh_json(
        f"repos/golang/go/git/ref/tags/{locks.GO_SOURCE_TAG}",
        network_environment=network_environment,
    )
    tag_object = tag.get("object")
    if not isinstance(tag_object, Mapping):
        raise HostedRunnerError("GO_SOURCE_MISMATCH", "tag object absent")
    if (
        tag_object.get("type") != "commit"
        or tag_object.get("sha") != locks.GO_SOURCE_COMMIT
    ):
        raise HostedRunnerError("GO_SOURCE_MISMATCH", "tag commit differs")
    commit = _gh_json(
        f"repos/golang/go/git/commits/{locks.GO_SOURCE_COMMIT}",
        network_environment=network_environment,
    )
    tree = commit.get("tree")
    if not isinstance(tree, Mapping) or tree.get("sha") != locks.GO_SOURCE_TREE:
        raise HostedRunnerError("GO_SOURCE_MISMATCH", "source tree differs")
    license_object = _gh_json(
        f"repos/golang/go/contents/LICENSE?ref={locks.GO_SOURCE_COMMIT}",
        network_environment=network_environment,
    )
    if license_object.get("sha") != locks.GO_LICENSE_BLOB:
        raise HostedRunnerError("GO_LICENSE_MISMATCH", "source license blob differs")
    return {
        "repository": locks.GO_SOURCE_REPOSITORY,
        "tag": locks.GO_SOURCE_TAG,
        "commit": locks.GO_SOURCE_COMMIT,
        "tree": locks.GO_SOURCE_TREE,
        "license_blob_sha1": locks.GO_LICENSE_BLOB,
    }


def _gh_json(
    endpoint: str, *, network_environment: Mapping[str, str]
) -> Mapping[str, Any]:
    completed = _run_phase_p_checked(
        ["/usr/bin/gh", "api", endpoint],
        cwd=Path.cwd(),
        env=_github_client_environment(network_environment),
        network_environment=network_environment,
        timeout=60,
    )
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise HostedRunnerError("UPSTREAM_METADATA_INVALID", endpoint) from error
    if not isinstance(value, Mapping):
        raise HostedRunnerError("UPSTREAM_METADATA_INVALID", endpoint)
    return value


def _gh_paginated_rows(
    endpoint: str,
    *,
    field: str,
    max_rows: int,
    network_environment: Mapping[str, str],
) -> list[Mapping[str, Any]]:
    """Read one complete bounded GitHub collection or fail closed on movement."""

    if (
        not endpoint
        or "page=" in endpoint
        or "per_page=" in endpoint
        or re.fullmatch(r"[a-z_]{1,64}", field) is None
        or max_rows <= 0
    ):
        raise HostedRunnerError(
            "REPLAY_LOOKUP_INVALID", "pagination request is invalid"
        )
    separator = "&" if "?" in endpoint else "?"
    expected_total: int | None = None
    page = 1
    rows: list[Mapping[str, Any]] = []
    seen_ids: set[int] = set()
    while expected_total is None or len(rows) < expected_total:
        response = _gh_json(
            f"{endpoint}{separator}per_page=100&page={page}",
            network_environment=network_environment,
        )
        total = response.get("total_count")
        raw_rows = response.get(field)
        if (
            isinstance(total, bool)
            or not isinstance(total, int)
            or total < 0
            or not isinstance(raw_rows, list)
        ):
            raise HostedRunnerError(
                "REPLAY_LOOKUP_INVALID", "paginated response is malformed"
            )
        if total > max_rows:
            raise HostedRunnerError(
                "REPLAY_LOOKUP_INVALID", "paginated response exceeds safety ceiling"
            )
        if expected_total is None:
            expected_total = total
        elif total != expected_total:
            raise HostedRunnerError(
                "EFFECT_UNKNOWN_REPLAY_BLOCKED", "GitHub collection moved during census"
            )
        if not raw_rows and len(rows) < expected_total:
            raise HostedRunnerError(
                "REPLAY_LOOKUP_INVALID", "paginated response ended early"
            )
        for raw_row in raw_rows:
            if not isinstance(raw_row, Mapping):
                raise HostedRunnerError(
                    "REPLAY_LOOKUP_INVALID", "paginated row is malformed"
                )
            row_id = raw_row.get("id")
            if (
                isinstance(row_id, bool)
                or not isinstance(row_id, int)
                or row_id <= 0
                or row_id in seen_ids
            ):
                raise HostedRunnerError(
                    "EFFECT_UNKNOWN_REPLAY_BLOCKED", "GitHub collection is ambiguous"
                )
            seen_ids.add(row_id)
            rows.append(raw_row)
        if len(rows) > expected_total:
            raise HostedRunnerError(
                "EFFECT_UNKNOWN_REPLAY_BLOCKED", "GitHub collection grew during census"
            )
        page += 1
    return rows


def _checkout_exact_zoekt(
    destination: Path, *, network_environment: Mapping[str, str]
) -> None:
    if destination.exists() or destination.is_symlink():
        raise HostedRunnerError("SOURCE_CONFLICT", destination.name)
    client_environment = _validated_phase_p_client_environment(network_environment)
    proxy_url = client_environment.get("HTTPS_PROXY")
    if not isinstance(proxy_url, str):
        raise HostedRunnerError(
            "ACQUISITION_ALLOWLIST_UNAVAILABLE", "Git proxy is absent"
        )
    git_environment = {
        **client_environment,
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }
    destination.mkdir(parents=True, mode=0o700)
    run_checked(["/usr/bin/git", "init", "-q"], cwd=destination, env=git_environment)
    run_checked(
        [
            "/usr/bin/git",
            "remote",
            "add",
            "origin",
            locks.ZOEKT_SOURCE_URL,
        ],
        cwd=destination,
        env=git_environment,
    )
    _run_phase_p_checked(
        [
            "/usr/bin/git",
            "-c",
            "protocol.version=2",
            "-c",
            f"http.proxy={proxy_url}",
            "-c",
            "http.followRedirects=false",
            "-c",
            "protocol.allow=never",
            "-c",
            "protocol.https.allow=always",
            "fetch",
            "--no-tags",
            "--depth=1",
            "origin",
            locks.ZOEKT_COMMIT,
        ],
        cwd=destination,
        env=git_environment,
        network_environment=network_environment,
        timeout=300,
    )
    run_checked(
        ["/usr/bin/git", "checkout", "--detach", "--quiet", locks.ZOEKT_COMMIT],
        cwd=destination,
        env=git_environment,
        timeout=60,
    )


def _repeat_build_zoekt(
    source: Path,
    *,
    go_binary: Path,
    scratch: Path,
    payload_bin: Path,
    network_environment: Mapping[str, str],
) -> Mapping[str, Any]:
    client_environment = _validated_phase_p_client_environment(network_environment)
    go = _verified_executable(go_binary, expected_sha256=None)
    module_cache = scratch / "gomodcache"
    go_path = scratch / "gopath"
    home = scratch / "home"
    for directory in (module_cache, go_path, home):
        directory.mkdir(parents=True, mode=0o700)
    common_env = {
        **client_environment,
        "CGO_ENABLED": "0",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GOARCH": "amd64",
        "GOENV": "off",
        "GOINSECURE": "",
        "GONOPROXY": "",
        "GONOSUMDB": "off",
        "GOOS": "linux",
        "GOPATH": os.fspath(go_path),
        "GOMODCACHE": os.fspath(module_cache),
        "GOPRIVATE": "",
        "GOPROXY": "https://proxy.golang.org",
        "GOSUMDB": "sum.golang.org",
        "GOTOOLCHAIN": "local",
        "GOVCS": "*:off",
        "HOME": os.fspath(home),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": f"{go.parent}:/usr/bin:/bin",
        "TZ": "UTC",
    }
    _run_phase_p_checked(
        [os.fspath(go), "mod", "download", "-json", "all"],
        cwd=source,
        env={**common_env, "GOCACHE": os.fspath(scratch / "download-cache")},
        network_environment=network_environment,
        timeout=600,
    )
    _run_phase_p_checked(
        [os.fspath(go), "mod", "verify"],
        cwd=source,
        env={**common_env, "GOCACHE": os.fspath(scratch / "verify-cache")},
        network_environment=network_environment,
        timeout=300,
    )
    inventory_output = _run_phase_p_checked(
        [os.fspath(go), "list", "-mod=readonly", "-m", "-json", "all"],
        cwd=source,
        env={**common_env, "GOCACHE": os.fspath(scratch / "list-cache")},
        network_environment=network_environment,
        timeout=300,
    ).stdout
    modules = _normalize_go_module_inventory(inventory_output)

    builds: list[dict[str, Mapping[str, object]]] = []
    packages = {
        "zoekt-git-index": "./cmd/zoekt-git-index",
        "zoekt-webserver": "./cmd/zoekt-webserver",
    }
    for attempt in (1, 2):
        output = scratch / f"build-{attempt}"
        cache = scratch / f"gocache-{attempt}"
        output.mkdir(mode=0o700)
        cache.mkdir(mode=0o700)
        rows: dict[str, Mapping[str, object]] = {}
        env = {**common_env, "GOCACHE": os.fspath(cache)}
        for name, package in packages.items():
            target = output / name
            _run_phase_p_checked(
                [
                    os.fspath(go),
                    "build",
                    "-mod=readonly",
                    "-trimpath",
                    "-buildvcs=false",
                    "-ldflags=-buildid=",
                    "-o",
                    os.fspath(target),
                    package,
                ],
                cwd=source,
                env=env,
                network_environment=network_environment,
                timeout=900,
            )
            executable = _verified_executable(target, expected_sha256=None)
            rows[name] = {
                "sha256": locks.sha256_file(executable, max_bytes=100_663_296),
                "size": executable.stat().st_size,
                "mode": "0755",
                "build_attempt": attempt,
            }
        builds.append(rows)
    first, second = builds
    for name in packages:
        if (
            first[name]["sha256"] != second[name]["sha256"]
            or first[name]["size"] != second[name]["size"]
        ):
            raise HostedRunnerError(
                "NONDETERMINISTIC_BUILD", f"{name} differs across clean caches"
            )
        source_binary = scratch / "build-1" / name
        target = payload_bin / name
        shutil.copyfile(source_binary, target)
        os.chmod(target, 0o755)
        if locks.sha256_file(target, max_bytes=100_663_296) != first[name]["sha256"]:
            raise HostedRunnerError("BINARY_COPY_MISMATCH", name)
    final_rows = {
        name: {
            "sha256": first[name]["sha256"],
            "size": first[name]["size"],
            "mode": "0755",
            "repeat_builds": 2,
            "byte_identical": True,
        }
        for name in packages
    }
    return {"modules": modules, "binaries": final_rows}


def _normalize_go_module_inventory(raw: str) -> list[Mapping[str, object]]:
    decoder = json.JSONDecoder()
    offset = 0
    modules: list[Mapping[str, object]] = []
    while True:
        while offset < len(raw) and raw[offset].isspace():
            offset += 1
        if offset == len(raw):
            break
        try:
            value, offset = decoder.raw_decode(raw, offset)
        except json.JSONDecodeError as error:
            raise HostedRunnerError(
                "DEPENDENCY_GRAPH_INVALID", "go list output is malformed"
            ) from error
        if not isinstance(value, Mapping):
            raise HostedRunnerError(
                "DEPENDENCY_GRAPH_INVALID", "module row is not an object"
            )
        path = value.get("Path")
        if not isinstance(path, str) or not path:
            raise HostedRunnerError("DEPENDENCY_GRAPH_INVALID", "module path is absent")
        row: dict[str, object] = {
            "path": path,
            "main": bool(value.get("Main", False)),
        }
        for source_key, target_key in (
            ("Version", "version"),
            ("Sum", "sum"),
            ("GoModSum", "go_mod_sum"),
        ):
            if source_key in value:
                field = value[source_key]
                if not isinstance(field, str) or not field:
                    raise HostedRunnerError(
                        "DEPENDENCY_GRAPH_INVALID", f"{source_key} is malformed"
                    )
                row[target_key] = field
        replace = value.get("Replace")
        if replace is not None:
            if not isinstance(replace, Mapping):
                raise HostedRunnerError(
                    "DEPENDENCY_GRAPH_INVALID", "replace row is malformed"
                )
            replacement_path = replace.get("Path")
            replacement_version = replace.get("Version")
            replacement_sum = replace.get("Sum")
            if (
                not isinstance(replacement_path, str)
                or not isinstance(replacement_version, str)
                or not isinstance(replacement_sum, str)
            ):
                raise HostedRunnerError(
                    "DEPENDENCY_GRAPH_INVALID",
                    "local or incompletely summed replacement is forbidden",
                )
            row["replace"] = {
                "path": replacement_path,
                "version": replacement_version,
                "sum": replacement_sum,
            }
        if not row["main"] and (
            "version" not in row or "sum" not in row or "go_mod_sum" not in row
        ):
            raise HostedRunnerError(
                "DEPENDENCY_GRAPH_INVALID", f"incomplete sums for {path}"
            )
        modules.append(row)
    if not modules or sum(bool(row["main"]) for row in modules) != 1:
        raise HostedRunnerError(
            "DEPENDENCY_GRAPH_INVALID", "main module census differs"
        )
    main_module = next(row for row in modules if bool(row["main"]))
    if main_module["path"] != locks.ZOEKT_MODULE_PATH:
        raise HostedRunnerError(
            "DEPENDENCY_GRAPH_INVALID", "main module path differs from pinned go.mod"
        )
    modules.sort(key=lambda row: (str(row["path"]), str(row.get("version", ""))))
    assert_secret_free(modules)
    return modules


def _verified_executable(path: Path, *, expected_sha256: str | None) -> Path:
    candidate = Path(path)
    try:
        metadata = candidate.lstat()
    except OSError as error:
        raise HostedRunnerError("EXECUTABLE_UNAVAILABLE", candidate.name) from error
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or not metadata.st_mode & 0o111
        or metadata.st_mode & (stat.S_IWOTH | stat.S_ISUID | stat.S_ISGID)
    ):
        raise HostedRunnerError("EXECUTABLE_UNSAFE", candidate.name)
    if expected_sha256 is not None:
        if _SHA256_RE.fullmatch(expected_sha256) is None:
            raise HostedRunnerError("EXECUTABLE_DIGEST_MISMATCH", candidate.name)
        if locks.sha256_file(candidate, max_bytes=100_663_296) != expected_sha256:
            raise HostedRunnerError("EXECUTABLE_DIGEST_MISMATCH", candidate.name)
    return candidate.resolve()


def _runner_confounds() -> Mapping[str, object]:
    value = {
        "runner_os": os.environ.get("RUNNER_OS", platform.system()),
        "runner_arch": os.environ.get("RUNNER_ARCH", platform.machine()),
        "runner_image": os.environ.get("ImageOS", "UNAVAILABLE"),
        "runner_image_version": os.environ.get("ImageVersion", "UNAVAILABLE"),
        "kernel_release": platform.release(),
        "python": platform.python_version(),
        "production_inert": True,
    }
    assert_secret_free(value)
    return value


def _fresh_directory(path: Path, code: str) -> Path:
    candidate = Path(path)
    if candidate.exists() or candidate.is_symlink():
        raise HostedRunnerError(code, f"{candidate.name} already exists")
    candidate.mkdir(parents=True, mode=0o700)
    return _real_directory(candidate, code)


def _append_github_outputs(path: Path, values: Mapping[str, str]) -> None:
    output = Path(path)
    if output.exists() or output.is_symlink():
        try:
            metadata = output.lstat()
        except OSError as error:
            raise HostedRunnerError("OUTPUT_UNSAFE", output.name) from error
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise HostedRunnerError("OUTPUT_UNSAFE", output.name)
    for key, value in values.items():
        if re.fullmatch(r"[a-z_]{1,64}", key) is None:
            raise HostedRunnerError("OUTPUT_UNSAFE", "invalid output key")
        if re.fullmatch(r"[A-Za-z0-9._+-]{1,256}", value) is None:
            raise HostedRunnerError("OUTPUT_UNSAFE", f"invalid output value for {key}")
    with output.open("a", encoding="utf-8", newline="\n") as stream:
        for key, value in values.items():
            stream.write(f"{key}={value}\n")


def _manifest_file_digest(manifest: Mapping[str, Any], relative: str) -> str:
    rows = manifest.get("files")
    if not isinstance(rows, list):
        raise HostedRunnerError("BUNDLE_MANIFEST_INVALID", "file rows absent")
    matching = [
        row for row in rows if isinstance(row, Mapping) and row.get("path") == relative
    ]
    if len(matching) != 1 or not isinstance(matching[0].get("sha256"), str):
        raise HostedRunnerError("BUNDLE_MANIFEST_INVALID", relative)
    digest = matching[0]["sha256"]
    if _SHA256_RE.fullmatch(digest) is None:
        raise HostedRunnerError("BUNDLE_MANIFEST_INVALID", relative)
    return digest


def _validate_workflow_action_pins(
    workflow_path: Path, lock: locks.ToolchainLock
) -> None:
    """Require every workflow Action use to equal the independently pinned lock."""

    candidate = _regular_file(
        workflow_path, "ACTION_PIN_MISMATCH", max_bytes=1_048_576
    )
    try:
        source = candidate.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise HostedRunnerError(
            "ACTION_PIN_MISMATCH", "workflow source is unavailable"
        ) from error
    observed: dict[str, set[str]] = {}
    for repository, commit in re.findall(
        r"(?m)^\s*- uses: ([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@([^\s#]+)",
        source,
    ):
        observed.setdefault(repository, set()).add(commit)
    expected = {
        str(row["repository"]): str(row["commit"])
        for row in lock.payload["actions"].values()
    }
    if set(observed) != set(expected) or any(
        commits != {expected[repository]}
        for repository, commits in observed.items()
    ):
        raise HostedRunnerError(
            "ACTION_PIN_MISMATCH", "workflow Action pins differ from the closed lock"
        )
    if (
        source.count("ref: ${{ inputs.consumer_sha }}") != 1
        or "refs/pull/" in source
        or "switch -C" in source
    ):
        raise HostedRunnerError(
            "ACTION_PIN_MISMATCH",
            "workflow consumer checkout is not bound to the immutable input SHA",
        )


def _require_within_root(path: Path, root: Path) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError) as error:
        raise HostedRunnerError(
            "CONSUMER_PATH_POLICY_UNSAFE", "path escaped consumer root"
        ) from error


def _require_outside_consumer_root(path: Path, consumer_root: Path) -> None:
    try:
        Path(path).resolve().relative_to(Path(consumer_root).resolve())
    except ValueError:
        return
    except OSError as error:
        raise HostedRunnerError(
            "CONSUMER_MOUNT_SEAL_UNSAFE", "boundary path cannot be resolved"
        ) from error
    raise HostedRunnerError(
        "CONSUMER_MOUNT_SEAL_UNSAFE",
        "writable Phase E path overlaps the consumer source root",
    )


def _regular_file(path: Path, code: str, *, max_bytes: int) -> Path:
    candidate = Path(path)
    try:
        metadata = candidate.lstat()
    except OSError as error:
        raise HostedRunnerError(code, candidate.name) from error
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size > max_bytes
        or metadata.st_mode & stat.S_IWOTH
    ):
        raise HostedRunnerError(code, candidate.name)
    return candidate.resolve()


def _launch_fixed_consumer(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout_seconds: int,
    log_limit: int,
) -> LaunchEvidence:
    started = time.monotonic()
    before = resource.getrusage(resource.RUSAGE_CHILDREN)

    def limits() -> None:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_CPU, (timeout_seconds, timeout_seconds + 1))
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
        resource.setrlimit(resource.RLIMIT_NPROC, (256, 256))
        resource.setrlimit(resource.RLIMIT_FSIZE, (536_870_912, 536_870_912))

    try:
        process = subprocess.Popen(
            list(argv),
            cwd=os.fspath(cwd),
            env=dict(env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            preexec_fn=limits,
        )
    except OSError as error:
        raise HostedRunnerError(
            "CONSUMER_LAUNCH_FAILED", "fixed process unavailable"
        ) from error
    assert process.stdout is not None
    assert process.stderr is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    streams = {"stdout": bytearray(), "stderr": bytearray()}
    timed_out = False
    overflow: str | None = None
    try:
        while selector.get_map():
            remaining = timeout_seconds - (time.monotonic() - started)
            if remaining <= 0:
                timed_out = True
                break
            events = selector.select(timeout=min(1.0, remaining))
            if not events and process.poll() is not None:
                # A final nonblocking pass delivers EOF for both pipes.
                events = selector.select(timeout=0)
                if not events:
                    break
            for key, _mask in events:
                chunk = os.read(key.fileobj.fileno(), 65_536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                    continue
                target = streams[str(key.data)]
                target.extend(chunk)
                if len(target) > log_limit:
                    overflow = str(key.data)
                    break
            if overflow:
                break
        if timed_out or overflow:
            _kill_process_group(process.pid)
        returncode = process.wait(timeout=15)
    except (OSError, subprocess.TimeoutExpired) as error:
        _kill_process_group(process.pid)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            pass
        raise HostedRunnerError(
            "CONSUMER_EFFECT_UNKNOWN", "process result could not be reconciled"
        ) from error
    finally:
        selector.close()
        for stream in (process.stdout, process.stderr):
            try:
                stream.close()
            except OSError:
                pass
    if timed_out:
        raise HostedRunnerError("CONSUMER_TIMEOUT", str(timeout_seconds))
    if overflow:
        raise HostedRunnerError("LOG_LIMIT_EXCEEDED", overflow)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    stdout = bytes(streams["stdout"])
    stderr = bytes(streams["stderr"])
    assert_secret_free(stdout)
    assert_secret_free(stderr)
    return LaunchEvidence(
        returncode=returncode,
        pid=process.pid,
        process_group=process.pid,
        stdout_sha256=hashlib.sha256(stdout).hexdigest(),
        stderr_sha256=hashlib.sha256(stderr).hexdigest(),
        stdout_bytes=len(stdout),
        stderr_bytes=len(stderr),
        user_seconds=max(0.0, after.ru_utime - before.ru_utime),
        system_seconds=max(0.0, after.ru_stime - before.ru_stime),
        max_rss_kib=max(0, int(after.ru_maxrss)),
    )


def _kill_process_group(process_group: int) -> None:
    try:
        os.killpg(process_group, signal.SIGKILL)
    except ProcessLookupError:
        return
    except OSError as error:
        raise HostedRunnerError(
            "CLEANUP_LEAK", "process group could not be killed"
        ) from error


def _process_group_dead(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


def _cleanup_candidate_scratch(
    *, process_group: int, shard_root: Path, log_root: Path
) -> CleanupEvidence:
    for path in (shard_root, log_root):
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise HostedRunnerError(
                "CLEANUP_LEAK", "candidate scratch could not be inspected"
            ) from error
        if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
            try:
                shutil.rmtree(path)
            except OSError as error:
                raise HostedRunnerError(
                    "CLEANUP_LEAK", "candidate scratch could not be removed"
                ) from error
    residue = tuple(
        label
        for label, path in (("shards", shard_root), ("logs", log_root))
        if path.exists() or path.is_symlink()
    )
    return CleanupEvidence(
        process_group_dead=_process_group_dead(process_group),
        unexpected_residue=residue,
    )


def _validate_success_artifacts(
    *,
    output: Path,
    request: ExperimentRequest,
    manifest_payload: Mapping[str, object],
    path_policy: Path,
    source_digest: str,
    binary_digests: Mapping[str, str],
    expected_tool_schema_digest: str,
) -> Mapping[str, object]:
    """Validate the consumer's complete zero-exit evidence before success."""

    result_path = _regular_file(
        Path(output) / "z0-result.json",
        "RESULT_ARTIFACT_REQUIRED",
        max_bytes=1_048_576,
    )
    report_path = _regular_file(
        Path(output) / "z0-report.md",
        "RESULT_ARTIFACT_REQUIRED",
        max_bytes=1_048_576,
    )
    result_bytes = result_path.read_bytes()
    report_bytes = report_path.read_bytes()
    assert_secret_free(result_bytes)
    assert_secret_free(report_bytes)

    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        decoded: dict[str, object] = {}
        for key, value in pairs:
            if key in decoded:
                raise ValueError(f"duplicate key: {key}")
            decoded[key] = value
        return decoded

    def reject_non_finite(value: str) -> object:
        raise ValueError(f"non-finite value: {value}")

    try:
        payload = json.loads(
            result_bytes.decode("utf-8"),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_non_finite,
        )
    except (UnicodeDecodeError, ValueError) as error:
        raise HostedRunnerError(
            "RESULT_JSON_INVALID", "z0-result.json is not strict UTF-8 JSON"
        ) from error
    if not isinstance(payload, Mapping) or set(payload) != _Z0_RESULT_FIELDS:
        raise HostedRunnerError(
            "RESULT_IDENTITY_MISMATCH", "result top-level fields differ"
        )

    repositories = manifest_payload.get("repositories")
    if not isinstance(repositories, list) or len(repositories) != 1:
        raise HostedRunnerError(
            "RESULT_IDENTITY_MISMATCH", "host manifest identity is unavailable"
        )
    manifest_row = repositories[0]
    if not isinstance(manifest_row, Mapping):
        raise HostedRunnerError(
            "RESULT_IDENTITY_MISMATCH", "host manifest row is unavailable"
        )
    material_fields = (
        "repository_id",
        "repository_name",
        "ref_label",
        "commit_sha",
        "included_prefixes",
        "excluded_globs",
        "source_tree_digest",
    )
    try:
        material_row = {field: manifest_row[field] for field in material_fields}
    except KeyError as error:
        raise HostedRunnerError(
            "RESULT_IDENTITY_MISMATCH", "host manifest material fields differ"
        ) from error
    expected_manifest_digest = locks.sha256_bytes(
        locks.canonical_json_bytes(
            {
                "schema_version": "mastermind.codeintel_index_manifest.v1",
                "repositories": [material_row],
            }
        )
    )
    expected_binaries = {
        "zoekt_git_index": binary_digests.get("zoekt-git-index"),
        "zoekt_webserver": binary_digests.get("zoekt-webserver"),
    }
    expected_resource_observations = {
        "benchmarks_complete": False,
        "benchmark_gate": "separate evidenced ingestion required",
        "production_inert": True,
        "endpoint_scope": "loopback_disposable_only",
    }
    if (
        payload.get("schema_version") != "mastermind.codeintel_z0_result.v1"
        or payload.get("decision") != _Z0_NON_ACCEPTANCE_DECISION
        or payload.get("manifest_digest") != expected_manifest_digest
        or payload.get("path_policy_digest")
        != locks.sha256_file(path_policy, max_bytes=1_048_576)
        or payload.get("tool_schema_digest") != expected_tool_schema_digest
        or payload.get("zoekt_source_commit") != locks.ZOEKT_COMMIT
        or payload.get("binary_digests") != expected_binaries
        or payload.get("resource_observations") != expected_resource_observations
    ):
        raise HostedRunnerError(
            "RESULT_IDENTITY_MISMATCH", "result request/source/tool identity differs"
        )

    def require_utc_timestamp(value: object) -> str:
        if not isinstance(value, str) or not value or len(value) > 128:
            raise HostedRunnerError(
                "RESULT_IDENTITY_MISMATCH", "result timestamp is malformed"
            )
        try:
            observed = datetime.fromisoformat(value)
        except ValueError as error:
            raise HostedRunnerError(
                "RESULT_IDENTITY_MISMATCH", "result timestamp is malformed"
            ) from error
        if observed.tzinfo is None or observed.utcoffset() != timedelta(0):
            raise HostedRunnerError(
                "RESULT_IDENTITY_MISMATCH", "result timestamp is not UTC"
            )
        return value

    generated_at = require_utc_timestamp(payload.get("generated_at"))
    statuses = payload.get("repository_statuses")
    if not isinstance(statuses, list) or len(statuses) != 1:
        raise HostedRunnerError(
            "RESULT_IDENTITY_MISMATCH", "result repository status census differs"
        )
    status_row = statuses[0]
    if not isinstance(status_row, Mapping) or set(status_row) != _Z0_STATUS_FIELDS:
        raise HostedRunnerError(
            "RESULT_IDENTITY_MISMATCH", "result repository status fields differ"
        )
    shard_material = "\0".join(
        (
            "mastermind",
            FIXED_REPOSITORY,
            FIXED_CONSUMER_BRANCH,
            request.consumer_sha,
            source_digest,
        )
    ).encode("utf-8")
    expected_shard = f"z0-{hashlib.sha256(shard_material).hexdigest()[:24]}"
    freshness = status_row.get("freshness_seconds")
    if (
        status_row.get("repository_id") != "mastermind"
        or status_row.get("ref_label") != FIXED_CONSUMER_BRANCH
        or status_row.get("indexed_commit_sha") != request.consumer_sha
        or status_row.get("source_tree_digest") != source_digest
        or status_row.get("shard_namespace") != expected_shard
        or status_row.get("health") != "healthy"
        or status_row.get("coverage") != "covered"
        or isinstance(freshness, bool)
        or freshness != 0.0
    ):
        raise HostedRunnerError(
            "RESULT_IDENTITY_MISMATCH", "result repository status identity differs"
        )
    require_utc_timestamp(status_row.get("generated_at"))
    require_utc_timestamp(status_row.get("observed_at"))

    expected_report = (
        "# Z0 Global Discovery Falsifier Result\n\n"
        f"Decision: {_Z0_NON_ACCEPTANCE_DECISION}\n\n"
        f"Generated at: {generated_at}\n\n"
        "## Repository/ref status\n\n"
        f"- mastermind/{FIXED_CONSUMER_BRANCH}: health=healthy; "
        f"coverage=covered; indexed_sha={request.consumer_sha}\n\n"
        "This is a disposable production-inert experiment result. It does not "
        "provision a persistent service, capability profile, credential, MCP "
        "endpoint, CI3 grant, or deployment.\n"
    ).encode("utf-8")
    if report_bytes != expected_report:
        raise HostedRunnerError(
            "RESULT_REPORT_MISMATCH", "z0-report.md does not bind result identity"
        )
    return _result_artifact_census(Path(output))


def _result_artifact_census(output: Path) -> Mapping[str, object]:
    rows: dict[str, object] = {}
    for relative in ("z0-result.json", "z0-report.md"):
        path = output / relative
        if path.exists() or path.is_symlink():
            candidate = _regular_file(
                path, "RESULT_ARTIFACT_UNSAFE", max_bytes=1_048_576
            )
            body = candidate.read_bytes()
            assert_secret_free(body)
            rows[relative] = {
                "name": relative,
                "size": candidate.stat().st_size,
                "sha256": locks.sha256_bytes(body),
            }
        else:
            rows[relative] = {"name": relative, "state": "ABSENT"}
    assert_secret_free(rows)
    return rows


def _bundle_payload_census(root: Path) -> list[tuple[str, Path, int]]:
    rows: list[tuple[str, Path, int]] = []
    for path in sorted(
        root.rglob("*"), key=lambda value: value.relative_to(root).as_posix()
    ):
        relative = path.relative_to(root).as_posix()
        _safe_bundle_name(relative)
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise HostedRunnerError("BUNDLE_PAYLOAD_UNSAFE", f"symlink {relative}")
        if stat.S_ISDIR(metadata.st_mode):
            if metadata.st_mode & stat.S_IWOTH:
                raise HostedRunnerError(
                    "BUNDLE_PAYLOAD_UNSAFE", f"world-writable {relative}"
                )
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise HostedRunnerError("BUNDLE_PAYLOAD_UNSAFE", f"special file {relative}")
        if metadata.st_mode & (stat.S_IWOTH | stat.S_ISUID | stat.S_ISGID):
            raise HostedRunnerError("BUNDLE_PAYLOAD_UNSAFE", f"unsafe mode {relative}")
        mode = 0o755 if metadata.st_mode & 0o111 else 0o644
        if relative.startswith("bin/") and mode != 0o755:
            raise HostedRunnerError(
                "BUNDLE_PAYLOAD_UNSAFE", f"non-executable binary {relative}"
            )
        if not relative.startswith("bin/") and mode != 0o644:
            raise HostedRunnerError(
                "BUNDLE_PAYLOAD_UNSAFE", f"executable metadata {relative}"
            )
        if metadata.st_size > 100_663_296:
            raise HostedRunnerError(
                "BUNDLE_PAYLOAD_UNSAFE", f"oversized file {relative}"
            )
        body = path.read_bytes()
        assert_secret_free(body)
        rows.append((relative, path, mode))
    return rows


def _bundle_role(relative: str) -> str:
    roles = {
        "bin/zoekt-git-index": "Z0_INDEXER_EXECUTABLE",
        "bin/zoekt-webserver": "Z0_SEARCH_EXECUTABLE",
        "meta/NOTICE.txt": "RIGHTS_AND_NOTICES",
        "meta/provenance.json": "PHASE_P_PROVENANCE",
        "meta/sbom.json": "GO_MODULE_INVENTORY",
        "meta/toolchain-lock.json": "EXACT_TOOLCHAIN_LOCK",
    }
    try:
        return roles[relative]
    except KeyError as error:
        raise HostedRunnerError("BUNDLE_PAYLOAD_UNEXPECTED", relative) from error


def _safe_bundle_name(name: str) -> str:
    if not name or "\\" in name or "\x00" in name:
        raise HostedRunnerError("BUNDLE_PAYLOAD_UNSAFE", "invalid path")
    candidate = PurePosixPath(name)
    if candidate.is_absolute() or any(
        part in {"", ".", ".."} for part in candidate.parts
    ):
        raise HostedRunnerError("BUNDLE_PAYLOAD_UNSAFE", name)
    if any(_SAFE_BUNDLE_PART_RE.fullmatch(part) is None for part in candidate.parts):
        raise HostedRunnerError("BUNDLE_PAYLOAD_UNSAFE", name)
    return candidate.as_posix()


def _add_tar_directory(archive: tarfile.TarFile, relative: str) -> None:
    info = tarfile.TarInfo(relative)
    info.type = tarfile.DIRTYPE
    info.size = 0
    info.mode = 0o755
    _canonicalize_tar_info(info)
    archive.addfile(info)


def _add_tar_file(
    archive: tarfile.TarFile, relative: str, source: Path, mode: int
) -> None:
    info = tarfile.TarInfo(relative)
    info.type = tarfile.REGTYPE
    info.size = source.stat().st_size
    info.mode = mode
    _canonicalize_tar_info(info)
    with source.open("rb") as stream:
        archive.addfile(info, stream)


def _add_tar_bytes(
    archive: tarfile.TarFile, relative: str, body: bytes, mode: int
) -> None:
    info = tarfile.TarInfo(relative)
    info.type = tarfile.REGTYPE
    info.size = len(body)
    info.mode = mode
    _canonicalize_tar_info(info)
    archive.addfile(info, io.BytesIO(body))


def _canonicalize_tar_info(info: tarfile.TarInfo) -> None:
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    info.pax_headers = {}


def _validate_bundle_members(members: Sequence[tarfile.TarInfo]) -> None:
    if not members:
        raise HostedRunnerError("BUNDLE_UNSAFE", "bundle is empty")
    seen: set[str] = set()
    total = 0
    for member in members:
        name = _safe_bundle_name(member.name)
        if name in seen:
            raise HostedRunnerError("BUNDLE_UNSAFE", f"duplicate {name}")
        seen.add(name)
        if not (member.isdir() or member.isreg()):
            raise HostedRunnerError("BUNDLE_UNSAFE", f"link/special {name}")
        if member.mode & (stat.S_IWOTH | stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX):
            raise HostedRunnerError("BUNDLE_UNSAFE", f"unsafe mode {name}")
        if member.uid != 0 or member.gid != 0 or member.mtime != 0:
            raise HostedRunnerError("BUNDLE_NONDETERMINISTIC", name)
        if member.isreg():
            if member.size < 0 or member.size > 100_663_296:
                raise HostedRunnerError("BUNDLE_UNSAFE", f"oversized {name}")
            total += member.size
            if total > 536_870_912:
                raise HostedRunnerError(
                    "BUNDLE_UNSAFE", "expanded bundle exceeds ceiling"
                )
    if "manifest.json" not in seen:
        raise HostedRunnerError("BUNDLE_MANIFEST_INVALID", "manifest absent")


def _validate_bundle_manifest(value: object) -> None:
    if not isinstance(value, Mapping):
        raise HostedRunnerError("BUNDLE_MANIFEST_INVALID", "manifest must be an object")
    if set(value) != {"schema_version", "mode", "context", "files"}:
        raise HostedRunnerError("BUNDLE_MANIFEST_INVALID", "manifest fields differ")
    if (
        value.get("schema_version") != BUNDLE_MANIFEST_SCHEMA_VERSION
        or value.get("mode") != "Z0"
    ):
        raise HostedRunnerError("BUNDLE_MANIFEST_INVALID", "manifest identity differs")
    context = value.get("context")
    rows = value.get("files")
    if not isinstance(context, Mapping) or not isinstance(rows, list):
        raise HostedRunnerError(
            "BUNDLE_MANIFEST_INVALID", "manifest content is malformed"
        )
    expected_fields = {"path", "role", "mode", "size", "sha256"}
    paths: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != expected_fields:
            raise HostedRunnerError("BUNDLE_MANIFEST_INVALID", "file row fields differ")
        path = row.get("path")
        if (
            not isinstance(path, str)
            or _safe_bundle_name(path) != path
            or path in paths
        ):
            raise HostedRunnerError("BUNDLE_MANIFEST_INVALID", "file path is invalid")
        paths.add(path)
        if row.get("role") != _bundle_role(path):
            raise HostedRunnerError(
                "BUNDLE_MANIFEST_INVALID", f"role differs for {path}"
            )
        expected_mode = "0755" if path.startswith("bin/") else "0644"
        if row.get("mode") != expected_mode:
            raise HostedRunnerError(
                "BUNDLE_MANIFEST_INVALID", f"mode differs for {path}"
            )
        if not isinstance(row.get("size"), int) or not 0 <= row["size"] <= 100_663_296:
            raise HostedRunnerError(
                "BUNDLE_MANIFEST_INVALID", f"size differs for {path}"
            )
        if (
            not isinstance(row.get("sha256"), str)
            or _SHA256_RE.fullmatch(row["sha256"]) is None
        ):
            raise HostedRunnerError(
                "BUNDLE_MANIFEST_INVALID", f"digest differs for {path}"
            )
    if paths != _REQUIRED_BUNDLE_FILES:
        raise HostedRunnerError("BUNDLE_MANIFEST_INVALID", "payload roles differ")
    assert_secret_free(value)


def _ensure_output_directory(path: Path) -> Path:
    output = Path(path)
    if output.exists() or output.is_symlink():
        return _real_directory(output, "OUTPUT_UNSAFE")
    output.mkdir(parents=True, mode=0o700)
    return _real_directory(output, "OUTPUT_UNSAFE")


def _real_directory(path: Path, code: str) -> Path:
    candidate = Path(path)
    try:
        metadata = candidate.lstat()
    except OSError as error:
        raise HostedRunnerError(code, f"{candidate.name} is unavailable") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise HostedRunnerError(code, f"{candidate.name} is not a real directory")
    return candidate.resolve()


def _normalize_github_remote(remote: str) -> str | None:
    candidate = remote.strip()
    if candidate.startswith("git@github.com:"):
        path = candidate.removeprefix("git@github.com:")
    else:
        parsed = urlparse(candidate)
        if parsed.scheme not in {"https", "ssh"} or parsed.hostname != "github.com":
            return None
        if parsed.scheme == "ssh" and parsed.username != "git":
            return None
        if parsed.username is not None and parsed.scheme == "https":
            return None
        path = parsed.path.lstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return path if path == FIXED_REPOSITORY else None


def _git_bytes(root: Path, *arguments: str) -> bytes:
    try:
        completed = subprocess.run(
            ["/usr/bin/git", "-C", os.fspath(root), *arguments],
            check=False,
            capture_output=True,
            timeout=30,
            env={
                "PATH": "/usr/bin:/bin",
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_ASKPASS": "/bin/false",
                "LANG": "C",
                "LC_ALL": "C",
                "TZ": "UTC",
            },
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise HostedRunnerError(
            "GIT_INSPECTION_FAILED", "Git invocation failed"
        ) from error
    if completed.returncode != 0:
        raise HostedRunnerError("GIT_INSPECTION_FAILED", "Git rejected identity census")
    return completed.stdout


def _atomic_write_new_or_identical(path: Path, body: bytes, *, mode: int) -> None:
    parent = _ensure_output_directory(path.parent)
    target = parent / path.name
    if target.exists() or target.is_symlink():
        if target.is_symlink() or not target.is_file():
            raise HostedRunnerError("RECEIPT_CONFLICT", target.name)
        if target.read_bytes() == body:
            return
        raise HostedRunnerError("RECEIPT_CONFLICT", "existing receipt bytes differ")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    temporary = Path(temporary_name)
    descriptor_open = True
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as output:
            descriptor_open = False
            output.write(body)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
    finally:
        if descriptor_open:
            try:
                os.close(descriptor)
            except OSError:
                pass
        temporary.unlink(missing_ok=True)


def _bounded_redacted(value: str, limit: int) -> str:
    text = value[:limit]
    for pattern in _SECRET_TEXT_PATTERNS:
        text = pattern.sub("<redacted>", text)
    for pattern in _PRIVATE_PATH_PATTERNS:
        text = pattern.sub(" <private-path>", text)
    return text.replace("\x00", "?")


def _validate_receipt_state(status: object, effect: object) -> None:
    if (status, effect) not in _RECEIPT_STATE_PAIRS:
        raise HostedRunnerError(
            "RECEIPT_INVALID", "status and effect are not one exact semantic state"
        )


def _require_linux_amd64() -> None:
    machine = platform.machine().lower()
    if sys.platform != "linux" or machine not in {"x86_64", "amd64"}:
        raise HostedRunnerError(
            "UNSUPPORTED_PLATFORM", f"{sys.platform}/{machine or 'unknown'}"
        )


def _receipt_staging_path(receipt_path: Path) -> tuple[Path, Path]:
    parent = _ensure_output_directory(Path(receipt_path).parent)
    try:
        directory = Path(tempfile.mkdtemp(prefix=".host-userns-", dir=parent))
        os.chmod(directory, 0o700)
    except OSError as error:
        raise HostedRunnerError(
            "RECEIPT_UNAVAILABLE", "host-policy receipt staging failed"
        ) from error
    return directory, directory / Path(receipt_path).name


def _publish_staged_semantic_receipt(
    staging_path: Path,
    receipt_path: Path,
    request: ExperimentRequest,
    host_userns_policy: HostUsernsPolicyEvidence,
) -> None:
    receipt = load_semantic_receipt(staging_path)
    if receipt.get("request_digest") != request.digest:
        raise HostedRunnerError("RECEIPT_INVALID", "staged request identity differs")
    evidence = receipt.get("evidence")
    if not isinstance(evidence, Mapping):  # pragma: no cover - receipt validator guards
        raise HostedRunnerError("RECEIPT_INVALID", "staged evidence is malformed")
    normalized_evidence = dict(evidence)
    normalized_evidence["host_userns_policy"] = _host_userns_policy_success_evidence(
        host_userns_policy
    )
    write_semantic_receipt(
        receipt_path,
        request=request,
        status=str(receipt["status"]),
        effect=str(receipt["effect"]),
        evidence=normalized_evidence,
    )


def _write_host_userns_policy_failure(
    request: ExperimentRequest,
    receipt_path: Path,
    *,
    phase: str,
    error: HostedRunnerError,
    effect_unknown: bool,
) -> None:
    policy_evidence = error.host_userns_policy_evidence
    if policy_evidence is None:
        policy_evidence = _host_userns_policy_failure_evidence(None)
    write_semantic_receipt(
        receipt_path,
        request=request,
        status="RECONCILIATION_REQUIRED" if effect_unknown else "REFUSED",
        effect="EFFECT_UNKNOWN" if effect_unknown else "NOT_APPLIED",
        evidence={
            "failure": {
                "code": error.code,
                "detail": _bounded_redacted(error.detail, 512),
            },
            "phase": phase,
            "consumer_launch_state": "UNKNOWN" if effect_unknown else "NOT_LAUNCHED",
            "host_userns_policy": policy_evidence,
            "runner": _runner_confounds(),
        },
    )


def reconcile_prior_runs_hosted(
    request: ExperimentRequest,
    *,
    current_run_id: int,
    destination: Path,
    github_output: Path,
    receipt_path: Path,
) -> ReplayResolution:
    """Reconcile through one bounded host-policy window."""

    resolution: ReplayResolution | None = None
    body_error: HostedRunnerError | locks.ToolchainLockError | None = None
    policy_evidence: HostUsernsPolicyEvidence | None = None
    try:
        with github_hosted_userns_policy_window() as observed_policy:
            policy_evidence = observed_policy
            try:
                resolution = reconcile_prior_runs(
                    request,
                    current_run_id=current_run_id,
                    destination=destination,
                    github_output=github_output,
                )
            except (HostedRunnerError, locks.ToolchainLockError) as error:
                body_error = error
    except HostedRunnerError as policy_error:
        _write_host_userns_policy_failure(
            request,
            receipt_path,
            phase="P",
            error=policy_error,
            effect_unknown=False,
        )
        raise
    if body_error is not None:
        if policy_evidence is None:  # pragma: no cover - context entry gates the body
            raise HostedRunnerError(
                "HOST_USERNS_POLICY_UNAVAILABLE", "policy evidence is unavailable"
            )
        _write_phase_p_refusal(
            request,
            receipt_path,
            code=body_error.code,
            detail=_bounded_redacted(body_error.detail, 512),
            host_userns_policy=policy_evidence,
        )
        raise body_error
    if resolution is None:  # pragma: no cover - exhaustive state guard
        raise HostedRunnerError("REPLAY_LOOKUP_INVALID", "replay returned no result")
    return resolution


def prepare_phase_p_hosted(
    forge_root: Path,
    request: ExperimentRequest,
    *,
    scratch_root: Path,
    output_directory: Path,
    github_output: Path,
    receipt_path: Path,
) -> Mapping[str, Any]:
    """Run Phase P and publish a receipt only after exact host restoration."""

    staging_directory, staging_receipt = _receipt_staging_path(receipt_path)
    result: Mapping[str, Any] | None = None
    body_error: HostedRunnerError | locks.ToolchainLockError | None = None
    policy_evidence: HostUsernsPolicyEvidence | None = None
    try:
        try:
            with github_hosted_userns_policy_window() as observed_policy:
                policy_evidence = observed_policy
                try:
                    result = prepare_phase_p_or_record_refusal(
                        forge_root,
                        request,
                        scratch_root=scratch_root,
                        output_directory=output_directory,
                        github_output=github_output,
                        receipt_path=staging_receipt,
                    )
                except (HostedRunnerError, locks.ToolchainLockError) as error:
                    body_error = error
        except HostedRunnerError as policy_error:
            _write_host_userns_policy_failure(
                request,
                receipt_path,
                phase="P",
                error=policy_error,
                effect_unknown=False,
            )
            raise
        if staging_receipt.exists():
            if policy_evidence is None:  # pragma: no cover - staged inside context
                raise HostedRunnerError(
                    "HOST_USERNS_POLICY_UNAVAILABLE", "policy evidence is unavailable"
                )
            _publish_staged_semantic_receipt(
                staging_receipt,
                receipt_path,
                request,
                policy_evidence,
            )
        if body_error is not None:
            raise body_error
        if result is None:  # pragma: no cover - exhaustive state guard
            raise HostedRunnerError("PHASE_P_FAILED", "Phase P returned no result")
        return result
    finally:
        shutil.rmtree(staging_directory, ignore_errors=True)


def _phase_e_namespace_probe() -> subprocess.CompletedProcess[str]:
    return _invoke_phase_p_boundary(
        [
            "/usr/bin/unshare",
            "--user",
            "--map-root-user",
            "--mount",
            "--net",
            "--",
            "/usr/bin/env",
            "-i",
            "PATH=/usr/bin:/bin",
            "/bin/bash",
            "--noprofile",
            "--norc",
            "-euo",
            "pipefail",
            "-c",
            "/bin/mount --make-rprivate / && /usr/sbin/ip link set lo up",
        ],
        cwd="/",
        env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
        close_fds=True,
        pass_fds=(),
        start_new_session=True,
    )


def probe_phase_e_hosted(request: ExperimentRequest, *, receipt_path: Path) -> None:
    """Prove Phase-E namespace support after a reversible host prelude."""

    completed: subprocess.CompletedProcess[str] | None = None
    invocation_error: OSError | subprocess.TimeoutExpired | None = None
    policy_evidence: HostUsernsPolicyEvidence | None = None
    try:
        with github_hosted_userns_policy_window() as observed_policy:
            policy_evidence = observed_policy
            try:
                completed = _phase_e_namespace_probe()
            except (OSError, subprocess.TimeoutExpired) as error:
                invocation_error = error
    except HostedRunnerError as policy_error:
        _write_host_userns_policy_failure(
            request,
            receipt_path,
            phase="E",
            error=policy_error,
            effect_unknown=False,
        )
        raise
    if invocation_error is not None or completed is None or completed.returncode != 0:
        if policy_evidence is None:  # pragma: no cover - probe ran inside context
            raise HostedRunnerError(
                "HOST_USERNS_POLICY_UNAVAILABLE", "policy evidence is unavailable"
            )
        write_network_seal_boundary_receipt(
            request,
            receipt_path,
            effect_unknown=False,
            host_userns_policy=policy_evidence,
        )
        raise HostedRunnerError(
            "NETWORK_SEAL_UNAVAILABLE", "user and network namespace probe failed"
        ) from invocation_error


def _phase_e_namespace_command(
    *,
    forge_root: Path,
    consumer_root: Path,
    request_path: Path,
    bundle_path: Path,
    bundle_sha256: str,
    sealed_home: Path,
    scratch_root: Path,
    result_directory: Path,
    receipt_path: Path,
) -> list[str]:
    layout = _consumer_git_seal_layout(consumer_root)
    roots = {row.role: row for row in layout.roots}
    consumer = roots["consumer_source"].path
    for external in (
        sealed_home,
        sealed_home / "tmp",
        scratch_root,
        result_directory,
        receipt_path.parent,
        bundle_path.parent,
        request_path.parent,
    ):
        for sealed in layout.unique_roots:
            _require_outside_consumer_root(external, sealed.path)
    inner_environment = {
        "HOME": os.fspath(sealed_home),
        "TMPDIR": os.fspath(sealed_home / "tmp"),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        "PYTHONHASHSEED": "0",
        "RUNNER_OS": os.environ.get("RUNNER_OS", "UNAVAILABLE"),
        "RUNNER_ARCH": os.environ.get("RUNNER_ARCH", "UNAVAILABLE"),
        "ImageOS": os.environ.get("ImageOS", "UNAVAILABLE"),
        "ImageVersion": os.environ.get("ImageVersion", "UNAVAILABLE"),
        "FORGE_ROOT": os.fspath(forge_root),
        "CONSUMER_ROOT": os.fspath(consumer),
        "CONSUMER_ROOT_EXPECTED": (
            f"{roots['consumer_source'].device}:{roots['consumer_source'].inode}"
        ),
        "CONSUMER_ROOT_SEAL_ID": roots["consumer_source"].seal_id,
        "CONSUMER_GIT_DIR": os.fspath(roots["git_worktree_dir"].path),
        "CONSUMER_GIT_DIR_EXPECTED": (
            f"{roots['git_worktree_dir'].device}:{roots['git_worktree_dir'].inode}"
        ),
        "CONSUMER_GIT_DIR_SEAL_ID": roots["git_worktree_dir"].seal_id,
        "CONSUMER_GIT_COMMON_DIR": os.fspath(roots["git_common_dir"].path),
        "CONSUMER_GIT_COMMON_DIR_EXPECTED": (
            f"{roots['git_common_dir'].device}:{roots['git_common_dir'].inode}"
        ),
        "CONSUMER_GIT_COMMON_DIR_SEAL_ID": roots["git_common_dir"].seal_id,
        "REQUEST_PATH": os.fspath(request_path),
        "BUNDLE_PATH": os.fspath(bundle_path),
        "BUNDLE_SHA256": bundle_sha256,
        "SCRATCH_PATH": os.fspath(scratch_root),
        "RESULT_PATH": os.fspath(result_directory),
        "RECEIPT_PATH": os.fspath(receipt_path),
    }
    if any(
        "\x00" in key or "\x00" in value for key, value in inner_environment.items()
    ):
        raise HostedRunnerError("INVALID_ARGV", "Phase E environment is malformed")
    environment_argv = [f"{key}={value}" for key, value in inner_environment.items()]
    return [
        "/usr/bin/unshare",
        "--user",
        "--map-root-user",
        "--mount",
        "--net",
        "--",
        "/usr/bin/env",
        "-i",
        *environment_argv,
        "/bin/bash",
        "--noprofile",
        "--norc",
        "-euo",
        "pipefail",
        "-c",
        """
/usr/sbin/ip link set lo up
set -E
record_seal_refusal() {
  trap - ERR
  /usr/bin/python3 "$FORGE_ROOT/experiments/codeintel_supply/hosted_runner.py" \
    record-phase-e-seal-refusal \
    --request "$REQUEST_PATH" \
    --receipt "$RECEIPT_PATH" || true
  exit 1
}
trap record_seal_refusal ERR
/bin/mount --make-rprivate /
seal_root() {
  local target="$1"
  local expected="$2"
  local before
  local after
  before="$(/usr/bin/python3 -c 'import os,sys; value=os.stat(sys.argv[1]); print(f"{value.st_dev}:{value.st_ino}")' "$target")"
  test "$before" = "$expected"
  /bin/mount --bind "$target" "$target"
  /bin/mount -o remount,bind,ro,nosuid,nodev,noexec "$target"
  after="$(/usr/bin/python3 -c 'import os,sys; value=os.stat(sys.argv[1]); print(f"{value.st_dev}:{value.st_ino}")' "$target")"
  test "$after" = "$expected"
  /usr/bin/python3 - "$target" <<'PY'
import errno
import os
import sys

target = sys.argv[1]
if not os.statvfs(target).f_flag & os.ST_RDONLY:
    raise SystemExit("sealed root lacks ST_RDONLY")
probe = os.path.join(target, ".codeintel-read-only-probe")
try:
    descriptor = os.open(probe, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except OSError as error:
    if error.errno != errno.EROFS:
        raise
else:
    os.close(descriptor)
    os.unlink(probe)
    raise SystemExit("sealed-root write unexpectedly succeeded")
PY
}
seal_root "$CONSUMER_ROOT" "$CONSUMER_ROOT_EXPECTED"
if test "$CONSUMER_GIT_COMMON_DIR_SEAL_ID" != "$CONSUMER_ROOT_SEAL_ID"; then
  seal_root "$CONSUMER_GIT_COMMON_DIR" "$CONSUMER_GIT_COMMON_DIR_EXPECTED"
fi
if test "$CONSUMER_GIT_DIR_SEAL_ID" != "$CONSUMER_ROOT_SEAL_ID" && \
   test "$CONSUMER_GIT_DIR_SEAL_ID" != "$CONSUMER_GIT_COMMON_DIR_SEAL_ID"; then
  seal_root "$CONSUMER_GIT_DIR" "$CONSUMER_GIT_DIR_EXPECTED"
fi
/usr/bin/mkdir -p -m 700 "$TMPDIR"
trap - ERR
exec /usr/bin/python3 "$FORGE_ROOT/experiments/codeintel_supply/hosted_runner.py" \
  run-phase-e \
  --forge-root "$FORGE_ROOT" \
  --consumer-root "$CONSUMER_ROOT" \
  --request "$REQUEST_PATH" \
  --bundle "$BUNDLE_PATH" \
  --bundle-sha256 "$BUNDLE_SHA256" \
  --scratch "$SCRATCH_PATH" \
  --result-directory "$RESULT_PATH" \
  --receipt "$RECEIPT_PATH"
""".strip(),
    ]


def run_phase_e_hosted(
    forge_root: Path,
    consumer_root: Path,
    request: ExperimentRequest,
    *,
    request_path: Path,
    bundle_path: Path,
    bundle_sha256: str,
    sealed_home: Path,
    scratch_root: Path,
    result_directory: Path,
    receipt_path: Path,
) -> None:
    """Invoke the fixed sealed child and accept its receipt only after restore."""

    home = _fresh_directory(sealed_home, "SEALED_HOME_CONFLICT")
    staging_directory, staging_receipt = _receipt_staging_path(receipt_path)
    attempted = False
    completed: subprocess.CompletedProcess[str] | None = None
    invocation_error: OSError | subprocess.TimeoutExpired | None = None
    policy_evidence: HostUsernsPolicyEvidence | None = None
    try:
        try:
            with github_hosted_userns_policy_window() as observed_policy:
                policy_evidence = observed_policy
                command = _phase_e_namespace_command(
                    forge_root=forge_root,
                    consumer_root=consumer_root,
                    request_path=request_path,
                    bundle_path=bundle_path,
                    bundle_sha256=bundle_sha256,
                    sealed_home=home,
                    scratch_root=scratch_root,
                    result_directory=result_directory,
                    receipt_path=staging_receipt,
                )
                attempted = True
                try:
                    completed = _invoke_phase_p_boundary(
                        command,
                        cwd=os.fspath(forge_root),
                        env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
                        check=False,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=1_100,
                        close_fds=True,
                        pass_fds=(),
                        start_new_session=True,
                    )
                except (OSError, subprocess.TimeoutExpired) as error:
                    invocation_error = error
        except HostedRunnerError as policy_error:
            _write_host_userns_policy_failure(
                request,
                receipt_path,
                phase="E",
                error=policy_error,
                effect_unknown=attempted,
            )
            raise

        receipt_missing = not staging_receipt.exists()
        if not receipt_missing:
            if policy_evidence is None:  # pragma: no cover - launch context gate
                raise HostedRunnerError(
                    "HOST_USERNS_POLICY_UNAVAILABLE", "policy evidence is unavailable"
                )
            _publish_staged_semantic_receipt(
                staging_receipt,
                receipt_path,
                request,
                policy_evidence,
            )
        else:
            if policy_evidence is None:  # pragma: no cover - launch context gate
                raise HostedRunnerError(
                    "HOST_USERNS_POLICY_UNAVAILABLE", "policy evidence is unavailable"
                )
            write_network_seal_boundary_receipt(
                request,
                receipt_path,
                effect_unknown=attempted,
                host_userns_policy=policy_evidence,
            )
        if receipt_missing:
            raise HostedRunnerError(
                "NETWORK_SEAL_EFFECT_UNKNOWN",
                "sealed child exited without a durable semantic receipt",
            )
        if invocation_error is not None:
            raise HostedRunnerError(
                "NETWORK_SEAL_EFFECT_UNKNOWN",
                "sealed child process could not be reconciled",
            ) from invocation_error
        if completed is None:
            raise HostedRunnerError(
                "NETWORK_SEAL_UNAVAILABLE", "sealed child did not start"
            )
        if completed.returncode != 0:
            raise HostedRunnerError(
                "SEALED_PHASE_E_FAILED",
                f"sealed child returned known code {completed.returncode}",
            )
    finally:
        shutil.rmtree(staging_directory, ignore_errors=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    derive = commands.add_parser("derive-request")
    derive.add_argument("--forge-root", type=Path, required=True)
    derive.add_argument("--operation-key", required=True)
    derive.add_argument("--consumer-sha", required=True)
    derive.add_argument("--consumer-tree-sha", required=True)
    derive.add_argument("--output", type=Path, required=True)
    derive.add_argument("--github-output", type=Path)

    reconcile = commands.add_parser("reconcile-prior-runs")
    reconcile.add_argument("--request", type=Path, required=True)
    reconcile.add_argument("--current-run-id", type=int, required=True)
    reconcile.add_argument("--destination", type=Path, required=True)
    reconcile.add_argument("--github-output", type=Path, required=True)
    reconcile.add_argument("--receipt", type=Path, required=True)

    phase_p = commands.add_parser("phase-p")
    phase_p.add_argument("--forge-root", type=Path, required=True)
    phase_p.add_argument("--request", type=Path, required=True)
    phase_p.add_argument("--scratch", type=Path, required=True)
    phase_p.add_argument("--output", type=Path, required=True)
    phase_p.add_argument("--github-output", type=Path, required=True)
    phase_p.add_argument("--receipt", type=Path, required=True)

    verify = commands.add_parser("verify-bundle")
    verify.add_argument("--bundle", type=Path, required=True)
    verify.add_argument("--sha256", required=True)

    phase_e = commands.add_parser("run-phase-e")
    phase_e.add_argument("--forge-root", type=Path, required=True)
    phase_e.add_argument("--consumer-root", type=Path, required=True)
    phase_e.add_argument("--request", type=Path, required=True)
    phase_e.add_argument("--bundle", type=Path, required=True)
    phase_e.add_argument("--bundle-sha256", required=True)
    phase_e.add_argument("--scratch", type=Path, required=True)
    phase_e.add_argument("--result-directory", type=Path, required=True)
    phase_e.add_argument("--receipt", type=Path, required=True)

    phase_e_probe = commands.add_parser("probe-phase-e-hosted")
    phase_e_probe.add_argument("--request", type=Path, required=True)
    phase_e_probe.add_argument("--receipt", type=Path, required=True)

    phase_e_hosted = commands.add_parser("run-phase-e-hosted")
    phase_e_hosted.add_argument("--forge-root", type=Path, required=True)
    phase_e_hosted.add_argument("--consumer-root", type=Path, required=True)
    phase_e_hosted.add_argument("--request", type=Path, required=True)
    phase_e_hosted.add_argument("--bundle", type=Path, required=True)
    phase_e_hosted.add_argument("--bundle-sha256", required=True)
    phase_e_hosted.add_argument("--sealed-home", type=Path, required=True)
    phase_e_hosted.add_argument("--scratch", type=Path, required=True)
    phase_e_hosted.add_argument("--result-directory", type=Path, required=True)
    phase_e_hosted.add_argument("--receipt", type=Path, required=True)

    seal_refusal = commands.add_parser("record-network-seal-refusal")
    seal_refusal.add_argument("--request", type=Path, required=True)
    seal_refusal.add_argument("--receipt", type=Path, required=True)

    seal_unknown = commands.add_parser("record-network-seal-effect-unknown")
    seal_unknown.add_argument("--request", type=Path, required=True)
    seal_unknown.add_argument("--receipt", type=Path, required=True)

    phase_e_seal_refusal = commands.add_parser("record-phase-e-seal-refusal")
    phase_e_seal_refusal.add_argument("--request", type=Path, required=True)
    phase_e_seal_refusal.add_argument("--receipt", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "derive-request":
            request = derive_request(
                arguments.forge_root,
                operation_key=arguments.operation_key,
                consumer_sha=arguments.consumer_sha,
                consumer_tree_sha=arguments.consumer_tree_sha,
            )
            _atomic_write_new_or_identical(
                arguments.output, request.canonical_bytes + b"\n", mode=0o600
            )
            if arguments.github_output is not None:
                _append_github_outputs(
                    arguments.github_output,
                    {
                        "request_digest": request.digest,
                        "run_name": workflow_run_name(request),
                    },
                )
        elif arguments.command == "reconcile-prior-runs":
            request = load_request(arguments.request)
            reconcile_prior_runs_hosted(
                request,
                current_run_id=arguments.current_run_id,
                destination=arguments.destination,
                github_output=arguments.github_output,
                receipt_path=arguments.receipt,
            )
        elif arguments.command == "phase-p":
            _require_linux_amd64()
            prepare_phase_p_hosted(
                arguments.forge_root,
                load_request(arguments.request),
                scratch_root=arguments.scratch,
                output_directory=arguments.output,
                github_output=arguments.github_output,
                receipt_path=arguments.receipt,
            )
        elif arguments.command == "verify-bundle":
            _require_linux_amd64()
            verified = verify_bundle(arguments.bundle, expected_sha256=arguments.sha256)
            print(
                json.dumps(
                    {
                        "bundle_sha256": verified.sha256,
                        "manifest_sha256": verified.manifest_sha256,
                        "size": verified.size,
                    },
                    sort_keys=True,
                )
            )
        elif arguments.command == "run-phase-e":
            _require_linux_amd64()
            run_phase_e(
                arguments.forge_root,
                arguments.consumer_root,
                load_request(arguments.request),
                bundle_path=arguments.bundle,
                bundle_sha256=arguments.bundle_sha256,
                scratch_root=arguments.scratch,
                result_directory=arguments.result_directory,
                receipt_path=arguments.receipt,
            )
        elif arguments.command == "probe-phase-e-hosted":
            _require_linux_amd64()
            probe_phase_e_hosted(
                load_request(arguments.request), receipt_path=arguments.receipt
            )
        elif arguments.command == "run-phase-e-hosted":
            _require_linux_amd64()
            run_phase_e_hosted(
                arguments.forge_root,
                arguments.consumer_root,
                load_request(arguments.request),
                request_path=arguments.request,
                bundle_path=arguments.bundle,
                bundle_sha256=arguments.bundle_sha256,
                sealed_home=arguments.sealed_home,
                scratch_root=arguments.scratch,
                result_directory=arguments.result_directory,
                receipt_path=arguments.receipt,
            )
        elif arguments.command == "record-network-seal-refusal":
            write_network_seal_boundary_receipt(
                load_request(arguments.request),
                arguments.receipt,
                effect_unknown=False,
            )
        elif arguments.command == "record-network-seal-effect-unknown":
            write_network_seal_boundary_receipt(
                load_request(arguments.request),
                arguments.receipt,
                effect_unknown=True,
            )
        elif arguments.command == "record-phase-e-seal-refusal":
            write_phase_e_seal_refusal(
                load_request(arguments.request), arguments.receipt
            )
        else:  # pragma: no cover - argparse is exhaustive
            raise HostedRunnerError("INVALID_COMMAND", str(arguments.command))
    except (HostedRunnerError, locks.ToolchainLockError) as error:
        print(
            f"{getattr(error, 'code', 'RUNNER_FAILED')}: "
            f"{_bounded_redacted(getattr(error, 'detail', str(error)), 1024)}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
