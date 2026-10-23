"""Root-only status/arm/disarm surface for Executive OS autonomy.

The status path is implemented first and is strictly read-only.  Arm and
disarm share this fixed parser but do not acquire mutation behavior until their
transaction gates are implemented and tested in the following plan tasks.

The CEO-submit operation domain (ARM/DISARM of the chair-default ingress sink)
rides the one existing ``AUTONOMY_TRANSACTION`` owner.  ``ceo_submit_sink_eligible``
is the SOURCE-side eligibility gate for the existing ``submit-ceo-intent`` sink:
``control_plane/executive_service.py`` does not yet consult it -- that integration
is a later wave -- so that function proves eligibility in source only and claims
no runtime effect.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import fcntl
import grp
import hashlib
import json
import os
import plistlib
import pwd
import re
import secrets
import selectors
import signal
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
from control_plane.codex_worker import ProcessInspector

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
    load_receipt_file,
    validate_runtime_guard_document,
)
from ops.executive_os import release_manifest
from ops.executive_os import git_handoff_preflight
from ops.executive_os import provider_readiness
from ops.executive_os import provider_worker_slots
from scripts import executive_os_phase1c_control_wrapper as control_wrapper


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
DIALOGUE_CANARY_OPERATIONS = frozenset({"DIALOGUE_WAKE_CANARY_PUBLISH"})
CONTROL_ONLY_TRANSACTION_OPERATIONS = CEO_SUBMIT_OPERATIONS | DIALOGUE_CANARY_OPERATIONS
_CANARY_RECEIPT_ARCHIVE = "prior-dialogue-canary-receipt.json"
_CANARY_MANIFEST_FIELDS = frozenset({
    "prior_canary_receipt_sha256", "target_canary_receipt_sha256",
    "prior_canary_receipt_present",
})
_COEXISTENCE_ARCHIVES = ("prior-autonomy-receipt.json", "prior-ceo-submit-receipt.json")
_COEXISTENCE_MANIFEST_FIELDS = frozenset({
    "prior_autonomy_receipt_sha256", "target_autonomy_receipt_sha256",
    "prior_ceo_receipt_present", "prior_ceo_receipt_sha256",
    "target_ceo_receipt_sha256",
})
_FINITE_RECEIPT_ARCHIVE = "prior-finite-disarmed-receipt.json"
_FINITE_RECEIPT_FIELDS = frozenset({
    "finite_prior_receipt_present", "finite_prior_receipt_sha256",
    "finite_target_receipt_sha256",
})

_PAID_RECEIPT_ARCHIVE = "prior-paid-disarmed-receipt.json"
_PAID_RECEIPT_FIELDS = frozenset({
    "paid_prior_receipt_present", "paid_prior_receipt_sha256",
    "paid_target_receipt_sha256", "paid_definition_sha256",
})

_CONTROL_LAUNCHD_PREIMAGE_FIELD = "control_launchd_disabled_before_reconcile"
_CONTROL_LAUNCHD_DISABLED_ROW_RE = re.compile(
    r'^"(?P<label>[^"]+)"\s*=>\s*(?P<state>enabled|disabled|true|false)$'
)
_CONTROL_LAUNCHD_DISABLED_SPELLINGS = {
    "disabled": True,
    "true": True,
    "enabled": False,
    "false": False,
}
_MAX_LAUNCHCTL_DISABLED_BYTES = 64 * 1024
# R17 B1: the CEO-submit operation domain as it is reachable from THIS CLI.  A
# closed set, so `main` can route the four verbs with one membership test and no
# string prefix matching.
CEO_SUBMIT_COMMANDS = frozenset(
    {
        "ceo-submit-status",
        "ceo-submit-arm",
        "ceo-submit-disarm",
        "ceo-submit-reconcile",
    }
)
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
        "native_selection_invalid",
        "native_listener_unavailable",
        "native_relay_unavailable",
    }
)
_MAX_JSON_BYTES = 1024 * 1024
_TRANSACTION_SCHEMA = "mastermind.executive_autonomy_transaction/v1"
A2_DISABLE_COMMANDS = frozenset({"a2-disable-prepare", "a2-disable-prepare-reconcile"})
_TRANSACTION_OPERATIONS = frozenset({"ARM", "DISARM", "A2_DISABLE_PREPARATION", "FINITE_CONTROL_STAGE", "PAID_CONTROL_STAGE", "OS_GATEWAY_PUBLICATION"}) | CONTROL_ONLY_TRANSACTION_OPERATIONS
# One manifest name for the canonical marker and for the private generation it
# is published from, so a renamed generation is always readable in place.
_TRANSACTION_MANIFEST_NAME = "transaction.json"
_CEO_SUBMIT_ADMISSION_CODES = frozenset(
    {
        "release_identity_mismatch",
        "app_peer_invalid",
        "app_binding_invalid",
        "app_acl_invalid",
        "app_topology_invalid",
        "app_binding_absent",
        "ceo_submit_already_armed",
        # Declared by R9 for the DISARM vocabulary.  ``ceo_submit_already_disarmed``
        # is deliberately unreachable: an already-False arm flag is a read-only
        # REPLAY, never a refusal, and the other three are the disarm refusals.
        "ceo_submit_already_disarmed",
        "full_autonomy_armed_unsafe_coexistence",
        "app_install_would_regress",
        "ceo_submit_effect_unknown_sticky",
        # R68 (R68 item 1): ceo_ingress_app_armed is UID458 transport/peer
        # ADMISSION, not CEO-submit AUTHORITY.  ARM must REQUIRE it True; a
        # False / non-boolean value refuses ARM with this typed pre-write
        # refusal code.  The OLD code name is gone; ``ceo_ingress_app_armed``
        # remains the CONFIG field name and the projection/digest key -- only
        # the refusal CODE was renamed.
        "ceo_ingress_app_unarmed",
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
_CEO_SUBMIT_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "state",
        "operation",
        "projection",
        "projection_digest",
        "transaction_id",
        "observed_at",
        "tool_version",
    }
)
_CEO_SUBMIT_TRANSACTION_RE = re.compile(r"^autonomy-[0-9a-f]{12}$")

# The OS gateway publication operation domain: one closed, root-only
# composition that publishes the three fixed OS gateway targets through the
# ONE existing ``AUTONOMY_TRANSACTION`` owner.  The MCP daemon identity below
# is the same fixed pair ``service-control.sh`` already qualifies; nothing
# here is caller selectable.
OS_GATEWAY_PUBLICATION = "OS_GATEWAY_PUBLICATION"
OS_GATEWAY_COMMANDS = frozenset({"publish-os-gateway", "reconcile-os-gateway"})
OS_GATEWAY_RECEIPT = CONFIG_ROOT / "os-gateway-publication-v1.json"
OS_GATEWAY_RECEIPT_SCHEMA = "mastermind.executive_os_gateway_receipt/v1"
OS_GATEWAY_MCP_CONFIG = Path(
    "/Library/Application Support/MastermindExecutive/config/executive-mcp.json"
)
OS_GATEWAY_MCP_PLIST = Path("/Library/LaunchDaemons/com.mastermind.executive.mcp.plist")
OS_GATEWAY_MCP_LABEL = "com.mastermind.executive.mcp"
OS_GATEWAY_COMMISSION_GRANT = CONFIG_ROOT / "os-commission-publication.json"
OS_GATEWAY_GRANT_SCHEMA = "mastermind.os_commission_publication.v1"
OS_GATEWAY_GRANT_KEYS = frozenset(
    {
        "schema",
        "release_sha",
        "studio_uid",
        "studio_account",
        "studio_port",
        "policy",
        "grants",
        "base_sha",
        "audit_directory",
        "auth_helper_sha256",
        "file_helper_sha256",
    }
)
OS_GATEWAY_GRANT_AUDIT_DIRECTORY = (
    "/Library/Application Support/MastermindExecutive/audit/os-commission-publication"
)
# The one dedicated Studio publication seat: fixed identity, fixed port, fixed
# label, fixed paths.  No account, path or port is ever a CLI argument.
OS_GATEWAY_STUDIO_UID = 501
OS_GATEWAY_STUDIO_ACCOUNT = "mastermind-os-publication"
OS_GATEWAY_STUDIO_PORT = 45120
OS_GATEWAY_STUDIO_LABEL = (
    f"com.mastermind.studio-direct-private.{OS_GATEWAY_STUDIO_ACCOUNT}"
)
_GATEWAY_STUDIO_BASE_REL = (
    Path(".local/share/studio-direct-mcp/private") / OS_GATEWAY_STUDIO_ACCOUNT
)
_GATEWAY_STUDIO_PLIST_REL = Path(
    f"Library/LaunchAgents/{OS_GATEWAY_STUDIO_LABEL}.plist"
)
_GATEWAY_GRANT_ARCHIVE = "prior-os-commission-grant.json"
# The canonical audit-directory prerequisite is bound in the SAME retained
# intent as the three DATA targets: its before-identity (qualified present
# custody or explicit absence) plus the planned metadata, sealed BEFORE the
# directory create and the first target write.
_GATEWAY_AUDIT_STATE_FIELD = "gateway_audit_directory_state"
_GATEWAY_AUDIT_UID_FIELD = "gateway_audit_directory_uid"
_GATEWAY_AUDIT_GID_FIELD = "gateway_audit_directory_gid"
_GATEWAY_AUDIT_MODE_FIELD = "gateway_audit_directory_mode"
_GATEWAY_AUDIT_BEFORE_FIELD = "gateway_audit_directory_before_identity"
_GATEWAY_AUDIT_AFTER_FIELD = "gateway_audit_directory_identity"


def _gateway_inode_identity(value: Any) -> bool:
    return (type(value) is list and len(value) == 2
            and all(type(item) is int and item >= 0 for item in value)
            and value[1] > 0)

_GATEWAY_MANIFEST_FIELDS = frozenset(
    {
        "gateway_release_bundle_digest",
        "gateway_studio_definition_sha256",
        "gateway_prior_grant_present",
        "gateway_prior_grant_sha256",
        "gateway_target_grant_sha256",
        "gateway_prior_mcp_config_sha256",
        "gateway_target_mcp_config_sha256",
        "gateway_prior_mcp_plist_sha256",
        "gateway_target_mcp_plist_sha256",
        _GATEWAY_AUDIT_STATE_FIELD,
        _GATEWAY_AUDIT_UID_FIELD,
        _GATEWAY_AUDIT_GID_FIELD,
        _GATEWAY_AUDIT_MODE_FIELD,
        _GATEWAY_AUDIT_BEFORE_FIELD,
        _GATEWAY_AUDIT_AFTER_FIELD,
    }
)
_GATEWAY_DIGEST_MANIFEST_FIELDS = frozenset(
    _GATEWAY_MANIFEST_FIELDS
    - {
        "gateway_prior_grant_present",
        _GATEWAY_AUDIT_STATE_FIELD,
        _GATEWAY_AUDIT_UID_FIELD,
        _GATEWAY_AUDIT_GID_FIELD,
        _GATEWAY_AUDIT_MODE_FIELD,
        _GATEWAY_AUDIT_BEFORE_FIELD,
        _GATEWAY_AUDIT_AFTER_FIELD,
    }
)
_GATEWAY_PHASES = frozenset(
    {
        "LOCKED",
        "AUDIT_DIRECTORY_READY",
        "GRANT_PUBLISHED",
        "GATEWAY_CONFIG_REPLACED",
        "GATEWAY_PLIST_REPLACED",
        "GATEWAY_RECEIPT_REPLACED",
    }
)
_GATEWAY_ROOT_FILE_MAX_BYTES = 4 * 1024 * 1024
_GATEWAY_STUDIO_FILE_MAX_BYTES = 1024 * 1024
# The one canonical audit leaf and its closed producer law.  The leaf is the
# only node this owner may create; the fixed parent chain is qualified, never
# fabricated.
_GATEWAY_AUDIT_DIRECTORY = Path(OS_GATEWAY_GRANT_AUDIT_DIRECTORY)
_GATEWAY_AUDIT_LEAF_NAME = _GATEWAY_AUDIT_DIRECTORY.name
_GATEWAY_AUDIT_LEAF_MODE = 0o700
_GATEWAY_AUDIT_ENTRY_MAX_COUNT = 32
_GATEWAY_AUDIT_ENTRY_NAME_MAX = 128


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


def _create_directory(path, mode, *, dir_fd=None):
    """The ONE directory creation site in this module.

    Exactly two lawful creations go through it: a private transaction
    generation for the existing ``AUTONOMY_TRANSACTION`` owner, and the one
    canonical OS gateway audit leaf below its qualified fixed parent.
    Nothing else in this composition ever creates a directory.
    """

    return os.mkdir(
        path,
        mode,
        **({"dir_fd": dir_fd} if dir_fd is not None else {}),
    )


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


# The closed OS gateway publication refusal vocabulary.  Every refusal is
# typed before any target write; publication uncertainty after the marker
# exists is always ``TransactionEffectUnknown`` instead.
_GATEWAY_ADMISSION_CODES = frozenset(
    {
        "gateway_audit_directory_invalid",
        "gateway_bundle_digest_mismatch",
        "gateway_compiler_contract_invalid",
        "gateway_compiler_unavailable",
        "gateway_grant_invalid",
        "gateway_grant_state_conflict",
        "gateway_helper_source_invalid",
        "gateway_launch_receipt_invalid",
        "gateway_mcp_generation_invalid",
        "gateway_namespace_scope_invalid",
        "gateway_receipt_conflict",
        "gateway_receipt_invalid",
        "gateway_release_tree_invalid",
        "gateway_service_running",
        "gateway_studio_invalid",
        "gateway_studio_running",
        "gateway_port_occupied",
        "gateway_submit_allowlist_invalid",
        "gateway_target_invalid",
        "gateway_template_refused",
        "gateway_transaction_incomplete",
        "gateway_workspace_binding_invalid",
    }
)


class GatewayPublicationError(RuntimeError):
    def __init__(self, code: str):
        if code not in _GATEWAY_ADMISSION_CODES:
            raise ValueError("unknown gateway publication refusal")
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


class TransactionOwnershipError(TransactionEffectUnknown):
    """The transaction began but this process never acquired its owner."""


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
    native_return: bool = False
    foreground_only: bool = False


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
    binding: ExecutiveAppBinding | None = None
    separation: CeoSubmitSeparation | None = None
    configs: ConfigEvidence | None = None
    # A DISARM request against an already-False arm flag is a REPLAY: read-only,
    # no lock, no write and no receipt rewrite (R9).  The payload fields above are
    # left unset on that branch on purpose -- nothing was read past the arm flag.
    replayed: bool = False
    replay_transaction_id: str | None = None


@dataclasses.dataclass(frozen=True)
class GatewayPublicationRequest:
    """One closed publish/reconcile request; no path, account or selector."""

    expected_sha: str
    bundle_digest: str
    prior_mcp_config_sha256: str = ""
    prior_mcp_plist_sha256: str = ""
    prior_grant_sha256: str | None = None
    prior_grant_absent: bool = False
    transaction_id: str | None = None


@dataclasses.dataclass(frozen=True)
class GatewayStudioEvidence:
    """The observed identity of the one dedicated Studio publication seat.

    ``definition_sha256`` is a canonical digest over the whole observed
    definition (paths, hashes, custody-relevant facts); it is the stable
    preimage the transaction marker retains and rechecks before every write.
    """

    studio_uid: int
    studio_gid: int
    account: str
    label: str
    port: int
    home: Path
    base: Path
    plist: Path
    source: Path
    node: Path
    backend: Path
    node_sha256: str
    backend_sha256: str
    dependency_tree_sha256: str
    definition_sha256: str


@dataclasses.dataclass(frozen=True)
class GatewayPreparation:
    """Everything the publication phase writes is qualified before the marker.

    ``publication_document`` is the ONE exact existing grant document the
    compiler accepts; the launch/source/Studio provenance above it is kept
    separate and never folded into that document.
    """

    installed: str
    tree_sha: str
    bundle_digest: str
    configs: ConfigEvidence
    candidate_configs: CandidateConfigs
    prior_mcp_config_bytes: bytes
    prior_mcp_plist_bytes: bytes
    prior_release: str
    prior_grant_present: bool
    prior_grant_bytes: bytes
    candidate: Mapping[str, Any]
    publication_document: Mapping[str, Any]
    launch_document: Mapping[str, Any]
    workspace_identity: Mapping[str, str]
    derived_principal_scope: str
    commission_template: Mapping[str, Any]
    derived_policy: Mapping[str, Any]
    audit_directory: Mapping[str, Any]
    studio: GatewayStudioEvidence


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

    def require_native_listener(self, config: ConfigEvidence) -> None: ...

    def require_runtime_quiescent(self, config: ConfigEvidence) -> None: ...

    def require_services_stopped(self) -> None: ...

    def require_services_already_stopped(self) -> None: ...

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

    def proves_safe_coexistence(self, configs: ConfigEvidence) -> bool: ...

    def rebind_full_autonomy_receipt(self, transaction: TransactionContext) -> None: ...

    def incomplete_transaction_operation(self) -> str | None: ...

    def existing_ceo_submit_receipt(self) -> Mapping[str, Any] | None: ...

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

    def prove_control_admission_bound(
        self, expected_sha: str, expected_control_sha256: str
    ) -> None: ...

    def complete_transaction(self, transaction: TransactionContext) -> None: ...

    def rollback_ceo_submit(
        self, transaction: TransactionContext, receipt: Mapping[str, Any]
    ) -> None: ...

    def recover_ceo_submit_effect_unknown(
        self, request: CeoSubmitRequest, *, now: datetime
    ) -> TransactionResult: ...


class _StoreOnce(argparse.Action):
    """Reject repeated authority-bearing flags instead of silently taking last."""

    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is not None:
            parser.error(f"{option_string} may be supplied only once")
        setattr(namespace, self.dest, values)


class _StoreTrueOnce(argparse.Action):
    """Reject a repeated boolean publication flag instead of absorbing it."""

    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is not False:
            parser.error(f"{option_string} may be supplied only once")
        setattr(namespace, self.dest, True)


def _exact_sha(value: str) -> str:
    if _SHA_RE.fullmatch(value) is None:
        raise argparse.ArgumentTypeError(
            "expected SHA must contain exactly 40 lowercase hexadecimal characters"
        )
    return value


def _exact_digest(value: str) -> str:
    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise argparse.ArgumentTypeError(
            "expected digest must contain exactly 64 lowercase hexadecimal characters"
        )
    return value


def _gateway_transaction_id(value: str) -> str:
    if re.fullmatch(r"autonomy-[0-9a-f]{12}", value) is None:
        raise argparse.ArgumentTypeError(
            "transaction id must be exactly autonomy- plus 12 lowercase hexadecimal characters"
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
    arm.add_argument("--native-return", action="store_true",
                     help="Select the bounded native-return profile after full v5 acceptance; requires the installed Company listener.")
    arm.add_argument("--foreground-only", action="store_true",
                     help="Allow only fresh authenticated same-call cycles; keep background selection disabled across restart.")

    arm_quiesce = sub.add_parser(
        "arm-quiesce-control-uid",
        help="Quiesce only the fixed Control service UID before a receipt-gated arm.",
    )
    arm_quiesce.add_argument(
        "--expected-sha", type=_exact_sha, action=_StoreOnce, required=True
    )

    disarm = sub.add_parser("disarm", help="Converge both arm bits to false.")
    disarm.add_argument(
        "--expected-sha", type=_exact_sha, action=_StoreOnce, required=True
    )

    # The CEO-submit operation domain: root-only, bounded to the release identity
    # and to nothing else.  No Gate B receipt, no credential, no path and no label
    # is caller-selectable here -- the CEO sink is armed from the installed
    # release and the dedicated App binding alone.
    ceo_status = sub.add_parser(
        "ceo-submit-status", help="Read back the CEO-submit sink state (read-only)."
    )
    ceo_status.add_argument(
        "--expected-sha", type=_exact_sha, action=_StoreOnce, required=True
    )

    ceo_arm = sub.add_parser(
        "ceo-submit-arm", help="Arm only the CEO-submit sink."
    )
    ceo_arm.add_argument(
        "--expected-sha", type=_exact_sha, action=_StoreOnce, required=True
    )

    ceo_disarm = sub.add_parser(
        "ceo-submit-disarm", help="Disarm only the CEO-submit sink."
    )
    ceo_disarm.add_argument(
        "--expected-sha", type=_exact_sha, action=_StoreOnce, required=True
    )

    ceo_reconcile = sub.add_parser(
        "ceo-submit-reconcile",
        help="Reconcile one existing effect-unknown CEO-submit transaction to its archived preimage.",
    )
    ceo_reconcile.add_argument(
        "--expected-sha", type=_exact_sha, action=_StoreOnce, required=True
    )
    canary_publish = sub.add_parser(
        "dialogue-canary-publish", help="Publish one bounded, source-derived continuation grant."
    )
    canary_publish.add_argument("--expected-sha", type=_exact_sha, action=_StoreOnce, required=True)
    canary_publish.add_argument("--read-ref", action=_StoreOnce, required=True)
    canary_publish.add_argument("--validity-seconds", type=int, action=_StoreOnce, required=True)
    canary_publish.add_argument("--native-return", action="store_true",
        help="Publish the exact native grant on the existing receipt without restarting Control.")
    canary_reconcile = sub.add_parser(
        "dialogue-canary-reconcile", help="Restore one interrupted grant publication's exact preimages."
    )
    canary_reconcile.add_argument("--expected-sha", type=_exact_sha, action=_StoreOnce, required=True)
    for command in sorted(A2_DISABLE_COMMANDS):
        a2 = sub.add_parser(command, help="Prepare or reconcile the fixed unloaded A2 disable.")
        a2.add_argument("--expected-sha", type=_exact_sha, action=_StoreOnce, required=True)
    finite_stage = sub.add_parser('finite-control-stage', help='Stage the fixed finite definition while stopped and disarmed.')
    finite_stage.add_argument('--expected-sha', type=_exact_sha, action=_StoreOnce, required=True)
    finite_stage.add_argument('--expected-control-sha256', action=_StoreOnce, required=True)
    finite_reconcile = sub.add_parser('finite-control-stage-reconcile', help='Prove an already-published finite stage without replay.')
    finite_reconcile.add_argument('--expected-sha', type=_exact_sha, action=_StoreOnce, required=True)
    for command in ('paid-control-stage','paid-control-stage-reconcile'):
        paid=sub.add_parser(command,help='Stage or reconcile the qualified disarmed paid source.')
        paid.add_argument('--expected-sha',type=_exact_sha,action=_StoreOnce,required=True)
        paid.add_argument('--expected-definition-sha256',action=_StoreOnce,required=True)
        if command=='paid-control-stage':
            paid.add_argument('--expected-control-sha256',action=_StoreOnce,required=True)
    # The OS gateway publication domain: two closed verbs on the ONE existing
    # transaction owner.  Every argument is a bounded digest or the original
    # transaction id; no path, account, label, port, grant text or verified
    # boolean is ever caller selectable here.
    gateway_publish = sub.add_parser(
        "publish-os-gateway",
        help="Publish the OS gateway through the existing transaction owner.",
    )
    gateway_publish.add_argument(
        "--expected-sha", type=_exact_sha, action=_StoreOnce, required=True
    )
    gateway_publish.add_argument(
        "--expected-bundle-digest", type=_exact_digest, action=_StoreOnce, required=True
    )
    gateway_publish.add_argument(
        "--expected-mcp-config-sha256",
        type=_exact_digest,
        action=_StoreOnce,
        required=True,
    )
    gateway_publish.add_argument(
        "--expected-mcp-plist-sha256",
        type=_exact_digest,
        action=_StoreOnce,
        required=True,
    )
    gateway_publish.add_argument(
        "--expected-grant-sha256", type=_exact_digest, action=_StoreOnce
    )
    gateway_publish.add_argument(
        "--expected-grant-absent", action=_StoreTrueOnce, nargs=0, default=False
    )
    gateway_reconcile = sub.add_parser(
        "reconcile-os-gateway",
        help="Prove one interrupted OS gateway publication to its retained postimages.",
    )
    gateway_reconcile.add_argument(
        "--expected-sha", type=_exact_sha, action=_StoreOnce, required=True
    )
    gateway_reconcile.add_argument(
        "--expected-bundle-digest", type=_exact_digest, action=_StoreOnce, required=True
    )
    gateway_reconcile.add_argument(
        "--transaction-id",
        type=_gateway_transaction_id,
        action=_StoreOnce,
        required=True,
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


_NATIVE_QUOTA_SUFFIX = ".native-return"


def _require_native_preselection(control: Mapping[str, Any]) -> None:
    """Only the accepted readonly composition can enter native arm."""
    company = control.get("company_consultation")
    quota = control.get("coo_operator_quota_class")
    if (control.get("coo_operator_model_alias") != "coo.operator.readonly"
            or control.get("dialogue_wake_canary_activation") is not None
            or type(company) is not dict or company.get("armed") is not True
            or company.get("native_return_armed", False) is not False
            or not isinstance(quota, str)
            or re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,48}", quota) is None
            or quota.endswith(_NATIVE_QUOTA_SUFFIX)):
        raise ArmAdmissionError("native_selection_invalid")


def _native_selection_matches(control: Mapping[str, Any], native_return: bool) -> bool:
    company = control.get("company_consultation", {})
    if type(company) is not dict:
        return False
    selected = control.get("coo_operator_model_alias") == "coo.operator.native-return"
    flag = company.get("native_return_armed", False)
    if type(flag) is not bool or selected != flag or selected != native_return:
        return False
    if selected:
        quota = control.get("coo_operator_quota_class")
        return (isinstance(quota, str) and quota.endswith(_NATIVE_QUOTA_SUFFIX)
                and re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,48}",
                                 quota[:-len(_NATIVE_QUOTA_SUFFIX)]) is not None
                and company.get("armed") is True)
    return True


def derive_candidate_configs(
    configs: ConfigEvidence, *, armed: bool, native_return: bool = False,
    foreground_only: bool = False,
) -> CandidateConfigs:
    control_value = copy.deepcopy(dict(configs.control))
    worker_value = copy.deepcopy(dict(configs.worker))
    if (
        not isinstance(control_value.get("coo_autonomy_armed"), bool)
        or not isinstance(control_value.get("coo_operator_harness_armed"), bool)
        or not isinstance(worker_value.get("operator_harness_armed"), bool)
    ):
        raise ArmTransactionError("arm_rolled_back")
    if type(native_return) is not bool or (native_return and not armed):
        raise ArmAdmissionError("native_selection_invalid")
    if (type(foreground_only) is not bool or (foreground_only and not armed)
            or (foreground_only and native_return)):
        raise ArmAdmissionError("native_selection_invalid")
    if native_return:
        _require_native_preselection(control_value)
        control_value["coo_operator_model_alias"] = "coo.operator.native-return"
        # The incumbent registry refuses mutating an existing quota policy.
        # A reversible, distinct selector preserves the accepted readonly class.
        control_value["coo_operator_quota_class"] += _NATIVE_QUOTA_SUFFIX
        control_value["company_consultation"]["native_return_armed"] = True
    elif control_value.get("coo_operator_model_alias") == "coo.operator.native-return":
        if not _native_selection_matches(control_value, True):
            raise ArmAdmissionError("native_selection_invalid")
        control_value["coo_operator_model_alias"] = "coo.operator.readonly"
        control_value["coo_operator_quota_class"] = control_value["coo_operator_quota_class"][:-len(_NATIVE_QUOTA_SUFFIX)]
        control_value["company_consultation"]["native_return_armed"] = False
    elif not _native_selection_matches(control_value, False):
        raise ArmAdmissionError("native_selection_invalid")
    control_value["coo_autonomy_armed"] = armed
    control_value["coo_operator_harness_armed"] = armed
    if foreground_only or "coo_foreground_only" in control_value:
        control_value["coo_foreground_only"] = foreground_only
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



def _ceo_submit_preimage(configs: ConfigEvidence) -> CandidateConfigs:
    """Rollback restores archived bytes; it is not a fresh arm transition."""
    return CandidateConfigs(
        control=copy.deepcopy(dict(configs.control)),
        worker=copy.deepcopy(dict(configs.worker)),
        control_bytes=configs.control_bytes or encode_config(configs.control),
        worker_bytes=configs.worker_bytes or encode_config(configs.worker),
        control_sha256=configs.control_sha256,
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


def _ceo_submit_binding_matches_control(
    control: Mapping[str, Any], binding: ExecutiveAppBinding
) -> bool:
    """Compare all existing live-binding fields without adding receipt fields."""

    return (
        control.get("ceo_ingress_app_peer_uid") == binding.app_peer_uid
        and control.get("ceo_ingress_app_armed") is binding.app_armed
        and control.get("ceo_ingress_peer_uid") == binding.ingress_peer_uid
        and control.get("ceo_ingress_app_macro_root") == binding.app_macro_root
        and control.get("ceo_ingress_socket_path") == binding.ingress_socket_path
        and control.get("ceo_ingress_launchd_socket_name") == binding.launchd_socket_name
    )


def _ceo_submit_arm_state_refusal(
    control: Mapping[str, Any], binding: ExecutiveAppBinding, *, coexistence: bool = False
) -> str | None:
    """Return the first current-evidence ARM authority refusal, in fixed order.

    R81: a self-digested receipt is correlation evidence, not authority. ARM
    and sink/status readback therefore consume the same current-state owner.
    """

    if binding.app_peer_user != EXECUTIVE_APP_USER:
        return "app_peer_invalid"
    if binding.binding_valid is not True:
        return "app_binding_invalid"
    if binding.acl_valid is not True:
        return "app_acl_invalid"
    if binding.topology_valid is not True:
        return "app_topology_invalid"
    if control.get("ceo_ingress_app_armed") is not True:
        return "ceo_ingress_app_unarmed"
    app_peer_uid = control.get("ceo_ingress_app_peer_uid")
    ingress_peer_uid = control.get("ceo_ingress_peer_uid")
    if (
        type(app_peer_uid) is not int
        or type(ingress_peer_uid) is not int
        or type(binding.app_peer_uid) is not int
        or type(binding.ingress_peer_uid) is not int
        or app_peer_uid == ingress_peer_uid
        or binding.app_peer_uid != app_peer_uid
    ):
        return "ceo_ingress_separation_invalid"
    if not _ceo_submit_binding_matches_control(control, binding):
        return "app_binding_invalid"
    if control.get("coo_autonomy_armed") is not coexistence:
        return "coo_autonomy_armed"
    if control.get("coo_operator_harness_armed") is not coexistence:
        return "coo_operator_harness_armed"
    return None


def _ceo_submit_arm_state_authorized(
    control: Mapping[str, Any], binding: ExecutiveAppBinding, *, coexistence: bool = False
) -> bool:
    """Whether current canonical evidence authorizes CEO-submit ARM/readback."""

    return _ceo_submit_arm_state_refusal(control, binding, coexistence=coexistence) is None


def _full_autonomy_flags(configs: ConfigEvidence) -> bool:
    return (
        configs.control.get("coo_autonomy_armed") is True
        and configs.control.get("coo_operator_harness_armed") is True
        and configs.worker.get("operator_harness_armed") is True
    )


def coexistence_receipt_eligible(
    configs: ConfigEvidence, receipt: Mapping[str, Any] | None,
    metadata: ReceiptMetadata, *, expected_sha: str, now: datetime | None = None,
) -> bool:
    """Prove both current config bytes against existing full-arm authority."""
    if not _full_autonomy_flags(configs) or not isinstance(receipt, Mapping):
        return False
    try:
        binding = validate_runtime_guard_document(
            receipt, metadata=metadata, role="control",
            own_config_sha256=configs.control_sha256, release_sha=expected_sha, now=now,
        )
        return binding.worker_config_sha256 == configs.worker_sha256
    except (AutonomyRefusal, TypeError, ValueError):
        return False


def rebind_coexistence_receipt(
    transaction: TransactionContext, receipt: Mapping[str, Any]
) -> dict[str, Any]:
    """Change config correlation only; never refresh readiness or authority."""
    require_ceo_submit_preservation(transaction.prior_configs, transaction.candidates)
    value = copy.deepcopy(dict(receipt))
    value.update(
        control_config_sha256=transaction.candidates.control_sha256,
        prior_control_config_sha256=transaction.prior_configs.control_sha256,
        transaction_id=transaction.transaction_id,
    )
    return value


def ceo_submit_projection(
    transaction: TransactionContext,
    admission: CeoSubmitAdmission,
    *,
    armed: bool,
) -> dict[str, Any]:
    """The CLOSED authority-bearing projection of the CEO-submit postimage.

    R76 safe-direction repair: the projection is a FAITHFUL FACT-CARRIER.  It
    records the postimage authority values and the host-observed App binding
    facts as they stand, so DISARM and rollback can ALWAYS project a receipt
    even when the App transport is absent or has drifted away -- the state in
    which removing or restoring CEO-submit authority matters most.  ARM never
    reaches this function with a mismatched live binding because its admission
    gate chain (in ``evaluate_ceo_submit_arm_admission``) refuses with a typed
    pre-write refusal and zero writes; the projection's old
    ``app_binding_invalid`` refusal made DISARM and rollback unreachable when
    transport was absent.

    Only the declared authority fields and host-observed App binding facts are
    rebound from current evidence. ``transaction_id`` is a correlation label:
    it is required to be well formed and equal in the outer document and
    projection, but it is not an authority source. The whole control document
    is never bound, so an unrelated later COO field cannot invalidate the receipt.
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


