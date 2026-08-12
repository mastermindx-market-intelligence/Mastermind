"""Worker-principal, value-blind probe for a live control process environment."""
from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import os
import re
import subprocess
import sys
from typing import Any

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if os.fspath(_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_ROOT))

from control_plane.codex_worker import ProcessInspector


_HEX_VALUE_RE = re.compile(rb"[0-9a-f]{64}")


class ProbeError(RuntimeError):
    pass


def _identity(pid: int) -> bytes:
    completed = subprocess.run(
        ["/bin/ps", "-o", "pid=,lstart=,uid=,gid=", "-p", str(pid)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=5,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"},
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        raise ProbeError("control process identity is unavailable")
    return completed.stdout.strip()


def _contains_secret(payload: bytes, name: bytes, value_sha256: str) -> bool:
    if name in payload:
        return True
    return any(
        hashlib.sha256(candidate).hexdigest() == value_sha256
        for candidate in _HEX_VALUE_RE.findall(payload)
    )


def _command_probe(argv: list[str], name: bytes, value_sha256: str) -> str:
    completed = subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=5,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"},
    )
    if len(completed.stdout) > 1024 * 1024 or len(completed.stderr) > 1024 * 1024:
        raise ProbeError("environment probe output exceeded its bound")
    if _contains_secret(completed.stdout + completed.stderr, name, value_sha256):
        raise ProbeError("worker observed the control canary")
    return "DENIED" if completed.returncode != 0 else "ABSENT"


def _kern_procargs2(pid: int, name: bytes, value_sha256: str) -> str:
    libc = ctypes.CDLL(None, use_errno=True)
    sysctl = libc.sysctl
    sysctl.argtypes = [
        ctypes.POINTER(ctypes.c_int),
        ctypes.c_uint,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.c_void_p,
        ctypes.c_size_t,
    ]
    sysctl.restype = ctypes.c_int
    mib = (ctypes.c_int * 3)(1, 49, pid)  # CTL_KERN, KERN_PROCARGS2, pid
    size = ctypes.c_size_t()
    if sysctl(mib, 3, None, ctypes.byref(size), None, 0) != 0:
        observed = ctypes.get_errno()
        if observed in {errno.EACCES, errno.EPERM}:
            return "DENIED"
        raise ProbeError("KERN_PROCARGS2 size probe failed ambiguously")
    if size.value <= 0 or size.value > 1024 * 1024:
        raise ProbeError("KERN_PROCARGS2 output size is invalid")
    buffer = ctypes.create_string_buffer(size.value)
    if sysctl(mib, 3, buffer, ctypes.byref(size), None, 0) != 0:
        observed = ctypes.get_errno()
        if observed in {errno.EACCES, errno.EPERM}:
            return "DENIED"
        raise ProbeError("KERN_PROCARGS2 read failed ambiguously")
    payload = bytes(buffer.raw[: size.value])
    if _contains_secret(payload, name, value_sha256):
        raise ProbeError("worker observed the control canary through KERN_PROCARGS2")
    return "ABSENT"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--sentinel-name", required=True)
    parser.add_argument("--sentinel-value-sha256", required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--release-manifest-sha256", required=True)
    parser.add_argument("--expected-worker-uid", type=int, required=True)
    parser.add_argument("--expected-worker-gid", type=int, required=True)
    args = parser.parse_args()
    digests = (
        args.sentinel_value_sha256,
        args.config_sha256,
        args.release_manifest_sha256,
    )
    if args.pid <= 1 or any(re.fullmatch(r"[0-9a-f]{64}", value) is None for value in digests):
        print("environment probe error: invalid bounded input", file=sys.stderr)
        return 2
    if (
        os.getuid() != args.expected_worker_uid
        or os.geteuid() != args.expected_worker_uid
        or os.getgid() != args.expected_worker_gid
        or os.getegid() != args.expected_worker_gid
    ):
        print("environment probe error: worker principal mismatch", file=sys.stderr)
        return 2
    name = args.sentinel_name.encode("utf-8", errors="strict")
    try:
        before = _identity(args.pid)
        checks: dict[str, Any] = {
            "launchctl": _command_probe(
                ["/bin/launchctl", "print", f"system/{args.label}"],
                name,
                args.sentinel_value_sha256,
            ),
            "ps": _command_probe(
                ["/bin/ps", "eww", "-p", str(args.pid), "-o", "command="],
                name,
                args.sentinel_value_sha256,
            ),
            "kern_procargs2": _kern_procargs2(
                args.pid,
                name,
                args.sentinel_value_sha256,
            ),
        }
        after = _identity(args.pid)
        if before != after:
            raise ProbeError("control process identity changed during the probe")
        control_identity = ProcessInspector().inspect(args.pid)
        identity_document = {
            "pid": args.pid,
            "pgid": control_identity.pgid,
            "session_id": control_identity.session_id,
            "start_identity": control_identity.start_identity,
            "boot_id": ProcessInspector().boot_session_id(),
            "effective_uid": control_identity.effective_uid,
            "effective_gid": control_identity.effective_gid,
            "real_uid": control_identity.real_uid,
            "real_gid": control_identity.real_gid,
        }
        identity_sha256 = hashlib.sha256(
            json.dumps(
                identity_document,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        receipt = {
            "schema_version": "mastermind.executive_control_env_probe/v1",
            "passed": True,
            "control_process_identity": identity_document,
            "worker_principal": {
                "real_uid": os.getuid(),
                "effective_uid": os.geteuid(),
                "real_gid": os.getgid(),
                "effective_gid": os.getegid(),
            },
            "config_sha256": args.config_sha256,
            "release_manifest_sha256": args.release_manifest_sha256,
            "sentinel_value_sha256": args.sentinel_value_sha256,
            "process_identity_sha256": identity_sha256,
            "checks": checks,
        }
        print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
        return 0
    except (OSError, ProbeError, subprocess.TimeoutExpired) as exc:
        print(f"environment probe error: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
