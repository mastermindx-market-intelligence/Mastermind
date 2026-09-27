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
        PersistedWakeCarrier,
    )

    wake_client = CodexCurrentWriterWakeClient(
        operator_adapter=resolved.operator_adapter,
        generation=generation,
        attempt_id=resolved.target_attempt_id,
        runtime_binding=current_binding,
    )
    return PersistedWakeCarrier(
        repository=WakeLedgerRepository(runtime),
        dispatchers=WakeDispatcherRegistry(
            {"codex-app-server": CodexAppServerWakeDispatcher(wake_client)}
        ),
        current_binding_for=lambda _route: project_runtime_binding(
            runtime,
            resolved.target_attempt_id,
            target,
        ),
        retry_policy=retry_policy,
        target_registry=resolved.registry,
    )


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
        "workspace_acquisition",
        "workspace_resource_policy",
        "workspace_control_room",
        "proof_branch",
        "exact_worker_claim_target",
        "worker_id",
        "worker_account_label",
        "quota_class",
        "model",
        "effort",
        "cost_class",
        "coo_autonomy_armed",
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
        ("register-worker", "Register the single configured Codex worker."),
        ("create-proof-job", "Create the fixed harmless Phase 1C-A proof Job."),
        ("reconcile", "Reconcile durable attempts without automatic requeue."),
        ("backup", "Create an online DB backup in the configured backup root."),
    ):
        cmd_parser = sub.add_parser(name, help=help_text)
        if name.startswith("content-observer-"):
            cmd_parser.add_argument(
                "--profile-key",
                choices=["web", "mac"],
                help="Content profile key (web or mac). Omit for legacy single-profile.",
            )

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
        topology = config["workspace_control_room"]
        if (type(topology) is not dict or set(topology) != {"port"}
                or type(topology["port"]) is not int or not 1 <= topology["port"] <= 65535):
            raise ServiceError("workspace Control Room topology refused")
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
    content_profile_loader: Callable[[], Any] | None = None,
    workspace_acquisition_loader: Callable[[], Any] | None = None,
    exact_target_source: _ExactWorkerTargetSource | None = None,
    workspace_bindings_path: Path | None = None,
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
        ceo_submit_armed=raw.get("ceo_submit_armed", False),
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
            exact_target_provider=(
                (lambda job_id: exact_target_source.for_job(job_id, now_ms=runtime.store.now_ms()))
                if exact_target_source is not None else None
            ),
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
                result_synopsis_version="v2",
            )

        terminal_return_kwargs["terminal_return_projector_factory"] = (
            terminal_return_projector_factory
        )

    from integrations.executive_mcp.web_ceo import WEB_CEO_V2_PROFILE
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

        reader_kwargs = dict(
            repo_root=Path(raw["proof_source_repository"]),
            macro_root=Path(raw["ceo_ingress_app_macro_root"]),
            runtime_root=Path(raw["runtime_root"]),
            boot_python=(Path(raw["ceo_ingress_app_boot_python"])
                         if "ceo_ingress_app_boot_python" in raw else None),
            code_root=Path(__file__).resolve().parents[1],
            expected_source_sha=str(raw["proof_base_sha"]),
        )
        if installed_profile in {WEB_CEO_V2_PROFILE, WEB_CEO_V3_PROFILE}:
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
            port = raw["workspace_control_room"]["port"]
            workspace_control_room = HostedControlRoom(ServerConfig(
                repo_root=Path(raw["proof_source_repository"]),
                macro_root=str(raw["ceo_ingress_app_macro_root"]), bindings_path=workspace_bindings_path,
                token=secrets.token_urlsafe(32), origin=f"http://127.0.0.1:{port}", port=port,
                compose_inputs=compose_inputs))
            workspace_factories["workspace_read_provider_factory"] = workspace_provider_factory(
                control_room=workspace_control_room, authorize=authorize,
                armed={**{key: raw.get(key) if type(raw.get(key)) is bool else None for key in ARM_KEYS}, "source": "control.json"},
                runtime_identity={"root": None, "db_present": True, "identity": None},
                # The factory is inert until the actual service has started.
                # Namespace custody belongs to that service and validates the
                # exact Runtime supplied by its App request handler.
                bounded_runtime=lambda runtime: service._namespace_custody.bound_runtime(runtime))
        ceo_ingress_kwargs["ceo_ingress_app_binding"] = CeoIngressAppBinding(
            peer_uid=int(raw["ceo_ingress_app_peer_uid"]),
            armed=raw["ceo_ingress_app_armed"],
            grounding_provider=readers, read_provider=readers,
            read_schema=app_read_schema,
            **content_factories, **workspace_factories,
        )
        ceo_ingress_kwargs["ceo_ingress_dialogue_source_provider"] = (
            GitHubWebCommissionSourceProvider()
        )
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
                carrier_factory=_build_executive_dialogue_wake_carrier,
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
    service = ExecutiveControlService(
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
        workspace_control_room=workspace_control_room,
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


async def _serve_from_config(config_path: Path) -> None:
    raw = load_control_config(config_path)
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

    content_profile_loader: Callable[[], Any] | None = None
    if hot_content_profile_source is not None:
        content_profile_loader = hot_content_profile_source.load
    elif "content_observer" in raw:
        content_profile_loader = lambda: load_control_config(config_path)[
            "content_observer"
        ]

    service = _service_from_config(
        raw,
        canary_loader=load_canary,
        autonomy_guard=autonomy_guard,
        initial_canary=initial_canary,
        content_profile_loader=content_profile_loader,
        workspace_acquisition_loader=lambda: load_control_config(config_path)["workspace_acquisition"],
        **({"exact_target_source": exact_target_source} if exact_target_source is not None else {}),
    )
    await service.serve_until_stopped()


def _client_request(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    if args.command in {
        "content-observer-enroll", "content-observer-status", "content-observer-revoke",
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
        if args.command.startswith("content-observer-") and hasattr(args, 'profile_key') and args.profile_key:
            return args.command, {"profile_key": args.profile_key}
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
