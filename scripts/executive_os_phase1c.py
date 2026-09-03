"""Launch or query the private Executive OS Phase 1C-A control service.

The production ``serve --config`` path consumes a root-owned, secret-free JSON
configuration and launchd-activated Unix sockets.  Worker execution always
crosses the distinct-UID worker broker; this entrypoint has no local adapter or
TCP fallback.  G1 adds one exact-root deterministic COO-cycle operation and one
bounded service tick; both remain disabled by checked-in host configuration.
C1 may additionally expose the already-implemented dedicated CeoIngress state
listener through the SAME service process while CEO write admission remains
hard-disabled. Restore operations are deliberately offline CLI commands and are
never exposed through the live control socket.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import stat
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping

from control_plane.executive_runtime import RuntimeProofError, RuntimeStore
from control_plane.executive_autonomy import (
    AutonomyRefusal,
    validate_runtime_guard_file,
)
from control_plane.executive_service import (
    ExecutiveDialogueWakeBridge,
    ExecutiveControlService,
    ServiceConfig,
    ServiceError,
    activate_launchd_socket,
    send_control_request,
)
from control_plane.wake_ledger import WakeRetryPolicy


CONTROL_CONFIG_SCHEMA_VERSION = "mastermind.executive_control_config/v1"
AUTONOMY_RECEIPT = Path(
    "/Library/Application Support/MastermindExecutive/config/autonomy-state-v1.json"
)
SECRET_CANARY_ENVELOPE_SCHEMA_VERSION = (
    "mastermind.executive_secret_canary_envelope/v1"
)
CONTROL_ENVIRONMENT_PROBE_SCHEMA_VERSION = (
    "mastermind.executive_control_env_probe/v1"
)
_CANONICAL_AGENT_RELAY_SOCKET = Path(
    "/var/run/mastermind-agent-relay/agent-relay.sock"
)
_CANONICAL_DIALOGUE_OBSERVATION_SOCKET = Path(
    "/var/run/mastermind-dialogue-observation/dialogue-observation.sock"
)
_BACKUP_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.sqlite3$")
_CONFIG_REQUIRED = frozenset(
    {
        "schema_version",
        "runtime_root",
        "control_socket_path",
        "launchd_socket_name",
        "worker_broker_socket_path",
        "worker_provider_home",
        "worker_runs_root",
        "receipts_root",
        "proof_source_repository",
        "proof_workspace_root",
        "proof_base_sha",
        "backup_root",
        "control_uid",
        "worker_uid",
        "worker_gid",
        "worker_user",
        "shared_run_gid",
        "allowed_peer_uids",
        "secret_canary_receipt_path",
        "control_environment_attestation_path",
    }
)
_CONFIG_OPTIONAL = frozenset(
    {
        "proof_branch",
        "worker_id",
        "worker_account_label",
        "quota_class",
        "model",
        "effort",
        "cost_class",
        "coo_autonomy_armed",
        "coo_operator_harness_armed",
        "coo_tick_interval_seconds",
        "coo_model_alias",
        "coo_quota_class",
        "coo_default_quota_class",
        "coo_operator_model_alias",
        "coo_operator_quota_class",
        "operator_harness_binary_digest",
        "operator_harness_version",
        "broker_timeout_seconds",
        "shutdown_grace_seconds",
        "ceo_ingress_socket_path",
        "ceo_ingress_launchd_socket_name",
        "ceo_ingress_peer_uid",
        "terminal_return_armed",
        "terminal_return_socket_path",
        "dialogue_observation_socket_path",
        "dialogue_observation_launchd_socket_name",
        "dialogue_observation_peer_uid",
        "dialogue_bridge_armed",
        "dialogue_wake_retry_policy",
    }
)
_CEO_INGRESS_CONFIG_KEYS = frozenset(
    {
        "ceo_ingress_socket_path",
        "ceo_ingress_launchd_socket_name",
        "ceo_ingress_peer_uid",
    }
)
_TERMINAL_RETURN_CONFIG_KEYS = frozenset(
    {
        "terminal_return_armed",
        "terminal_return_socket_path",
    }
)
_DIALOGUE_BRIDGE_CONFIG_KEYS = frozenset(
    {
        "dialogue_observation_socket_path",
        "dialogue_observation_launchd_socket_name",
        "dialogue_observation_peer_uid",
        "dialogue_bridge_armed",
        "dialogue_wake_retry_policy",
    }
)
_CONFIG_DISABLED_EXTENSIONS = frozenset()


def _absolute_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("path must be absolute")
    return path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Operate the private launchd-backed Executive OS control service."
    )
    parser.add_argument(
        "--socket",
        type=_absolute_path,
        help="Absolute AF_UNIX socket for client commands; production serve uses --config.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Run the persistent launchd control service.")
    serve.add_argument("--config", type=_absolute_path, required=True)

    for name, help_text in (
        ("status", "Show service and startup-reconciliation status."),
        ("health", "Check SQLite migration and integrity health."),
        ("activate-canary", "Validate and activate the current PID-bound canary."),
        ("workers", "List durable worker identities."),
        ("jobs", "List durable Jobs."),
        ("register-worker", "Register the single configured Codex worker."),
        ("create-proof-job", "Create the fixed harmless Phase 1C-A proof Job."),
        ("reconcile", "Reconcile durable attempts without automatic requeue."),
        ("backup", "Create an online DB backup in the configured backup root."),
    ):
        sub.add_parser(name, help=help_text)

    job = sub.add_parser("job", help="Inspect one Job.")
    job.add_argument("job_id")
    attempt = sub.add_parser("attempt", help="Inspect one Attempt.")
    attempt.add_argument("attempt_id")
    dispatch = sub.add_parser("dispatch", help="Explicitly dispatch one fixed proof Job.")
    dispatch.add_argument("job_id")
    coo_cycle = sub.add_parser(
        "run-coo-cycle",
        help="Run one deterministic action for one exact host-bound strict-v2 root.",
    )
    coo_cycle.add_argument("root_job_id")
    cancel = sub.add_parser("cancel", help="Request cancellation for one Job.")
    cancel.add_argument("job_id")
    requeue = sub.add_parser("requeue", help="Explicitly requeue one LOST proof Job.")
    requeue.add_argument("job_id")
    verify = sub.add_parser("verify-backup", help="Verify one named backup in backup root.")
    verify.add_argument("name")

    restore_verify = sub.add_parser(
        "restore-verify",
        help="Offline restore drill for one named backup; does not replace the live DB.",
    )
    restore_verify.add_argument("--config", type=_absolute_path, required=True)
    restore_verify.add_argument("name")
    restore = sub.add_parser(
        "restore-backup",
        help="Offline verified restore; fails while the service marker/lock is live.",
    )
    restore.add_argument("--config", type=_absolute_path, required=True)
    restore.add_argument("name")
    return parser


def _private_json(path: Path, *, label: str, root_owned: bool) -> dict[str, Any]:
    if not path.is_absolute():
        raise ServiceError(f"{label} path must be absolute")
    try:
        info = path.lstat()
    except OSError as exc:
        raise ServiceError(f"{label} is unavailable: {exc}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ServiceError(f"{label} must be a single-link regular file")
    allowed_owners = {os.geteuid(), 0} if root_owned else {os.geteuid()}
    if info.st_uid not in allowed_owners:
        raise ServiceError(f"{label} has an untrusted owner")
    if stat.S_IMODE(info.st_mode) & 0o022:
        raise ServiceError(f"{label} is writable by group or other")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ServiceError(f"{label} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ServiceError(f"{label} must contain a JSON object")
    return value


def _path(value: Any, name: str) -> Path:
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ServiceError(f"control config {name} must be an absolute path")
    return Path(value).resolve(strict=False)


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ServiceError(f"control config {name} must be a non-negative integer")
    return value


def load_control_config(path: str | Path) -> dict[str, Any]:
    """Load the exact secret-free, root-owned production composition contract."""

    config = _private_json(Path(path), label="Executive control config", root_owned=True)
    if config.get("schema_version") != CONTROL_CONFIG_SCHEMA_VERSION:
        raise ServiceError("unsupported Executive control config schema")
    keys = set(config)
    missing = sorted(_CONFIG_REQUIRED - keys)
    unknown = sorted(
        keys
        - _CONFIG_REQUIRED
        - _CONFIG_OPTIONAL
        - _CONFIG_DISABLED_EXTENSIONS
    )
    if missing or unknown:
        raise ServiceError(
            f"Executive control config fields drifted; missing={missing}, unknown={unknown}"
        )
    ceo_ingress_present = keys & _CEO_INGRESS_CONFIG_KEYS
    if ceo_ingress_present and ceo_ingress_present != _CEO_INGRESS_CONFIG_KEYS:
        raise ServiceError("CeoIngress control config fields must be supplied together")
    terminal_return_present = keys & _TERMINAL_RETURN_CONFIG_KEYS
    if terminal_return_present and terminal_return_present != _TERMINAL_RETURN_CONFIG_KEYS:
        raise ServiceError("terminal-return control config fields must be supplied together")
    observation_present = keys & _DIALOGUE_BRIDGE_CONFIG_KEYS
    if observation_present and observation_present != _DIALOGUE_BRIDGE_CONFIG_KEYS:
        raise ServiceError(
            "dialogue-observation control config fields must be supplied together"
        )
    for name in (
        "runtime_root",
        "control_socket_path",
        "worker_broker_socket_path",
        "worker_provider_home",
        "worker_runs_root",
        "receipts_root",
        "proof_source_repository",
        "proof_workspace_root",
        "backup_root",
        "secret_canary_receipt_path",
        "control_environment_attestation_path",
    ):
        config[name] = _path(config[name], name)
    if ceo_ingress_present:
        config["ceo_ingress_socket_path"] = _path(
            config["ceo_ingress_socket_path"], "ceo_ingress_socket_path"
        )
    if terminal_return_present:
        terminal_return_socket = config["terminal_return_socket_path"]
        config["terminal_return_socket_path"] = _path(
            terminal_return_socket,
            "terminal_return_socket_path",
        )
        if terminal_return_socket != os.fspath(_CANONICAL_AGENT_RELAY_SOCKET):
            raise ServiceError(
                "control config terminal_return_socket_path must be exactly "
                f"{_CANONICAL_AGENT_RELAY_SOCKET}"
            )
    if observation_present:
        observation_socket = config["dialogue_observation_socket_path"]
        config["dialogue_observation_socket_path"] = _path(
            observation_socket,
            "dialogue_observation_socket_path",
        )
        if observation_socket != os.fspath(_CANONICAL_DIALOGUE_OBSERVATION_SOCKET):
            raise ServiceError(
                "control config dialogue_observation_socket_path must be exactly "
                f"{_CANONICAL_DIALOGUE_OBSERVATION_SOCKET}"
            )
    for name in ("control_uid", "worker_uid", "worker_gid", "shared_run_gid"):
        config[name] = _integer(config[name], name)
    if ceo_ingress_present:
        config["ceo_ingress_peer_uid"] = _integer(
            config["ceo_ingress_peer_uid"], "ceo_ingress_peer_uid"
        )
    if observation_present:
        config["dialogue_observation_peer_uid"] = _integer(
            config["dialogue_observation_peer_uid"],
            "dialogue_observation_peer_uid",
        )
        if config["dialogue_observation_peer_uid"] != 457:
            raise ServiceError(
                "dialogue observation peer uid must be Agent Relay uid 457"
            )
        if type(config["dialogue_bridge_armed"]) is not bool:
            raise ServiceError("control config dialogue_bridge_armed must be boolean")
        retry_policy = config["dialogue_wake_retry_policy"]
        retry_keys = {
            "max_delivery_attempts",
            "retry_cooldown_s",
            "accepted_ttl_s",
            "target_unavailable_backoff_s",
            "reenable_on_binding_rotation",
            "armed",
        }
        if not isinstance(retry_policy, dict) or set(retry_policy) != retry_keys:
            raise ServiceError(
                "control config dialogue_wake_retry_policy fields drifted"
            )
        for name in (
            "max_delivery_attempts",
            "retry_cooldown_s",
            "accepted_ttl_s",
            "target_unavailable_backoff_s",
        ):
            value = retry_policy[name]
            if value is not None and (
                type(value) is not int or value < 1
            ):
                raise ServiceError(
                    f"control config dialogue_wake_retry_policy.{name} "
                    "must be null or a positive integer"
                )
        for name in ("reenable_on_binding_rotation", "armed"):
            if type(retry_policy[name]) is not bool:
                raise ServiceError(
                    f"control config dialogue_wake_retry_policy.{name} "
                    "must be boolean"
                )
        if retry_policy["armed"] is not config["dialogue_bridge_armed"]:
            raise ServiceError(
                "dialogue bridge and Wake retry policy arming must match"
            )
        try:
            config["dialogue_wake_retry_policy"] = WakeRetryPolicy(
                **retry_policy
            )
        except (TypeError, ValueError) as exc:
            raise ServiceError(
                "control config dialogue_wake_retry_policy is invalid"
            ) from exc
    if config["control_uid"] != os.geteuid():
        raise ServiceError("control service effective uid does not match control config")
    if config["worker_uid"] == config["control_uid"]:
        raise ServiceError("worker_uid must differ from control_uid")
    peers = config["allowed_peer_uids"]
    if not isinstance(peers, list) or not peers:
        raise ServiceError("allowed_peer_uids must be a non-empty list")
    config["allowed_peer_uids"] = tuple(
        _integer(value, "allowed_peer_uids") for value in peers
    )
    for name in ("launchd_socket_name", "worker_user"):
        if not isinstance(config[name], str) or not config[name].strip():
            raise ServiceError(f"control config {name} is required")
    if ceo_ingress_present:
        name = config["ceo_ingress_launchd_socket_name"]
        if not isinstance(name, str) or not name.strip():
            raise ServiceError("control config ceo_ingress_launchd_socket_name is required")
        if config["ceo_ingress_socket_path"] == config["control_socket_path"]:
            raise ServiceError("CeoIngress socket must differ from Operator socket")
        if config["ceo_ingress_launchd_socket_name"] == config["launchd_socket_name"]:
            raise ServiceError("CeoIngress launchd socket name must differ from Operator")
        if config["ceo_ingress_peer_uid"] == config["control_uid"]:
            raise ServiceError("CeoIngress peer uid must differ from control uid")
    if observation_present:
        name = config["dialogue_observation_launchd_socket_name"]
        if not isinstance(name, str) or not name.strip():
            raise ServiceError(
                "control config dialogue_observation_launchd_socket_name is required"
            )
        names = {config["launchd_socket_name"]}
        if ceo_ingress_present:
            names.add(config["ceo_ingress_launchd_socket_name"])
        if name in names:
            raise ServiceError(
                "Dialogue Observation launchd socket name must be distinct"
            )
        observation_socket = config["dialogue_observation_socket_path"]
        forbidden_sockets = {
            config["control_socket_path"],
            config["worker_broker_socket_path"],
            _CANONICAL_AGENT_RELAY_SOCKET,
        }
        if ceo_ingress_present:
            forbidden_sockets.add(config["ceo_ingress_socket_path"])
        if observation_socket in forbidden_sockets:
            raise ServiceError(
                "Dialogue Observation socket must be distinct from every service path"
            )
    if terminal_return_present:
        if type(config["terminal_return_armed"]) is not bool:
            raise ServiceError("control config terminal_return_armed must be boolean")
        terminal_socket = config["terminal_return_socket_path"]
        forbidden_sockets = {
            "control socket": config["control_socket_path"],
            "worker broker socket": config["worker_broker_socket_path"],
        }
        if ceo_ingress_present:
            forbidden_sockets["CeoIngress socket"] = config[
                "ceo_ingress_socket_path"
            ]
        for label, forbidden_socket in forbidden_sockets.items():
            if terminal_socket == forbidden_socket:
                raise ServiceError(
                    f"terminal-return Relay socket must be distinct from {label}"
                )
    if "coo_autonomy_armed" in config and not isinstance(
        config["coo_autonomy_armed"], bool
    ):
        raise ServiceError("control config coo_autonomy_armed must be boolean")
    if "coo_operator_harness_armed" in config and not isinstance(
        config["coo_operator_harness_armed"], bool
    ):
        raise ServiceError(
            "control config coo_operator_harness_armed must be boolean"
        )
    if config.get("coo_operator_harness_armed", False) and not config.get(
        "coo_autonomy_armed", False
    ):
        raise ServiceError(
            "control config cannot arm the COO Operator Harness while COO autonomy is off"
        )
    if "operator_harness_binary_digest" in config:
        digest = config["operator_harness_binary_digest"]
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ServiceError(
                "control config operator_harness_binary_digest must be SHA-256"
            )
    if "operator_harness_version" in config:
        version = config["operator_harness_version"]
        if not isinstance(version, str) or not version.strip() or len(version) > 64:
            raise ServiceError(
                "control config operator_harness_version must be bounded"
            )
    if "coo_tick_interval_seconds" in config and (
        isinstance(config["coo_tick_interval_seconds"], bool)
        or not isinstance(config["coo_tick_interval_seconds"], (int, float))
    ):
        raise ServiceError(
            "control config coo_tick_interval_seconds must be numeric"
        )
    return config


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    try:
        payload = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ServiceError("canary receipt contains non-canonical JSON data") from exc
    return hashlib.sha256(payload).hexdigest()


def _load_control_environment_attestation(
    path: Path,
    *,
    config_path: Path,
    expected_release_sha: str,
) -> dict[str, Any]:
    """Validate the wrapper receipt against this exact live process and env."""

    from control_plane.codex_worker import ProcessInspector

    value = _private_json(
        path,
        label="control-environment attestation",
        root_owned=False,
    )
    required = {
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
    if set(value) != required:
        raise ServiceError("control-environment attestation fields drifted")
    if (
        value.get("schema_version")
        != "mastermind.executive_control_environment_attestation/v1"
        or value.get("sentinel_present") is not True
    ):
        raise ServiceError("control-environment attestation is unsupported")
    sentinel_name = "EXECUTIVE_CONTROL_CANARY_VALUE"
    sentinel = os.environ.get(sentinel_name)
    if not isinstance(sentinel, str) or not sentinel:
        raise ServiceError("control process has no injected environment canary")
    executable = Path(sys.executable).resolve(strict=True)
    release_manifest = Path(__file__).resolve().parents[1] / ".executive-release-manifest.json"
    if not release_manifest.is_file():
        raise ServiceError("installed release manifest is unavailable")
    identity = ProcessInspector().inspect(os.getpid())
    observed_identity = {
        "pid": os.getpid(),
        "pgid": identity.pgid,
        "session_id": identity.session_id,
        "start_identity": identity.start_identity,
        "boot_id": ProcessInspector().boot_session_id(),
        "effective_uid": identity.effective_uid,
        "effective_gid": identity.effective_gid,
        "real_uid": identity.real_uid,
        "real_gid": identity.real_gid,
    }
    expected_digests = {
        "config_sha256": _sha256_file(config_path),
        "release_manifest_sha256": _sha256_file(release_manifest),
        "python_executable_sha256": _sha256_file(executable),
        "sentinel_name_sha256": hashlib.sha256(sentinel_name.encode()).hexdigest(),
        "sentinel_value_sha256": hashlib.sha256(sentinel.encode()).hexdigest(),
    }
    if value.get("process_identity") != observed_identity:
        raise ServiceError("control-environment attestation process identity is stale")
    if any(value.get(key) != digest for key, digest in expected_digests.items()):
        raise ServiceError("control-environment attestation digest binding failed")
    if value.get("python_executable_path") != os.fspath(executable):
        raise ServiceError("control-environment attestation Python path differs")
    if value.get("release_commit_sha") != expected_release_sha:
        raise ServiceError("control-environment attestation release SHA differs")
    return value


def _load_canary_envelope(
    path: Path,
    *,
    raw: Mapping[str, Any],
    control_attestation: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate one fresh same-PID worker-bound canary envelope."""

    try:
        info = path.lstat()
    except OSError as exc:
        raise ServiceError(f"secret-canary envelope is unavailable: {exc}") from exc
    if stat.S_IMODE(info.st_mode) != 0o400:
        raise ServiceError("secret-canary envelope must be control-owned mode 0400")
    envelope = _private_json(
        path,
        label="secret-canary envelope",
        root_owned=False,
    )
    return _validate_canary_envelope(
        envelope,
        raw=raw,
        control_attestation=control_attestation,
    )


