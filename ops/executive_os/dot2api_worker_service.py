"""Installed host composition for one read-only Dot2API Executive worker.

This is a provider-specific construction boundary over the existing Executive
WorkerBroker. It owns no Job, Attempt, Worker, retry, queue, placement, routing,
or result state. Dot2API remains a provider-local transport; Executive OS keeps
the canonical lifecycle.
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import hashlib
import ipaddress
import json
import os
import re
import signal
import stat
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Mapping, Sequence

from control_plane.dot2api_worker import Dot2ApiWorkerAdapter
from control_plane.executive_ambient_process import DarwinDistnotedClassifier
from control_plane.executive_worker_broker import (
    BrokerPolicy,
    DedicatedUIDSweeper,
    ExecutiveWorkerBroker,
    WorkerBrokerError,
    activate_launchd_socket,
)
from control_plane.worker_adapter import construct_reviewed_adapter
from integrations.dot2api.client import Dot2ApiClient

CONFIG_SCHEMA_VERSION = "mastermind.executive_dot2api_worker_config/v1"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FIELDS = frozenset(
    {
        "schema_version",
        "control_uid",
        "worker_uid",
        "worker_gid",
        "allowed_supplementary_gids",
        "worker_user",
        "worker_id",
        "workspace_root",
        "run_root",
        "provider_home",
        "python_binary",
        "python_binary_sha256",
        "transport_script_sha256",
        "dot2api_base_url",
        "dot2api_token_path",
        "queue",
        "poll_seconds",
        "submission_timeout_seconds",
        "launchd_socket_name",
        "uid_sweep_receipt",
        "require_secret_canary",
        "operator_harness_armed",
    }
)
_MAX_CONFIG_BYTES = 64 * 1024
_MAX_BINARY_BYTES = 1024 * 1024 * 1024
_MAX_TOKEN_BYTES = 4096


class Dot2ApiWorkerServiceError(ValueError):
    """One fail-closed, secret-free installed-composition refusal."""


@dataclasses.dataclass(frozen=True)
class Dot2ApiWorkerServiceConfig:
    schema_version: str
    control_uid: int
    worker_uid: int
    worker_gid: int
    allowed_supplementary_gids: frozenset[int]
    worker_user: str
    worker_id: str
    workspace_root: Path
    run_root: Path
    provider_home: Path
    python_binary: Path
    python_binary_sha256: str
    transport_script_sha256: str
    dot2api_base_url: str
    dot2api_token_path: Path
    queue: str
    poll_seconds: float
    submission_timeout_seconds: float
    launchd_socket_name: str
    uid_sweep_receipt: Path
    require_secret_canary: bool
    operator_harness_armed: bool


def _strict_json(raw: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    try:
        return json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                ValueError("non-finite JSON constant")
            ),
        )
    except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError):
        raise Dot2ApiWorkerServiceError("worker config is not strict UTF-8 JSON") from None


def _config_file(path: Path, *, require_root_owner: bool) -> Mapping[str, Any]:
    lexical = Path(path)
    if not lexical.is_absolute():
        raise Dot2ApiWorkerServiceError("worker config path must be absolute")
    try:
        before = lexical.lstat()
        if (
            stat.S_ISLNK(before.st_mode)
            or not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) & 0o022
            or (require_root_owner and before.st_uid != 0)
            or before.st_size <= 0
            or before.st_size > _MAX_CONFIG_BYTES
        ):
            raise Dot2ApiWorkerServiceError("worker config file identity is invalid")
        raw = lexical.read_bytes()
        after = lexical.lstat()
    except OSError as exc:
        raise Dot2ApiWorkerServiceError("worker config is unavailable") from exc
    if (
        len(raw) != before.st_size
        or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    ):
        raise Dot2ApiWorkerServiceError("worker config changed while reading")
    value = _strict_json(raw)
    if type(value) is not dict or set(value) != _FIELDS:
        raise Dot2ApiWorkerServiceError("worker config fields do not match the schema")
    return value


def _positive_int(value: Any, field: str) -> int:
    if type(value) is not int or value <= 0 or value >= 2**31:
        raise Dot2ApiWorkerServiceError(f"{field} is invalid")
    return value


def _absolute(value: Any, field: str) -> Path:
    if type(value) is not str or not value or not Path(value).is_absolute():
        raise Dot2ApiWorkerServiceError(f"{field} must be an absolute path")
    return Path(value)


def _real_directory(path: Path, *, owner_uid: int | None = None, private: bool = False) -> Path:
    try:
        info = path.lstat()
        resolved = path.resolve(strict=True)
        resolved_info = resolved.lstat()
    except OSError as exc:
        raise Dot2ApiWorkerServiceError("worker directory is unavailable") from exc
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISDIR(resolved_info.st_mode)
        or (owner_uid is not None and resolved_info.st_uid != owner_uid)
        or (private and stat.S_IMODE(resolved_info.st_mode) & 0o077)
    ):
        raise Dot2ApiWorkerServiceError("worker directory identity is invalid")
    return resolved


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=True))
        return True
    except (OSError, ValueError):
        return False


def _normalize_base_url(value: Any) -> str:
    if type(value) is not str:
        raise Dot2ApiWorkerServiceError("Dot2API base URL is invalid")
    try:
        normalized = Dot2ApiClient(value, token_loader=lambda: "validation-only").base_url
        parsed = urllib.parse.urlsplit(normalized)
        host = parsed.hostname or ""
        is_loopback = host.lower() == "localhost" or ipaddress.ip_address(host).is_loopback
    except (ValueError, TypeError):
        raise Dot2ApiWorkerServiceError("Dot2API base URL must be loopback") from None
    if not is_loopback or normalized != value.rstrip("/"):
        raise Dot2ApiWorkerServiceError("Dot2API base URL must be loopback")
    return normalized


def _digest(value: Any, field: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise Dot2ApiWorkerServiceError(f"{field} must be SHA-256")
    return value


def _file_sha256(path: Path, *, maximum: int = _MAX_BINARY_BYTES) -> str:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > maximum:
                    raise Dot2ApiWorkerServiceError("installed file exceeds its digest ceiling")
                digest.update(chunk)
    except OSError as exc:
        raise Dot2ApiWorkerServiceError("installed file is unavailable") from exc
    if size <= 0:
        raise Dot2ApiWorkerServiceError("installed file is empty")
    return digest.hexdigest()


def _token_metadata(config: Dot2ApiWorkerServiceConfig) -> tuple[int, int, int, int]:
    path = config.dot2api_token_path
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            info = os.fstat(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise Dot2ApiWorkerServiceError("Dot2API credential is unavailable") from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != config.worker_uid
        or info.st_gid != config.worker_gid
        or stat.S_IMODE(info.st_mode) & 0o077
        or info.st_size < 20
        or info.st_size > _MAX_TOKEN_BYTES
    ):
        raise Dot2ApiWorkerServiceError("Dot2API credential file identity is invalid")
    return int(info.st_dev), int(info.st_ino), int(info.st_size), int(info.st_mtime_ns)


def load_dot2api_worker_config(
    path: Path | str, *, require_root_owner: bool = True
) -> Dot2ApiWorkerServiceConfig:
    raw = _config_file(Path(path), require_root_owner=require_root_owner)
    if raw["schema_version"] != CONFIG_SCHEMA_VERSION:
        raise Dot2ApiWorkerServiceError("worker config schema is unsupported")
    control_uid = _positive_int(raw["control_uid"], "control_uid")
    worker_uid = _positive_int(raw["worker_uid"], "worker_uid")
    worker_gid = _positive_int(raw["worker_gid"], "worker_gid")
    if control_uid == worker_uid:
        raise Dot2ApiWorkerServiceError("control and worker principals must differ")
    groups = raw["allowed_supplementary_gids"]
    if (
        type(groups) is not list
        or any(type(item) is not int or item <= 0 for item in groups)
        or groups != sorted(set(groups))
        or worker_gid in groups
        or len(groups) > 8
    ):
        raise Dot2ApiWorkerServiceError("allowed supplementary groups are invalid")
    worker_user = raw["worker_user"]
    worker_id = raw["worker_id"]
    queue = raw["queue"]
    launchd_socket_name = raw["launchd_socket_name"]
    if type(worker_user) is not str or not worker_user or any(ch.isspace() for ch in worker_user):
        raise Dot2ApiWorkerServiceError("worker_user is invalid")
    for value, field in (
        (worker_id, "worker_id"),
        (queue, "queue"),
        (launchd_socket_name, "launchd_socket_name"),
    ):
        if type(value) is not str or _ID_RE.fullmatch(value) is None:
            raise Dot2ApiWorkerServiceError(f"{field} is invalid")
    workspace = _real_directory(_absolute(raw["workspace_root"], "workspace_root"))
    run_root = _real_directory(_absolute(raw["run_root"], "run_root"))
    provider_home = _real_directory(
        _absolute(raw["provider_home"], "provider_home"),
        owner_uid=worker_uid,
        private=True,
    )
    roots = (workspace, run_root, provider_home)
    for index, left in enumerate(roots):
        for right in roots[index + 1 :]:
            if _within(left, right) or _within(right, left):
                raise Dot2ApiWorkerServiceError("worker filesystem roots must be disjoint")
    python_binary = _absolute(raw["python_binary"], "python_binary")
    token_path = _absolute(raw["dot2api_token_path"], "dot2api_token_path")
    if not _within(token_path, provider_home):
        raise Dot2ApiWorkerServiceError("Dot2API credential must remain under provider_home")
    receipt = _absolute(raw["uid_sweep_receipt"], "uid_sweep_receipt")
    if not _within(receipt, run_root):
        raise Dot2ApiWorkerServiceError("UID sweep receipt must remain under run_root")
    poll = raw["poll_seconds"]
    submit_timeout = raw["submission_timeout_seconds"]
    if type(poll) not in (int, float) or not 0.05 <= float(poll) <= 30.0:
        raise Dot2ApiWorkerServiceError("poll_seconds is invalid")
    if type(submit_timeout) not in (int, float) or not 1.0 <= float(submit_timeout) <= 120.0:
        raise Dot2ApiWorkerServiceError("submission_timeout_seconds is invalid")
    if raw["require_secret_canary"] is not True:
        raise Dot2ApiWorkerServiceError("Dot2API worker must require the secret canary")
    if raw["operator_harness_armed"] is not False:
        raise Dot2ApiWorkerServiceError("Dot2API worker cannot arm the Operator Harness")
    config = Dot2ApiWorkerServiceConfig(
        schema_version=CONFIG_SCHEMA_VERSION,
        control_uid=control_uid,
        worker_uid=worker_uid,
        worker_gid=worker_gid,
        allowed_supplementary_gids=frozenset(groups),
        worker_user=worker_user,
        worker_id=worker_id,
        workspace_root=workspace,
        run_root=run_root,
        provider_home=provider_home,
        python_binary=python_binary,
        python_binary_sha256=_digest(raw["python_binary_sha256"], "python_binary_sha256"),
        transport_script_sha256=_digest(
            raw["transport_script_sha256"], "transport_script_sha256"
        ),
        dot2api_base_url=_normalize_base_url(raw["dot2api_base_url"]),
        dot2api_token_path=token_path,
        queue=queue,
        poll_seconds=float(poll),
        submission_timeout_seconds=float(submit_timeout),
        launchd_socket_name=launchd_socket_name,
        uid_sweep_receipt=receipt,
        require_secret_canary=True,
        operator_harness_armed=False,
    )
    _token_metadata(config)
    return config


def read_dot2api_token(config: Dot2ApiWorkerServiceConfig) -> str:
    if type(config) is not Dot2ApiWorkerServiceConfig:
        raise TypeError("Dot2API worker config is required")
    expected = _token_metadata(config)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(config.dot2api_token_path, flags)
        try:
            before = os.fstat(descriptor)
            raw = os.read(descriptor, _MAX_TOKEN_BYTES + 1)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise Dot2ApiWorkerServiceError("Dot2API credential is unavailable") from exc
    observed = (int(before.st_dev), int(before.st_ino), int(before.st_size), int(before.st_mtime_ns))
    after_identity = (
        int(after.st_dev), int(after.st_ino), int(after.st_size), int(after.st_mtime_ns)
    )
    if observed != expected or after_identity != expected or len(raw) != before.st_size:
        raise Dot2ApiWorkerServiceError("Dot2API credential changed while reading")
    if raw.endswith(b"\n"):
        raw = raw[:-1]
        if raw.endswith(b"\r"):
            raw = raw[:-1]
    try:
        token = raw.decode("ascii", errors="strict")
    except UnicodeError:
        raise Dot2ApiWorkerServiceError("Dot2API credential format is invalid") from None
    if not 20 <= len(token) <= _MAX_TOKEN_BYTES or any(ord(ch) < 33 or ord(ch) > 126 for ch in token):
        raise Dot2ApiWorkerServiceError("Dot2API credential format is invalid")
    return token


def build_dot2api_worker_broker(
    config: Dot2ApiWorkerServiceConfig, *, release_root: Path | str
) -> ExecutiveWorkerBroker:
    if type(config) is not Dot2ApiWorkerServiceConfig:
        raise TypeError("Dot2API worker config is required")
    root = Path(release_root).resolve(strict=True)
    transport_script = root / "ops" / "executive_os" / "dot2api_transport_worker.py"
    if _file_sha256(config.python_binary) != config.python_binary_sha256:
        raise Dot2ApiWorkerServiceError("Python binary digest differs from worker config")
    if _file_sha256(transport_script, maximum=1024 * 1024) != config.transport_script_sha256:
        raise Dot2ApiWorkerServiceError("transport script digest differs from worker config")
    adapter = construct_reviewed_adapter(
        "dot2api",
        config.dot2api_base_url,
        credential_loader=lambda: read_dot2api_token(config),
        queue=config.queue,
        poll_seconds=config.poll_seconds,
        submission_timeout_seconds=config.submission_timeout_seconds,
        python_path=config.python_binary,
        transport_script=transport_script,
    )
    policy = BrokerPolicy(
        control_uid=config.control_uid,
        worker_uid=config.worker_uid,
        worker_gid=config.worker_gid,
        worker_user=config.worker_user,
        worker_id=config.worker_id,
        workspace_root=config.workspace_root,
        run_root=config.run_root,
        provider_home=config.provider_home,
        allowed_supplementary_gids=config.allowed_supplementary_gids,
        require_secret_canary=config.require_secret_canary,
    )
    sweeper = DedicatedUIDSweeper(
        config.worker_uid,
        receipt_path=config.uid_sweep_receipt,
        ambient_classifier=DarwinDistnotedClassifier(),
    )
    return ExecutiveWorkerBroker(
        adapter,
        policy,
        sweeper,
        adapter_id="dot2api",
        operator_harness_armed=False,
    )


async def _serve_broker(broker: ExecutiveWorkerBroker, socket_name: str) -> None:
    activated = None
    serve_task = stop_task = None
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()

    def stop() -> None:
        stopping.set()

    for signum in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(signum, stop)
        except NotImplementedError:  # pragma: no cover - Unix service only
            pass
    try:
        activated = activate_launchd_socket(socket_name)
        serve_task = asyncio.create_task(broker.serve(activated))
        stop_task = asyncio.create_task(stopping.wait())
        done, _ = await asyncio.wait(
            {serve_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if serve_task in done:
            await serve_task
    finally:
        for task in (serve_task, stop_task):
            if task is not None:
                task.cancel()
        await asyncio.gather(
            *(task for task in (serve_task, stop_task) if task is not None),
            return_exceptions=True,
        )
        try:
            await broker.shutdown()
        finally:
            if activated is not None:
                activated.close()
            for signum in (signal.SIGTERM, signal.SIGINT):
                try:
                    loop.remove_signal_handler(signum)
                except NotImplementedError:
                    pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run or validate the distinct-UID Executive Dot2API worker broker."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--config", type=Path, required=True)
    check = sub.add_parser("check-config")
    check.add_argument("--config", type=Path, required=True)
    check.add_argument("--allow-non-root-owner-for-test", action="store_true")
    return parser


def main(
    argv: Sequence[str] | None = None, *, release_root: Path | str | None = None
) -> int:
    args = _parser().parse_args(argv)
    root = Path(release_root or Path(__file__).resolve().parents[2]).resolve(strict=True)
    try:
        config = load_dot2api_worker_config(
            args.config,
            require_root_owner=(
                args.command == "serve"
                or not getattr(args, "allow_non_root_owner_for_test", False)
            ),
        )
        broker = build_dot2api_worker_broker(config, release_root=root)
        if args.command == "check-config":
            print(
                json.dumps(
                    {
                        "schema_version": config.schema_version,
                        "valid": True,
                        "worker_id": config.worker_id,
                        "worker_uid": config.worker_uid,
                        "launchd_socket_name": config.launchd_socket_name,
                    },
                    sort_keys=True,
                )
            )
            return 0
        if Path.cwd().resolve(strict=True) != root:
            raise Dot2ApiWorkerServiceError(
                "Dot2API worker must run from its installed release root"
            )
        asyncio.run(_serve_broker(broker, config.launchd_socket_name))
        return 0
    except (Dot2ApiWorkerServiceError, WorkerBrokerError, OSError, ValueError) as exc:
        print(f"dot2api worker service error: {exc}", file=sys.stderr)
        return 2


__all__ = [
    "CONFIG_SCHEMA_VERSION",
    "Dot2ApiWorkerServiceConfig",
    "Dot2ApiWorkerServiceError",
    "build_dot2api_worker_broker",
    "load_dot2api_worker_config",
    "main",
    "read_dot2api_token",
]
