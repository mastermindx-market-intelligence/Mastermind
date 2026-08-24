"""launchd entrypoint for the distinct-UID Executive Codex worker broker.

The JSON config is intentionally secret-free and root-owned.  Provider
authentication remains only in the dedicated worker ``CODEX_HOME`` referenced
by the config; no credential value is accepted on argv or in the plist.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import stat
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if os.fspath(_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_ROOT))

from control_plane.codex_worker import (
    BinaryAttestationError,
    CodexWorkerAdapter,
    load_codex_attestation_receipt,
)
from control_plane.codex_operator_adapter import CodexOperatorAdapter
from control_plane.executive_worker_broker import (
    BrokerPolicy,
    DedicatedUIDSweeper,
    ExecutiveWorkerBroker,
    WorkerBrokerError,
    activate_launchd_socket,
)
from control_plane.executive_ambient_process import DarwinDistnotedClassifier


CONFIG_SCHEMA_VERSION = "mastermind.executive_worker_broker_config/v4"
_OPENAI_TEAM_IDENTIFIER = "2DC432GLL2"
_REVIEWED_AMBIENT_GID_SETS = (
    frozenset({12, 61, 100}),
    frozenset({12, 61, 100, 396}),
)
_CONFIG_FIELDS = frozenset(
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
        "codex_binary",
        "codex_attestation_receipt",
        "allowed_codex_versions",
        "required_team_identifier",
        "launchd_socket_name",
        "uid_sweep_receipt",
        "require_secret_canary",
        "operator_harness_armed",
    }
)


class WorkerConfigError(WorkerBrokerError):
    """The root-owned worker configuration is unsafe or malformed."""


def _load_config(path: Path, *, require_root_owner: bool) -> dict[str, Any]:
    lexical = Path(path)
    if not lexical.is_absolute():
        raise WorkerConfigError("worker config path must be absolute")
    info = lexical.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise WorkerConfigError("worker config must be a regular non-symlink file")
    if stat.S_IMODE(info.st_mode) & 0o022:
        raise WorkerConfigError("worker config must not be writable by group or other")
    if require_root_owner and info.st_uid != 0:
        raise WorkerConfigError("worker config must be owned by root")
    try:
        raw = lexical.read_bytes()
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkerConfigError("worker config is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict) or set(value) != _CONFIG_FIELDS:
        raise WorkerConfigError("worker config fields do not match the schema")
    if value.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise WorkerConfigError("worker config schema version is unsupported")
    versions = value.get("allowed_codex_versions")
    if (
        not isinstance(versions, list)
        or not versions
        or len(versions) > 4
        or any(not isinstance(item, str) or not item for item in versions)
        or len(versions) != len(set(versions))
    ):
        raise WorkerConfigError("allowed_codex_versions must be a small non-empty set")
    for field in (
        "workspace_root",
        "run_root",
        "provider_home",
        "codex_binary",
        "codex_attestation_receipt",
        "uid_sweep_receipt",
    ):
        if not isinstance(value.get(field), str) or not Path(value[field]).is_absolute():
            raise WorkerConfigError(f"{field} must be an absolute path")
    if value.get("required_team_identifier") != _OPENAI_TEAM_IDENTIFIER:
        raise WorkerConfigError("the worker config must require the reviewed OpenAI team")
    if value.get("require_secret_canary") is not True:
        raise WorkerConfigError("production worker config must require the secret canary")
    if not isinstance(value.get("operator_harness_armed"), bool):
        raise WorkerConfigError("operator_harness_armed must be boolean")
    allowed_groups = value.get("allowed_supplementary_gids")
    if (
        not isinstance(allowed_groups, list)
        or len(allowed_groups) > 8
        or any(type(group_id) is not int or group_id <= 0 for group_id in allowed_groups)
        or allowed_groups != sorted(set(allowed_groups))
        or int(value["worker_gid"]) in allowed_groups
        or frozenset(allowed_groups) not in _REVIEWED_AMBIENT_GID_SETS
    ):
        raise WorkerConfigError("allowed supplementary groups are invalid")
    return value


def _build_broker(config: dict[str, Any]) -> ExecutiveWorkerBroker:
    policy = BrokerPolicy(
        control_uid=int(config["control_uid"]),
        worker_uid=int(config["worker_uid"]),
        worker_gid=int(config["worker_gid"]),
        allowed_supplementary_gids=frozenset(config["allowed_supplementary_gids"]),
        worker_user=str(config["worker_user"]),
        worker_id=str(config["worker_id"]),
        workspace_root=Path(config["workspace_root"]),
        run_root=Path(config["run_root"]),
        provider_home=Path(config["provider_home"]),
        require_secret_canary=True,
    )
    if os.geteuid() != policy.worker_uid or os.getegid() != policy.worker_gid:
        raise WorkerConfigError("worker broker is not running as its configured OS principal")
    # Fast, no-subprocess path: the receipt was attested once, warm, at
    # normal priority, by install.sh running as root.  Loading it here (one
    # open+fstat of the receipt, one open+fstat of the binary) is what keeps
    # a throttled, loaded worker daemon off the slow cold trust-service and
    # --version subprocess path that caused the real-host startup timeout
    # this mechanism fixes -- see
    # control_plane.codex_worker.load_codex_attestation_receipt.  There is no
    # fallback to attest_codex_binary here: a missing or unsafe receipt must
    # refuse to start, never silently re-pay the cost this removes.
    binary_attestation = load_codex_attestation_receipt(
        Path(config["codex_attestation_receipt"]),
        expected_binary_path=Path(config["codex_binary"]),
        expected_owner_gid=policy.worker_gid,
    )
    adapter = CodexWorkerAdapter(
        Path(config["codex_binary"]),
        binary_attestation=binary_attestation,
        allowed_versions=frozenset(config["allowed_codex_versions"]),
        required_team_identifier=str(config["required_team_identifier"]),
    )
    sweeper = DedicatedUIDSweeper(
        policy.worker_uid,
        receipt_path=Path(config["uid_sweep_receipt"]),
        ambient_classifier=DarwinDistnotedClassifier(),
    )

    def operator_adapter_factory(workspace: Path, turn_input_loader):
        return CodexOperatorAdapter(
            binary_path=Path(config["codex_binary"]),
            codex_home=Path(config["provider_home"]),
            workspace_root=workspace,
            worker_id=policy.worker_id,
            expected_harness_version=binary_attestation.version,
            network_policy="disabled",
            turn_input_loader=turn_input_loader,
        )

    return ExecutiveWorkerBroker(
        adapter,
        policy,
        sweeper,
        operator_adapter_factory=operator_adapter_factory,
        operator_harness_armed=bool(config["operator_harness_armed"]),
    )


async def _serve(config: dict[str, Any]) -> None:
    broker = _build_broker(config)
    activated = activate_launchd_socket(str(config["launchd_socket_name"]))
    task = asyncio.create_task(broker.serve(activated))
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
    done, _ = await asyncio.wait({task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
    if task in done:
        stop_task.cancel()
        await asyncio.gather(stop_task, return_exceptions=True)
        await task
        return
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    try:
        await broker.shutdown()
    finally:
        activated.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run or validate the distinct-UID Executive Codex worker broker."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="Claim the launchd socket and serve typed requests.")
    serve.add_argument("--config", type=Path, required=True)
    check = sub.add_parser("check-config", help="Validate a worker config without launching.")
    check.add_argument("--config", type=Path, required=True)
    check.add_argument(
        "--allow-non-root-owner-for-test",
        action="store_true",
        help="Test-only escape hatch; the launchd serve path always requires root ownership.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "serve" and Path.cwd().resolve(strict=True) != _ROOT:
            raise WorkerConfigError("worker must run from its installed release root")
        if args.command == "check-config":
            value = _load_config(
                args.config,
                require_root_owner=not args.allow_non_root_owner_for_test,
            )
            # install.sh runs check-config as the worker principal itself
            # (sudo -u "$WORKER_USER" ... check-config) -- the one moment
            # before launchd is trusted with the daemon that anything runs
            # AS the receipt's actual reader.  Exercise the exact
            # receipt-load step _build_broker takes at real startup here
            # too, so a broken or unreadable receipt fails installation
            # loudly and up front, not only later and silently when
            # launchd first starts the daemon.
            load_codex_attestation_receipt(
                Path(value["codex_attestation_receipt"]),
                expected_binary_path=Path(value["codex_binary"]),
                expected_owner_gid=int(value["worker_gid"]),
            )
            print(
                json.dumps(
                    {
                        "schema_version": CONFIG_SCHEMA_VERSION,
                        "valid": True,
                        "worker_id": value["worker_id"],
                        "worker_uid": value["worker_uid"],
                        "control_uid": value["control_uid"],
                        "launchd_socket_name": value["launchd_socket_name"],
                    },
                    sort_keys=True,
                )
            )
            return 0
        config = _load_config(args.config, require_root_owner=True)
        asyncio.run(_serve(config))
        return 0
    except (WorkerBrokerError, BinaryAttestationError, OSError, ValueError) as exc:
        # BinaryAttestationError (and its CodexAttestationReceiptError subclass
        # raised by _build_broker) is not a WorkerBrokerError -- without this
        # arm a fail-closed receipt/identity refusal would propagate as a raw
        # Python traceback instead of the one clean, bounded line below, which
        # is the operator's actual diagnostic surface in worker stderr.
        print(f"worker broker error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
