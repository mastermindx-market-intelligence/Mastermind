#!/usr/bin/env python3
"""Foreground launchd entrypoint for one installed MH1 gateway service."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Sequence, TextIO

_SCRIPT_DIRECTORY = Path(__file__).resolve().parent
_RELEASE_ROOT = _SCRIPT_DIRECTORY.parent
if str(_RELEASE_ROOT) not in sys.path:
    sys.path.insert(0, str(_RELEASE_ROOT))

from ops.executive_os.remote_worker_gateway_service import (  # noqa: E402
    RemoteWorkerGatewayServiceError,
    SERVICE_CHECK_SCHEMA,
    load_remote_worker_gateway_config,
    remote_worker_gateway_config_digest,
    run_remote_worker_gateway_service,
)


class _Parser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise ValueError("arguments_invalid")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(add_help=False)
    parser.add_argument("--config", required=True)
    parser.add_argument("--check-config", action="store_true")
    return parser


def _emit(stream: TextIO, value: dict[str, Any]) -> None:
    stream.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
    stream.flush()


def main(
    argv: Sequence[str] | None = None,
    *,
    loader: Callable[..., Any] = load_remote_worker_gateway_config,
    runner: Callable[[Any], None] = run_remote_worker_gateway_service,
    geteuid: Callable[[], int] = os.geteuid,
    getegid: Callable[[], int] = os.getegid,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    try:
        args = _parser().parse_args(list(argv) if argv is not None else None)
    except (ValueError, SystemExit):
        _emit(stderr, {"schema": SERVICE_CHECK_SCHEMA, "ok": False, "code": "ARGUMENTS_INVALID"})
        return 64
    if geteuid() == 0:
        _emit(stderr, {"schema": SERVICE_CHECK_SCHEMA, "ok": False, "code": "ROOT_EXECUTION_REFUSED"})
        return 77
    try:
        config = loader(
            Path(args.config),
            expected_owner_uid=0,
            expected_group_gid=getegid(),
        )
    except (RemoteWorkerGatewayServiceError, TypeError, ValueError, OSError):
        _emit(stderr, {"schema": SERVICE_CHECK_SCHEMA, "ok": False, "code": "CONFIG_REFUSED"})
        return 65
    if args.check_config:
        _emit(
            stdout,
            {
                "schema": SERVICE_CHECK_SCHEMA,
                "ok": True,
                "config_sha256": remote_worker_gateway_config_digest(config),
            },
        )
        return 0
    try:
        runner(config)
    except Exception:
        _emit(stderr, {"schema": SERVICE_CHECK_SCHEMA, "ok": False, "code": "SERVICE_FAILED"})
        return 70
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
