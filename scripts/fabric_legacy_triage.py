#!/usr/bin/env python3
"""One-shot read-only batch triage over the installed native fabric_task.py status.

Example (after normal source release):
  python scripts/fabric_legacy_triage.py --fabric-task /ABS/PATH/ext/fabric_task.py \
    --expected-sha256 <installed-source-sha> --run-id RUN1 --run-id RUN2

No provider launch, shell execution, retry, queue, ledger write, or auto-reallocation.
The caller must already know the exact original run IDs and trusted installed path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPOSITORY = Path(__file__).resolve().parents[1]
if str(_REPOSITORY) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY))

from control_plane.legacy_fabric_run_triage import _validate_run_id, project_legacy_fleet

_SHA = re.compile(r"^[0-9a-f]{64}$")
_MAX_SCRIPT = 1_048_576
_MAX_STDOUT = 16_384


def safe_fabric_entry(path: Path, expected_sha256: str) -> Path:
    """Reject unpinned/untrusted scripts; not a provider credential check."""
    if (not isinstance(path, Path) or not path.is_absolute()
            or path.name != "fabric_task.py"
            or not isinstance(expected_sha256, str)
            or not _SHA.fullmatch(expected_sha256)):
        raise ValueError("a pinned, absolute installed fabric_task.py is required")
    try:
        source = path.lstat()
        if (not stat.S_ISREG(source.st_mode) or stat.S_ISLNK(source.st_mode)
                or source.st_uid != os.getuid()
                or source.st_mode & 0o002 or source.st_size > _MAX_SCRIPT):
            raise ValueError("untrusted installed fabric_task.py")
        raw = path.read_bytes()
        after = path.lstat()
    except OSError as exc:
        raise ValueError("installed Fabric entry is not readable") from exc
    if (len(raw) != source.st_size
            or (source.st_dev, source.st_ino, source.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_mtime_ns)
            or hashlib.sha256(raw).hexdigest() != expected_sha256):
        raise ValueError("installed Fabric entry digest/identity mismatch")
    return path


def read_legacy_status(path: Path, run_id: str, expected_sha256: str,
                       *, timeout_seconds: int = 10) -> dict[str, Any]:
    run_id = _validate_run_id(run_id)
    safe_fabric_entry(path, expected_sha256)
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 30:
        raise ValueError("status read timeout must be between 1 and 30 seconds")
    result = subprocess.run(
        [sys.executable, "-B", str(path), "status", run_id],
        cwd=str(path.parent), timeout=timeout_seconds,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        env={
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.path.expanduser("~"),
            "LC_ALL": "C",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    )
    # A read that changed its installed source while running is unknown, never
    # a successful accepted status. Preserve the incumbent carrier for triage.
    safe_fabric_entry(path, expected_sha256)
    if result.returncode or not result.stdout or len(result.stdout) > _MAX_STDOUT:
        raise ValueError("native status response unavailable or unbounded")
    try:
        decoded = json.loads(result.stdout.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("native status is not bounded JSON") from exc
    if (not isinstance(decoded, dict)
            or decoded.get("schema") != "mastermind.fabric_task_status.v1"
            or decoded.get("run_id") != run_id):
        raise ValueError("native status is not bound to the original run")
    return decoded


def bounded_reader(path: Path, expected_sha256: str, *,
                   per_run_seconds: int, total_seconds: int,
                   clock=None, read=read_legacy_status):
    """Cap a whole batch without starting any new monitoring or retry loop."""
    if (type(per_run_seconds) is not int or not 1 <= per_run_seconds <= 30
            or type(total_seconds) is not int or not 1 <= total_seconds <= 300):
        raise ValueError("native status budgets must be bounded positive seconds")
    if clock is None:
        clock = time.monotonic
    deadline = clock() + total_seconds

    def one(run_id: str):
        remaining = deadline - clock()
        if remaining <= 0:
            raise TimeoutError("batch status budget exhausted")
        budget = min(per_run_seconds, max(1, math.ceil(remaining)))
        return read(path, run_id, expected_sha256, timeout_seconds=budget)

    return one


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fabric-task", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--run-id", action="append", required=True)
    parser.add_argument("--expected-root-id")
    parser.add_argument("--expected-parent-run-id")
    parser.add_argument("--timeout-seconds", type=int, default=10)
    parser.add_argument("--total-seconds", type=int, default=30)
    args = parser.parse_args(argv)
    path = safe_fabric_entry(args.fabric_task, args.expected_sha256)
    # Batch budget is shared: an unresponsive run never hides healthy siblings.
    reader = bounded_reader(
        path, args.expected_sha256, per_run_seconds=args.timeout_seconds,
        total_seconds=args.total_seconds,
    )
    result = project_legacy_fleet(
        args.run_id, reader,
        expected_root_id=args.expected_root_id,
        expected_parent_run_id=args.expected_parent_run_id,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