def validate_ceo_submit_receipt_document(
    receipt: Mapping[str, Any], *, armed: bool
) -> bool:
    """Validate receipt shape without treating self-described facts as authority.

    ``transaction_id`` is a correlation label only: the outer and projected
    values must be well formed and equal. Current authority is asserted later
    from canonical evidence by ``_ceo_submit_arm_state_authorized``.
    """

    if not isinstance(receipt, Mapping) or set(receipt) != _CEO_SUBMIT_RECEIPT_FIELDS:
        return False
    expected_state = "CEO_SUBMIT_ARMED" if armed else "CEO_SUBMIT_DISARMED"
    expected_operation = "CEO_SUBMIT_ARM" if armed else "CEO_SUBMIT_DISARM"
    if (
        receipt.get("schema_version") != CEO_SUBMIT_RECEIPT_SCHEMA
        or receipt.get("state") != expected_state
        or receipt.get("operation") != expected_operation
    ):
        return False
    projection = receipt.get("projection")
    if (
        not isinstance(projection, Mapping)
        or set(projection) != _CEO_SUBMIT_PROJECTION_FIELDS
    ):
        return False
    if projection.get("ceo_submit_armed") is not armed:
        return False
    transaction_id = receipt.get("transaction_id")
    projected_transaction_id = projection.get("transaction_id")
    if (
        not isinstance(transaction_id, str)
        or _CEO_SUBMIT_TRANSACTION_RE.fullmatch(transaction_id) is None
        or transaction_id != projected_transaction_id
    ):
        return False
    if any(
        not isinstance(projection.get(field), str)
        or _SHA_RE.fullmatch(projection[field]) is None
        for field in ("release_sha", "installed_sha")
    ):
        return False
    observed_at = receipt.get("observed_at")
    if not isinstance(observed_at, str):
        return False
    try:
        parsed_observed_at = datetime.strptime(
            observed_at, "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return False
    if _receipt_timestamp(parsed_observed_at) != observed_at:
        return False
    if receipt.get("tool_version") != TOOL_VERSION:
        return False
    try:
        expected_digest = ceo_submit_projection_digest(projection)
    except (TypeError, ValueError):
        return False
    return receipt.get("projection_digest") == expected_digest


def build_ceo_submit_receipt(
    transaction: TransactionContext,
    admission: CeoSubmitAdmission,
    *,
    armed: bool,
    now: datetime,
) -> dict[str, Any]:
    projection = ceo_submit_projection(transaction, admission, armed=armed)
    receipt = {
        "schema_version": CEO_SUBMIT_RECEIPT_SCHEMA,
        "state": "CEO_SUBMIT_ARMED" if armed else "CEO_SUBMIT_DISARMED",
        "operation": "CEO_SUBMIT_ARM" if armed else "CEO_SUBMIT_DISARM",
        "projection": dict(projection),
        "projection_digest": ceo_submit_projection_digest(projection),
        "transaction_id": transaction.transaction_id,
        "observed_at": _receipt_timestamp(now),
        "tool_version": TOOL_VERSION,
    }
    if not validate_ceo_submit_receipt_document(receipt, armed=armed):
        raise CeoSubmitAdmissionError("ceo_submit_config_schema_drift")
    return receipt


def ceo_submit_effect_unknown_sticky(
    marker_operation: str | None, requested_operation: str
) -> bool:
    """R9 stickiness: ambiguity is EFFECT_UNKNOWN for the SAME operation only.

    ``marker_operation`` is the operation named by an extant (therefore
    incomplete) transaction marker -- ``None`` when the owner is free.  A marker
    for this exact CEO-submit verb means a prior attempt of this verb may already
    have written: the ambiguity is sticky and the operation must never be
    re-attempted.  A marker for any OTHER operation (a COO ``ARM``/``DISARM``, or
    the other CEO-submit verb) is a different ambiguity and stays the typed HOLD.
    """

    return (
        marker_operation in CEO_SUBMIT_OPERATIONS
        and marker_operation == requested_operation
    )


def _hold_on_occupied_global_owner(host: CeoSubmitTransactionHost) -> None:
    """R18-B4: refuse with ZERO writes unless the ONE global owner is FREE.

    ``incomplete_transaction_operation()`` answers ``None`` both when the owner
    is genuinely free AND when an extant marker cannot be classified, so it can
    never on its own prove the owner free.  The EXISTING
    ``require_transaction_absent()`` probe is what refuses an occupied owner: a
    ``CEO_SUBMIT_ARM`` still in flight before its control replace, a COO
    ``ARM``/``DISARM``, or an occupied-but-unclassifiable marker all become the
    existing typed ``ceo_submit_transaction_incomplete`` HOLD.  This is a stat
    probe on the one existing ``AUTONOMY_TRANSACTION``: no second lock, no
    candidate, no receipt, no byte.
    """

    try:
        host.require_transaction_absent()
    except (HostControlError, ArmAdmissionError) as exc:
        raise CeoSubmitAdmissionError("ceo_submit_transaction_incomplete") from exc


def require_ceo_submit_preservation(
    prior: ConfigEvidence, candidates: CandidateConfigs
) -> None:
    """R9 preservation: only ``ceo_submit_armed`` may move; worker bytes never.

    A CEO-submit candidate that also clears COO authority, drops (or adds) a key,
    or rewrites the worker document would regress the UID458 App install/ACL and
    the unrelated control values.  Any such delta is refused before any write.
    """

    if set(prior.control) != set(candidates.control):
        raise CeoSubmitAdmissionError("app_install_would_regress")
    changed = {
        key
        for key in prior.control
        if prior.control[key] != candidates.control[key]
    }
    if changed != {"ceo_submit_armed"}:
        raise CeoSubmitAdmissionError("app_install_would_regress")
    if (
        candidates.worker_bytes != prior.worker_bytes
        or candidates.worker_sha256 != prior.worker_sha256
    ):
        raise CeoSubmitAdmissionError("app_install_would_regress")


def ceo_submit_sink_eligible(
    *,
    control_config: Mapping[str, Any],
    worker_config: Mapping[str, Any],
    worker_config_sha256: str,
    receipt: Mapping[str, Any] | None,
    binding: ExecutiveAppBinding,
    expected_sha: str,
    installed_sha: str,
    control_config_sha256: str | None = None,
    autonomy_receipt: Mapping[str, Any] | None = None,
    autonomy_metadata: ReceiptMetadata | None = None,
    now: datetime | None = None,
) -> bool:
    """Shared eligibility predicate for root status and runtime host admission.

    Eligible ONLY when the present control and worker documents, exact installed
    release, live host-observed App binding, and sealed ARM receipt independently
    re-derive every authority-bearing projection field.  Unrelated control keys
    remain outside that closed projection.
    """

    if not isinstance(control_config, Mapping) or control_config.get(
        "ceo_submit_armed"
    ) is not True:
        return False
    if not isinstance(worker_config, Mapping):
        return False
    worker_armed = worker_config.get("operator_harness_armed")
    coexistence = False
    if worker_armed is True and autonomy_metadata is not None:
        coexistence = coexistence_receipt_eligible(
            ConfigEvidence(control=control_config, worker=worker_config,
                           control_sha256=control_config_sha256 or "",
                           worker_sha256=worker_config_sha256),
            autonomy_receipt, autonomy_metadata, expected_sha=expected_sha, now=now,
        )
    if worker_armed is not False and not coexistence:
        return False
    if (
        not isinstance(expected_sha, str)
        or _SHA_RE.fullmatch(expected_sha) is None
        or not isinstance(installed_sha, str)
        or _SHA_RE.fullmatch(installed_sha) is None
        or expected_sha != installed_sha
    ):
        return False
    if (
        not isinstance(worker_config_sha256, str)
        or len(worker_config_sha256) != 64
    ):
        return False
    if not validate_ceo_submit_receipt_document(receipt, armed=True):
        return False
    projection = receipt["projection"]
    if projection["installed_sha"] != installed_sha:
        return False
    projection_digest = receipt["projection_digest"]
    if not isinstance(binding, ExecutiveAppBinding) or not binding.present:
        return False
    if not _ceo_submit_arm_state_authorized(control_config, binding, coexistence=coexistence):
        return False
    recomputed = {field: control_config[field] for field in _CEO_SUBMIT_CONTROL_FIELDS}
    if set(recomputed) != _CEO_SUBMIT_CONTROL_FIELDS:
        return False
    recomputed.update(
        {
            "release_sha": expected_sha,
            "installed_sha": installed_sha,
            "app_peer_user": binding.app_peer_user,
            "app_binding_valid": binding.binding_valid,
            "app_acl_valid": binding.acl_valid,
            "app_topology_valid": binding.topology_valid,
            "worker_operator_harness_armed": worker_armed,
            "worker_config_sha256": worker_config_sha256,
            "transaction_id": receipt["transaction_id"],
        }
    )
    if set(recomputed) != _CEO_SUBMIT_PROJECTION_FIELDS:
        return False
    try:
        digest = ceo_submit_projection_digest(recomputed)
    except (ArmTransactionError, TypeError, ValueError):
        return False
    if (
        projection["worker_operator_harness_armed"] is not worker_armed
        or projection["worker_operator_harness_armed"] is not coexistence
    ):
        return False
    if worker_config_sha256 != projection["worker_config_sha256"]:
        return False
    if projection_digest != digest:
        return False
    return True


def require_ceo_submit_runtime_admission(
    control_config: Mapping[str, Any], *, own_config_sha256: str,
    now: datetime | None = None,
) -> None:
    """Control-side guard: read only the two public root-sealed receipts.

    The service composition separately revalidates its current config/attestation
    and dedicated App peer. The worker config stays private to its own principal.
    """
    try:
        try:
            AUTONOMY_TRANSACTION.lstat()
        except FileNotFoundError:
            pass
        else:
            raise ValueError("transaction occupied")
        receipt, metadata = load_receipt_file(CEO_SUBMIT_RECEIPT)
        if metadata != ReceiptMetadata(uid=0, gid=0, mode=0o444, nlink=1,
                                       is_regular=True, is_symlink=False, has_acl=False):
            raise ValueError("unsealed receipt")
        if not validate_ceo_submit_receipt_document(receipt, armed=True):
            raise ValueError("invalid receipt")
        projection = receipt["projection"]
        binding = ExecutiveAppBinding(
            present=True, app_peer_user=projection["app_peer_user"],
            app_peer_uid=projection["ceo_ingress_app_peer_uid"],
            app_armed=projection["ceo_ingress_app_armed"],
            app_macro_root=projection["ceo_ingress_app_macro_root"],
            ingress_peer_uid=projection["ceo_ingress_peer_uid"],
            ingress_socket_path=projection["ceo_ingress_socket_path"],
            launchd_socket_name=projection["ceo_ingress_launchd_socket_name"],
            binding_valid=projection["app_binding_valid"],
            acl_valid=projection["app_acl_valid"], topology_valid=projection["app_topology_valid"],
        )
        full_receipt, full_metadata = (None, None)
        if projection["worker_operator_harness_armed"] is True:
            full_receipt, full_metadata = load_receipt_file(AUTONOMY_RECEIPT)
        if not ceo_submit_sink_eligible(
            control_config=control_config,
            worker_config={"operator_harness_armed": projection["worker_operator_harness_armed"]},
            worker_config_sha256=projection["worker_config_sha256"], receipt=receipt,
            binding=binding, expected_sha=str(control_config["proof_base_sha"]),
            installed_sha=projection["installed_sha"], control_config_sha256=own_config_sha256,
            autonomy_receipt=full_receipt, autonomy_metadata=full_metadata, now=now,
        ):
            raise ValueError("receipt not eligible")
    except Exception as exc:
        raise CeoSubmitAdmissionError("ceo_submit_transaction_incomplete") from exc


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

    if (type(request.native_return) is not bool or type(request.foreground_only) is not bool
            or (request.foreground_only and request.native_return)):
        raise ArmAdmissionError("native_selection_invalid")
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
    if request.native_return:
        _require_native_preselection(configs.control)
        host.require_native_listener(configs)
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
    if (type(request.native_return) is not bool or type(request.foreground_only) is not bool
            or (request.foreground_only and request.native_return)):
        raise ArmAdmissionError("native_selection_invalid")
    existing = host.existing_arm(request, now=now)
    if existing is not None:
        return existing
    admission = evaluate_arm_admission(host, request, now=now)
    transaction = TransactionContext(
        transaction_id=host.new_transaction_id(),
        expected_sha=request.expected_sha,
        prior_configs=admission.configs,
        candidates=derive_candidate_configs(admission.configs, armed=True,
                                            native_return=request.native_return,
                                            foreground_only=request.foreground_only),
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
    except ArmAdmissionError:
        # A marker that appeared between the read-only admission check and the
        # atomic mkdir belongs to another root transaction. Never "recover"
        # it through this operation's rollback carrier.
        raise
    except TransactionOwnershipError:
        # A failed begin may have left durable marker evidence, but without the
        # execution owner this process may neither stop services nor roll back.
        raise
    except TransactionEffectUnknown:
        # Publication or another owner boundary may already have taken effect.
        # Preserve its identity and exclusion for explicit reconciliation;
        # uncertainty is not permission to stop services or manufacture rollback.
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
    try:
        host.complete_transaction(transaction)
    except TransactionEffectUnknown:
        raise
    except Exception as exc:
        # Publication/terminal cleanup has started; rollback cannot erase that
        # boundary and publish again, even if cleanup raises an ordinary error.
        raise TransactionEffectUnknown() from exc
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
    try:
        prior_configs = host.begin_disarm(expected_sha, transaction_id)
        host.stop_services(expected_sha)
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
    except TransactionEffectUnknown:
        # A lost publication/ownership acknowledgement is not an instruction
        # to rewrite the configs, receipt or original journal through rollback.
        raise
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
    try:
        # Closeout may publish the observation and then remove journal files.
        # Any failure here (including an ordinary cleanup OSError) is ambiguous;
        # never enter rollback, which itself calls complete_transaction again.
        host.complete_transaction(transaction)
    except TransactionEffectUnknown:
        raise
    except Exception as exc:
        raise TransactionEffectUnknown() from exc
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
    # IDENTITY BY NAME, never by uid literal (D8): the host-observed App peer is
    # pinned to its dedicated account here; the uid identities are structural
    # facts of the composed config and are checked at the separation gate below.
    if binding.app_peer_user != EXECUTIVE_APP_USER:
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
    # R68 (item 1): UID458 App transport/peer ADMISSION is what gates ARM, not
    # CEO-submit AUTHORITY.  The governed App composition that H3 arms from
    # REQUIRES ``ceo_ingress_app_armed`` to be True.  A False value -- or a
    # non-boolean (schema drift) value that is not strictly True -- is a typed
    # pre-write refusal with the new code ``ceo_ingress_app_unarmed``.  The
    # check stays in the SAME fixed-order position (between the structural
    # binding/ACL/topology gates and the UID-vs-separation structural gate)
    # so a refusal lands BEFORE any write, marker, phase, or receipt.
    if separation.ceo_ingress_app_armed is not True:
        raise CeoSubmitAdmissionError("ceo_ingress_app_unarmed")
    # R9 separation invariant, read from the CONTROL CONFIG and never from a
    # source literal: both ingress peers are uids, they are DISTINCT (the
    # UID452 C1/ingress peer is not the UID458 App peer), and the host-observed
    # App peer agrees with the config's declared App peer.  This check runs
    # BEFORE the R76 helper so a peer-identity mismatch refuses the typed
    # ``ceo_ingress_separation_invalid`` code (the structural separation gate
    # is the one and only place that code is raised); the helper that follows
    # keeps the remaining live-binding facts (socket path, launchd socket
    # name, App macro root, App transport) in one comparison.
    app_peer_uid = separation.ceo_ingress_app_peer_uid
    ingress_peer_uid = separation.ceo_ingress_peer_uid
    if (
        type(app_peer_uid) is not int
        or type(ingress_peer_uid) is not int
        or app_peer_uid == ingress_peer_uid
        or binding.app_peer_uid != app_peer_uid
    ):
        raise CeoSubmitAdmissionError("ceo_ingress_separation_invalid")
    # R81 authority parity: one current-evidence owner is consumed by both
    # ARM and sink/status readback. The earlier gates preserve the existing
    # typed refusal order before config loading; this assertion catches any
    # disagreement between canonical control evidence and the live binding.
    coexistence = _full_autonomy_flags(configs) and host.proves_safe_coexistence(configs)
    authority_refusal = _ceo_submit_arm_state_refusal(configs.control, binding, coexistence=coexistence)
    if authority_refusal is not None:
        raise CeoSubmitAdmissionError(authority_refusal)
    if separation.coo_autonomy_armed and not coexistence:
        raise CeoSubmitAdmissionError("coo_autonomy_armed")
    if separation.coo_operator_harness_armed and not coexistence:
        raise CeoSubmitAdmissionError("coo_operator_harness_armed")
    if separation.worker_operator_harness_armed and not coexistence:
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

    # R9 stickiness: a marker for THIS verb means a prior attempt may already have
    # written.  Never retry it and never silently succeed; stay EFFECT_UNKNOWN.
    if ceo_submit_effect_unknown_sticky(
        host.incomplete_transaction_operation(), "CEO_SUBMIT_ARM"
    ):
        raise TransactionEffectUnknown()
    admission = evaluate_ceo_submit_arm_admission(host, request, now=now)
    configs = admission.configs
    if not isinstance(configs, ConfigEvidence):
        raise CeoSubmitAdmissionError("ceo_submit_config_schema_drift")
    candidates = derive_ceo_submit_candidate(configs, armed=True)
    require_ceo_submit_preservation(configs, candidates)
    transaction = TransactionContext(
        transaction_id=host.new_transaction_id(),
        expected_sha=request.expected_sha,
        prior_configs=configs,
        candidates=candidates,
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
        if _full_autonomy_flags(configs):
            host.rebind_full_autonomy_receipt(transaction)
        host.replace_control_config(transaction)
        receipt = build_ceo_submit_receipt(transaction, admission, armed=True, now=now)
        host.write_ceo_submit_receipt(transaction, receipt)
        host.reconcile_control_service(request.expected_sha)
        host.prove_control_admission_bound(
            request.expected_sha, transaction.candidates.control_sha256
        )
        host.complete_transaction(transaction)
    except TransactionEffectUnknown:
        # An effect boundary explicitly classified UNKNOWN keeps this transaction
        # marker sticky. Do not convert it into an automatic rollback/retry.
        raise
    except Exception as exc:
        try:
            rollback = dataclasses.replace(
                transaction,
                candidates=_ceo_submit_preimage(transaction.prior_configs),
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


def evaluate_ceo_submit_disarm_admission(
    host: CeoSubmitTransactionHost, request: CeoSubmitRequest, *, now: datetime
) -> CeoSubmitAdmission:
    """Evaluate every CEO-submit disarm gate in fixed order, with no mutation.

    The fixed order is: root, installed release identity, config read (which may
    short-circuit into a read-only REPLAY, but only across a proven-free global
    transaction owner), separation/coexistence, the App binding facts, then the
    extant-transaction HOLD.  Every refusal happens
    before the lock is acquired and before any byte is written.
    """

    require_root_privilege(host.effective_uid())
    if _SHA_RE.fullmatch(request.expected_sha) is None:
        raise CeoSubmitAdmissionError("release_identity_mismatch")
    installed_sha = host.require_exact_install(request.expected_sha)
    if installed_sha != request.expected_sha:
        raise CeoSubmitAdmissionError("release_identity_mismatch")
    configs = host.load_ceo_submit_configs(request.expected_sha)
    armed_flag = dict(configs.control).get("ceo_submit_armed")
    if not isinstance(armed_flag, bool):
        raise CeoSubmitAdmissionError("ceo_submit_config_schema_drift")
    if armed_flag is False:
        # R18-B4: the already-disarmed REPLAY may only be taken across a FREE
        # global owner.  Reconcile the ONE existing AUTONOMY_TRANSACTION first:
        # a marker naming THIS verb stays the sticky EFFECT_UNKNOWN, and any
        # DIFFERENT extant operation -- a CEO_SUBMIT_ARM still in flight before
        # its control replace, a COO ARM/DISARM, or an occupied-but-
        # unclassifiable marker -- is the existing typed HOLD with zero writes.
        # Without this the replay answers CEO_SUBMIT_DISARMED while the in-flight
        # arm goes on to arm the sink after that success response.
        if ceo_submit_effect_unknown_sticky(
            host.incomplete_transaction_operation(), "CEO_SUBMIT_DISARM"
        ):
            raise TransactionEffectUnknown()
        _hold_on_occupied_global_owner(host)

        # REPLAY, not a refusal.  R9: "no independent receipt rewrite" -- the
        # existing receipt keeps its bytes, its object identity and its digest.
        # Nothing past this point is read: no lock, no candidate, no write.
        return CeoSubmitAdmission(
            expected_sha=request.expected_sha,
            installed_sha=installed_sha,
            replayed=True,
            replay_transaction_id=_sealed_ceo_submit_transaction_id(
                host.existing_ceo_submit_receipt()
            ),
        )
    separation = host.ceo_submit_separation(configs)
    if any((separation.coo_autonomy_armed, separation.coo_operator_harness_armed,
            separation.worker_operator_harness_armed)) and not host.proves_safe_coexistence(configs):
        # Later full autonomy is armed: refuse unless the SOURCE proves that
        # coexistence is safe.  The default is refuse.
        raise CeoSubmitAdmissionError("full_autonomy_armed_unsafe_coexistence")
    binding = host.executive_app_binding()
    # ASYMMETRY (R9): an absent or invalid App binding must NOT block disarm --
    # disarm is the safe direction.  The binding facts are still recorded in the
    # receipt projection, which is why no binding gate appears here.
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


def _sealed_ceo_submit_transaction_id(receipt: Mapping[str, Any] | None) -> str | None:
    """The transaction id of the sealed receipt, or None.  Read-only."""

    if not isinstance(receipt, Mapping):
        return None
    if receipt.get("schema_version") != CEO_SUBMIT_RECEIPT_SCHEMA:
        return None
    transaction_id = receipt.get("transaction_id")
    if not isinstance(transaction_id, str):
        return None
    if re.fullmatch(r"autonomy-[0-9a-f]{12}", transaction_id) is None:
        return None
    return transaction_id


def execute_ceo_submit_disarm(
    host: CeoSubmitTransactionHost, request: CeoSubmitRequest, *, now: datetime
) -> TransactionResult:
    """Disarm exactly the CEO-submit sink inside the one serialized transaction."""

    # R9 stickiness, before anything else: a marker for THIS verb is ambiguity
    # sticky to this operation, so it is neither replayed nor retried.
    if ceo_submit_effect_unknown_sticky(
        host.incomplete_transaction_operation(), "CEO_SUBMIT_DISARM"
    ):
        raise TransactionEffectUnknown()
    admission = evaluate_ceo_submit_disarm_admission(host, request, now=now)
    if admission.replayed:
        return TransactionResult(
            state="CEO_SUBMIT_DISARMED",
            status="CEO_SUBMIT_DISARMED",
            transaction_id=admission.replay_transaction_id,
            replayed=True,
        )
    configs = admission.configs
    if not isinstance(configs, ConfigEvidence):
        raise CeoSubmitAdmissionError("ceo_submit_config_schema_drift")
    candidates = derive_ceo_submit_candidate(configs, armed=False)
    require_ceo_submit_preservation(configs, candidates)
    transaction = TransactionContext(
        transaction_id=host.new_transaction_id(),
        expected_sha=request.expected_sha,
        prior_configs=configs,
        candidates=candidates,
        admission=None,
    )
    try:
        host.begin_ceo_submit_transaction(transaction, operation="CEO_SUBMIT_DISARM")
    except CeoSubmitAdmissionError:
        # A marker that appeared between the read-only admission check and the
        # atomic mkdir belongs to another root transaction.  Never "recover" it
        # through this operation's rollback carrier.
        raise
    try:
        host.write_candidates(transaction)
        host.validate_candidates(transaction)
        if _full_autonomy_flags(configs):
            host.rebind_full_autonomy_receipt(transaction)
        host.replace_control_config(transaction)
        receipt = build_ceo_submit_receipt(transaction, admission, armed=False, now=now)
        host.write_ceo_submit_receipt(transaction, receipt)
        host.reconcile_control_service(request.expected_sha)
        host.prove_control_admission_bound(
            request.expected_sha, transaction.candidates.control_sha256
        )
        host.complete_transaction(transaction)
    except TransactionEffectUnknown:
        # An effect boundary explicitly classified UNKNOWN keeps this transaction
        # marker sticky. Do not convert it into an automatic rollback/retry.
        raise
    except Exception as exc:
        try:
            rollback = dataclasses.replace(
                transaction,
                candidates=_ceo_submit_preimage(transaction.prior_configs),
            )
            host.rollback_ceo_submit(
                rollback,
                build_ceo_submit_receipt(rollback, admission, armed=True, now=now),
            )
        except Exception as rollback_exc:
            raise TransactionEffectUnknown() from rollback_exc
        raise ArmTransactionError("disarm_recovered") from exc
    return TransactionResult(
        state="CEO_SUBMIT_DISARMED",
        status="CEO_SUBMIT_DISARMED",
        transaction_id=transaction.transaction_id,
        replayed=False,
    )


def evaluate_ceo_submit_status(
    host: CeoSubmitTransactionHost, request: CeoSubmitRequest
) -> TransactionResult:
    """Read-only CEO-submit readback: no lock, no write, no receipt rewrite.

    R9's source tests must kill the manual-config shortcut, so an armed FLAG is
    not reported as armed on its own: the sealed receipt must still bind the
    present config and the live App binding through
    ``ceo_submit_sink_eligible``.  A hand-edited ``ceo_submit_armed: true`` with
    no sealed receipt reads back CEO_SUBMIT_ARMED_UNBOUND, never CEO_SUBMIT_ARMED.
    """

    require_root_privilege(host.effective_uid())
    if _SHA_RE.fullmatch(request.expected_sha) is None:
        raise CeoSubmitAdmissionError("release_identity_mismatch")
    installed_sha = host.require_exact_install(request.expected_sha)
    if installed_sha != request.expected_sha:
        raise CeoSubmitAdmissionError("release_identity_mismatch")
    # R18-B4: a verified CEO snapshot is never read THROUGH an occupied global
    # owner.  Same-CEO-operation ambiguity keeps its EFFECT_UNKNOWN; any
    # DIFFERENT occupied owner -- a COO ARM/DISARM or an unclassifiable marker --
    # returns the existing typed unverified/HOLD through that same owner.
    if host.incomplete_transaction_operation() in CEO_SUBMIT_OPERATIONS:
        raise TransactionEffectUnknown()
    _hold_on_occupied_global_owner(host)
    configs = host.load_ceo_submit_configs(request.expected_sha)
    armed_flag = dict(configs.control).get("ceo_submit_armed")
    if not isinstance(armed_flag, bool):
        raise CeoSubmitAdmissionError("ceo_submit_config_schema_drift")
    receipt = host.existing_ceo_submit_receipt()
    transaction_id = _sealed_ceo_submit_transaction_id(receipt)
    if not armed_flag:
        return TransactionResult(
            state="CEO_SUBMIT_DISARMED",
            status="CEO_SUBMIT_DISARMED",
            transaction_id=transaction_id,
            replayed=False,
        )
    full_receipt, full_metadata = None, None
    if _full_autonomy_flags(configs):
        try:
            full_receipt, full_metadata = load_receipt_file(AUTONOMY_RECEIPT)
        except AutonomyRefusal:
            pass
    eligible = ceo_submit_sink_eligible(
        control_config=configs.control,
        worker_config=configs.worker,
        worker_config_sha256=configs.worker_sha256,
        receipt=receipt,
        binding=host.executive_app_binding(),
        expected_sha=request.expected_sha,
        installed_sha=installed_sha,
        control_config_sha256=configs.control_sha256,
        autonomy_receipt=full_receipt, autonomy_metadata=full_metadata,
    )
    state = "CEO_SUBMIT_ARMED" if eligible else "CEO_SUBMIT_ARMED_UNBOUND"
    return TransactionResult(
        state=state, status=state, transaction_id=transaction_id, replayed=False
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
    def _loaded_observe_only(label: str) -> bool:
        """Return loaded/absent only when launchd proves either state.

        This helper is intentionally narrower than the historical ``_loaded``
        predicate.  The quiesce-only command must not treat a permission, IPC,
        or transient launchctl read failure as service absence before signaling
        the fixed Control UID.
        """
        completed = subprocess.run(
            ["/bin/launchctl", "print", f"system/{label}"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
        if completed.returncode == 0:
            return True
        if completed.returncode == 113:
            return False
        raise ArmAdmissionError("services_gate_failed")

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

    def effective_uid(self) -> int:
        return os.geteuid()

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
            from ops.executive_os.acceptance_maintenance import (
                MaintenanceError, validate_carry_receipt,
            )
            summary_digest = hashlib.sha256(raw).hexdigest()
            try:
                validate_carry_receipt(expected_sha, summary_digest)
            except (MaintenanceError, OSError, ValueError) as exc:
                raise ArmAdmissionError("acceptance_receipt_invalid") from exc
            return summary_digest
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

    def require_native_listener(self, config: ConfigEvidence) -> None:
        # Installation owns the listener. Arm only observes its fixed root-owned
        # launchd binding, after exact install and the full acceptance gates.
        from scripts.executive_os_phase1c import company_consultation_launchd_entry, ServiceError
        try:
            expected = company_consultation_launchd_entry(config.control)
            public_plist_mode = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH
            raw, _info = _read_root_file(
                CONTROL_PLIST, modes=frozenset({public_plist_mode}), gid=0
            )
            value = plistlib.loads(raw)
            sockets = value.get("Sockets", {})
            if (expected is None or type(sockets) is not dict
                    or sockets.get("CompanyConsultation") != expected):
                raise ArmAdmissionError("native_listener_unavailable")
        except (HostControlError, OSError, ValueError, plistlib.InvalidFileException, ServiceError) as exc:
            raise ArmAdmissionError("native_listener_unavailable") from exc
        from ops.executive_os.a2_agent_relay_enrollment import w3c_plist_configured
        if not w3c_plist_configured(release_sha=config.control.get("proof_base_sha")):
            raise ArmAdmissionError("native_relay_unavailable")

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

    def require_services_already_stopped(self) -> None:
        """Observe the fixed Control/worker labels without changing lifecycle state."""
        try:
            loaded = (
                self._loaded_observe_only(CONTROL_LABEL),
                self._loaded_observe_only(WORKER_LABEL),
            )
        except ArmAdmissionError:
            raise
        except (OSError, subprocess.SubprocessError) as exc:
            raise ArmAdmissionError("services_gate_failed") from exc
        if any(loaded):
            raise ArmAdmissionError("services_not_stopped")

    def quiesce_control_uid_for_arm(self) -> tuple[int, ...]:
        """Converge only the fixed Control service UID to zero live processes.

        This is a pre-arm cleanup action, not part of the arm admission gate.
        It never targets the worker UID (whose one attested distnoted may be
        permitted by require_service_uids_quiescent), and it accepts no
        caller-selected UID, PID, signal or timeout. The process table is the
        reconciliation source: every signal target must still be observed under
        the canonical Control UID, and success requires two consecutive empty
        observations after the final signal.
        """

        from control_plane.executive_worker_broker import _ps_pids_for_uid

        try:
            control_uid = pwd.getpwnam(CONTROL_USER).pw_uid
        except KeyError as exc:
            raise ArmAdmissionError("service_uid_process_unknown") from exc
        if control_uid <= 0:
            raise ArmAdmissionError("service_uid_process_unknown")

        try:
            before = _ps_pids_for_uid(control_uid)
        except Exception as exc:
            raise ArmAdmissionError("service_uid_process_unknown") from exc
        if not before:
            time.sleep(0.1)
            try:
                if not _ps_pids_for_uid(control_uid):
                    return ()
            except Exception as exc:
                raise ArmAdmissionError("service_uid_process_unknown") from exc

        signalled: set[int] = set()
        for signum in (signal.SIGTERM, signal.SIGKILL):
            phase_signalled: set[int] = set()
            for _ in range(50):
                try:
                    live = _ps_pids_for_uid(control_uid)
                except Exception as exc:
                    raise ArmAdmissionError("service_uid_process_unknown") from exc
                if not live:
                    time.sleep(0.1)
                    try:
                        live = _ps_pids_for_uid(control_uid)
                    except Exception as exc:
                        raise ArmAdmissionError("service_uid_process_unknown") from exc
                    if not live:
                        return tuple(sorted(signalled))
                for pid in live:
                    if pid <= 1:
                        raise ArmAdmissionError("service_uid_process_unknown")
                    if pid in phase_signalled:
                        continue
                    try:
                        os.kill(pid, signum)
                    except ProcessLookupError:
                        continue
                    except OSError as exc:
                        raise ArmAdmissionError("service_uid_process_unknown") from exc
                    phase_signalled.add(pid)
                    signalled.add(pid)
                time.sleep(0.1)

        try:
            remaining = _ps_pids_for_uid(control_uid)
        except Exception as exc:
            raise ArmAdmissionError("service_uid_process_unknown") from exc
        if remaining:
            raise ArmAdmissionError("service_uid_process_live")
        return tuple(sorted(signalled))

    def require_service_uids_quiescent(self) -> None:
        # Reuse the worker owner's saved/real/effective UID projection and exact
        # Apple launchd attribution. Process names and argv never grant an
        # exception. This gate observes only; it never sweeps or signals.
        from control_plane.executive_ambient_process import (
            AmbientClassification, AmbientProcessIdentity, DarwinDistnotedClassifier,
        )
        from control_plane.executive_worker_broker import _ps_pids_for_uid

        try:
            control_uid = pwd.getpwnam(CONTROL_USER).pw_uid
            worker = provider_worker_slots.get_slot("codex-01")
            worker_uid = pwd.getpwnam(worker.worker_user).pw_uid
            if worker_uid != worker.worker_uid:
                raise ArmAdmissionError("service_uid_process_unknown")
        except (KeyError, provider_worker_slots.SlotCatalogError) as exc:
            raise ArmAdmissionError("service_uid_process_unknown") from exc
        for uid in (control_uid, worker_uid):
            try:
                before = _ps_pids_for_uid(uid)
                if not before:
                    continue
                # The reviewed ambient exception belongs only to the dedicated
                # worker principal. Control must remain entirely absent.
                if uid != worker_uid:
                    raise ArmAdmissionError("service_uid_process_live")
                classifier = DarwinDistnotedClassifier()
                ambient = classifier.classify(worker_uid=uid)
                if type(ambient) is not AmbientClassification or ambient.status == "failed_closed":
                    raise ArmAdmissionError("service_uid_process_unknown")
                if ambient.status != "attested" or len(ambient.identities) != 1:
                    raise ArmAdmissionError("service_uid_process_live")
                identity = ambient.identities[0]
                if type(identity) is not AmbientProcessIdentity or identity.codesign_verified is not True:
                    raise ArmAdmissionError("service_uid_process_unknown")
                if (identity.uid != uid or identity.pid <= 1
                        or identity.launchd_reported_pid != identity.pid
                        or before != (identity.pid,)):
                    raise ArmAdmissionError("service_uid_process_live")
                # Process creation, exit, PID replacement or attribution drift
                # during the read cannot inherit the earlier observation.
                if (_ps_pids_for_uid(uid) != before
                        or classifier.classify(worker_uid=uid) != ambient):
                    raise ArmAdmissionError("service_uid_process_unknown")
            except ArmAdmissionError:
                raise
            except Exception as exc:
                raise ArmAdmissionError("service_uid_process_unknown") from exc

    def require_transaction_absent(self) -> None:
        if AUTONOMY_TRANSACTION.exists() or AUTONOMY_TRANSACTION.is_symlink():
            raise ArmAdmissionError("transaction_incomplete")


class ProductionTransactionHost(ProductionArmHost):
    """One crash-recoverable transaction over the two installed configs."""

    def __init__(self) -> None:
        super().__init__()
        self._active_transaction: TransactionContext | None = None
        self._transaction_owner_fd: int | None = None

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
        return AUTONOMY_TRANSACTION / _TRANSACTION_MANIFEST_NAME

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

    def _claim_transaction_owner(self) -> None:
        """Exclusively own the existing marker directory for this process.

        The persistent directory remains the single transaction owner.  Its
        advisory lock only distinguishes a crashed owner from a still-running
        ARM/DISARM or recovery process; it does not create another lifecycle.
        """

        if self._transaction_owner_fd is not None:
            raise TransactionEffectUnknown()
        self._config_root_safe()
        descriptor: int | None = None
        try:
            if not self._transaction_present():
                raise TransactionEffectUnknown()
            descriptor = os.open(
                AUTONOMY_TRANSACTION,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            )
            info = os.fstat(descriptor)
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid != 0
                or info.st_gid != 0
                or stat.S_IMODE(info.st_mode) != 0o700
            ):
                raise TransactionEffectUnknown()
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if not self._transaction_present():
                raise TransactionEffectUnknown()
            path_info = AUTONOMY_TRANSACTION.lstat()
            if (
                path_info.st_dev != info.st_dev
                or path_info.st_ino != info.st_ino
            ):
                raise TransactionEffectUnknown()
        except Exception as exc:
            if descriptor is not None:
                os.close(descriptor)
            if isinstance(exc, TransactionEffectUnknown):
                raise
            raise TransactionEffectUnknown() from exc
        self._transaction_owner_fd = descriptor

    def _release_transaction_owner(self) -> None:
        descriptor = self._transaction_owner_fd
        if descriptor is None:
            raise TransactionEffectUnknown()
        self._transaction_owner_fd = None
        self._control_observation_origin = None
        self._control_observation_fresh_transaction = None
        self._control_observation_recovery_owner = None
        self._control_observation_rollback_proven = None
        os.close(descriptor)

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
        if set(value) & _COEXISTENCE_MANIFEST_FIELDS:
            if (value.get("operation") not in CEO_SUBMIT_OPERATIONS
                    or type(value.get("prior_ceo_receipt_present")) is not bool
                    or any(re.fullmatch(r"[0-9a-f]{64}", str(value.get(field, ""))) is None
                           for field in _COEXISTENCE_MANIFEST_FIELDS - {"prior_ceo_receipt_present"})):
                raise TransactionEffectUnknown()
            required |= _COEXISTENCE_MANIFEST_FIELDS
        if set(value) & _FINITE_RECEIPT_FIELDS:
            if (value.get("operation") != "FINITE_CONTROL_STAGE"
                    or type(value.get("finite_prior_receipt_present")) is not bool
                    or any(re.fullmatch(r"[0-9a-f]{64}", str(value.get(field, ""))) is None
                           for field in _FINITE_RECEIPT_FIELDS - {"finite_prior_receipt_present"})):
                raise TransactionEffectUnknown()
            required |= _FINITE_RECEIPT_FIELDS
        if set(value) & _PAID_RECEIPT_FIELDS:
            if (value.get("operation") != "PAID_CONTROL_STAGE"
                    or type(value.get("paid_prior_receipt_present")) is not bool
                    or any(re.fullmatch(r"[0-9a-f]{64}", str(value.get(field, ""))) is None
                           for field in _PAID_RECEIPT_FIELDS - {"paid_prior_receipt_present"})):
                raise TransactionEffectUnknown()
            required |= _PAID_RECEIPT_FIELDS
        if set(value) & _GATEWAY_MANIFEST_FIELDS:
            # A gateway marker is refused unless it names THIS operation and
            # every closed gateway field is exactly shaped.  Old schemas are
            # never interpreted as gateway publications and vice versa.  The
            # audit prerequisite is part of the same closed intent: a marker
            # without its bound before-identity never classifies.
            if (value.get("operation") != OS_GATEWAY_PUBLICATION
                    or type(value.get("gateway_prior_grant_present")) is not bool
                    or value.get(_GATEWAY_AUDIT_STATE_FIELD) not in ("absent", "present")
                    or type(value.get(_GATEWAY_AUDIT_UID_FIELD)) is not int
                    or type(value.get(_GATEWAY_AUDIT_UID_FIELD)) is bool
                    or value[_GATEWAY_AUDIT_UID_FIELD] <= 0
                    or type(value.get(_GATEWAY_AUDIT_GID_FIELD)) is not int
                    or type(value.get(_GATEWAY_AUDIT_GID_FIELD)) is bool
                    or type(value.get(_GATEWAY_AUDIT_MODE_FIELD)) is not int
                    or type(value.get(_GATEWAY_AUDIT_MODE_FIELD)) is bool
                    or value[_GATEWAY_AUDIT_MODE_FIELD] != _GATEWAY_AUDIT_LEAF_MODE
                    or any(re.fullmatch(r"[0-9a-f]{64}", str(value.get(field, ""))) is None
                           for field in _GATEWAY_DIGEST_MANIFEST_FIELDS)):
                raise TransactionEffectUnknown()
            before_inode = value.get(_GATEWAY_AUDIT_BEFORE_FIELD)
            after_inode = value.get(_GATEWAY_AUDIT_AFTER_FIELD)
            if (
                (value[_GATEWAY_AUDIT_STATE_FIELD] == "absent" and before_inode is not None)
                or (value[_GATEWAY_AUDIT_STATE_FIELD] == "present"
                    and not _gateway_inode_identity(before_inode))
                or (after_inode is not None and not _gateway_inode_identity(after_inode))
                or (value.get("phase") != "LOCKED" and after_inode is None)
            ):
                raise TransactionEffectUnknown()
            required |= _GATEWAY_MANIFEST_FIELDS
        elif value.get("operation") == OS_GATEWAY_PUBLICATION:
            # A gateway marker is never valid without its own closed fields.
            raise TransactionEffectUnknown()
        if value.get("operation") in DIALOGUE_CANARY_OPERATIONS:
            required |= _CANARY_MANIFEST_FIELDS
            if (
                type(value.get("prior_canary_receipt_present")) is not bool
                or any(re.fullmatch(r"[0-9a-f]{64}", str(value.get(field, ""))) is None
                       for field in ("prior_canary_receipt_sha256", "target_canary_receipt_sha256"))
            ):
                raise TransactionEffectUnknown()
        keys = set(value)
        allowed_with_control_preimage = required | {_CONTROL_LAUNCHD_PREIMAGE_FIELD}
        if (
            frozenset(keys)
            not in {
                frozenset(required),
                frozenset(allowed_with_control_preimage),
            }
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
            or (
                _CONTROL_LAUNCHD_PREIMAGE_FIELD in value
                and (
                    value.get("operation") not in CONTROL_ONLY_TRANSACTION_OPERATIONS
                    or type(value.get(_CONTROL_LAUNCHD_PREIMAGE_FIELD)) is not bool
                )
            )
        ):
            raise TransactionEffectUnknown()
        return value

    @staticmethod
    def _manifest_document(
        transaction: TransactionContext, phase: str, *, operation: str
    ) -> dict[str, Any]:
        """The one recoverable identity document, unchanged across phases."""

        return {
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

    def _persist_phase(self, transaction: TransactionContext, phase: str, *, operation: str | None = None) -> None:
        current: Mapping[str, Any] | None = None
        if operation is None:
            current = self._manifest()
            operation = str(current["operation"])
        value = self._manifest_document(transaction, phase, operation=operation)
        if current is not None and _CONTROL_LAUNCHD_PREIMAGE_FIELD in current:
            value[_CONTROL_LAUNCHD_PREIMAGE_FIELD] = current[
                _CONTROL_LAUNCHD_PREIMAGE_FIELD
            ]
        if current is not None and operation in DIALOGUE_CANARY_OPERATIONS:
            value.update({key: current[key] for key in _CANARY_MANIFEST_FIELDS})
        if current is not None and set(current) & _COEXISTENCE_MANIFEST_FIELDS:
            value.update({key: current[key] for key in _COEXISTENCE_MANIFEST_FIELDS})
        if current is not None and set(current) & _FINITE_RECEIPT_FIELDS:
            value.update({key: current[key] for key in _FINITE_RECEIPT_FIELDS})
        if current is not None and set(current) & _PAID_RECEIPT_FIELDS:
            value.update({key: current[key] for key in _PAID_RECEIPT_FIELDS})
        if current is not None and set(current) & _GATEWAY_MANIFEST_FIELDS:
            value.update({key: current[key] for key in _GATEWAY_MANIFEST_FIELDS})
        _atomic_file(
            self._manifest_path(),
            _encoded_json(value),
            mode=0o400,
            uid=0,
            gid=0,
            replace=self._manifest_path().exists(),
        )

    @staticmethod
    def _generation_path(transaction_id: str) -> Path:
        """This creator's private, not-yet-canonical marker generation."""

        if re.fullmatch(r"autonomy-[0-9a-f]{12}", transaction_id) is None:
            raise TransactionEffectUnknown()
        suffix = transaction_id.removeprefix("autonomy-")
        return CONFIG_ROOT / (
            f".autonomy-transaction-{suffix}.{os.getpid()}"
            f".{secrets.token_hex(8)}.generating"
        )

    @staticmethod
    def _generation_archive_paths(generation: Path) -> tuple[Path, Path]:
        return (
            generation / "prior-control.json",
            generation / "prior-worker.json",
        )

    def _seal_generation(
        self, generation: Path, transaction: TransactionContext, *, operation: str
    ) -> None:
        """Write the COMPLETE recoverable marker into the private generation.

        Everything a later recovery needs -- the identity manifest and both
        exact preimages, each fsynced -- is sealed here, before the canonical
        ``AUTONOMY_TRANSACTION`` path can become visible at all.  Nothing in
        this method reads or writes the canonical path.
        """

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
        prior_control, prior_worker = self._generation_archive_paths(generation)
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
        _atomic_file(
            generation / _TRANSACTION_MANIFEST_NAME,
            _encoded_json(
                self._manifest_document(transaction, "LOCKED", operation=operation)
            ),
            mode=0o400,
            uid=0,
            gid=0,
            replace=False,
        )
        _fsync_directory(generation)

    @staticmethod
    def _publication_mutex() -> int:
        """Serialize FIRST publication on the existing config-directory inode.

        Every creator takes this same lock on the trusted ``CONFIG_ROOT``
        directory itself, so only one generation can be renamed onto the
        canonical marker at a time.  It adds no lock file and no second owner
        registry; the kernel releases it if this process dies.
        """

        descriptor = os.open(
            CONFIG_ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
        try:
            info = os.fstat(descriptor)
            path_info = CONFIG_ROOT.lstat()
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid != 0
                or info.st_gid != 0
                or stat.S_IMODE(info.st_mode) != 0o755
                or path_info.st_dev != info.st_dev
                or path_info.st_ino != info.st_ino
            ):
                raise TransactionEffectUnknown()
            fcntl.flock(descriptor, fcntl.LOCK_EX)
        except Exception:
            os.close(descriptor)
            raise
        return descriptor

    @staticmethod
    def _require_canonical_absent() -> None:
        """No-clobber, rechecked under the publication mutex.

        ``rename`` CAN replace an existing empty directory, so the competing
        canonical identity is preserved explicitly: any entry at the canonical
        path -- directory, file or symlink -- refuses this publication and is
        never removed or replaced here.
        """

        try:
            AUTONOMY_TRANSACTION.lstat()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise FileExistsError(os.fspath(AUTONOMY_TRANSACTION)) from exc
        raise FileExistsError(os.fspath(AUTONOMY_TRANSACTION))

    def _verify_published_inode(self, descriptor: int) -> None:
        """The canonical path must resolve to the exact held inode."""

        info = os.fstat(descriptor)
        try:
            path_info = AUTONOMY_TRANSACTION.lstat()
        except OSError as exc:
            raise TransactionEffectUnknown() from exc
        if (
            not stat.S_ISDIR(path_info.st_mode)
            or path_info.st_dev != info.st_dev
            or path_info.st_ino != info.st_ino
            or stat.S_IMODE(path_info.st_mode) != 0o700
        ):
            raise TransactionEffectUnknown()

    def _discard_own_generation(self, generation: Path, descriptor: int) -> None:
        """Dispose of this process's own generation that never published.

        Confined to a proven own unpublished inode: the canonical path must
        still be absent, the open descriptor must still be that generation's
        directory inode, and every entry must be a plain regular file this
        process sealed itself.  Anything else is ambiguous publication
        evidence and is deliberately left in place.
        """

        if self._transaction_owner_fd is not None:
            return
        try:
            AUTONOMY_TRANSACTION.lstat()
            return  # a canonical marker appeared: this is publication evidence
        except FileNotFoundError:
            pass
        except OSError:
            return
        try:
            held = os.fstat(descriptor)
            path_info = generation.lstat()
            if (
                not stat.S_ISDIR(path_info.st_mode)
                or path_info.st_dev != held.st_dev
                or path_info.st_ino != held.st_ino
            ):
                return
            for entry in sorted(os.listdir(generation)):
                candidate = generation / entry
                entry_info = candidate.lstat()
                if stat.S_ISLNK(entry_info.st_mode) or not stat.S_ISREG(
                    entry_info.st_mode
                ):
                    return
                candidate.unlink()
            os.rmdir(generation)
            _fsync_directory(CONFIG_ROOT)
        except OSError:
            return

    @staticmethod
    def _generation_definitely_unpublished(generation: Path, descriptor: int) -> bool:
        """Prove the held inode is still private while the publication mutex is held.

        A failed rename acknowledgment says nothing about whether rename took
        effect.  Only an absent canonical name AND this exact still-private
        inode permit the known-prepublication cleanup path.  Missing, replaced,
        or unreadable names leave publication uncertain and retain the owner.
        """

        try:
            AUTONOMY_TRANSACTION.lstat()
        except FileNotFoundError:
            pass
        except OSError:
            return False
        else:
            return False
        try:
            held = os.fstat(descriptor)
            private = generation.lstat()
        except OSError:
            return False
        return (
            stat.S_ISDIR(private.st_mode)
            and stat.S_ISDIR(held.st_mode)
            and (private.st_dev, private.st_ino) == (held.st_dev, held.st_ino)
        )

    def _create_marker(self, transaction: TransactionContext, *, operation: str) -> None:
        """Publish the ONE transaction marker complete, or not at all.

        The recoverable identity, both exact preimages and this creator's own
        directory flock are sealed into a private generation first, so the
        canonical path never exists in an empty or partial state.  First
        publication is then serialized on the config-directory inode lock,
        canonical absence is rechecked under that mutex, the generation is
        renamed into place while this process keeps its marker descriptor, the
        parent directory is fsynced, and the canonical path is verified to be
        the exact held inode before ownership is recorded.
        """

        self._config_root_safe()
        generation = self._generation_path(transaction.transaction_id)
        descriptor = -1
        try:
            _create_directory(generation, 0o700)
            os.chown(generation, 0, 0)
            os.chmod(generation, 0o700)
            descriptor = os.open(
                generation, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            )
            info = os.fstat(descriptor)
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid != 0
                or info.st_gid != 0
                or stat.S_IMODE(info.st_mode) != 0o700
            ):
                raise TransactionEffectUnknown()
            # Creator-owned exclusion exists BEFORE the canonical path does.
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._seal_generation(generation, transaction, operation=operation)
            lock = self._publication_mutex()
            try:
                self._require_canonical_absent()
                try:
                    os.rename(generation, AUTONOMY_TRANSACTION)
                    _fsync_directory(CONFIG_ROOT)
                    self._verify_published_inode(descriptor)
                except Exception as exc:
                    # Reconcile actual names/inodes under the same mutex, not
                    # a boolean inferred from whether rename returned normally.
                    if not self._generation_definitely_unpublished(generation, descriptor):
                        self._transaction_owner_fd = descriptor
                        raise TransactionEffectUnknown() from exc
                    raise
                self._transaction_owner_fd = descriptor
            finally:
                try:
                    fcntl.flock(lock, fcntl.LOCK_UN)
                finally:
                    os.close(lock)
            # Actual creator provenance remains process-local and bound to the
            # held marker inode. Reclaiming an old marker never creates it.
            self._control_observation_origin = (
                os.getpid(), descriptor, transaction.transaction_id,
                transaction.expected_sha,
            )
        except Exception as exc:
            if descriptor >= 0 and self._transaction_owner_fd == descriptor:
                # Successful or uncertain publication retains the original
                # held inode even if parent-fsync, readback or unlock fails.
                raise TransactionEffectUnknown() from exc
            if descriptor >= 0:
                self._discard_own_generation(generation, descriptor)
                os.close(descriptor)
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
        try:
            control, _worker, control_digest, worker_digest, _cr, _wr = self._configs()
        except (HostControlError, OSError) as exc:
            raise ArmAdmissionError("changed_arm_evidence") from exc
        if (control_digest != snapshot.control_config_sha256
                or worker_digest != snapshot.worker_config_sha256
                or control.get("coo_foreground_only", False) is not request.foreground_only
                or not _native_selection_matches(control, request.native_return)):
            raise ArmAdmissionError("changed_arm_evidence")
        if request.native_return:
            self.require_native_listener(ConfigEvidence(control_digest, worker_digest, control, _worker, _cr, _wr))
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
            self._claim_transaction_owner()
            return str(self._manifest()["transaction_id"])
        return f"autonomy-{secrets.token_hex(6)}"

    def begin_transaction(self, transaction: TransactionContext) -> None:
        if AUTONOMY_TRANSACTION.exists() or AUTONOMY_TRANSACTION.is_symlink():
            raise ArmAdmissionError("transaction_incomplete")
        self._active_transaction = transaction
        try:
            self._create_marker(transaction, operation="ARM")
        except FileExistsError as exc:
            if self._transaction_owner_fd is not None:
                raise
            self._active_transaction = None
            raise ArmAdmissionError("transaction_incomplete") from exc
        except Exception as exc:
            if self._transaction_owner_fd is None:
                self._active_transaction = None
                raise TransactionOwnershipError() from exc
            raise

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
        # Process-local publication provenance. Reconstructed recovery contexts
        # can verify the derivative observation, never issue another write.
        self._control_observation_fresh_transaction = transaction

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
        if self._transaction_owner_fd is None:
            raise TransactionEffectUnknown()
        manifest = self._manifest()
        if (
            manifest.get("transaction_id") != transaction.transaction_id
            or manifest.get("expected_sha") != transaction.expected_sha
        ):
            raise TransactionEffectUnknown()
        from ops.executive_os.control_observation import publish_for_transaction
        publish_for_transaction(self, transaction)
        control_candidate, worker_candidate = self._candidate_paths(
            transaction.transaction_id
        )
        self._remove_candidate(control_candidate)
        self._remove_candidate(worker_candidate)
        expected = {"transaction.json", "prior-control.json", "prior-worker.json"}
        archives = list(self._archive_paths())
        if set(manifest) & _COEXISTENCE_MANIFEST_FIELDS:
            expected.update(_COEXISTENCE_ARCHIVES)
            archives.extend(AUTONOMY_TRANSACTION / name for name in _COEXISTENCE_ARCHIVES)
        if set(manifest) & _FINITE_RECEIPT_FIELDS:
            expected.add(_FINITE_RECEIPT_ARCHIVE)
            archives.append(AUTONOMY_TRANSACTION / _FINITE_RECEIPT_ARCHIVE)
        if set(manifest) & _PAID_RECEIPT_FIELDS:
            expected.add(_PAID_RECEIPT_ARCHIVE)
            archives.append(AUTONOMY_TRANSACTION / _PAID_RECEIPT_ARCHIVE)
        if set(manifest) & _GATEWAY_MANIFEST_FIELDS:
            expected.add(_GATEWAY_GRANT_ARCHIVE)
            archives.append(AUTONOMY_TRANSACTION / _GATEWAY_GRANT_ARCHIVE)
        if manifest.get("operation") in DIALOGUE_CANARY_OPERATIONS:
            expected.add(_CANARY_RECEIPT_ARCHIVE)
            archives.append(AUTONOMY_TRANSACTION / _CANARY_RECEIPT_ARCHIVE)
        if set(os.listdir(AUTONOMY_TRANSACTION)) != expected:
            raise TransactionEffectUnknown()
        for path in (*archives, self._manifest_path()):
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
        self._release_transaction_owner()

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
            if self._transaction_owner_fd is None:
                self._claim_transaction_owner()
            manifest = self._manifest()
            if (
                manifest.get("operation") not in {"ARM", "DISARM"}
                or manifest.get("transaction_id") != transaction_id
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

    def _seal_generation(self, generation, transaction, *, operation):
        super()._seal_generation(generation, transaction, operation=operation)
        if not _full_autonomy_flags(transaction.prior_configs):
            return
        payload, metadata = load_receipt_file(AUTONOMY_RECEIPT)
        if not coexistence_receipt_eligible(
            transaction.prior_configs, payload, metadata,
            expected_sha=transaction.expected_sha,
        ):
            raise TransactionEffectUnknown()
        raw, _ = _read_root_file(AUTONOMY_RECEIPT, modes=frozenset({0o444}), uid=0, gid=0)
        if json.loads(raw) != payload:
            raise TransactionEffectUnknown()
        ceo_present = CEO_SUBMIT_RECEIPT.exists() or CEO_SUBMIT_RECEIPT.is_symlink()
        ceo_raw = b""
        if ceo_present:
            ceo_raw, _ = _read_root_file(CEO_SUBMIT_RECEIPT, modes=frozenset({0o444}), uid=0, gid=0)
        for name, contents in zip(_COEXISTENCE_ARCHIVES, (raw, ceo_raw)):
            _atomic_file(generation / name, contents, mode=0o400, uid=0, gid=0, replace=False)
        manifest = self._manifest_document(transaction, "LOCKED", operation=operation)
        # Seal recovery's launchd preimage before the FIRST paired receipt
        # effect, including a crash before service reconciliation is reached.
        disabled = self._read_control_launchd_disabled_override()
        if type(disabled) is not bool:
            raise TransactionEffectUnknown()
        manifest[_CONTROL_LAUNCHD_PREIMAGE_FIELD] = disabled
        manifest.update(
            prior_autonomy_receipt_sha256=sha256_bytes(raw),
            target_autonomy_receipt_sha256=sha256_bytes(_encoded_json(rebind_coexistence_receipt(transaction, payload))),
            prior_ceo_receipt_present=ceo_present,
            prior_ceo_receipt_sha256=sha256_bytes(ceo_raw),
            target_ceo_receipt_sha256=sha256_bytes(ceo_raw),
        )
        _atomic_file(generation / _TRANSACTION_MANIFEST_NAME, _encoded_json(manifest),
                     mode=0o400, uid=0, gid=0, replace=True)
        _fsync_directory(generation)

    def _coexistence_archives(self, transaction):
        if (self._transaction_owner_fd is None or self._active_transaction is None
                or self._active_transaction.transaction_id != transaction.transaction_id):
            raise TransactionEffectUnknown()
        self._verify_published_inode(self._transaction_owner_fd)
        manifest = self._manifest()
        if (manifest.get("transaction_id") != transaction.transaction_id
                or manifest.get("expected_sha") != transaction.expected_sha
                or not _COEXISTENCE_MANIFEST_FIELDS <= set(manifest)):
            raise TransactionEffectUnknown()
        contents = []
        for name, key in zip(_COEXISTENCE_ARCHIVES,
                             ("prior_autonomy_receipt_sha256", "prior_ceo_receipt_sha256")):
            raw, _ = _read_root_file(AUTONOMY_TRANSACTION / name, modes=frozenset({0o400}), uid=0, gid=0)
            if sha256_bytes(raw) != manifest[key]:
                raise TransactionEffectUnknown()
            contents.append(raw)
        if not manifest["prior_ceo_receipt_present"] and contents[1] != b"":
            raise TransactionEffectUnknown()
        return manifest, contents

    def rebind_full_autonomy_receipt(self, transaction):
        manifest, (raw, _) = self._coexistence_archives(transaction)
        current, _ = _read_root_file(AUTONOMY_RECEIPT, modes=frozenset({0o444}), uid=0, gid=0)
        configs = self.load_ceo_submit_configs(transaction.expected_sha)
        if (current != raw or configs.control_sha256 != transaction.prior_configs.control_sha256
                or configs.worker_sha256 != transaction.prior_configs.worker_sha256
                or not self.proves_safe_coexistence(configs)):
            raise TransactionEffectUnknown()
        rebound = _encoded_json(rebind_coexistence_receipt(transaction, json.loads(raw)))
        if sha256_bytes(rebound) != manifest["target_autonomy_receipt_sha256"]:
            raise TransactionEffectUnknown()
        _atomic_file(AUTONOMY_RECEIPT, rebound, mode=0o444, uid=0, gid=0, replace=True)
        self._persist_phase(transaction, "AUTONOMY_RECEIPT_REBOUND")

    def _check_coexistence_rollback(self, transaction):
        manifest, archived = self._coexistence_archives(transaction)
        configs = self.load_ceo_submit_configs(transaction.expected_sha)
        if (configs.control_sha256 not in {transaction.prior_configs.control_sha256, manifest["target_control_sha256"]}
                or configs.worker_sha256 != transaction.prior_configs.worker_sha256):
            raise TransactionEffectUnknown()
        for path, prefix in ((AUTONOMY_RECEIPT, "autonomy"), (CEO_SUBMIT_RECEIPT, "ceo")):
            if prefix == "ceo" and not path.exists() and not path.is_symlink():
                current = b""
            else:
                current, _ = _read_root_file(path, modes=frozenset({0o444}), uid=0, gid=0)
            if sha256_bytes(current) not in {manifest[f"prior_{prefix}_receipt_sha256"],
                                             manifest[f"target_{prefix}_receipt_sha256"]}:
                raise TransactionEffectUnknown()
        return manifest, archived

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
            self._claim_transaction_owner()
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

    def _read_validated_control_candidate(self, transaction: TransactionContext):
        release = SYSTEM_ROOT / "releases" / transaction.expected_sha
        control_candidate, _worker_candidate = self._candidate_paths(
            transaction.transaction_id
        )
        control_home = RUNTIME_ROOT / "control" / "home"
        control_gid = grp.getgrnam(CONTROL_GROUP).gr_gid
        worker_gid = grp.getgrnam(WORKER_GROUP).gr_gid
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
        return candidate_control, candidate_raw, worker_raw

    def validate_candidates(self, transaction: TransactionContext) -> None:
        candidate_control, candidate_raw, worker_raw = self._read_validated_control_candidate(transaction)
        expected_armed = self._manifest().get("operation") == "CEO_SUBMIT_ARM"
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
        manifest = self._manifest()
        if set(manifest) & _COEXISTENCE_MANIFEST_FIELDS:
            self._coexistence_archives(transaction)
            manifest["target_ceo_receipt_sha256"] = sha256_bytes(_encoded_json(dict(receipt)))
            _atomic_file(self._manifest_path(), _encoded_json(manifest),
                         mode=0o400, uid=0, gid=0, replace=True)
        _atomic_file(
            CEO_SUBMIT_RECEIPT,
            _encoded_json(dict(receipt)),
            mode=0o444,
            uid=0,
            gid=0,
            replace=replace,
        )
        self._persist_phase(transaction, "RECEIPT_REPLACED")

    @staticmethod
    def _terminate_launchctl_reader(process: subprocess.Popen[bytes]) -> None:
        """Terminate and reap the fixed read-only launchctl child."""

        try:
            process.terminate()
        except ProcessLookupError:
            pass
        except OSError as exc:
            if process.poll() is None:
                raise TransactionEffectUnknown() from exc
        try:
            process.wait(timeout=0.5)
            return
        except subprocess.TimeoutExpired:
            pass
        except OSError as exc:
            raise TransactionEffectUnknown() from exc
        try:
            process.kill()
        except ProcessLookupError:
            pass
        except OSError as exc:
            if process.poll() is None:
                raise TransactionEffectUnknown() from exc
        try:
            process.wait(timeout=0.5)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise TransactionEffectUnknown() from exc
        if process.poll() is None:
            raise TransactionEffectUnknown()

    @staticmethod
    def _capture_control_launchd_disabled_output() -> bytes:
        """Capture fixed ``print-disabled`` output without unbounded buffering."""

        deadline = time.monotonic() + 5.0
        try:
            process = subprocess.Popen(
                ["/bin/launchctl", "print-disabled", "system"],
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=False,
                close_fds=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise TransactionEffectUnknown() from exc
        stdout = process.stdout
        if stdout is None:
            ProductionCeoSubmitHost._terminate_launchctl_reader(process)
            raise TransactionEffectUnknown()

        selector: selectors.BaseSelector | None = None
        payload = bytearray()
        succeeded = False
        try:
            selector = selectors.DefaultSelector()
            descriptor = stdout.fileno()
            os.set_blocking(descriptor, False)
            selector.register(descriptor, selectors.EVENT_READ)
            eof = False
            while not eof:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TransactionEffectUnknown()
                events = selector.select(remaining)
                if not events:
                    raise TransactionEffectUnknown()
                for _key, _mask in events:
                    while True:
                        remaining_capacity = (
                            _MAX_LAUNCHCTL_DISABLED_BYTES + 1 - len(payload)
                        )
                        if remaining_capacity <= 0:
                            raise TransactionEffectUnknown()
                        try:
                            chunk = os.read(
                                descriptor, min(65_536, remaining_capacity)
                            )
                        except BlockingIOError:
                            break
                        if not chunk:
                            eof = True
                            break
                        payload.extend(chunk)
                        if len(payload) > _MAX_LAUNCHCTL_DISABLED_BYTES:
                            raise TransactionEffectUnknown()
                    if eof:
                        break

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TransactionEffectUnknown()
            try:
                returncode = process.wait(timeout=remaining)
            except subprocess.TimeoutExpired as exc:
                raise TransactionEffectUnknown() from exc
            if returncode != 0 or process.poll() is None:
                raise TransactionEffectUnknown()
            succeeded = True
            return bytes(payload)
        except TransactionEffectUnknown:
            raise
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            raise TransactionEffectUnknown() from exc
        finally:
            if not succeeded:
                ProductionCeoSubmitHost._terminate_launchctl_reader(process)
            if selector is not None:
                try:
                    selector.close()
                except Exception as exc:
                    if succeeded:
                        raise TransactionEffectUnknown() from exc
            try:
                stdout.close()
            except (OSError, ValueError) as exc:
                if succeeded:
                    raise TransactionEffectUnknown() from exc

    @staticmethod
    def _read_control_launchd_disabled_override() -> bool:
        return ProductionCeoSubmitHost._read_launchd_disabled_override(CONTROL_LABEL)

    @staticmethod
    def _read_launchd_disabled_override(target_label: str, *, allow_absent: bool = False):
        """Read one exact persistent launchd override with a closed parser.

        ``print-disabled`` is a global table. Before a CEO-submit transaction may
        mutate the fixed control label, every non-empty row must parse, labels must
        be unique, output is acquired under a hard byte/time bound, and the control
        label itself must be explicitly present. Missing/ambiguous output is not
        interpreted as the launchd default because rollback must restore an
        observed preimage, not an inferred one.
        """

        raw = ProductionCeoSubmitHost._capture_control_launchd_disabled_output()
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise TransactionEffectUnknown() from exc
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) < 2 or lines[0] != "disabled services = {" or lines[-1] != "}":
            raise TransactionEffectUnknown()
        observed: dict[str, bool] = {}
        for line in lines[1:-1]:
            match = _CONTROL_LAUNCHD_DISABLED_ROW_RE.fullmatch(line)
            if match is None:
                raise TransactionEffectUnknown()
            label = match.group("label")
            state = match.group("state")
            if label in observed or state not in _CONTROL_LAUNCHD_DISABLED_SPELLINGS:
                raise TransactionEffectUnknown()
            observed[label] = _CONTROL_LAUNCHD_DISABLED_SPELLINGS[state]
        if target_label not in observed:
            if allow_absent:
                return None
            raise TransactionEffectUnknown()
        return observed[target_label]

    def _persist_control_launchd_preimage(
        self, transaction: TransactionContext, disabled: bool
    ) -> None:
        """Persist the fixed-label launchd preimage before the first enable."""

        if type(disabled) is not bool:
            raise TransactionEffectUnknown()
        current = self._manifest()
        if (
            current.get("operation") not in CONTROL_ONLY_TRANSACTION_OPERATIONS
            or current.get("transaction_id") != transaction.transaction_id
            or current.get("expected_sha") != transaction.expected_sha
        ):
            raise TransactionEffectUnknown()
        existing = current.get(_CONTROL_LAUNCHD_PREIMAGE_FIELD)
        if existing is not None:
            if type(existing) is not bool or existing is not disabled:
                raise TransactionEffectUnknown()
            return
        value = dict(current)
        value[_CONTROL_LAUNCHD_PREIMAGE_FIELD] = disabled
        value["phase"] = "CONTROL_OVERRIDE_SNAPSHOTTED"
        _atomic_file(
            self._manifest_path(),
            _encoded_json(value),
            mode=0o400,
            uid=0,
            gid=0,
            replace=True,
        )
        reread = self._manifest()
        if reread.get(_CONTROL_LAUNCHD_PREIMAGE_FIELD) is not disabled:
            raise TransactionEffectUnknown()

    def _ensure_control_launchd_preimage(self) -> bool:
        transaction = self._active_transaction
        if transaction is None:
            raise TransactionEffectUnknown()
        current = self._manifest()
        existing = current.get(_CONTROL_LAUNCHD_PREIMAGE_FIELD)
        if existing is not None:
            if type(existing) is not bool:
                raise TransactionEffectUnknown()
            return existing
        disabled = self._read_control_launchd_disabled_override()
        self._persist_control_launchd_preimage(transaction, disabled)
        return disabled

    def _restore_control_launchd_preimage_if_recorded(
        self, transaction: TransactionContext
    ) -> None:
        """Restore and prove a recorded launchd override before marker release."""

        current = self._manifest()
        if (
            current.get("transaction_id") != transaction.transaction_id
            or current.get("expected_sha") != transaction.expected_sha
        ):
            raise TransactionEffectUnknown()
        if _CONTROL_LAUNCHD_PREIMAGE_FIELD not in current:
            # Legacy transactions created before this repair made no launchd
            # override effect through this source path. Their separate same-carrier
            # reconciliation remains evidence-driven; never invent a preimage here.
            return
        disabled = current.get(_CONTROL_LAUNCHD_PREIMAGE_FIELD)
        if type(disabled) is not bool:
            raise TransactionEffectUnknown()
        release = SYSTEM_ROOT / "releases" / transaction.expected_sha
        if disabled:
            try:
                self._run_fixed(
                    ["/bin/launchctl", "disable", f"system/{CONTROL_LABEL}"],
                    cwd=release,
                    timeout=45.0,
                )
            except Exception as exc:
                raise TransactionEffectUnknown() from exc
        if self._read_control_launchd_disabled_override() is not disabled:
            raise TransactionEffectUnknown()
        self._persist_phase(transaction, "CONTROL_OVERRIDE_RESTORED")

    def _reconcile_control_boundary(self, expected_sha: str) -> None:
        """Converge ONLY the control launchd boundary. Never the worker.

        R17 B2: the reviewed lifecycle script exposes no control-only verb and its
        ``start`` bootstraps the worker daemon first, so it is not used from the
        CEO-submit domain at all. The two argv forms below are fixed and name the
        hard-coded control label and control plist; nothing is caller-selected.
        The persistent disabled-state preimage is sealed in the existing
        transaction marker before the fixed ``enable`` effect.
        """
        release = SYSTEM_ROOT / "releases" / expected_sha
        self._ensure_control_launchd_preimage()
        try:
            self._run_fixed(
                ["/bin/launchctl", "enable", f"system/{CONTROL_LABEL}"],
                cwd=release,
                timeout=45.0,
            )
        except Exception as exc:
            # The command may have crossed the launchd effect boundary even when
            # its response is unavailable. Preserve the marker; do not convert a
            # possibly-applied enable into a false-clean rollback.
            raise TransactionEffectUnknown() from exc
        if self._loaded(CONTROL_LABEL):
            self._run_fixed(
                ["/bin/launchctl", "kickstart", "-k", f"system/{CONTROL_LABEL}"],
                cwd=release,
                timeout=45.0,
            )
        else:
            self._require_control_plist_safe()
            self._run_fixed(
                ["/bin/launchctl", "bootstrap", "system", os.fspath(CONTROL_PLIST)],
                cwd=release,
                timeout=45.0,
            )
        if not self._loaded(CONTROL_LABEL):
            raise TransactionEffectUnknown()

    @staticmethod
    def _require_control_plist_safe() -> None:
        """Validate the single fixed bootstrap target before a privileged bootstrap."""
        try:
            info = CONTROL_PLIST.lstat()
        except OSError as exc:
            raise TransactionEffectUnknown() from exc
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or info.st_gid != 0
            or stat.S_IMODE(info.st_mode) & 0o022
            or info.st_nlink != 1
        ):
            raise TransactionEffectUnknown()

    def reconcile_control_service(self, expected_sha: str) -> None:
        """Converge only the control boundary onto the replaced config."""
        self._reconcile_control_boundary(expected_sha)
        if self._active_transaction is not None:
            # The manifest keeps whichever CEO-submit verb opened this
            # transaction; the boundary call must not relabel a DISARM as an ARM.
            self._persist_phase(self._active_transaction, "CONTROL_RECONCILED")

    def _ceo_admission_probe(
        self, expected_sha: str, expected_control_sha256: str
    ) -> bool:
        full_armed = (self._active_transaction is not None
                      and _full_autonomy_flags(self._active_transaction.prior_configs))
        return self._control_config_probe(
            expected_sha, expected_control_sha256,
            required_state="READY" if full_armed else "AWAITING_CANARY",
        )

    def _control_config_probe(
        self, expected_sha: str, expected_control_sha256: str, *,
        required_state: str | None = None,
    ) -> bool:
        """CEO-admission probe: fixed label + fixed socket + AWAITING_CANARY +
        wrapper-owned attestation validator.

        The phase1c status response exposes the FIXED socket path and the
        service_state, so the live liveness witness (label + socket +
        AWAITING_CANARY) is unchanged.  R80 then closes the
        kickstart-no-op hole by ALSO consulting the wrapper-owned live
        attestation document: the document proves that the live process
        with the ``pid`` the status response just reported is the SAME
        process that wrote the attestation document, that its process /
        boot identity is fresh, and that the document's
        ``config_sha256`` / ``release_commit_sha`` match the bytes H3
        hashed.  Anything else makes the admission proof REFUSE.

        The probe therefore carries one extra keyword-only parameter
        (``expected_control_sha256``); the live ``service_state`` +
        ``socket`` + status ``pid`` + the on-disk attestation document
        MUST all align on the EXACT bytes, or the probe refuses.
        """

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
        if (
            not isinstance(value, dict)
            or value.get("ok") is not True
            or not isinstance(value.get("result"), dict)
        ):
            return False
        result = value["result"]
        if result.get("service_state") not in {"READY", "AWAITING_CANARY"}:
            return False
        if required_state is not None and result.get("service_state") != required_state:
            return False
        # The service resolves its host-owned socket declaration (on macOS,
        # /var/run is /private/var/run). Admit only these two fixed spellings;
        # never resolve an arbitrary path supplied in the status response.
        try:
            canonical_control_socket = CONTROL_SOCKET.resolve(strict=False)
        except (OSError, RuntimeError):
            return False
        if result.get("socket") not in (
            os.fspath(CONTROL_SOCKET),
            os.fspath(canonical_control_socket),
        ):
            return False
        status_pid = result.get("pid")
        if (
            type(status_pid) is not int
            or isinstance(status_pid, bool)
            or not (0 < status_pid <= 2**31 - 1)
        ):
            return False
        try:
            control_gid = grp.getgrnam(CONTROL_GROUP).gr_gid
            control, control_raw = _root_json(
                CONTROL_CONFIG, modes=frozenset({0o440}), gid=control_gid
            )
            if (
                not isinstance(expected_control_sha256, str)
                or re.fullmatch(r"[0-9a-f]{64}", expected_control_sha256) is None
                or hashlib.sha256(control_raw).hexdigest()
                != expected_control_sha256
            ):
                return False
            attestation_path = control.get("control_environment_attestation_path")
            if (
                not isinstance(attestation_path, str)
                or not attestation_path
                or not os.path.isabs(attestation_path)
            ):
                return False
            control_uid = control.get("control_uid")
            if type(control_uid) is not int:
                return False
            attestation_bytes, _info = _read_root_file(
                Path(attestation_path),
                modes=frozenset({0o400}),
                uid=int(control_uid),
                gid=None,
            )
            document = json.loads(attestation_bytes.decode("utf-8"))
            control_wrapper.validate_control_environment_attestation(
                document,
                expected_config_sha256=expected_control_sha256,
                expected_release_commit_sha=expected_sha,
                expected_pid=status_pid,
                inspector=ProcessInspector(),
            )
        except (
            HostControlError,
            control_wrapper.ControlWrapperError,
            OSError,
            ValueError,
            TypeError,
            KeyError,
            json.JSONDecodeError,
        ):
            return False
        return True

    def _await_control_admission_bound(
        self, expected_sha: str, expected_control_sha256: str
    ) -> None:
        """Poll the CEO-admission probe until it returns True or the deadline.

        The fixed control label presence is the per-pass guard: a direct
        caller (the polling seam) probes only when ``_loaded(CONTROL_LABEL)``
        is true, so the proof never burns a deadline second waiting for an
        unregistered control boundary.  ``prove_control_admission_bound`` is
        the path ARM/DISARM ride; rollback's ``_prove_rolled_back_control_live``
        early-returns on a missing label and then runs its OWN loop reusing
        ``_ceo_admission_probe`` (without the per-pass ``_loaded`` re-check
        that would double-write the seam).
        """

        deadline = time.monotonic() + 45.0
        while time.monotonic() < deadline:
            if (
                self._loaded(CONTROL_LABEL)
                and self._ceo_admission_probe(expected_sha, expected_control_sha256)
            ):
                return
            time.sleep(1.0)
        raise RuntimeError(
            "Executive control service did not bind to the CEO admission surface"
        )

    def prove_control_admission_bound(
        self, expected_sha: str, expected_control_sha256: str
    ) -> None:
        """Prove the LIVE control service is bound to the CEO admission surface.

        R80: replaces the older ``prove_control_ready`` global-READY poll with
        a probe tailored to the post-reconcile, pre-canary state the CEO-
        submit admit path needs.  The proof is post-restart, pre-canary
        LIVENESS plus a wrapper-owned attestation validator that proves the
        live process consumed the exact candidate/restored control bytes.
        A failure here surfaces as ``RuntimeError``; the caller in
        ``execute_ceo_submit_*`` and ``rollback_ceo_submit`` translates that
        into the typed ``arm_rolled_back`` / ``disarm_recovered`` (for
        ARM/DISARM) or ``TransactionEffectUnknown`` (for rollback, R17 B3),
        with the marker KEPT.  The COO/global READY semantics in
        ``_service_state``, ``ARMED_READY``, and ``status_document`` are
        deliberately untouched.
        """

        self._await_control_admission_bound(expected_sha, expected_control_sha256)
        if self._active_transaction is not None:
            self._persist_phase(self._active_transaction, "ADMISSION_BOUND")

    def _prove_rolled_back_control_live(self, transaction: TransactionContext) -> None:
        """Prove the LIVE control service is running the restored preimage.

        R17 B3: disk agreement is not proof.  If the control boundary was already
        reconciled the service consumed the candidate config, so a rollback that
        only rewrites bytes leaves an armed service behind an ``arm_rolled_back``
        answer.  A REGISTERED control service is therefore reconciled onto the
        restored preimage through the control-only boundary and re-proven READY
        before the transaction marker may be removed.  If no control service is
        registered there is no live consumer of ``control.json`` and the restored
        disk state IS the live state.  Anything else is EFFECT_UNKNOWN, and the
        marker is deliberately KEPT so the ambiguity stays sticky to this
        operation.
        """

        if not self._loaded(CONTROL_LABEL):
            self._persist_phase(transaction, "ROLLBACK_CONTROL_PROVEN")
            return
        try:
            self._reconcile_control_boundary(transaction.expected_sha)
            # R80: rollback proves the LIVE control service is bound to the
            # RESTORED preimage using the SAME CEO-admission probe as ARM and
            # DISARM.  The live probe proves post-restart, pre-canary LIVENESS
            # only (label + socket + AWAITING_CANARY); the EXACT restored
            # preimage digest is pinned by the disk re-read above, NOT by
            # this probe, so a rollback can never release the marker while
            # the service still runs the candidate config.  The proof runs
            # the probe inline -- NOT through ``_await_control_admission_bound``
            # -- because the label was already proven loaded above; the
            # per-pass ``_loaded`` re-check would double-write the seam and
            # bury the proof.
            deadline = time.monotonic() + 45.0
            while time.monotonic() < deadline:
                if self._ceo_admission_probe(
                    transaction.expected_sha,
                    transaction.prior_configs.control_sha256,
                ):
                    break
                time.sleep(1.0)
            else:
                raise RuntimeError(
                    "Executive control service did not bind to the CEO admission surface"
                )
            if self._active_transaction is not None:
                self._persist_phase(self._active_transaction, "ADMISSION_BOUND")
        except Exception as exc:
            raise TransactionEffectUnknown() from exc
        self._persist_phase(transaction, "ROLLBACK_CONTROL_PROVEN")

    def rollback_ceo_submit(
        self, transaction: TransactionContext, receipt: Mapping[str, Any]
    ) -> None:
        """Restore the archived preimage, prove it LIVE, then release the marker.

        R17 B3: disk agreement is not proof.  The restored preimage is proven
        against the REGISTERED control service (control-only reconcile, then a
        readiness re-probe) before this carrier may release the transaction
        marker, so a rollback can never answer ``arm_rolled_back`` /
        ``disarm_recovered`` while the live control service still runs the
        candidate config.
        """

        self._active_transaction = transaction
        paired = self._check_coexistence_rollback(transaction) if _full_autonomy_flags(transaction.prior_configs) else None
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
        self._control_observation_fresh_transaction = transaction
        if paired is None:
            self.write_ceo_submit_receipt(transaction, receipt)
        else:
            manifest, (autonomy_raw, ceo_raw) = paired
            _atomic_file(AUTONOMY_RECEIPT, autonomy_raw, mode=0o444, uid=0, gid=0, replace=True)
            if manifest["prior_ceo_receipt_present"]:
                _atomic_file(CEO_SUBMIT_RECEIPT, ceo_raw, mode=0o444, uid=0, gid=0,
                             replace=CEO_SUBMIT_RECEIPT.exists())
            elif CEO_SUBMIT_RECEIPT.exists():
                CEO_SUBMIT_RECEIPT.unlink()
                _fsync_directory(CONFIG_ROOT)
        expected_armed = dict(transaction.candidates.control).get("ceo_submit_armed")
        if not isinstance(expected_armed, bool):
            raise TransactionEffectUnknown()
        (
            control,
            _worker,
            control_digest,
            worker_digest,
            _control_raw,
            _worker_raw,
        ) = self._configs()
        if (
            control.get("ceo_submit_armed") is not expected_armed
            or control_digest != transaction.prior_configs.control_sha256
            or worker_digest != transaction.prior_configs.worker_sha256
        ):
            raise TransactionEffectUnknown()
        self._prove_rolled_back_control_live(transaction)
        self._restore_control_launchd_preimage_if_recorded(transaction)
        self._control_observation_rollback_proven = transaction
        self.complete_transaction(transaction)

    def recover_ceo_submit_effect_unknown(
        self, request: CeoSubmitRequest, *, now: datetime
    ) -> TransactionResult:
        """Rollback one existing CEO-submit marker without minting a new operation.

        Recovery is available only to repaired-generation markers that sealed the
        persistent launchd preimage before the first enable. Legacy markers that
        lack that evidence remain EFFECT_UNKNOWN and require a separate,
        evidence-driven same-carrier reconciliation.
        """

        require_root_privilege(self.effective_uid())
        installed_sha = self.require_exact_install(request.expected_sha)
        if installed_sha != request.expected_sha:
            raise CeoSubmitAdmissionError("release_identity_mismatch")
        self._claim_transaction_owner()
        manifest = self._manifest()
        if (
            manifest.get("operation") not in CEO_SUBMIT_OPERATIONS
            or manifest.get("expected_sha") != request.expected_sha
            or _CONTROL_LAUNCHD_PREIMAGE_FIELD not in manifest
            or type(manifest.get(_CONTROL_LAUNCHD_PREIMAGE_FIELD)) is not bool
        ):
            raise TransactionEffectUnknown()
        prior = self._archived_configs(request.expected_sha)
        prior_armed = dict(prior.control).get("ceo_submit_armed")
        if type(prior_armed) is not bool:
            raise TransactionEffectUnknown()
        control_bytes = prior.control_bytes or encode_config(prior.control)
        worker_bytes = prior.worker_bytes or encode_config(prior.worker)
        candidates = CandidateConfigs(
            control=copy.deepcopy(dict(prior.control)),
            worker=copy.deepcopy(dict(prior.worker)),
            control_bytes=control_bytes,
            worker_bytes=worker_bytes,
            control_sha256=prior.control_sha256,
            worker_sha256=prior.worker_sha256,
        )
        transaction = TransactionContext(
            transaction_id=str(manifest["transaction_id"]),
            expected_sha=request.expected_sha,
            prior_configs=prior,
            candidates=candidates,
            admission=None,
        )
        self._active_transaction = transaction
        binding = self.executive_app_binding()
        separation = self.ceo_submit_separation(prior)
        admission = CeoSubmitAdmission(
            expected_sha=request.expected_sha,
            installed_sha=installed_sha,
            binding=binding,
            separation=separation,
            configs=prior,
        )
        from ops.executive_os.control_observation import (
            PUBLICATION_PHASE, ROLLBACK_PUBLICATION_PHASE,
            verify_ceo_rollback_readback,
        )
        if manifest['phase'] == PUBLICATION_PHASE:
            # A projection response cannot authorize rolling back an already
            # completed forward effect. Preserve this original uncertainty.
            raise TransactionEffectUnknown()
        if manifest['phase'] in {ROLLBACK_PUBLICATION_PHASE, 'CONTROL_OVERRIDE_RESTORED'}:
            verify_ceo_rollback_readback(self, transaction, admission)
            self.complete_transaction(transaction)
        else:
            # Only this incumbent recovery verb, after its original installed
            # source/archive/launchd checks, may restore its archived preimage.
            # The observer and a reconstructed context cannot select this path.
            self._control_observation_recovery_owner = (
                os.getpid(), self._transaction_owner_fd,
                transaction.transaction_id, transaction.expected_sha,
            )
            receipt = build_ceo_submit_receipt(
                transaction, admission, armed=prior_armed, now=now,
            )
            self.rollback_ceo_submit(transaction, receipt)
        state = "CEO_SUBMIT_ARMED" if prior_armed else "CEO_SUBMIT_DISARMED"
        return TransactionResult(
            state=state,
            status=state,
            transaction_id=transaction.transaction_id,
            replayed=True,
        )

    def proves_safe_coexistence(self, configs: ConfigEvidence) -> bool:
        """Require the current sealed full-arm generation, never flags alone."""
        try:
            receipt, metadata = load_receipt_file(AUTONOMY_RECEIPT)
            return coexistence_receipt_eligible(
                configs, receipt, metadata, expected_sha=str(configs.control.get("proof_base_sha", "")),
            )
        except (AutonomyRefusal, HostControlError, OSError, ValueError):
            return False

    def incomplete_transaction_operation(self) -> str | None:
        """The operation of an extant marker, or None when the owner is free.

        Read-only, and deliberately narrow: only a marker naming THIS exact
        CEO-submit verb is evidence that the same operation is ambiguous.
        """

        self.effective_uid()
        if not self._transaction_present():
            return None
        try:
            operation = self._manifest().get("operation")
        except TransactionEffectUnknown:
            # An extant marker whose manifest cannot be classified is not proof
            # that this operation is ambiguous: fall through to the typed HOLD in
            # ``require_transaction_absent``.
            return None
        return operation if isinstance(operation, str) else None

    def existing_ceo_submit_receipt(self) -> Mapping[str, Any] | None:
        """The already-sealed receipt document, or None.  Strictly read-only."""

        if not CEO_SUBMIT_RECEIPT.exists() or CEO_SUBMIT_RECEIPT.is_symlink():
            return None
        try:
            raw, _info = _read_root_file(
                CEO_SUBMIT_RECEIPT, modes=frozenset({0o444}), uid=0, gid=0
            )

            def object_pairs(pairs):
                value = {}
                for key, item in pairs:
                    if key in value:
                        raise ValueError("duplicate receipt field")
                    value[key] = item
                return value

            payload = json.loads(raw.decode("utf-8"), object_pairs_hook=object_pairs)
        except HostControlError:
            return None
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return None
        if not isinstance(payload, dict):
            return None
        return payload


class ProductionGatewayPublicationHost(ProductionCeoSubmitHost):
    """Root-only OS gateway publication inside the ONE existing transaction owner.

    The publication replaces exactly three fixed targets -- the installed MCP
    configuration, the MCP LaunchDaemon plist, and the root-sealed OS
    commission publication grant -- while the Executive host is stopped,
    quiescent and unarmed.  It reuses ``AUTONOMY_TRANSACTION``, that marker's
    manifest, generation seal, publication mutex and completion path.  There is
    no second lock, no installer, no dispatcher, no service action and no
    credential access: the marker is created complete before the first target
    write, every write is exact-CAS against the sealed preimage, and any
    interruption leaves the original marker UNKNOWN for explicit
    reconciliation.  The Studio publication seat is observed, never operated:
    its real UID-501 account, fixed paths, sealed definition, stopped launchd
    state and absent port are admission predicates, not caller arguments.
    """

    # The compiler's frozen logical paths and kinds, joined by equality to the
    # owner's own fixed targets.  Nothing here is caller selectable.
    _GATEWAY_TARGETS = (
        ("mcp_config_bytes", "mcp_config_sha256"),
        ("mcp_plist_bytes", "mcp_plist_sha256"),
        ("commission_grant_bytes", "commission_grant_sha256"),
    )

    def __init__(self) -> None:
        super().__init__()
        self._sealed_gateway: dict[str, Any] | None = None
        self._prior_grant_bytes: bytes | None = None

    # ------------------------------------------------------------------
    # Closed compiler adapter.  The publication compiler is a separate pure
    # module exposing one frozen candidate: exact before-images plus a tuple
    # of GatewayArtifact(path, kind, content, sha256, byte_count).  This small
    # adapter translates those actual fields onto the owner's existing internal
    # map and refuses anything that drifts from the bytes this host qualified
    # itself.  No flattened attribute expectation is invented here.
    # ------------------------------------------------------------------

    def _compile_gateway_candidates(
        self,
        prior_mcp_config_bytes: bytes,
        prior_mcp_plist_bytes: bytes,
        *,
        publication_document: Mapping[str, Any],
        helper_hashes: Mapping[str, str],
        expected_sha: str,
        bundle_digest: str,
    ) -> Mapping[str, Any]:
        try:
            from ops.executive_os import os_gateway_publication as compiler
        except ImportError as exc:
            raise GatewayPublicationError("gateway_compiler_unavailable") from exc
        try:
            candidate = compiler.compile_gateway_candidates(
                prior_mcp_config_bytes,
                prior_mcp_plist_bytes,
                expected_release_sha=expected_sha,
                expected_bundle_digest=bundle_digest,
                qualified_publication_inputs={
                    "publication_document": publication_document,
                    "auth_helper_sha256": helper_hashes["auth_helper_sha256"],
                    "file_helper_sha256": helper_hashes["file_helper_sha256"],
                },
            )
        except (GatewayPublicationError, TransactionEffectUnknown):
            raise
        except Exception as exc:
            raise GatewayPublicationError("gateway_compiler_contract_invalid") from exc
        return self._bind_gateway_candidate(
            compiler,
            candidate,
            prior_mcp_config_bytes,
            prior_mcp_plist_bytes,
            expected_sha=expected_sha,
            bundle_digest=bundle_digest,
        )

    def _bind_gateway_candidate(
        self,
        compiler: Any,
        candidate: Any,
        prior_mcp_config_bytes: bytes,
        prior_mcp_plist_bytes: bytes,
        *,
        expected_sha: str,
        bundle_digest: str,
    ) -> Mapping[str, Any]:
        """Bind the real candidate fields onto the existing internal map."""

        def invalid() -> GatewayPublicationError:
            return GatewayPublicationError("gateway_compiler_contract_invalid")

        expected_paths = (
            (os.fspath(OS_GATEWAY_MCP_CONFIG), "executive-mcp-config",
             compiler.MCP_CONFIG_PATH),
            (os.fspath(OS_GATEWAY_MCP_PLIST), "executive-mcp-plist",
             compiler.MCP_PLIST_PATH),
            (os.fspath(OS_GATEWAY_COMMISSION_GRANT), "os-commission-publication",
             compiler.COMMISSION_CONFIG_PATH),
        )
        try:
            artifacts = candidate.artifacts
            publication_before = candidate.publication_before_sha256
            schema = candidate.schema
            operation = candidate.operation
            candidate_release = candidate.expected_release_sha
            candidate_bundle = candidate.expected_bundle_digest
            before_config = candidate.before_mcp_bytes
            before_plist = candidate.before_plist_bytes
            before_config_sha = candidate.before_mcp_sha256
            before_plist_sha = candidate.before_plist_sha256
        except AttributeError as exc:
            raise invalid() from exc
        if (
            schema != compiler.SCHEMA
            or operation != OS_GATEWAY_PUBLICATION
            or candidate_release != expected_sha
            or candidate_bundle != bundle_digest
            or type(before_config) is not bytes
            or type(before_plist) is not bytes
            or before_config != prior_mcp_config_bytes
            or before_plist != prior_mcp_plist_bytes
            or before_config_sha != sha256_bytes(prior_mcp_config_bytes)
            or before_plist_sha != sha256_bytes(prior_mcp_plist_bytes)
            or publication_before is not None
            or type(artifacts) is not tuple
            or len(artifacts) != len(expected_paths)
        ):
            raise invalid()
        values: dict[str, Any] = {
            "operation": operation,
            "release_sha": candidate_release,
            "bundle_digest": candidate_bundle,
            "prior_mcp_config_bytes": before_config,
            "prior_mcp_plist_bytes": before_plist,
        }
        for index, (payload_name, digest_name) in enumerate(self._GATEWAY_TARGETS):
            artifact = artifacts[index]
            target_path, target_kind, compiler_path = expected_paths[index]
            try:
                path = artifact.path
                kind = artifact.kind
                content = artifact.content
                artifact_sha = artifact.sha256
                byte_count = artifact.byte_count
            except AttributeError as exc:
                raise invalid() from exc
            if (
                type(path) is not str
                or type(kind) is not str
                or type(content) is not bytes
                or not content
                or path != target_path
                or path != os.fspath(compiler_path)
                or kind != target_kind
                or byte_count != len(content)
                or type(artifact_sha) is not str
                or re.fullmatch(r"[0-9a-f]{64}", artifact_sha) is None
                or artifact_sha != sha256_bytes(content)
            ):
                raise invalid()
            values[payload_name] = content
            values[digest_name] = artifact_sha
        for payload_name, digest_name in self._GATEWAY_TARGETS:
            if values[digest_name] != sha256_bytes(values[payload_name]):
                raise invalid()
        return values

    # ------------------------------------------------------------------
    # Root-safe fixed-target reads.
    # ------------------------------------------------------------------

    @staticmethod
    def _gateway_root_file(path: Path, *, code: str) -> bytes:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = -1
        try:
            descriptor = os.open(path, flags)
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != 0
                or info.st_gid != 0
                or stat.S_IMODE(info.st_mode) & 0o022
                or info.st_nlink != 1
                or _has_acl(path)
            ):
                raise GatewayPublicationError(code)
            raw = os.read(descriptor, _GATEWAY_ROOT_FILE_MAX_BYTES + 1)
            if len(raw) > _GATEWAY_ROOT_FILE_MAX_BYTES or os.read(descriptor, 1):
                raise GatewayPublicationError(code)
            after = os.fstat(descriptor)
            if (
                (after.st_dev, after.st_ino, after.st_mode, after.st_size, after.st_nlink)
                != (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_nlink)
            ):
                raise GatewayPublicationError(code)
            return raw
        except GatewayPublicationError:
            raise
        except OSError as exc:
            raise GatewayPublicationError(code) from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    def _grant_observation(self) -> tuple[bool, bytes]:
        """The commission grant preimage: absence is evidence, occupancy is custody."""

        try:
            OS_GATEWAY_COMMISSION_GRANT.lstat()
        except FileNotFoundError:
            return False, b""
        except OSError as exc:
            raise GatewayPublicationError("gateway_grant_state_conflict") from exc
        raw = self._gateway_root_file(
            OS_GATEWAY_COMMISSION_GRANT, code="gateway_grant_state_conflict"
        )
        return True, raw

    # ------------------------------------------------------------------
    # Launch build qualification: the receipt is the target release's own
    # sealed artifact; os_release_assets owns its strict qualification.
    # ------------------------------------------------------------------

    def _gateway_release_tree(self, expected_sha: str) -> str:
        root = SYSTEM_ROOT / "releases" / expected_sha
        try:
            value, _raw = _root_json(
                root / release_manifest.MANIFEST_NAME,
                modes=frozenset({0o444}),
                gid=0,
            )
        except HostControlError as exc:
            raise GatewayPublicationError("gateway_release_tree_invalid") from exc
        tree = value.get("tree_sha")
        if (
            value.get("commit_sha") != expected_sha
            or type(tree) is not str
            or _SHA_RE.fullmatch(tree) is None
        ):
            raise GatewayPublicationError("gateway_release_tree_invalid")
        return tree

    def qualify_launch_publication(
        self, expected_sha: str, tree_sha: str
    ) -> tuple[bytes, dict[str, Any], str]:
        from ops.executive_os import os_release_assets as assets

        release = SYSTEM_ROOT / "releases" / expected_sha
        receipt_path = release / assets.INSTALLED_RECEIPT
        try:
            assets.require_sealed_path(release / "app/mastermind_os", directory=True)
            assets.require_sealed_path(receipt_path)
            receipt_bytes = assets._read(receipt_path, assets.RECEIPT_MAX_BYTES)
            receipt = json.loads(receipt_bytes)
        except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GatewayPublicationError("gateway_launch_receipt_invalid") from exc
        if type(receipt) is not dict or receipt.get("schema") != assets.LAUNCH_SCHEMA:
            raise GatewayPublicationError("gateway_launch_receipt_invalid")
        try:
            resource, _manifest_raw = assets._receipt_launch_inputs(receipt)
            assets._client(receipt["web_client_id"])
        except (ValueError, KeyError, TypeError) as exc:
            raise GatewayPublicationError("gateway_launch_receipt_invalid") from exc
        if (
            receipt.get("source_sha") != expected_sha
            or receipt.get("source_tree") != tree_sha
        ):
            raise GatewayPublicationError("gateway_launch_receipt_invalid")
        try:
            actual, files = assets._capture_dist(release, sealed=True)
            manifest_bytes = files.get("asset-manifest.json")
        except (OSError, ValueError) as exc:
            raise GatewayPublicationError("gateway_launch_receipt_invalid") from exc
        if (
            manifest_bytes is None
            or json.loads(manifest_bytes) != actual
            or assets._hash(manifest_bytes) != receipt["asset_manifest_sha256"]
        ):
            raise GatewayPublicationError("gateway_launch_receipt_invalid")
        bundle_digest = assets._hash(
            assets._canonical(
                {
                    "receipt": assets._hash(receipt_bytes),
                    "files": {
                        name: assets._hash(data)
                        for name, data in sorted(files.items())
                    },
                }
            )
        )
        template = self._gateway_template(receipt["launch_config"])
        document = {
            "schema": assets.LAUNCH_SCHEMA,
            "release_sha": expected_sha,
            "source_tree": tree_sha,
            "release_bundle_digest": bundle_digest,
            "web_client_id": receipt["web_client_id"],
            "executive_resource": resource,
            "launch_config": receipt["launch_config"],
            "launch_config_sha256": receipt["launch_config_sha256"],
            "commission_template": template,
        }
        return receipt_bytes, document, bundle_digest

    def _gateway_template(self, launch_config: str) -> dict[str, Any]:
        """Derive the ONE Root-authorized single Research-only template.

        Every field is an exact mapping from the qualified Launch receipt;
        nothing is caller granted.  The department/execution-profile references
        and their single-entry shape were already enforced by the incumbent
        Launch decoder; the canonical CEO-request bounds are enforced here.
        """
        from control_plane import ceo_request

        try:
            values = json.loads(launch_config)
        except (TypeError, json.JSONDecodeError) as exc:
            raise GatewayPublicationError("gateway_template_refused") from exc
        projects = values.get("projects") if type(values) is dict else None
        profiles = values.get("profiles") if type(values) is dict else None
        if (
            type(projects) is not list
            or len(projects) != 1
            or type(projects[0]) is not dict
            or type(profiles) is not list
            or len(profiles) != 1
            or type(profiles[0]) is not dict
        ):
            raise GatewayPublicationError("gateway_template_refused")
        if profiles[0].get("ref") != "research_only":
            raise GatewayPublicationError("gateway_template_refused")
        priority = values.get("priority")
        from ops.executive_os.os_release_assets import _decode_launch_binding

        try:
            if _decode_launch_binding(values) is None:
                raise ValueError("invalid sealed Launch form")
        except (KeyError, TypeError, ValueError) as exc:
            raise GatewayPublicationError("gateway_template_refused") from exc
        attempt_limit = values.get("attemptLimit", ceo_request.DEFAULT_ATTEMPT_LIMIT)
        template = {
            "workstream": values["workstream"],
            "department": projects[0]["ref"],
            "execution_profile": "research_only",
            "priority": priority,
        }
        # Match the actual browser form exactly, including optional presence.
        for source, target in (
            ("attemptLimit", "attempt_limit"),
            ("allowedWritePaths", "allowed_write_paths"),
            ("validation", "validation"),
        ):
            if source in values:
                template[target] = copy.deepcopy(values[source])
        if (
            template["execution_profile"] not in ceo_request.EXECUTION_PROFILES
            or type(priority) is not int
            or not ceo_request.MIN_PRIORITY <= priority <= ceo_request.MAX_PRIORITY
            or type(attempt_limit) is not int
            or not ceo_request.MIN_ATTEMPT_LIMIT
            <= attempt_limit
            <= ceo_request.MAX_ATTEMPT_LIMIT
        ):
            raise GatewayPublicationError("gateway_template_refused")
        return template

    # ------------------------------------------------------------------
    # Namespace DATA derivation.  These are identity digests, never a live
    # authentication context, token, or expiry claim.
    # ------------------------------------------------------------------

    def qualify_workspace_identity(
        self, prior_mcp_config_bytes: bytes, *, web_client_id: str
    ) -> dict[str, Any]:
        from integrations.business_mcp_auth.claims import _client_ref
        from integrations.business_mcp_auth.contracts import load_resource_policy
        from integrations.mastermind_executive_app.gateway import load_app_policies
        from integrations.mastermind_workspace_app.contract import (
            validate_workspace_bindings,
        )

        try:
            prior = json.loads(prior_mcp_config_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GatewayPublicationError("gateway_workspace_binding_invalid") from exc
        workspace = prior.get("workspace") if type(prior) is dict else None
        if type(workspace) is not dict:
            raise GatewayPublicationError("gateway_workspace_binding_invalid")
        try:
            policy = load_resource_policy(workspace["policy"])
            profiles = validate_workspace_bindings(workspace["bindings"], policy)
            app_policies = load_app_policies(prior["policies"])
        except Exception as exc:
            raise GatewayPublicationError("gateway_workspace_binding_invalid") from exc
        web = profiles["profiles"]["web"]
        if web.get("enabled") is not True or type(web.get("binding")) is not dict:
            raise GatewayPublicationError("gateway_workspace_binding_invalid")
        binding = web["binding"]
        # The SAME actual public client ref: the receipt's real web client id
        # must derive the enrolled binding client under the canonical law.
        if _client_ref({"client_id": web_client_id}, policy.issuer) != binding["client_ref"]:
            raise GatewayPublicationError("gateway_workspace_binding_invalid")
        # The SAME issuer and subject in the existing Executive submit
        # allowlist; every current policy scope/subject/resource stays intact.
        submit = app_policies.submit
        if (
            hashlib.sha256(submit.issuer.encode("utf-8")).hexdigest()
            != binding["issuer_digest"]
            or binding["subject_digest"] not in submit.allowed_subject_digests
        ):
            raise GatewayPublicationError("gateway_submit_allowlist_invalid")
        from ops.executive_os.executive_mcp_entry import OS_EXECUTIVE_RESOURCE

        return {
            "issuer_digest": binding["issuer_digest"],
            "subject_digest": binding["subject_digest"],
            "client_ref": binding["client_ref"],
            "resource": OS_EXECUTIVE_RESOURCE,
        }

    @staticmethod
    def _derived_namespace_scope(identity: Mapping[str, str]) -> str:
        """The one derived namespace grant, from explicit DATA only.

        The incumbent pure stdlib helper
        ``integrations.mastermind_executive_app.principal_namespace`` owns the
        single unchanged canonical domain/NUL/resource-literal recipe.  This
        owner only qualifies its DATA inputs and calls it: no principal
        object, no authenticated context, no expiry claim and no HTTP
        transport is ever constructed here.
        """
        values = {}
        for key in ("issuer_digest", "subject_digest"):
            value = identity.get(key) if isinstance(identity, Mapping) else None
            if (
                type(value) is not str
                or re.fullmatch(r"[0-9a-f]{64}", value) is None
            ):
                raise GatewayPublicationError("gateway_namespace_scope_invalid")
            values[key] = value
        client_ref = identity.get("client_ref")
        resource = identity.get("resource")
        if (
            type(client_ref) is not str
            or not client_ref
            or len(client_ref) > 1024
            or type(resource) is not str
            or not resource
            or len(resource) > 2048
        ):
            raise GatewayPublicationError("gateway_namespace_scope_invalid")
        try:
            from integrations.mastermind_executive_app.principal_namespace import (
                principal_scope_from_identity,
            )
        except ImportError as exc:
            raise GatewayPublicationError("gateway_namespace_scope_invalid") from exc
        try:
            scope = principal_scope_from_identity(
                issuer_digest=values["issuer_digest"],
                subject_digest=values["subject_digest"],
                client_ref=client_ref,
                resource=resource,
            )
        except GatewayPublicationError:
            raise
        except Exception as exc:
            raise GatewayPublicationError("gateway_namespace_scope_invalid") from exc
        if type(scope) is not str or re.fullmatch(r"[0-9a-f]{64}", scope) is None:
            raise GatewayPublicationError("gateway_namespace_scope_invalid")
        return scope

    def _derived_publication_policy(
        self,
        prior_mcp_config_bytes: bytes,
        *,
        expected_sha: str,
        studio_port: int,
    ) -> dict[str, Any]:
        """The one canonical OS submit policy, derived from the incumbent owner.

        ``executive_mcp_entry.build_additional_policies`` derives every sealed
        resource variant from the current prior policies and the exact fixed OS
        resource; exactly one such variant exists and its submit side is the
        fixed publication audience.  The returned mapping is the JSON-shaped
        canonical policy document the existing grant law carries.
        """
        from integrations.mastermind_executive_app.gateway import (
            READ_SCOPE,
            SUBMIT_SCOPE,
            load_app_policies,
        )
        from ops.executive_os.executive_mcp_entry import (
            OS_EXECUTIVE_RESOURCE,
            build_additional_policies,
            validate_document,
        )

        try:
            prior = json.loads(prior_mcp_config_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GatewayPublicationError("gateway_grant_invalid") from exc
        if type(prior) is not dict:
            raise GatewayPublicationError("gateway_grant_invalid")
        proposed = dict(prior)
        for key in ("os_executive_transport", "os_executive_resource",
                    "os_commission_port"):
            proposed.pop(key, None)
        proposed["release_sha"] = expected_sha
        proposed["os_executive_transport"] = True
        proposed["os_executive_resource"] = OS_EXECUTIVE_RESOURCE
        proposed["os_commission_port"] = studio_port
        try:
            validate_document(proposed)
            policies = load_app_policies(proposed["policies"])
            additional = build_additional_policies(proposed, policies)
        except Exception as exc:
            raise GatewayPublicationError("gateway_grant_invalid") from exc
        pairs = [
            pair
            for pair in additional
            if pair.read.resource == OS_EXECUTIVE_RESOURCE
            and pair.submit.resource == OS_EXECUTIVE_RESOURCE
        ]
        if len(pairs) != 1:
            raise GatewayPublicationError("gateway_grant_invalid")
        submit = dataclasses.asdict(pairs[0].submit)
        if (
            submit.get("resource") != OS_EXECUTIVE_RESOURCE
            or submit.get("allowed_algorithms") != ("RS256",)
            or tuple(submit.get("required_scopes") or ())
            != tuple(sorted((READ_SCOPE, SUBMIT_SCOPE)))
        ):
            raise GatewayPublicationError("gateway_grant_invalid")
        return {
            key: list(value) if type(value) is tuple else value
            for key, value in submit.items()
        }

    def _helper_hashes(self, expected_sha: str) -> dict[str, str]:
        release = SYSTEM_ROOT / "releases" / expected_sha
        hashes: dict[str, str] = {}
        for name, relative in (
            ("auth_helper_sha256", "ops/executive_os/os_commission_auth_entry.py"),
            ("file_helper_sha256", "integrations/studio_direct_mcp/commission_file.py"),
        ):
            try:
                raw = self._gateway_root_file(release / relative, code="gateway_helper_source_invalid")
            except GatewayPublicationError:
                raise
            hashes[name] = sha256_bytes(raw)
        return hashes

    # ------------------------------------------------------------------
    # Studio publication seat observation (read-only; never operated).
    # ------------------------------------------------------------------

    def _studio_account_identity(self) -> tuple[Path, int]:
        """The real UID-501 account from the password database, never $HOME."""

        try:
            record = pwd.getpwuid(OS_GATEWAY_STUDIO_UID)
        except KeyError as exc:
            raise GatewayPublicationError("gateway_studio_invalid") from exc
        home = Path(record.pw_dir)
        name = getattr(record, "pw_name", None)
        if (
            record.pw_uid != OS_GATEWAY_STUDIO_UID
            or record.pw_uid == 0
            or type(record.pw_gid) is not int
            or record.pw_gid == 0
            or type(name) is not str
            or not name
            or not home.is_absolute()
        ):
            raise GatewayPublicationError("gateway_studio_invalid")
        # The instance accountLabel is a private_service key, not an OS
        # username. Rejoin the actual UID-501 pwd principal independently.
        try:
            named = pwd.getpwnam(name)
        except (KeyError, TypeError, ValueError) as exc:
            raise GatewayPublicationError("gateway_studio_invalid") from exc
        if (named.pw_uid, named.pw_gid, named.pw_dir, named.pw_name) != (
            record.pw_uid, record.pw_gid, record.pw_dir, name
        ):
            raise GatewayPublicationError("gateway_studio_invalid")
        return home, record.pw_gid

    def _launchd_state(self, target: str) -> str:
        """Read-only launchd observation: absent | registered | running."""

        completed = subprocess.run(
            ["/bin/launchctl", "print", target],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
        if completed.returncode == 113:
            return "absent"
        if completed.returncode != 0:
            raise GatewayPublicationError("gateway_studio_invalid")
        state = None
        pid = None
        for line in completed.stdout.decode("utf-8", "replace").splitlines():
            stripped = line.strip()
            if state is None and stripped.startswith("state = "):
                state = stripped.split("=", 1)[1].strip()
            elif stripped.startswith("pid = "):
                raw = stripped.split("=", 1)[1].strip()
                if raw.isdigit():
                    pid = int(raw)
        if state is None:
            raise GatewayPublicationError("gateway_studio_invalid")
        if (pid is not None and pid > 0) or state == "running":
            return "running"
        return "registered"

    def _studio_port_absent(self) -> bool:
        completed = subprocess.run(
            ["/usr/sbin/lsof", "-nP", f"-iTCP:{OS_GATEWAY_STUDIO_PORT}", "-sTCP:LISTEN"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
        if completed.returncode == 1:
            return True
        if completed.returncode == 0:
            return False
        raise GatewayPublicationError("gateway_studio_invalid")

    def _studio_file_bytes(
        self, path: Path, studio_uid: int, studio_gid: int
    ) -> bytes:
        try:
            before = path.lstat()
        except OSError as exc:
            raise GatewayPublicationError("gateway_studio_invalid") from exc
        if (
            stat.S_ISLNK(before.st_mode)
            or not stat.S_ISREG(before.st_mode)
            or before.st_uid != studio_uid
            or before.st_gid != studio_gid
            or stat.S_IMODE(before.st_mode) & 0o022
            or before.st_nlink != 1
            or before.st_size <= 0
            or before.st_size > _GATEWAY_STUDIO_FILE_MAX_BYTES
            or _has_acl(path)
        ):
            raise GatewayPublicationError("gateway_studio_invalid")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = -1
        try:
            descriptor = os.open(path, flags)
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
                or opened.st_size != before.st_size
            ):
                raise GatewayPublicationError("gateway_studio_invalid")
            raw = os.read(descriptor, _GATEWAY_STUDIO_FILE_MAX_BYTES + 1)
            if len(raw) != before.st_size or os.read(descriptor, 1):
                raise GatewayPublicationError("gateway_studio_invalid")
            after = os.fstat(descriptor)
            if (
                not stat.S_ISREG(after.st_mode)
                or (after.st_dev, after.st_ino, after.st_mode, after.st_size, after.st_nlink)
                != (opened.st_dev, opened.st_ino, opened.st_mode, opened.st_size, opened.st_nlink)
            ):
                raise GatewayPublicationError("gateway_studio_invalid")
        except GatewayPublicationError:
            raise
        except OSError as exc:
            raise GatewayPublicationError("gateway_studio_invalid") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        identity = lambda info: (
            info.st_dev,
            info.st_ino,
            info.st_mode,
            info.st_uid,
            info.st_gid,
            info.st_nlink,
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
        )
        try:
            current = path.lstat()
        except OSError as exc:
            raise GatewayPublicationError("gateway_studio_invalid") from exc
        if identity(before) != identity(current):
            raise GatewayPublicationError("gateway_studio_invalid")
        return raw

    @staticmethod
    def _studio_tool_custody(
        tool: Path,
        home: Path,
        studio_uid: int,
        studio_gid: int,
        *,
        executable: bool,
    ) -> None:
        """Actual Studio custody over the tool AND every ancestor, pre-open.

        The whole chain from the fixed Studio home down to the tool must be
        real, UID-501/GID-exact, non-symlinked, ACL-free directories that the
        Studio identity can actually traverse, and the leaf must be a single-
        link bounded regular file the Studio identity can actually read (and
        execute for the interpreter).  Nothing is opened before this holds, so
        a manifest can never aim Root at protected foreign bytes.
        """

        current = tool.parent
        while True:
            try:
                info = current.lstat()
            except OSError as exc:
                raise GatewayPublicationError("gateway_studio_invalid") from exc
            if (
                stat.S_ISLNK(info.st_mode)
                or not stat.S_ISDIR(info.st_mode)
                or info.st_uid != studio_uid
                or info.st_gid != studio_gid
                or stat.S_IMODE(info.st_mode) & 0o022
                or not stat.S_IMODE(info.st_mode) & 0o500
                or _has_acl(current)
            ):
                raise GatewayPublicationError("gateway_studio_invalid")
            if current == home:
                break
            parent = current.parent
            if parent == current:
                raise GatewayPublicationError("gateway_studio_invalid")
            current = parent
        try:
            info = tool.lstat()
        except OSError as exc:
            raise GatewayPublicationError("gateway_studio_invalid") from exc
        mode = stat.S_IMODE(info.st_mode)
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or info.st_uid != studio_uid
            or info.st_gid != studio_gid
            or mode & 0o022
            or info.st_nlink != 1
            or not 0 < info.st_size <= _GATEWAY_STUDIO_FILE_MAX_BYTES
            or not mode & stat.S_IRUSR
            or (executable and not mode & stat.S_IXUSR)
            or _has_acl(tool)
        ):
            raise GatewayPublicationError("gateway_studio_invalid")

    def observe_studio(self, expected_sha: str) -> GatewayStudioEvidence:
        from integrations.studio_direct_mcp import private_service

        home, studio_gid = self._studio_account_identity()
        studio_uid = OS_GATEWAY_STUDIO_UID
        base = home / _GATEWAY_STUDIO_BASE_REL
        plist_path = home / _GATEWAY_STUDIO_PLIST_REL
        release = SYSTEM_ROOT / "releases" / expected_sha
        source = release / "integrations/studio_direct_mcp"
        manifest_path = base / "manifest.json"
        config_path = base / "config.json"

        # Fixed-tree custody: every directory from the base through the derived
        # home is a real, expected-identity, non-symlinked, ACL-free,
        # foreign-write-free directory.
        current = base
        while True:
            try:
                info = current.lstat()
            except OSError as exc:
                raise GatewayPublicationError("gateway_studio_invalid") from exc
            if (
                stat.S_ISLNK(info.st_mode)
                or not stat.S_ISDIR(info.st_mode)
                or info.st_uid != studio_uid
                or info.st_gid != studio_gid
                or stat.S_IMODE(info.st_mode) & 0o022
                or _has_acl(current)
            ):
                raise GatewayPublicationError("gateway_studio_invalid")
            if current == home:
                break
            parent = current.parent
            if parent == current:
                raise GatewayPublicationError("gateway_studio_invalid")
            current = parent

        manifest_raw = self._studio_file_bytes(manifest_path, studio_uid, studio_gid)
        config_raw = self._studio_file_bytes(config_path, studio_uid, studio_gid)
        agent_plist_raw = self._studio_file_bytes(plist_path, studio_uid, studio_gid)
        try:
            manifest = json.loads(manifest_raw)
            config = json.loads(config_raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GatewayPublicationError("gateway_studio_invalid") from exc
        if type(manifest) is not dict or manifest.get("version") != 2:
            raise GatewayPublicationError("gateway_studio_invalid")
        # The runtime seal is REQUIRED: an absent, non-canonical or drifting
        # dependency tree digest never observes as this publication seat.
        dependency = manifest.get("dependencyTreeHash")
        if (
            type(dependency) is not str
            or re.fullmatch(r"[0-9a-f]{64}", dependency) is None
        ):
            raise GatewayPublicationError("gateway_studio_invalid")
        try:
            if not private_service._valid_manifest(
                manifest, OS_GATEWAY_STUDIO_ACCOUNT, OS_GATEWAY_STUDIO_LABEL
            ):
                raise GatewayPublicationError("gateway_studio_invalid")
            source_files = private_service._check_source_files(source)
            incoming = {
                item.name: private_service._sha256_file(item) for item in source_files
            }
        except GatewayPublicationError:
            raise
        except SystemExit as exc:
            raise GatewayPublicationError("gateway_studio_invalid") from exc
        files = manifest["files"]
        node = Path(manifest["node"])
        backend = Path(manifest["backend"])
        if (
            manifest.get("host") != "127.0.0.1"
            or manifest.get("port") != OS_GATEWAY_STUDIO_PORT
            or manifest.get("source") != os.fspath(source)
            or not node.is_absolute()
            or not backend.is_absolute()
            or incoming != files
        ):
            raise GatewayPublicationError("gateway_studio_invalid")
        # The staged config is the one closed repository-workspace profile,
        # WITHOUT the commission opt-in, on the fixed loopback port.
        if (
            type(config) is not dict
            or config.get("accountLabel") != OS_GATEWAY_STUDIO_ACCOUNT
            or config.get("host") != "127.0.0.1"
            or config.get("port") != OS_GATEWAY_STUDIO_PORT
            or config.get("command") != os.fspath(node)
            or config.get("args") != [os.fspath(backend), "--no-onboarding"]
            or config.get("cwd") != os.fspath(home)
            or config.get("repositoryWorkspaces")
            != {"enabled": True, "allowedRepositories": ["mastermind", "macro", "terminal"]}
            or "commissionPublication" in config
            or "fabricOnly" in config
            or type(config.get("gitPublish")) is not dict
            or config["gitPublish"].get("enabled") is not True
        ):
            raise GatewayPublicationError("gateway_studio_invalid")

        # STOPPED identity proof before the expensive byte qualification.
        self._require_studio_stopped()

        try:
            for name in files:
                staged = base / name
                info = staged.lstat()
                if (
                    stat.S_ISLNK(info.st_mode)
                    or not stat.S_ISREG(info.st_mode)
                    or info.st_uid != studio_uid
                    or info.st_gid != studio_gid
                    or stat.S_IMODE(info.st_mode) & 0o022
                    or info.st_nlink != 1
                    or _has_acl(staged)
                ):
                    raise GatewayPublicationError("gateway_studio_invalid")
            installed_files = private_service._installed_file_hashes(
                base, tuple(files)
            )
            if installed_files != files:
                raise GatewayPublicationError("gateway_studio_invalid")
            # The observed manifest never redirects Root into protected
            # arbitrary files: node and backend are qualified to actual
            # Studio custody over EVERY ancestor, with real owner
            # readability/traversal, before this owner opens or hashes a
            # single byte.  A root-owned or otherwise foreign payload target
            # refuses here, whatever self-hashes the manifest carries.
            for tool, executable in ((node, True), (backend, False)):
                self._studio_tool_custody(
                    tool, home, studio_uid, studio_gid, executable=executable
                )
            node_hash = private_service._stable_regular_file_hash(node, label="studio node")
            backend_hash = private_service._stable_regular_file_hash(
                backend, label="studio backend"
            )
            if node_hash != manifest["nodeHash"] or backend_hash != manifest["backendHash"]:
                raise GatewayPublicationError("gateway_studio_invalid")
            if private_service._dependency_tree_hash(
                base / "node_modules"
            ) != dependency:
                raise GatewayPublicationError("gateway_studio_invalid")
        except GatewayPublicationError:
            raise
        except SystemExit as exc:
            raise GatewayPublicationError("gateway_studio_invalid") from exc

        # STOPPED identity proof again, after the expensive qualification.
        self._require_studio_stopped()

        try:
            agent_plist = plistlib.loads(agent_plist_raw)
        except (plistlib.InvalidFileException, ValueError) as exc:
            raise GatewayPublicationError("gateway_studio_invalid") from exc
        expected_argv = private_service._expected_argv(
            node,
            base / private_service.PRIVATE_GATEWAY_NAME,
            config_path,
        )
        if (
            not isinstance(agent_plist, dict)
            or agent_plist.get("Label") != OS_GATEWAY_STUDIO_LABEL
            or agent_plist.get("ProgramArguments") != expected_argv
        ):
            raise GatewayPublicationError("gateway_studio_invalid")

        definition = {
            "account": OS_GATEWAY_STUDIO_ACCOUNT,
            "label": OS_GATEWAY_STUDIO_LABEL,
            "host": "127.0.0.1",
            "port": OS_GATEWAY_STUDIO_PORT,
            "studio_uid": studio_uid,
            "studio_gid": studio_gid,
            "home": os.fspath(home),
            "base": os.fspath(base),
            "launchd_plist": os.fspath(plist_path),
            "source": os.fspath(source),
            "node": os.fspath(node),
            "backend": os.fspath(backend),
            "node_sha256": node_hash,
            "backend_sha256": backend_hash,
            "dependency_tree_sha256": dependency,
            "manifest_sha256": sha256_bytes(manifest_raw),
            "config_sha256": sha256_bytes(config_raw),
            "launchd_plist_sha256": sha256_bytes(agent_plist_raw),
            "files": dict(sorted(files.items())),
        }
        return GatewayStudioEvidence(
            studio_uid=studio_uid,
            studio_gid=studio_gid,
            account=OS_GATEWAY_STUDIO_ACCOUNT,
            label=OS_GATEWAY_STUDIO_LABEL,
            port=OS_GATEWAY_STUDIO_PORT,
            home=home,
            base=base,
            plist=plist_path,
            source=source,
            node=node,
            backend=backend,
            node_sha256=node_hash,
            backend_sha256=backend_hash,
            dependency_tree_sha256=dependency,
            definition_sha256=sha256_bytes(_encoded_json(definition)),
        )

    def _require_studio_stopped(self) -> None:
        state = self._launchd_state(
            f"gui/{OS_GATEWAY_STUDIO_UID}/{OS_GATEWAY_STUDIO_LABEL}"
        )
        if state == "running":
            raise GatewayPublicationError("gateway_studio_running")
        if not self._studio_port_absent():
            raise GatewayPublicationError("gateway_port_occupied")

    def _gateway_service_enabled(self) -> bool:
        """The incumbent MCP daemon override table: structurally complete.

        Read-only observation of ``launchctl print-disabled system`` with the
        incumbent controller's law: a complete table without this label's row
        means default-enabled; an explicit disabled/true row refuses.
        """

        completed = subprocess.run(
            ["/bin/launchctl", "print-disabled", "system"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
        if completed.returncode != 0:
            raise GatewayPublicationError("gateway_mcp_generation_invalid")
        label = '"' + OS_GATEWAY_MCP_LABEL + '"'
        state = 0
        header = footer = invalid = seen = disabled = 0
        for line in completed.stdout.decode("utf-8", "replace").splitlines():
            fields = line.split()
            if not fields:
                continue
            if state == 0 and fields == ["disabled", "services", "=", "{"]:
                state, header = 1, header + 1
                continue
            if state == 1 and fields == ["}"]:
                state, footer = 2, footer + 1
                continue
            if (
                state == 1
                and len(fields) == 3
                and fields[1] == "=>"
                and fields[0].startswith('"')
                and fields[0].endswith('"')
                and fields[2] in ("enabled", "disabled", "true", "false")
            ):
                if fields[0] == label:
                    if seen:
                        invalid = 1
                        continue
                    seen = 1
                    if fields[2] in ("disabled", "true"):
                        disabled = 1
                continue
            invalid = 1
        if state != 2 or header != 1 or footer != 1 or invalid or seen > 1 or disabled:
            raise GatewayPublicationError("gateway_mcp_generation_invalid")
        return True

    def require_gateway_generation_current(
        self,
        *,
        plist_sha256s: frozenset[str],
        release_shas: frozenset[str] | None = None,
    ) -> str:
        """The incumbent MCP daemon stays enabled and running, qualified.

        The accepted release ordering keeps the incumbent MCP enabled and
        running THROUGH this publication; the normal service-control
        restart-gateway later observes enabled+running itself and owns its own
        stop and start.  This owner therefore observes — never operates — the
        current generation: the installed launchd job definition must be the
        closed installed gateway profile pinned to one of the exact releases
        (when given) and exactly one of the exact plist images this owner
        already holds, and the daemon must be enabled and running now.  No
        stop, start or activation happens here, and the custody of any live
        operation stays held externally; this observation never claims to
        clear it.
        """

        from control_plane import executive_installed_peer as installed

        topology = installed._role_topology("gateway")
        budget = installed._Budget(installed._SERVICE_BUDGET_SECONDS)
        try:
            observation = installed._verify_role_plist(topology, budget)
        except GatewayPublicationError:
            raise
        except Exception as exc:
            raise GatewayPublicationError("gateway_mcp_generation_invalid") from exc
        if (
            type(observation.release) is not str
            or observation.digest not in plist_sha256s
            or (release_shas is not None and observation.release not in release_shas)
        ):
            raise GatewayPublicationError("gateway_mcp_generation_invalid")
        self._gateway_service_enabled()
        if self._launchd_state(f"system/{OS_GATEWAY_MCP_LABEL}") != "running":
            raise GatewayPublicationError("gateway_mcp_generation_invalid")
        return observation.release

    # ------------------------------------------------------------------
    # Actual origin admission: Darwin root plus the selected sealed source.
    # Root UID alone, and a self-reported expected SHA alone, never admit.
    # ------------------------------------------------------------------

    def require_gateway_module_origin(self, expected_sha: str) -> None:
        """The real installed release's own module and controller origin.

        This composition may only run as actual root on Darwin, from the fixed
        installed release directory the closed service-control entry itself
        execs: the module path, its controller sibling and the whole chain
        under SYSTEM_ROOT must be root-custodied, and the trusted release seal
        must join the same expected SHA.  A direct unsealed invocation refuses
        here, before any protected configuration, receipt or marker IO.
        """

        if sys.platform != "darwin":
            raise GatewayPublicationError("gateway_target_invalid")
        if os.getuid() != 0 or os.geteuid() != 0:
            raise GatewayPublicationError("gateway_target_invalid")
        if type(expected_sha) is not str or _SHA_RE.fullmatch(expected_sha) is None:
            raise GatewayPublicationError("gateway_target_invalid")
        release = SYSTEM_ROOT / "releases" / expected_sha
        entry_directory = release / "ops/executive_os"
        expected_module = entry_directory / "autonomy_control.py"
        expected_controller = entry_directory / "service-control.sh"
        try:
            module_path = Path(__file__).absolute()
        except (TypeError, ValueError) as exc:
            raise GatewayPublicationError("gateway_target_invalid") from exc
        if module_path != expected_module:
            raise GatewayPublicationError("gateway_target_invalid")
        try:
            self._sealed_origin_chain(release)
            self._sealed_origin_file(module_path)
            self._sealed_origin_file(expected_controller)
        except OSError as exc:
            raise GatewayPublicationError("gateway_target_invalid") from exc
        # Verify the actual bytes against the normal retained release seal;
        # a manifest's self-reported commit/tree is not a content check.
        tree_sha = self._gateway_release_tree(expected_sha)
        try:
            release_manifest.verify(release, expected_sha, tree_sha)
        except Exception as exc:
            raise GatewayPublicationError("gateway_target_invalid") from exc

    @staticmethod
    def _sealed_origin_chain(release: Path) -> None:
        current = release
        while True:
            info = current.lstat()
            if (
                stat.S_ISLNK(info.st_mode)
                or not stat.S_ISDIR(info.st_mode)
                or info.st_uid != 0
                or info.st_gid != 0
                or stat.S_IMODE(info.st_mode) & 0o022
                or _has_acl(current)
            ):
                raise GatewayPublicationError("gateway_target_invalid")
            if current.parent == current:
                return
            parent = current.parent
            if parent == current:
                raise GatewayPublicationError("gateway_target_invalid")
            current = parent

    @staticmethod
    def _sealed_origin_file(path: Path) -> None:
        info = path.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or info.st_gid != 0
            or stat.S_IMODE(info.st_mode) & 0o022
            or info.st_nlink != 1
            or _has_acl(path)
        ):
            raise GatewayPublicationError("gateway_target_invalid")

    # ------------------------------------------------------------------
    # Stopped, quiescent, unarmed admission posture.
    # ------------------------------------------------------------------

    def checked_gateway_configs(
        self,
        expected_sha: str,
        *,
        allowed_plist_sha256s: frozenset[str],
        allowed_release_shas: frozenset[str] | None = None,
    ) -> ConfigEvidence:
        self.require_services_already_stopped()
        self.require_service_uids_quiescent()
        self.require_gateway_generation_current(
            plist_sha256s=allowed_plist_sha256s,
            release_shas=allowed_release_shas,
        )
        prior = self.load_unarmed_configs(expected_sha)
        self.require_runtime_quiescent(prior)
        return prior

    def require_gateway_receipt_absent(self) -> None:
        """ONE terminal receipt: an existing valid receipt refuses publication."""

        if not OS_GATEWAY_RECEIPT.exists() and not OS_GATEWAY_RECEIPT.is_symlink():
            return
        try:
            _root_json(OS_GATEWAY_RECEIPT, modes=frozenset({0o444}), uid=0, gid=0)
        except HostControlError as exc:
            raise GatewayPublicationError("gateway_receipt_invalid") from exc
        raise GatewayPublicationError("gateway_receipt_conflict")

    # ------------------------------------------------------------------
    # The one canonical audit-directory prerequisite.
    #
    # The fixed leaf below the qualified fixed parent is the ONLY node this
    # owner may create, and only through a held fixed-parent descriptor with
    # an exclusive no-follow mkdir, a parent fsync and real UID/GID plus mode
    # proven on the held same inode.  Its before-identity (qualified present
    # custody or explicit absence) plus the planned metadata are bound in the
    # retained intent BEFORE the create and before the three DATA target
    # writes.  A poisoned file, a held lock or an unsafe topology keeps the
    # leaf closed: nothing is ever repaired, deleted, chowned blind or
    # regenerated here.
    # ------------------------------------------------------------------

    @staticmethod
    def _gateway_audit_parent() -> Path:
        return _GATEWAY_AUDIT_DIRECTORY.parent

    def _audit_parent_topology(self) -> None:
        """The fixed parent chain from the leaf's parent through SYSTEM_ROOT."""

        current = self._gateway_audit_parent()
        while True:
            try:
                info = current.lstat()
            except OSError as exc:
                raise GatewayPublicationError("gateway_audit_directory_invalid") from exc
            if (
                stat.S_ISLNK(info.st_mode)
                or not stat.S_ISDIR(info.st_mode)
                or info.st_uid != 0
                or info.st_gid != 0
                or stat.S_IMODE(info.st_mode) & 0o022
                or _has_acl(current)
            ):
                raise GatewayPublicationError("gateway_audit_directory_invalid")
            if current == SYSTEM_ROOT:
                return
            parent = current.parent
            if parent == current:
                raise GatewayPublicationError("gateway_audit_directory_invalid")
            current = parent

    def _audit_entry_law(self, path: Path, studio_uid: int, studio_gid: int) -> None:
        """Bounded metadata and existing sink laws for one contained entry."""

        try:
            info = path.lstat()
        except OSError as exc:
            raise GatewayPublicationError("gateway_audit_directory_invalid") from exc
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or info.st_uid != studio_uid
            or info.st_gid != studio_gid
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
            or _has_acl(path)
        ):
            raise GatewayPublicationError("gateway_audit_directory_invalid")

    def _audit_leaf_occupied(
        self, directory: Path, studio_uid: int, studio_gid: int
    ) -> None:
        """Bounded flat topology, contained-entry law and lock freedom.

        Only metadata is observed; no audit file content is ever read here.  A
        subdirectory, a poisoned entry or a lock already held by a live writer
        keeps the whole leaf closed.
        """

        try:
            info = directory.lstat()
            names = os.listdir(directory)
        except OSError as exc:
            raise GatewayPublicationError("gateway_audit_directory_invalid") from exc
        if (
            not stat.S_ISDIR(info.st_mode)
            # Darwin counts regular directory entries in st_nlink; Linux
            # counts subdirectories. Flatness is proved by each entry's
            # no-symlink/regular/single-link metadata law below, not this
            # platform-dependent directory link count.
            or info.st_nlink < 1
            or len(names) > _GATEWAY_AUDIT_ENTRY_MAX_COUNT
        ):
            raise GatewayPublicationError("gateway_audit_directory_invalid")
        flock = getattr(fcntl, "flock", None)
        for name in sorted(names):
            if (
                type(name) is not str
                or not name
                or len(name) > _GATEWAY_AUDIT_ENTRY_NAME_MAX
                or any(ord(character) < 32 or ord(character) == 127 for character in name)
            ):
                raise GatewayPublicationError("gateway_audit_directory_invalid")
            entry = directory / name
            self._audit_entry_law(entry, studio_uid, studio_gid)
            if flock is None:
                continue
            descriptor = -1
            try:
                descriptor = os.open(
                    entry,
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
                )
                flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                flock(descriptor, fcntl.LOCK_UN)
            except OSError as exc:
                raise GatewayPublicationError("gateway_audit_directory_invalid") from exc
            finally:
                if descriptor >= 0:
                    os.close(descriptor)

    def observe_gateway_audit_directory(
        self, *, studio_uid: int, studio_gid: int
    ) -> dict[str, Any]:
        """Qualified present custody or explicit absence of the fixed leaf."""

        self._audit_parent_topology()
        planned = {
            _GATEWAY_AUDIT_STATE_FIELD: "absent",
            _GATEWAY_AUDIT_UID_FIELD: studio_uid,
            _GATEWAY_AUDIT_GID_FIELD: studio_gid,
            _GATEWAY_AUDIT_MODE_FIELD: _GATEWAY_AUDIT_LEAF_MODE,
            _GATEWAY_AUDIT_BEFORE_FIELD: None,
        }
        try:
            info = _GATEWAY_AUDIT_DIRECTORY.lstat()
        except FileNotFoundError:
            return planned
        except OSError as exc:
            raise GatewayPublicationError("gateway_audit_directory_invalid") from exc
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != studio_uid
            or info.st_gid != studio_gid
            or stat.S_IMODE(info.st_mode) != _GATEWAY_AUDIT_LEAF_MODE
            or _has_acl(_GATEWAY_AUDIT_DIRECTORY)
        ):
            raise GatewayPublicationError("gateway_audit_directory_invalid")
        self._audit_leaf_occupied(_GATEWAY_AUDIT_DIRECTORY, studio_uid, studio_gid)
        return {
            _GATEWAY_AUDIT_STATE_FIELD: "present",
            _GATEWAY_AUDIT_UID_FIELD: studio_uid,
            _GATEWAY_AUDIT_GID_FIELD: studio_gid,
            _GATEWAY_AUDIT_MODE_FIELD: _GATEWAY_AUDIT_LEAF_MODE,
            _GATEWAY_AUDIT_BEFORE_FIELD: [info.st_dev, info.st_ino],
        }

    def _establish_gateway_audit_directory(self, manifest: Mapping[str, Any]) -> list[int]:
        """Create ONLY the canonical leaf through the qualified fixed parent."""

        if (
            self._transaction_owner_fd is None
            or self._active_transaction is None
            or self._active_transaction.transaction_id != manifest.get("transaction_id")
        ):
            raise TransactionEffectUnknown()
        self._verify_published_inode(self._transaction_owner_fd)
        parent = self._gateway_audit_parent()
        bound_state = manifest[_GATEWAY_AUDIT_STATE_FIELD]
        bound_uid = manifest[_GATEWAY_AUDIT_UID_FIELD]
        bound_gid = manifest[_GATEWAY_AUDIT_GID_FIELD]
        flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            parent_fd = os.open(parent, flags)
        except OSError as exc:
            raise TransactionEffectUnknown() from exc
        leaf_fd = -1
        try:
            # The bound before-identity must still be exactly the leaf state
            # now, BEFORE any create: an ambiguity stays the original UNKNOWN
            # and nothing is adopted, deleted or regenerated.
            try:
                prior_info = os.stat(
                    _GATEWAY_AUDIT_LEAF_NAME,
                    dir_fd=parent_fd,
                    follow_symlinks=False,
                )
                exists = True
            except FileNotFoundError:
                exists = False
            except OSError as exc:
                raise TransactionEffectUnknown() from exc
            if exists is not (bound_state == "present"):
                raise TransactionEffectUnknown()
            if exists and [prior_info.st_dev, prior_info.st_ino] != manifest[_GATEWAY_AUDIT_BEFORE_FIELD]:
                raise TransactionEffectUnknown()
            try:
                _create_directory(
                    _GATEWAY_AUDIT_LEAF_NAME,
                    _GATEWAY_AUDIT_LEAF_MODE,
                    dir_fd=parent_fd,
                )
                created = True
            except FileExistsError:
                created = False
            except OSError as exc:
                raise TransactionEffectUnknown() from exc
            if created is not (bound_state == "absent"):
                raise TransactionEffectUnknown()
            try:
                os.fsync(parent_fd)
            except OSError as exc:
                raise TransactionEffectUnknown() from exc
            try:
                leaf_fd = os.open(
                    _GATEWAY_AUDIT_LEAF_NAME, flags, dir_fd=parent_fd
                )
                held = os.fstat(leaf_fd)
                if not stat.S_ISDIR(held.st_mode):
                    raise TransactionEffectUnknown()
                if not created and [held.st_dev, held.st_ino] != manifest[_GATEWAY_AUDIT_BEFORE_FIELD]:
                    raise TransactionEffectUnknown()
                if created:
                    os.fchown(leaf_fd, bound_uid, bound_gid)
                    os.fchmod(leaf_fd, _GATEWAY_AUDIT_LEAF_MODE)
                    held = os.fstat(leaf_fd)
                if (
                    held.st_uid != bound_uid
                    or held.st_gid != bound_gid
                    or stat.S_IMODE(held.st_mode) != _GATEWAY_AUDIT_LEAF_MODE
                ):
                    raise TransactionEffectUnknown()
                # The held descriptor and the canonical name must be the SAME
                # inode before any target write follows.
                try:
                    named = _GATEWAY_AUDIT_DIRECTORY.lstat()
                except OSError as exc:
                    raise TransactionEffectUnknown() from exc
                if (named.st_dev, named.st_ino) != (held.st_dev, held.st_ino):
                    raise TransactionEffectUnknown()
                try:
                    os.fsync(leaf_fd)
                except OSError as exc:
                    raise TransactionEffectUnknown() from exc
            except OSError as exc:
                raise TransactionEffectUnknown() from exc
        finally:
            if leaf_fd >= 0:
                os.close(leaf_fd)
            os.close(parent_fd)
        observation = self.observe_gateway_audit_directory(
            studio_uid=bound_uid, studio_gid=bound_gid
        )
        if (observation[_GATEWAY_AUDIT_STATE_FIELD] != "present"
                or observation[_GATEWAY_AUDIT_BEFORE_FIELD] != [held.st_dev, held.st_ino]):
            raise TransactionEffectUnknown()
        return [held.st_dev, held.st_ino]

    def _verify_gateway_audit_directory(self, manifest: Mapping[str, Any]) -> None:
        """Postimage-only metadata proof of the bound audit prerequisite."""

        try:
            self._audit_parent_topology()
            info = _GATEWAY_AUDIT_DIRECTORY.lstat()
        except GatewayPublicationError:
            raise
        except OSError as exc:
            raise TransactionEffectUnknown() from exc
        if (
            not _gateway_inode_identity(manifest.get(_GATEWAY_AUDIT_AFTER_FIELD))
            or [info.st_dev, info.st_ino] != manifest[_GATEWAY_AUDIT_AFTER_FIELD]
            or stat.S_ISLNK(info.st_mode)
            or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != manifest[_GATEWAY_AUDIT_UID_FIELD]
            or info.st_gid != manifest[_GATEWAY_AUDIT_GID_FIELD]
            or stat.S_IMODE(info.st_mode) != manifest[_GATEWAY_AUDIT_MODE_FIELD]
            or _has_acl(_GATEWAY_AUDIT_DIRECTORY)
        ):
            raise TransactionEffectUnknown()
        try:
            self._audit_leaf_occupied(
                _GATEWAY_AUDIT_DIRECTORY,
                manifest[_GATEWAY_AUDIT_UID_FIELD],
                manifest[_GATEWAY_AUDIT_GID_FIELD],
            )
        except GatewayPublicationError as exc:
            raise TransactionEffectUnknown() from exc

    # ------------------------------------------------------------------
    # Marker lifecycle for the gateway operation.
    # ------------------------------------------------------------------

    def _manifest_document(
        self, transaction: TransactionContext, phase: str, *, operation: str
    ) -> dict[str, Any]:
        value = super()._manifest_document(transaction, phase, operation=operation)
        if operation != OS_GATEWAY_PUBLICATION or self._sealed_gateway is None:
            raise TransactionEffectUnknown()
        # Recovery may restore prior bytes, but never relabel the original
        # identity: every partial postimage remains classifiable after crash.
        value.update(self._sealed_gateway)
        value["phase"] = phase
        return value

    def _persist_phase(self, transaction: TransactionContext, phase: str, *, operation: str | None = None) -> None:
        if phase != "AUDIT_DIRECTORY_READY":
            super()._persist_phase(transaction, phase, operation=operation)
            return
        if self._transaction_owner_fd is None or self._active_transaction != transaction:
            raise TransactionEffectUnknown()
        self._verify_published_inode(self._transaction_owner_fd)
        current = self._manifest()
        value = self._manifest_document(transaction, phase, operation=OS_GATEWAY_PUBLICATION)
        if (
            current.get("operation") != OS_GATEWAY_PUBLICATION
            or current.get("phase") != "LOCKED"
            or operation not in (None, OS_GATEWAY_PUBLICATION)
            or {key: item for key, item in current.items()
                if key not in ("phase", _GATEWAY_AUDIT_AFTER_FIELD)}
            != {key: item for key, item in value.items()
                if key not in ("phase", _GATEWAY_AUDIT_AFTER_FIELD)}
        ):
            raise TransactionEffectUnknown()
        self._verify_gateway_audit_directory(value)
        _atomic_file(self._manifest_path(), _encoded_json(value), mode=0o400,
                     uid=0, gid=0, replace=True)

    def _seal_generation(
        self, generation: Path, transaction: TransactionContext, *, operation: str
    ) -> None:
        if operation != OS_GATEWAY_PUBLICATION or self._prior_grant_bytes is None:
            raise TransactionEffectUnknown()
        # The gateway publication is wholly disarmed: the armed CEO coexistence
        # transformer cannot apply.  The plain global-owner seal carries both
        # unchanged config preimages and the sealed gateway identity manifest.
        ProductionTransactionHost._seal_generation(
            self, generation, transaction, operation=operation
        )
        _atomic_file(
            generation / _GATEWAY_GRANT_ARCHIVE,
            self._prior_grant_bytes,
            mode=0o400,
            uid=0,
            gid=0,
            replace=False,
        )
        _fsync_directory(generation)

    def new_transaction_id(self) -> str:
        # Unlike recovery-oriented inherited helpers, a fresh publication may
        # never lock/adopt a marker that appeared after its absence preflight.
        return f"autonomy-{secrets.token_hex(6)}"

    def _recheck_gateway_bound(self, transaction: TransactionContext) -> None:
        if (
            self._transaction_owner_fd is None
            or self._active_transaction is None
            or self._active_transaction.transaction_id != transaction.transaction_id
        ):
            raise TransactionEffectUnknown()
        self._config_root_safe()
        self._verify_published_inode(self._transaction_owner_fd)
        manifest = self._manifest()
        if (
            manifest.get("operation") != OS_GATEWAY_PUBLICATION
            or manifest.get("transaction_id") != transaction.transaction_id
            or manifest.get("expected_sha") != transaction.expected_sha
            or not _GATEWAY_MANIFEST_FIELDS <= set(manifest)
        ):
            raise TransactionEffectUnknown()
        # The retained Studio definition is re-observed before every phase
        # write; drifted source, custody or running state never publishes.
        if (
            self.observe_studio(transaction.expected_sha).definition_sha256
            != manifest["gateway_studio_definition_sha256"]
        ):
            raise TransactionEffectUnknown()

    def _recheck_gateway_preimages(
        self, transaction: TransactionContext, preparation: GatewayPreparation
    ) -> None:
        self._recheck_gateway_bound(transaction)
        manifest = self._manifest()
        expected = self._manifest_document(
            transaction, "LOCKED", operation=OS_GATEWAY_PUBLICATION
        )
        if manifest != expected:
            raise TransactionEffectUnknown()
        current = self.load_unarmed_configs(transaction.expected_sha)
        if (
            current.control_bytes != transaction.prior_configs.control_bytes
            or current.worker_bytes != transaction.prior_configs.worker_bytes
        ):
            raise TransactionEffectUnknown()
        for path, field in (
            (OS_GATEWAY_MCP_CONFIG, "gateway_prior_mcp_config_sha256"),
            (OS_GATEWAY_MCP_PLIST, "gateway_prior_mcp_plist_sha256"),
        ):
            raw = self._gateway_root_file(path, code="gateway_target_invalid")
            if sha256_bytes(raw) != manifest[field]:
                raise TransactionEffectUnknown()
        present, raw = self._grant_observation()
        if (
            present != manifest["gateway_prior_grant_present"]
            or sha256_bytes(raw) != manifest["gateway_prior_grant_sha256"]
        ):
            raise TransactionEffectUnknown()
        if (
            self.observe_studio(transaction.expected_sha).definition_sha256
            != manifest["gateway_studio_definition_sha256"]
        ):
            raise TransactionEffectUnknown()
        # The bound audit before-identity must still be exactly the retained
        # intent before the first directory or target effect.
        current_audit = self.observe_gateway_audit_directory(
            studio_uid=manifest[_GATEWAY_AUDIT_UID_FIELD],
            studio_gid=manifest[_GATEWAY_AUDIT_GID_FIELD],
        )
        if current_audit != {
            field: manifest[field]
            for field in (
                _GATEWAY_AUDIT_STATE_FIELD,
                _GATEWAY_AUDIT_UID_FIELD,
                _GATEWAY_AUDIT_GID_FIELD,
                _GATEWAY_AUDIT_MODE_FIELD,
                _GATEWAY_AUDIT_BEFORE_FIELD,
            )
        }:
            raise TransactionEffectUnknown()

    def _publish_gateway_grant(
        self, transaction: TransactionContext, preparation: GatewayPreparation
    ) -> None:
        self._recheck_gateway_bound(transaction)
        manifest = self._manifest()
        present, raw = self._grant_observation()
        if (
            present != manifest["gateway_prior_grant_present"]
            or sha256_bytes(raw) != manifest["gateway_prior_grant_sha256"]
        ):
            raise TransactionEffectUnknown()
        payload = preparation.candidate["commission_grant_bytes"]
        if sha256_bytes(payload) != manifest["gateway_target_grant_sha256"]:
            raise TransactionEffectUnknown()
        _atomic_file(
            OS_GATEWAY_COMMISSION_GRANT,
            payload,
            mode=0o444,
            uid=0,
            gid=0,
            replace=present,
        )
        written = self._gateway_root_file(
            OS_GATEWAY_COMMISSION_GRANT, code="gateway_grant_state_conflict"
        )
        if written != payload:
            raise TransactionEffectUnknown()
        self._persist_phase(transaction, "GRANT_PUBLISHED")

    def _replace_gateway_target(
        self,
        transaction: TransactionContext,
        path: Path,
        *,
        prior_field: str,
        target_field: str,
        payload: bytes,
        phase: str,
    ) -> None:
        self._recheck_gateway_bound(transaction)
        manifest = self._manifest()
        raw = self._gateway_root_file(path, code="gateway_target_invalid")
        if sha256_bytes(raw) != manifest[prior_field]:
            raise TransactionEffectUnknown()
        if sha256_bytes(payload) != manifest[target_field]:
            raise TransactionEffectUnknown()
        _atomic_file(path, payload, mode=0o644, uid=0, gid=0, replace=True)
        written = self._gateway_root_file(path, code="gateway_target_invalid")
        if written != payload:
            raise TransactionEffectUnknown()
        self._persist_phase(transaction, phase)

    def _qualify_published_gateway(self, manifest: Mapping[str, Any]) -> None:
        """Reuse the normal installed gateway qualifier before terminal proof.

        Content hashes alone cannot establish the mode, ancestry, launchd
        profile, sealed release or network-runtime contract of these targets.
        This helper is read-only and owns no gateway lifecycle operation.
        """
        from ops.executive_os.gateway_refresh_preflight import qualify_gateway_refresh

        try:
            result = qualify_gateway_refresh(manifest["expected_sha"])
            if (
                result.get("schema") != "mastermind.gateway_refresh_preflight/v1"
                or result.get("release_sha") != manifest["expected_sha"]
                or result.get("config_sha256")
                != manifest["gateway_target_mcp_config_sha256"]
            ):
                raise ValueError("published gateway qualification mismatch")
        except Exception as exc:
            raise TransactionEffectUnknown() from exc

    def write_gateway_receipt(
        self, transaction: TransactionContext, receipt: Mapping[str, Any]
    ) -> None:
        if (
            self._transaction_owner_fd is None
            or self._active_transaction is None
            or self._active_transaction.transaction_id != transaction.transaction_id
        ):
            raise TransactionEffectUnknown()
        self._verify_published_inode(self._transaction_owner_fd)
        encoded = _encoded_json(receipt)
        replace = OS_GATEWAY_RECEIPT.exists() or OS_GATEWAY_RECEIPT.is_symlink()
        if replace:
            metadata = _receipt_metadata(OS_GATEWAY_RECEIPT)
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
            OS_GATEWAY_RECEIPT, encoded, mode=0o444, uid=0, gid=0, replace=replace
        )
        readback, _info = _read_root_file(
            OS_GATEWAY_RECEIPT, modes=frozenset({0o444}), uid=0, gid=0
        )
        if readback != encoded:
            raise TransactionEffectUnknown()

    def complete_transaction(self, transaction: TransactionContext) -> None:
        if self._transaction_owner_fd is None:
            raise TransactionEffectUnknown()
        manifest = self._manifest()
        if manifest.get("operation") != OS_GATEWAY_PUBLICATION:
            super().complete_transaction(transaction)
            return
        # Gateway-only completion writes no Control observation hook: the
        # gateway targets are not Executive configs and no service restarts.
        if (
            manifest.get("transaction_id") != transaction.transaction_id
            or manifest.get("expected_sha") != transaction.expected_sha
        ):
            raise TransactionEffectUnknown()
        # The terminal receipt must still hold its exact published identity at
        # marker completion; a lost receipt keeps the original owner UNKNOWN.
        try:
            payload, _raw = _root_json(
                OS_GATEWAY_RECEIPT, modes=frozenset({0o444}), uid=0, gid=0
            )
            validate_gateway_receipt_document(
                payload,
                transaction_id=manifest["transaction_id"],
                expected_sha=manifest["expected_sha"],
                bundle_digest=manifest["gateway_release_bundle_digest"],
                mcp_config_sha256=manifest["gateway_target_mcp_config_sha256"],
                mcp_plist_sha256=manifest["gateway_target_mcp_plist_sha256"],
                grant_sha256=manifest["gateway_target_grant_sha256"],
                prior_grant_present=manifest["gateway_prior_grant_present"],
            )
        except (HostControlError, GatewayPublicationError) as exc:
            raise TransactionEffectUnknown() from exc
        # Close the receipt-write interval against target metadata drift.
        # A retained receipt with a still-present marker is not completion.
        self._qualify_published_gateway(manifest)
        # The whole publication is complete ONLY with its canonical audit
        # prerequisite still qualified and bound to THIS original intent.
        self._verify_gateway_audit_directory(manifest)
        control_candidate, worker_candidate = self._candidate_paths(
            transaction.transaction_id
        )
        self._remove_candidate(control_candidate)
        self._remove_candidate(worker_candidate)
        expected = {
            "transaction.json",
            "prior-control.json",
            "prior-worker.json",
            _GATEWAY_GRANT_ARCHIVE,
        }
        if set(os.listdir(AUTONOMY_TRANSACTION)) != expected:
            raise TransactionEffectUnknown()
        archives = (*self._archive_paths(), AUTONOMY_TRANSACTION / _GATEWAY_GRANT_ARCHIVE)
        for path in (*archives, self._manifest_path()):
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
        self._release_transaction_owner()


def _gateway_receipt_document(
    *,
    transaction_id: str,
    expected_sha: str,
    bundle_digest: str,
    mcp_config_sha256: str,
    mcp_plist_sha256: str,
    grant_sha256: str,
    prior_grant_present: bool,
    now: datetime,
) -> dict[str, Any]:
    """The ONE fixed terminal receipt: original id plus exact target hashes."""

    return {
        "schema_version": OS_GATEWAY_RECEIPT_SCHEMA,
        "state": "PUBLISHED",
        "operation": OS_GATEWAY_PUBLICATION,
        "transaction_id": transaction_id,
        "expected_sha": expected_sha,
        "release_bundle_digest": bundle_digest,
        "target_mcp_config_sha256": mcp_config_sha256,
        "target_mcp_plist_sha256": mcp_plist_sha256,
        "target_commission_grant_sha256": grant_sha256,
        "prior_commission_grant_present": prior_grant_present,
        "observed_at": _receipt_timestamp(now),
        "tool_version": TOOL_VERSION,
    }


_GATEWAY_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "state",
        "operation",
        "transaction_id",
        "expected_sha",
        "release_bundle_digest",
        "target_mcp_config_sha256",
        "target_mcp_plist_sha256",
        "target_commission_grant_sha256",
        "prior_commission_grant_present",
        "observed_at",
        "tool_version",
    }
)


def validate_gateway_receipt_document(
    payload: Any,
    *,
    transaction_id: str,
    expected_sha: str,
    bundle_digest: str,
    mcp_config_sha256: str,
    mcp_plist_sha256: str,
    grant_sha256: str,
    prior_grant_present: bool,
) -> None:
    if (
        type(payload) is not dict
        or set(payload) != _GATEWAY_RECEIPT_KEYS
        or payload["schema_version"] != OS_GATEWAY_RECEIPT_SCHEMA
        or payload["state"] != "PUBLISHED"
        or payload["operation"] != OS_GATEWAY_PUBLICATION
        or payload["transaction_id"] != transaction_id
        or payload["expected_sha"] != expected_sha
        or payload["release_bundle_digest"] != bundle_digest
        or payload["target_mcp_config_sha256"] != mcp_config_sha256
        or payload["target_mcp_plist_sha256"] != mcp_plist_sha256
        or payload["target_commission_grant_sha256"] != grant_sha256
        or payload["prior_commission_grant_present"] is not prior_grant_present
        or _parse_timestamp(payload["observed_at"]) is None
        or payload["tool_version"] != TOOL_VERSION
    ):
        raise GatewayPublicationError("gateway_receipt_invalid")


def prepare_gateway_publication(
    host: ProductionGatewayPublicationHost, request: GatewayPublicationRequest
) -> GatewayPreparation:
    """Qualify every publication input BEFORE any marker or target effect."""

    host.effective_uid()
    installed = host.require_exact_install(request.expected_sha)
    try:
        prior_json = json.loads(
            host._gateway_root_file(
                OS_GATEWAY_MCP_CONFIG, code="gateway_target_invalid"
            ).decode("utf-8")
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GatewayPublicationError("gateway_target_invalid") from exc
    prior_release = (
        prior_json.get("release_sha") if type(prior_json) is dict else None
    )
    if type(prior_release) is not str or _SHA_RE.fullmatch(prior_release) is None:
        raise GatewayPublicationError("gateway_target_invalid")
    configs = host.checked_gateway_configs(
        request.expected_sha,
        allowed_plist_sha256s=frozenset({request.prior_mcp_plist_sha256}),
        allowed_release_shas=frozenset({prior_release}),
    )
    tree_sha = host._gateway_release_tree(request.expected_sha)
    host._gateway_release_tree(prior_release)
    _receipt_bytes, launch_document, bundle_digest = host.qualify_launch_publication(
        request.expected_sha, tree_sha
    )
    if bundle_digest != request.bundle_digest:
        raise GatewayPublicationError("gateway_bundle_digest_mismatch")
    prior_mcp_config = host._gateway_root_file(
        OS_GATEWAY_MCP_CONFIG, code="gateway_target_invalid"
    )
    prior_mcp_plist = host._gateway_root_file(
        OS_GATEWAY_MCP_PLIST, code="gateway_target_invalid"
    )
    if (
        sha256_bytes(prior_mcp_config) != request.prior_mcp_config_sha256
        or sha256_bytes(prior_mcp_plist) != request.prior_mcp_plist_sha256
    ):
        raise GatewayPublicationError("gateway_target_invalid")
    grant_present, grant_bytes = host._grant_observation()
    # Exactly one grant expectation: an explicit prior digest or an explicit
    # qualified absence.  Anything else refuses before any effect.
    if request.prior_grant_absent:
        if grant_present or request.prior_grant_sha256 is not None:
            raise GatewayPublicationError("gateway_grant_state_conflict")
    elif request.prior_grant_sha256 is not None:
        if not grant_present or sha256_bytes(grant_bytes) != request.prior_grant_sha256:
            raise GatewayPublicationError("gateway_grant_state_conflict")
    else:
        raise GatewayPublicationError("gateway_grant_state_conflict")
    studio = host.observe_studio(request.expected_sha)
    audit_directory = host.observe_gateway_audit_directory(
        studio_uid=studio.studio_uid, studio_gid=studio.studio_gid
    )
    web_client_id = launch_document["web_client_id"]
    identity = host.qualify_workspace_identity(
        prior_mcp_config, web_client_id=web_client_id
    )
    scope = host._derived_namespace_scope(identity)
    derived_policy = host._derived_publication_policy(
        prior_mcp_config,
        expected_sha=request.expected_sha,
        studio_port=OS_GATEWAY_STUDIO_PORT,
    )
    template = launch_document["commission_template"]
    helper_hashes = host._helper_hashes(request.expected_sha)
    # The ONE exact existing grant document the compiler accepts.  The
    # launch/source and Studio provenance stay in ``launch_document`` and the
    # preparation, never folded into this document.
    publication_document = {
        "schema": OS_GATEWAY_GRANT_SCHEMA,
        "release_sha": request.expected_sha,
        "studio_uid": OS_GATEWAY_STUDIO_UID,
        "studio_account": OS_GATEWAY_STUDIO_ACCOUNT,
        "studio_port": OS_GATEWAY_STUDIO_PORT,
        "policy": derived_policy,
        "grants": [{"principal_scope": scope, "template": template}],
        "base_sha": prior_release,
        "audit_directory": os.fspath(_GATEWAY_AUDIT_DIRECTORY),
        "auth_helper_sha256": helper_hashes["auth_helper_sha256"],
        "file_helper_sha256": helper_hashes["file_helper_sha256"],
    }
    candidate = host._compile_gateway_candidates(
        prior_mcp_config,
        prior_mcp_plist,
        publication_document=publication_document,
        helper_hashes=helper_hashes,
        expected_sha=request.expected_sha,
        bundle_digest=bundle_digest,
    )
    _verify_gateway_postimages(
        host,
        prior_mcp_config,
        candidate,
        expected_sha=request.expected_sha,
        prior_release=prior_release,
        web_client_id=web_client_id,
        derived_scope=scope,
        derived_policy=derived_policy,
        commission_template=template,
        helper_hashes=helper_hashes,
    )
    candidate_configs = CandidateConfigs(
        control=configs.control,
        worker=configs.worker,
        control_bytes=configs.control_bytes,
        worker_bytes=configs.worker_bytes,
        control_sha256=configs.control_sha256,
        worker_sha256=configs.worker_sha256,
    )
    return GatewayPreparation(
        installed=installed,
        tree_sha=tree_sha,
        bundle_digest=bundle_digest,
        configs=configs,
        candidate_configs=candidate_configs,
        prior_mcp_config_bytes=prior_mcp_config,
        prior_mcp_plist_bytes=prior_mcp_plist,
        prior_release=prior_release,
        prior_grant_present=grant_present,
        prior_grant_bytes=grant_bytes,
        candidate=candidate,
        publication_document=publication_document,
        launch_document=launch_document,
        workspace_identity=identity,
        derived_principal_scope=scope,
        commission_template=template,
        derived_policy=derived_policy,
        audit_directory=audit_directory,
        studio=studio,
    )


def _verify_gateway_postimages(
    host: ProductionGatewayPublicationHost,
    prior_mcp_config: bytes,
    candidate: Mapping[str, Any],
    *,
    expected_sha: str,
    prior_release: str,
    web_client_id: str,
    derived_scope: str,
    derived_policy: Mapping[str, Any],
    commission_template: Mapping[str, Any],
    helper_hashes: Mapping[str, str],
) -> None:
    """Hold the publication's own preservation law before any target write.

    The two JSON targets must be the owner's canonical document encoding, the
    MCP postimage must remain a valid installed configuration that preserves
    every current policy block and the same enrolled web identity, the plist
    postimage must join the fixed release entry point and config path, and the
    grant postimage must be the ONE exact existing grant document: the
    derived canonical OS submit policy and the single Research-only template
    grant carrying the Root-derived namespace scope.
    """
    from ops.executive_os import executive_mcp_entry

    try:
        from ops.executive_os.os_gateway_publication import (
            canonical as compiler_canonical,
        )
    except ImportError as exc:
        raise GatewayPublicationError("gateway_compiler_unavailable") from exc
    try:
        config = json.loads(candidate["mcp_config_bytes"].decode("utf-8"))
        grant = json.loads(candidate["commission_grant_bytes"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GatewayPublicationError("gateway_compiler_contract_invalid") from exc
    if (
        type(config) is not dict
        or type(grant) is not dict
        or candidate["mcp_config_bytes"] != compiler_canonical(config) + b"\n"
        or candidate["commission_grant_bytes"] != compiler_canonical(grant) + b"\n"
    ):
        raise GatewayPublicationError("gateway_compiler_contract_invalid")
    try:
        executive_mcp_entry.validate_document(config)
    except Exception as exc:
        raise GatewayPublicationError("gateway_target_invalid") from exc
    if config.get("release_sha") != expected_sha:
        raise GatewayPublicationError("gateway_target_invalid")
    prior = json.loads(prior_mcp_config.decode("utf-8"))
    for block in ("policies", "workspace"):
        if block in prior and config.get(block) != prior[block]:
            raise GatewayPublicationError("gateway_target_invalid")
    if host.qualify_workspace_identity(
        candidate["mcp_config_bytes"], web_client_id=web_client_id
    ) != host.qualify_workspace_identity(prior_mcp_config, web_client_id=web_client_id):
        raise GatewayPublicationError("gateway_workspace_binding_invalid")
    try:
        plist_value = plistlib.loads(candidate["mcp_plist_bytes"])
    except Exception as exc:
        raise GatewayPublicationError("gateway_target_invalid") from exc
    release_text = os.fspath(SYSTEM_ROOT / "releases" / expected_sha)
    arguments = plist_value.get("ProgramArguments") if isinstance(plist_value, dict) else None
    if (
        not isinstance(plist_value, dict)
        or plist_value.get("Label") != OS_GATEWAY_MCP_LABEL
        or not isinstance(arguments, list)
        or len(arguments) != 6
        or arguments[3] != f"{release_text}/ops/executive_os/executive_mcp_entry.py"
        or arguments[4] != "--config"
        or arguments[5] != os.fspath(OS_GATEWAY_MCP_CONFIG)
    ):
        raise GatewayPublicationError("gateway_target_invalid")
    if (
        set(grant) != OS_GATEWAY_GRANT_KEYS
        or grant["schema"] != OS_GATEWAY_GRANT_SCHEMA
        or grant["release_sha"] != expected_sha
        or grant["studio_uid"] != OS_GATEWAY_STUDIO_UID
        or grant["studio_account"] != OS_GATEWAY_STUDIO_ACCOUNT
        or grant["studio_port"] != OS_GATEWAY_STUDIO_PORT
        or grant["audit_directory"] != os.fspath(_GATEWAY_AUDIT_DIRECTORY)
        or grant["base_sha"] != prior_release
        or grant["auth_helper_sha256"] != helper_hashes["auth_helper_sha256"]
        or grant["file_helper_sha256"] != helper_hashes["file_helper_sha256"]
        or grant["policy"] != dict(derived_policy)
        or type(grant["grants"]) is not list
        or len(grant["grants"]) != 1
        or type(grant["grants"][0]) is not dict
        or set(grant["grants"][0]) != {"principal_scope", "template"}
        or grant["grants"][0]["principal_scope"] != derived_scope
        or grant["grants"][0]["template"] != dict(commission_template)
    ):
        raise GatewayPublicationError("gateway_grant_invalid")


def execute_gateway_publication(
    host: ProductionGatewayPublicationHost,
    request: GatewayPublicationRequest,
    *,
    now: datetime,
) -> TransactionResult:
    """Publish the three fixed gateway targets through the existing owner."""

    # Actual root origin and the selected sealed source join BEFORE any
    # protected configuration, receipt or marker IO.
    host.effective_uid()
    host.require_gateway_module_origin(request.expected_sha)
    host.require_gateway_receipt_absent()
    host.require_transaction_absent()
    preparation = prepare_gateway_publication(host, request)
    transaction = TransactionContext(
        transaction_id=host.new_transaction_id(),
        expected_sha=request.expected_sha,
        prior_configs=preparation.candidate_configs,
        candidates=preparation.candidate_configs,
        admission=None,
    )
    host._sealed_gateway = {
        "gateway_release_bundle_digest": preparation.bundle_digest,
        "gateway_studio_definition_sha256": preparation.studio.definition_sha256,
        "gateway_prior_grant_present": preparation.prior_grant_present,
        "gateway_prior_grant_sha256": sha256_bytes(preparation.prior_grant_bytes),
        "gateway_target_grant_sha256": preparation.candidate["commission_grant_sha256"],
        "gateway_prior_mcp_config_sha256": request.prior_mcp_config_sha256,
        "gateway_target_mcp_config_sha256": preparation.candidate["mcp_config_sha256"],
        "gateway_prior_mcp_plist_sha256": request.prior_mcp_plist_sha256,
        "gateway_target_mcp_plist_sha256": preparation.candidate["mcp_plist_sha256"],
        **preparation.audit_directory,
        _GATEWAY_AUDIT_AFTER_FIELD: None,
    }
    host._prior_grant_bytes = preparation.prior_grant_bytes
    host._active_transaction = transaction
    try:
        host._create_marker(transaction, operation=OS_GATEWAY_PUBLICATION)
    except FileExistsError as exc:
        host._active_transaction = None
        raise GatewayPublicationError("gateway_transaction_incomplete") from exc
    try:
        host._recheck_gateway_preimages(transaction, preparation)
        # The canonical audit prerequisite is created strictly from the
        # RETAINED intent, already sealed before any effect.
        host._sealed_gateway[_GATEWAY_AUDIT_AFTER_FIELD] = (
            host._establish_gateway_audit_directory(host._manifest())
        )
        # Retain the actual created/reused inode in THIS original operation
        # before any grant/config effect. Receipt loss cannot infer a new one.
        host._persist_phase(transaction, "AUDIT_DIRECTORY_READY")
        host._publish_gateway_grant(transaction, preparation)
        host._replace_gateway_target(
            transaction,
            OS_GATEWAY_MCP_CONFIG,
            prior_field="gateway_prior_mcp_config_sha256",
            target_field="gateway_target_mcp_config_sha256",
            payload=preparation.candidate["mcp_config_bytes"],
            phase="GATEWAY_CONFIG_REPLACED",
        )
        host._replace_gateway_target(
            transaction,
            OS_GATEWAY_MCP_PLIST,
            prior_field="gateway_prior_mcp_plist_sha256",
            target_field="gateway_target_mcp_plist_sha256",
            payload=preparation.candidate["mcp_plist_bytes"],
            phase="GATEWAY_PLIST_REPLACED",
        )
        host._qualify_published_gateway(host._manifest())
        receipt = _gateway_receipt_document(
            transaction_id=transaction.transaction_id,
            expected_sha=request.expected_sha,
            bundle_digest=preparation.bundle_digest,
            mcp_config_sha256=preparation.candidate["mcp_config_sha256"],
            mcp_plist_sha256=preparation.candidate["mcp_plist_sha256"],
            grant_sha256=preparation.candidate["commission_grant_sha256"],
            prior_grant_present=preparation.prior_grant_present,
            now=now,
        )
        host.write_gateway_receipt(transaction, receipt)
        host._persist_phase(transaction, "GATEWAY_RECEIPT_REPLACED")
        host.complete_transaction(transaction)
    except Exception:
        raise TransactionEffectUnknown() from None
    return TransactionResult(
        state="PUBLISHED",
        status="OS_GATEWAY_PUBLISHED",
        transaction_id=transaction.transaction_id,
        replayed=False,
    )


def reconcile_gateway_publication(
    host: ProductionGatewayPublicationHost,
    request: GatewayPublicationRequest,
    *,
    now: datetime,
) -> str:
    """Prove one interrupted publication to its exact retained postimages.

    Reconciliation NEVER republishes: it requalifies the retained source and
    provenance, proves every target postimage, and completes the terminal
    receipt and marker only when all of them hold exactly.
    """

    host.effective_uid()
    host.require_gateway_module_origin(request.expected_sha)
    host.require_exact_install(request.expected_sha)
    host._claim_transaction_owner()
    manifest = host._manifest()
    if (
        manifest.get("operation") != OS_GATEWAY_PUBLICATION
        or manifest.get("transaction_id") != request.transaction_id
        or manifest.get("expected_sha") != request.expected_sha
        or manifest.get("phase") not in _GATEWAY_PHASES
        or manifest.get("gateway_release_bundle_digest") != request.bundle_digest
        or not _GATEWAY_MANIFEST_FIELDS <= set(manifest)
    ):
        raise TransactionEffectUnknown()
    # Recovery restores the original sealed identity from the retained
    # manifest; it never relabels a phase with new identity fields.
    host._sealed_gateway = {
        field: manifest[field] for field in _GATEWAY_MANIFEST_FIELDS
    }
    configs = host.checked_gateway_configs(
        request.expected_sha,
        allowed_plist_sha256s=frozenset(
            {
                manifest["gateway_prior_mcp_plist_sha256"],
                manifest["gateway_target_mcp_plist_sha256"],
            }
        ),
    )
    archived = host._archived_configs(request.expected_sha)
    if (
        configs.control_bytes != archived.control_bytes
        or configs.worker_bytes != archived.worker_bytes
    ):
        raise TransactionEffectUnknown()
    archived_grant, _info = _read_root_file(
        AUTONOMY_TRANSACTION / _GATEWAY_GRANT_ARCHIVE,
        modes=frozenset({0o400}),
        uid=0,
        gid=0,
    )
    if (
        sha256_bytes(archived_grant) != manifest["gateway_prior_grant_sha256"]
        or bool(archived_grant) is not manifest["gateway_prior_grant_present"]
    ):
        raise TransactionEffectUnknown()
    tree_sha = host._gateway_release_tree(request.expected_sha)
    _receipt_bytes, _document, bundle_digest = host.qualify_launch_publication(
        request.expected_sha, tree_sha
    )
    if bundle_digest != manifest["gateway_release_bundle_digest"]:
        raise TransactionEffectUnknown()
    if (
        host.observe_studio(request.expected_sha).definition_sha256
        != manifest["gateway_studio_definition_sha256"]
    ):
        raise TransactionEffectUnknown()
    for path, field in (
        (OS_GATEWAY_MCP_CONFIG, "gateway_target_mcp_config_sha256"),
        (OS_GATEWAY_MCP_PLIST, "gateway_target_mcp_plist_sha256"),
    ):
        raw = host._gateway_root_file(path, code="gateway_target_invalid")
        if sha256_bytes(raw) != manifest[field]:
            raise TransactionEffectUnknown()
    present, raw = host._grant_observation()
    if not present or sha256_bytes(raw) != manifest["gateway_target_grant_sha256"]:
        raise TransactionEffectUnknown()
    # Reconciliation is postimage-only: the bound canonical audit
    # prerequisite must still hold exactly; it is never created, repaired or
    # regenerated here, and a lost or drifted prerequisite stays UNKNOWN.
    host._verify_gateway_audit_directory(manifest)
    host._qualify_published_gateway(manifest)
    transaction = TransactionContext(
        transaction_id=manifest["transaction_id"],
        expected_sha=request.expected_sha,
        prior_configs=archived,
        candidates=CandidateConfigs(
            control=archived.control,
            worker=archived.worker,
            control_bytes=archived.control_bytes,
            worker_bytes=archived.worker_bytes,
            control_sha256=archived.control_sha256,
            worker_sha256=archived.worker_sha256,
        ),
        admission=None,
    )
    host._active_transaction = transaction
    receipt_present = OS_GATEWAY_RECEIPT.exists() or OS_GATEWAY_RECEIPT.is_symlink()
    # A lost receipt with the retained marker reconciles: the terminal
    # document is re-derived from the sealed manifest fields, never from a
    # new request.  A missing marker is never reconciled into one.
    if not receipt_present:
        receipt = _gateway_receipt_document(
            transaction_id=manifest["transaction_id"],
            expected_sha=request.expected_sha,
            bundle_digest=manifest["gateway_release_bundle_digest"],
            mcp_config_sha256=manifest["gateway_target_mcp_config_sha256"],
            mcp_plist_sha256=manifest["gateway_target_mcp_plist_sha256"],
            grant_sha256=manifest["gateway_target_grant_sha256"],
            prior_grant_present=manifest["gateway_prior_grant_present"],
            now=now,
        )
        host.write_gateway_receipt(transaction, receipt)
        host._persist_phase(transaction, "GATEWAY_RECEIPT_REPLACED")
    else:
        payload, _raw = _root_json(
            OS_GATEWAY_RECEIPT, modes=frozenset({0o444}), uid=0, gid=0
        )
        validate_gateway_receipt_document(
            payload,
            transaction_id=manifest["transaction_id"],
            expected_sha=request.expected_sha,
            bundle_digest=manifest["gateway_release_bundle_digest"],
            mcp_config_sha256=manifest["gateway_target_mcp_config_sha256"],
            mcp_plist_sha256=manifest["gateway_target_mcp_plist_sha256"],
            grant_sha256=manifest["gateway_target_grant_sha256"],
            prior_grant_present=manifest["gateway_prior_grant_present"],
        )
    host.complete_transaction(transaction)
    return transaction.transaction_id


def _run_gateway_command(
    host: ProductionGatewayPublicationHost, args: argparse.Namespace, *, now: datetime
) -> int:
    """The closed root-only gateway CLI: typed refusals, sanitized documents."""

    try:
        if args.command == "publish-os-gateway":
            request = GatewayPublicationRequest(
                expected_sha=args.expected_sha,
                bundle_digest=args.expected_bundle_digest,
                prior_mcp_config_sha256=args.expected_mcp_config_sha256,
                prior_mcp_plist_sha256=args.expected_mcp_plist_sha256,
                prior_grant_sha256=args.expected_grant_sha256,
                prior_grant_absent=args.expected_grant_absent,
            )
            result = execute_gateway_publication(host, request, now=now)
            document = operation_document(
                code="os_gateway_published",
                state=result.state,
                status=result.status,
                transaction_id=result.transaction_id,
                replayed=result.replayed,
            )
            exit_code = 0
        else:
            request = GatewayPublicationRequest(
                expected_sha=args.expected_sha,
                bundle_digest=args.expected_bundle_digest,
                transaction_id=args.transaction_id,
            )
            transaction_id = reconcile_gateway_publication(host, request, now=now)
            document = operation_document(
                code="os_gateway_reconciled",
                state="PUBLISHED",
                status="OS_GATEWAY_PUBLISHED",
                transaction_id=transaction_id,
            )
            exit_code = 0
    except TransactionEffectUnknown:
        document = operation_document(
            code="effect_unknown",
            state="UNKNOWN",
            status="EFFECT_UNKNOWN",
            transaction_id=None,
        )
        exit_code = 2
    except (
        HostControlError,
        ArmAdmissionError,
        CeoSubmitAdmissionError,
        GatewayPublicationError,
    ) as exc:
        document = operation_document(
            code=exc.code,
            state="UNKNOWN",
            status="OS_GATEWAY_UNVERIFIED",
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
    finally:
        if host._transaction_owner_fd is not None:
            host._release_transaction_owner()
    print(json.dumps(document, sort_keys=True, separators=(",", ":")))
    return exit_code


def _run_ceo_submit_command(
    host: CeoSubmitTransactionHost, args: argparse.Namespace, *, now: datetime
) -> int:
    """The one closed, root-only CEO-submit operation domain on the CLI.

    Every refusal is TYPED: the caller never receives a bare traceback and never
    receives a state claim the module did not verify.  Nothing here starts a
    provider call, a Job or a worker effect.
    """

    request = CeoSubmitRequest(expected_sha=args.expected_sha)
    try:
        if args.command == "ceo-submit-status":
            result = evaluate_ceo_submit_status(host, request)
            code = {
                "CEO_SUBMIT_ARMED": "ceo_submit_armed",
                "CEO_SUBMIT_DISARMED": "ceo_submit_disarmed",
                "CEO_SUBMIT_ARMED_UNBOUND": "ceo_submit_armed_unbound",
            }[result.state]
            exit_code = 0 if result.state != "CEO_SUBMIT_ARMED_UNBOUND" else 2
        elif args.command == "ceo-submit-arm":
            result = execute_ceo_submit_arm(host, request, now=now)
            code = "ceo_submit_armed"
            exit_code = 0
        elif args.command == "ceo-submit-disarm":
            result = execute_ceo_submit_disarm(host, request, now=now)
            code = (
                "ceo_submit_already_disarmed"
                if result.replayed
                else "ceo_submit_disarmed"
            )
            exit_code = 0
        else:
            result = host.recover_ceo_submit_effect_unknown(request, now=now)
            code = "ceo_submit_reconciled"
            exit_code = 0
        document = operation_document(
            code=code,
            state=result.state,
            status=result.status,
            transaction_id=result.transaction_id,
            replayed=result.replayed,
        )
    except TransactionEffectUnknown:
        document = operation_document(
            code="effect_unknown",
            state="UNKNOWN",
            status="EFFECT_UNKNOWN",
            transaction_id=None,
        )
        exit_code = 2
    except (HostControlError, CeoSubmitAdmissionError, ArmAdmissionError) as exc:
        document = operation_document(
            code=exc.code,
            state="UNKNOWN",
            status="CEO_SUBMIT_UNVERIFIED",
            transaction_id=None,
        )
        exit_code = 2
    except ArmTransactionError as exc:
        document = operation_document(
            code=exc.code,
            state="UNKNOWN",
            status="CEO_SUBMIT_UNVERIFIED",
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

    if args.command in CEO_SUBMIT_COMMANDS:
        ceo_host = ProductionCeoSubmitHost() if host is None else host
        return _run_ceo_submit_command(ceo_host, args, now=current)

    if args.command == "arm-quiesce-control-uid":
        arm_host = ProductionArmHost() if host is None else host
        try:
            require_root_privilege(arm_host.effective_uid())
            installed = arm_host.require_exact_install(args.expected_sha)
            if installed != args.expected_sha:
                raise ArmAdmissionError("install_gate_failed")
            arm_host.validate_acceptance(args.expected_sha)
            configs = arm_host.load_unarmed_configs(args.expected_sha)
            arm_host.require_runtime_quiescent(configs)
            arm_host.require_services_already_stopped()
            arm_host.require_transaction_absent()
            signalled = arm_host.quiesce_control_uid_for_arm()
            arm_host.require_service_uids_quiescent()
            document = operation_document(
                code="control_uid_quiesced",
                state=UNARMED,
                status=UNARMED,
                transaction_id=None,
                replayed=not signalled,
            )
            exit_code = 0
        except ArmAdmissionError as exc:
            document = operation_document(
                code=exc.code,
                state=UNARMED,
                status=UNARMED,
                transaction_id=None,
            )
            exit_code = 2
        except Exception:
            document = operation_document(
                code="service_uid_process_unknown",
                state=UNARMED,
                status=UNARMED,
                transaction_id=None,
            )
            exit_code = 2
        print(json.dumps(document, sort_keys=True, separators=(",", ":")))
        return exit_code

    if args.command in {"dialogue-canary-publish", "dialogue-canary-reconcile"}:
        from ops.executive_os.dialogue_wake_canary_control import run_command
        return run_command(args, host=host)

    if args.command in A2_DISABLE_COMMANDS:
        from ops.executive_os.a2_disable_preparation_control import run_command
        return run_command(args, host=host)

    if args.command in {'finite-control-stage', 'finite-control-stage-reconcile'}:
        from ops.executive_os.attended_control_staging import run_command
        return run_command(args, host=host)

    if args.command in {'paid-control-stage','paid-control-stage-reconcile'}:
        from ops.executive_os.paid_control_staging import run_command
        return run_command(args,host=host)

    if args.command in OS_GATEWAY_COMMANDS:
        gateway_host = ProductionGatewayPublicationHost() if host is None else host
        return _run_gateway_command(gateway_host, args, now=current)

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
                    native_return=args.native_return,
                    foreground_only=args.foreground_only,
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
    # The installed wrapper executes this file with -I -S -B. Publication
    # imports this module by package name and requires its genuine classes;
    # objects defined under __main__ have a different identity. Delegate the
    # entry, not the type check, and do not alias an arbitrary module in sys.modules.
    from ops.executive_os.autonomy_control import main as canonical_main

    raise SystemExit(canonical_main())
