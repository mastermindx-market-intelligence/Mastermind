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


_HEX_VALUE_RE = re.compile(rb"[0-9a-f]{64}")


class ProbeError(RuntimeError):
    pass


_CONTROL_IDENTITY_KEYS = {
    "pid",
    "pgid",
    "session_id",
    "start_identity",
    "boot_id",
    "effective_uid",
    "effective_gid",
    "real_uid",
    "real_gid",
}


def _identity(pid: int) -> tuple[bytes, dict[str, int]]:
    completed = subprocess.run(
        [
            "/bin/ps",
            "-o",
            "pid=,pgid=,sess=,lstart=,uid=,gid=,ruid=,rgid=",
            "-p",
            str(pid),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=5,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"},
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        raise ProbeError("ps_identity_unavailable")
    raw = completed.stdout.strip()
    fields = raw.split()
    if len(fields) != 12:
        raise ProbeError("ps_identity_malformed")
    try:
        observed = {
            "pid": int(fields[0]),
            "pgid": int(fields[1]),
            "session_id": int(fields[2]),
            "effective_uid": int(fields[-4]),
            "effective_gid": int(fields[-3]),
            "real_uid": int(fields[-2]),
            "real_gid": int(fields[-1]),
        }
    except ValueError as exc:
        raise ProbeError("ps_identity_invalid") from exc
    return raw, observed


def _expected_identity(raw: str, pid: int, observed: dict[str, int]) -> dict[str, Any]:
    try:
        identity = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProbeError("expected_identity_invalid") from exc
    if (
        not isinstance(identity, dict)
        or set(identity) != _CONTROL_IDENTITY_KEYS
        or any(
            type(identity.get(key)) is not int
            for key in (
                "pid",
                "pgid",
                "session_id",
                "effective_uid",
                "effective_gid",
                "real_uid",
                "real_gid",
            )
        )
        or not isinstance(identity.get("start_identity"), str)
        or not identity["start_identity"]
        or not isinstance(identity.get("boot_id"), str)
        or not identity["boot_id"]
        or identity["pid"] != pid
    ):
        raise ProbeError("expected_identity_invalid")
    if any(identity[key] != value for key, value in observed.items()):
        raise ProbeError("expected_identity_mismatch")
    boot = subprocess.run(
        ["/usr/sbin/sysctl", "-n", "kern.bootsessionuuid"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=5,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"},
    )
    if (
        boot.returncode != 0
        or boot.stdout.decode("ascii", errors="strict").strip() != identity["boot_id"]
    ):
        raise ProbeError("boot_identity_mismatch")
    return identity


def _contains_secret(payload: bytes, name: bytes, value_sha256: str) -> bool:
    if name in payload:
        return True
    return any(
        hashlib.sha256(candidate).hexdigest() == value_sha256
        for candidate in _HEX_VALUE_RE.findall(payload)
    )


def _command_probe(
    argv: list[str], name: bytes, value_sha256: str, *, label: str
) -> str:
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
        raise ProbeError(f"{label}_output_oversize")
    if _contains_secret(completed.stdout + completed.stderr, name, value_sha256):
        raise ProbeError(f"{label}_observed_canary")
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
        raise ProbeError("kern_procargs2_size_ambiguous")
    if size.value <= 0 or size.value > 1024 * 1024:
        raise ProbeError("kern_procargs2_size_invalid")
    buffer = ctypes.create_string_buffer(size.value)
    if sysctl(mib, 3, buffer, ctypes.byref(size), None, 0) != 0:
        observed = ctypes.get_errno()
        if observed in {errno.EACCES, errno.EPERM}:
            return "DENIED"
        raise ProbeError("kern_procargs2_read_ambiguous")
    payload = bytes(buffer.raw[: size.value])
    if _contains_secret(payload, name, value_sha256):
        raise ProbeError("kern_procargs2_observed_canary")
    return "ABSENT"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--sentinel-name", required=True)
    parser.add_argument("--sentinel-value-sha256", required=True)
    parser.add_argument("--config-sha256", required=True)
    parser.add_argument("--release-manifest-sha256", required=True)
    parser.add_argument("--control-process-identity-json", required=True)
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
        before, observed_identity = _identity(args.pid)
        control_identity = _expected_identity(
            args.control_process_identity_json,
            args.pid,
            observed_identity,
        )
        checks: dict[str, Any] = {
            "launchctl": _command_probe(
                ["/bin/launchctl", "print", f"system/{args.label}"],
                name,
                args.sentinel_value_sha256,
                label="launchctl",
            ),
            "ps": _command_probe(
                ["/bin/ps", "eww", "-p", str(args.pid), "-o", "command="],
                name,
                args.sentinel_value_sha256,
                label="ps",
            ),
            "kern_procargs2": _kern_procargs2(
                args.pid,
                name,
                args.sentinel_value_sha256,
            ),
        }
        after, after_identity = _identity(args.pid)
        if before != after:
            raise ProbeError("control_identity_changed")
        if after_identity != observed_identity:
            raise ProbeError("control_identity_changed")
        identity_sha256 = hashlib.sha256(
            json.dumps(
                control_identity,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        receipt = {
            "schema_version": "mastermind.executive_control_env_probe/v1",
            "passed": True,
            "control_process_identity": control_identity,
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
    except ProbeError as exc:
        print(f"environment probe error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"environment probe error: os_error_{exc.errno}", file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired:
        print("environment probe error: subprocess_timeout", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
