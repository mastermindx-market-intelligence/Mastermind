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
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise Refused("ADAPTER_UNAVAILABLE")
    return path


def _run_bounded(argv: list[str], max_bytes: int) -> bytes:
    """Cap memory at source, time-bound the exact read, clean its process group."""
    try:
        process = subprocess.Popen(
            argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, start_new_session=True,
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
                chunk = os.read(fd, max_bytes + 1 - len(output))
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
    value = _run_bounded([sys.executable, str(_adapter(adapter)), *args], max_bytes)
    if len(value) > max_bytes:
        raise Refused("RESPONSE_TOO_LARGE")
    return value


def _status(adapter: Path, run_id: str, expected_root: str) -> dict[str, Any]:
    run_id, expected_root = _ident(run_id), _ident(expected_root)
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
    if value["state"] != "NOT_FOUND" and value.get("root_id") != expected_root:
        raise Refused("ROOT_NOT_VERIFIED")
    # An early controller may have no root: never interpret that as retry permission.
    return value


def status(adapter: Path, run_id: str, expected_root: str) -> dict[str, Any]:
    value = _status(adapter, run_id, expected_root)
    return {
        "schema": SCHEMA,
        "action": "status",
        "correlation_not_authentication": True,
        "may_retry_request": False,
        "status": {k: value.get(k) for k in STATUS_FIELDS},
    }


def result(
    adapter: Path, run_id: str, expected_root: str,
    max_bytes: int = DEFAULT_RESULT_BYTES,
) -> dict[str, Any]:
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_RESULT_BYTES:
        raise Refused("RESULT_BOUND_INVALID")
    value = _status(adapter, run_id, expected_root)
    if (
        value.get("state") != "TERMINAL"
        or value.get("rc") != 0
        or value.get("result_available") is not True
    ):
        raise Refused("RESULT_NOT_READY")
    raw = _call(adapter, ["result", _ident(run_id), "--max-bytes", str(max_bytes)], max_bytes)
    try:
        decoded = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise Refused("RESULT_NOT_UTF8") from None
    return {
        "schema": SCHEMA,
        "action": "result",
        "run_id": run_id,
        "root_id": expected_root,
        "correlation_not_authentication": True,
        "accepted": value.get("accepted") is True,
        "result_sha256": hashlib.sha256(raw).hexdigest(),
        "result_bytes": len(raw),
        "text": decoded,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", type=Path, required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    for verb in ("status", "result"):
        p = sub.add_parser(verb)
        p.add_argument("--run-id", required=True)
        p.add_argument("--root-id", required=True)
        if verb == "result":
            p.add_argument("--max-bytes", type=int, default=DEFAULT_RESULT_BYTES)
    args = parser.parse_args(argv)
    try:
        if args.action == "status":
            response = status(args.adapter, args.run_id, args.root_id)
        else:
            response = result(args.adapter, args.run_id, args.root_id, args.max_bytes)
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
