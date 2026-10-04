"""Read-only external recovery-route readiness probe.

This probe answers a deliberately narrower question than
host_recovery_readiness.py: from the operator machine, can an already-known
SSH recovery identity traverse one already-known gateway and reach one target
Mac over SSH?

It never unlocks FileVault, prompts for a password, edits SSH configuration,
adds host keys, changes routes, starts services, or persists state. Both hops
use public-key-only BatchMode with strict host-key verification and
UpdateHostKeys=no. The only remote command is the fixed /usr/bin/true.

A target that accepts the TCP/SSH journey but refuses public-key
authentication is not called offline. It is classified
HUMAN_RECOVERY_REQUIRED because that observation is compatible with the
macOS FileVault preboot unlock environment but can also mean ordinary
authorized_keys drift. This probe never tries to distinguish those causes by
soliciting or carrying a secret.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, NoReturn, Sequence

SCHEMA = "mastermind.external_recovery_readiness/v1"
SSH_BINARY = "/usr/bin/ssh"
TRUE_BINARY = "/usr/bin/true"
CONNECT_TIMEOUT_SECONDS = 12
PROBE_TIMEOUT_SECONDS = 18
MAX_STDERR_BYTES = 16 * 1024

ROUTE_STATES = frozenset(
    {"READY", "HUMAN_RECOVERY_REQUIRED", "NOT_READY", "UNKNOWN"}
)
RESULT_STATUSES = frozenset({"OK", "HUMAN_ACTION", "NOT_READY", "UNKNOWN", "SKIPPED"})
EXIT_BY_STATE = {
    "READY": 0,
    "HUMAN_RECOVERY_REQUIRED": 3,
    "NOT_READY": 4,
    "UNKNOWN": 5,
}

_ROUTE_REF_RE = re.compile(r"^route-[0-9a-f]{64}$")
_USER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_HOST_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,253}[A-Za-z0-9])?$")

_ERROR_CODES = frozenset(
    {
        "ARGUMENTS_INVALID",
        "IDENTITY_FILE_INVALID",
        "PROBE_INTERNAL_ERROR",
        "REFERENCE_INVALID",
    }
)

_GATEWAY_FAILURE_PATTERNS = (
    (
        (
            "host key verification failed",
            "remote host identification has changed",
        ),
        "GATEWAY_HOST_KEY_REFUSED",
        "NOT_READY",
    ),
    (
        ("permission denied",),
        "GATEWAY_PUBLIC_KEY_AUTH_REFUSED",
        "NOT_READY",
    ),
    (
        ("could not resolve hostname", "name or service not known"),
        "GATEWAY_NAME_RESOLUTION_FAILED",
        "NOT_READY",
    ),
    (
        (
            "connection refused",
            "connection timed out",
            "operation timed out",
            "no route to host",
            "network is unreachable",
            "connection reset",
            "connection closed",
        ),
        "GATEWAY_UNREACHABLE",
        "NOT_READY",
    ),
)

_TARGET_FAILURE_PATTERNS = (
    (
        ("permission denied",),
        "TARGET_SSH_REACHABLE_KEY_AUTH_UNAVAILABLE",
        "HUMAN_RECOVERY_REQUIRED",
    ),
    (
        (
            "host key verification failed",
            "remote host identification has changed",
        ),
        "TARGET_HOST_KEY_REFUSED",
        "NOT_READY",
    ),
    (
        ("could not resolve hostname", "name or service not known"),
        "TARGET_NAME_RESOLUTION_FAILED",
        "NOT_READY",
    ),
    (
        (
            "connection refused",
            "connection timed out",
            "operation timed out",
            "no route to host",
            "network is unreachable",
            "connection reset",
            "connection closed",
            "timed out during banner exchange",
        ),
        "TARGET_SSH_UNREACHABLE",
        "NOT_READY",
    ),
)


class ExternalRecoveryProbeError(RuntimeError):
    """Typed local refusal; messages never include caller values."""

    def __init__(self, code: str) -> None:
        safe = code if code in _ERROR_CODES else "PROBE_INTERNAL_ERROR"
        self.code = safe
        super().__init__(safe)


def _refuse(code: str) -> NoReturn:
    raise ExternalRecoveryProbeError(code)


@dataclass(frozen=True)
class RouteSpec:
    route_ref: str | None
    gateway_host: str
    gateway_user: str
    gateway_host_key_alias: str | None
    target_host: str
    target_user: str
    identity_file: Path


@dataclass(frozen=True)
class Attempt:
    returncode: int | None
    stderr: str
    timed_out: bool = False


Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[bytes]]


def _token(value: str, pattern: re.Pattern[str]) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        _refuse("REFERENCE_INVALID")
    return value


def _identity_file(raw: str, *, home: Path | None = None) -> Path:
    """Accept one regular private-key file directly beneath the caller's .ssh."""

    if type(raw) is not str or not raw or "\x00" in raw:
        _refuse("IDENTITY_FILE_INVALID")
    base = Path.home() if home is None else home
    ssh_root = base / ".ssh"
    try:
        root_resolved = ssh_root.resolve(strict=True)
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            _refuse("IDENTITY_FILE_INVALID")
        lstat = candidate.lstat()
        if stat.S_ISLNK(lstat.st_mode) or not stat.S_ISREG(lstat.st_mode):
            _refuse("IDENTITY_FILE_INVALID")
        resolved = candidate.resolve(strict=True)
        if resolved.parent != root_resolved:
            _refuse("IDENTITY_FILE_INVALID")
        current_uid = os.getuid()
        if lstat.st_uid != current_uid or lstat.st_mode & 0o077:
            _refuse("IDENTITY_FILE_INVALID")
    except ExternalRecoveryProbeError:
        raise
    except Exception:
        _refuse("IDENTITY_FILE_INVALID")
    return resolved


