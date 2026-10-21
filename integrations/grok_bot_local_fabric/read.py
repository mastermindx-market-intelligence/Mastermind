"""Grok Bot Mac-local, read-only Fabric result consumer.

This intentionally invokes only the incumbent fabric_task.py status and result
commands. It creates no Job, scheduler, queue, retry ledger, token, principal
identity, permission policy, or persistent store.

The expected root is correlation evidence, NOT authentication: any process with
the same Mac user privileges can still invoke the original Fabric adapter.
Authenticated Grok-specific delegation must be admitted by the existing
Executive/Capacity authority at its protected service boundary.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import selectors
import signal
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
from typing import Any

SCHEMA = "mastermind.grok_bot_local_fabric_read.v1"
STATUS_SCHEMA = "mastermind.fabric_task_status.v1"
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
MAX_STATUS_BYTES = 16_384
MAX_RESULT_BYTES = 8_192
DEFAULT_RESULT_BYTES = 4_096
TIMEOUT_SECONDS = 15
# Exact installed *existing* adapter on the attended m2studio host. The
# reviewed adapter contents are pinned; owner release drift must be qualified.
APPROVED_ADAPTER = (
    Path.home()
    / ".claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard"
    / "handoff_kits/meta-ceo-b-2026-09-08/ext/fabric_task.py"
)
APPROVED_ADAPTER_SHA256 = "6695a14b953461485026cadb4583be4e961147bda749dc0ccb62357cf00e2087"
MAX_ADAPTER_BYTES = 128_000
STATUS_FIELDS = (
    "run_id", "root_id", "parent_run_id", "state", "rc",
    "signal", "result_available", "accepted", "accepted_by",
    "acceptance_state",
)


class Refused(ValueError):
    """Fixed, non-secret reason for denying a read."""


def _ident(value: str) -> str:
    if not isinstance(value, str) or ID_PATTERN.fullmatch(value) is None:
        raise Refused("INVALID_ID")
    return value


def _adapter(path: Path) -> Path:
    """Pin exact original adapter path and bytes, without creating an auth plane."""
    if not isinstance(path, Path) or path != APPROVED_ADAPTER or not path.is_absolute():
        raise Refused("ADAPTER_UNAVAILABLE")
    try:
        if path.is_symlink() or path.resolve(strict=True) != path:
            raise Refused("ADAPTER_UNAVAILABLE")
        before = path.stat()
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size > MAX_ADAPTER_BYTES
            or not before.st_size
        ):
            raise Refused("ADAPTER_UNAVAILABLE")
        contents = path.read_bytes()
        after = path.stat()
        if (
            before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_size != after.st_size
            or hashlib.sha256(contents).hexdigest() != APPROVED_ADAPTER_SHA256
        ):
            raise Refused("ADAPTER_CHANGED")
    except (OSError, RuntimeError):
        raise Refused("ADAPTER_UNAVAILABLE") from None
    return path


def _run_bounded(argv: list[str], max_bytes: int) -> bytes:
    """Cap memory at source, time-bound the exact read, clean its process group."""
    try:
        process = subprocess.Popen(
            argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, start_new_session=True, cwd="/",
            env={
                "HOME": str(Path.home()),
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin",
                "LANG": "C",
                "LC_ALL": "C",
                "PYTHONIOENCODING": "utf-8",
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )
    except OSError:
        raise Refused("ADAPTER_OBSERVATION_UNAVAILABLE") from None
    deadline = time.monotonic() + TIMEOUT_SECONDS
    output = bytearray()
    completed = False
    try:
        assert process.stdout is not None
        fd = process.stdout.fileno()
        os.set_blocking(fd, False)
        with selectors.DefaultSelector() as selector:
            selector.register(fd, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise Refused("ADAPTER_OBSERVATION_UNAVAILABLE")
                if not selector.select(timeout=min(remaining, 0.2)):
                    continue
                try:
                    chunk = os.read(fd, max_bytes + 1 - len(output))
                except OSError:
                    raise Refused("ADAPTER_OBSERVATION_UNAVAILABLE") from None
                if not chunk:
                    break
                output.extend(chunk)
                if len(output) > max_bytes:
                    raise Refused("RESPONSE_TOO_LARGE")
        try:
            process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            raise Refused("ADAPTER_OBSERVATION_UNAVAILABLE") from None
        if process.returncode != 0:
            raise Refused("ADAPTER_READ_REFUSED")
        completed = True
        return bytes(output)
    finally:
        if not completed:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        if process.stdout is not None:
            process.stdout.close()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def _call(adapter: Path, args: list[str], max_bytes: int) -> bytes:
    # A fixed argument vector: no shell, environment-supplied request packet,
    # plugin credential, or arbitrary argument forwarding.
    value = _run_bounded(
        [sys.executable, "-I", "-S", str(_adapter(adapter)), *args], max_bytes
    )
    if len(value) > max_bytes:
        raise Refused("RESPONSE_TOO_LARGE")
    return value


def _status(
    adapter: Path, run_id: str, expected_root: str, expected_parent: str,
) -> dict[str, Any]:
    run_id, expected_root, expected_parent = (
        _ident(run_id), _ident(expected_root), _ident(expected_parent)
    )
    raw = _call(adapter, ["status", run_id], MAX_STATUS_BYTES)
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except (ValueError, UnicodeDecodeError):
        raise Refused("STATUS_INVALID") from None
    if (
        type(value) is not dict
        or value.get("schema") != STATUS_SCHEMA
        or value.get("run_id") != run_id
        or type(value.get("state")) is not str
    ):
        raise Refused("STATUS_INVALID")
    if value["state"] != "NOT_FOUND":
        if value.get("root_id") != expected_root:
            raise Refused("ROOT_NOT_VERIFIED")
        if value.get("parent_run_id") != expected_parent:
            raise Refused("PARENT_NOT_VERIFIED")
    # Early/unknown controller metadata is not permission to submit or retry.
    return value


def status(
    adapter: Path, run_id: str, expected_root: str, expected_parent: str,
) -> dict[str, Any]:
    value = _status(adapter, run_id, expected_root, expected_parent)
    return {
        "schema": SCHEMA,
        "action": "status",
        "correlation_not_authentication": True,
        "may_retry_request": False,
        "status": {k: value.get(k) for k in STATUS_FIELDS},
    }


def result(
    adapter: Path, run_id: str, expected_root: str, expected_parent: str,
    max_bytes: int = DEFAULT_RESULT_BYTES,
) -> dict[str, Any]:
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_RESULT_BYTES:
        raise Refused("RESULT_BOUND_INVALID")
    value = _status(adapter, run_id, expected_root, expected_parent)
    if (
        value.get("state") != "TERMINAL"
        or type(value.get("rc")) is not int
        or value.get("rc") != 0
        or value.get("result_available") is not True
    ):
        raise Refused("RESULT_NOT_READY")
    raw = _call(adapter, ["result", _ident(run_id), "--max-bytes", str(max_bytes)], max_bytes)
    # No authenticated Grok-specific result-recipient binding exists yet.
    # Never echo arbitrary worker bytes into the model/chat/Slack transcript.
    # A future principal-authenticated consumer must use canonical Executive
    # result consumption, not a caller-supplied --show-text escape switch.
    return {
        "schema": SCHEMA,
        "action": "result",
        "run_id": run_id,
        "root_id": expected_root,
        "correlation_not_authentication": True,
        "accepted": value.get("accepted") is True,
        "result_sha256": hashlib.sha256(raw).hexdigest(),
        "result_bytes": len(raw),
        "content_exposed": False,
        "content_policy": "DIGEST_ONLY_UNAUTHENTICATED",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for verb in ("status", "result"):
        p = sub.add_parser(verb)
        p.add_argument("--run-id", required=True)
        p.add_argument("--root-id", required=True)
        p.add_argument("--parent-id", required=True)
        if verb == "result":
            p.add_argument("--max-bytes", type=int, default=DEFAULT_RESULT_BYTES)
    args = parser.parse_args(argv)
    try:
        if args.action == "status":
            response = status(APPROVED_ADAPTER, args.run_id, args.root_id, args.parent_id)
        else:
            response = result(
                APPROVED_ADAPTER, args.run_id, args.root_id,
                args.parent_id, args.max_bytes
            )
        print(json.dumps(response, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
        return 0
    except Refused as exc:
        print(json.dumps({
            "schema": SCHEMA,
            "action": args.action,
            "error": str(exc),
            "may_retry_request": False,
        }, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
