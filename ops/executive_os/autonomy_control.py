"""Root-only status/arm/disarm surface for Executive OS autonomy.

The status path is implemented first and is strictly read-only.  Arm and
disarm share this fixed parser but do not acquire mutation behavior until their
transaction gates are implemented and tested in the following plan tasks.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import grp
import hashlib
import json
import os
import plistlib
import pwd
import re
import secrets
import stat
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

_ROOT = Path(__file__).resolve().parents[2]
if os.fspath(_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_ROOT))

from control_plane.fs_security import FilesystemSecurityError, has_macos_acl

from control_plane.executive_autonomy import (
    ARMED_READY,
    CAPABILITY_POLICY_DIGEST,
    EXECUTION_PROFILE_DIGEST,
    NATIVE_HELPER_GRANT_DIGEST,
    RECEIPT_SCHEMA_VERSION,
    SECURITY_CONFIG_DIGEST,
    TOOL_VERSION,
    UNARMED,
    WORKSPACE_BINDING_CLASS,
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
OPERATION_SCHEMA_VERSION = "mastermind.executive_autonomy_operation/v1"
SYSTEM_ROOT = Path("/Library/Application Support/MastermindExecutive")
CONFIG_ROOT = SYSTEM_ROOT / "config"
RUNTIME_ROOT = Path("/var/db/mastermind-executive")
CONTROL_CONFIG = CONFIG_ROOT / "control.json"
WORKER_CONFIG = CONFIG_ROOT / "worker-codex.json"
AUTONOMY_RECEIPT = CONFIG_ROOT / "autonomy-state-v1.json"
AUTONOMY_TRANSACTION = CONFIG_ROOT / "autonomy-transaction.lock"
CEO_SUBMIT_RECEIPT = CONFIG_ROOT / "ceo-submit-state-v1.json"
CEO_SUBMIT_RECEIPT_SCHEMA = "mastermind.executive_ceo_submit_receipt/v1"
CEO_SUBMIT_OPERATIONS = frozenset({"CEO_SUBMIT_ARM", "CEO_SUBMIT_DISARM"})
CEO_INGRESS_APP_PEER_UID = 458
CEO_INGRESS_PEER_UID = 452
EXECUTIVE_APP_USER = "_mastermind_executive_mcp"
CEO_INGRESS_LAUNCHD_SOCKET_NAME = "CeoIngress"
CEO_INGRESS_SOCKET_PATH = "/var/run/mastermind-executive/ceo-ingress.sock"
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
        "changed_arm_evidence",
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
_TRANSACTION_SCHEMA = "mastermind.executive_autonomy_transaction/v1"
_TRANSACTION_OPERATIONS = frozenset({"ARM", "DISARM"}) | CEO_SUBMIT_OPERATIONS
_CEO_SUBMIT_ADMISSION_CODES = frozenset(
    {
        "release_identity_mismatch",
        "app_peer_invalid",
        "app_binding_invalid",
        "app_acl_invalid",
        "app_topology_invalid",
        "app_binding_absent",
        "ceo_submit_already_armed",
        "ceo_ingress_app_armed",
        "ceo_ingress_separation_invalid",
        "coo_autonomy_armed",
        "coo_operator_harness_armed",
        "worker_operator_harness_armed",
        "ceo_submit_transaction_incomplete",
        "ceo_submit_config_schema_drift",
    }
)
# The CEO-submit receipt binds a CLOSED semantic projection.  ``..._CONTROL_FIELDS``
# are the authority-bearing keys read from the postimage ``control.json``;
# ``..._PROJECTION_FIELDS`` adds the host-observed identity/binding facts.  Nothing
# outside this set is ever digest-bound, so an unrelated later COO field cannot
# invalidate the receipt, and the receipt never carries the whole control document.
_CEO_SUBMIT_CONTROL_FIELDS = frozenset(
    {
        "ceo_submit_armed",
        "ceo_ingress_app_peer_uid",
        "ceo_ingress_app_armed",
        "ceo_ingress_peer_uid",
        "ceo_ingress_socket_path",
        "ceo_ingress_launchd_socket_name",
        "ceo_ingress_app_macro_root",
        "coo_autonomy_armed",
        "coo_operator_harness_armed",
    }
)
_CEO_SUBMIT_PROJECTION_FIELDS = _CEO_SUBMIT_CONTROL_FIELDS | frozenset(
    {
        "release_sha",
        "installed_sha",
        "app_peer_user",
        "app_binding_valid",
        "app_acl_valid",
        "app_topology_valid",
        "worker_operator_harness_armed",
        "worker_config_sha256",
        "transaction_id",
    }
)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_file(
    path: Path,
    payload: bytes,
    *,
    mode: int,
    uid: int,
    gid: int,
    replace: bool,
) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = -1
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            mode,
        )
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short autonomy transaction write")
            view = view[written:]
        os.fchown(descriptor, uid, gid)
        os.fchmod(descriptor, mode)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        if not replace and (path.exists() or path.is_symlink()):
            raise FileExistsError(os.fspath(path))
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary.exists() or temporary.is_symlink():
            temporary.unlink()


def _encoded_json(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


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


class CeoSubmitAdmissionError(RuntimeError):
    def __init__(self, code: str):
        if code not in _CEO_SUBMIT_ADMISSION_CODES:
            raise ValueError("unknown ceo-submit admission refusal")
        self.code = code
        super().__init__(code)


class ArmTransactionError(RuntimeError):
    CODES = frozenset({"arm_rolled_back", "disarm_recovered"})

    def __init__(self, code: str):
        if code not in self.CODES:
            raise ValueError("unknown autonomy transaction refusal")
        self.code = code
        super().__init__(code)


class TransactionEffectUnknown(RuntimeError):
    def __init__(self, code: str = "effect_unknown"):
        if code != "effect_unknown":
            raise ValueError("unknown autonomy effect-unknown code")
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
    control_bytes: bytes = b""
    worker_bytes: bytes = b""


@dataclasses.dataclass(frozen=True)
class ArmAdmission:
    expected_sha: str
    acceptance_receipt_sha256: str
    gate_b_receipt_sha256: str
    readiness: ReadinessEvidence
    configs: ConfigEvidence
    expected_credential_kind: str
    workspace_binding_class: str
    predicates: Mapping[str, bool]


@dataclasses.dataclass(frozen=True)
class CandidateConfigs:
    control: Mapping[str, Any]
    worker: Mapping[str, Any]
    control_bytes: bytes
    worker_bytes: bytes
    control_sha256: str
    worker_sha256: str


@dataclasses.dataclass(frozen=True)
class TransactionContext:
    transaction_id: str
    expected_sha: str
    prior_configs: ConfigEvidence
    candidates: CandidateConfigs
    admission: ArmAdmission | None


@dataclasses.dataclass(frozen=True)
class TransactionResult:
    state: str
    status: str
    transaction_id: str | None
    replayed: bool


@dataclasses.dataclass(frozen=True)
class ExecutiveAppBinding:
    """Host-observed identity of the dedicated Executive App caller."""

    present: bool
    app_peer_uid: int
    app_peer_user: str
    app_armed: bool
    app_macro_root: str
    ingress_peer_uid: int
    ingress_socket_path: str
    launchd_socket_name: str
    binding_valid: bool
    acl_valid: bool
    topology_valid: bool


@dataclasses.dataclass(frozen=True)
class CeoSubmitSeparation:
    """The disarmed-separation facts a CEO-submit arm must observe first."""

    ceo_ingress_app_armed: bool
    ceo_ingress_app_peer_uid: int
    ceo_ingress_peer_uid: int
    coo_autonomy_armed: bool
    coo_operator_harness_armed: bool
    worker_operator_harness_armed: bool


@dataclasses.dataclass(frozen=True)
class CeoSubmitRequest:
    expected_sha: str


@dataclasses.dataclass(frozen=True)
class CeoSubmitAdmission:
    expected_sha: str
    installed_sha: str
    binding: ExecutiveAppBinding
    separation: CeoSubmitSeparation
    configs: ConfigEvidence


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


class TransactionHost(ArmAdmissionHost, Protocol):
    def existing_arm(
        self, request: ArmRequest, *, now: datetime
    ) -> TransactionResult | None: ...

    def existing_disarm(
        self, expected_sha: str, *, now: datetime
    ) -> TransactionResult | None: ...

    def new_transaction_id(self) -> str: ...

    def begin_transaction(self, transaction: TransactionContext) -> None: ...

    def write_candidates(self, transaction: TransactionContext) -> None: ...

    def validate_candidates(self, transaction: TransactionContext) -> None: ...

    def replace_worker_config(self, transaction: TransactionContext) -> None: ...

    def replace_control_config(self, transaction: TransactionContext) -> None: ...

    def write_autonomy_receipt(
        self, transaction: TransactionContext, receipt: Mapping[str, Any]
    ) -> None: ...

    def start_services(self, expected_sha: str) -> None: ...

    def prove_services_ready(self, expected_sha: str) -> None: ...

    def complete_transaction(self, transaction: TransactionContext) -> None: ...

    def stop_services(self, expected_sha: str) -> None: ...

    def rollback_disarmed(
        self, transaction: TransactionContext, receipt: Mapping[str, Any]
    ) -> None: ...

    def begin_disarm(self, expected_sha: str, transaction_id: str) -> ConfigEvidence: ...


class CeoSubmitTransactionHost(Protocol):
    """The CEO-submit operation domain rides the one existing transaction owner.

    Every mutating method here is served by the same ``AUTONOMY_TRANSACTION``
    serialization/atomic-write owner as the COO arm path.  There is deliberately
    no second lock, no controller, no daemon and no JSON editor.
    """

    def effective_uid(self) -> int: ...

    def require_exact_install(self, expected_sha: str) -> str: ...

    def load_ceo_submit_configs(self, expected_sha: str) -> ConfigEvidence: ...

    def executive_app_binding(self) -> ExecutiveAppBinding: ...

    def ceo_submit_separation(
        self, configs: ConfigEvidence
    ) -> CeoSubmitSeparation: ...

    def require_transaction_absent(self) -> None: ...

    def new_transaction_id(self) -> str: ...

    def begin_ceo_submit_transaction(
        self, transaction: TransactionContext, *, operation: str
    ) -> None: ...

    def write_candidates(self, transaction: TransactionContext) -> None: ...

    def validate_candidates(self, transaction: TransactionContext) -> None: ...

    def replace_control_config(self, transaction: TransactionContext) -> None: ...

    def write_ceo_submit_receipt(
        self, transaction: TransactionContext, receipt: Mapping[str, Any]
    ) -> None: ...

    def reconcile_control_service(self, expected_sha: str) -> None: ...

    def prove_control_ready(self, expected_sha: str) -> None: ...

    def complete_transaction(self, transaction: TransactionContext) -> None: ...

    def rollback_ceo_submit(
        self, transaction: TransactionContext, receipt: Mapping[str, Any]
    ) -> None: ...


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


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def require_root_privilege(effective_uid: int) -> None:
    """Root-only gate with the effective uid injected by the caller."""

    if effective_uid != 0:
        raise HostControlError("privilege_required")


def encode_config(value: Mapping[str, Any]) -> bytes:
    try:
        return (
            json.dumps(
                value,
                sort_keys=True,
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ArmTransactionError("arm_rolled_back") from exc


def derive_candidate_configs(
    configs: ConfigEvidence, *, armed: bool
) -> CandidateConfigs:
    control_value = copy.deepcopy(dict(configs.control))
    worker_value = copy.deepcopy(dict(configs.worker))
    if (
        not isinstance(control_value.get("coo_autonomy_armed"), bool)
        or not isinstance(control_value.get("coo_operator_harness_armed"), bool)
        or not isinstance(worker_value.get("operator_harness_armed"), bool)
    ):
        raise ArmTransactionError("arm_rolled_back")
    control_value["coo_autonomy_armed"] = armed
    control_value["coo_operator_harness_armed"] = armed
    worker_value["operator_harness_armed"] = armed
    control_bytes = encode_config(control_value)
    worker_bytes = encode_config(worker_value)
    return CandidateConfigs(
        control=control_value,
        worker=worker_value,
        control_bytes=control_bytes,
        worker_bytes=worker_bytes,
        control_sha256=sha256_bytes(control_bytes),
        worker_sha256=sha256_bytes(worker_bytes),
    )


def _receipt_timestamp(now: datetime) -> str:
    return now.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _ceo_submit_only_flag_differs(
    prior: Mapping[str, Any], candidate: Mapping[str, Any]
) -> bool:
    """True when the postimage differs from the preimage only in the arm flag."""

    if set(prior) != set(candidate):
        return False
    return all(
        key == "ceo_submit_armed" or candidate[key] == prior[key] for key in prior
    )


def derive_ceo_submit_candidate(
    configs: ConfigEvidence, *, armed: bool
) -> CandidateConfigs:
    """Derive the CEO-submit postimage: ``control.json`` only, worker untouched."""

    control_value = copy.deepcopy(dict(configs.control))
    if not isinstance(control_value.get("ceo_submit_armed"), bool):
        raise CeoSubmitAdmissionError("ceo_submit_config_schema_drift")
    control_value["ceo_submit_armed"] = armed
    if not _ceo_submit_only_flag_differs(dict(configs.control), control_value):
        raise CeoSubmitAdmissionError("ceo_submit_config_schema_drift")
    if armed and dict(configs.control) == control_value:
        raise CeoSubmitAdmissionError("ceo_submit_config_schema_drift")
    try:
        control_bytes = encode_config(control_value)
    except ArmTransactionError as exc:
        raise CeoSubmitAdmissionError("ceo_submit_config_schema_drift") from exc
    return CandidateConfigs(
        control=control_value,
        worker=configs.worker,
        worker_bytes=configs.worker_bytes,
        control_bytes=control_bytes,
        control_sha256=sha256_bytes(control_bytes),
        worker_sha256=configs.worker_sha256,
    )


def build_transaction_receipt(
    transaction: TransactionContext, *, state: str, now: datetime
) -> dict[str, Any]:
    if state == "ARMED":
        admission = transaction.admission
        if admission is None:
            raise ArmTransactionError("arm_rolled_back")
        acceptance_digest = admission.acceptance_receipt_sha256
        gate_b_digest = admission.gate_b_receipt_sha256
        readiness_digest = admission.readiness.receipt_sha256
        readiness_observed_at = admission.readiness.observed_at
        credential_expires_at = admission.readiness.credential_expires_at
        readiness_expires_at = admission.readiness.readiness_expires_at
        kind = admission.expected_credential_kind
        binding_class = admission.workspace_binding_class
        predicates = dict(admission.predicates)
    elif state == "DISARMED":
        timestamp = _receipt_timestamp(now)
        acceptance_digest = "0" * 64
        gate_b_digest = "0" * 64
        readiness_digest = "0" * 64
        readiness_observed_at = timestamp
        credential_expires_at = timestamp
        readiness_expires_at = timestamp
        kind = "none"
        binding_class = "none"
        predicates = {
            "acceptance_passed": False,
            "configs_validated": True,
            "gate_b_passed": False,
            "provider_readiness_passed": False,
            "runtime_quiescent": False,
            "service_uids_quiescent": True,
        }
    else:
        raise ArmTransactionError("arm_rolled_back")
    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "state": state,
        "release_sha": transaction.expected_sha,
        "acceptance_receipt_sha256": acceptance_digest,
        "gate_b_receipt_sha256": gate_b_digest,
        "provider_readiness_receipt_sha256": readiness_digest,
        "readiness_observed_at": readiness_observed_at,
        "credential_expires_at": credential_expires_at,
        "readiness_expires_at": readiness_expires_at,
        "expected_credential_kind": kind,
        "workspace_binding_class": binding_class,
        "prior_control_config_sha256": transaction.prior_configs.control_sha256,
        "prior_worker_config_sha256": transaction.prior_configs.worker_sha256,
        "control_config_sha256": transaction.candidates.control_sha256,
        "worker_config_sha256": transaction.candidates.worker_sha256,
        "capability_policy_digest": CAPABILITY_POLICY_DIGEST,
        "execution_profile_digest": EXECUTION_PROFILE_DIGEST,
        "native_helper_grant_digest": NATIVE_HELPER_GRANT_DIGEST,
        "security_config_digest": SECURITY_CONFIG_DIGEST,
        "transaction_id": transaction.transaction_id,
        "observed_at": _receipt_timestamp(now),
        "tool_version": TOOL_VERSION,
        "predicates": predicates,
    }


def ceo_submit_projection(
    transaction: TransactionContext,
    admission: CeoSubmitAdmission,
    *,
    armed: bool,
) -> dict[str, Any]:
    """The CLOSED authority-bearing projection of the CEO-submit postimage.

    Only the declared field set is bound: the postimage control values that
    carry authority, the host-observed App binding facts, and the transaction
    identity.  The whole control document is never bound, so an unrelated later
    COO field cannot invalidate the receipt.
    """

    control = transaction.candidates.control
    worker = transaction.candidates.worker
    binding = admission.binding
    values: dict[str, Any] = {}
    for field in _CEO_SUBMIT_CONTROL_FIELDS:
        if field not in control:
            raise CeoSubmitAdmissionError("ceo_submit_config_schema_drift")
        values[field] = control[field]
    if values["ceo_submit_armed"] is not armed:
        raise CeoSubmitAdmissionError("ceo_submit_config_schema_drift")
    if (
        values["ceo_ingress_app_peer_uid"] != binding.app_peer_uid
        or values["ceo_ingress_app_armed"] is not binding.app_armed
        or values["ceo_ingress_peer_uid"] != binding.ingress_peer_uid
        or values["ceo_ingress_app_macro_root"] != binding.app_macro_root
        or values["ceo_ingress_socket_path"] != binding.ingress_socket_path
        or values["ceo_ingress_launchd_socket_name"] != binding.launchd_socket_name
    ):
        raise CeoSubmitAdmissionError("app_binding_invalid")
    worker_armed = worker.get("operator_harness_armed")
    if not isinstance(worker_armed, bool):
        raise CeoSubmitAdmissionError("ceo_submit_config_schema_drift")
    values.update(
        {
            "release_sha": transaction.expected_sha,
            "installed_sha": admission.installed_sha,
            "app_peer_user": binding.app_peer_user,
            "app_binding_valid": binding.binding_valid,
            "app_acl_valid": binding.acl_valid,
            "app_topology_valid": binding.topology_valid,
            "worker_operator_harness_armed": worker_armed,
            "worker_config_sha256": transaction.candidates.worker_sha256,
            "transaction_id": transaction.transaction_id,
        }
    )
    if set(values) != _CEO_SUBMIT_PROJECTION_FIELDS:
        raise CeoSubmitAdmissionError("ceo_submit_config_schema_drift")
    return values


def ceo_submit_projection_digest(projection: Mapping[str, Any]) -> str:
    """Digest the closed projection, never the whole control document."""

    return sha256_bytes(_encoded_json(projection))


def build_ceo_submit_receipt(
    transaction: TransactionContext,
    admission: CeoSubmitAdmission,
    *,
    armed: bool,
    now: datetime,
) -> dict[str, Any]:
    projection = ceo_submit_projection(transaction, admission, armed=armed)
    return {
        "schema_version": CEO_SUBMIT_RECEIPT_SCHEMA,
        "state": "CEO_SUBMIT_ARMED" if armed else "CEO_SUBMIT_DISARMED",
        "operation": "CEO_SUBMIT_ARM" if armed else "CEO_SUBMIT_DISARM",
        "projection": dict(projection),
        "projection_digest": ceo_submit_projection_digest(projection),
        "transaction_id": transaction.transaction_id,
        "observed_at": _receipt_timestamp(now),
        "tool_version": TOOL_VERSION,
    }


def ceo_submit_receipt_binds(
    receipt: Mapping[str, Any],
    *,
    control_config: Mapping[str, Any],
    admission_projection: Mapping[str, Any],
) -> bool:
    """Re-derive the closed projection from the current config and re-bind.

    Only the declared field set participates, so a later change to an unrelated
    COO key leaves this True; a change to any authority-bearing field makes it
    False.
    """

    if not isinstance(receipt, Mapping) or not isinstance(admission_projection, Mapping):
        return False
    if receipt.get("schema_version") != CEO_SUBMIT_RECEIPT_SCHEMA:
        return False
    projection = receipt.get("projection")
    if not isinstance(projection, Mapping) or set(projection) != _CEO_SUBMIT_PROJECTION_FIELDS:
        return False
    recomputed = dict(admission_projection)
    for field in _CEO_SUBMIT_CONTROL_FIELDS:
        if field not in control_config:
            return False
        recomputed[field] = control_config[field]
    if set(recomputed) != _CEO_SUBMIT_PROJECTION_FIELDS:
        return False
    try:
        digest = ceo_submit_projection_digest(recomputed)
    except (ArmTransactionError, TypeError, ValueError):
        return False
    return receipt.get("projection_digest") == digest


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
    if request.workspace_binding_class != WORKSPACE_BINDING_CLASS:
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
        expected_credential_kind=request.expected_credential_kind,
        workspace_binding_class=request.workspace_binding_class,
        predicates={
            "acceptance_passed": True,
            "configs_validated": True,
            "gate_b_passed": True,
            "provider_readiness_passed": True,
            "runtime_quiescent": True,
            "service_uids_quiescent": True,
        },
    )


def execute_arm(
    host: TransactionHost, request: ArmRequest, *, now: datetime
) -> TransactionResult:
    existing = host.existing_arm(request, now=now)
    if existing is not None:
        return existing
    admission = evaluate_arm_admission(host, request, now=now)
    transaction = TransactionContext(
        transaction_id=host.new_transaction_id(),
        expected_sha=request.expected_sha,
        prior_configs=admission.configs,
        candidates=derive_candidate_configs(admission.configs, armed=True),
        admission=admission,
    )
    try:
        host.begin_transaction(transaction)
        host.write_candidates(transaction)
        host.validate_candidates(transaction)
        host.replace_worker_config(transaction)
        host.replace_control_config(transaction)
        receipt = build_transaction_receipt(transaction, state="ARMED", now=now)
        host.write_autonomy_receipt(transaction, receipt)
        host.start_services(request.expected_sha)
        host.prove_services_ready(request.expected_sha)
        host.complete_transaction(transaction)
    except ArmAdmissionError:
        # A marker that appeared between the read-only admission check and the
        # atomic mkdir belongs to another root transaction. Never "recover"
        # it through this operation's rollback carrier.
        raise
    except Exception as exc:
        try:
            host.stop_services(request.expected_sha)
            rollback = dataclasses.replace(
                transaction,
                candidates=derive_candidate_configs(
                    transaction.prior_configs, armed=False
                ),
                admission=None,
            )
            host.rollback_disarmed(
                rollback,
                build_transaction_receipt(rollback, state="DISARMED", now=now),
            )
        except Exception as rollback_exc:
            raise TransactionEffectUnknown() from rollback_exc
        raise ArmTransactionError("arm_rolled_back") from exc
    return TransactionResult(
        state="ARMED",
        status="ARMED_READY",
        transaction_id=transaction.transaction_id,
        replayed=False,
    )


def execute_disarm(
    host: TransactionHost, expected_sha: str, *, now: datetime
) -> TransactionResult:
    existing = host.existing_disarm(expected_sha, now=now)
    if existing is not None:
        return existing
    host.require_exact_install(expected_sha)
    transaction_id = host.new_transaction_id()
    host.stop_services(expected_sha)
    try:
        prior_configs = host.begin_disarm(expected_sha, transaction_id)
    except Exception as exc:
        raise TransactionEffectUnknown() from exc
    transaction = TransactionContext(
        transaction_id=transaction_id,
        expected_sha=expected_sha,
        prior_configs=prior_configs,
        candidates=derive_candidate_configs(prior_configs, armed=False),
        admission=None,
    )
    try:
        host.write_candidates(transaction)
        host.validate_candidates(transaction)
        host.replace_worker_config(transaction)
        host.replace_control_config(transaction)
        receipt = build_transaction_receipt(transaction, state="DISARMED", now=now)
        host.write_autonomy_receipt(transaction, receipt)
        host.complete_transaction(transaction)
    except Exception as exc:
        try:
            host.stop_services(expected_sha)
            host.rollback_disarmed(
                transaction,
                build_transaction_receipt(
                    transaction, state="DISARMED", now=now
                ),
            )
        except Exception as rollback_exc:
            raise TransactionEffectUnknown() from rollback_exc
        raise ArmTransactionError("disarm_recovered") from exc
    return TransactionResult(
        state="DISARMED",
        status="UNARMED",
        transaction_id=transaction.transaction_id,
        replayed=False,
    )


def evaluate_ceo_submit_arm_admission(
    host: CeoSubmitTransactionHost, request: CeoSubmitRequest, *, now: datetime
) -> CeoSubmitAdmission:
    """Evaluate every CEO-submit arm gate in fixed order, with no mutation.

    Deliberately absent: provider readiness, Gate B, worker credentials and any
    service/runtime quiescence gate.  R9 arms the CEO-submit sink only from the
    installed release, the dedicated App caller binding and the disarmed
    separation facts.
    """

    require_root_privilege(host.effective_uid())
    if _SHA_RE.fullmatch(request.expected_sha) is None:
        raise CeoSubmitAdmissionError("release_identity_mismatch")
    installed_sha = host.require_exact_install(request.expected_sha)
    if installed_sha != request.expected_sha:
        raise CeoSubmitAdmissionError("release_identity_mismatch")
    binding = host.executive_app_binding()
    if not binding.present:
        raise CeoSubmitAdmissionError("app_binding_absent")
    if (
        binding.app_peer_uid != CEO_INGRESS_APP_PEER_UID
        or binding.app_peer_user != EXECUTIVE_APP_USER
    ):
        raise CeoSubmitAdmissionError("app_peer_invalid")
    if not binding.binding_valid:
        raise CeoSubmitAdmissionError("app_binding_invalid")
    if not binding.acl_valid:
        raise CeoSubmitAdmissionError("app_acl_invalid")
    if not binding.topology_valid:
        raise CeoSubmitAdmissionError("app_topology_invalid")
    configs = host.load_ceo_submit_configs(request.expected_sha)
    armed_flag = dict(configs.control).get("ceo_submit_armed")
    if not isinstance(armed_flag, bool):
        raise CeoSubmitAdmissionError("ceo_submit_config_schema_drift")
    if armed_flag is not False:
        raise CeoSubmitAdmissionError("ceo_submit_already_armed")
    separation = host.ceo_submit_separation(configs)
    if separation.ceo_ingress_app_armed:
        raise CeoSubmitAdmissionError("ceo_ingress_app_armed")
    if (
        separation.ceo_ingress_peer_uid != CEO_INGRESS_PEER_UID
        or separation.ceo_ingress_app_peer_uid != CEO_INGRESS_APP_PEER_UID
        or separation.ceo_ingress_peer_uid == separation.ceo_ingress_app_peer_uid
    ):
        raise CeoSubmitAdmissionError("ceo_ingress_separation_invalid")
    if separation.coo_autonomy_armed:
        raise CeoSubmitAdmissionError("coo_autonomy_armed")
    if separation.coo_operator_harness_armed:
        raise CeoSubmitAdmissionError("coo_operator_harness_armed")
    if separation.worker_operator_harness_armed:
        raise CeoSubmitAdmissionError("worker_operator_harness_armed")
    try:
        host.require_transaction_absent()
    except (HostControlError, ArmAdmissionError) as exc:
        raise CeoSubmitAdmissionError("ceo_submit_transaction_incomplete") from exc
    return CeoSubmitAdmission(
        expected_sha=request.expected_sha,
        installed_sha=installed_sha,
        binding=binding,
        separation=separation,
        configs=configs,
    )


def execute_ceo_submit_arm(
    host: CeoSubmitTransactionHost, request: CeoSubmitRequest, *, now: datetime
) -> TransactionResult:
    """Arm exactly the CEO-submit sink inside the one serialized transaction."""

    admission = evaluate_ceo_submit_arm_admission(host, request, now=now)
    transaction = TransactionContext(
        transaction_id=host.new_transaction_id(),
        expected_sha=request.expected_sha,
        prior_configs=admission.configs,
        candidates=derive_ceo_submit_candidate(admission.configs, armed=True),
        admission=None,
    )
    try:
        host.begin_ceo_submit_transaction(transaction, operation="CEO_SUBMIT_ARM")
    except CeoSubmitAdmissionError:
        # A marker that appeared between the read-only admission check and the
        # atomic mkdir belongs to another root transaction. Never "recover" it
        # through this operation's rollback carrier.
        raise
    try:
        host.write_candidates(transaction)
        host.validate_candidates(transaction)
        host.replace_control_config(transaction)
        receipt = build_ceo_submit_receipt(transaction, admission, armed=True, now=now)
        host.write_ceo_submit_receipt(transaction, receipt)
        host.reconcile_control_service(request.expected_sha)
        host.prove_control_ready(request.expected_sha)
        host.complete_transaction(transaction)
    except Exception as exc:
        try:
            rollback = dataclasses.replace(
                transaction,
                candidates=derive_ceo_submit_candidate(
                    transaction.prior_configs, armed=False
                ),
            )
            host.rollback_ceo_submit(
                rollback,
                build_ceo_submit_receipt(rollback, admission, armed=False, now=now),
            )
        except Exception as rollback_exc:
            raise TransactionEffectUnknown() from rollback_exc
        raise ArmTransactionError("arm_rolled_back") from exc
    return TransactionResult(
        state="CEO_SUBMIT_ARMED",
        status="CEO_SUBMIT_ARMED",
        transaction_id=transaction.transaction_id,
        replayed=False,
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


def operation_document(
    *,
    code: str,
    state: str,
    status: str,
    transaction_id: str | None,
    replayed: bool = False,
) -> dict[str, Any]:
    return {
        "schema_version": OPERATION_SCHEMA_VERSION,
        "code": code,
        "state": state,
        "status": status,
        "transaction_id": transaction_id,
        "replayed": replayed,
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
    try:
        return has_macos_acl(path)
    except FilesystemSecurityError:
        return True


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
    def _configs() -> tuple[
        dict[str, Any], dict[str, Any], str, str, bytes, bytes
    ]:
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
        ):
            raise HostControlError("config_schema_drift")
        return (
            control,
            worker,
            hashlib.sha256(control_raw).hexdigest(),
            hashlib.sha256(worker_raw).hexdigest(),
            control_raw,
            worker_raw,
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
        state: str | None = None
        readiness_deadline: datetime | None = None
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
            return state, False, readiness_deadline, "receipt_invalid"

    def collect_status(self, expected_sha: str, *, now: datetime) -> StatusSnapshot:
        self._require_host()
        installed_sha = self._release_identity(expected_sha)
        transaction_present = self._transaction_present()
        (
            control,
            worker,
            control_digest,
            worker_digest,
            _control_raw,
            _worker_raw,
        ) = self._configs()
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
        config_drift = config_drift or refusal is not None
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

    def __init__(self) -> None:
        self._admission_sha: str | None = None

    def require_exact_install(self, expected_sha: str) -> str:
        try:
            self._require_host()
            installed = self._release_identity(expected_sha)
            self._admission_sha = installed
            return installed
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
            (
                control,
                worker,
                control_digest,
                worker_digest,
                control_raw,
                worker_raw,
            ) = self._configs()
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
            control_bytes=control_raw,
            worker_bytes=worker_raw,
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

    def _stop_services_for_admission(self) -> None:
        if self._admission_sha is None:
            raise ArmAdmissionError("services_gate_failed")
        release = SYSTEM_ROOT / "releases" / self._admission_sha
        try:
            completed = subprocess.run(
                [
                    "/bin/bash",
                    os.fspath(release / "ops/executive_os/service-control.sh"),
                    "stop",
                ],
                cwd=release,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=45,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ArmAdmissionError("services_gate_failed") from exc
        if completed.returncode != 0:
            raise ArmAdmissionError("services_gate_failed")

    def require_services_stopped(self) -> None:
        try:
            loaded = (self._loaded(CONTROL_LABEL), self._loaded(WORKER_LABEL))
        except (OSError, subprocess.SubprocessError) as exc:
            raise ArmAdmissionError("services_gate_failed") from exc
        if any(loaded):
            self._stop_services_for_admission()
            loaded = (self._loaded(CONTROL_LABEL), self._loaded(WORKER_LABEL))
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


class ProductionTransactionHost(ProductionArmHost):
    """One crash-recoverable transaction over the two installed configs."""

    def __init__(self) -> None:
        super().__init__()
        self._active_transaction: TransactionContext | None = None

    @staticmethod
    def _candidate_paths(transaction_id: str) -> tuple[Path, Path]:
        if re.fullmatch(r"autonomy-[0-9a-f]{12}", transaction_id) is None:
            raise TransactionEffectUnknown()
        suffix = transaction_id.removeprefix("autonomy-")
        return (
            CONFIG_ROOT / f".autonomy-control-{suffix}.candidate.json",
            CONFIG_ROOT / f".autonomy-worker-{suffix}.candidate.json",
        )

    @staticmethod
    def _manifest_path() -> Path:
        return AUTONOMY_TRANSACTION / "transaction.json"

    @staticmethod
    def _archive_paths() -> tuple[Path, Path]:
        return (
            AUTONOMY_TRANSACTION / "prior-control.json",
            AUTONOMY_TRANSACTION / "prior-worker.json",
        )

    @staticmethod
    def _config_root_safe() -> None:
        try:
            info = CONFIG_ROOT.lstat()
        except OSError as exc:
            raise TransactionEffectUnknown() from exc
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != 0
            or info.st_gid != 0
            or stat.S_IMODE(info.st_mode) != 0o755
            or _has_acl(CONFIG_ROOT)
        ):
            raise TransactionEffectUnknown()

    def _manifest(self) -> dict[str, Any]:
        try:
            value, _raw = _root_json(
                self._manifest_path(),
                modes=frozenset({0o400}),
                uid=0,
                gid=0,
            )
        except HostControlError as exc:
            raise TransactionEffectUnknown() from exc
        required = {
            "schema_version",
            "operation",
            "phase",
            "transaction_id",
            "expected_sha",
            "prior_control_sha256",
            "prior_worker_sha256",
            "target_control_sha256",
            "target_worker_sha256",
        }
        if (
            set(value) != required
            or value.get("schema_version") != _TRANSACTION_SCHEMA
            or value.get("operation") not in _TRANSACTION_OPERATIONS
            or not isinstance(value.get("phase"), str)
            or re.fullmatch(
                r"autonomy-[0-9a-f]{12}", str(value.get("transaction_id", ""))
            )
            is None
            or _SHA_RE.fullmatch(str(value.get("expected_sha", ""))) is None
            or any(
                re.fullmatch(r"[0-9a-f]{64}", str(value.get(field, ""))) is None
                for field in (
                    "prior_control_sha256",
                    "prior_worker_sha256",
                    "target_control_sha256",
                    "target_worker_sha256",
                )
            )
        ):
            raise TransactionEffectUnknown()
        return value

    def _persist_phase(self, transaction: TransactionContext, phase: str, *, operation: str | None = None) -> None:
        if operation is None:
            current = self._manifest()
            operation = str(current["operation"])
        value = {
            "schema_version": _TRANSACTION_SCHEMA,
            "operation": operation,
            "phase": phase,
            "transaction_id": transaction.transaction_id,
            "expected_sha": transaction.expected_sha,
            "prior_control_sha256": transaction.prior_configs.control_sha256,
            "prior_worker_sha256": transaction.prior_configs.worker_sha256,
            "target_control_sha256": transaction.candidates.control_sha256,
            "target_worker_sha256": transaction.candidates.worker_sha256,
        }
        _atomic_file(
            self._manifest_path(),
            _encoded_json(value),
            mode=0o400,
            uid=0,
            gid=0,
            replace=self._manifest_path().exists(),
        )

    def _create_marker(self, transaction: TransactionContext, *, operation: str) -> None:
        self._config_root_safe()
        try:
            os.mkdir(AUTONOMY_TRANSACTION, 0o700)
            os.chown(AUTONOMY_TRANSACTION, 0, 0)
            os.chmod(AUTONOMY_TRANSACTION, 0o700)
            _fsync_directory(CONFIG_ROOT)
            prior_control, prior_worker = self._archive_paths()
            control_bytes = transaction.prior_configs.control_bytes or encode_config(
                transaction.prior_configs.control
            )
            worker_bytes = transaction.prior_configs.worker_bytes or encode_config(
                transaction.prior_configs.worker
            )
            if (
                sha256_bytes(control_bytes)
                != transaction.prior_configs.control_sha256
                or sha256_bytes(worker_bytes)
                != transaction.prior_configs.worker_sha256
            ):
                raise TransactionEffectUnknown()
            _atomic_file(
                prior_control,
                control_bytes,
                mode=0o400,
                uid=0,
                gid=0,
                replace=False,
            )
            _atomic_file(
                prior_worker,
                worker_bytes,
                mode=0o400,
                uid=0,
                gid=0,
                replace=False,
            )
            self._persist_phase(transaction, "LOCKED", operation=operation)
        except Exception:
            # A partially created marker is evidence and is deliberately kept.
            raise

    def existing_arm(
        self, request: ArmRequest, *, now: datetime
    ) -> TransactionResult | None:
        self.require_exact_install(request.expected_sha)
        snapshot = self.collect_status(request.expected_sha, now=now)
        evidence = snapshot.evidence
        if not evidence.control_armed and not evidence.worker_armed:
            return None
        if status_document(snapshot, now=now)["status"] != "ARMED_READY":
            raise ArmAdmissionError("changed_arm_evidence")
        try:
            payload, _raw = _root_json(
                AUTONOMY_RECEIPT, modes=frozenset({0o444}), uid=0, gid=0
            )
            gate_digest = self.validate_gate_b(
                request.gate_b_receipt, request.expected_sha
            )
            acceptance_digest = self.validate_acceptance(request.expected_sha)
        except (HostControlError, ArmAdmissionError) as exc:
            raise ArmAdmissionError("changed_arm_evidence") from exc
        if (
            payload.get("state") != "ARMED"
            or payload.get("gate_b_receipt_sha256") != gate_digest
            or payload.get("acceptance_receipt_sha256") != acceptance_digest
            or payload.get("expected_credential_kind")
            != request.expected_credential_kind
            or payload.get("workspace_binding_class")
            != request.workspace_binding_class
            or payload.get("credential_expires_at")
            != request.credential_expires_at
        ):
            raise ArmAdmissionError("changed_arm_evidence")
        return TransactionResult(
            state="ARMED",
            status="ARMED_READY",
            transaction_id=str(payload["transaction_id"]),
            replayed=True,
        )

    def existing_disarm(
        self, expected_sha: str, *, now: datetime
    ) -> TransactionResult | None:
        self.require_exact_install(expected_sha)
        if AUTONOMY_TRANSACTION.exists() or AUTONOMY_TRANSACTION.is_symlink():
            return None
        snapshot = self.collect_status(expected_sha, now=now)
        if status_document(snapshot, now=now)["status"] != "UNARMED":
            return None
        transaction_id: str | None = None
        if AUTONOMY_RECEIPT.exists() and not AUTONOMY_RECEIPT.is_symlink():
            try:
                payload, _raw = _root_json(
                    AUTONOMY_RECEIPT,
                    modes=frozenset({0o444}),
                    uid=0,
                    gid=0,
                )
                if payload.get("state") == "DISARMED" and re.fullmatch(
                    r"autonomy-[0-9a-f]{12}",
                    str(payload.get("transaction_id", "")),
                ):
                    transaction_id = str(payload["transaction_id"])
            except HostControlError:
                return None
        return TransactionResult(
            state="DISARMED",
            status="UNARMED",
            transaction_id=transaction_id,
            replayed=True,
        )

    def new_transaction_id(self) -> str:
        if AUTONOMY_TRANSACTION.exists() and not AUTONOMY_TRANSACTION.is_symlink():
            return str(self._manifest()["transaction_id"])
        return f"autonomy-{secrets.token_hex(6)}"

    def begin_transaction(self, transaction: TransactionContext) -> None:
        if AUTONOMY_TRANSACTION.exists() or AUTONOMY_TRANSACTION.is_symlink():
            raise ArmAdmissionError("transaction_incomplete")
        self._active_transaction = transaction
        try:
            self._create_marker(transaction, operation="ARM")
        except FileExistsError as exc:
            self._active_transaction = None
            raise ArmAdmissionError("transaction_incomplete") from exc

    def write_candidates(self, transaction: TransactionContext) -> None:
        self._active_transaction = transaction
        control_candidate, worker_candidate = self._candidate_paths(
            transaction.transaction_id
        )
        control_gid = grp.getgrnam(CONTROL_GROUP).gr_gid
        worker_gid = grp.getgrnam(WORKER_GROUP).gr_gid
        _atomic_file(
            control_candidate,
            transaction.candidates.control_bytes,
            mode=0o440,
            uid=0,
            gid=control_gid,
            replace=False,
        )
        _atomic_file(
            worker_candidate,
            transaction.candidates.worker_bytes,
            mode=0o440,
            uid=0,
            gid=worker_gid,
            replace=False,
        )
        self._persist_phase(transaction, "CANDIDATES_WRITTEN")

    @staticmethod
    def _run_fixed(command: Sequence[str], *, cwd: Path, timeout: float = 30.0) -> None:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=timeout,
        )
        if completed.returncode != 0:
            raise RuntimeError("fixed Executive host command refused")

    def validate_candidates(self, transaction: TransactionContext) -> None:
        release = SYSTEM_ROOT / "releases" / transaction.expected_sha
        control_candidate, worker_candidate = self._candidate_paths(
            transaction.transaction_id
        )
        worker_home = RUNTIME_ROOT / "workers" / "codex-01" / "provider-home"
        control_home = RUNTIME_ROOT / "control" / "home"
        self._run_fixed(
            [
                "/usr/bin/sudo",
                "-u",
                "_mastermind_worker",
                "/usr/bin/env",
                "-i",
                f"HOME={worker_home}",
                "PATH=/usr/bin:/bin:/usr/sbin:/sbin",
                "LANG=C.UTF-8",
                "LC_ALL=C.UTF-8",
                os.fspath(PINNED_PYTHON),
                "-I",
                "-S",
                "-B",
                os.fspath(release / "scripts/executive_os_phase1c_worker.py"),
                "check-config",
                "--config",
                os.fspath(worker_candidate),
            ],
            cwd=release,
        )
        self._run_fixed(
            [
                "/usr/bin/sudo",
                "-u",
                CONTROL_USER,
                "/usr/bin/env",
                "-i",
                f"HOME={control_home}",
                "PATH=/usr/bin:/bin:/usr/sbin:/sbin",
                "LANG=C.UTF-8",
                "LC_ALL=C.UTF-8",
                "PYTHONDONTWRITEBYTECODE=1",
                os.fspath(PINNED_PYTHON),
                "-I",
                "-S",
                "-B",
                "-c",
                (
                    "import sys;sys.path.insert(0,sys.argv[1]);"
                    "from scripts.executive_os_phase1c import load_control_config;"
                    "load_control_config(sys.argv[2])"
                ),
                os.fspath(release),
                os.fspath(control_candidate),
            ],
            cwd=release,
        )
        self._persist_phase(transaction, "CANDIDATES_VALIDATED")

    @staticmethod
    def _replace_candidate(candidate: Path, destination: Path, *, gid: int) -> None:
        info = candidate.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or info.st_gid != gid
            or stat.S_IMODE(info.st_mode) != 0o440
            or info.st_nlink != 1
            or _has_acl(candidate)
        ):
            raise TransactionEffectUnknown()
        os.replace(candidate, destination)
        _fsync_directory(CONFIG_ROOT)

    def replace_worker_config(self, transaction: TransactionContext) -> None:
        _control_candidate, worker_candidate = self._candidate_paths(
            transaction.transaction_id
        )
        self._replace_candidate(
            worker_candidate,
            WORKER_CONFIG,
            gid=grp.getgrnam(WORKER_GROUP).gr_gid,
        )
        self._persist_phase(transaction, "WORKER_REPLACED")

    def replace_control_config(self, transaction: TransactionContext) -> None:
        control_candidate, _worker_candidate = self._candidate_paths(
            transaction.transaction_id
        )
        self._replace_candidate(
            control_candidate,
            CONTROL_CONFIG,
            gid=grp.getgrnam(CONTROL_GROUP).gr_gid,
        )
        self._persist_phase(transaction, "CONTROL_REPLACED")

    def write_autonomy_receipt(
        self, transaction: TransactionContext, receipt: Mapping[str, Any]
    ) -> None:
        observed = _parse_timestamp(receipt.get("observed_at"))
        if observed is None:
            raise TransactionEffectUnknown()
        try:
            validate_receipt_document(
                receipt,
                metadata=ReceiptMetadata(
                    uid=0,
                    gid=0,
                    mode=0o444,
                    nlink=1,
                    is_regular=True,
                    is_symlink=False,
                    has_acl=False,
                ),
                expected=AutonomyExpectation(
                    release_sha=transaction.expected_sha,
                    control_config_sha256=transaction.candidates.control_sha256,
                    worker_config_sha256=transaction.candidates.worker_sha256,
                    provider_readiness_receipt_sha256=str(
                        receipt.get("provider_readiness_receipt_sha256", "")
                    ),
                    capability_policy_digest=CAPABILITY_POLICY_DIGEST,
                    execution_profile_digest=EXECUTION_PROFILE_DIGEST,
                    native_helper_grant_digest=NATIVE_HELPER_GRANT_DIGEST,
                    security_config_digest=SECURITY_CONFIG_DIGEST,
                ),
                now=observed,
                require_current=receipt.get("state") == "ARMED",
            )
        except AutonomyRefusal as exc:
            raise TransactionEffectUnknown() from exc
        replace = AUTONOMY_RECEIPT.exists() or AUTONOMY_RECEIPT.is_symlink()
        if replace:
            metadata = _receipt_metadata(AUTONOMY_RECEIPT)
            if metadata != ReceiptMetadata(
                uid=0,
                gid=0,
                mode=0o444,
                nlink=1,
                is_regular=True,
                is_symlink=False,
                has_acl=False,
            ):
                raise TransactionEffectUnknown()
        _atomic_file(
            AUTONOMY_RECEIPT,
            _encoded_json(receipt),
            mode=0o444,
            uid=0,
            gid=0,
            replace=replace,
        )
        self._persist_phase(transaction, "RECEIPT_REPLACED")

    def _service_command(self, expected_sha: str, action: str) -> None:
        if action not in {"start", "stop"}:
            raise TransactionEffectUnknown()
        release = SYSTEM_ROOT / "releases" / expected_sha
        self._run_fixed(
            [
                "/bin/bash",
                os.fspath(release / "ops/executive_os/service-control.sh"),
                action,
            ],
            cwd=release,
            timeout=45.0,
        )

    def start_services(self, expected_sha: str) -> None:
        self._service_command(expected_sha, "start")
        if self._active_transaction is not None:
            self._persist_phase(self._active_transaction, "SERVICES_STARTED")

    def prove_services_ready(self, expected_sha: str) -> None:
        deadline = time.monotonic() + 45.0
        while time.monotonic() < deadline:
            service_state, reconciled = self._service_state(expected_sha)
            if reconciled and service_state == "READY":
                if self._active_transaction is not None:
                    self._persist_phase(self._active_transaction, "READY_PROVEN")
                return
            time.sleep(1.0)
        raise RuntimeError("Executive services did not reach READY")

    def stop_services(self, expected_sha: str) -> None:
        self._service_command(expected_sha, "stop")
        if self._loaded(CONTROL_LABEL) or self._loaded(WORKER_LABEL):
            raise TransactionEffectUnknown()

    @staticmethod
    def _remove_candidate(path: Path) -> None:
        if not path.exists() and not path.is_symlink():
            return
        info = path.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or info.st_nlink != 1
        ):
            raise TransactionEffectUnknown()
        path.unlink()
        _fsync_directory(CONFIG_ROOT)

    def complete_transaction(self, transaction: TransactionContext) -> None:
        manifest = self._manifest()
        if (
            manifest.get("transaction_id") != transaction.transaction_id
            or manifest.get("expected_sha") != transaction.expected_sha
        ):
            raise TransactionEffectUnknown()
        control_candidate, worker_candidate = self._candidate_paths(
            transaction.transaction_id
        )
        self._remove_candidate(control_candidate)
        self._remove_candidate(worker_candidate)
        expected = {"transaction.json", "prior-control.json", "prior-worker.json"}
        if set(os.listdir(AUTONOMY_TRANSACTION)) != expected:
            raise TransactionEffectUnknown()
        for path in (*self._archive_paths(), self._manifest_path()):
            info = path.lstat()
            if (
                stat.S_ISLNK(info.st_mode)
                or not stat.S_ISREG(info.st_mode)
                or info.st_uid != 0
                or info.st_gid != 0
                or stat.S_IMODE(info.st_mode) != 0o400
                or info.st_nlink != 1
            ):
                raise TransactionEffectUnknown()
            path.unlink()
        _fsync_directory(AUTONOMY_TRANSACTION)
        AUTONOMY_TRANSACTION.rmdir()
        _fsync_directory(CONFIG_ROOT)
        self._active_transaction = None

    def _archived_configs(self, expected_sha: str) -> ConfigEvidence:
        control_path, worker_path = self._archive_paths()
        control, control_raw = _root_json(
            control_path, modes=frozenset({0o400}), uid=0, gid=0
        )
        worker, worker_raw = _root_json(
            worker_path, modes=frozenset({0o400}), uid=0, gid=0
        )
        manifest = self._manifest()
        if (
            manifest.get("expected_sha") != expected_sha
            or sha256_bytes(control_raw) != manifest.get("prior_control_sha256")
            or sha256_bytes(worker_raw) != manifest.get("prior_worker_sha256")
        ):
            raise TransactionEffectUnknown()
        return ConfigEvidence(
            control_sha256=sha256_bytes(control_raw),
            worker_sha256=sha256_bytes(worker_raw),
            control=control,
            worker=worker,
            control_bytes=control_raw,
            worker_bytes=worker_raw,
        )

    def begin_disarm(self, expected_sha: str, transaction_id: str) -> ConfigEvidence:
        if AUTONOMY_TRANSACTION.exists() and not AUTONOMY_TRANSACTION.is_symlink():
            manifest = self._manifest()
            if (
                manifest.get("transaction_id") != transaction_id
                or manifest.get("expected_sha") != expected_sha
            ):
                raise TransactionEffectUnknown()
            return self._archived_configs(expected_sha)
        try:
            (
                control,
                worker,
                control_digest,
                worker_digest,
                control_raw,
                worker_raw,
            ) = self._configs()
        except (HostControlError, KeyError, OSError) as exc:
            raise TransactionEffectUnknown() from exc
        configs = ConfigEvidence(
            control_sha256=control_digest,
            worker_sha256=worker_digest,
            control=control,
            worker=worker,
            control_bytes=control_raw,
            worker_bytes=worker_raw,
        )
        placeholder = TransactionContext(
            transaction_id=transaction_id,
            expected_sha=expected_sha,
            prior_configs=configs,
            candidates=derive_candidate_configs(configs, armed=False),
            admission=None,
        )
        self._active_transaction = placeholder
        self._create_marker(placeholder, operation="DISARM")
        return configs

    def rollback_disarmed(
        self, transaction: TransactionContext, receipt: Mapping[str, Any]
    ) -> None:
        self._active_transaction = transaction
        control_candidate, worker_candidate = self._candidate_paths(
            transaction.transaction_id
        )
        self._remove_candidate(control_candidate)
        self._remove_candidate(worker_candidate)
        self.write_candidates(transaction)
        self.validate_candidates(transaction)
        self.replace_worker_config(transaction)
        self.replace_control_config(transaction)
        self.write_autonomy_receipt(transaction, receipt)
        (
            control,
            worker,
            control_digest,
            worker_digest,
            _control_raw,
            _worker_raw,
        ) = self._configs()
        if (
            control.get("coo_autonomy_armed") is not False
            or control.get("coo_operator_harness_armed") is not False
            or worker.get("operator_harness_armed") is not False
            or control_digest != transaction.candidates.control_sha256
            or worker_digest != transaction.candidates.worker_sha256
            or self._loaded(CONTROL_LABEL)
            or self._loaded(WORKER_LABEL)
        ):
            raise TransactionEffectUnknown()
        self.complete_transaction(transaction)


class ProductionCeoSubmitHost(ProductionTransactionHost):
    """Root-only CEO-submit arm owner inside the one global autonomy transaction.

    The CEO-submit operation domain is a distinct operation inside the existing
    serialized controller: it reuses ``AUTONOMY_TRANSACTION``, that marker's
    manifest, the atomic candidate writer, the postimage verifier and the
    completion path.  It opens no second lock, never writes
    ``worker-codex.json``, and never consults provider readiness, Gate B or a
    worker credential.
    """

    def effective_uid(self) -> int:
        uid = os.geteuid()
        require_root_privilege(uid)
        return uid

    def require_exact_install(self, expected_sha: str) -> str:
        try:
            self._require_host()
        except HostControlError as exc:
            if exc.code == "privilege_required":
                raise
            raise CeoSubmitAdmissionError("release_identity_mismatch") from exc
        try:
            return self._release_identity(expected_sha)
        except HostControlError as exc:
            raise CeoSubmitAdmissionError("release_identity_mismatch") from exc

    def load_ceo_submit_configs(self, expected_sha: str) -> ConfigEvidence:
        try:
            (
                control,
                worker,
                control_digest,
                worker_digest,
                control_raw,
                worker_raw,
            ) = self._configs()
        except (HostControlError, KeyError, OSError) as exc:
            raise CeoSubmitAdmissionError("ceo_submit_config_schema_drift") from exc
        if control.get("proof_base_sha") != expected_sha:
            raise CeoSubmitAdmissionError("release_identity_mismatch")
        return ConfigEvidence(
            control_sha256=control_digest,
            worker_sha256=worker_digest,
            control=control,
            worker=worker,
            control_bytes=control_raw,
            worker_bytes=worker_raw,
        )

    def executive_app_binding(self) -> ExecutiveAppBinding:
        binding_values: dict[str, Any] = {
            "present": False,
            "app_peer_uid": -1,
            "app_peer_user": "",
            "app_armed": False,
            "app_macro_root": "",
            "ingress_peer_uid": -1,
            "ingress_socket_path": "",
            "launchd_socket_name": "",
            "binding_valid": False,
            "acl_valid": False,
            "topology_valid": False,
        }
        try:
            identity = pwd.getpwnam(EXECUTIVE_APP_USER)
        except KeyError:
            return ExecutiveAppBinding(**binding_values)
        binding_values["present"] = True
        binding_values["app_peer_user"] = identity.pw_name
        try:
            control_gid = grp.getgrnam(CONTROL_GROUP).gr_gid
            control, _raw = _root_json(
                CONTROL_CONFIG, modes=frozenset({0o440}), gid=control_gid
            )
        except (HostControlError, KeyError, OSError):
            return ExecutiveAppBinding(**binding_values)
        app_peer_uid = control.get("ceo_ingress_app_peer_uid")
        app_armed = control.get("ceo_ingress_app_armed")
        ingress_peer_uid = control.get("ceo_ingress_peer_uid")
        app_macro_root = control.get("ceo_ingress_app_macro_root")
        socket_path = control.get("ceo_ingress_socket_path")
        launchd_name = control.get("ceo_ingress_launchd_socket_name")
        if (
            type(app_peer_uid) is not int
            or type(ingress_peer_uid) is not int
            or type(app_armed) is not bool
            or not all(
                isinstance(value, str) and value
                for value in (app_macro_root, socket_path, launchd_name)
            )
        ):
            return ExecutiveAppBinding(**binding_values)
        reserved: set[Any] = {
            control.get("control_uid"),
            ingress_peer_uid,
            control.get("worker_uid"),
        }
        allowed = control.get("allowed_peer_uids")
        if isinstance(allowed, (list, tuple)):
            reserved.update(value for value in allowed if type(value) is int)
        binding_values.update(
            {
                "app_peer_uid": app_peer_uid,
                "app_armed": app_armed,
                "app_macro_root": app_macro_root,
                "ingress_peer_uid": ingress_peer_uid,
                "ingress_socket_path": socket_path,
                "launchd_socket_name": launchd_name,
            }
        )
        binding_values["binding_valid"] = (
            app_peer_uid == identity.pw_uid and app_peer_uid not in reserved
        )
        binding_values["acl_valid"] = not _has_acl(CONTROL_CONFIG) and not _has_acl(
            CONTROL_PLIST
        )
        binding_values["topology_valid"] = (
            launchd_name == CEO_INGRESS_LAUNCHD_SOCKET_NAME
            and socket_path == CEO_INGRESS_SOCKET_PATH
            and launchd_name != control.get("launchd_socket_name")
            and socket_path != control.get("control_socket_path")
            and Path(app_macro_root).is_absolute()
            and os.path.dirname(app_macro_root)
            == os.fspath(SYSTEM_ROOT / "macro-sources")
            and re.fullmatch(r"[0-9a-f]{40}", Path(app_macro_root).name) is not None
        )
        return ExecutiveAppBinding(**binding_values)

    def ceo_submit_separation(self, configs: ConfigEvidence) -> CeoSubmitSeparation:
        control = dict(configs.control)
        worker = dict(configs.worker)
        app_armed = control.get("ceo_ingress_app_armed")
        coo_armed = control.get("coo_autonomy_armed")
        operator_armed = control.get("coo_operator_harness_armed")
        worker_armed = worker.get("operator_harness_armed")
        ingress_peer_uid = control.get("ceo_ingress_peer_uid")
        app_peer_uid = control.get("ceo_ingress_app_peer_uid")
        if (
            type(app_armed) is not bool
            or type(coo_armed) is not bool
            or type(operator_armed) is not bool
            or type(worker_armed) is not bool
            or type(ingress_peer_uid) is not int
            or type(app_peer_uid) is not int
        ):
            raise CeoSubmitAdmissionError("ceo_submit_config_schema_drift")
        return CeoSubmitSeparation(
            ceo_ingress_app_armed=app_armed,
            ceo_ingress_app_peer_uid=app_peer_uid,
            ceo_ingress_peer_uid=ingress_peer_uid,
            coo_autonomy_armed=coo_armed,
            coo_operator_harness_armed=operator_armed,
            worker_operator_harness_armed=worker_armed,
        )

    def require_transaction_absent(self) -> None:
        try:
            present = self._transaction_present()
        except HostControlError as exc:
            raise CeoSubmitAdmissionError("ceo_submit_transaction_incomplete") from exc
        if present:
            raise CeoSubmitAdmissionError("ceo_submit_transaction_incomplete")

    def new_transaction_id(self) -> str:
        if AUTONOMY_TRANSACTION.exists() and not AUTONOMY_TRANSACTION.is_symlink():
            return str(self._manifest()["transaction_id"])
        return f"autonomy-{secrets.token_hex(6)}"

    def begin_ceo_submit_transaction(
        self, transaction: TransactionContext, *, operation: str
    ) -> None:
        if operation not in CEO_SUBMIT_OPERATIONS:
            raise CeoSubmitAdmissionError("ceo_submit_transaction_incomplete")
        if AUTONOMY_TRANSACTION.exists() or AUTONOMY_TRANSACTION.is_symlink():
            raise CeoSubmitAdmissionError("ceo_submit_transaction_incomplete")
        self._active_transaction = transaction
        try:
            self._create_marker(transaction, operation=operation)
        except FileExistsError as exc:
            self._active_transaction = None
            raise CeoSubmitAdmissionError("ceo_submit_transaction_incomplete") from exc

    def write_candidates(self, transaction: TransactionContext) -> None:
        self._active_transaction = transaction
        control_candidate, _worker_candidate = self._candidate_paths(
            transaction.transaction_id
        )
        _atomic_file(
            control_candidate,
            transaction.candidates.control_bytes,
            mode=0o440,
            uid=0,
            gid=grp.getgrnam(CONTROL_GROUP).gr_gid,
            replace=False,
        )
        self._persist_phase(transaction, "CANDIDATES_WRITTEN")

    def validate_candidates(self, transaction: TransactionContext) -> None:
        release = SYSTEM_ROOT / "releases" / transaction.expected_sha
        control_candidate, _worker_candidate = self._candidate_paths(
            transaction.transaction_id
        )
        control_home = RUNTIME_ROOT / "control" / "home"
        control_gid = grp.getgrnam(CONTROL_GROUP).gr_gid
        worker_gid = grp.getgrnam(WORKER_GROUP).gr_gid
        expected_armed = self._manifest().get("operation") == "CEO_SUBMIT_ARM"
        self._run_fixed(
            [
                "/usr/bin/sudo",
                "-u",
                CONTROL_USER,
                "/usr/bin/env",
                "-i",
                f"HOME={control_home}",
                "PATH=/usr/bin:/bin:/usr/sbin:/sbin",
                "LANG=C.UTF-8",
                "LC_ALL=C.UTF-8",
                "PYTHONDONTWRITEBYTECODE=1",
                os.fspath(PINNED_PYTHON),
                "-I",
                "-S",
                "-B",
                "-c",
                (
                    "import sys;sys.path.insert(0,sys.argv[1]);"
                    "from scripts.executive_os_phase1c import load_control_config;"
                    "load_control_config(sys.argv[2])"
                ),
                os.fspath(release),
                os.fspath(control_candidate),
            ],
            cwd=release,
        )
        candidate_control, candidate_raw = _root_json(
            control_candidate, modes=frozenset({0o440}), uid=0, gid=control_gid
        )
        worker_raw, _worker_info = _read_root_file(
            WORKER_CONFIG, modes=frozenset({0o440}), gid=worker_gid
        )
        if (
            sha256_bytes(candidate_raw) != transaction.candidates.control_sha256
            or candidate_control.get("ceo_submit_armed") is not expected_armed
            or not _ceo_submit_only_flag_differs(
                transaction.prior_configs.control, candidate_control
            )
            or sha256_bytes(worker_raw) != transaction.candidates.worker_sha256
            or sha256_bytes(worker_raw) != transaction.prior_configs.worker_sha256
        ):
            raise TransactionEffectUnknown()
        self._persist_phase(transaction, "CANDIDATES_VALIDATED")

    def replace_worker_config(self, transaction: TransactionContext) -> None:
        # The CEO-submit domain never owns the worker config, even by accident.
        raise TransactionEffectUnknown()

    def write_ceo_submit_receipt(
        self, transaction: TransactionContext, receipt: Mapping[str, Any]
    ) -> None:
        if _parse_timestamp(receipt.get("observed_at")) is None:
            raise TransactionEffectUnknown()
        projection = receipt.get("projection")
        if (
            receipt.get("schema_version") != CEO_SUBMIT_RECEIPT_SCHEMA
            or receipt.get("operation") not in CEO_SUBMIT_OPERATIONS
            or receipt.get("state") not in {"CEO_SUBMIT_ARMED", "CEO_SUBMIT_DISARMED"}
            or receipt.get("transaction_id") != transaction.transaction_id
            or not isinstance(projection, Mapping)
            or set(projection) != _CEO_SUBMIT_PROJECTION_FIELDS
            or receipt.get("projection_digest")
            != ceo_submit_projection_digest(projection)
            or projection.get("transaction_id") != transaction.transaction_id
            or projection.get("release_sha") != transaction.expected_sha
            or (receipt.get("state") == "CEO_SUBMIT_ARMED")
            is not projection.get("ceo_submit_armed")
        ):
            raise TransactionEffectUnknown()
        replace = CEO_SUBMIT_RECEIPT.exists() or CEO_SUBMIT_RECEIPT.is_symlink()
        if replace and _receipt_metadata(CEO_SUBMIT_RECEIPT) != ReceiptMetadata(
            uid=0,
            gid=0,
            mode=0o444,
            nlink=1,
            is_regular=True,
            is_symlink=False,
            has_acl=False,
        ):
            raise TransactionEffectUnknown()
        _atomic_file(
            CEO_SUBMIT_RECEIPT,
            _encoded_json(dict(receipt)),
            mode=0o444,
            uid=0,
            gid=0,
            replace=replace,
        )
        self._persist_phase(transaction, "RECEIPT_REPLACED")

    def reconcile_control_service(self, expected_sha: str) -> None:
        """Converge only the control boundary onto the replaced config.

        The reviewed lifecycle controller exposes no control-only verb, so the
        reload uses the one fixed control label through ``launchctl kickstart``.
        The worker boundary is never reloaded by this ARM path; both arm bits are
        still false afterwards, so a running worker cannot execute anything.
        """

        if self._loaded(CONTROL_LABEL):
            self._run_fixed(
                ["/bin/launchctl", "kickstart", "-k", f"system/{CONTROL_LABEL}"]
            )
        else:
            release = SYSTEM_ROOT / "releases" / expected_sha
            self._run_fixed(
                [
                    "/bin/bash",
                    os.fspath(release / "ops/executive_os/service-control.sh"),
                    "start",
                ],
                cwd=release,
                timeout=45.0,
            )
        if not self._loaded(CONTROL_LABEL):
            raise TransactionEffectUnknown()
        if self._active_transaction is not None:
            self._persist_phase(
                self._active_transaction,
                "CONTROL_RECONCILED",
                operation="CEO_SUBMIT_ARM",
            )

    def prove_control_ready(self, expected_sha: str) -> None:
        deadline = time.monotonic() + 45.0
        while time.monotonic() < deadline:
            if self._loaded(CONTROL_LABEL) and self._control_ready(expected_sha):
                if self._active_transaction is not None:
                    self._persist_phase(
                        self._active_transaction,
                        "READY_PROVEN",
                        operation="CEO_SUBMIT_ARM",
                    )
                return
            time.sleep(1.0)
        raise RuntimeError("Executive control service did not reach READY")

    def rollback_ceo_submit(
        self, transaction: TransactionContext, receipt: Mapping[str, Any]
    ) -> None:
        """Restore the archived preimage and prove it, or stay EFFECT_UNKNOWN."""

        self._active_transaction = transaction
        control_candidate, _worker_candidate = self._candidate_paths(
            transaction.transaction_id
        )
        self._remove_candidate(control_candidate)
        prior_control_bytes = transaction.prior_configs.control_bytes or encode_config(
            transaction.prior_configs.control
        )
        if (
            sha256_bytes(prior_control_bytes) != transaction.prior_configs.control_sha256
        ):
            raise TransactionEffectUnknown()
        _atomic_file(
            CONTROL_CONFIG,
            prior_control_bytes,
            mode=0o440,
            uid=0,
            gid=grp.getgrnam(CONTROL_GROUP).gr_gid,
            replace=CONTROL_CONFIG.exists() or CONTROL_CONFIG.is_symlink(),
        )
        self.write_ceo_submit_receipt(transaction, receipt)
        (
            control,
            _worker,
            control_digest,
            worker_digest,
            _control_raw,
            _worker_raw,
        ) = self._configs()
        if (
            control.get("ceo_submit_armed") is not False
            or control_digest != transaction.prior_configs.control_sha256
            or worker_digest != transaction.prior_configs.worker_sha256
        ):
            raise TransactionEffectUnknown()
        self.complete_transaction(transaction)


def main(
    argv: Sequence[str] | None = None,
    *,
    host: StatusHost | TransactionHost | None = None,
    now: Callable[[], datetime] | None = None,
) -> int:
    args = _parser().parse_args(argv)
    current = (datetime.now(UTC) if now is None else now()).astimezone(UTC)
    if args.command == "status":
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

    transaction_host = ProductionTransactionHost() if host is None else host
    try:
        if args.command == "arm":
            result = execute_arm(
                transaction_host,
                ArmRequest(
                    expected_sha=args.expected_sha,
                    gate_b_receipt=args.gate_b_receipt,
                    expected_credential_kind=args.expected_credential_kind,
                    workspace_binding_class=args.workspace_binding_class,
                    credential_expires_at=args.credential_expires_at,
                ),
                now=current,
            )
            code = "already_armed" if result.replayed else "armed"
        else:
            result = execute_disarm(
                transaction_host, args.expected_sha, now=current
            )
            code = "already_disarmed" if result.replayed else "disarmed"
        document = operation_document(
            code=code,
            state=result.state,
            status=result.status,
            transaction_id=result.transaction_id,
            replayed=result.replayed,
        )
        exit_code = 0
    except ArmTransactionError as exc:
        document = operation_document(
            code=exc.code,
            state="DISARMED",
            status="UNARMED",
            transaction_id=None,
        )
        exit_code = 2
    except ArmAdmissionError as exc:
        document = operation_document(
            code=exc.code,
            state="UNARMED",
            status="UNARMED",
            transaction_id=None,
        )
        exit_code = 2
    except TransactionEffectUnknown:
        document = operation_document(
            code="effect_unknown",
            state="UNKNOWN",
            status="EFFECT_UNKNOWN",
            transaction_id=None,
        )
        exit_code = 2
    except Exception:
        document = operation_document(
            code="effect_unknown",
            state="UNKNOWN",
            status="EFFECT_UNKNOWN",
            transaction_id=None,
        )
        exit_code = 2
    print(json.dumps(document, sort_keys=True, separators=(",", ":")))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
