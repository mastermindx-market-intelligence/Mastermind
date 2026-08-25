"""launchd entrypoint for the distinct-UID Executive Codex worker broker.

The JSON config is intentionally secret-free and root-owned.  Provider
authentication remains only in the dedicated worker ``CODEX_HOME`` referenced
by the config; no credential value is accepted on argv or in the plist.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Mapping

_ROOT = Path(__file__).resolve().parents[1]
if os.fspath(_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_ROOT))

from control_plane.codex_worker import (
    BinaryAttestationError,
    CodexWorkerAdapter,
    load_codex_attestation_receipt,
)
from control_plane.codex_operator_adapter import CodexOperatorAdapter
from control_plane.executive_autonomy import (
    AutonomyRefusal,
    sha256_file,
    validate_runtime_guard_file,
)
from control_plane.executive_agent_capabilities import (
    CapabilityPolicyError,
    ExecutionCapabilityRegistry,
)
from control_plane.executive_canary import (
    PrincipalIdentity,
    SecretCanaryConfig,
    SecretCanaryError,
    run_secret_canary,
)
from control_plane.executive_worker_broker import (
    BrokerPolicy,
    DedicatedUIDSweeper,
    ExecutiveWorkerBroker,
    WorkerBrokerError,
    activate_launchd_socket,
)
from control_plane.executive_ambient_process import DarwinDistnotedClassifier


CONFIG_SCHEMA_VERSION = "mastermind.executive_worker_broker_config/v4"
AUTONOMY_RECEIPT = Path(
    "/Library/Application Support/MastermindExecutive/config/autonomy-state-v1.json"
)
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
_CONTROL_ENV_ATTESTATION_FIELDS = frozenset(
    {
        "schema_version",
        "observed_at",
        "process_identity",
        "config_sha256",
        "release_manifest_sha256",
        "release_commit_sha",
        "python_executable_path",
        "python_executable_sha256",
        "sentinel_name_sha256",
        "sentinel_value_sha256",
        "sentinel_present",
    }
)
_CONTROL_PROCESS_IDENTITY_FIELDS = frozenset(
    {
        "pid",
        "pgid",
        "session_id",
        "start_identity",
        "boot_id",
        "effective_uid",
        "effective_gid",
        "real_uid",
        "real_gid",
    }
)
_CONTROL_ENV_SENTINEL = "EXECUTIVE_CONTROL_CANARY_VALUE"
_CONTROL_LABEL = "com.mastermind.executive.control"
_SECRET_CANARY_ENVELOPE_SCHEMA_VERSION = (
    "mastermind.executive_secret_canary_envelope/v1"
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


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _run_environment_probe(argv: list[str]) -> Mapping[str, Any]:
    completed = subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=20,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"},
    )
    if len(completed.stdout) > 256 * 1024 or len(completed.stderr) > 64 * 1024:
        raise WorkerConfigError("autonomy environment probe output exceeds the bound")
    if completed.returncode != 0:
        raise WorkerConfigError("autonomy environment probe refused")
    try:
        value = json.loads(completed.stdout.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkerConfigError("autonomy environment probe returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise WorkerConfigError("autonomy environment probe returned no object")
    return value


def _build_autonomy_canary_factory(
    config: Mapping[str, Any],
    *,
    release_root: Path = _ROOT,
    environment_probe_runner: Callable[[list[str]], Mapping[str, Any]] = (
        _run_environment_probe
    ),
    secret_canary_runner: Callable[[SecretCanaryConfig], Mapping[str, Any]] = (
        run_secret_canary
    ),
) -> Callable[[Mapping[str, Any]], Mapping[str, Any]]:
    """Bind boot re-attestation to fixed installed paths and no provider call."""

    workspace_root = Path(str(config["workspace_root"])).resolve(strict=True)
    run_root = Path(str(config["run_root"])).resolve(strict=True)
    provider_home = Path(str(config["provider_home"])).resolve(strict=True)
    runtime_root = workspace_root.parents[1]
    worker_id = str(config["worker_id"])
    if (
        workspace_root != runtime_root / "jobs" / "workspaces"
        or run_root != runtime_root / "jobs" / "runs"
        or provider_home
        != runtime_root / "workers" / worker_id / "provider-home"
    ):
        raise WorkerConfigError("armed worker paths do not match the fixed host layout")
    release_root = Path(release_root).resolve(strict=True)
    release_sha = release_root.name
    manifest = release_root / ".executive-release-manifest.json"
    if (
        re.fullmatch(r"[0-9a-f]{40}", release_sha) is None
        or not manifest.is_file()
    ):
        raise WorkerConfigError("armed worker release identity is unavailable")
    manifest_sha256 = sha256_file(manifest)
    probe_script = release_root / "scripts" / "executive_os_phase1c_env_probe.py"
    if not probe_script.is_file():
        raise WorkerConfigError("autonomy environment probe is unavailable")

    def issue(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        if set(payload) != {"control_environment_attestation"}:
            raise WorkerConfigError("autonomy canary request fields differ")
        attestation = payload.get("control_environment_attestation")
        if (
            not isinstance(attestation, Mapping)
            or set(attestation) != _CONTROL_ENV_ATTESTATION_FIELDS
            or attestation.get("schema_version")
            != "mastermind.executive_control_environment_attestation/v1"
            or attestation.get("sentinel_present") is not True
            or attestation.get("release_commit_sha") != release_sha
            or attestation.get("release_manifest_sha256") != manifest_sha256
            or attestation.get("sentinel_name_sha256")
            != hashlib.sha256(_CONTROL_ENV_SENTINEL.encode()).hexdigest()
        ):
            raise WorkerConfigError("control environment attestation differs")
        identity = attestation.get("process_identity")
        digest_fields = (
            "config_sha256",
            "python_executable_sha256",
            "sentinel_value_sha256",
        )
        if (
            not isinstance(identity, Mapping)
            or set(identity) != _CONTROL_PROCESS_IDENTITY_FIELDS
            or any(
                type(identity.get(field)) is not int
                for field in (
                    "pid",
                    "pgid",
                    "session_id",
                    "effective_uid",
                    "effective_gid",
                    "real_uid",
                    "real_gid",
                )
            )
            or any(
                not isinstance(identity.get(field), str) or not identity[field]
                for field in ("start_identity", "boot_id")
            )
            or int(identity["pid"]) <= 1
            or int(identity["effective_uid"]) != int(config["control_uid"])
            or int(identity["real_uid"]) != int(config["control_uid"])
            or int(identity["effective_gid"]) <= 0
            or int(identity["real_gid"]) != int(identity["effective_gid"])
            or any(
                not isinstance(attestation.get(field), str)
                or re.fullmatch(r"[0-9a-f]{64}", str(attestation[field])) is None
                for field in digest_fields
            )
        ):
            raise WorkerConfigError("control environment process identity differs")
        environment_probe = dict(
            environment_probe_runner(
                [
                    sys.executable,
                    "-I",
                    "-S",
                    "-B",
                    os.fspath(probe_script),
                    "--pid",
                    str(identity["pid"]),
                    "--label",
                    _CONTROL_LABEL,
                    "--sentinel-name",
                    _CONTROL_ENV_SENTINEL,
                    "--sentinel-value-sha256",
                    str(attestation["sentinel_value_sha256"]),
                    "--config-sha256",
                    str(attestation["config_sha256"]),
                    "--release-manifest-sha256",
                    manifest_sha256,
                    "--control-process-identity-json",
                    json.dumps(
                        dict(identity),
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                        allow_nan=False,
                    ),
                    "--expected-worker-uid",
                    str(config["worker_uid"]),
                    "--expected-worker-gid",
                    str(config["worker_gid"]),
                ]
            )
        )
        environment_probe_sha256 = _canonical_sha256(environment_probe)
        canary_config = SecretCanaryConfig(
            expected_worker_uid=int(config["worker_uid"]),
            expected_worker_gid=int(config["worker_gid"]),
            control_uid=int(config["control_uid"]),
            control_gid=int(identity["effective_gid"]),
            control_environment_sentinel=_CONTROL_ENV_SENTINEL,
            control_environment_probe_sha256=environment_probe_sha256,
            administrative_checkout_sentinel=(
                runtime_root
                / "control"
                / "admin-checkout"
                / release_sha
                / ".git"
                / "executive-secret-canary"
            ),
            executive_database=(
                runtime_root
                / "control"
                / "db"
                / "data"
                / "control_plane"
                / "executive.sqlite3"
            ),
            other_worker_home_sentinel=(
                runtime_root / "canary-fixtures" / "other-worker-home" / "sentinel"
            ),
            forbidden_production_sentinel=(
                runtime_root / "canary-fixtures" / "production-like" / "sentinel"
            ),
            codex_home=provider_home,
        )
        try:
            secret_canary = dict(secret_canary_runner(canary_config))
        except SecretCanaryError as exc:
            raise WorkerConfigError("autonomy secret canary refused") from exc
        return {
            "schema_version": _SECRET_CANARY_ENVELOPE_SCHEMA_VERSION,
            "secret_canary": secret_canary,
            "control_environment_probe": environment_probe,
            "control_environment_probe_sha256": environment_probe_sha256,
        }

    return issue


def _build_broker(
    config: dict[str, Any],
    *,
    autonomy_guard=None,
) -> ExecutiveWorkerBroker:
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

    try:
        capability_registry = ExecutionCapabilityRegistry.load()
    except CapabilityPolicyError as exc:
        raise WorkerConfigError(f"worker capability policy is invalid: {exc}") from exc

    def operator_adapter_factory(workspace: Path, turn_input_loader, requested):
        matching = []
        for profile in capability_registry.profiles.values():
            if not profile.enabled or profile.execution_surface != "codex-app-server":
                continue
            try:
                manifest = profile.capability_manifest(
                    harness_binary_digest=requested.harness_binary_digest
                )
            except CapabilityPolicyError:
                continue
            if (
                manifest == requested.capabilities
                and profile.sandbox_policy == requested.sandbox_policy
                and profile.approval_policy == requested.approval_policy
                and profile.network_policy == requested.network_policy
                and profile.write_capable == requested.write_capable
                and profile.native_helper_policy == requested.native_helper_policy
                and profile.expected_config_digest == requested.expected_config_digest
            ):
                matching.append(profile)
        if len(matching) != 1:
            raise WorkerConfigError(
                "requested Operator Harness profile does not resolve to one reviewed policy"
            )
        profile = matching[0]
        return CodexOperatorAdapter(
            binary_path=Path(config["codex_binary"]),
            codex_home=Path(config["provider_home"]),
            workspace_root=workspace,
            worker_id=policy.worker_id,
            expected_harness_version=binary_attestation.version,
            expected_config_digest=profile.expected_config_digest,
            app_server_config_overrides=profile.app_server_config_overrides(),
            native_helper_grant=profile.native_helper,
            network_policy="disabled",
            turn_input_loader=turn_input_loader,
        )

    armed = bool(config["operator_harness_armed"])
    return ExecutiveWorkerBroker(
        adapter,
        policy,
        sweeper,
        operator_adapter_factory=operator_adapter_factory,
        operator_harness_armed=armed,
        autonomy_guard=autonomy_guard,
        autonomy_canary_factory=(
            _build_autonomy_canary_factory(config) if armed else None
        ),
    )


async def _serve(config: dict[str, Any], *, autonomy_guard=None) -> None:
    broker = _build_broker(config, autonomy_guard=autonomy_guard)
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
        config_path = Path(args.config)
        config = _load_config(config_path, require_root_owner=True)
        autonomy_guard = None
        if config.get("operator_harness_armed") is True:
            own_config_sha256 = sha256_file(config_path)
            release_sha = _ROOT.name
            if re.fullmatch(r"[0-9a-f]{40}", release_sha) is None:
                raise WorkerConfigError(
                    "armed worker release root is not an exact commit SHA"
                )

            def require_autonomy() -> None:
                try:
                    validate_runtime_guard_file(
                        AUTONOMY_RECEIPT,
                        role="worker",
                        own_config_sha256=own_config_sha256,
                        release_sha=release_sha,
                    )
                except AutonomyRefusal as exc:
                    raise WorkerConfigError(
                        "Executive autonomy receipt refused"
                    ) from exc

            autonomy_guard = require_autonomy
        asyncio.run(_serve(config, autonomy_guard=autonomy_guard))
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