def build_route_spec(
    *,
    route_ref: str | None,
    gateway_host: str,
    gateway_user: str,
    gateway_host_key_alias: str | None,
    target_host: str,
    target_user: str,
    identity_file: str,
    home: Path | None = None,
) -> RouteSpec:
    if route_ref is not None and _ROUTE_REF_RE.fullmatch(route_ref) is None:
        _refuse("REFERENCE_INVALID")
    return RouteSpec(
        route_ref=route_ref,
        gateway_host=_token(gateway_host, _HOST_RE),
        gateway_user=_token(gateway_user, _USER_RE),
        gateway_host_key_alias=(
            None
            if gateway_host_key_alias is None
            else _token(gateway_host_key_alias, _HOST_RE)
        ),
        target_host=_token(target_host, _HOST_RE),
        target_user=_token(target_user, _USER_RE),
        identity_file=_identity_file(identity_file, home=home),
    )


def _common_ssh(identity_file: Path) -> list[str]:
    return [
        SSH_BINARY,
        "-i",
        str(identity_file),
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        "PasswordAuthentication=no",
        "-o",
        "KbdInteractiveAuthentication=no",
        "-o",
        "PreferredAuthentications=publickey",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "UpdateHostKeys=no",
        "-o",
        "ConnectionAttempts=1",
        "-o",
        f"ConnectTimeout={CONNECT_TIMEOUT_SECONDS}",
        "-o",
        "LogLevel=ERROR",
    ]


def gateway_command(spec: RouteSpec) -> list[str]:
    command = _common_ssh(spec.identity_file)
    if spec.gateway_host_key_alias is not None:
        command.extend(["-o", f"HostKeyAlias={spec.gateway_host_key_alias}"])
    command.extend([f"{spec.gateway_user}@{spec.gateway_host}", TRUE_BINARY])
    return command


def target_command(spec: RouteSpec) -> list[str]:
    proxy = _common_ssh(spec.identity_file)
    if spec.gateway_host_key_alias is not None:
        proxy.extend(["-o", f"HostKeyAlias={spec.gateway_host_key_alias}"])
    proxy.extend(["-W", "%h:%p", f"{spec.gateway_user}@{spec.gateway_host}"])

    command = _common_ssh(spec.identity_file)
    command.extend(
        [
            "-o",
            "ProxyCommand=" + shlex.join(proxy),
            f"{spec.target_user}@{spec.target_host}",
            TRUE_BINARY,
        ]
    )
    return command


