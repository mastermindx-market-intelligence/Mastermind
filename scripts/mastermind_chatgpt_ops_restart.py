#!/usr/bin/env python3
"""Bounded SCF-OPS2 restart through the existing Studio Direct owner.

The caller supplies only an allowlisted semantic service reference, exact
previously observed instance/build identities, and a closed reason code. The
server chooses the fixed account mapping and existing service-manager helper.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Callable

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from control_plane.sol_ops_restart import (
    ALLOWED_REASONS,
    RestartObservation,
    RestartRequest,
    RestartResult,
    RestartState,
    SCHEMA,
    preflight_restart,
    validate_request,
)
from scripts.mastermind_chatgpt_ops_health import (
    CONTROL_ROOT,
    STUDIO_LAUNCHER,
    read_personal_status,
    verify_studio_control_owner,
)

SERVICE_TO_ACCOUNT = {
    "studio-direct.chatgpt1": "chatgpt1",
    "studio-direct.chatgpt2-personal": "chatgpt2-personal",
    "studio-direct.chatgpt2-business": "chatgpt2-business",
    "studio-direct.admin-business": "admin-business",
    "studio-direct.chatgpt3-w570f6f34": "chatgpt3-w570f6f34",
    "studio-direct.chatgpt3-wa2a9e6f9": "chatgpt3-wa2a9e6f9",
    "studio-direct.chatgpt4": "chatgpt4",
}
PRIVATE_ROOT = Path.home() / ".local" / "share" / "studio-direct-mcp" / "private"
MANIFEST_NAME = "manifest.json"
MAX_MANIFEST_BYTES = 64 * 1024
OWNER_ACTION_TIMEOUT_SECONDS = 96
RESTART_LOCK_NAME = ".scf-ops-restart.lock"
_TUNNEL = re.compile(r"^tunnel_[0-9a-f]{32}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _closed_service(service_ref: str) -> str:
    account = SERVICE_TO_ACCOUNT.get(service_ref)
    if account is None:
        raise ValueError("service_ref is outside the closed allowlist")
    return account


def _read_regular_bounded(path: Path, maximum: int) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as error:
        raise ValueError("owner manifest is unavailable") from error
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            raise ValueError("owner manifest must be a regular bounded file")
        data = os.read(fd, maximum + 1)
        if len(data) > maximum or os.read(fd, 1):
            raise ValueError("owner manifest must be a regular bounded file")
        return data
    finally:
        os.close(fd)


def _manifest_reader(account: str) -> dict[str, object]:
    if account not in SERVICE_TO_ACCOUNT.values():
        raise ValueError("account is outside the closed allowlist")
    raw = _read_regular_bounded(PRIVATE_ROOT / account / MANIFEST_NAME, MAX_MANIFEST_BYTES)
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("owner manifest is invalid") from error
    if not isinstance(value, dict):
        raise ValueError("owner manifest must be an object")
    return value


def _hash_field(manifest: dict[str, object], key: str) -> str:
    value = manifest.get(key)
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise ValueError(f"owner manifest {key} is invalid")
    return value


def _build_identity(account: str, manifest: dict[str, object]) -> str:
    if manifest.get("account") != account:
        raise ValueError("owner manifest account mismatch")
    version = manifest.get("version")
    label = manifest.get("label")
    files = manifest.get("files")
    if type(version) is not int or not isinstance(label, str) or not label:
        raise ValueError("owner manifest identity is invalid")
    if not isinstance(files, dict) or not files:
        raise ValueError("owner manifest files are invalid")
    safe_files: dict[str, str] = {}
    for name, digest in files.items():
        if not isinstance(name, str) or not name or "/" in name or "\\" in name:
            raise ValueError("owner manifest file name is invalid")
        if not isinstance(digest, str) or _SHA.fullmatch(digest) is None:
            raise ValueError("owner manifest file digest is invalid")
        safe_files[name] = digest
    payload = {
        "version": version,
        "account": account,
        "label": label,
        "configHash": _hash_field(manifest, "configHash"),
        "nodeHash": _hash_field(manifest, "nodeHash"),
        "backendHash": _hash_field(manifest, "backendHash"),
        "dependencyTreeHash": _hash_field(manifest, "dependencyTreeHash"),
        "plistHash": _hash_field(manifest, "plistHash"),
        "files": safe_files,
    }
    return _digest(payload)


def _pid(value: object, field: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value <= 0:
        raise ValueError(f"owner status {field} is invalid")
    return value


def _instance_identity(account: str, status: dict[str, object]) -> str:
    gateway = status.get("gateway")
    tunnel = status.get("tunnel")
    if not isinstance(gateway, dict) or not isinstance(tunnel, dict):
        raise ValueError("owner status is incomplete")
    tunnel_id = tunnel.get("tunnelId")
    if tunnel_id is not None and (
        not isinstance(tunnel_id, str) or _TUNNEL.fullmatch(tunnel_id) is None
    ):
        raise ValueError("owner status tunnel identity is invalid")
    runtime_version = gateway.get("runtimeVersion")
    if runtime_version is not None and not isinstance(runtime_version, str):
        raise ValueError("owner status runtime version is invalid")
    payload = {
        "account": account,
        "gateway_pid": _pid(gateway.get("pid"), "gateway pid"),
        "tunnel_pid": _pid(tunnel.get("pid"), "tunnel pid"),
        "tunnel_id": tunnel_id,
        "runtime_version": runtime_version,
    }
    return _digest(payload)


def observe_exact_service(
    service_ref: str,
    *,
    status_reader: Callable[[str], dict[str, object]] = read_personal_status,
    manifest_reader: Callable[[str], dict[str, object]] = _manifest_reader,
) -> RestartObservation:
    account = _closed_service(service_ref)
    status = status_reader(account)
    if not isinstance(status, dict):
        raise ValueError("owner status must be an object")
    manifest = manifest_reader(account)
    gateway = status.get("gateway")
    if not isinstance(gateway, dict):
        raise ValueError("owner status gateway is unavailable")
    runtime_version = gateway.get("runtimeVersion")
    if runtime_version is not None and not isinstance(runtime_version, str):
        raise ValueError("owner runtime version is invalid")
    issues: tuple[str, ...] = (
        ("CONFIGURATION_DRIFT",)
        if gateway.get("configurationDrift") is True
        else ()
    )
    return RestartObservation(
        service_ref=service_ref,
        instance_identity=_instance_identity(account, status),
        build_identity=_build_identity(account, manifest),
        ready=bool(status.get("ready")),
        runtime_version=runtime_version,
        issues=issues,
    )


def _run_owner_action(account: str, action: str) -> dict[str, object]:
    if account not in SERVICE_TO_ACCOUNT.values():
        raise ValueError("account is outside the closed allowlist")
    if action not in {"stop", "start"}:
        raise ValueError("owner action is outside the closed restart sequence")
    verify_studio_control_owner(control_root=CONTROL_ROOT, launcher=STUDIO_LAUNCHER)
    helper = CONTROL_ROOT / "studio_direct_control.py"
    result = subprocess.run(
        [sys.executable, str(helper), action, "--account", account],
        capture_output=True,
        text=True,
        timeout=OWNER_ACTION_TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("existing Studio Direct owner action failed")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("existing Studio Direct owner returned invalid JSON") from error
    if not isinstance(value, dict):
        raise RuntimeError("existing Studio Direct owner returned invalid output")
    return value


@contextlib.contextmanager
def _restart_lock():
    """Serialize SCF restart attempts without owning service lifecycle state."""
    try:
        root_info = CONTROL_ROOT.lstat()
    except OSError as exc:
        raise RuntimeError("existing Studio Direct control root is unavailable") from exc
    if (
        CONTROL_ROOT.is_symlink()
        or not stat.S_ISDIR(root_info.st_mode)
        or root_info.st_uid != os.getuid()
        or stat.S_IMODE(root_info.st_mode) & 0o077
    ):
        raise RuntimeError("existing Studio Direct control root is unsafe")
    path = CONTROL_ROOT / RESTART_LOCK_NAME
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise RuntimeError("restart serialization lock is unavailable") from exc
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) & 0o077
        ):
            raise RuntimeError("restart serialization lock is unsafe")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("restart already in progress") from exc
        yield
    finally:
        os.close(fd)


def _effect_unknown(request: RestartRequest, code: str, observed: RestartObservation | None) -> RestartResult:
    return RestartResult(
        RestartState.EFFECT_UNKNOWN,
        code,
        request.service_ref,
        observed.instance_identity if observed else None,
        observed.build_identity if observed else None,
        observed.ready if observed else None,
        observed.runtime_version if observed else None,
        False,
    )


def _applied(request: RestartRequest, observed: RestartObservation, code: str) -> RestartResult:
    return RestartResult(
        RestartState.APPLIED,
        code,
        request.service_ref,
        observed.instance_identity,
        observed.build_identity,
        observed.ready,
        observed.runtime_version,
        False,
    )


def _restart_exact_service_locked(
    request: RestartRequest,
    *,
    observe_fn: Callable[[str], RestartObservation],
    action_fn: Callable[[str, str], dict[str, object]],
) -> RestartResult:
    account = _closed_service(request.service_ref)
    before = observe_fn(request.service_ref)
    refusal = preflight_restart(request, before)
    if refusal is not None:
        return refusal

    try:
        action_fn(account, "stop")
        action_fn(account, "start")
    except Exception:
        try:
            after = observe_fn(request.service_ref)
        except Exception:
            return _effect_unknown(request, "OWNER_RESPONSE_LOST_READBACK_UNAVAILABLE", None)
        if after.instance_identity != before.instance_identity:
            return _applied(request, after, "APPLIED_RECONCILED_AFTER_OWNER_ERROR")
        return _effect_unknown(request, "OWNER_RESPONSE_LOST_INSTANCE_UNCHANGED", after)

    try:
        after = observe_fn(request.service_ref)
    except Exception:
        return _effect_unknown(request, "POST_RESTART_READBACK_UNAVAILABLE", None)
    if after.instance_identity == before.instance_identity:
        return _effect_unknown(request, "INSTANCE_GENERATION_UNCHANGED_AFTER_RESTART", after)
    if after.build_identity != before.build_identity:
        return _applied(request, after, "APPLIED_BUILD_CHANGED_DURING_RESTART")
    if not after.ready:
        return _applied(request, after, "APPLIED_NOT_READY")
    return _applied(request, after, "APPLIED_READY")


def restart_exact_service(
    request: RestartRequest,
    *,
    observe_fn: Callable[[str], RestartObservation] = observe_exact_service,
    action_fn: Callable[[str, str], dict[str, object]] = _run_owner_action,
    lock_fn=None,
) -> RestartResult:
    """Restart one exact service while serializing duplicate SCF effects.

    The lock is invocation-local synchronization only; Studio Direct remains the
    lifecycle owner. The instance identity still fences replay after completion.
    """
    request = validate_request(request)
    lock_factory = _restart_lock if lock_fn is None else lock_fn
    with lock_factory():
        return _restart_exact_service_locked(
            request, observe_fn=observe_fn, action_fn=action_fn
        )


def _request_from_args(args: argparse.Namespace) -> RestartRequest:
    return RestartRequest(
        service_ref=args.service_ref,
        expected_instance_identity=args.expected_instance_identity,
        expected_build_identity=args.expected_build_identity,
        reason_code=args.reason_code,
    )


def main() -> int:
    parser = argparse.ArgumentParser(prog="mastermind-chatgpt-ops-restart")
    subparsers = parser.add_subparsers(dest="command", required=True)
    observe = subparsers.add_parser("observe")
    observe.add_argument("--service-ref", required=True, choices=sorted(SERVICE_TO_ACCOUNT))
    restart = subparsers.add_parser("restart")
    restart.add_argument("--service-ref", required=True, choices=sorted(SERVICE_TO_ACCOUNT))
    restart.add_argument("--expected-instance-identity", required=True)
    restart.add_argument("--expected-build-identity", required=True)
    restart.add_argument("--reason-code", required=True, choices=sorted(ALLOWED_REASONS))
    args = parser.parse_args()
    try:
        if args.command == "observe":
            print(json.dumps({"schema": SCHEMA, **observe_exact_service(args.service_ref).to_dict()}, sort_keys=True))
            return 0
        result = restart_exact_service(_request_from_args(args))
        print(json.dumps(result.to_dict(), sort_keys=True))
        return 0 if result.state == RestartState.APPLIED else 2
    except (ValueError, RuntimeError, subprocess.TimeoutExpired):
        print(
            json.dumps(
                {
                    "schema": SCHEMA,
                    "state": RestartState.NOT_APPLIED.value,
                    "code": "OWNER_OR_REQUEST_UNAVAILABLE",
                    "retry_allowed": False,
                },
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
