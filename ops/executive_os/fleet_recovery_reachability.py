#!/usr/bin/env python3
"""Read-only lead-host recovery reachability probe for the four home Mac minis.

This observer is deliberately separate from host_recovery_readiness.py.  The
local readiness contract proves whether one Mac is physically capable of
unattended recovery; this probe proves whether the established M2 fleet gateway
can actually reach that recovery surface.

It performs no host mutation, credential write, key generation, service
restart, or persistence.  The host set, SSH aliases, expected users, gateway
public-key path/fingerprint, and probed ports are closed source constants.
Only bounded classifications are emitted; raw SSH stderr is never returned.
"""
from __future__ import annotations

import base64
import hashlib
import json
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence


SCHEMA = "mastermind.fleet_recovery_reachability/v1"
EXPECTED_GATEWAY_FINGERPRINT = (
    "SHA256:lgLmcaeG4Zv9rnKwfTBaC1KFNTZsRQ0I2r1Zyro9aRg"
)
GATEWAY_KEY_BASENAME = "mastermind_fleet_gateway_ed25519"
SSH = "/usr/bin/ssh"
TCP_TIMEOUT_SECONDS = 2.0
SSH_TIMEOUT_SECONDS = 8

HOSTS = (
    ("mini1", "mmx-mini1", "mini1"),
    ("mini2", "mmx-mini2", "mini2"),
    ("mini3", "mmx-mini3", "mini3"),
    ("mini4", "mmx-mini4", "mini4"),
)
PROBE_PORTS = {
    "ssh": 22,
    "screen_sharing": 5900,
    "apple_remote_desktop": 3283,
}

_ALLOWED_AUTH_CODES = frozenset(
    {
        "PASS",
        "KEY_REJECTED",
        "HOST_IDENTITY_REJECTED",
        "TRANSPORT_UNAVAILABLE",
        "TIMEOUT",
        "PROBE_ERROR",
    }
)
_ALLOWED_TCP_CODES = frozenset({"OPEN", "CLOSED", "UNAVAILABLE", "TIMEOUT"})


class ReachabilityProbeError(RuntimeError):
    """Closed local probe refusal without raw external output."""


@dataclass(frozen=True)
class SshConfig:
    alias: str
    hostname: str
    user: str
    identity_file: str
    identities_only: bool


@dataclass(frozen=True)
class SshAuthObservation:
    code: str
    methods: tuple[str, ...]


def _fingerprint_public_key(path: Path) -> str:
    try:
        line = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise ReachabilityProbeError("GATEWAY_PUBLIC_KEY_UNAVAILABLE") from exc
    fields = line.split()
    if len(fields) < 2 or fields[0] != "ssh-ed25519":
        raise ReachabilityProbeError("GATEWAY_PUBLIC_KEY_INVALID")
    try:
        blob = base64.b64decode(fields[1], validate=True)
    except ValueError as exc:
        raise ReachabilityProbeError("GATEWAY_PUBLIC_KEY_INVALID") from exc
    digest = base64.b64encode(hashlib.sha256(blob).digest()).decode("ascii").rstrip("=")
    return f"SHA256:{digest}"


def _closed_env(home: Path) -> dict[str, str]:
    return {
        "HOME": str(home),
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "C",
        "LC_ALL": "C",
    }


