"""Launch or query the private Executive OS Phase 1C-A control service.

The production ``serve --config`` path consumes a root-owned, secret-free JSON
configuration and launchd-activated Unix sockets.  Worker execution always
crosses the distinct-UID worker broker; this entrypoint has no local adapter or
TCP fallback.  G1 adds one exact-root deterministic COO-cycle operation and one
bounded service tick; both remain disabled by checked-in host configuration.
C1 may additionally expose the already-implemented dedicated CeoIngress state
listener through the SAME service process while C1 write admission remains
hard-disabled. An explicitly configured App peer has a separate admission
setting and canonical read binding on that same socket. Restore operations are deliberately offline CLI commands and are
never exposed through the live control socket.
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import hashlib
import json
import os
import re
import stat
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping

_ROOT = Path(__file__).resolve().parents[1]
if os.fspath(_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_ROOT))

from control_plane.executive_runtime import RuntimeProofError
from control_plane.executive_autonomy import (
    AutonomyRefusal,
    validate_runtime_guard_file,
)
from control_plane.executive_service import (
    ExecutiveDialogueWakeBridge,
    ExecutiveControlService,
    CeoIngressAppBinding,
    CEO_APP_READ_SCHEMA,
    CEO_WEB_CEO_V2_READ_SCHEMA,
    ServiceConfig,
    ServiceError,
    CeoAdmissionPhaseRefusal,
    activate_launchd_socket,
    send_control_request,
)
from control_plane.wake_ledger import WakeRetryPolicy


def _build_executive_dialogue_wake_carrier(
    *,
    runtime,
    resolved,
    target,
    current_binding,
    retry_policy,
    generation,
    source_guard=None,
    canary_profile=None,
    pre_submit_guard=None,
    historical_context_for=None,
    historical_only=False,
    physical_source=None,
):
    """Compose existing Wake owners outside the control-plane dependency layer."""

    from control_plane.runtime_binding_projection import project_runtime_binding
    from control_plane.wake_persist import WakeLedgerRepository
    from integrations.executive_wake.codex_app_server import (
        CodexAppServerWakeDispatcher,
    )
    from integrations.executive_wake.codex_app_server_rpc import (
        CodexCurrentWriterWakeClient,
    )
    from integrations.executive_wake.registry import WakeDispatcherRegistry
    from integrations.slack_agent_dialogue.persisted_wake_carrier import (
        HistoricalWakeContext,
        PersistedWakeCarrier,
    )

    def historical_context(attempt):
        if not callable(historical_context_for):
            raise ServiceError("historical Wake resolver is unavailable")
        historical = historical_context_for(attempt)
        grant = None if canary_profile is None else canary_profile.grant
        if grant is None:
            raise ServiceError("historical Wake grant is unavailable")
        from control_plane.session_targets import load_session_targets
        registry = load_session_targets()
        binding = historical.runtime_binding
        old_target = registry.get(binding.session_alias)
        if (binding.session_alias != grant.target_session_alias
                or binding.binding_id != grant.binding_id
                or binding.binding_generation != grant.binding_generation
                or historical.target_attempt_id != grant.target_attempt_id
                or historical.generation.process_generation_id != grant.process_generation_id
                or old_target.target_seat != grant.target_seat
                or old_target.wake_transport != "codex-app-server"):
            raise ServiceError("historical Wake target disagrees")
        registry = registry.with_root_job_bindings({
            **registry.root_job_bindings,
            grant.source_root_job_id: {
                **registry.root_job_bindings.get(grant.source_root_job_id, {}),
                grant.target_seat: binding.session_alias}})
        client = CodexCurrentWriterWakeClient(
            operator_adapter=historical.operator_adapter,
            generation=historical.generation,
            attempt_id=historical.target_attempt_id,
            runtime_binding=binding,
        )
        return HistoricalWakeContext(
            dispatchers=WakeDispatcherRegistry(
                {"codex-app-server": CodexAppServerWakeDispatcher(client)}),
            runtime_binding=binding, target_registry=registry,
        )

    canary_kwargs = {}
    if canary_profile is not None:
        canary_kwargs = dict(
            canary_profile=canary_profile, physical_source=physical_source,
            historical_context_for=historical_context)
    if historical_only:
        if canary_profile is None:
            raise ServiceError("historical Wake requires its original canary profile")
        return PersistedWakeCarrier(
            repository=WakeLedgerRepository(runtime),
            dispatchers=WakeDispatcherRegistry(),
            current_binding_for=lambda _route: None,
            retry_policy=retry_policy, **canary_kwargs,
        )

    wake_client = CodexCurrentWriterWakeClient(
        operator_adapter=resolved.operator_adapter,
        generation=generation,
        attempt_id=resolved.target_attempt_id,
        runtime_binding=current_binding,
        pre_submit_guard=pre_submit_guard,
    )
    def current_binding_for(_route):
        if source_guard is not None:
            source_guard()
        return project_runtime_binding(runtime, resolved.target_attempt_id, target)

    return PersistedWakeCarrier(
        repository=WakeLedgerRepository(runtime),
        dispatchers=WakeDispatcherRegistry(
            {"codex-app-server": CodexAppServerWakeDispatcher(wake_client)}
        ),
        current_binding_for=current_binding_for,
        retry_policy=retry_policy,
        target_registry=resolved.registry,
        **canary_kwargs,
    )


CONTROL_CONFIG_SCHEMA_VERSION = "mastermind.executive_control_config/v1"


def _validate_subscription_canary_realm_config(config: dict[str, Any]) -> None:
    """Validate the optional root-owned ``subscription_canary_realm`` block.

    The shape is fixed: exactly ``{binding_id, generation, config_sha256}``
    and each field passes the same fail-closed check the supervisor and the
    worker re-apply on disk.  Validation does not rewrite the loaded mapping:
    fixed-target source identity and hashes continue to cover the exact
    root-owned bytes.  An ordinary (no realm) configuration remains unchanged.
    """

    realm = config.get("subscription_canary_realm")
    if realm is None:
        return
    if not isinstance(realm, dict) or set(realm) != {
        "binding_id", "generation", "config_sha256",
    }:
        raise ServiceError(
            "control config subscription_canary_realm must have exactly "
            "binding_id, generation, config_sha256"
        )
    binding_id = realm["binding_id"]
    generation = realm["generation"]
    config_sha = realm["config_sha256"]
    if (
        not isinstance(binding_id, str)
        or not binding_id
        or binding_id != binding_id.strip()
    ):
        raise ServiceError(
            "control config subscription_canary_realm.binding_id is invalid"
        )
    if (
        type(generation) is not int
        or isinstance(generation, bool)
        or generation < 1
        or generation >= 2 ** 63
    ):
        raise ServiceError(
            "control config subscription_canary_realm.generation is invalid"
        )
    if (
        not isinstance(config_sha, str)
        or config_sha != config_sha.lower()
        or re.fullmatch(r"[0-9a-f]{64}", config_sha) is None
    ):
        raise ServiceError(
            "control config subscription_canary_realm.config_sha256 is invalid"
        )
    # Final fail-closed review of the binding against the catalog so a typo
    # in the realm cannot survive even if the three scalar fields look sane.
    from control_plane.subscription_harness_bindings import (
        HarnessBindingError,
        get_binding,
    )
    try:
        binding = get_binding(binding_id)
    except (HarnessBindingError, ValueError) as exc:
        raise ServiceError(
            "control config subscription_canary_realm binding is not reviewed"
        ) from exc
    if (
        binding.adapter_id != "codex-cli"
        or binding.implementation_state == "SPEC_ONLY"
        or binding.autonomous_allowed is not False
    ):
        raise ServiceError(
            "control config subscription_canary_realm binding is not a "
            "reviewed codex-cli attended-only implementation"
        )
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
    "/var/db/mastermind-agent-relay/socket/agent-relay.sock"
)
# Explicit stopped/disarmed recovery of an already-enrolled historical A2
# generation. Never a candidate for an armed return or ordinary install.
_LEGACY_A2_RECOVERY_SOCKET = Path(
    "/var/run/mastermind-agent-relay/agent-relay.sock"
)


def _agent_relay_readside_socket_for_control(config):
    # Only the already-validated, wholly disarmed legacy recovery profile
    # redirects existing consumers of the A2 socket. Normal installations
    # continue to bind exclusively to the canonical persistent socket.
    # load_control_config / ServiceConfig normalize through the macOS
    # /var -> /private/var symlink. Compare the same normalized identity;
    # keep the original lexical constant for exact config-wire validation.
    legacy = _LEGACY_A2_RECOVERY_SOCKET.resolve(strict=False)
    if (config.terminal_return_armed is False
            and config.terminal_return_socket_path == legacy):
        return legacy
    return _CANONICAL_AGENT_RELAY_SOCKET
_CANONICAL_DIALOGUE_OBSERVATION_SOCKET = Path(
    "/var/run/mastermind-dialogue-observation/dialogue-observation.sock"
)
_BACKUP_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.sqlite3$")
_CONTENT_PROFILE_MAX_BYTES = 65536
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
        "content_observer",
        "content_observer_profile_path",
        "company_consultation",
        "workspace_acquisition",
        "workspace_resource_policy",
        "workspace_control_room",
        "coo_principal_armed",
        "coo_principal_dialogue_armed",
        "proof_branch",
        "exact_worker_claim_target",
        "worker_id",
        "worker_account_label",
        "quota_class",
        "model",
        "effort",
        "cost_class",
        "coo_autonomy_armed",
        "coo_foreground_only",
        "ceo_submit_armed",
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
        "ceo_ingress_app_peer_uid",
        "ceo_ingress_app_armed",
        "ceo_ingress_app_macro_root",
        "ceo_ingress_app_boot_python",
        "executive_mcp_profile",
        "terminal_return_armed",
        "terminal_return_socket_path",
        "dialogue_observation_socket_path",
        "dialogue_observation_launchd_socket_name",
        "dialogue_observation_peer_uid",
        "dialogue_bridge_armed",
        "dialogue_wake_retry_policy",
        "dialogue_wake_canary_activation",
        "subscription_canary_realm",
        "privileged_readiness_armed",
        "privileged_broker_socket_path",
        "python_runtime_provenance_digest",
        "fabric_bindings_path",
        "fabric_bindings_sha256",
        "fabric_bridge_armed",
        "canonical_paid_fabric",
        "fabric_attended_probe",
        "native_capacity_v2",
    }
)
_CEO_INGRESS_CONFIG_KEYS = frozenset(
    {
        "ceo_ingress_socket_path",
        "ceo_ingress_launchd_socket_name",
        "ceo_ingress_peer_uid",
    }
)
_CEO_INGRESS_APP_CONFIG_KEYS = frozenset({
    "ceo_ingress_app_peer_uid", "ceo_ingress_app_armed", "ceo_ingress_app_macro_root",
})
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


class FabricActivationRefused(ServiceError):
    """Shared Fabric execution has no admitted backend and isolation profile."""


def _native_capacity_staging_only(raw: Mapping[str, Any]) -> bool:
    """A source pin can be prepared only while every execution switch is off."""
    return all(raw.get(key, False) is False for key in (
        "coo_autonomy_armed", "coo_operator_harness_armed", "coo_foreground_only",
        "ceo_submit_armed", "fabric_bridge_armed"))


def _validate_fabric_bridge_config(raw: Mapping[str, Any]) -> bool:
    armed = raw.get("fabric_bridge_armed", False)
    if type(armed) is not bool:
        raise ServiceError("fabric_bridge_armed must be boolean")
    if armed:
        raise FabricActivationRefused(
            "Fabric activation is disabled until an actual backend and isolation profile are admitted"
        )
    pair = {"fabric_bindings_path", "fabric_bindings_sha256"}
    present = set(raw) & pair
    if present and present != pair:
        raise ServiceError("Fabric bindings path and approved hash must be supplied together")
    if present:
        value, digest = raw["fabric_bindings_path"], raw["fabric_bindings_sha256"]
        if (type(value) is not str or not value or not Path(value).is_absolute()
                or ".." in Path(value).parts or str(Path(value)) != value or "\x00" in value
                or type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None):
            raise ServiceError("Fabric bindings require a canonical absolute path and exact SHA-256")
    if "fabric_attended_probe" in raw:
        probe = raw["fabric_attended_probe"]
        if (not present or type(probe) is not dict or set(probe) != {"worker_config_path"}
                or type(probe["worker_config_path"]) is not str
                or not Path(probe["worker_config_path"]).is_absolute()
                or ".." in Path(probe["worker_config_path"]).parts
                or str(Path(probe["worker_config_path"])) != probe["worker_config_path"]
                or "\x00" in probe["worker_config_path"]):
            raise ServiceError("Fabric attended probe requires one fixed worker definition")
    if "native_capacity_v2" in raw:
        stanza = raw["native_capacity_v2"]
        if ("fabric_attended_probe" not in raw
                or (not _native_capacity_staging_only(raw)
                    and raw.get("coo_foreground_only") is not True)
                or type(stanza) is not dict or set(stanza) != {"macro_release", "producer_sha256"}
                or type(stanza["macro_release"]) is not str
                or re.fullmatch(r"[0-9a-f]{40}", stanza["macro_release"]) is None
                or type(stanza["producer_sha256"]) is not str
                or re.fullmatch(r"[0-9a-f]{64}", stanza["producer_sha256"]) is None):
            raise ServiceError("native V2 capacity requires fixed source and foreground Control custody")
    return bool(present)


def _staged_fabric_binding_source(raw: Mapping[str, Any]):
    """Validate optional root-installed data without enabling its execution route."""
    if not _validate_fabric_bridge_config(raw):
        return None
    from control_plane.executive_fabric_composition import (
        FabricBindingSource, FabricCompositionError,
    )
    try:
        return FabricBindingSource.from_path(raw["fabric_bindings_path"], raw["fabric_bindings_sha256"])
    except FabricCompositionError as exc:
        raise ServiceError("Staged Fabric binding source refused") from exc


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
        ("content-observer-enroll", "Explicitly enroll the installed content profile as control uid."),
        ("content-observer-status", "Reconcile the installed content profile without enrollment."),
        ("content-observer-revoke", "Revoke the installed content profile as control uid."),
        ("status", "Show service and startup-reconciliation status."),
        ("health", "Check SQLite migration and integrity health."),
        ("activate-canary", "Validate and activate the current PID-bound canary."),
        ("workers", "List durable worker identities."),
        ("jobs", "List durable Jobs."),
        ("register-worker", "Register the configured identities; paid source begins OFFLINE."),
        ("paid-capacity-observe", "Observe existing paid state only; never refresh provider quota."),
        ("paid-capacity-bootstrap", "Explicit bounded original-owner paid quota status operation."),
        ("create-proof-job", "Create the fixed harmless Phase 1C-A proof Job."),
        ("reconcile", "Reconcile durable attempts without automatic requeue."),
        ("backup", "Create an online DB backup in the configured backup root."),
    ):
        cmd_parser = sub.add_parser(name, help=help_text)
        if name == "status":
            cmd_parser.add_argument(
                "--ceo-admission", action="store_true",
                help="As Control UID, observe current CEO guard only; never submit work.",
            )
        if name.startswith("content-observer-"):
            cmd_parser.add_argument(
                "--profile-key",
                choices=["web", "mac"],
                help="Content profile key (web or mac). Omit for legacy single-profile.",
            )

    readiness = sub.add_parser("check-current-worker-login", help="Read assigned worker login status for one current Attempt.")
    readiness.add_argument("job_id")
    readiness.add_argument("attempt_id")
    readiness.add_argument("fence_generation", type=int)

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
    recovery = sub.add_parser("recover-proof-capacity", help="Requalify one explicitly requeued missing-owner proof quota.")
    recovery.add_argument("job_id")
    recovery.add_argument("lost_attempt_id")
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


def _content_profile_identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_uid,
        info.st_gid,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _sealed_content_profile_ancestors(path: Path) -> tuple[tuple[str, tuple[int, ...]], ...]:
    """Return stable identities for root-owned, non-symlink path ancestors."""

    identities = []
    for node in path.parents:
        try:
            info = node.lstat()
        except OSError as exc:
            raise ServiceError("content observer profile path is unavailable") from exc
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != 0
            or stat.S_IMODE(info.st_mode) & 0o022
        ):
            raise ServiceError(
                "content observer profile path ancestors must be root-owned and sealed"
            )
        identities.append((os.fspath(node), _content_profile_identity(info)))
    return tuple(identities)


def _content_profile_path(value: Any) -> Path:
    """Accept one exact, normalized path without resolving aliases silently."""

    if type(value) is not str or not value or not Path(value).is_absolute():
        raise ServiceError("content observer profile path must be absolute")
    path = Path(value)
    if os.path.normpath(value) != value or os.fspath(path) != value:
        raise ServiceError("content observer profile path must be normalized")
    _sealed_content_profile_ancestors(path)
    try:
        if path.resolve(strict=True) != path:
            raise ServiceError("content observer profile path must not traverse symlinks")
    except ServiceError:
        raise
    except OSError as exc:
        raise ServiceError("content observer profile path is unavailable") from exc
    return path


def _read_content_profile_document(path: Path, *, expected_gid: int) -> dict[str, Any]:
    """Read one current root-published profile snapshot without cached fallback."""

    if type(expected_gid) is not int or expected_gid < 0:
        raise ServiceError("content observer profile Control GID is invalid")
    before_ancestors = _sealed_content_profile_ancestors(path)
    fd = -1
    try:
        fd = os.open(
            path,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
        )
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_uid != 0
            or before.st_gid != expected_gid
            or stat.S_IMODE(before.st_mode) != 0o440
            or before.st_size > _CONTENT_PROFILE_MAX_BYTES
        ):
            raise ServiceError("content observer profile source identity is invalid")
        parts: list[bytes] = []
        size = 0
        while True:
            part = os.read(
                fd,
                min(65536, _CONTENT_PROFILE_MAX_BYTES + 1 - size),
            )
            if not part:
                break
            parts.append(part)
            size += len(part)
            if size > _CONTENT_PROFILE_MAX_BYTES:
                raise ServiceError("content observer profile exceeds byte bound")
        raw = b"".join(parts)
        after = os.fstat(fd)
        path_info = path.lstat()
        after_ancestors = _sealed_content_profile_ancestors(path)
        if (
            _content_profile_identity(before) != _content_profile_identity(after)
            or _content_profile_identity(after) != _content_profile_identity(path_info)
            or before_ancestors != after_ancestors
            or len(raw) != after.st_size
        ):
            raise ServiceError("content observer profile changed during read")

        def unique_pairs(items):
            result = {}
            for key, item in items:
                if key in result:
                    raise ServiceError("content observer profile contains duplicate keys")
                result[key] = item
            return result

        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs)
        if type(value) is not dict:
            raise ServiceError("content observer profile must contain a JSON object")
        return value
    except ServiceError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ServiceError("content observer profile is unavailable or malformed") from exc
    finally:
        if fd >= 0:
            os.close(fd)


def _validate_content_profiles(value: Any, *, expected_release_sha: str) -> Any:
    from common.executive_content_contract import (
        ContentObserverProfile,
        load_content_profiles,
    )

    try:
        configured = load_content_profiles(value)
    except (TypeError, ValueError) as exc:
        raise ServiceError("content observer profile is invalid") from exc
    profiles = (
        (configured,)
        if type(configured) is ContentObserverProfile
        else tuple(
            slot.profile
            for slot in (configured.web, configured.mac)
            if slot.profile is not None
        )
    )
    if any(profile.release_sha != expected_release_sha for profile in profiles):
        raise ServiceError("content observer release differs from control source")
    return configured


def _path(value: Any, name: str) -> Path:
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ServiceError(f"control config {name} must be an absolute path")
    return Path(value).resolve(strict=False)


def _sealed_root_executable(value: Any, name: str) -> Path:
    """Require one root-owned executable behind no symlink/writable ancestor."""
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ServiceError(f"control config {name} must be an absolute path")
    path = Path(value)
    try:
        if path.resolve(strict=True) != path:
            raise ServiceError(f"control config {name} must not traverse symlinks")
        for node in (path, *path.parents):
            info = node.lstat()
            if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
                raise ServiceError(
                    f"control config {name} must be root-owned and sealed through its path"
                )
            if node == path:
                if (not stat.S_ISREG(info.st_mode) or not info.st_mode & 0o111
                        or info.st_nlink != 1):
                    raise ServiceError(
                        f"control config {name} must name one sealed executable file"
                    )
            elif not stat.S_ISDIR(info.st_mode):
                raise ServiceError(
                    f"control config {name} has a non-directory ancestor"
                )
    except ServiceError:
        raise
    except OSError as exc:
        raise ServiceError(f"control config {name} is unavailable") from exc
    return path


def _attest_app_boot_runtime(path: Path) -> Path:
    """Bind the optional App boot interpreter to the accepted CF2 capacity runtime."""
    from control_plane.ceo_boot_packet import attest_capacity_boot_runtime

    try:
        attest_capacity_boot_runtime(path)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ServiceError("App boot runtime attestation failed") from exc
    return path


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ServiceError(f"control config {name} must be a non-negative integer")
    return value


_CONTROL_TARGET_COMPOSITION = object()


@dataclasses.dataclass(frozen=True, repr=False)
class _TargetConfigSnapshot:
    path: Path
    raw: bytes
    identity: tuple[int, ...]

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.raw).hexdigest()


class _LoadedTargetConfig(dict):
    """A startup-only snapshot; never accepted as serialized authority."""
    def __init__(self, value, snapshot: _TargetConfigSnapshot):
        super().__init__(value)
        self._target_snapshot = snapshot
        self._normalized_sha256 = ""


def _target_file_identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _read_target_config_snapshot(path: Path) -> tuple[dict[str, Any], _TargetConfigSnapshot]:
    """Read one bounded owner-controlled file and hash the very bytes parsed."""
    if not path.is_absolute():
        raise ServiceError("exact worker target config path must be absolute")
    fd = -1
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or before.st_uid not in {0, os.geteuid()} or stat.S_IMODE(before.st_mode) & 0o022
            or before.st_size <= 0 or before.st_size > 256 * 1024):
            raise ServiceError("exact worker target source identity is invalid")
        parts, size = [], 0
        while True:
            part = os.read(fd, min(65536, 256 * 1024 + 1 - size))
            if not part:
                break
            size += len(part)
            if size > 256 * 1024:
                raise ServiceError("exact worker target config exceeds byte bound")
            parts.append(part)
        raw = b"".join(parts)
        after = os.fstat(fd)
        if (_target_file_identity(before) != _target_file_identity(after)
            or _target_file_identity(after) != _target_file_identity(path.lstat())
            or len(raw) != after.st_size):
            raise ServiceError("exact worker target source changed during read")
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ServiceError("exact worker target config contains duplicate keys")
                result[key] = value
            return result
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
        if not isinstance(value, dict):
            raise ServiceError("exact worker target config is not an object")
        return value, _TargetConfigSnapshot(path, raw, _target_file_identity(after))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ServiceError("exact worker target source is unavailable or malformed") from exc
    finally:
        if fd >= 0:
            os.close(fd)


def _target_config_mode(config: Mapping[str, Any]) -> str:
    value = config.get("exact_worker_claim_target", {"mode": "disabled"})
    if value == {"mode": "disabled"}:
        return "disabled"
    if (not isinstance(value, dict) or set(value) != {"mode", "definition", "max_age_ms"}
        or value.get("mode") != "fixed"):
        raise ServiceError("exact worker target configuration is not closed")
    from control_plane.executive_runtime import _normalise_exact_worker_target_documents
    try:
        definition, _ = _normalise_exact_worker_target_documents(value["definition"], {
            "schema_version": "mastermind.exact_worker_target_observation/v1",
            "source_sha256": "0" * 64, "control_attestation_sha256": "0" * 64,
            "observed_at_ms": 1, "max_age_ms": value["max_age_ms"],
        })
    except (ValueError, RuntimeProofError) as exc:
        raise ServiceError("exact worker target definition is invalid") from exc
    if (definition["worker_id"] != config.get("worker_id", "codex-01")
        or definition["expected_account_label"] != config.get("worker_account_label", "dedicated-codex-home")):
        raise ServiceError("exact worker target does not match the fixed broker identity")
    return "fixed"


class _ExactWorkerTargetSource:
    """Private adapter of the existing attested config into the claim owner."""
    def __init__(self, raw, attestation, attestation_loader, *, capability):
        if capability is not _CONTROL_TARGET_COMPOSITION or type(raw) is not _LoadedTargetConfig:
            raise ServiceError("exact worker target lacks attested source composition")
        self._raw = raw
        self._snapshot = raw._target_snapshot
        self._attestation = dict(attestation)
        self._attestation_loader = attestation_loader
        self._target = json.loads(self._snapshot.raw)["exact_worker_claim_target"]
        self.require_current()

    def require_current(self) -> None:
        if _canonical_sha256(_jsonable(self._raw)) != self._raw._normalized_sha256:
            raise ServiceError("exact worker target loaded composition was modified")
        _, current = _read_target_config_snapshot(self._snapshot.path)
        if current != self._snapshot:
            raise ServiceError("exact worker target consumed source snapshot changed")
        attestation = self._attestation_loader()
        if (not isinstance(attestation, Mapping)
            or attestation.get("config_sha256") != self._snapshot.sha256
            or self._attestation.get("config_sha256") != self._snapshot.sha256
            or _canonical_sha256(attestation) != _canonical_sha256(self._attestation)):
            raise ServiceError("exact worker target source/attestation binding differs")

    def for_job(self, job_id: str, *, now_ms: int):
        from control_plane.executive_runtime import (
            _issue_exact_worker_claim_target, _EXACT_WORKER_TARGET_PRODUCER,
        )
        if job_id != self._target["definition"]["job_id"]:
            raise ServiceError("exact worker target does not select this Job")
        self.require_current()
        return _issue_exact_worker_claim_target(
            self._target["definition"], {
                "schema_version": "mastermind.exact_worker_target_observation/v1",
                "source_sha256": self._snapshot.sha256,
                "control_attestation_sha256": _canonical_sha256(self._attestation),
                "observed_at_ms": now_ms, "max_age_ms": self._target["max_age_ms"],
            }, _producer_capability=_EXACT_WORKER_TARGET_PRODUCER,
            revalidate=self.require_current,
        )


def _bind_exact_worker_target_source(raw, attestation, *, _producer_capability, attestation_loader):
    if _target_config_mode(raw) == "disabled":
        return None
    return _ExactWorkerTargetSource(raw, attestation, attestation_loader,
                                   capability=_producer_capability)


_CANONICAL_COMPANY_CONSULTATION_SOCKET = "/var/run/mastermind-executive/company-consultation.sock"
_COMPANY_CONSULTATION_SOCKET_NAME = "CompanyConsultation"


_CANONICAL_WORKSPACE_CONTROL_ROOM_SOCKET = "/var/run/mastermind-executive/workspace-control-room.sock"
_WORKSPACE_CONTROL_ROOM_SOCKET_NAME = "WorkspaceControlRoom"


def validate_workspace_control_room(stanza: Any, *, control_uid: int) -> dict[str, Any]:
    """Closed unix/launchd stanza for the in-process workspace Control Room.

    The legacy ``{"port": int}`` TCP shape is refused loudly so a forgotten
    migration tool never silently degrades Control back onto a loopback socket.
    """

    if type(stanza) is dict and set(stanza) == {"port"}:
        raise ServiceError(
            "workspace Control Room legacy TCP port stanza refused; "
            "migrate it with ops/executive_os/migrate_workspace_control_room.py"
        )
    if type(stanza) is not dict:
        raise ServiceError("workspace Control Room topology refused")
    expected = {"transport", "socket_path", "launchd_socket_name", "allowed_peer_uids"}
    if set(stanza) != expected:
        raise ServiceError("workspace Control Room topology refused")
    if stanza["transport"] != "unix":
        raise ServiceError("workspace Control Room topology refused")
    if stanza["socket_path"] != _CANONICAL_WORKSPACE_CONTROL_ROOM_SOCKET:
        raise ServiceError("workspace Control Room topology refused")
    if stanza["launchd_socket_name"] != _WORKSPACE_CONTROL_ROOM_SOCKET_NAME:
        raise ServiceError("workspace Control Room topology refused")
    peers = stanza["allowed_peer_uids"]
    if (type(peers) is not list or len(peers) == 0
            or any(type(item) is not int for item in peers)
            or any(item is True or item is False for item in peers)
            or len(set(peers)) != len(peers)):
        raise ServiceError("workspace Control Room topology refused")
    if any(peer != control_uid for peer in peers):
        raise ServiceError("workspace Control Room topology refused")
    return {key: value for key, value in stanza.items()}


def workspace_control_room_launchd_entry(
    config: Mapping[str, Any], *, control_gid: int
) -> dict[str, Any] | None:
    """Closed optional host binding, shared by loader, installer and factory."""

    if "workspace_control_room" not in config:
        return None
    validate_workspace_control_room(
        config["workspace_control_room"], control_uid=int(config["control_uid"]))
    if type(control_gid) is not int or control_gid <= 0:
        raise ServiceError("workspace Control Room launchd entry requires a positive control gid")
    return {
        "SockPathName": _CANONICAL_WORKSPACE_CONTROL_ROOM_SOCKET,
        "SockType": "stream", "SockPassive": True,
        "SockPathOwner": int(config["control_uid"]),
        "SockPathGroup": control_gid,
        "SockPathMode": 0o600,
    }


def company_consultation_launchd_entry(config: Mapping[str, Any]) -> dict[str, Any] | None:
    """One closed optional host binding, shared by loader, installer and factory."""
    value = config.get("company_consultation")
    if "company_consultation" not in config:
        return None
    if (type(value) is not dict
            or not {"armed", "socket_path", "launchd_socket_name"} <= set(value)
            or set(value) - {"armed", "socket_path", "launchd_socket_name", "native_return_armed", "product_acceptance_armed"}
            or type(value.get("native_return_armed", False)) is not bool
            or type(value.get("product_acceptance_armed", False)) is not bool
            or type(value["armed"]) is not bool
            or value["socket_path"] != _CANONICAL_COMPANY_CONSULTATION_SOCKET
            or value["launchd_socket_name"] != _COMPANY_CONSULTATION_SOCKET_NAME):
        raise ServiceError("Company consultation control binding is invalid")
    if value.get("product_acceptance_armed", False) and (
            value["armed"] is not True or config.get("coo_principal_dialogue_armed") is not True):
        raise ServiceError("Product acceptance requires the Company socket and principal dialogue owner")
    if not value["armed"]:
        return None
    for key in ("control_uid", "worker_uid", "worker_gid"):
        if type(config.get(key)) is not int or config[key] <= 0:
            raise ServiceError("Company consultation requires fixed service identities")
    if config["worker_uid"] == config["control_uid"]:
        raise ServiceError("Company consultation requires a distinct worker principal")
    return {
        "SockPathName": _CANONICAL_COMPANY_CONSULTATION_SOCKET,
        "SockType": "stream", "SockPassive": True,
        "SockPathOwner": config["control_uid"], "SockPathGroup": config["worker_gid"],
        "SockPathMode": 0o660,
    }


def load_control_config(
    path: str | Path, *, enforce_current_uid: bool = True
) -> dict[str, Any]:
    """Load the exact secret-free, root-owned production composition contract.

    The service path keeps the default live-UID check.  A root-only credential
    interlock may request static validation so it can prove the configured
    control UID without impersonating that UID or weakening service startup.
    """

    if type(enforce_current_uid) is not bool:
        raise ServiceError("control config UID enforcement selector must be boolean")
    if not enforce_current_uid and os.geteuid() != 0:
        raise ServiceError("static control config validation requires root")
    config = _private_json(Path(path), label="Executive control config", root_owned=True)
    if _target_config_mode(config) == "fixed":
        parsed, snapshot = _read_target_config_snapshot(Path(path))
        if parsed != config:
            raise ServiceError("exact worker target config moved between observations")
        config = _LoadedTargetConfig(parsed, snapshot)
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
    _staged_fabric_binding_source(config)
    company_consultation_launchd_entry(config)
    arm = config.get("privileged_readiness_armed", False)
    broker_socket = config.get("privileged_broker_socket_path")
    if type(arm) is not bool:
        raise ServiceError("privileged_readiness_armed must be boolean")
    if (arm and broker_socket != "/var/run/mastermind-executive/privileged.sock") or (not arm and broker_socket is not None):
        raise ServiceError("privileged readiness requires the armed canonical broker socket")
    from ops.executive_os.coo_principal_host import validate_control_coo
    try:
        validate_control_coo(config)
    except ValueError:
        raise ServiceError("COO principal requires explicit Workspace and v2 App composition") from None
    ceo_ingress_present = keys & _CEO_INGRESS_CONFIG_KEYS
    if ceo_ingress_present and ceo_ingress_present != _CEO_INGRESS_CONFIG_KEYS:
        raise ServiceError("CeoIngress control config fields must be supplied together")
    app_present = keys & _CEO_INGRESS_APP_CONFIG_KEYS
    content_sources = keys & {"content_observer", "content_observer_profile_path"}
    if len(content_sources) > 1:
        raise ServiceError("content observer sources are mutually exclusive")
    if app_present and (
        app_present != _CEO_INGRESS_APP_CONFIG_KEYS
        or ceo_ingress_present != _CEO_INGRESS_CONFIG_KEYS
    ):
        raise ServiceError("App binding requires all App and CeoIngress configuration fields")
    if "ceo_ingress_app_boot_python" in keys and app_present != _CEO_INGRESS_APP_CONFIG_KEYS:
        raise ServiceError("App boot interpreter requires the complete App binding")
    from integrations.executive_mcp.web_ceo_v3 import validate_installed_mcp_profile_current
    try:
        validate_installed_mcp_profile_current(config.get("executive_mcp_profile", "legacy"))
    except ValueError:
        raise ServiceError("installed Executive MCP profile is invalid") from None
    if "executive_mcp_profile" in keys and (
        app_present != _CEO_INGRESS_APP_CONFIG_KEYS
        or ceo_ingress_present != _CEO_INGRESS_CONFIG_KEYS
    ):
        raise ServiceError("App binding requires all App and CeoIngress configuration fields")
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
    if "content_observer_profile_path" in config:
        config["content_observer_profile_path"] = _content_profile_path(
            config["content_observer_profile_path"]
        )
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
        is_current = terminal_return_socket == os.fspath(_CANONICAL_AGENT_RELAY_SOCKET)
        legacy_disarmed = (
            terminal_return_socket == os.fspath(_LEGACY_A2_RECOVERY_SOCKET)
            and config.get("terminal_return_armed") is False
            and config.get("ceo_submit_armed") is False
            and config.get("coo_autonomy_armed") is False
            and config.get("coo_operator_harness_armed") is False
            and config.get("coo_foreground_only", False) is False
            and config.get("fabric_bridge_armed", False) is False
        )
        if not is_current and not legacy_disarmed:
            raise ServiceError(
                "control config terminal_return_socket_path must be the "
                "persistent path, or the exact disarmed legacy A2 recovery path"
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
    if app_present:
        config["ceo_ingress_app_peer_uid"] = _integer(
            config["ceo_ingress_app_peer_uid"], "ceo_ingress_app_peer_uid"
        )
        if config["ceo_ingress_app_peer_uid"] in {
            config["control_uid"], config["ceo_ingress_peer_uid"], config["worker_uid"],
            *config["allowed_peer_uids"],
        }:
            raise ServiceError("App peer must be distinct from control, Operator, C1 and worker identities")
        if type(config["ceo_ingress_app_armed"]) is not bool:
            raise ServiceError("App admission arming must be boolean")
        config["ceo_ingress_app_macro_root"] = _path(
            config["ceo_ingress_app_macro_root"], "ceo_ingress_app_macro_root"
        )
        if "ceo_ingress_app_boot_python" in config:
            sealed_boot_python = _sealed_root_executable(
                config["ceo_ingress_app_boot_python"], "ceo_ingress_app_boot_python"
            )
            config["ceo_ingress_app_boot_python"] = _attest_app_boot_runtime(
                sealed_boot_python
            )
    workspace_keys = {"workspace_acquisition", "workspace_resource_policy", "workspace_control_room"}
    if keys & workspace_keys:
        if keys & workspace_keys != workspace_keys or app_present != _CEO_INGRESS_APP_CONFIG_KEYS:
            raise ServiceError("workspace acquisition requires its policy and installed App peer")
        config["workspace_control_room"] = validate_workspace_control_room(
            config["workspace_control_room"], control_uid=config["control_uid"])
        from integrations.business_mcp_auth.contracts import load_resource_policy
        from integrations.mastermind_workspace_app.contract import validate_workspace_bindings
        try:
            workspace_policy = load_resource_policy(config["workspace_resource_policy"])
            config["workspace_acquisition"] = validate_workspace_bindings(config["workspace_acquisition"], workspace_policy)
        except Exception:
            raise ServiceError("workspace acquisition policy or binding refused") from None
    if content_sources:
        if not app_present:
            raise ServiceError("content observer requires installed App peer")
        value = (
            config["content_observer"]
            if "content_observer" in config
            else _read_content_profile_document(
                config["content_observer_profile_path"],
                expected_gid=os.getegid(),
            )
        )
        _validate_content_profiles(
            value,
            expected_release_sha=str(config["proof_base_sha"]),
        )
    if "dialogue_wake_canary_activation" in config and not observation_present:
        raise ServiceError("dialogue Wake canary requires the observation configuration")
    if observation_present:
        from control_plane.dialogue_wake_canary_activation import (
            DialogueWakeCanaryActivationError, parse_dialogue_wake_canary_activation,
        )
        try:
            config["dialogue_wake_canary_activation"] = parse_dialogue_wake_canary_activation(
                config.get("dialogue_wake_canary_activation"))
        except DialogueWakeCanaryActivationError as exc:
            raise ServiceError("control config dialogue Wake canary activation is invalid") from exc
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
    _validate_subscription_canary_realm_config(config)
    if enforce_current_uid and config["control_uid"] != os.geteuid():
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
    if type(config.get("coo_foreground_only", False)) is not bool:
        raise ServiceError("control config coo_foreground_only must be boolean")
    if config.get("coo_foreground_only", False) and (
            config.get("coo_autonomy_armed") is not True
            or config.get("coo_operator_model_alias") == "coo.operator.native-return"):
        raise ServiceError("foreground-only mode requires armed ordinary foreground execution")
    if "ceo_submit_armed" in config and not isinstance(
        config["ceo_submit_armed"], bool
    ):
        raise ServiceError("control config ceo_submit_armed must be boolean")
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
    if "python_runtime_provenance_digest" in config:
        digest = config["python_runtime_provenance_digest"]
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ServiceError(
                "control config python_runtime_provenance_digest must be lowercase "
                "64-hex SHA-256"
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
    if type(config) is _LoadedTargetConfig:
        config._normalized_sha256 = _canonical_sha256(_jsonable(config))
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


class _HotContentProfileSource:
    """A fixed-path mutable profile source bound to one startup identity."""

    def __init__(
        self,
        *,
        profile_path: Path,
        expected_gid: int,
        expected_release_sha: str,
        config_path: Path,
        startup_attestation: Mapping[str, Any],
        attestation_loader: Callable[[], Mapping[str, Any]],
    ):
        if not isinstance(startup_attestation, Mapping):
            raise ServiceError("content observer startup attestation is invalid")
        config_sha256 = startup_attestation.get("config_sha256")
        process_identity = startup_attestation.get("process_identity")
        if (
            not isinstance(config_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", config_sha256) is None
            or not isinstance(process_identity, Mapping)
        ):
            raise ServiceError("content observer startup identity is incomplete")
        self._profile_path = profile_path
        self._expected_gid = expected_gid
        self._expected_release_sha = expected_release_sha
        self._config_path = config_path
        self._config_sha256 = config_sha256
        self._startup_attestation = json.loads(
            json.dumps(startup_attestation, ensure_ascii=False)
        )
        self._startup_attestation_sha256 = _canonical_sha256(
            self._startup_attestation
        )
        self._startup_process_identity_sha256 = _canonical_sha256(
            self._startup_attestation["process_identity"]
        )
        self._attestation_loader = attestation_loader
        self.load()

    def _require_startup_identity(self) -> None:
        try:
            current_config_sha256 = _sha256_file(self._config_path)
        except OSError as exc:
            raise ServiceError("content observer control config is unavailable") from exc
        current = self._attestation_loader()
        if (
            not isinstance(current, Mapping)
            or current_config_sha256 != self._config_sha256
            or current.get("config_sha256") != self._config_sha256
            or current.get("release_commit_sha") != self._expected_release_sha
            or _canonical_sha256(current) != self._startup_attestation_sha256
            or _canonical_sha256(current.get("process_identity"))
            != self._startup_process_identity_sha256
        ):
            raise ServiceError("content observer startup config or attestation changed")

    def load(self) -> dict[str, Any]:
        self._require_startup_identity()
        value = _read_content_profile_document(
            self._profile_path,
            expected_gid=self._expected_gid,
        )
        _validate_content_profiles(
            value,
            expected_release_sha=self._expected_release_sha,
        )
        self._require_startup_identity()
        return value


def _bind_hot_content_profile_source(
    raw: Mapping[str, Any],
    startup_attestation: Mapping[str, Any],
    *,
    config_path: Path,
    attestation_loader: Callable[[], Mapping[str, Any]],
) -> _HotContentProfileSource | None:
    if "content_observer_profile_path" not in raw:
        return None
    return _HotContentProfileSource(
        profile_path=Path(raw["content_observer_profile_path"]),
        expected_gid=os.getegid(),
        expected_release_sha=str(raw["proof_base_sha"]),
        config_path=config_path,
        startup_attestation=startup_attestation,
        attestation_loader=attestation_loader,
    )


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
    attended_config=None,
    attended_binding=None,
) -> dict[str, Any]:
    """Validate an in-memory or persisted same-PID worker-bound envelope."""

    from control_plane.executive_canary import (
        PrincipalIdentity,
        SecretCanaryConfig,
        SecretCanaryError,
        validate_secret_canary_binding,
        validate_attended_secret_canary_binding,
        AttendedCanaryBinding,
    )

    if ((attended_config is None) != (attended_binding is None)
            or (attended_config is not None and (
                type(attended_config) is not SecretCanaryConfig
                or type(attended_binding) is not AttendedCanaryBinding))):
        raise ServiceError("finite canary validation requires coupled typed owner inputs")
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
        "real_uid": attended_config.expected_worker_uid if attended_config else int(raw["worker_uid"]),
        "effective_uid": attended_config.expected_worker_uid if attended_config else int(raw["worker_uid"]),
        "real_gid": attended_config.expected_worker_gid if attended_config else int(raw["worker_gid"]),
        "effective_gid": attended_config.expected_worker_gid if attended_config else int(raw["worker_gid"]),
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
        if attended_config is not None:
            if (attended_config.control_environment_probe_sha256 != probe_sha256
                    or attended_config.control_uid != raw["control_uid"]
                    or attended_config.control_gid != control_identity["effective_gid"]
                    or any(getattr(attended_config, key) != getattr(canary_config, key) for key in (
                        "administrative_checkout_sentinel", "executive_database",
                        "other_worker_home_sentinel", "forbidden_production_sentinel"))):
                raise ServiceError("finite probe targets differ from the actual Control layout")
            return validate_attended_secret_canary_binding(
                attended_config, attended_binding, principal, inner)
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
    ceo_submit_admission_guard: Callable[[], None] | None = None,
    initial_canary: Mapping[str, Any] | None = None,
    content_profile_loader: Callable[[], Any] | None = None,
    workspace_acquisition_loader: Callable[[], Any] | None = None,
    exact_target_source: _ExactWorkerTargetSource | None = None,
    workspace_bindings_path: Path | None = None,
    coo_source: Any | None = None,
    claimed_operator_adapter_factory: Callable[..., Any] | None = None,
    remote_operator_binding_source: Callable[..., Any] | None = None,
    dialogue_canary_profile: Any | None = None,
    native_dialogue_canary_profile_loader: Callable[[], Any] | None = None,
    remote_worker_binding_source: Callable[..., Any] | None = None,
    plan_schema_version: str | None = None,
    fabric_worker_binding_source: Any | None = None,
    fabric_attended_probe_source: Any | None = None,
    attended_work_placements: tuple = (),
    paid_worker_binding_source: Any | None = None,
) -> ExecutiveControlService:
    from control_plane.dialogue_wake_canary_activation import DialogueWakeCanaryProfile
    if dialogue_canary_profile is None:
        dialogue_canary_profile = DialogueWakeCanaryProfile(None)
    if type(dialogue_canary_profile) is not DialogueWakeCanaryProfile:
        raise ServiceError("dialogue canary profile requires trusted composition")
    # This is trusted host composition, never a JSON/model-selected factory.
    from control_plane.executive_orchestration_result import (
        PLAN_SCHEMA_V1, PLAN_SCHEMA_V3, PLAN_SCHEMA_V4, PLAN_SCHEMA_V5,
    )
    # Legacy omission stays legacy: only an explicit version opts this Control
    # host into a native planner producer, and that needs an explicitly supplied
    # trusted claim-bound adapter. The remote transport has not qualified native
    # contract custody.
    if plan_schema_version is not None and (
        type(plan_schema_version) is not str
        or plan_schema_version not in {
            PLAN_SCHEMA_V1, PLAN_SCHEMA_V3, PLAN_SCHEMA_V4, PLAN_SCHEMA_V5,
        }
    ):
        raise ServiceError("trusted planner plan schema is unsupported")
    if plan_schema_version is not None and (
        claimed_operator_adapter_factory is None
        or remote_operator_binding_source is not None
    ):
        raise ServiceError("versioned producer needs a trusted claim-bound adapter")
    _validate_fabric_bridge_config(raw)
    from control_plane.fabric_attended_routing import AttendedWorkPlacement, placement_member, qualification_for
    if (type(attended_work_placements) is not tuple
            or len(attended_work_placements) > 6
            or any(type(item) is not AttendedWorkPlacement for item in attended_work_placements)):
        raise ServiceError('attended placements require bounded typed host configuration')
    if qualification_for(attended_work_placements) is not None and raw.get('coo_foreground_only') is not True:
        raise ServiceError('finite qualification requires foreground-only host configuration')
    if attended_work_placements and (fabric_worker_binding_source is None
                                    or fabric_attended_probe_source is None):
        raise ServiceError('attended placements require the binding and startup probe sources')
    if fabric_attended_probe_source is not None:
        from control_plane.fabric_attended_canary import AttendedControlProbeSource
        if type(fabric_attended_probe_source) is not AttendedControlProbeSource:
            raise ServiceError('attended probe requires the exact startup-bound source')
        fabric_attended_probe_source.require_definition(raw)
    if fabric_worker_binding_source is not None:
        from control_plane.executive_fabric_composition import FabricBindingSource
        if type(fabric_worker_binding_source) is not FabricBindingSource:
            raise ServiceError("Fabric worker composition requires the exact root-installed binding source")
        if remote_worker_binding_source is not None:
            raise ServiceError("Fabric and remote worker binding sources conflict")
        if initial_canary is not None:
            if fabric_attended_probe_source is None or not attended_work_placements:
                raise FabricActivationRefused(
                    "A dedicated-worker canary does not qualify shared Fabric execution"
                )
            from control_plane.executive_canary import validate_initial_secret_canary_verdict
            validate_initial_secret_canary_verdict(initial_canary)
        # Mixed ownership is keyed by worker_id, while physical lookup also
        # includes host. One logical owner may not silently change principal
        # according to binding-file order or the selected host.
        principals = {}
        for binding in fabric_worker_binding_source.bindings:
            principal = (binding.worker_uid, binding.worker_gid)
            previous = principals.setdefault(binding.worker_id, principal)
            if previous != principal:
                raise ServiceError("Fabric worker has conflicting physical principals")
        if any(binding.worker_id == str(raw.get("worker_id") or "codex-01")
               for binding in fabric_worker_binding_source.bindings):
            raise ServiceError("Fabric binding cannot replace the primary worker")
    if attended_work_placements:
        from control_plane.model_router import ModelRouter
        router = ModelRouter.load()
        for placement in attended_work_placements:
            placement_member(router, placement)
    paid_work_placements=()
    if paid_worker_binding_source is not None:
        from control_plane.executive_paid_fabric_composition import PaidBindingSource,PaidWorkPlacement
        if (type(paid_worker_binding_source) is not PaidBindingSource
                or fabric_worker_binding_source is not None or attended_work_placements):
            raise ServiceError('paid and attended owner compositions cannot mix')
        paid_worker_binding_source._current()
        identities=set()
        placements=[]
        for physical in paid_worker_binding_source.bindings:
            if physical.worker_id in identities or physical.worker_id==str(raw.get('worker_id') or 'codex-01'):
                raise ServiceError('paid physical owner conflicts with another Worker')
            identities.add(physical.worker_id)
            placements.append(PaidWorkPlacement('glm.paid.sealed-input',
                paid_worker_binding_source.quota_for(physical)))
        paid_work_placements=tuple(dict.fromkeys(placements))
    if (remote_worker_binding_source is not None
            and not callable(remote_worker_binding_source)):
        raise ServiceError("remote worker binding source must be callable")
    if (claimed_operator_adapter_factory is not None
            and not callable(claimed_operator_adapter_factory)):
        raise ServiceError("claimed operator factory must be callable")
    if (remote_operator_binding_source is not None
            and (not callable(remote_operator_binding_source)
                 or claimed_operator_adapter_factory is not None)):
        raise ServiceError("remote operator binding source conflicts with factory")
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

    if _target_config_mode(raw) == "fixed":
        if type(exact_target_source) is not _ExactWorkerTargetSource or exact_target_source._raw is not raw:
            raise ServiceError("exact worker target has no attested composition")
        exact_target_source.require_current()
    elif exact_target_source is not None:
        raise ServiceError("exact worker target source conflicts with disabled config")

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

    realm_raw = raw.get("subscription_canary_realm")
    realm_binding_id: str | None = None
    realm_generation: int | None = None
    realm_config_sha256: str | None = None
    worker_provider = "codex"
    worker_type = "codex-cli"
    worker_model = str(raw.get("model") or "gpt-5.6-sol")
    if realm_raw is not None:
        _validate_subscription_canary_realm_config(
            {"subscription_canary_realm": realm_raw}
        )
        # load_control_config has already validated this exact closed object.
        # Derive worker identity from the reviewed catalog instead of trusting
        # parallel provider/model fields in root configuration.
        from control_plane.subscription_harness_bindings import get_binding
        from control_plane.subscription_provider_profiles import get_profile

        realm_binding_id = str(realm_raw["binding_id"])
        realm_generation = int(realm_raw["generation"])
        realm_config_sha256 = str(realm_raw["config_sha256"])
        reviewed_binding = get_binding(realm_binding_id)
        reviewed_profile = get_profile(reviewed_binding.profile_id)
        worker_provider = reviewed_binding.provider
        worker_type = reviewed_binding.adapter_id
        worker_model = reviewed_binding.model_for(reviewed_profile)

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
        worker_type=worker_type,
        provider=worker_provider,
        quota_class=str(raw.get("quota_class") or "codex-native"),
        model=worker_model,
        effort=str(raw.get("effort") or "xhigh"),
        cost_class=str(raw.get("cost_class") or "standard"),
        privileged_readiness_armed=raw.get("privileged_readiness_armed", False),
        privileged_broker_socket_path=raw.get("privileged_broker_socket_path"),
        coo_autonomy_armed=raw.get("coo_autonomy_armed", False),
        coo_foreground_only=raw.get("coo_foreground_only", False),
        ceo_submit_armed=raw.get("ceo_submit_armed", False),
        coo_operator_harness_armed=raw.get(
            "coo_operator_harness_armed", False
        ),
        coo_attended_work_placements=attended_work_placements,
        coo_paid_work_placements=paid_work_placements,
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
        subscription_canary_realm_binding_id=realm_binding_id,
        subscription_canary_realm_generation=realm_generation,
        subscription_canary_realm_config_sha256=realm_config_sha256,
    )
    # Keep all existing A2 read-side consumers on the same socket selected
    # by validated Control. A returned old A2 daemon listens only on /var/run,
    # so a hard-coded /var/db consumer would silently miss native replies.
    relay_readside_socket_path = _agent_relay_readside_socket_for_control(config)
    # A persisted receipt from another service instance is never startup
    # authority. Every new PID starts quarantined and can activate only after a
    # fresh same-PID worker probe followed by the private activation command.
    canary: dict[str, Any] = dict(initial_canary or {})
    initially_ready = initial_canary is not None

    recovery_controller = {}

    def recovery_controller_for(attempt):
        owners = recovery_controller.get("owners")
        if owners is not None:
            owner = owners.get(attempt.worker_id)
            if owner is None:
                raise ServiceError("proof recovery has no exact execution owner")
            return owner.process_controller
        return recovery_controller.get("current")

    def proof_capacity_recovery_observer(attempt):
        controller = recovery_controller_for(attempt)
        if controller is None or not controller.absence_verified(attempt):
            raise ServiceError("proof capacity has no fresh broker absence")
        return dict(controller.uid_sweep_receipt(attempt))

    def proof_capacity_recovery_worker_uid(attempt):
        controller = recovery_controller_for(attempt)
        if controller is None:
            raise ServiceError("proof capacity has no recovery controller")
        return controller.expected_worker_uid(attempt)

    # The existing R2 selection carries original-intent review on every actual
    # worker owner. Freeze the host-owned source before constructing a supervisor;
    # no worker/model can choose or rotate a Macro root through its request.
    product_acceptance_macro_root = None
    product_acceptance_context_owner = None

    def product_acceptance_basis_reader():
        from control_plane.agentos_product_acceptance_basis import AgentOsProductAcceptanceBasisReader
        if product_acceptance_macro_root is None:
            raise ServiceError("Product acceptance requires its bound Macro source")
        if product_acceptance_context_owner is not None:
            return product_acceptance_context_owner.product_acceptance_basis_reader(
                macro_root=product_acceptance_macro_root)
        return AgentOsProductAcceptanceBasisReader(macro_root=product_acceptance_macro_root)
    if raw.get("coo_principal_dialogue_armed", False) is True:
        from ops.executive_os.coo_principal_host import CooInstalledSource, validate_control_coo
        try:
            if (not validate_control_coo(raw)
                    or not _CEO_INGRESS_APP_CONFIG_KEYS <= set(raw)
                    or type(coo_source) is not CooInstalledSource):
                raise ValueError("incomplete principal binding")
        except ValueError:
            raise ServiceError("product acceptance review requires the sealed COO and complete App binding") from None
        product_acceptance_macro_root = Path(raw["ceo_ingress_app_macro_root"])

    native_capacity_source = None
    if ("native_capacity_v2" in raw and _native_capacity_staging_only(raw)
            and attended_work_placements):
        raise ServiceError("staged native capacity cannot carry active placements")
    if "native_capacity_v2" in raw and not _native_capacity_staging_only(raw):
        if (len(attended_work_placements) != 1
                or qualification_for(attended_work_placements) is None):
            raise ServiceError("native V2 capacity requires the single original finite placement")
        from control_plane.native_capacity_acquisition import NativeCapacitySource
        native_capacity_source = NativeCapacitySource.from_startup(
            fabric_attended_probe_source, fabric_worker_binding_source)

    def supervisor_factory(runtime):
        def validations(spec):
            job = runtime.jobs.get_job(spec.job_id)
            if job is None or job.current_attempt_id != spec.run_id:
                raise ServiceError("remote validation lookup lost Job/Attempt identity")
            return tuple(tuple(command) for command in job.validation_commands)

        from control_plane.worker_execution_contract import CleanupPolicy

        if remote_worker_binding_source is None:
            adapter = RemoteCodexWorkerAdapter(
                client,
                validation_commands_for_spec=validations,
            )
            process_controller = RemoteWorkerProcessController(
                client, expected_worker_uid=int(raw["worker_uid"])
            )
        else:
            from control_plane.remote_attempt_transport import (
                AttemptBoundRemoteWorkerAdapter,
            )

            # Resolve only the already-claimed Worker. A missing or uncertain
            # remote binding must never fall back to the primary local broker.
            adapter = AttemptBoundRemoteWorkerAdapter(
                runtime,
                remote_worker_binding_source,
                validation_commands_for_spec=validations,
            )
            process_controller = adapter.process_controller
        # Only the attended subscription-canary lane gets a claim provider;
        # ordinary composition passes ``None`` so the supervisor never calls
        # the observation owner and never enriches the LaunchSpec.
        claim_provider: Callable[[str, str], Mapping[str, Any]] | None = None
        claim_binding_id: str | None = None
        if config.subscription_canary_realm() is not None:
            from control_plane.model_router import observe_subscription_canary_claim

            realm = config.subscription_canary_realm()
            assert realm is not None

            def claim_provider(
                attempt_id: str,
                binding_id: str,
                _runtime=runtime,
            ) -> Mapping[str, Any]:
                return observe_subscription_canary_claim(
                    _runtime,
                    attempt_id=attempt_id,
                    binding_id=binding_id,
                )

            claim_binding_id = str(realm["binding_id"])
        recovery_controller["current"] = process_controller
        primary = ExecutiveSupervisor(
            runtime,
            adapter,
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
            cleanup_policy=CleanupPolicy.DEDICATED_UID,
            process_controller=process_controller,
            exact_target_provider=(
                (lambda job_id: exact_target_source.for_job(job_id, now_ms=runtime.store.now_ms()))
                if exact_target_source is not None else None
            ),
            subscription_canary_claim_provider=claim_provider,
            subscription_canary_binding_id=claim_binding_id,
            product_acceptance_macro_root=product_acceptance_macro_root,
            product_acceptance_context_reader=(product_acceptance_basis_reader()
                if product_acceptance_context_owner is not None else None),
        )
        if paid_worker_binding_source is not None:
            from control_plane.executive_paid_fabric_adapter import CanonicalPaidFabricWorkerAdapter
            from control_plane.mixed_worker_supervisor import MixedExecutionOwnerSupervisor
            paid_adapter=CanonicalPaidFabricWorkerAdapter(runtime,paid_worker_binding_source)
            owners={config.worker_id:primary}
            for physical in paid_worker_binding_source.bindings:
                owners[physical.worker_id]=ExecutiveSupervisor(runtime,paid_adapter,
                    runs_root=raw['worker_runs_root'],
                    isolation_roots=(raw['proof_workspace_root'],raw['worker_runs_root']),
                    receipts_root=raw['receipts_root'],worker_user=physical.worker_user,
                    worker_uid=physical.worker_uid,worker_gid=physical.worker_gid,
                    shared_run_gid=None,secret_canary_verdict=None,
                    require_complete_launch_attestation=True,
                    cleanup_policy=CleanupPolicy.FABRIC_PROCESS_GROUP,
                    process_controller=paid_adapter,instance_id=primary.instance_id,
                    product_acceptance_macro_root=product_acceptance_macro_root,
                    product_acceptance_context_reader=(product_acceptance_basis_reader()
                        if product_acceptance_context_owner is not None else None))
            mixed=MixedExecutionOwnerSupervisor(primary,owners)
            recovery_controller['owners']=mixed.owners
            return mixed
        if fabric_worker_binding_source is None:
            return primary
        from control_plane.executive_fabric_adapter import AttendedFabricWorkerAdapter
        from control_plane.mixed_worker_supervisor import MixedExecutionOwnerSupervisor
        fabric_adapter = AttendedFabricWorkerAdapter(runtime, fabric_worker_binding_source,
            request_client_factory=fabric_worker_binding_source.client_for,
            attended_probe_source=fabric_attended_probe_source)
        owners = {config.worker_id: primary}
        for physical in fabric_worker_binding_source.bindings:
            if physical.worker_id in owners:
                continue  # Principal conflicts were refused before clients.
            finite_definition = (fabric_attended_probe_source.configuration(physical)[1]
                if fabric_attended_probe_source is not None else None)
            # Keep canonical Job worktrees on Control. Only this finite owner's
            # new Attempt inputs use its protected, separately enrolled store.
            runs_root = (finite_definition['run_root'] if finite_definition is not None
                         else raw['worker_runs_root'])
            owners[physical.worker_id] = ExecutiveSupervisor(
                runtime, fabric_adapter,
                runs_root=runs_root,
                isolation_roots=(raw["proof_workspace_root"], runs_root),
                receipts_root=raw["receipts_root"],
                worker_user=raw["worker_user"], worker_uid=physical.worker_uid,
                worker_gid=physical.worker_gid,
                # Ordinary Fabric retains Control's original filesystem group.
                # The separately enrolled finite store uses its exact worker
                # group; actual Control membership is checked before allocation.
                shared_run_gid=(physical.worker_gid if finite_definition is not None
                                else raw["shared_run_gid"]),
                secret_canary_verdict={}, require_complete_launch_attestation=True,
                cleanup_policy=CleanupPolicy.FABRIC_PROCESS_GROUP,
                process_controller=fabric_adapter, instance_id=primary.instance_id,
                product_acceptance_macro_root=product_acceptance_macro_root,
                product_acceptance_context_reader=(product_acceptance_basis_reader()
                    if product_acceptance_context_owner is not None else None),
            )
        initial_admission = None
        if native_capacity_source is not None:
            from control_plane.finite_initial_admission import FiniteInitialAdmission
            initial_admission = FiniteInitialAdmission(native_capacity_source)
        mixed = MixedExecutionOwnerSupervisor(primary, owners, initial_admission=initial_admission)
        recovery_controller["owners"] = mixed.owners
        return mixed

    def operator_supervisor_factory(runtime, sealed_supervisor):
        from control_plane.mixed_worker_supervisor import MixedExecutionOwnerSupervisor
        def primary_factory(attempt, requested, turn_input_loader, *, recovery):
            # A fixed primary client must never carry another claimed worker.
            # Multi-worker composition supplies its current owner-bound factory.
            if (attempt.worker_id != config.worker_id
                    or requested.worker_id != config.worker_id
                    or requested.provider != "openai-codex"
                    or requested.harness_kind != "codex-app-server"):
                raise ServiceError("claim differs from the configured operator worker")
            return RemoteCodexOperatorAdapter(
                client,
                turn_input_loader=turn_input_loader,
            )

        factory = claimed_operator_adapter_factory
        workspace_source = None
        if remote_operator_binding_source is not None:
            from control_plane.remote_attempt_transport import (
                build_claimed_remote_operator_factory,
                build_claimed_remote_workspace_identity_source,
            )
            factory = build_claimed_remote_operator_factory(runtime, remote_operator_binding_source)
            workspace_source = build_claimed_remote_workspace_identity_source(
                runtime, remote_operator_binding_source
            )
        return ExecutiveOperatorSupervisor(
            runtime,
            claimed_adapter_factory=(factory if factory is not None else primary_factory),
            workspace_identity_source=workspace_source,
            foreground_only=config.coo_foreground_only,
            prompt_source=(sealed_supervisor.primary
                           if type(sealed_supervisor) is MixedExecutionOwnerSupervisor
                           else sealed_supervisor),
            plan_schema_version=plan_schema_version,
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
                result_synopsis_version="v2",
            )

        terminal_return_kwargs["terminal_return_projector_factory"] = (
            terminal_return_projector_factory
        )

    from integrations.executive_mcp.web_ceo import WEB_CEO_V2_PROFILE
    from integrations.executive_mcp.web_ceo_sessions import WEB_CEO_SESSIONS_PROFILE
    from integrations.executive_mcp.web_ceo_v3 import (
        WEB_CEO_V3_PROFILE,
        validate_installed_mcp_profile_current,
    )

    try:
        installed_profile = validate_installed_mcp_profile_current(
            raw.get("executive_mcp_profile", "legacy")
        )
    except ValueError:
        raise ServiceError("installed Executive MCP profile is invalid") from None
    if "executive_mcp_profile" in raw and not (
        _CEO_INGRESS_APP_CONFIG_KEYS <= set(raw)
        and _CEO_INGRESS_CONFIG_KEYS <= set(raw)
    ):
        raise ServiceError("App binding requires all App and CeoIngress configuration fields")

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
    workspace_control_room = None
    if _CEO_INGRESS_APP_CONFIG_KEYS <= set(raw):
        # SDK-free canonical projection runs under the existing control uid.
        # The network App has no Runtime database or source-checkout access.
        # Commission lookup is likewise host-owned. Provider construction is
        # network-inert; observations occur only during trusted admission.
        from integrations.mastermind_executive_app.web_commission_source import (
            GitHubWebCommissionSourceProvider,
        )

        commission_source_provider = GitHubWebCommissionSourceProvider()

        reader_kwargs = dict(
            repo_root=Path(raw["proof_source_repository"]),
            macro_root=Path(raw["ceo_ingress_app_macro_root"]),
            runtime_root=Path(raw["runtime_root"]),
            boot_python=(Path(raw["ceo_ingress_app_boot_python"])
                         if "ceo_ingress_app_boot_python" in raw else None),
            code_root=Path(__file__).resolve().parents[1],
            expected_source_sha=str(raw["proof_base_sha"]),
        )
        if installed_profile in {
            WEB_CEO_V2_PROFILE,
            WEB_CEO_V3_PROFILE,
            WEB_CEO_SESSIONS_PROFILE,
        }:
            from integrations.executive_mcp.web_ceo import (
                WebCeoV2InstalledExecutiveReaders,
            )
            readers = WebCeoV2InstalledExecutiveReaders(**reader_kwargs)
            from control_plane.fabric_job_view import ARM_KEYS
            readers.bind_fabric_source(
                bounded_runtime=lambda: service._namespace_custody.bound_runtime(
                    service._require_runtime()
                ),
                armed={
                    **{
                        key: raw.get(key) if type(raw.get(key)) is bool else None
                        for key in ARM_KEYS
                    },
                    "source": "control.json",
                },
                runtime_identity={"root": None, "db_present": True, "identity": None},
            )
            app_read_schema = CEO_WEB_CEO_V2_READ_SCHEMA
        else:
            from integrations.executive_mcp.installed import InstalledExecutiveReaders
            readers = InstalledExecutiveReaders(**reader_kwargs)
            app_read_schema = CEO_APP_READ_SCHEMA
        content_factories = {}
        if {"content_observer", "content_observer_profile_path"} & set(raw):
            from control_plane.executive_content_observer import ExecutiveContentObserver
            from integrations.mastermind_steward_app.installed_reads import InstalledStewardReadProvider
            from datetime import datetime, timezone
            import time
            if content_profile_loader is None:
                raise ServiceError("sealed current content profile loader is required")
            content_factories = {
                "content_provider_factory": lambda runtime: ExecutiveContentObserver(
                    runtime=runtime, broker_client=client, profile_loader=content_profile_loader,
                    now=lambda: int(time.time())),
                "steward_provider_factory": lambda runtime: InstalledStewardReadProvider(
                    readers=readers, runtime=runtime, bindings_path=None,
                    now=lambda: datetime.now(timezone.utc)),
            }
        workspace_factories = {}
        if "workspace_acquisition" in raw:
            from integrations.business_mcp_auth.contracts import load_resource_policy
            from integrations.mastermind_workspace_app.contract import workspace_authorizers
            from control_plane.workspace_control_room_lifecycle import HostedControlRoom
            from control_plane.workspace_read_service import workspace_provider_factory
            from scripts.chairman_control_room import ServerConfig
            from control_plane.fabric_job_view import ARM_KEYS
            import secrets
            if workspace_acquisition_loader is None:
                raise ServiceError("sealed current workspace acquisition loader is required")
            policy = load_resource_policy(raw["workspace_resource_policy"])
            _, authorize = workspace_authorizers(policy=policy, load_bindings=workspace_acquisition_loader)
            # Installed source join: the trusted parent builds the composer from
            # the same sealed roots the readers use, never from the public App.
            # The collector is the existing installed one, constructed directly
            # with the attested boot interpreter and sealed source SHA.  The
            # custody callback stays late-bound: it closes over the local
            # ``service`` built below and is only ever invoked by the off-demand
            # refresh, after that service has started.  A ``None`` bindings path
            # stays an explicit unavailable binding — no HOME expansion.
            if "ceo_ingress_app_boot_python" not in raw:
                raise ServiceError("workspace acquisition requires the sealed boot interpreter")
            from control_plane.workspace_source_join import build_workspace_composer
            from integrations.executive_mcp.installed import InstalledBootPacketCollector
            packet_collector = InstalledBootPacketCollector(
                source_root=Path(raw["proof_source_repository"]),
                macro_root=Path(raw["ceo_ingress_app_macro_root"]),
                code_root=Path(__file__).resolve().parents[1],
                python_executable=_attest_app_boot_runtime(
                    Path(raw["ceo_ingress_app_boot_python"])),
                expected_source_sha=str(raw["proof_base_sha"]),
            )
            if product_acceptance_macro_root is not None:
                product_acceptance_context_owner = packet_collector
            compose_inputs = build_workspace_composer(
                packet_collector=packet_collector,
                repo_root=Path(raw["proof_source_repository"]),
                macro_root=Path(raw["ceo_ingress_app_macro_root"]),
                bounded_runtime=lambda: service._namespace_custody.bound_runtime(
                    service._require_runtime()),
                bindings_path=workspace_bindings_path,
            )
            # Existing source paths and existing controller permissions only.
            # Bind the installation-selected incumbent topology before publishing.
            # Closed AF_UNIX launchd listener; never a TCP loopback port.
            room_listener = activate_launchd_socket(_WORKSPACE_CONTROL_ROOM_SOCKET_NAME)
            activated_listeners.append(room_listener)
            from scripts.chairman_control_room import UNIX_CONTROL_ROOM_ORIGIN
            workspace_control_room = HostedControlRoom(
                ServerConfig(
                    repo_root=Path(raw["proof_source_repository"]),
                    macro_root=str(raw["ceo_ingress_app_macro_root"]),
                    bindings_path=workspace_bindings_path,
                    token=secrets.token_urlsafe(32),
                    origin=UNIX_CONTROL_ROOM_ORIGIN,
                    port=0,
                    compose_inputs=compose_inputs,
                ),
                listener=room_listener,
                socket_path=str(raw["workspace_control_room"]["socket_path"]),
                allowed_peer_uids=tuple(raw["workspace_control_room"]["allowed_peer_uids"]),
            )
            from integrations.product_acceptance_read import read_acceptance
            from integrations.product_acceptance_selector import read_original_acceptance_observation
            from ops.executive_os.coo_principal_host import CooInstalledSource, validate_control_coo
            original_target = original_target_guard = None
            if validate_control_coo(raw) and type(coo_source) is CooInstalledSource:
                # Same installed source already selected by _serve_from_config.
                # HTTP and Runtime rows cannot nominate or rotate this target.
                target_reader = coo_source.original_acceptance_target
                original_target = target_reader()
                if original_target is not None:
                    def original_target_guard():
                        if target_reader() is not original_target:
                            raise ServiceError("installed acceptance target changed")
            workspace_factories["workspace_read_provider_factory"] = workspace_provider_factory(
                control_room=workspace_control_room, authorize=authorize,
                armed={**{key: raw.get(key) if type(raw.get(key)) is bool else None for key in ARM_KEYS}, "source": "control.json"},
                runtime_identity={"root": None, "db_present": True, "identity": None},
                # The factory is inert until the actual service has started.
                # Namespace custody belongs to that service and validates the
                # exact Runtime supplied by its App request handler.
                bounded_runtime=lambda runtime: service._namespace_custody.bound_runtime(runtime),
                product_acceptance_basis_reader=packet_collector.product_acceptance_basis_reader(
                    macro_root=Path(raw["ceo_ingress_app_macro_root"])),
                product_acceptance_owner_target=original_target,
                product_acceptance_owner_guard=original_target_guard,
                product_acceptance_read=read_acceptance,
                product_acceptance_observe=read_original_acceptance_observation)
        coo_factories = {}
        from ops.executive_os.coo_principal_host import CooInstalledSource, validate_control_coo
        from control_plane.coo_principal_host import CooHostProvider
        if validate_control_coo(raw):
            if type(coo_source) is not CooInstalledSource or "workspace_read_provider_factory" not in workspace_factories:
                raise ServiceError("COO principal requires the sealed source and existing Workspace owner")
            def coo_factory(runtime):
                return CooHostProvider(coo_source, workspace_factories["workspace_read_provider_factory"](runtime))
            coo_factories = dict(principal_facts_factory=coo_factory, principal_admission_armed=True,
                principal_admission_guard=lambda envelope: coo_factory(service._require_runtime()).guard(envelope))
            if raw.get("coo_principal_dialogue_armed", False) is True:
                from integrations.mastermind_company_principal_app_receiver import PrincipalDialogueAppReceiver
                from integrations.slack_agent_dialogue.host_local_observation import HostLocalDialogueObservationReader

                def principal_dialogue_factory(runtime):
                    # The incumbent namespace/Workspace owner validates this
                    # Runtime; the reader additionally requires this exact
                    # Control service and opens no Relay-only observation socket.
                    service._namespace_custody.bound_runtime(runtime)
                    authority = coo_factory(runtime)
                    return PrincipalDialogueAppReceiver(runtime, authority,
                        relay_readside_socket_path,
                        HostLocalDialogueObservationReader(service, runtime),
                        product_acceptance_reader=product_acceptance_basis_reader())

                coo_factories["principal_dialogue_provider_factory"] = principal_dialogue_factory
        session_factories = {}
        if installed_profile in {WEB_CEO_SESSIONS_PROFILE, WEB_CEO_V3_PROFILE}:
            from integrations.session_bridge.installed import build_runtime_session_bridge
            from integrations.session_bridge.native_backends import ExecutiveSummonAdapter
            from integrations.session_bridge.schemas import BridgeError
            from integrations.mastermind_executive_app.gateway import READ_SCOPE, SUBMIT_SCOPE
            from control_plane import executive_ceo_ingress as session_ingress, ceo_request

            def session_bridge_factory(runtime):
                # Validate the supplied live Runtime through the incumbent
                # namespace owner before constructing any projection or writer.
                service._namespace_custody.bound_runtime(runtime)
                binding = service._ceo_ingress_app_binding

                def require_session_admission(_envelope=None):
                    if (binding is not service._ceo_ingress_app_binding
                            or not binding.armed or service._closing
                            or service._service_state not in {"READY", "AWAITING_CANARY"}):
                        raise BridgeError("ingress_unavailable", "Executive admission is unavailable")

                async def submit_summon(payload):
                    require_session_admission()
                    from control_plane.foreground_operation import (
                        ForegroundOperationRefusal, _current_foreground_operation_or_none,
                    )
                    from control_plane.ceo_intent import _FreshAdmissionObserverFailed
                    try:
                        operation = _current_foreground_operation_or_none()
                        qualification = service._require_attended_qualification()
                        if operation is not None:
                            operation.require_arguments(payload)
                    except ForegroundOperationRefusal as exc:
                        raise BridgeError(exc.code, exc.message) from None

                    expectation = None

                    def require_summon_session(_envelope=None):
                        require_session_admission(_envelope)
                        if service._require_attended_qualification() != qualification:
                            raise BridgeError("ingress_unavailable", "Executive qualification changed")
                        if operation is not None:
                            operation.require_arguments(payload)

                    def require_summon_admission(_envelope=None):
                        require_summon_session(_envelope)
                        if operation is not None:
                            try:
                                if expectation is None:
                                    raise ValueError("fresh foreground binding is unavailable")
                                service._require_foreground_execution(expectation)
                            except Exception:
                                raise BridgeError("ingress_unavailable", "Executive admission is unavailable") from None

                    def current_execution_binding():
                        nonlocal expectation
                        current = service._require_coo_admission_binding()
                        if operation is not None:
                            # This callback is fresh-only. Durable duplicates
                            # do not require renewed autonomy or current routing.
                            if expectation is None:
                                expectation = service._foreground_execution_state(binding=current)
                            # Exact immutable request-local binding, including
                            # queued-mode reasons, must survive fresh admission.
                            if current != json.loads(expectation.binding):
                                raise ValueError("foreground binding changed")
                            return json.loads(expectation.binding)
                        return current

                    def observe_fresh_admission(root_id, command_id):
                        # This callback is post-commit. Configuration drift
                        # retains the original root as EFFECT_UNKNOWN and
                        # prevents binding/driving it; it is not rollback.
                        require_summon_session()
                        operation._bind_admitted_root(root_id, command_id)

                    request = dict(payload)
                    request_ref = ceo_request.app_request_ref(request.pop("operation_key"))
                    try:
                        observed = await session_ingress._observe_trusted_grounding(readers)
                        require_summon_session()
                        async with service._foreground_cycle_scope(operation):
                            receipt = await service._run_owned_coroutine(session_ingress.handle_frame(
                                {"schema": session_ingress.SUBMIT_SCHEMA_V2,
                                 "request_ref": request_ref, "observed_grounding": observed,
                                 "request": request},
                                runtime=runtime, grounding_provider=readers,
                                workspace_root=config.proof_workspace_root,
                                service_state=service._service_state,
                                ceo_ingress_armed=binding.armed,
                                strict_v2_admission=True,
                                execution_binding_provider=current_execution_binding,
                                frontier_selection_provider=service._resolve_ceo_frontier_selection,
                                dialogue_source_provider=commission_source_provider,
                                admission_guard=require_summon_admission,
                                fresh_admission_observer=(
                                    observe_fresh_admission if operation is not None else None
                                ),
                            ))
                            if expectation and receipt.get("duplicate") is False:
                                try:
                                    operation.require_root(receipt["job_id"])
                                    completion = await service._drive_foreground_cycle(operation, receipt["job_id"])
                                except Exception:
                                    raise BridgeError("effect_unknown", "reconcile the original Executive operation") from None
                                # Preserve the immutable QUEUED admission receipt.
                                # Result delivery is a distinct current-call fact.
                                receipt = {**receipt, "foreground_completion": completion}
                    except _FreshAdmissionObserverFailed:
                        raise BridgeError("effect_unknown", "reconcile the original Executive operation") from None
                    except ForegroundOperationRefusal as exc:
                        # This occurs before the canonical sink's guarded
                        # commit. Post-commit observer failures are above.
                        raise BridgeError(exc.code, exc.message) from None
                    except session_ingress.CeoIngressError as exc:
                        # Canonical owner classifies its durable effect/refusal.
                        raise BridgeError(exc.code, exc.message) from None
                    # After the mutation owner returns, drift cannot be described
                    # as a zero-effect refusal. The private transport preserves it.
                    try:
                        if receipt.get("duplicate") is True:
                            require_summon_session()
                        else:
                            require_summon_admission()
                    except (BridgeError, ForegroundOperationRefusal):
                        raise BridgeError("effect_unknown", "reconcile the original Executive operation") from None
                    return receipt

                adapter = ExecutiveSummonAdapter(submit_summon)
                async def summon(principal, arguments):
                    if not {READ_SCOPE, SUBMIT_SCOPE} <= set(principal.scopes):
                        raise BridgeError("authority_refused", "Executive submit scopes are required")
                    return await adapter(arguments)

                def codex_owner_configured():
                    from ops.executive_os.a2_agent_relay_enrollment import w3c_plist_configured
                    # Canonical CONTINUE is carrier-only. The current Runtime
                    # projector proves native ownership; Wake arming is separate.
                    return w3c_plist_configured(release_sha=config.proof_base_sha)

                return build_runtime_session_bridge(
                    runtime, dialogue_socket_path=relay_readside_socket_path,
                    summon_handler=summon, codex_owner_configured=codex_owner_configured)
            session_factories["session_bridge_provider_factory"] = session_bridge_factory
        ceo_ingress_kwargs["ceo_ingress_app_binding"] = CeoIngressAppBinding(
            peer_uid=int(raw["ceo_ingress_app_peer_uid"]),
            armed=raw["ceo_ingress_app_armed"],
            grounding_provider=readers, read_provider=readers,
            read_schema=app_read_schema,
            **content_factories, **workspace_factories, **coo_factories, **session_factories,
        )
        ceo_ingress_kwargs["ceo_ingress_dialogue_source_provider"] = (
            commission_source_provider
        )
    dialogue_observation_kwargs: dict[str, Any] = {}
    if (
        _DIALOGUE_BRIDGE_CONFIG_KEYS <= set(raw)
        and (raw["dialogue_bridge_armed"] is True
             or dialogue_canary_profile.grant is not None
             or native_dialogue_canary_profile_loader is not None)
    ):
        from control_plane.dialogue_wake_canary_activation import DialogueWakeCanaryProfile

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
                carrier_factory=_build_executive_dialogue_wake_carrier,
                # An absent grant stays an explicit disarmed profile; it must
                # never select the generic carrier path after grant removal.
                canary_profile=dialogue_canary_profile,
                native_canary_profile_loader=native_dialogue_canary_profile_loader,
                installed_release_sha=config.proof_base_sha,
                canary_now_epoch_seconds=lambda: int(time.time()),
            ),
            "dialogue_observation_activated_socket": observation_listener,
        }
    company_binding = None
    company_socket = company_consultation_launchd_entry(raw)
    if company_socket is not None:
        from control_plane.executive_service import CompanyConsultationBinding
        from integrations.company_consultation_host import CompanyConsultationHost
        from ops.executive_os.a2_agent_relay_enrollment import SLACK_WORKSPACE_ID, SLACK_CHANNEL_ID

        company_repository = Path(raw["proof_source_repository"])
        company_worker_uid = int(raw["worker_uid"])
        acceptance_selected = raw["company_consultation"].get("product_acceptance_armed", False)
        acceptance_reader = None
        if acceptance_selected:
            if product_acceptance_context_owner is None or product_acceptance_macro_root is None:
                raise ServiceError("Product acceptance requires the sealed Context and Workspace owners")
            acceptance_reader = product_acceptance_basis_reader()
        answer_bridge = dialogue_observation_kwargs.get("dialogue_wake_handler")
        if answer_bridge is None or answer_bridge.canary_profile is not None:
            # Company answer obligations keep their incumbent generic owner;
            # the closed parenting canary handles only Dialogue turn sources.
            from control_plane.wake_ledger import WakeRetryPolicy
            def company_wake_turn_input_loader(_turn):
                raise ServiceError("Company answer Wake cannot load provider turns")
            answer_bridge = ExecutiveDialogueWakeBridge(
                target_provider=None,
                retry_policy=raw.get("dialogue_wake_retry_policy", WakeRetryPolicy(armed=False)),
                operator_adapter=RemoteCodexOperatorAdapter(
                    client, turn_input_loader=company_wake_turn_input_loader,
                ),
                carrier_factory=_build_executive_dialogue_wake_carrier,
            )
        def company_host_factory(runtime):
            async def dispatch_answer(projection):
                service._require_company_answer_attention()
                return await answer_bridge.dispatch_requester_answer(
                    runtime, projection, before_effect=service._require_company_answer_attention,
                )
            acceptance_host = None
            if acceptance_selected:
                from integrations.product_acceptance_request_host import ProductAcceptanceRequestHost
                service._namespace_custody.bound_runtime(runtime)
                acceptance_host = ProductAcceptanceRequestHost(
                    runtime=runtime, reader=acceptance_reader, worker_uid=company_worker_uid,
                    relay_socket_path=relay_readside_socket_path,
                    workspace_id=SLACK_WORKSPACE_ID, channel_id=SLACK_CHANNEL_ID,
                    armed=True, principal_authority=coo_factory(runtime))
            return CompanyConsultationHost(
                runtime=runtime, repository_root=company_repository,
                worker_uid=company_worker_uid, relay_socket_path=relay_readside_socket_path,
                workspace_id=SLACK_WORKSPACE_ID, channel_id=SLACK_CHANNEL_ID,
                requester_answer_wake_dispatch=dispatch_answer,
                product_acceptance_host=acceptance_host,
                native_return_armed=raw["company_consultation"].get("native_return_armed", False))
        company_listener = activate_launchd_socket(_COMPANY_CONSULTATION_SOCKET_NAME)
        activated_listeners.append(company_listener)
        company_binding = CompanyConsultationBinding(
            socket_path=Path(company_socket["SockPathName"]), worker_uid=company_worker_uid,
            group_gid=int(raw["worker_gid"]), host_factory=company_host_factory,
            activated_socket=company_listener)
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
    readiness_factory = None
    if config.privileged_readiness_armed:
        from control_plane.executive_privileged_authority import PrivilegedReadinessController
        def readiness_factory(runtime):
            return PrivilegedReadinessController(runtime, release_sha=config.proof_base_sha)
    attended_registration = None
    if qualification_for(attended_work_placements) is not None:
        from control_plane.fabric_attended_registration import register_fixed_finite
        def attended_registration(runtime):
            if native_capacity_source is not None:
                from control_plane.finite_initial_registration import register_initial
                return register_initial(runtime, attended_work_placements[0],
                    native_capacity_source, autonomy_guard)
            return register_fixed_finite(runtime, attended_work_placements[0],
                fabric_worker_binding_source, fabric_attended_probe_source, autonomy_guard)
    service = ExecutiveControlService(
        config,
        supervisor_factory=supervisor_factory,
        attended_worker_registration=attended_registration,
        paid_worker_binding_source=paid_worker_binding_source,
        privileged_readiness_controller_factory=readiness_factory,
        proof_capacity_recovery_observer=proof_capacity_recovery_observer,
        proof_capacity_recovery_worker_uid=(
            int(raw["worker_uid"]) if (remote_worker_binding_source is None
                                       and fabric_worker_binding_source is None)
            else proof_capacity_recovery_worker_uid
        ),
        operator_supervisor_factory=operator_supervisor_factory,
        operator_identity_verifier=(
            verify_operator_identity if expected_operator_arm else None
        ),
        autonomy_guard=autonomy_guard,
        ceo_submit_admission_guard=ceo_submit_admission_guard,
        activated_socket=listener,
        service_state="READY" if initially_ready else "AWAITING_CANARY",
        canary_loader=canary_loader,
        workspace_control_room=workspace_control_room,
        company_consultation_binding=company_binding,
        **ceo_ingress_kwargs,
        **dialogue_observation_kwargs,
        **terminal_return_kwargs,
    )
    return service


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


def _ceo_admission_guard(raw: Mapping[str, Any], config_path: Path,
                         attestation_loader: Callable[[], Mapping[str, Any]]) -> Callable[[], None]:
    """One production callback shared by submission and private current observation."""
    own_config_sha256 = _sha256_file(config_path)

    def require_ceo_admission() -> None:
        from ops.executive_os.autonomy_control import require_ceo_submit_runtime_admission
        try:
            attestation = attestation_loader()
        except Exception as exc:
            raise CeoAdmissionPhaseRefusal("attestation_refused") from exc
        try:
            current_config_bytes = config_path.read_bytes()
            if (attestation["config_sha256"] != own_config_sha256
                    or hashlib.sha256(current_config_bytes).hexdigest() != own_config_sha256):
                raise ServiceError("CEO admission config changed")
            receipt_config = raw
            for field in ("ceo_ingress_socket_path", "ceo_ingress_app_macro_root"):
                if isinstance(raw.get(field), Path):
                    if receipt_config is raw:
                        receipt_config = dict(raw)
                        encoded_config = json.loads(current_config_bytes)
                    # The loader resolves aliases for service I/O. Receipts bind
                    # the exact JSON strings, not that resolved spelling. Parse
                    # only the same bytes whose hash matched the attestation,
                    # and refuse if they no longer describe the loaded route.
                    encoded_path = encoded_config[field]
                    if _path(encoded_path, field) != raw[field]:
                        raise ServiceError("CEO admission loaded path changed")
                    receipt_config[field] = encoded_path
        except Exception as exc:
            raise CeoAdmissionPhaseRefusal("config_binding_refused") from exc
        try:
            require_ceo_submit_runtime_admission(receipt_config, own_config_sha256=own_config_sha256)
        except Exception as exc:
            raise CeoAdmissionPhaseRefusal("receipt_refused") from exc

    return require_ceo_admission


async def _serve_from_config(config_path: Path, *, attended_work_placements: tuple = (),
                             _installed_control: bool = False) -> None:
    installed_config_sha256 = _sha256_file(config_path) if _installed_control else None
    raw = load_control_config(config_path)
    # Only a fixed host composition may select typed placements. Merely
    # staging a file or setting a JSON flag cannot activate its worker owners.
    physical_source = _staged_fabric_binding_source(raw)
    from control_plane.executive_paid_fabric_composition import installed_paid_source
    paid_source=installed_paid_source(raw,installed_control=_installed_control)
    if paid_source is not None and (physical_source is not None or attended_work_placements):
        raise ServiceError('installed paid source cannot replace or mix an attended owner')
    if _installed_control:
        if attended_work_placements:
            raise ServiceError('installed Control cannot replace its fixed source composition')
        from control_plane.fabric_attended_routing import installed_control_placements, FINITE_SOCKET_PATH
        attended_work_placements = installed_control_placements(raw)
        if attended_work_placements and _sha256_file(config_path) != installed_config_sha256:
            raise ServiceError('installed finite Control definition changed while loading')
        if attended_work_placements and (physical_source is None
                or len(physical_source.bindings) != 1
                or physical_source.bindings[0].worker_id != 'minimax-finite-01'
                or physical_source.bindings[0].provider != 'minimax'
                or physical_source.bindings[0].socket_path != FINITE_SOCKET_PATH):
            raise ServiceError('installed finite composition requires its one physical owner')
    from control_plane.fabric_attended_routing import AttendedWorkPlacement, placement_member, qualification_for
    if (type(attended_work_placements) is not tuple
            or len(attended_work_placements) > 6
            or any(type(item) is not AttendedWorkPlacement for item in attended_work_placements)):
        raise ServiceError('attended placements require bounded typed host configuration')
    if qualification_for(attended_work_placements) is not None and raw.get('coo_foreground_only') is not True:
        raise ServiceError('finite qualification requires foreground-only host configuration')
    if attended_work_placements:
        if physical_source is None or 'fabric_attended_probe' not in raw:
            raise ServiceError('attended placements require the binding and startup probe sources')
        # Refuse an unselected/disabled catalogue before any host canary call.
        # The constructor checks the current catalogue again before clients.
        from control_plane.model_router import ModelRouter
        router = ModelRouter.load()
        for placement in attended_work_placements:
            placement_member(router, placement)
    control_attestation = _load_control_environment_attestation(
        Path(raw["control_environment_attestation_path"]),
        config_path=config_path,
        expected_release_sha=str(raw["proof_base_sha"]),
    )
    exact_target_source = _bind_exact_worker_target_source(
        raw, control_attestation, _producer_capability=_CONTROL_TARGET_COMPOSITION,
        attestation_loader=lambda: _load_control_environment_attestation(
            Path(raw["control_environment_attestation_path"]), config_path=config_path,
            expected_release_sha=str(raw["proof_base_sha"]),
        ),
    )
    content_attestation_loader = lambda: _load_control_environment_attestation(
        Path(raw["control_environment_attestation_path"]),
        config_path=config_path,
        expected_release_sha=str(raw["proof_base_sha"]),
    )
    hot_content_profile_source = _bind_hot_content_profile_source(
        raw,
        control_attestation,
        config_path=config_path,
        attestation_loader=content_attestation_loader,
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
        finite_installed = _installed_control and bool(attended_work_placements)
        if finite_installed:
            own_config_sha256 = control_attestation['config_sha256']
            if own_config_sha256 != installed_config_sha256:
                raise ServiceError('installed finite Control attestation changed')
        release_sha = str(raw["proof_base_sha"])

        def require_autonomy() -> None:
            if finite_installed and _sha256_file(config_path) != own_config_sha256:
                raise ServiceError('installed finite Control definition changed')
            try:
                validate_runtime_guard_file(
                    AUTONOMY_RECEIPT,
                    role="control",
                    own_config_sha256=own_config_sha256,
                    release_sha=release_sha,
                )
            except AutonomyRefusal as exc:
                raise ServiceError("Executive autonomy receipt refused") from exc
            if finite_installed and _sha256_file(config_path) != own_config_sha256:
                raise ServiceError('installed finite Control definition changed')

        autonomy_guard = require_autonomy
        require_autonomy()
        initial_canary = await _request_boot_autonomy_canary(
            raw,
            control_attestation,
            persist_path=canary_path,
        )

    content_profile_loader: Callable[[], Any] | None = None
    if hot_content_profile_source is not None:
        content_profile_loader = hot_content_profile_source.load
    elif "content_observer" in raw:
        content_profile_loader = lambda: load_control_config(config_path)[
            "content_observer"
        ]

    coo_source = None
    from ops.executive_os.coo_principal_host import CooInstalledSource, DEFAULT_INSTALL_PATH, validate_control_coo
    if validate_control_coo(raw):
        coo_source = CooInstalledSource.from_path(DEFAULT_INSTALL_PATH,
            Path(__file__).resolve().parents[1], expected_uid=os.geteuid())
    from ops.executive_os.dialogue_wake_canary_control import load_verified_profile
    dialogue_canary_profile = load_verified_profile(
        control_sha256=control_attestation["config_sha256"],
        release_sha=raw["proof_base_sha"],
        grant=raw.get("dialogue_wake_canary_activation"),
    )
    native_dialogue_canary_profile_loader = None
    if (raw.get("coo_operator_model_alias") == "coo.operator.native-return"
            and raw.get("company_consultation", {}).get("native_return_armed") is True):
        from ops.executive_os.dialogue_wake_canary_control import require_native_selection, load_native_verified_profile
        require_native_selection(raw)
        bound_native_control_sha256 = control_attestation["config_sha256"]
        def native_dialogue_canary_profile_loader():
            # This changes only the bound grant. Ambient config/attestation,
            # admission flags, Runtime and current writer retain their owners.
            service._require_company_answer_attention()
            current = content_attestation_loader()
            if (current["config_sha256"] != bound_native_control_sha256
                    or _sha256_file(config_path) != bound_native_control_sha256):
                raise ServiceError("native grant cannot rebind Control configuration")
            return load_native_verified_profile(service._require_runtime(),
                control_sha256=bound_native_control_sha256, release_sha=raw["proof_base_sha"])
    # Bind fresh public CEO admission to the exact running config and the
    # existing root-owned receipt pair. Never read worker-codex.json as Control.
    require_ceo_admission = _ceo_admission_guard(raw, config_path, content_attestation_loader)
    from control_plane.fabric_attended_canary import AttendedControlProbeSource

    service = _service_from_config(
        raw,
        fabric_worker_binding_source=physical_source if attended_work_placements else None,
        paid_worker_binding_source=paid_source,
        attended_work_placements=attended_work_placements,
        fabric_attended_probe_source=(
            AttendedControlProbeSource.from_startup(config_path, raw, control_attestation)
            if 'fabric_attended_probe' in raw else None),
        dialogue_canary_profile=dialogue_canary_profile,
        native_dialogue_canary_profile_loader=native_dialogue_canary_profile_loader,
        canary_loader=load_canary,
        autonomy_guard=autonomy_guard,
        ceo_submit_admission_guard=require_ceo_admission,
        initial_canary=initial_canary,
        content_profile_loader=content_profile_loader,
        workspace_acquisition_loader=lambda: load_control_config(config_path)["workspace_acquisition"],
        **({"coo_source": coo_source} if coo_source is not None else {}),
        **({"exact_target_source": exact_target_source} if exact_target_source is not None else {}),
    )
    await service.serve_until_stopped()


def serve_installed_control(config_path: Path) -> int:
    """Canonical wrapper entry; same service/guard, fixed source composition."""
    try:
        asyncio.run(_serve_from_config(config_path, _installed_control=True))
        return 0
    except (OSError, RuntimeProofError, ServiceError, ValueError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2


def _client_request(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    if args.command == "status" and getattr(args, "ceo_admission", False):
        return "status", {"ceo_admission": True}
    if args.command in {
        "content-observer-enroll", "content-observer-status", "content-observer-revoke",
        "status",
        "health",
        "activate-canary",
        "workers",
        "jobs",
        "register-worker",
        "paid-capacity-observe",
        "paid-capacity-bootstrap",
        "create-proof-job",
        "reconcile",
        "backup",
    }:
        if args.command.startswith("content-observer-") and hasattr(args, 'profile_key') and args.profile_key:
            return args.command, {"profile_key": args.profile_key}
        return args.command, {}
    if args.command == "recover-proof-capacity":
        return args.command, {"job_id": args.job_id, "lost_attempt_id": args.lost_attempt_id}
    if args.command in {"job", "dispatch", "cancel", "requeue"}:
        return args.command, {"job_id": args.job_id}
    if args.command == "check-current-worker-login":
        return args.command, {"job_id": args.job_id, "attempt_id": args.attempt_id,
                              "fence_generation": args.fence_generation}
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
    return restore_backup_offline(
        Path(config["runtime_root"]), database, manifest,
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
    # asdict() skips to_dict() on nested dataclasses and leaves Enums as-is; neither
    # applies to WakeRetryPolicy (flat, frozen, bool/int/None fields).
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _jsonable(dataclasses.asdict(value))
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
