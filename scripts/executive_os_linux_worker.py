#!/usr/bin/env python3
"""Linux/systemd entrypoint for one existing Executive Codex worker broker.

This is a service/package adapter only. It does not select workers, enroll provider
credentials, create Runtime state, reissue work, or bind a Capacity decision. The
existing ExecutiveWorkerBroker remains the sole worker lifecycle owner.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import platform
import re
import signal
import socket
import stat
import sys
from typing import Any, Mapping, Sequence

_ROOT = Path(__file__).resolve().parents[1]
if os.fspath(_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_ROOT))

from control_plane.codex_worker import (  # noqa: E402
    BinaryAttestationError,
    CodexWorkerAdapter,
    attest_codex_binary,
)
from control_plane.executive_ambient_process import NullAmbientClassifier  # noqa: E402
from control_plane.executive_worker_broker import (  # noqa: E402
    BrokerPolicy,
    DedicatedUIDSweeper,
    ExecutiveWorkerBroker,
    WorkerBrokerError,
)

CONFIG_SCHEMA = "mastermind.executive_linux_worker_broker_config/v1"
_CONFIG_FIELDS = frozenset(
    {
        "schema_version",
        "control_uid",
        "control_gid",
        "worker_uid",
        "worker_gid",
        "worker_user",
        "worker_id",
        "workspace_root",
        "run_root",
        "provider_home",
        "codex_binary",
        "allowed_codex_versions",
        "socket_path",
        "uid_sweep_receipt",
        "operator_harness_armed",
    }
)
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,127}$")
_USER_RE = re.compile(r"^_?[A-Za-z][A-Za-z0-9_-]{0,63}$")


class LinuxWorkerConfigError(WorkerBrokerError):
    """Linux worker package/configuration refusal."""


def _integer(value: Any, *, name: str) -> int:
    if type(value) is not int or not 1 <= value < 2**31:
        raise LinuxWorkerConfigError(f"{name} is invalid")
    return int(value)


def _absolute_path(value: Any, *, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise LinuxWorkerConfigError(f"{name} is invalid")
    path = Path(value)
    if not path.is_absolute():
        raise LinuxWorkerConfigError(f"{name} must be absolute")
    return str(path)


def load_linux_worker_config(
    path: Path,
    *,
    require_root_owner: bool = True,
) -> dict[str, Any]:
    """Load one secret-free, closed Linux worker definition."""

    lexical = Path(path)
    if not lexical.is_absolute():
        raise LinuxWorkerConfigError("worker config path must be absolute")
    try:
        info = lexical.lstat()
    except OSError as exc:
        raise LinuxWorkerConfigError("worker config is unavailable") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise LinuxWorkerConfigError("worker config must be one direct regular file")
    if require_root_owner and info.st_uid != 0:
        raise LinuxWorkerConfigError("worker config must be root-owned")
    if stat.S_IMODE(info.st_mode) & 0o022:
        raise LinuxWorkerConfigError("worker config must not be group/other writable")
    if info.st_size > 32 * 1024:
        raise LinuxWorkerConfigError("worker config exceeds its size limit")
    try:
        value = json.loads(lexical.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LinuxWorkerConfigError("worker config is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict) or set(value) != _CONFIG_FIELDS:
        raise LinuxWorkerConfigError("worker config fields do not match the schema")
    if value.get("schema_version") != CONFIG_SCHEMA:
        raise LinuxWorkerConfigError("worker config schema version is unsupported")

    normalized = dict(value)
    for field in ("control_uid", "control_gid", "worker_uid", "worker_gid"):
        normalized[field] = _integer(value.get(field), name=field)
    if normalized["control_uid"] == normalized["worker_uid"]:
        raise LinuxWorkerConfigError("control and worker principals must be distinct")
    if normalized["control_gid"] == normalized["worker_gid"]:
        raise LinuxWorkerConfigError("control and worker groups must be distinct")
    if require_root_owner and (
        info.st_gid != normalized["worker_gid"] or stat.S_IMODE(info.st_mode) != 0o440
    ):
        raise LinuxWorkerConfigError(
            "production worker config must be root:worker-group mode 0440"
        )

    user = value.get("worker_user")
    worker_id = value.get("worker_id")
    if not isinstance(user, str) or _USER_RE.fullmatch(user) is None:
        raise LinuxWorkerConfigError("worker_user is invalid")
    if not isinstance(worker_id, str) or _ID_RE.fullmatch(worker_id) is None:
        raise LinuxWorkerConfigError("worker_id is invalid")

    for field in (
        "workspace_root",
        "run_root",
        "provider_home",
        "codex_binary",
        "socket_path",
        "uid_sweep_receipt",
    ):
        normalized[field] = _absolute_path(value.get(field), name=field)

    versions = value.get("allowed_codex_versions")
    if (
        not isinstance(versions, list)
        or not 1 <= len(versions) <= 4
        or len(set(versions)) != len(versions)
        or any(
            not isinstance(item, str)
            or not item
            or item != item.strip()
            or len(item) > 64
            for item in versions
        )
    ):
        raise LinuxWorkerConfigError("allowed_codex_versions is invalid")
    if value.get("operator_harness_armed") is not False:
        raise LinuxWorkerConfigError("Linux v1 worker cannot arm the Operator Harness")
    normalized["allowed_codex_versions"] = list(versions)
    normalized["operator_harness_armed"] = False
    return normalized


def _require_worker_directories(config: Mapping[str, Any]) -> None:
    for field in ("workspace_root", "run_root", "provider_home"):
        path = Path(str(config[field]))
        try:
            info = path.lstat()
        except OSError as exc:
            raise LinuxWorkerConfigError(f"{field} is unavailable") from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise LinuxWorkerConfigError(f"{field} must be a direct directory")
        if info.st_uid != int(config["worker_uid"]):
            raise LinuxWorkerConfigError(f"{field} is not owned by the worker")
        if stat.S_IMODE(info.st_mode) & 0o022:
            raise LinuxWorkerConfigError(f"{field} is group/other writable")


def build_linux_worker_broker(config: Mapping[str, Any]) -> ExecutiveWorkerBroker:
    """Compose the existing one-worker broker for a dedicated Linux principal."""

    worker_uid = int(config["worker_uid"])
    worker_gid = int(config["worker_gid"])
    if os.geteuid() != worker_uid or os.getegid() != worker_gid:
        raise LinuxWorkerConfigError("worker broker is not running as its configured OS principal")
    observed_groups = set(os.getgroups()) - {worker_gid}
    if observed_groups:
        raise LinuxWorkerConfigError("Linux worker principal has supplementary groups")
    _require_worker_directories(config)

    try:
        binary = attest_codex_binary(
            Path(str(config["codex_binary"])),
            allowed_versions=frozenset(config["allowed_codex_versions"]),
            required_team_identifier=None,
        )
    except BinaryAttestationError as exc:
        raise LinuxWorkerConfigError("Linux Codex binary attestation refused") from exc
    if binary.uid != 0:
        raise LinuxWorkerConfigError("Linux Codex binary must be root-owned")
    if binary.team_identifier is not None:
        raise LinuxWorkerConfigError("Linux Codex binary unexpectedly carries an Apple team identity")

    policy = BrokerPolicy(
        control_uid=int(config["control_uid"]),
        worker_uid=worker_uid,
        worker_gid=worker_gid,
        allowed_supplementary_gids=frozenset(),
        worker_user=str(config["worker_user"]),
        worker_id=str(config["worker_id"]),
        workspace_root=Path(str(config["workspace_root"])),
        run_root=Path(str(config["run_root"])),
        provider_home=Path(str(config["provider_home"])),
        require_secret_canary=True,
    )
    adapter = CodexWorkerAdapter(
        Path(str(config["codex_binary"])),
        codex_home=Path(str(config["provider_home"])),
        binary_attestation=binary,
        allowed_versions=frozenset(config["allowed_codex_versions"]),
        required_team_identifier=None,
    )
    sweeper = DedicatedUIDSweeper(
        worker_uid,
        receipt_path=Path(str(config["uid_sweep_receipt"])),
        ambient_classifier=NullAmbientClassifier(),
    )
    return ExecutiveWorkerBroker(
        adapter,
        policy,
        sweeper,
        adapter_id="codex-cli",
        operator_harness_armed=False,
    )


def activate_systemd_socket(
    expected_path: Path,
    *,
    expected_owner_uid: int,
    expected_group_gid: int,
    expected_mode: int = 0o600,
    env: Mapping[str, str] | None = None,
    fd: int = 3,
    duplicate_fd: bool = True,
) -> socket.socket:
    """Adopt exactly one systemd-owned AF_UNIX listener; never bind a fallback."""

    values = os.environ if env is None else env
    if values.get("LISTEN_PID") != str(os.getpid()):
        raise LinuxWorkerConfigError("systemd listener PID binding is invalid")
    if values.get("LISTEN_FDS") != "1":
        raise LinuxWorkerConfigError("exactly one systemd listener is required")
    if values.get("LISTEN_FDNAMES") != "worker":
        raise LinuxWorkerConfigError("systemd listener name is invalid")

    path = Path(expected_path)
    try:
        visible = path.lstat()
    except OSError as exc:
        raise LinuxWorkerConfigError("systemd worker socket path is unavailable") from exc
    if not stat.S_ISSOCK(visible.st_mode):
        raise LinuxWorkerConfigError("systemd worker socket is not a Unix socket")
    if visible.st_uid != int(expected_owner_uid) or visible.st_gid != int(expected_group_gid):
        raise LinuxWorkerConfigError("systemd worker socket owner is invalid")
    if stat.S_IMODE(visible.st_mode) != int(expected_mode):
        raise LinuxWorkerConfigError("systemd worker socket mode is invalid")

    try:
        listener = (
            socket.fromfd(fd, socket.AF_UNIX, socket.SOCK_STREAM)
            if duplicate_fd
            else socket.socket(fileno=fd)
        )
    except OSError as exc:
        raise LinuxWorkerConfigError("systemd worker listener could not be adopted") from exc
    try:
        if listener.family != socket.AF_UNIX or listener.type & socket.SOCK_STREAM == 0:
            raise LinuxWorkerConfigError("systemd worker listener has the wrong socket type")
        if os.fspath(listener.getsockname()) != os.fspath(path):
            raise LinuxWorkerConfigError("systemd worker listener path differs from config")
        if hasattr(socket, "SO_ACCEPTCONN"):
            try:
                accepting = listener.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN)
            except OSError as exc:
                if platform.system() == "Linux":
                    raise LinuxWorkerConfigError(
                        "systemd worker listener accept state is unavailable"
                    ) from exc
            else:
                if accepting != 1:
                    raise LinuxWorkerConfigError("systemd worker listener is not listening")
        listener.setblocking(False)
        return listener
    except BaseException:
        if duplicate_fd:
            listener.close()
        else:
            listener.detach()
        raise


async def serve_linux_worker(config: Mapping[str, Any]) -> None:
    if platform.system() != "Linux":
        raise LinuxWorkerConfigError("Linux worker service requires Linux")
    broker = build_linux_worker_broker(config)
    listener = activate_systemd_socket(
        Path(str(config["socket_path"])),
        expected_owner_uid=int(config["control_uid"]),
        expected_group_gid=int(config["control_gid"]),
    )
    broker_task = asyncio.create_task(broker.serve(listener))
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()

    def request_stop() -> None:
        stopping.set()

    for signum in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(signum, request_stop)
        except NotImplementedError:  # pragma: no cover - Unix service only
            pass
    stop_task = asyncio.create_task(stopping.wait())
    done, _ = await asyncio.wait(
        {broker_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
    )
    if broker_task in done:
        stop_task.cancel()
        await asyncio.gather(stop_task, return_exceptions=True)
        await broker_task
        return
    broker_task.cancel()
    await asyncio.gather(broker_task, return_exceptions=True)
    try:
        await broker.shutdown()
    finally:
        listener.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Linux Executive worker broker service")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("check-config", "serve"):
        child = sub.add_parser(command)
        child.add_argument("--config", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        config = load_linux_worker_config(Path(args.config))
        if args.command == "check-config":
            sys.stdout.write(
                json.dumps(
                    {
                        "schema": "mastermind.executive_linux_worker_check/v1",
                        "ok": True,
                        "worker_id": config["worker_id"],
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )
            return 0
        asyncio.run(serve_linux_worker(config))
        return 0
    except (LinuxWorkerConfigError, WorkerBrokerError, OSError, ValueError) as exc:
        sys.stderr.write(
            json.dumps(
                {
                    "schema": "mastermind.executive_linux_worker_check/v1",
                    "ok": False,
                    "code": type(exc).__name__,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        return 65


if __name__ == "__main__":
    raise SystemExit(main())