def _resolve_ssh_config(
    alias: str,
    *,
    home: Path,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> SshConfig:
    try:
        completed = runner(
            [SSH, "-G", alias],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=SSH_TIMEOUT_SECONDS,
            env=_closed_env(home),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReachabilityProbeError("SSH_CONFIG_UNAVAILABLE") from exc
    if completed.returncode != 0 or len(completed.stdout) > 256 * 1024:
        raise ReachabilityProbeError("SSH_CONFIG_UNAVAILABLE")
    try:
        text = completed.stdout.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise ReachabilityProbeError("SSH_CONFIG_INVALID") from exc

    values: dict[str, list[str]] = {}
    for raw in text.splitlines():
        if " " not in raw:
            continue
        key, value = raw.split(" ", 1)
        key = key.strip().lower()
        value = value.strip()
        if key in {"hostname", "user", "identityfile", "identitiesonly"}:
            values.setdefault(key, []).append(value)

    def exactly_one(key: str) -> str:
        rows = values.get(key, [])
        if len(rows) != 1 or not rows[0]:
            raise ReachabilityProbeError("SSH_CONFIG_INVALID")
        return rows[0]

    return SshConfig(
        alias=alias,
        hostname=exactly_one("hostname"),
        user=exactly_one("user"),
        identity_file=exactly_one("identityfile"),
        identities_only=exactly_one("identitiesonly").lower() == "yes",
    )


def _normalize_identity_file(value: str, home: Path) -> Path:
    if value.startswith("~/"):
        return home / value[2:]
    path = Path(value)
    if not path.is_absolute():
        raise ReachabilityProbeError("SSH_IDENTITY_PATH_INVALID")
    return path


def _probe_tcp(hostname: str, port: int) -> str:
    try:
        with socket.create_connection((hostname, port), timeout=TCP_TIMEOUT_SECONDS):
            return "OPEN"
    except socket.timeout:
        return "TIMEOUT"
    except ConnectionRefusedError:
        return "CLOSED"
    except OSError:
        return "UNAVAILABLE"


def _parse_auth_methods(stderr: bytes) -> tuple[str, ...]:
    sample = stderr[:16384].decode("utf-8", errors="replace").lower()
    methods: set[str] = set()
    marker = "authentications that can continue:"
    for raw in sample.splitlines():
        if marker not in raw:
            continue
        _, values = raw.split(marker, 1)
        for value in values.strip().split(","):
            token = value.strip()
            if token in {"publickey", "password", "keyboard-interactive"}:
                methods.add(token)
    return tuple(sorted(methods))


def _classify_ssh_failure(returncode: int, stderr: bytes) -> str:
    if returncode == 0:
        return "PASS"
    sample = stderr[:8192].decode("utf-8", errors="replace").lower()
    if "permission denied" in sample:
        return "KEY_REJECTED"
    if (
        "host key verification failed" in sample
        or "remote host identification has changed" in sample
        or "no matching host key" in sample
    ):
        return "HOST_IDENTITY_REJECTED"
    if (
        "connection refused" in sample
        or "no route to host" in sample
        or "could not resolve hostname" in sample
        or "network is unreachable" in sample
    ):
        return "TRANSPORT_UNAVAILABLE"
    if "connection timed out" in sample or "operation timed out" in sample:
        return "TIMEOUT"
    return "PROBE_ERROR"


def _probe_ssh_key_auth(
    config: SshConfig,
    *,
    home: Path,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> SshAuthObservation:
    known_hosts = home / ".ssh" / "known_hosts"
    try:
        completed = runner(
            [
                SSH,
                "-v",
                "-o", "BatchMode=yes",
                "-o", "NumberOfPasswordPrompts=0",
                "-o", "PasswordAuthentication=no",
                "-o", "KbdInteractiveAuthentication=no",
                "-o", "ChallengeResponseAuthentication=no",
                "-o", "PubkeyAuthentication=yes",
                "-o", "IdentitiesOnly=yes",
                "-o", "IdentityAgent=none",
                "-o", "StrictHostKeyChecking=yes",
                "-o", f"UserKnownHostsFile={known_hosts}",
                "-o", f"ConnectTimeout={SSH_TIMEOUT_SECONDS - 2}",
                config.alias,
                "/usr/bin/true",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
            timeout=SSH_TIMEOUT_SECONDS,
            env=_closed_env(home),
        )
    except subprocess.TimeoutExpired:
        return SshAuthObservation("TIMEOUT", ())
    except OSError:
        return SshAuthObservation("PROBE_ERROR", ())
    return SshAuthObservation(
        _classify_ssh_failure(completed.returncode, completed.stderr),
        _parse_auth_methods(completed.stderr),
    )


def observe(
    *,
    home: Path | None = None,
    resolver: Callable[..., SshConfig] = _resolve_ssh_config,
    tcp_probe: Callable[[str, int], str] = _probe_tcp,
    auth_probe: Callable[..., SshAuthObservation] = _probe_ssh_key_auth,
    now_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
) -> dict[str, Any]:
    home = Path.home() if home is None else home
    public_key = home / ".ssh" / f"{GATEWAY_KEY_BASENAME}.pub"
    fingerprint = _fingerprint_public_key(public_key)
    if fingerprint != EXPECTED_GATEWAY_FINGERPRINT:
        raise ReachabilityProbeError("GATEWAY_KEY_IDENTITY_MISMATCH")

    hosts: dict[str, dict[str, Any]] = {}
    degraded: list[str] = []
    for name, alias, expected_user in HOSTS:
        try:
            config = resolver(alias, home=home)
            identity = _normalize_identity_file(config.identity_file, home)
            config_ok = (
                config.user == expected_user
                and config.hostname == f"{name}.local"
                and config.identities_only
                and identity == home / ".ssh" / GATEWAY_KEY_BASENAME
            )
        except ReachabilityProbeError:
            config = None
            config_ok = False

        if config is None or not config_ok:
            row = {
                "alias": alias,
                "hostname": f"{name}.local",
                "ssh_config": "INVALID",
                "ssh_listener": "UNAVAILABLE",
                "ssh_key_auth": "PROBE_ERROR",
                "ssh_auth_methods": [],
                "screen_sharing": "UNAVAILABLE",
                "apple_remote_desktop": "UNAVAILABLE",
                "recovery_state": "DEGRADED",
                "preboot_suspected": False,
                "issues": ["SSH_CONFIG_INVALID"],
            }
        else:
            tcp = {
                label: tcp_probe(config.hostname, port)
                for label, port in PROBE_PORTS.items()
            }
            if any(value not in _ALLOWED_TCP_CODES for value in tcp.values()):
                raise ReachabilityProbeError("TCP_PROBE_INVALID")
            auth = auth_probe(config, home=home)
            if (
                not isinstance(auth, SshAuthObservation)
                or auth.code not in _ALLOWED_AUTH_CODES
            ):
                raise ReachabilityProbeError("SSH_AUTH_PROBE_INVALID")

            issues: list[str] = []
            if tcp["ssh"] != "OPEN":
                issues.append("SSH_LISTENER_UNREACHABLE")
            if auth.code != "PASS":
                issues.append(f"SSH_KEY_AUTH_{auth.code}")
            if tcp["screen_sharing"] != "OPEN":
                issues.append("SCREEN_SHARING_UNREACHABLE")
            if tcp["apple_remote_desktop"] != "OPEN":
                issues.append("APPLE_REMOTE_DESKTOP_UNREACHABLE")

            password_methods = {"password", "keyboard-interactive"}
            preboot_suspected = (
                tcp["ssh"] == "OPEN"
                and auth.code == "KEY_REJECTED"
                and password_methods.issubset(set(auth.methods))
                and tcp["screen_sharing"] != "OPEN"
                and tcp["apple_remote_desktop"] != "OPEN"
            )
            if preboot_suspected:
                issues.append("FILEVAULT_PREBOOT_SUSPECTED")

            # Exact rescue-key authentication is the load-bearing normal-boot
            # recovery path.  GUI reachability is an independent redundant
            # avenue.  A password-capable SSH server that rejects the gateway
            # key while GUI services are absent is reported as a FileVault
            # preboot *suspect*, never misclassified as deleted authorized_keys.
            ready = (
                tcp["ssh"] == "OPEN"
                and auth.code == "PASS"
                and (
                    tcp["screen_sharing"] == "OPEN"
                    or tcp["apple_remote_desktop"] == "OPEN"
                )
            )
            row = {
                "alias": alias,
                "hostname": config.hostname,
                "ssh_config": "VALID",
                "ssh_listener": tcp["ssh"],
                "ssh_key_auth": auth.code,
                "ssh_auth_methods": list(auth.methods),
                "screen_sharing": tcp["screen_sharing"],
                "apple_remote_desktop": tcp["apple_remote_desktop"],
                "recovery_state": "READY" if ready else "DEGRADED",
                "preboot_suspected": preboot_suspected,
                "issues": issues,
            }

        hosts[name] = row
        if row["recovery_state"] != "READY":
            degraded.append(name)

    return {
        "schema": SCHEMA,
        "observed_at_ms": int(now_ms()),
        "gateway_key_fingerprint": fingerprint,
        "state": "READY" if not degraded else "DEGRADED",
        "degraded_hosts": degraded,
        "hosts": hosts,
    }


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if values:
        sys.stderr.write("fleet recovery reachability probe accepts no arguments\n")
        return 64
    try:
        report = observe()
    except ReachabilityProbeError as exc:
        sys.stdout.write(
            json.dumps(
                {"schema": SCHEMA, "state": "REFUSED", "code": str(exc)},
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        return 65
    sys.stdout.write(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n")
    return 0 if report["state"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
