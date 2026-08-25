"""Root-only status/arm/disarm surface for Executive OS autonomy.

The status path is implemented first and is strictly read-only.  Arm and
disarm share this fixed parser but do not acquire mutation behavior until their
transaction gates are implemented and tested in the following plan tasks.
"""

from __future__ import annotations

import argparse
import dataclasses
import grp
import hashlib
import json
import os
import plistlib
import pwd
import re
import stat
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from control_plane.executive_autonomy import (
    ARMED_READY,
    UNARMED,
    AutonomyExpectation,
    AutonomyRefusal,
    ReceiptMetadata,
    StatusEvidence,
    classify_status,
    validate_receipt_document,
)
from ops.executive_os import release_manifest
from ops.executive_os import git_handoff_preflight
from ops.executive_os import provider_readiness


STATUS_SCHEMA_VERSION = "mastermind.executive_autonomy_status/v1"
SYSTEM_ROOT = Path("/Library/Application Support/MastermindExecutive")
CONFIG_ROOT = SYSTEM_ROOT / "config"
RUNTIME_ROOT = Path("/var/db/mastermind-executive")
CONTROL_CONFIG = CONFIG_ROOT / "control.json"
WORKER_CONFIG = CONFIG_ROOT / "worker-codex.json"
AUTONOMY_RECEIPT = CONFIG_ROOT / "autonomy-state-v1.json"
AUTONOMY_TRANSACTION = CONFIG_ROOT / "autonomy-transaction.lock"
PROVIDER_READINESS_RECEIPT = CONFIG_ROOT / "provider-readiness-v2.json"
CONTROL_PLIST = Path("/Library/LaunchDaemons/com.mastermind.executive.control.plist")
WORKER_PLIST = Path("/Library/LaunchDaemons/com.mastermind.executive.worker.codex.plist")
CONTROL_LABEL = "com.mastermind.executive.control"
WORKER_LABEL = "com.mastermind.executive.worker.codex"
CONTROL_SOCKET = Path("/var/run/mastermind-executive/control.sock")
PINNED_PYTHON = Path(
    "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12"
)
CONTROL_USER = "_mastermind_exec"
CONTROL_GROUP = "_mastermind_exec"
WORKER_GROUP = "_mastermind_worker"

CAPABILITY_POLICY_DIGEST = (
    "b8fbfd9065764206b03f835f7fbc09910326f806584a8185229474aff59008b7"
)
EXECUTION_PROFILE_DIGEST = (
    "536853fb01d69ae8deca9a028b55c90aea0d1529f1fc80d83bb20d5d54f2cc44"
)
NATIVE_HELPER_GRANT_DIGEST = (
    "2d5929ea453f368e7b3284b8509fd6e70d5ac16409642c216217c8fb78908c40"
)
SECURITY_CONFIG_DIGEST = (
    "89612a1d7a64a77b9b42fab1522cab3465a7a763ba5be696f8a952ba7eaa366f"
)

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_HOST_CODES = frozenset(
    {
        "command_not_implemented",
        "config_identity_unavailable",
        "config_schema_drift",
        "installed_identity_unavailable",
        "installed_identity_mismatch",
        "platform_unsupported",
        "privilege_required",
        "receipt_invalid",
        "service_identity_ambiguous",
        "status_unavailable",
        "transaction_identity_unsafe",
    }
)
_ARM_ADMISSION_CODES = frozenset(
    {
        "acceptance_fields_mismatch",
        "acceptance_gate_failed",
        "acceptance_not_passed",
        "acceptance_predicate_failed",
        "acceptance_schema_mismatch",
        "acceptance_sha_mismatch",
        "acceptance_receipt_invalid",
        "configs_gate_failed",
        "configs_not_unarmed",
        "credential_expired",
        "credential_expiry_invalid",
        "credential_kind_invalid",
        "gate_b_gate_failed",
        "gate_b_invalid",
        "gate_b_receipt_invalid",
        "gate_b_sha_mismatch",
        "install_gate_failed",
        "readiness_gate_failed",
        "provider_readiness_invalid",
        "runtime_attempt_status_unknown",
        "runtime_gate_failed",
        "runtime_live_attempt",
        "runtime_integrity_failed",
        "services_gate_failed",
        "services_not_stopped",
        "service_uid_process_live",
        "service_uid_process_unknown",
        "transaction_gate_failed",
        "transaction_incomplete",
        "uids_gate_failed",
        "workspace_binding_invalid",
    }
)
_MAX_JSON_BYTES = 1024 * 1024


