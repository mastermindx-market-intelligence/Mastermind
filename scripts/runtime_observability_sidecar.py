#!/usr/bin/env python3
"""Run the production-inert P0 runtime diagnostic sidecar on a disposable socket."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import signal
import socket
import stat
import sys
from collections.abc import Sequence
from pathlib import Path

# Isolated-mode entrypoints bind imports to the exact reviewed release tree.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integrations.runtime_observability.sidecar import RuntimeDiagnosticSidecar
from integrations.runtime_observability.sinks import JsonLineSink


class CliConfigurationError(ValueError):
    """The disposable P0 sidecar was given an unsafe configuration."""


@dataclasses.dataclass(frozen=True)
class CliConfiguration:
    socket_path: Path
    max_events: int


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--socket-path",
        required=True,
        help="absolute disposable Unix datagram socket path",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=1,
        help="stop after this many accepted events (1..10000)",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def _is_disposable_path(path: Path) -> bool:
    allowed_roots = (Path("/tmp"), Path("/private/tmp"))
    return any(path != root and root in path.parents for root in allowed_roots)


def validate_cli_configuration(
    args: argparse.Namespace,
    *,
    effective_uid: int,
) -> CliConfiguration:
    if effective_uid == 0:
        raise CliConfigurationError("the disposable sidecar refuses root execution")

    raw_path = str(getattr(args, "socket_path", "") or "").strip()
    if not raw_path or "://" in raw_path:
        raise CliConfigurationError("socket path must be an absolute filesystem path")
    socket_path = Path(raw_path)
    if not socket_path.is_absolute() or not _is_disposable_path(socket_path):
        raise CliConfigurationError(
            "socket path must be under an approved disposable directory"
        )

    max_events = getattr(args, "max_events", None)
    if type(max_events) is not int or not 1 <= max_events <= 10_000:
        raise CliConfigurationError("max-events must be an integer from 1 to 10000")

    return CliConfiguration(
        socket_path=socket_path,
        max_events=max_events,
    )


def _prepare_socket_path(path: Path, *, effective_uid: int) -> None:
    if path.exists() or path.is_symlink():
        raise CliConfigurationError("socket path already exists")
    parent = path.parent
    if not parent.is_dir() or parent.is_symlink():
        raise CliConfigurationError("socket parent must be an existing real directory")
    parent_stat = parent.stat()
    if parent not in {Path("/tmp"), Path("/private/tmp")} and parent_stat.st_uid != effective_uid:
        raise CliConfigurationError("socket parent must be owned by the current user")


def _remove_owned_socket(path: Path, *, effective_uid: int) -> None:
    try:
        current = path.lstat()
    except FileNotFoundError:
        return
    if current.st_uid == effective_uid and stat.S_ISSOCK(current.st_mode):
        path.unlink()


def main(argv: Sequence[str] | None = None) -> int:
    try:
        config = validate_cli_configuration(
            parse_args(argv),
            effective_uid=os.geteuid(),
        )
        _prepare_socket_path(config.socket_path, effective_uid=os.geteuid())
    except CliConfigurationError as exc:
        print(f"runtime-observability-sidecar configuration error: {exc}", file=sys.stderr)
        return 2

    stop = {"requested": False}

    def request_stop(_signum: int, _frame: object) -> None:
        stop["requested"] = True

    previous_umask = os.umask(0o077)
    receiver = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        receiver.bind(str(config.socket_path))
        os.chmod(config.socket_path, 0o600)
        signal.signal(signal.SIGINT, request_stop)
        signal.signal(signal.SIGTERM, request_stop)

        sink = JsonLineSink(sys.stdout, flush=True)
        sidecar = RuntimeDiagnosticSidecar(sink=sink)

        def stop_requested() -> bool:
            return stop["requested"] or sidecar.counters.accepted >= config.max_events

        counters = sidecar.serve_sockets(
            {"disposable": receiver},
            stop_requested=stop_requested,
        )
        summary = {
            "accepted": counters.accepted,
            "duplicate": counters.duplicate,
            "rejected": counters.rejected,
            "sink_failed": counters.sink_failed,
            "source": "runtime-observability-sidecar",
        }
        print(
            json.dumps(
                summary,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            ),
            file=sys.stderr,
        )
        return 0
    finally:
        try:
            receiver.close()
        finally:
            _remove_owned_socket(
                config.socket_path,
                effective_uid=os.geteuid(),
            )
            os.umask(previous_umask)


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CliConfiguration",
    "CliConfigurationError",
    "main",
    "parse_args",
    "validate_cli_configuration",
]