def _validate_canary_envelope(
    envelope: Mapping[str, Any],
    *,
    raw: Mapping[str, Any],
    control_attestation: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate an in-memory or persisted same-PID worker-bound envelope."""

    from control_plane.executive_canary import (
        PrincipalIdentity,
        SecretCanaryConfig,
        SecretCanaryError,
        validate_secret_canary_binding,
    )

    required_envelope = {
        "schema_version",
        "secret_canary",
        "control_environment_probe",
        "control_environment_probe_sha256",
    }
    if (
        set(envelope) != required_envelope
        or envelope.get("schema_version") != SECRET_CANARY_ENVELOPE_SCHEMA_VERSION
    ):
        raise ServiceError("secret-canary envelope fields or schema drifted")
    probe = envelope.get("control_environment_probe")
    required_probe = {
        "schema_version",
        "passed",
        "control_process_identity",
        "worker_principal",
        "config_sha256",
        "release_manifest_sha256",
        "sentinel_value_sha256",
        "process_identity_sha256",
        "checks",
    }
    if (
        not isinstance(probe, dict)
        or set(probe) != required_probe
        or probe.get("schema_version") != CONTROL_ENVIRONMENT_PROBE_SCHEMA_VERSION
        or probe.get("passed") is not True
    ):
        raise ServiceError("control-environment probe fields or schema drifted")
    probe_sha256 = _canonical_sha256(probe)
    if envelope.get("control_environment_probe_sha256") != probe_sha256:
        raise ServiceError("control-environment probe envelope digest differs")
    control_identity = probe.get("control_process_identity")
    if (
        not isinstance(control_identity, dict)
        or control_identity != control_attestation.get("process_identity")
        or probe.get("process_identity_sha256")
        != _canonical_sha256(control_identity)
    ):
        raise ServiceError("control-environment probe process identity is stale")
    worker_principal = probe.get("worker_principal")
    expected_worker_principal = {
        "real_uid": int(raw["worker_uid"]),
        "effective_uid": int(raw["worker_uid"]),
        "real_gid": int(raw["worker_gid"]),
        "effective_gid": int(raw["worker_gid"]),
    }
    if worker_principal != expected_worker_principal:
        raise ServiceError("control-environment probe worker principal differs")
    if (
        probe.get("config_sha256") != control_attestation.get("config_sha256")
        or probe.get("release_manifest_sha256")
        != control_attestation.get("release_manifest_sha256")
        or probe.get("sentinel_value_sha256")
        != control_attestation.get("sentinel_value_sha256")
    ):
        raise ServiceError("control-environment probe digest binding failed")
    checks = probe.get("checks")
    if (
        not isinstance(checks, dict)
        or set(checks) != {"launchctl", "ps", "kern_procargs2"}
        or any(value not in {"DENIED", "ABSENT"} for value in checks.values())
    ):
        raise ServiceError("control-environment probe checks are incomplete")

    runtime_root = Path(raw["runtime_root"])
    try:
        host_root = runtime_root.parents[1]
    except IndexError as exc:  # pragma: no cover - absolute config validation precedes this
        raise ServiceError("Executive runtime root cannot bind canary fixtures") from exc
    canary_config = SecretCanaryConfig(
        expected_worker_uid=int(raw["worker_uid"]),
        expected_worker_gid=int(raw["worker_gid"]),
        control_uid=int(raw["control_uid"]),
        control_gid=os.getegid(),
        control_environment_sentinel="EXECUTIVE_CONTROL_CANARY_VALUE",
        control_environment_probe_sha256=probe_sha256,
        administrative_checkout_sentinel=(
            Path(raw["proof_source_repository"])
            / ".git"
            / "executive-secret-canary"
        ),
        executive_database=(
            runtime_root / "data" / "control_plane" / "executive.sqlite3"
        ),
        other_worker_home_sentinel=(
            host_root / "canary-fixtures" / "other-worker-home" / "sentinel"
        ),
        forbidden_production_sentinel=(
            host_root / "canary-fixtures" / "production-like" / "sentinel"
        ),
        codex_home=Path(raw["worker_provider_home"]),
    )
    principal = PrincipalIdentity(**expected_worker_principal)
    inner = envelope.get("secret_canary")
    if not isinstance(inner, Mapping):
        raise ServiceError("secret-canary envelope has no inner receipt")
    try:
        return validate_secret_canary_binding(canary_config, principal, inner)
    except SecretCanaryError as exc:
        raise ServiceError(f"secret-canary binding is invalid: {exc.code}") from exc


def _persist_canary_envelope(
    path: Path,
    envelope: Mapping[str, Any],
) -> None:
    """Atomically replace the stale prior-PID envelope with the live one."""

    path = Path(path)
    if not path.is_absolute():
        raise ServiceError("secret-canary envelope destination must be absolute")
    parent = path.parent
    try:
        parent_info = parent.lstat()
    except OSError as exc:
        raise ServiceError("secret-canary envelope parent is unavailable") from exc
    if (
        stat.S_ISLNK(parent_info.st_mode)
        or not stat.S_ISDIR(parent_info.st_mode)
        or parent_info.st_uid != os.geteuid()
        or stat.S_IMODE(parent_info.st_mode) != 0o700
    ):
        raise ServiceError("secret-canary envelope parent is not owner-only")
    try:
        encoded = (
            json.dumps(
                dict(envelope),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ServiceError("secret-canary envelope is not canonical JSON") from exc
    if len(encoded) > 256 * 1024:
        raise ServiceError("secret-canary envelope exceeds the byte bound")
    temporary = parent / f".{path.name}.boot-{uuid.uuid4().hex}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = -1
    try:
        descriptor = os.open(temporary, flags, 0o400)
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != os.geteuid()
        ):
            raise ServiceError("secret-canary temporary file identity differs")
        remaining = memoryview(encoded)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise ServiceError("secret-canary envelope write did not advance")
            remaining = remaining[written:]
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o400)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
        directory_descriptor = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


class _C1UnavailableGroundingProvider:
    """Explicit C1-only grounding gap; B2/PR-C owns production grounding.

    R0 permits the diagnostic state frame to return while grounding is
    unavailable.  The existing hot-state builder then emits null grounding,
    a named degradation and ``do_not_submit=true``.  Keeping this provider
    intentionally unavailable prevents C1 from becoming an accidental B2
    arming path or from inventing a second source of trusted repository truth.
    """

    def observe(self):
        raise RuntimeError("C1_GROUNDING_UNAVAILABLE")


def _service_from_config(
    raw: Mapping[str, Any],
    *,
    canary_loader: Callable[[], Mapping[str, Any]] | None = None,
    autonomy_guard: Callable[[], None] | None = None,
    initial_canary: Mapping[str, Any] | None = None,
) -> ExecutiveControlService:
    from control_plane.executive_supervisor import ExecutiveSupervisor
    from control_plane.executive_operator_supervisor import (
        ExecutiveOperatorSupervisor,
    )
    from control_plane.remote_codex_operator_adapter import (
        RemoteCodexOperatorAdapter,
    )
    from control_plane.executive_worker_broker import (
        RemoteCodexWorkerAdapter,
        RemoteWorkerProcessController,
        WorkerBrokerClient,
    )

    client = WorkerBrokerClient(
        raw["worker_broker_socket_path"],
        timeout_seconds=float(raw.get("broker_timeout_seconds") or 30.0),
        max_response_bytes=16 * 1024 * 1024,
    )
    expected_operator_arm = bool(raw.get("coo_operator_harness_armed", False))
    binary_digest = str(raw.get("operator_harness_binary_digest") or "0" * 64)
    binary_version = str(raw.get("operator_harness_version") or "unproven")
    if expected_operator_arm and (
        re.fullmatch(r"[0-9a-f]{64}", binary_digest) is None
        or binary_digest == "0" * 64
        or not binary_version
        or binary_version == "unproven"
    ):
        raise ServiceError(
            "armed COO Operator Harness requires an exact installed binary identity"
        )

    config = ServiceConfig(
        runtime_root=raw["runtime_root"],
        socket_path=raw["control_socket_path"],
        proof_source_repository=raw["proof_source_repository"],
        proof_workspace_root=raw["proof_workspace_root"],
        proof_base_sha=raw["proof_base_sha"],
        proof_branch=str(raw.get("proof_branch") or "codex/phase1c-a-proof"),
        proof_shared_gid=raw["shared_run_gid"],
        backup_root=raw["backup_root"],
        worker_id=str(raw.get("worker_id") or "codex-01"),
        worker_account_label=str(
            raw.get("worker_account_label") or "dedicated-codex-home"
        ),
        quota_class=str(raw.get("quota_class") or "codex-native"),
        model=str(raw.get("model") or "gpt-5.6-sol"),
        effort=str(raw.get("effort") or "xhigh"),
        cost_class=str(raw.get("cost_class") or "standard"),
        coo_autonomy_armed=raw.get("coo_autonomy_armed", False),
        coo_operator_harness_armed=raw.get(
            "coo_operator_harness_armed", False
        ),
        coo_tick_interval_seconds=float(
            raw.get("coo_tick_interval_seconds", 15.0)
        ),
        coo_model_alias=str(raw.get("coo_model_alias") or "coo.sealed"),
        coo_quota_class=str(raw.get("coo_quota_class") or "codex-coo"),
        coo_default_quota_class=str(
            raw.get("coo_default_quota_class") or "codex-coo-default"
        ),
        coo_operator_model_alias=str(
            raw.get("coo_operator_model_alias") or "coo.operator.readonly"
        ),
        coo_operator_quota_class=str(
            raw.get("coo_operator_quota_class") or "codex-coo-operator"
        ),
        terminal_return_armed=raw.get("terminal_return_armed", False),
        terminal_return_socket_path=raw.get("terminal_return_socket_path"),
        operator_harness_binary_digest=binary_digest,
        operator_harness_version=binary_version,
        allowed_peer_uids=tuple(raw["allowed_peer_uids"]),
        shutdown_grace_seconds=float(raw.get("shutdown_grace_seconds") or 10.0),
    )
    # A persisted receipt from another service instance is never startup
    # authority. Every new PID starts quarantined and can activate only after a
    # fresh same-PID worker probe followed by the private activation command.
    canary: dict[str, Any] = dict(initial_canary or {})
    initially_ready = initial_canary is not None

    def supervisor_factory(runtime):
        def validations(spec):
            job = runtime.jobs.get_job(spec.job_id)
            if job is None or job.current_attempt_id != spec.run_id:
                raise ServiceError("remote validation lookup lost Job/Attempt identity")
            return tuple(tuple(command) for command in job.validation_commands)

        adapter = RemoteCodexWorkerAdapter(
            client,
            validation_commands_for_spec=validations,
        )
        return ExecutiveSupervisor(
            runtime,
            adapter,
            codex_home=raw["worker_provider_home"],
            runs_root=raw["worker_runs_root"],
            isolation_roots=(
                raw["proof_workspace_root"],
                raw["worker_runs_root"],
            ),
            receipts_root=raw["receipts_root"],
            worker_user=raw["worker_user"],
            worker_uid=raw["worker_uid"],
            worker_gid=raw["worker_gid"],
            shared_run_gid=raw["shared_run_gid"],
            secret_canary_verdict=canary,
            require_complete_launch_attestation=initially_ready,
            process_controller=RemoteWorkerProcessController(client),
        )

    def operator_supervisor_factory(runtime, sealed_supervisor):
        def adapter_factory(turn_input_loader):
            return RemoteCodexOperatorAdapter(
                client,
                turn_input_loader=turn_input_loader,
            )

        return ExecutiveOperatorSupervisor(
            runtime,
            adapter_factory=adapter_factory,
            prompt_source=sealed_supervisor,
        )

    async def verify_operator_identity() -> None:
        identity = await client.request("ohf-identity", {})
        if identity.get("worker_id") != config.worker_id:
            raise ServiceError("worker broker OHF identity has the wrong worker_id")
        if (
            identity.get("binary_sha256") != config.operator_harness_binary_digest
            or identity.get("binary_version") != config.operator_harness_version
        ):
            raise ServiceError("control/worker Operator Harness binary identity differs")
        if identity.get("operator_harness_armed") is not True:
            raise ServiceError("control/worker Operator Harness arming state differs")

    terminal_return_kwargs: dict[str, Any] = {}
    if config.terminal_return_armed:
        from integrations.slack_agent_dialogue.executive_terminal_return_projector import (
            ExecutiveTerminalReturnProjector,
            RuntimeTerminalReturnBindingResolver,
        )

        def terminal_return_projector_factory(runtime_provider, socket_path):
            return ExecutiveTerminalReturnProjector(
                RuntimeTerminalReturnBindingResolver(runtime_provider),
                socket_path=socket_path,
            )

        terminal_return_kwargs["terminal_return_projector_factory"] = (
            terminal_return_projector_factory
        )

    listener = activate_launchd_socket(str(raw["launchd_socket_name"]))
    activated_listeners = [listener]
    ceo_ingress_kwargs: dict[str, Any] = {}
    if _CEO_INGRESS_CONFIG_KEYS <= set(raw):
        ceo_listener = activate_launchd_socket(
            str(raw["ceo_ingress_launchd_socket_name"])
        )
        activated_listeners.append(ceo_listener)
        ceo_ingress_kwargs = {
            "ceo_ingress_socket_path": raw["ceo_ingress_socket_path"],
            "ceo_ingress_peer_uid": int(raw["ceo_ingress_peer_uid"]),
            "ceo_ingress_grounding_provider": _C1UnavailableGroundingProvider(),
            "ceo_ingress_armed": False,
            "ceo_ingress_activated_socket": ceo_listener,
        }
    dialogue_observation_kwargs: dict[str, Any] = {}
    if (
        _DIALOGUE_BRIDGE_CONFIG_KEYS <= set(raw)
        and raw["dialogue_bridge_armed"] is True
    ):
        def dialogue_wake_turn_input_loader(_turn):
            raise ServiceError(
                "dialogue Wake adapter cannot load provider turns"
            )

        observation_listener = activate_launchd_socket(
            str(raw["dialogue_observation_launchd_socket_name"])
        )
        activated_listeners.append(observation_listener)
        dialogue_observation_kwargs = {
            "dialogue_observation_socket_path": raw[
                "dialogue_observation_socket_path"
            ],
            "dialogue_observation_peer_uid": int(
                raw["dialogue_observation_peer_uid"]
            ),
            "dialogue_observation_group_gid": 457,
            "dialogue_wake_handler": ExecutiveDialogueWakeBridge(
                target_provider=None,
                retry_policy=raw["dialogue_wake_retry_policy"],
                operator_adapter=RemoteCodexOperatorAdapter(
                    client,
                    turn_input_loader=dialogue_wake_turn_input_loader,
                ),
            ),
            "dialogue_observation_activated_socket": observation_listener,
        }
    if config.terminal_return_socket_path is not None:
        for activated_listener in activated_listeners:
            getsockname = getattr(activated_listener, "getsockname", None)
            if not callable(getsockname):
                continue
            activated_path = getsockname()
            if isinstance(activated_path, bytes):
                activated_path = os.fsdecode(activated_path)
            if (
                isinstance(activated_path, str)
                and activated_path
                and not activated_path.startswith("\0")
                and Path(activated_path).resolve(strict=False)
                == config.terminal_return_socket_path
            ):
                raise ServiceError(
                    "terminal-return Relay socket must be distinct from every "
                    "activated listener"
                )
    return ExecutiveControlService(
        config,
        supervisor_factory=supervisor_factory,
        operator_supervisor_factory=operator_supervisor_factory,
        operator_identity_verifier=(
            verify_operator_identity if expected_operator_arm else None
        ),
        autonomy_guard=autonomy_guard,
        activated_socket=listener,
        service_state="READY" if initially_ready else "AWAITING_CANARY",
        canary_loader=canary_loader,
        **ceo_ingress_kwargs,
        **dialogue_observation_kwargs,
        **terminal_return_kwargs,
    )


async def _request_boot_autonomy_canary(
    raw: Mapping[str, Any],
    control_attestation: Mapping[str, Any],
    *,
    client=None,
    persist_path: Path | None = None,
) -> dict[str, Any]:
    """Obtain and validate one same-PID canary through the existing broker."""

    if client is None:
        from control_plane.executive_worker_broker import WorkerBrokerClient

        client = WorkerBrokerClient(
            raw["worker_broker_socket_path"],
            timeout_seconds=float(raw.get("broker_timeout_seconds") or 30.0),
            max_response_bytes=1024 * 1024,
        )
    result = await client.request(
        "autonomy-canary",
        {"control_environment_attestation": control_attestation},
    )
    envelope = result.get("envelope")
    if not isinstance(envelope, Mapping):
        raise ServiceError("worker boot canary returned no typed envelope")
    validated = _validate_canary_envelope(
        envelope,
        raw=raw,
        control_attestation=control_attestation,
    )
    if persist_path is not None:
        _persist_canary_envelope(persist_path, envelope)
    return validated


async def _serve_from_config(config_path: Path) -> None:
    raw = load_control_config(config_path)
    control_attestation = _load_control_environment_attestation(
        Path(raw["control_environment_attestation_path"]),
        config_path=config_path,
        expected_release_sha=str(raw["proof_base_sha"]),
    )
    canary_path = Path(raw["secret_canary_receipt_path"])

    def load_canary() -> Mapping[str, Any]:
        attestation = _load_control_environment_attestation(
            Path(raw["control_environment_attestation_path"]),
            config_path=config_path,
            expected_release_sha=str(raw["proof_base_sha"]),
        )
        return _load_canary_envelope(
            canary_path,
            raw=raw,
            control_attestation=attestation,
        )

    autonomy_guard: Callable[[], None] | None = None
    initial_canary: Mapping[str, Any] | None = None
    if raw.get("coo_autonomy_armed") is True:
        own_config_sha256 = _sha256_file(config_path)
        release_sha = str(raw["proof_base_sha"])

        def require_autonomy() -> None:
            try:
                validate_runtime_guard_file(
                    AUTONOMY_RECEIPT,
                    role="control",
                    own_config_sha256=own_config_sha256,
                    release_sha=release_sha,
                )
            except AutonomyRefusal as exc:
                raise ServiceError("Executive autonomy receipt refused") from exc

        autonomy_guard = require_autonomy
        require_autonomy()
        initial_canary = await _request_boot_autonomy_canary(
            raw,
            control_attestation,
            persist_path=canary_path,
        )

    service = _service_from_config(
        raw,
        canary_loader=load_canary,
        autonomy_guard=autonomy_guard,
        initial_canary=initial_canary,
    )
    await service.serve_until_stopped()


def _client_request(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    if args.command in {
        "status",
        "health",
        "activate-canary",
        "workers",
        "jobs",
        "register-worker",
        "create-proof-job",
        "reconcile",
        "backup",
    }:
        return args.command, {}
    if args.command in {"job", "dispatch", "cancel", "requeue"}:
        return args.command, {"job_id": args.job_id}
    if args.command == "run-coo-cycle":
        return args.command, {"root_job_id": args.root_job_id}
    if args.command == "attempt":
        return args.command, {"attempt_id": args.attempt_id}
    if args.command == "verify-backup":
        return args.command, {"name": args.name}
    raise AssertionError(args.command)


def _backup_paths(config: Mapping[str, Any], name: str) -> tuple[Path, Path]:
    if _BACKUP_NAME_RE.fullmatch(name) is None:
        raise ServiceError("backup name must be a simple .sqlite3 file name")
    root = Path(config["backup_root"])
    database = (root / name).resolve(strict=False)
    if database.parent != root.resolve(strict=False):
        raise ServiceError("backup path escapes configured backup root")
    return database, database.with_suffix(".manifest.json")


def _offline_restore(args: argparse.Namespace) -> Any:
    from control_plane.executive_backup import (
        restore_backup_offline,
        verify_restore_drill,
    )

    config = load_control_config(args.config)
    database, manifest = _backup_paths(config, args.name)
    if args.command == "restore-verify":
        return verify_restore_drill(database, manifest)
    store = RuntimeStore(config["runtime_root"])
    return restore_backup_offline(
        store,
        database,
        manifest,
        service_marker_path=store.path.parent / "executive-service.running",
        service_lock_path=store.path.parent / "executive-service.lock",
    )


async def _run(args: argparse.Namespace) -> int:
    if args.command == "serve":
        await _serve_from_config(args.config)
        return 0
    if args.command in {"restore-verify", "restore-backup"}:
        result = await asyncio.to_thread(_offline_restore, args)
        print(json.dumps(_jsonable(result), indent=2, sort_keys=True, ensure_ascii=False))
        return 0
    if args.socket is None:
        raise ServiceError("client commands require --socket")
    command, values = _client_request(args)
    response = await send_control_request(args.socket, command, values)
    print(json.dumps(response, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if response.get("ok") is True else 2


def _jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return _jsonable(value.to_dict())
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except (OSError, RuntimeProofError, ServiceError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