class HostControlError(RuntimeError):
    def __init__(self, code: str):
        if code not in _HOST_CODES:
            raise ValueError("unknown host-control refusal")
        self.code = code
        super().__init__(code)


class ArmAdmissionError(RuntimeError):
    def __init__(self, code: str):
        if code not in _ARM_ADMISSION_CODES:
            raise ValueError("unknown arm-admission refusal")
        self.code = code
        super().__init__(code)


@dataclasses.dataclass(frozen=True)
class StatusSnapshot:
    expected_sha: str
    installed_sha: str | None
    control_config_sha256: str | None
    worker_config_sha256: str | None
    evidence: StatusEvidence
    refusal_code: str | None = None


@dataclasses.dataclass(frozen=True)
class ArmRequest:
    expected_sha: str
    gate_b_receipt: Path
    expected_credential_kind: str
    workspace_binding_class: str
    credential_expires_at: str


@dataclasses.dataclass(frozen=True)
class ReadinessEvidence:
    receipt_sha256: str
    observed_at: str
    credential_expires_at: str
    readiness_expires_at: str


@dataclasses.dataclass(frozen=True)
class ConfigEvidence:
    control_sha256: str
    worker_sha256: str
    control: Mapping[str, Any]
    worker: Mapping[str, Any]


@dataclasses.dataclass(frozen=True)
class ArmAdmission:
    expected_sha: str
    acceptance_receipt_sha256: str
    gate_b_receipt_sha256: str
    readiness: ReadinessEvidence
    configs: ConfigEvidence
    predicates: Mapping[str, bool]


class StatusHost(Protocol):
    def collect_status(
        self, expected_sha: str, *, now: datetime
    ) -> StatusSnapshot: ...


class ArmAdmissionHost(Protocol):
    def require_exact_install(self, expected_sha: str) -> str: ...

    def validate_acceptance(self, expected_sha: str) -> str: ...

    def validate_gate_b(self, path: Path, expected_sha: str) -> str: ...

    def validate_provider_readiness(
        self, request: ArmRequest, *, now: datetime
    ) -> ReadinessEvidence: ...

    def load_unarmed_configs(self, expected_sha: str) -> ConfigEvidence: ...

    def require_runtime_quiescent(self, config: ConfigEvidence) -> None: ...

    def require_services_stopped(self) -> None: ...

    def require_service_uids_quiescent(self) -> None: ...

    def require_transaction_absent(self) -> None: ...


class _StoreOnce(argparse.Action):
    """Reject repeated authority-bearing flags instead of silently taking last."""

    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is not None:
            parser.error(f"{option_string} may be supplied only once")
        setattr(namespace, self.dest, values)


def _exact_sha(value: str) -> str:
    if _SHA_RE.fullmatch(value) is None:
        raise argparse.ArgumentTypeError(
            "expected SHA must contain exactly 40 lowercase hexadecimal characters"
        )
    return value


def _absolute_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("Gate B receipt path must be absolute")
    return path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Operate the receipt-gated Executive autonomy boundary."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status", help="Classify installed autonomy state.")
    status.add_argument(
        "--expected-sha", type=_exact_sha, action=_StoreOnce, required=True
    )

    arm = sub.add_parser("arm", help="Arm both reviewed Executive configs.")
    arm.add_argument(
        "--expected-sha", type=_exact_sha, action=_StoreOnce, required=True
    )
    arm.add_argument(
        "--gate-b-receipt", type=_absolute_path, action=_StoreOnce, required=True
    )
    arm.add_argument(
        "--expected-credential-kind",
        choices=("device-auth", "personal-access-token", "service-account"),
        action=_StoreOnce,
        required=True,
    )
    arm.add_argument("--workspace-binding-class", action=_StoreOnce, required=True)
    arm.add_argument("--credential-expires-at", action=_StoreOnce, required=True)

    disarm = sub.add_parser("disarm", help="Converge both arm bits to false.")
    disarm.add_argument(
        "--expected-sha", type=_exact_sha, action=_StoreOnce, required=True
    )
    return parser


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


