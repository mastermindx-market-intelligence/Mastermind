"""Fresh, secret-free PID1 status from the existing supervisor process.

This publisher labels configuration observations; it never attests installed
source, credentials, service health or model use. The host observer separately
requires its installation owner's source/runtime/unit/current-process proof.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import socket
import sys
import time

from common.hermes_role_status_contract import (
    ROLES, STATUS_SCHEMA, encode_status_text,
)
from integrations.hermes_harness.metadata import role_metadata

from .errors import RuntimeRefusal
from .profile import RuntimeProfile

IMPLEMENTATION_ENV = "MM_HERMES_IMPLEMENTATION_SHA"
PUBLICATION_INTERVAL_SECONDS = 5.0
_SHA = re.compile(r"[0-9a-f]{40}")
_INVOCATION = re.compile(r"[0-9a-f]{32}")
_BOOT = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")


def _context_refusal():
    return RuntimeRefusal("ROLE_STATUS_CONTEXT_INVALID")


def _notification_address(value: str) -> str:
    if (type(value) is not str or len(value) < 2 or value[0] not in {"/", "@"}
            or any(character in value for character in "\x00\r\n")):
        raise _context_refusal()
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeError:
        raise _context_refusal() from None
    if len(encoded) > 107:
        raise _context_refusal()
    return "\0" + value[1:] if value.startswith("@") else value


def _read_boot_id() -> str:
    try:
        with Path("/proc/sys/kernel/random/boot_id").open("rb") as stream:
            value = stream.read(64).decode("ascii").removesuffix("\n")
    except (OSError, UnicodeError):
        raise _context_refusal() from None
    if _BOOT.fullmatch(value) is None:
        raise _context_refusal()
    return value


@dataclass(frozen=True)
class RoleStatusPublisher:
    role: str
    state_dir: Path
    implementation_sha: str
    host_boot_id: str
    invocation_id: str
    process_pid: int
    notify_socket: str

    def __post_init__(self):
        if (self.role not in ROLES or not isinstance(self.state_dir, Path)
                or not self.state_dir.is_absolute()
                or type(self.implementation_sha) is not str or _SHA.fullmatch(self.implementation_sha) is None
                or type(self.host_boot_id) is not str or _BOOT.fullmatch(self.host_boot_id) is None
                or type(self.invocation_id) is not str or _INVOCATION.fullmatch(self.invocation_id) is None
                or self.invocation_id == "0" * 32
                or type(self.process_pid) is not int or self.process_pid <= 0):
            raise _context_refusal()
        _notification_address(self.notify_socket)

    def publish(self) -> bool:
        """One new read and bounded datagram; local send is not PID1 acceptance."""
        if os.getpid() != self.process_pid:
            return False
        try:
            # Time the start of this fresh acquisition. A slow read cannot
            # re-date old metadata as though it had just been acquired.
            wall_ms = time.time_ns() // 1_000_000
            monotonic_ms = time.monotonic_ns() // 1_000_000
            metadata = role_metadata(self.state_dir, self.role)
            text = encode_status_text({
                "schema": STATUS_SCHEMA, "role": self.role,
                "host_boot_id": self.host_boot_id, "invocation_id": self.invocation_id,
                "implementation_sha": self.implementation_sha,
                "observed_at_ms": wall_ms, "observed_monotonic_ms": monotonic_ms,
                "metadata": metadata,
            })
            payload = ("STATUS=" + text).encode("ascii")
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as channel:
                channel.set_inheritable(False)
                channel.setblocking(False)
                return channel.sendto(payload, _notification_address(self.notify_socket)) == len(payload)
        except Exception:
            # Publication must never restart the model child, expose exception
            # text, retry, or refresh the last successful document on failure.
            return False


def publisher_from_process(profile: RuntimeProfile) -> RoleStatusPublisher | None:
    """Optional unit label plus actual process context, never source admission.

    The caller must already have passed the existing root-cgroup, role-network,
    credential-isolation and TCP-policy guards. It calls this before secrets.
    Missing optional label performs no boot read, metadata read or send.
    """
    implementation = os.environ.get(IMPLEMENTATION_ENV)
    if implementation is None:
        return None
    if (sys.platform != "linux" or type(profile) is not RuntimeProfile
            or profile.role not in ROLES or _SHA.fullmatch(implementation) is None):
        raise _context_refusal()
    invocation = os.environ.get("INVOCATION_ID", "")
    address = os.environ.get("NOTIFY_SOCKET", "")
    if _INVOCATION.fullmatch(invocation) is None or invocation == "0" * 32:
        raise _context_refusal()
    _notification_address(address)
    pid = os.getpid()
    manager_pid = os.environ.get("SYSTEMD_EXEC_PID")
    if manager_pid is not None and manager_pid != str(pid):
        raise _context_refusal()
    return RoleStatusPublisher(profile.role, profile.state_dir, implementation,
                               _read_boot_id(), invocation, pid, address)