def _default_runner(command: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
    env = {
        "HOME": str(Path.home()),
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LC_ALL": "C",
    }
    return subprocess.run(
        list(command),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=False,
        close_fds=True,
        timeout=PROBE_TIMEOUT_SECONDS,
        env=env,
    )


def _attempt(command: Sequence[str], runner: Runner) -> Attempt:
    try:
        completed = runner(command)
    except subprocess.TimeoutExpired:
        return Attempt(None, "", timed_out=True)
    except Exception:
        return Attempt(None, "")
    if not isinstance(completed, subprocess.CompletedProcess):
        return Attempt(None, "")
    payload = completed.stderr or b""
    if type(payload) is not bytes or len(payload) > MAX_STDERR_BYTES:
        payload = b""
    return Attempt(
        completed.returncode,
        payload.decode("utf-8", errors="replace"),
    )


def _classify_failure(
    attempt: Attempt,
    *,
    gateway: bool,
) -> tuple[str, str]:
    if attempt.timed_out:
        return (
            ("GATEWAY_PROBE_TIMEOUT" if gateway else "TARGET_PROBE_TIMEOUT"),
            "NOT_READY",
        )
    if attempt.returncode is None:
        return (
            ("GATEWAY_STATE_UNKNOWN" if gateway else "TARGET_STATE_UNKNOWN"),
            "UNKNOWN",
        )
    text = attempt.stderr.lower()
    patterns = _GATEWAY_FAILURE_PATTERNS if gateway else _TARGET_FAILURE_PATTERNS
    for needles, code, state in patterns:
        if any(needle in text for needle in needles):
            return code, state
    return (
        ("GATEWAY_STATE_UNKNOWN" if gateway else "TARGET_STATE_UNKNOWN"),
        "UNKNOWN",
    )


def _result(status: str, code: str) -> dict[str, str]:
    if status not in RESULT_STATUSES:
        raise AssertionError("closed status")
    return {"status": status, "code": code}


def probe_external_recovery(
    spec: RouteSpec,
    *,
    runner: Runner = _default_runner,
    now_ms: Callable[[], int] | None = None,
) -> dict[str, object]:
    clock = now_ms or (lambda: time.time_ns() // 1_000_000)

    gateway_attempt = _attempt(gateway_command(spec), runner)
    if gateway_attempt.returncode != 0:
        code, route_state = _classify_failure(gateway_attempt, gateway=True)
        report = {
            "schema": SCHEMA,
            "route_ref": spec.route_ref,
            "observed_at_ms": clock(),
            "route_state": route_state,
            "human_secret_required": False,
            "gateway": _result(
                "UNKNOWN" if route_state == "UNKNOWN" else "NOT_READY",
                code,
            ),
            "target": _result("SKIPPED", "TARGET_NOT_PROBED"),
        }
        return report

    target_attempt = _attempt(target_command(spec), runner)
    if target_attempt.returncode == 0:
        return {
            "schema": SCHEMA,
            "route_ref": spec.route_ref,
            "observed_at_ms": clock(),
            "route_state": "READY",
            "human_secret_required": False,
            "gateway": _result("OK", "GATEWAY_PUBLIC_KEY_AUTH_OK"),
            "target": _result("OK", "TARGET_PUBLIC_KEY_AUTH_OK"),
        }

    code, route_state = _classify_failure(target_attempt, gateway=False)
    target_status = {
        "HUMAN_RECOVERY_REQUIRED": "HUMAN_ACTION",
        "NOT_READY": "NOT_READY",
        "UNKNOWN": "UNKNOWN",
    }[route_state]
    return {
        "schema": SCHEMA,
        "route_ref": spec.route_ref,
        "observed_at_ms": clock(),
        "route_state": route_state,
        "human_secret_required": route_state == "HUMAN_RECOVERY_REQUIRED",
        "gateway": _result("OK", "GATEWAY_PUBLIC_KEY_AUTH_OK"),
        "target": _result(target_status, code),
    }


def canonical_json(report: dict[str, object]) -> bytes:
    state = report.get("route_state")
    if state not in ROUTE_STATES:
        _refuse("PROBE_INTERNAL_ERROR")
    if set(report) != {
        "schema",
        "route_ref",
        "observed_at_ms",
        "route_state",
        "human_secret_required",
        "gateway",
        "target",
    }:
        _refuse("PROBE_INTERNAL_ERROR")
    return (
        json.dumps(
            report,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only external SSH recovery-route readiness probe"
    )
    parser.add_argument("--route-ref")
    parser.add_argument("--gateway-host", required=True)
    parser.add_argument("--gateway-user", required=True)
    parser.add_argument("--gateway-host-key-alias")
    parser.add_argument("--target-host", required=True)
    parser.add_argument("--target-user", required=True)
    parser.add_argument("--identity-file", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(list(sys.argv[1:] if argv is None else argv))
        spec = build_route_spec(
            route_ref=args.route_ref,
            gateway_host=args.gateway_host,
            gateway_user=args.gateway_user,
            gateway_host_key_alias=args.gateway_host_key_alias,
            target_host=args.target_host,
            target_user=args.target_user,
            identity_file=args.identity_file,
        )
        report = probe_external_recovery(spec)
        sys.stdout.buffer.write(canonical_json(report))
        return EXIT_BY_STATE[str(report["route_state"])]
    except ExternalRecoveryProbeError as exc:
        sys.stderr.write(exc.code + "\n")
        return 65
    except SystemExit:
        raise
    except Exception:
        sys.stderr.write("PROBE_INTERNAL_ERROR\n")
        return 70


if __name__ == "__main__":
    raise SystemExit(main())