_ACCEPTANCE_FIELDS = frozenset(
    {
        "schema_version",
        "passed",
        "observed_at",
        "exact_origin_master_sha",
        "release_root",
        "control_uid",
        "worker_uid",
        "success_job_id",
        "interrupted_requeued_job_id",
        "detached_session_cleanup",
        "terminal_assignment_sealing",
        "lost_workspace_rotation_boundary",
        "backup_restore",
        "no_public_listener",
        "credential_leakage_scan",
        "financial_scheduler_activation",
    }
)
_ACCEPTANCE_PASS_FIELDS = (
    "detached_session_cleanup",
    "terminal_assignment_sealing",
    "lost_workspace_rotation_boundary",
    "backup_restore",
    "no_public_listener",
    "credential_leakage_scan",
)
_TERMINAL_ATTEMPT_STATUSES = frozenset(
    {"RATE_LIMITED", "FAILED", "LOST", "COMPLETED", "CANCELLED"}
)
_LIVE_ATTEMPT_STATUSES = frozenset(
    {"CLAIMED", "RUNNING", "CHECKPOINTED", "CANCEL_REQUESTED"}
)


def validate_acceptance_document(
    payload: Mapping[str, Any], *, expected_sha: str
) -> None:
    if not isinstance(payload, Mapping) or set(payload) != _ACCEPTANCE_FIELDS:
        raise ArmAdmissionError("acceptance_fields_mismatch")
    if payload.get("schema_version") != "mastermind.executive_host_acceptance/v1":
        raise ArmAdmissionError("acceptance_schema_mismatch")
    if payload.get("passed") is not True:
        raise ArmAdmissionError("acceptance_not_passed")
    if payload.get("exact_origin_master_sha") != expected_sha:
        raise ArmAdmissionError("acceptance_sha_mismatch")
    expected_release = os.fspath(SYSTEM_ROOT / "releases" / expected_sha)
    if payload.get("release_root") != expected_release:
        raise ArmAdmissionError("acceptance_sha_mismatch")
    if any(payload.get(field) != "PASS" for field in _ACCEPTANCE_PASS_FIELDS):
        raise ArmAdmissionError("acceptance_predicate_failed")
    if payload.get("financial_scheduler_activation") != "NOT_REQUESTED_OR_TOUCHED":
        raise ArmAdmissionError("acceptance_predicate_failed")
    if (
        type(payload.get("control_uid")) is not int
        or type(payload.get("worker_uid")) is not int
        or payload["control_uid"] == payload["worker_uid"]
    ):
        raise ArmAdmissionError("acceptance_predicate_failed")
    for field in ("success_job_id", "interrupted_requeued_job_id", "observed_at"):
        if not isinstance(payload.get(field), str) or not payload[field]:
            raise ArmAdmissionError("acceptance_predicate_failed")


def validate_gate_b_document(
    payload: Mapping[str, Any], *, expected_sha: str
) -> None:
    try:
        git_handoff_preflight.validate_receipt(payload)
    except (git_handoff_preflight.PreflightError, TypeError, ValueError) as exc:
        raise ArmAdmissionError("gate_b_invalid") from exc
    if payload.get("passed") is not True:
        raise ArmAdmissionError("gate_b_invalid")
    if payload.get("release_sha") != expected_sha:
        raise ArmAdmissionError("gate_b_sha_mismatch")


def validate_runtime_attempt_statuses(statuses: Sequence[str]) -> None:
    for status_value in statuses:
        if status_value in _LIVE_ATTEMPT_STATUSES:
            raise ArmAdmissionError("runtime_live_attempt")
        if status_value not in _TERMINAL_ATTEMPT_STATUSES:
            raise ArmAdmissionError("runtime_attempt_status_unknown")


