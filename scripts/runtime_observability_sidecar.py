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


SocketIdentity = tuple[int, int, int, int]
_DISPOSABLE_ROOTS = (Path("/tmp"), Path("/private/tmp"))


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


def _lexical_disposable_root(path: Path) -> Path | None:
    for root in _DISPOSABLE_ROOTS:
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if relative.parts:
            return root
    return None


def _resolved_disposable_roots() -> tuple[Path, ...]:
    roots: list[Path] = []
    for root in _DISPOSABLE_ROOTS:
        resolved = root.resolve(strict=False)
        if resolved not in roots:
            roots.append(resolved)
    return tuple(roots)


def _resolved_disposable_root(path: Path) -> Path | None:
    for root in _resolved_disposable_roots():
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if relative.parts:
            return root
    return None


def _assert_no_symlink_below_root(path: Path, *, root: Path) -> None:
    """Reject existing symlink components below an approved disposable root.

    The root itself is deliberately excluded because macOS exposes ``/tmp`` as
    the system-managed alias for ``/private/tmp``.  Every caller-controlled
    component below that root must be a real path component.
    """

    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise CliConfigurationError(
            "socket path escaped the approved disposable directory"
        ) from exc

    current = root
    for component in relative.parts[:-1]:
        current = current / component
        try:
            observed = current.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise CliConfigurationError(
                "socket path component is not observable"
            ) from exc
        if stat.S_ISLNK(observed.st_mode):
            raise CliConfigurationError(
                "socket path contains a symlink below the disposable root"
            )


def _normalize_disposable_path(path: Path) -> Path:
    if ".." in path.parts:
        raise CliConfigurationError(
            "socket path must not contain parent-directory traversal"
        )
    lexical_root = _lexical_disposable_root(path)
    if lexical_root is None:
        raise CliConfigurationError(
            "socket path must be under an approved disposable directory"
        )
    _assert_no_symlink_below_root(path, root=lexical_root)

    try:
        resolved = path.resolve(strict=False)
    except OSError as exc:
        raise CliConfigurationError("socket path is not resolvable") from exc
    resolved_root = _resolved_disposable_root(resolved)
    if resolved_root is None:
        raise CliConfigurationError(
            "socket path escaped the approved disposable directory"
        )
    _assert_no_symlink_below_root(resolved, root=resolved_root)
    return resolved


def _is_disposable_path(path: Path) -> bool:
    try:
        _normalize_disposable_path(path)
    except CliConfigurationError:
        return False
    return True


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
    lexical_path = Path(raw_path)
    if not lexical_path.is_absolute():
        raise CliConfigurationError("socket path must be an absolute filesystem path")
    socket_path = _normalize_disposable_path(lexical_path)

    max_events = getattr(args, "max_events", None)
    if type(max_events) is not int or not 1 <= max_events <= 10_000:
        raise CliConfigurationError("max-events must be an integer from 1 to 10000")

    return CliConfiguration(
        socket_path=socket_path,
        max_events=max_events,
    )


def _prepare_socket_path(path: Path, *, effective_uid: int) -> None:
    resolved_root = _resolved_disposable_root(path)
    if resolved_root is None:
        raise CliConfigurationError(
            "socket path must remain under an approved disposable directory"
        )
    _assert_no_symlink_below_root(path, root=resolved_root)

    try:
        path.lstat()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise CliConfigurationError("socket path is not observable") from exc
    else:
        raise CliConfigurationError("socket path already exists")

    parent = path.parent
    try:
        parent_stat = parent.lstat()
    except OSError as exc:
        raise CliConfigurationError(
            "socket parent must be an existing real directory"
        ) from exc
    if stat.S_ISLNK(parent_stat.st_mode) or not stat.S_ISDIR(parent_stat.st_mode):
        raise CliConfigurationError(
            "socket parent must be an existing real directory"
        )
    if parent != resolved_root and parent_stat.st_uid != effective_uid:
        raise CliConfigurationError("socket parent must be owned by the current user")


def _socket_identity(observed: os.stat_result) -> SocketIdentity:
    return (
        int(observed.st_dev),
        int(observed.st_ino),
        int(observed.st_uid),
        int(stat.S_IFMT(observed.st_mode)),
    )


def _observe_owned_socket(path: Path, *, effective_uid: int) -> tuple[os.stat_result, SocketIdentity]:
    try:
        observed = path.lstat()
    except OSError as exc:
        raise CliConfigurationError("bound socket path is not observable") from exc
    if observed.st_uid != effective_uid or not stat.S_ISSOCK(observed.st_mode):
        raise CliConfigurationError("bound socket identity is not current-user owned")
    return observed, _socket_identity(observed)


def _remove_owned_socket(
    path: Path,
    *,
    effective_uid: int,
    expected_identity: SocketIdentity,
) -> bool:
    try:
        current = path.lstat()
    except FileNotFoundError:
        return False
    if (
        current.st_uid != effective_uid
        or not stat.S_ISSOCK(current.st_mode)
        or _socket_identity(current) != expected_identity
    ):
        return False
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True


def main(argv: Sequence[str] | None = None) -> int:
    try:
        effective_uid = os.geteuid()
        config = validate_cli_configuration(
            parse_args(argv),
            effective_uid=effective_uid,
        )
        _prepare_socket_path(config.socket_path, effective_uid=effective_uid)
    except CliConfigurationError as exc:
        print(f"runtime-observability-sidecar configuration error: {exc}", file=sys.stderr)
        return 2

    stop = {"requested": False}

    def request_stop(_signum: int, _frame: object) -> None:
        stop["requested"] = True

    previous_umask = os.umask(0o077)
    receiver: socket.socket | None = None
    bound_identity: SocketIdentity | None = None
    try:
        receiver = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        receiver.bind(str(config.socket_path))
        _observed, bound_identity = _observe_owned_socket(
            config.socket_path,
            effective_uid=effective_uid,
        )
        os.chmod(config.socket_path, 0o600)
        observed_after_chmod, identity_after_chmod = _observe_owned_socket(
            config.socket_path,
            effective_uid=effective_uid,
        )
        if identity_after_chmod != bound_identity:
            raise CliConfigurationError("bound socket identity changed during setup")
        if stat.S_IMODE(observed_after_chmod.st_mode) != 0o600:
            raise CliConfigurationError("bound socket mode is not 0600")

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
            if receiver is not None:
                receiver.close()
        finally:
            try:
                if bound_identity is not None:
                    _remove_owned_socket(
                        config.socket_path,
                        effective_uid=effective_uid,
                        expected_identity=bound_identity,
                    )
            finally:
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