def _request_expiry(request: ArmRequest, *, now: datetime) -> datetime:
    if request.expected_credential_kind not in {
        "device-auth",
        "personal-access-token",
        "service-account",
    }:
        raise ArmAdmissionError("credential_kind_invalid")
    if request.workspace_binding_class != "company-workspace-admin-attested":
        raise ArmAdmissionError("workspace_binding_invalid")
    if (
        not isinstance(request.credential_expires_at, str)
        or _TIMESTAMP_RE.fullmatch(request.credential_expires_at) is None
    ):
        raise ArmAdmissionError("credential_expiry_invalid")
    try:
        expiry = datetime.strptime(
            request.credential_expires_at, "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=UTC)
    except ValueError as exc:
        raise ArmAdmissionError("credential_expiry_invalid") from exc
    if expiry <= now.astimezone(UTC):
        raise ArmAdmissionError("credential_expired")
    return expiry


def evaluate_arm_admission(
    host: ArmAdmissionHost, request: ArmRequest, *, now: datetime
) -> ArmAdmission:
    """Evaluate all arm gates in fixed order without mutating host state."""

    _request_expiry(request, now=now)
    host.require_exact_install(request.expected_sha)
    acceptance_digest = host.validate_acceptance(request.expected_sha)
    gate_b_digest = host.validate_gate_b(
        request.gate_b_receipt, request.expected_sha
    )
    readiness = host.validate_provider_readiness(request, now=now)
    configs = host.load_unarmed_configs(request.expected_sha)
    host.require_runtime_quiescent(configs)
    host.require_services_stopped()
    host.require_service_uids_quiescent()
    host.require_transaction_absent()
    return ArmAdmission(
        expected_sha=request.expected_sha,
        acceptance_receipt_sha256=acceptance_digest,
        gate_b_receipt_sha256=gate_b_digest,
        readiness=readiness,
        configs=configs,
        predicates={
            "acceptance_passed": True,
            "configs_validated": True,
            "gate_b_passed": True,
            "provider_readiness_passed": True,
            "runtime_quiescent": True,
            "service_uids_quiescent": True,
        },
    )


def status_document(snapshot: StatusSnapshot, *, now: datetime) -> dict[str, Any]:
    evidence = snapshot.evidence
    return {
        "schema_version": STATUS_SCHEMA_VERSION,
        "status": classify_status(evidence, now=now),
        "expected_sha": snapshot.expected_sha,
        "installed_sha": snapshot.installed_sha,
        "config": {
            "control_armed": evidence.control_armed,
            "worker_armed": evidence.worker_armed,
            "control_sha256": snapshot.control_config_sha256,
            "worker_sha256": snapshot.worker_config_sha256,
        },
        "receipt_state": evidence.receipt_state,
        "readiness_expires_at": _iso(evidence.readiness_expires_at),
        "service_state": evidence.service_state,
        "refusal_code": snapshot.refusal_code,
    }


def _fallback_snapshot(expected_sha: str, refusal_code: str) -> StatusSnapshot:
    return StatusSnapshot(
        expected_sha=expected_sha,
        installed_sha=None,
        control_config_sha256=None,
        worker_config_sha256=None,
        evidence=StatusEvidence(
            transaction_present=False,
            control_armed=False,
            worker_armed=False,
            receipt_state=None,
            receipt_matches=False,
            config_drift=False,
            identity_reconciled=False,
            service_state="AMBIGUOUS",
            readiness_expires_at=None,
        ),
        refusal_code=refusal_code,
    )


def _has_acl(path: Path) -> bool:
    completed = subprocess.run(
        ["/usr/bin/stat", "-f", "%Sp", os.fspath(path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=5,
    )
    return completed.returncode != 0 or completed.stdout.strip().endswith(b"+")


def _read_root_file(
    path: Path,
    *,
    modes: frozenset[int],
    uid: int = 0,
    gid: int | None = None,
) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        descriptor = os.open(path, flags)
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != uid
            or (gid is not None and info.st_gid != gid)
            or stat.S_IMODE(info.st_mode) not in modes
            or info.st_nlink != 1
            or _has_acl(path)
        ):
            raise HostControlError("config_identity_unavailable")
        raw = os.read(descriptor, _MAX_JSON_BYTES + 1)
        if len(raw) > _MAX_JSON_BYTES or os.read(descriptor, 1):
            raise HostControlError("config_identity_unavailable")
        return raw, info
    except HostControlError:
        raise
    except OSError as exc:
        raise HostControlError("config_identity_unavailable") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _root_json(
    path: Path,
    *,
    modes: frozenset[int],
    uid: int = 0,
    gid: int | None = None,
) -> tuple[dict[str, Any], bytes]:
    raw, _info = _read_root_file(path, modes=modes, uid=uid, gid=gid)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HostControlError("config_schema_drift") from exc
    if not isinstance(value, dict):
        raise HostControlError("config_schema_drift")
    return value, raw


def _receipt_metadata(path: Path) -> ReceiptMetadata:
    try:
        info = path.lstat()
    except OSError as exc:
        raise HostControlError("receipt_invalid") from exc
    return ReceiptMetadata(
        uid=int(info.st_uid),
        gid=int(info.st_gid),
        mode=stat.S_IMODE(info.st_mode),
        nlink=int(info.st_nlink),
        is_regular=stat.S_ISREG(info.st_mode),
        is_symlink=stat.S_ISLNK(info.st_mode),
        has_acl=_has_acl(path),
    )


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or _TIMESTAMP_RE.fullmatch(value) is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


class ProductionStatusHost:
    """Read-only collector for the one fixed installed Executive host."""

    def _require_host(self) -> None:
        if sys.platform != "darwin":
            raise HostControlError("platform_unsupported")
        if os.geteuid() != 0:
            raise HostControlError("privilege_required")

    def _release_identity(self, expected_sha: str) -> str:
        root = SYSTEM_ROOT / "releases" / expected_sha
        try:
            manifest_value, _raw = _root_json(
                root / release_manifest.MANIFEST_NAME,
                modes=frozenset({0o444}),
                gid=0,
            )
            if manifest_value.get("commit_sha") != expected_sha:
                raise HostControlError("installed_identity_mismatch")
            tree_sha = manifest_value.get("tree_sha")
            if not isinstance(tree_sha, str) or _SHA_RE.fullmatch(tree_sha) is None:
                raise HostControlError("installed_identity_mismatch")
            release_manifest.verify(root, expected_sha, tree_sha)
            for path, script in (
                (CONTROL_PLIST, "scripts/executive_os_phase1c_control_wrapper.py"),
                (WORKER_PLIST, "scripts/executive_os_phase1c_worker.py"),
            ):
                raw, _info = _read_root_file(
                    path, modes=frozenset({0o644}), gid=0
                )
                value = plistlib.loads(raw)
                release_text = os.fspath(root)
                arguments = value.get("ProgramArguments")
                if (
                    value.get("WorkingDirectory") != release_text
                    or not isinstance(arguments, list)
                    or not all(isinstance(item, str) for item in arguments)
                    or os.fspath(PINNED_PYTHON) != arguments[0]
                    or os.fspath(root / script) not in arguments
                ):
                    raise HostControlError("installed_identity_mismatch")
        except HostControlError:
            raise
        except (OSError, ValueError, plistlib.InvalidFileException, release_manifest.ReleaseManifestError) as exc:
            raise HostControlError("installed_identity_unavailable") from exc
        return expected_sha

    @staticmethod
    def _transaction_present() -> bool:
        try:
            info = AUTONOMY_TRANSACTION.lstat()
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise HostControlError("transaction_identity_unsafe") from exc
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != 0
            or info.st_gid != 0
            or stat.S_IMODE(info.st_mode) != 0o700
            or _has_acl(AUTONOMY_TRANSACTION)
        ):
            raise HostControlError("transaction_identity_unsafe")
        return True

    @staticmethod
    def _configs() -> tuple[dict[str, Any], dict[str, Any], str, str]:
        control_gid = grp.getgrnam(CONTROL_GROUP).gr_gid
        worker_gid = grp.getgrnam(WORKER_GROUP).gr_gid
        control, control_raw = _root_json(
            CONTROL_CONFIG, modes=frozenset({0o440}), gid=control_gid
        )
        worker, worker_raw = _root_json(
            WORKER_CONFIG, modes=frozenset({0o440}), gid=worker_gid
        )
        control_arm = control.get("coo_autonomy_armed")
        operator_arm = control.get("coo_operator_harness_armed")
        worker_arm = worker.get("operator_harness_armed")
        if (
            not isinstance(control_arm, bool)
            or not isinstance(operator_arm, bool)
            or not isinstance(worker_arm, bool)
            or operator_arm is not worker_arm
        ):
            raise HostControlError("config_schema_drift")
        return (
            control,
            worker,
            hashlib.sha256(control_raw).hexdigest(),
            hashlib.sha256(worker_raw).hexdigest(),
        )

    @staticmethod
    def _loaded(label: str) -> bool:
        completed = subprocess.run(
            ["/bin/launchctl", "print", f"system/{label}"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
        return completed.returncode == 0

    @staticmethod
    def _control_ready(expected_sha: str) -> bool:
        release = SYSTEM_ROOT / "releases" / expected_sha
        control_home = RUNTIME_ROOT / "control" / "home"
        command = [
            "/usr/bin/sudo",
            "-u",
            CONTROL_USER,
            "/usr/bin/env",
            "-i",
            f"HOME={control_home}",
            "PATH=/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG=C.UTF-8",
            "LC_ALL=C.UTF-8",
            os.fspath(PINNED_PYTHON),
            "-I",
            "-S",
            "-B",
            os.fspath(release / "scripts/executive_os_phase1c.py"),
            "--socket",
            os.fspath(CONTROL_SOCKET),
            "status",
        ]
        completed = subprocess.run(
            command,
            cwd=release,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
        if completed.returncode != 0 or len(completed.stdout) > _MAX_JSON_BYTES:
            return False
        try:
            value = json.loads(completed.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        return (
            isinstance(value, dict)
            and value.get("ok") is True
            and isinstance(value.get("result"), dict)
            and value["result"].get("service_state") == "READY"
        )

    def _service_state(self, expected_sha: str) -> tuple[str, bool]:
        control_loaded = self._loaded(CONTROL_LABEL)
        worker_loaded = self._loaded(WORKER_LABEL)
        if not control_loaded and not worker_loaded:
            return "STOPPED", True
        if control_loaded is not worker_loaded:
            return "AMBIGUOUS", False
        if self._control_ready(expected_sha):
            return "READY", True
        return "DEGRADED", True

    @staticmethod
    def _receipt(
        *,
        expected_sha: str,
        control_digest: str,
        worker_digest: str,
        now: datetime,
    ) -> tuple[str | None, bool, datetime | None, str | None]:
        if not AUTONOMY_RECEIPT.exists() and not AUTONOMY_RECEIPT.is_symlink():
            return None, False, None, None
        try:
            payload, _raw = _root_json(
                AUTONOMY_RECEIPT, modes=frozenset({0o444}), gid=0
            )
            raw_state = payload.get("state")
            state = raw_state if raw_state in {"ARMED", "DISARMED"} else None
            readiness_deadline = _parse_timestamp(payload.get("readiness_expires_at"))
            if state == "ARMED":
                readiness_raw, _readiness_info = _read_root_file(
                    PROVIDER_READINESS_RECEIPT,
                    modes=frozenset({0o400}),
                    gid=0,
                )
                readiness_digest = hashlib.sha256(readiness_raw).hexdigest()
            else:
                readiness_digest = str(
                    payload.get("provider_readiness_receipt_sha256", "")
                )
            binding = validate_receipt_document(
                payload,
                metadata=_receipt_metadata(AUTONOMY_RECEIPT),
                expected=AutonomyExpectation(
                    release_sha=expected_sha,
                    control_config_sha256=control_digest,
                    worker_config_sha256=worker_digest,
                    provider_readiness_receipt_sha256=readiness_digest,
                    capability_policy_digest=CAPABILITY_POLICY_DIGEST,
                    execution_profile_digest=EXECUTION_PROFILE_DIGEST,
                    native_helper_grant_digest=NATIVE_HELPER_GRANT_DIGEST,
                    security_config_digest=SECURITY_CONFIG_DIGEST,
                ),
                now=now,
                require_current=False,
            )
            return binding.state, True, binding.readiness_expires_at, None
        except (AutonomyRefusal, HostControlError):
            return state if "state" in locals() else None, False, readiness_deadline if "readiness_deadline" in locals() else None, "receipt_invalid"

    def collect_status(self, expected_sha: str, *, now: datetime) -> StatusSnapshot:
        self._require_host()
        installed_sha = self._release_identity(expected_sha)
        transaction_present = self._transaction_present()
        control, worker, control_digest, worker_digest = self._configs()
        control_arm = bool(control["coo_autonomy_armed"])
        worker_arm = bool(worker["operator_harness_armed"])
        config_drift = (
            bool(control["coo_operator_harness_armed"]) is not worker_arm
            or control_arm is not worker_arm
        )
        receipt_state, receipt_matches, deadline, refusal = self._receipt(
            expected_sha=expected_sha,
            control_digest=control_digest,
            worker_digest=worker_digest,
            now=now,
        )
        service_state, reconciled = self._service_state(expected_sha)
        return StatusSnapshot(
            expected_sha=expected_sha,
            installed_sha=installed_sha,
            control_config_sha256=control_digest,
            worker_config_sha256=worker_digest,
            evidence=StatusEvidence(
                transaction_present=transaction_present,
                control_armed=control_arm,
                worker_armed=worker_arm,
                receipt_state=receipt_state,
                receipt_matches=receipt_matches,
                config_drift=config_drift,
                identity_reconciled=reconciled,
                service_state=service_state,
                readiness_expires_at=deadline,
            ),
            refusal_code=refusal,
        )


class ProductionArmHost(ProductionStatusHost):
    """Read-only production admission for the later arm transaction."""

    def require_exact_install(self, expected_sha: str) -> str:
        try:
            self._require_host()
            return self._release_identity(expected_sha)
        except HostControlError as exc:
            raise ArmAdmissionError("install_gate_failed") from exc

    def validate_acceptance(self, expected_sha: str) -> str:
        try:
            control_identity = pwd.getpwnam(CONTROL_USER)
            control_group = grp.getgrnam(CONTROL_GROUP)
            receipt_root = (
                RUNTIME_ROOT / "control" / "acceptance" / expected_sha
            )
            root_info = receipt_root.lstat()
            if (
                stat.S_ISLNK(root_info.st_mode)
                or not stat.S_ISDIR(root_info.st_mode)
                or root_info.st_uid != control_identity.pw_uid
                or root_info.st_gid != control_group.gr_gid
                or stat.S_IMODE(root_info.st_mode) != 0o700
                or _has_acl(receipt_root)
            ):
                raise ArmAdmissionError("acceptance_receipt_invalid")
            summary, raw = _root_json(
                receipt_root / "acceptance-summary.json",
                modes=frozenset({0o400}),
                uid=control_identity.pw_uid,
                gid=control_group.gr_gid,
            )
            validate_acceptance_document(summary, expected_sha=expected_sha)
            return hashlib.sha256(raw).hexdigest()
        except ArmAdmissionError:
            raise
        except (HostControlError, KeyError, OSError) as exc:
            raise ArmAdmissionError("acceptance_receipt_invalid") from exc

    def validate_gate_b(self, path: Path, expected_sha: str) -> str:
        try:
            receipt, raw = _root_json(
                path,
                modes=frozenset({0o600}),
                uid=0,
                gid=0,
            )
            validate_gate_b_document(receipt, expected_sha=expected_sha)
            return hashlib.sha256(raw).hexdigest()
        except ArmAdmissionError:
            raise
        except (HostControlError, OSError) as exc:
            raise ArmAdmissionError("gate_b_receipt_invalid") from exc

    def validate_provider_readiness(
        self, request: ArmRequest, *, now: datetime
    ) -> ReadinessEvidence:
        try:
            raw, _info = _read_root_file(
                PROVIDER_READINESS_RECEIPT,
                modes=frozenset({0o400}),
                uid=0,
                gid=0,
            )
            receipt = provider_readiness.validate_receipt_file(
                PROVIDER_READINESS_RECEIPT,
                auth_path=provider_readiness.AUTH_PATH,
                binary_path=provider_readiness.CODEX_BINARY,
                expected_kind=request.expected_credential_kind,
                workspace_binding_class=request.workspace_binding_class,
                credential_expires_at=request.credential_expires_at,
            )
            if receipt.get("passed") is not True:
                raise ArmAdmissionError("provider_readiness_invalid")
            observed = receipt.get("observed_at")
            credential_expiry = receipt.get("credential_expires_at")
            readiness_expiry = receipt.get("readiness_expires_at")
            if (
                not isinstance(observed, str)
                or not isinstance(credential_expiry, str)
                or not isinstance(readiness_expiry, str)
            ):
                raise ArmAdmissionError("provider_readiness_invalid")
            deadline = _parse_timestamp(readiness_expiry)
            if (
                deadline is None
                or deadline < now.astimezone(UTC) + provider_readiness.MIN_ACCEPTANCE_MARGIN
            ):
                raise ArmAdmissionError("provider_readiness_invalid")
            return ReadinessEvidence(
                receipt_sha256=hashlib.sha256(raw).hexdigest(),
                observed_at=observed,
                credential_expires_at=credential_expiry,
                readiness_expires_at=readiness_expiry,
            )
        except ArmAdmissionError:
            raise
        except (HostControlError, provider_readiness.ReadinessError, OSError) as exc:
            raise ArmAdmissionError("provider_readiness_invalid") from exc

    def load_unarmed_configs(self, expected_sha: str) -> ConfigEvidence:
        try:
            control, worker, control_digest, worker_digest = self._configs()
        except (HostControlError, KeyError, OSError) as exc:
            raise ArmAdmissionError("configs_gate_failed") from exc
        if (
            control.get("proof_base_sha") != expected_sha
            or control.get("coo_autonomy_armed") is not False
            or control.get("coo_operator_harness_armed") is not False
            or worker.get("operator_harness_armed") is not False
        ):
            raise ArmAdmissionError("configs_not_unarmed")
        return ConfigEvidence(
            control_sha256=control_digest,
            worker_sha256=worker_digest,
            control=control,
            worker=worker,
        )

    def require_runtime_quiescent(self, config: ConfigEvidence) -> None:
        try:
            from control_plane.executive_runtime import Runtime

            root_value = config.control.get("runtime_root")
            if not isinstance(root_value, str) or not Path(root_value).is_absolute():
                raise ArmAdmissionError("runtime_integrity_failed")
            runtime = Runtime.at(Path(root_value), create=False)
            with runtime.store.read() as connection:
                quick_check = [
                    str(row[0]) for row in connection.execute("PRAGMA quick_check")
                ]
                foreign_keys = list(connection.execute("PRAGMA foreign_key_check"))
                journal_row = connection.execute("PRAGMA journal_mode").fetchone()
                statuses = [
                    str(row[0])
                    for row in connection.execute(
                        "SELECT status FROM attempts ORDER BY created_at_ms,attempt_id"
                    )
                ]
            if (
                quick_check != ["ok"]
                or foreign_keys
                or journal_row is None
                or str(journal_row[0]).lower() != "wal"
            ):
                raise ArmAdmissionError("runtime_integrity_failed")
            validate_runtime_attempt_statuses(statuses)
        except ArmAdmissionError:
            raise
        except Exception as exc:
            raise ArmAdmissionError("runtime_integrity_failed") from exc

    def require_services_stopped(self) -> None:
        try:
            loaded = (self._loaded(CONTROL_LABEL), self._loaded(WORKER_LABEL))
        except (OSError, subprocess.SubprocessError) as exc:
            raise ArmAdmissionError("services_gate_failed") from exc
        if any(loaded):
            raise ArmAdmissionError("services_not_stopped")

    def require_service_uids_quiescent(self) -> None:
        try:
            identities = (
                pwd.getpwnam(CONTROL_USER).pw_uid,
                pwd.getpwnam("_mastermind_worker").pw_uid,
            )
        except KeyError as exc:
            raise ArmAdmissionError("service_uid_process_unknown") from exc
        for uid in identities:
            try:
                completed = subprocess.run(
                    ["/usr/bin/pgrep", "-U", str(uid)],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=5,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                raise ArmAdmissionError("service_uid_process_unknown") from exc
            if completed.returncode == 0 and completed.stdout.strip():
                raise ArmAdmissionError("service_uid_process_live")
            if completed.returncode not in {0, 1}:
                raise ArmAdmissionError("service_uid_process_unknown")

    def require_transaction_absent(self) -> None:
        if AUTONOMY_TRANSACTION.exists() or AUTONOMY_TRANSACTION.is_symlink():
            raise ArmAdmissionError("transaction_incomplete")


def main(
    argv: Sequence[str] | None = None,
    *,
    host: StatusHost | None = None,
    now: Callable[[], datetime] | None = None,
) -> int:
    args = _parser().parse_args(argv)
    current = (datetime.now(UTC) if now is None else now()).astimezone(UTC)
    if args.command != "status":
        document = status_document(
            _fallback_snapshot(args.expected_sha, "command_not_implemented"),
            now=current,
        )
        print(json.dumps(document, sort_keys=True, separators=(",", ":")))
        return 2
    collector = ProductionStatusHost() if host is None else host
    try:
        snapshot = collector.collect_status(args.expected_sha, now=current)
    except HostControlError as exc:
        snapshot = _fallback_snapshot(args.expected_sha, exc.code)
    except Exception:
        snapshot = _fallback_snapshot(args.expected_sha, "status_unavailable")
    document = status_document(snapshot, now=current)
    print(json.dumps(document, sort_keys=True, separators=(",", ":")))
    return 0 if document["status"] in {UNARMED, ARMED_READY} else 2


if __name__ == "__main__":
    raise SystemExit(main())
