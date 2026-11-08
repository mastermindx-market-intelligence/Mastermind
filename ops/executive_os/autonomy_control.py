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
# The expected owner of the installed configuration root and of every
# canonical artifact this owner publishes under it.  They are the root
# principal on the installed host.  The constants exist so the qualification
# is stated exactly once and so an unprivileged hermetic test can bind the
# SAME publication primitive to a private temporary root.
_CONFIG_ROOT_UID = 0
_CONFIG_ROOT_GID = 0
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
_A2_RESTORE_RECEIPT_ARCHIVE = "prior-a2-control-restore-disarmed-receipt.json"
_A2_RESTORE_RECEIPT_FIELDS = frozenset({
    "a2_prior_receipt_present", "a2_prior_receipt_sha256",
    "a2_target_receipt_sha256",
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

# Before Control binds status, installed startup allows 240 seconds for Workspace
# composition and 30 seconds each for its boot canary and OHF identity exchange.
# Reserve a further bounded minute for remaining initialization and observation;
# this allowance never substitutes for READY or extends an inner operation.
_SERVICES_READY_TIMEOUT = 240.0 + 2 * 30.0 + 60.0

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
_TRANSACTION_OPERATIONS = frozenset({"ARM", "DISARM", "A2_DISABLE_PREPARATION", "FINITE_CONTROL_STAGE", "FINITE_CONTROL_RETIRE", "PAID_CONTROL_STAGE", "OS_GATEWAY_PUBLICATION", "CONTROL_COMPONENT_UPDATE"}) | CONTROL_ONLY_TRANSACTION_OPERATIONS
# One manifest name for the canonical marker and for the private generation it
# is published from, so a renamed generation is always readable in place.
_TRANSACTION_MANIFEST_NAME = "transaction.json"
# Extend the incumbent operation set without replacing its expression:
# protected source may admit unrelated operations (for example OS Gateway).
A2_CONTROL_RESTORATION_COMMANDS = frozenset({
    "a2-restore-controller-socket", "a2-restore-controller-socket-reconcile",
    "a2-restored-readside-preflight",
})
_TRANSACTION_OPERATIONS |= frozenset({"A2_RETURN_SOCKET_RESTORE"})
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
OS_GATEWAY_SUCCESSOR_RECEIPT_SCHEMA = "mastermind.executive_os_gateway_receipt/v2"
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
_GATEWAY_RECEIPT_ARCHIVE = "prior-os-gateway-receipt.json"
_GATEWAY_SUCCESSOR_FIELDS = frozenset({
    "gateway_predecessor_receipt_sha256", "gateway_predecessor_receipt_identity",
    "gateway_predecessor_archive_identity",
})
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
_MCP_AUDIT_BEFORE_FIELD = "gateway_mcp_auth_audit_before"
_MCP_AUDIT_AFTER_FIELD = "gateway_mcp_auth_audit_after"
_MCP_AUDIT_FIELDS = frozenset({_MCP_AUDIT_BEFORE_FIELD, _MCP_AUDIT_AFTER_FIELD})


def _gateway_inode_identity(value: Any) -> bool:
    return (type(value) is list and len(value) == 2
            and all(type(item) is int and item >= 0 for item in value)
            and value[1] > 0)

def _gateway_receipt_identity(info: os.stat_result) -> list[int]:
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns, info.st_nlink, info.st_uid, info.st_gid, info.st_mode]


def _gateway_receipt_identity_valid(value: Any) -> bool:
    return (type(value) is list and len(value) == 9
            and all(type(item) is int and item >= 0 for item in value)
            and value[1] > 0 and value[2] > 0 and value[5:] == [1, 0, 0, stat.S_IFREG | 0o444])


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
        "PREDECESSOR_RECEIPT_RETAINED",
        "AUDIT_DIRECTORY_READY",
        "GRANT_PUBLISHED",
        "GATEWAY_CONFIG_REPLACED",
        "GATEWAY_PLIST_REPLACED",
        "GATEWAY_RECEIPT_REPLACED",
    }
)
_GATEWAY_ROOT_FILE_MAX_BYTES = 4 * 1024 * 1024
# The one canonical audit leaf and its closed producer law.  The leaf is the
# only node this owner may create; the fixed parent chain is qualified, never
# fabricated.
_GATEWAY_AUDIT_DIRECTORY = Path(OS_GATEWAY_GRANT_AUDIT_DIRECTORY)
_GATEWAY_AUDIT_LEAF_NAME = _GATEWAY_AUDIT_DIRECTORY.name
_GATEWAY_AUDIT_LEAF_MODE = 0o700
_GATEWAY_AUDIT_ENTRY_MAX_COUNT = 32
_GATEWAY_AUDIT_ENTRY_NAME_MAX = 128

# The Control component update operation domain: one closed, root-only
# composition that retargets the EXISTING installed Control source (its
# configuration proof coordinates, its Control plist and its already-inert
# Worker plist) onto an already-staged target release, through the ONE
# existing ``AUTONOMY_TRANSACTION`` owner.  It opens no second lock, writes no
# second marker, never touches the MCP component update's own lock, and never
# acts on the Relay, MCP, Backup or privileged broker.
CONTROL_COMPONENT_UPDATE = "CONTROL_COMPONENT_UPDATE"
CONTROL_COMPONENT_COMMANDS = frozenset(
    {
        "plan-control-component",
        "apply-control-component",
        "reconcile-control-component",
    }
)
# The retained preimages of this operation: the two installed plists and the
# three receipts it may replace.  They are sealed into the private generation
# before the canonical marker path can become visible, so an interrupted
# update always retains the ORIGINAL bytes.
_COMPONENT_ARCHIVES = (
    "prior-control-plist.plist",
    "prior-worker-plist.plist",
    "prior-component-autonomy-receipt.json",
    "prior-component-ceo-submit-receipt.json",
    "prior-component-receipt.json",
)
# The coordinated archives of ONE Hermes host-read selection.  They exist
# only for a transaction that sealed a selection, so the legacy transaction
# format is preserved exactly when the operation carries none.
_COMPONENT_BINDING_ARCHIVES = (
    "prior-component-binding-selection.json",
    "prior-component-hermes-read-input.json",
    "component-binding-candidate.json",
)
# The closed shape of the OPTIONAL nested selection member of a component
# marker.  It is a STRUCTURED member, not a digest: it carries hashes,
# EXPLICIT presence, the derived destination and the ordered effect.
_COMPONENT_NATIVE_BINDING_ARCHIVES = (
    "prior-component-binding-selection.json",
    "prior-component-native-conversation-input.json",
    "component-binding-candidate.json",
)
_COMPONENT_BINDING_MANIFEST_KEYS = frozenset(
    {
        "input_sha256",
        "candidate_sha256",
        "destination",
        "destination_present",
        "prior_selector_present",
        "prior_binding_sha256",
        "bindings_count",
        "remote_transports_count",
        "execution_present",
        "effect",
    }
)
_COMPONENT_MANIFEST_FIELDS = frozenset(
    {
        "component_plan_sha256",
        "component_prior_release_seal_sha256",
        "component_target_release_seal_sha256",
        "component_observed_at",
        "component_prior_control_plist_sha256",
        "component_target_control_plist_sha256",
        "component_prior_worker_plist_sha256",
        "component_target_worker_plist_sha256",
        "component_prior_autonomy_receipt_present",
        "component_prior_autonomy_receipt_sha256",
        "component_target_autonomy_receipt_sha256",
        "component_prior_ceo_receipt_present",
        "component_prior_ceo_receipt_sha256",
        "component_target_ceo_receipt_sha256",
        "component_prior_component_receipt_present",
        "component_prior_component_receipt_sha256",
        "component_target_component_receipt_sha256",
        "component_mode",
        "component_prior_control_launchd_disabled",
        "component_prior_worker_launchd_disabled",
    }
)
# The OPTIONAL selection member of a component marker.  It is absent for a
# transaction that carries no selection, and the legacy marker format is
# preserved exactly in that case.
_COMPONENT_OPTIONAL_MANIFEST_FIELDS = frozenset({"component_binding"})
_COMPONENT_DIGEST_MANIFEST_FIELDS = frozenset(
    _COMPONENT_MANIFEST_FIELDS
    - {
        "component_prior_autonomy_receipt_present",
        "component_prior_ceo_receipt_present",
        "component_prior_component_receipt_present",
        "component_observed_at",
        "component_mode",
        "component_prior_control_launchd_disabled",
        "component_prior_worker_launchd_disabled",
    }
)
# The two closed input states of this operation.  LIVE: the Control service is
# registered and enabled.  OFFLINE: the Control service is genuinely absent
# AND explicitly disabled.  Every other combination refuses before any
# effect.
_COMPONENT_LIVE_MODE = "live"
_COMPONENT_OFFLINE_MODE = "offline"
_COMPONENT_MODES = frozenset({_COMPONENT_LIVE_MODE, _COMPONENT_OFFLINE_MODE})
_COMPONENT_PHASES = frozenset(
    {
        "LOCKED",
        "CONTROL_BOOTOUT_RECORDED",
        "CONTROL_ABSENT_PROVEN",
        "CONTROL_ENABLE_RECORDED",
        "CONTROL_ENABLED_PROVEN",
        "CONTROL_PLIST_REPLACED",
        "WORKER_PLIST_REPLACED",
        "CONTROL_REPLACED",
        "AUTHORITY_RECEIPT_CORRELATED",
        "CONTROL_BOOTSTRAP_RECORDED",
        "ADMISSION_BOUND",
        "CONTROL_COMPONENT_TARGETS_PROVEN",
        "CONTROL_COMPONENT_RECEIPT_REPLACED",
        "CONTROL_OBSERVATION_PUBLICATION_STARTED",
        # The two ACTUAL binding phases of the same component vocabulary.
        # They record the ONE immutable Fabric-binding publication this
        # operation may dispatch.  They NEVER authorize re-entering the
        # canonical publication: a reconciliation proves the retained
        # postimage and never publishes again.
        "CONTROL_COMPONENT_BINDING_PUBLICATION_STARTED",
        "CONTROL_COMPONENT_BINDING_PROVEN",
        # The phase the component publication path actually records.  It is a
        # RECOVERABLE phase: an interruption after the observation was
        # published must be reconciled by an exact-byte readback, never by a
        # second publication.  It is deliberately NOT a member of
        # ``_CONTROL_COMPONENT_PUBLICATION_ADMISSIBLE_PHASES``.
        "CONTROL_COMPONENT_PUBLICATION_STARTED",
    }
)
# The fixed receipt of one completed update.  It carries only hashes, source
# identifiers and the closed effect list; it never carries configuration,
# token or credential content.
CONTROL_COMPONENT_RECEIPT = CONFIG_ROOT / "control-component-update-v1.json"
CONTROL_COMPONENT_RECEIPT_SCHEMA = "mastermind.executive_control_component_receipt/v1"
# The fixed administrative checkout that backs the installer-owned
# ``proof_source_repository`` coordinate.  It is prepared by the installer, not
# by this owner.
_CONTROL_ADMIN_CHECKOUT_ROOT = RUNTIME_ROOT / "control" / "admin-checkout"
_CONTROL_ADMIN_CHECKOUT_MAX_BYTES = 4 * 1024 * 1024
_CONTROL_COMPONENT_GIT_TIMEOUT = 10.0
# The bounded window in which the stopped boundary waits for the Control
# service UID to drain after a bootout.  The census is observed, never
# signalled, and it never accepts a caller-selected UID, PID or timeout.
_CONTROL_COMPONENT_UID_CENSUS_TIMEOUT = 30.0


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
        "gateway_capability_profiles_invalid",
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
    predecessor_receipt_sha256: str | None = None


@dataclasses.dataclass(frozen=True)
class GatewayPredecessorReceipt:
    raw: bytes
    identity: tuple[int, ...]
    document: Mapping[str, Any]


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
    commission_templates: tuple[Mapping[str, Any], ...]
    derived_policy: Mapping[str, Any]
    audit_directory: Mapping[str, Any]
    mcp_auth_audit: Mapping[str, Any]
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


def _canonical_absolute_path(value: str) -> str:
    """One canonical, absolute input path.

    The path is only ever a QUALIFIED INPUT the operator staged: it is read
    through the incumbent's own bounded, no-follow, identity-joined pinned
    read and bound to the exact digest supplied beside it.  It is never a
    destination, never an output path and never caller-selected.
    """

    if type(value) is not str or not value or "\x00" in value:
        raise argparse.ArgumentTypeError("an exact absolute path is required")
    path = Path(value)
    if (
        not path.is_absolute()
        or ".." in path.parts
        or str(path) != value
        or "//" in value
    ):
        raise argparse.ArgumentTypeError(
            "the path must be a canonical absolute path"
        )
    return value


def _a2_restore_digest(value: str) -> str:
    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise argparse.ArgumentTypeError("exact lower-case SHA-256 witness required")
    return value


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
    for command in sorted(A2_CONTROL_RESTORATION_COMMANDS):
        a2 = sub.add_parser(command, help="Restore one already-reversed A2 return socket while disarmed.")
        a2.add_argument("--expected-sha", type=_exact_sha, action=_StoreOnce, required=True)
        a2.add_argument("--expected-control-sha256", type=_a2_restore_digest, action=_StoreOnce, required=True)
        a2.add_argument("--expected-previous-release-sha", type=_exact_sha, action=_StoreOnce, required=True)
        a2.add_argument("--expected-previous-tree-sha", type=_exact_sha, action=_StoreOnce, required=True)
        a2.add_argument("--expected-previous-config-sha256", type=_a2_restore_digest, action=_StoreOnce, required=True)
        a2.add_argument("--expected-previous-plist-sha256", type=_a2_restore_digest, action=_StoreOnce, required=True)
        a2.add_argument("--expected-bot-user-id", action=_StoreOnce, required=True)
    finite_stage = sub.add_parser('finite-control-stage', help='Stage the fixed finite definition while stopped and disarmed.')
    finite_stage.add_argument('--expected-sha', type=_exact_sha, action=_StoreOnce, required=True)
    finite_stage.add_argument('--expected-control-sha256', action=_StoreOnce, required=True)
    finite_reconcile = sub.add_parser('finite-control-stage-reconcile', help='Prove an already-published finite stage without replay.')
    finite_reconcile.add_argument('--expected-sha', type=_exact_sha, action=_StoreOnce, required=True)
    for command in ('finite-control-retire', 'finite-control-retire-reconcile'):
        finite_retire = sub.add_parser(command, help='Retire the fixed finite selection, retaining its protected provenance.')
        finite_retire.add_argument('--expected-sha', type=_exact_sha, action=_StoreOnce, required=True)
        if command == 'finite-control-retire':
            finite_retire.add_argument('--expected-control-sha256', type=_exact_digest, action=_StoreOnce, required=True)
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
    gateway_publish.add_argument(
        "--expected-predecessor-receipt-sha256", type=_exact_digest, action=_StoreOnce,
        help="Explicit successor publication from this exact completed gateway receipt.",
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
    # The Control component update domain: three closed verbs on the ONE
    # existing transaction owner.  Every argument is a bounded digest or the
    # exact target release; no path, label, account, port or verified boolean
    # is ever caller selectable here.
    component_plan = sub.add_parser(
        "plan-control-component",
        help="Plan the configuration-preserving Control source update.",
    )
    component_plan.add_argument(
        "--expected-sha", type=_exact_sha, action=_StoreOnce, required=True
    )
    # The PAIRED Hermes host-read selection.  Both coordinates are one
    # selection: the exact qualified input path and the exact digest of its
    # raw bytes.  Both absent preserve the existing source-only behaviour
    # byte-for-byte; exactly one of them refuses.
    component_plan.add_argument(
        "--hermes-role-metadata-read-input",
        type=_canonical_absolute_path,
        action=_StoreOnce,
        default=None,
    )
    component_plan.add_argument(
        "--hermes-role-metadata-read-sha256",
        type=_exact_digest,
        action=_StoreOnce,
        default=None,
    )
    component_plan.add_argument(
        "--native-conversation-input", type=_canonical_absolute_path,
        action=_StoreOnce, default=None,
    )
    component_plan.add_argument(
        "--native-conversation-sha256", type=_exact_digest,
        action=_StoreOnce, default=None,
    )
    component_apply = sub.add_parser(
        "apply-control-component",
        help="Publish exactly the approved Control component plan.",
    )
    component_apply.add_argument(
        "--expected-sha", type=_exact_sha, action=_StoreOnce, required=True
    )
    component_apply.add_argument(
        "--plan-sha256", type=_exact_digest, action=_StoreOnce, required=True
    )
    component_apply.add_argument(
        "--hermes-role-metadata-read-input",
        type=_canonical_absolute_path,
        action=_StoreOnce,
        default=None,
    )
    component_apply.add_argument(
        "--hermes-role-metadata-read-sha256",
        type=_exact_digest,
        action=_StoreOnce,
        default=None,
    )
    component_apply.add_argument(
        "--native-conversation-input", type=_canonical_absolute_path,
        action=_StoreOnce, default=None,
    )
    component_apply.add_argument(
        "--native-conversation-sha256", type=_exact_digest,
        action=_StoreOnce, default=None,
    )
    component_reconcile = sub.add_parser(
        "reconcile-control-component",
        help="Prove one interrupted Control component update to its postimages.",
    )
    component_reconcile.add_argument(
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


def _release_manifest_bytes(expected_sha: str) -> bytes:
    """Capture only the fixed whole-release manifest, within its 4 MiB budget.

    The normal source inventory is larger than a configuration document.  This
    separate fixed-path reader does not enlarge the generic config JSON limit
    or replace the caller's subsequent full release_manifest.verify operation.
    """
    if type(expected_sha) is not str or _SHA_RE.fullmatch(expected_sha) is None:
        raise HostControlError("installed_identity_mismatch")
    path = SYSTEM_ROOT / "releases" / expected_sha / release_manifest.MANIFEST_NAME
    descriptor = -1
    identity = lambda info: (
        info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
        info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
    )
    try:
        descriptor = os.open(
            path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        )
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != 0 or before.st_gid != 0
            or stat.S_IMODE(before.st_mode) != 0o444 or before.st_nlink != 1
            or not 0 < before.st_size <= _GATEWAY_ROOT_FILE_MAX_BYTES
            or has_macos_acl(path, expected_identity=before, descriptor=descriptor)
        ):
            raise HostControlError("config_identity_unavailable")
        chunks, size = [], 0
        while size <= _GATEWAY_ROOT_FILE_MAX_BYTES:
            part = os.read(
                descriptor, min(65536, _GATEWAY_ROOT_FILE_MAX_BYTES + 1 - size)
            )
            if not part:
                break
            chunks.append(part)
            size += len(part)
        after = os.fstat(descriptor)
        if (
            size != before.st_size or size > _GATEWAY_ROOT_FILE_MAX_BYTES
            or identity(before) != identity(after)
            or identity(after) != identity(path.lstat())
            or has_macos_acl(path, expected_identity=after, descriptor=descriptor)
            or identity(after) != identity(os.fstat(descriptor))
            or identity(after) != identity(path.lstat())
        ):
            raise HostControlError("config_identity_unavailable")
        raw = b"".join(chunks)
    except (OSError, FilesystemSecurityError) as exc:
        raise HostControlError("config_identity_unavailable") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return raw


def _release_manifest_json(expected_sha: str) -> dict[str, Any]:
    """Decode the same bounded original bytes without changing their identity."""
    raw = _release_manifest_bytes(expected_sha)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HostControlError("config_schema_drift") from exc
    if not isinstance(value, dict):
        raise HostControlError("config_schema_drift")
    return value


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
            manifest_value = _release_manifest_json(expected_sha)
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
    def _loaded(label: str, *, timeout: float = 5.0) -> bool:
        completed = subprocess.run(
            ["/bin/launchctl", "print", f"system/{label}"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=timeout,
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
    def _control_ready(expected_sha: str, *, timeout: float = 10.0) -> bool:
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
            timeout=timeout,
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

    @staticmethod
    def _startup_timeout(deadline: float, maximum: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("Executive services did not reach READY")
        return min(maximum, remaining)

    def _service_state(
        self, expected_sha: str, *, startup_deadline: float | None = None,
    ) -> tuple[str, bool]:
        if startup_deadline is None:
            control_loaded = self._loaded(CONTROL_LABEL)
            worker_loaded = self._loaded(WORKER_LABEL)
        else:
            control_loaded = self._loaded(
                CONTROL_LABEL, timeout=self._startup_timeout(startup_deadline, 5.0)
            )
            worker_loaded = self._loaded(
                WORKER_LABEL, timeout=self._startup_timeout(startup_deadline, 5.0)
            )
        if not control_loaded and not worker_loaded:
            return "STOPPED", True
        if control_loaded is not worker_loaded:
            return "AMBIGUOUS", False
        if startup_deadline is None:
            ready = self._control_ready(expected_sha)
        else:
            try:
                ready = self._control_ready(
                    expected_sha, timeout=self._startup_timeout(startup_deadline, 10.0)
                )
            except subprocess.TimeoutExpired:
                # launchd can accept a connection while initial composition
                # still precedes the status handler. Only this startup wait
                # treats that bounded status timeout as not-yet-READY.
                ready = False
        if ready:
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
            or info.st_uid != _CONFIG_ROOT_UID
            or info.st_gid != _CONFIG_ROOT_GID
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
        if set(value) & _A2_RESTORE_RECEIPT_FIELDS:
            if (value.get("operation") != "A2_RETURN_SOCKET_RESTORE"
                    or type(value.get("a2_prior_receipt_present")) is not bool
                    or any(re.fullmatch(r"[0-9a-f]{64}", str(value.get(field, ""))) is None
                           for field in _A2_RESTORE_RECEIPT_FIELDS - {"a2_prior_receipt_present"})):
                raise TransactionEffectUnknown()
            required |= _A2_RESTORE_RECEIPT_FIELDS
        elif value.get("operation") == "A2_RETURN_SOCKET_RESTORE":
            raise TransactionEffectUnknown()
        if set(value) & _FINITE_RECEIPT_FIELDS:
            if (value.get("operation") not in {"FINITE_CONTROL_STAGE", "FINITE_CONTROL_RETIRE"}
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
                or (value.get("phase") not in {"LOCKED", "PREDECESSOR_RECEIPT_RETAINED"}
                    and after_inode is None)
            ):
                raise TransactionEffectUnknown()
            required |= _GATEWAY_MANIFEST_FIELDS
        elif value.get("operation") == OS_GATEWAY_PUBLICATION:
            # A gateway marker is never valid without its own closed fields.
            raise TransactionEffectUnknown()
        if set(value) & _MCP_AUDIT_FIELDS:
            if value.get("operation") != OS_GATEWAY_PUBLICATION or not _MCP_AUDIT_FIELDS <= set(value):
                raise TransactionEffectUnknown()
            from ops.executive_os import mcp_auth_audit_directories as mcp_audit
            try:
                mcp_audit.validate_observation(value[_MCP_AUDIT_BEFORE_FIELD])
                after = value[_MCP_AUDIT_AFTER_FIELD]
                if after is not None:
                    mcp_audit.validate_transition(value[_MCP_AUDIT_BEFORE_FIELD], after)
                elif value.get("phase") not in {"LOCKED", "PREDECESSOR_RECEIPT_RETAINED"}:
                    raise ValueError("MCP audit identities were not retained")
            except (ValueError, TypeError) as exc:
                raise TransactionEffectUnknown() from exc
            required |= _MCP_AUDIT_FIELDS
        if set(value) & _GATEWAY_SUCCESSOR_FIELDS:
            archive_identity = value.get("gateway_predecessor_archive_identity")
            if (value.get("operation") != OS_GATEWAY_PUBLICATION
                    or not _GATEWAY_SUCCESSOR_FIELDS <= set(value)
                    or type(value.get("gateway_predecessor_receipt_sha256")) is not str
                    or re.fullmatch(r"[0-9a-f]{64}", value["gateway_predecessor_receipt_sha256"]) is None
                    or not _gateway_receipt_identity_valid(value.get("gateway_predecessor_receipt_identity"))
                    or (archive_identity is not None and not _gateway_receipt_identity_valid(archive_identity))
                    or (value.get("phase") != "LOCKED" and archive_identity is None)
                    or value.get("gateway_prior_grant_present") is not True):
                raise TransactionEffectUnknown()
            required |= _GATEWAY_SUCCESSOR_FIELDS
        elif value.get("operation") == OS_GATEWAY_PUBLICATION and value.get("phase") == "PREDECESSOR_RECEIPT_RETAINED":
            raise TransactionEffectUnknown()
        if set(value) & _COMPONENT_MANIFEST_FIELDS:
            # A Control component marker is refused unless it names THIS
            # operation and every closed component field is exactly shaped.
            # The receipt-presence flags and the two launchd preimages are
            # booleans; the mode is one closed value; the rest are digests.
            # An old schema is never reinterpreted as a component update and
            # vice versa.
            if (value.get("operation") != CONTROL_COMPONENT_UPDATE
                    or type(value.get("component_prior_autonomy_receipt_present")) is not bool
                    or type(value.get("component_prior_ceo_receipt_present")) is not bool
                    or type(value.get("component_prior_component_receipt_present")) is not bool
                    or type(value.get("component_prior_control_launchd_disabled")) is not bool
                    or type(value.get("component_prior_worker_launchd_disabled")) is not bool
                    or value.get("component_mode") not in _COMPONENT_MODES
                    or _TIMESTAMP_RE.fullmatch(str(value.get("component_observed_at", ""))) is None
                    or any(re.fullmatch(r"[0-9a-f]{64}", str(value.get(field, ""))) is None
                           for field in _COMPONENT_DIGEST_MANIFEST_FIELDS)):
                raise TransactionEffectUnknown()
            # The Worker is disabled in BOTH modes, and the Control is
            # explicitly disabled in exactly the offline mode.  A marker that
            # contradicts its own mode is never a valid component marker.
            if (value.get("component_prior_worker_launchd_disabled") is not True
                    or (value.get("component_mode") == _COMPONENT_OFFLINE_MODE)
                    != (value.get("component_prior_control_launchd_disabled") is True)):
                raise TransactionEffectUnknown()
            # The OPTIONAL selection member is STRUCTURED: it has its own
            # closed validator and is never read as a digest string.
            if "component_binding" in value:
                _require_component_binding_member(value["component_binding"])
            required |= _COMPONENT_MANIFEST_FIELDS
        elif value.get("operation") == CONTROL_COMPONENT_UPDATE:
            # A component marker is never valid without its own closed fields.
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
        # The OPTIONAL selection member is part of a component marker only
        # when that marker carries a selection.  A component marker without
        # one keeps the legacy key set exactly.
        allowed_sets = {
            frozenset(required),
            frozenset(allowed_with_control_preimage),
        }
        if value.get("operation") == CONTROL_COMPONENT_UPDATE:
            allowed_sets.add(
                frozenset(required | _COMPONENT_OPTIONAL_MANIFEST_FIELDS))
            allowed_sets.add(
                frozenset(
                    required
                    | _COMPONENT_OPTIONAL_MANIFEST_FIELDS
                    | {_CONTROL_LAUNCHD_PREIMAGE_FIELD}
                )
            )
        if (
            frozenset(keys)
            not in allowed_sets
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
        if current is not None and set(current) & _A2_RESTORE_RECEIPT_FIELDS:
            value.update({key: current[key] for key in _A2_RESTORE_RECEIPT_FIELDS})
        if current is not None and set(current) & _FINITE_RECEIPT_FIELDS:
            value.update({key: current[key] for key in _FINITE_RECEIPT_FIELDS})
        if current is not None and set(current) & _PAID_RECEIPT_FIELDS:
            value.update({key: current[key] for key in _PAID_RECEIPT_FIELDS})
        if current is not None and set(current) & _GATEWAY_MANIFEST_FIELDS:
            value.update({key: current[key] for key in _GATEWAY_MANIFEST_FIELDS})
        if current is not None and set(current) & _MCP_AUDIT_FIELDS:
            value.update({key: current[key] for key in _MCP_AUDIT_FIELDS})
        if current is not None and set(current) & _GATEWAY_SUCCESSOR_FIELDS:
            value.update({key: current[key] for key in _GATEWAY_SUCCESSOR_FIELDS})
        if current is not None and set(current) & _COMPONENT_MANIFEST_FIELDS:
            value.update({key: current[key] for key in _COMPONENT_MANIFEST_FIELDS})
        if current is not None and "component_binding" in current:
            # The OPTIONAL selection member is carried forward unchanged: it
            # is part of the retained identity of this operation.
            value["component_binding"] = current["component_binding"]
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
        deadline = time.monotonic() + _SERVICES_READY_TIMEOUT
        while time.monotonic() < deadline:
            service_state, reconciled = self._service_state(
                expected_sha, startup_deadline=deadline
            )
            if time.monotonic() >= deadline:
                break
            if reconciled and service_state == "READY":
                if self._active_transaction is not None:
                    self._persist_phase(self._active_transaction, "READY_PROVEN")
                return
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(1.0, remaining))
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
        if set(manifest) & _A2_RESTORE_RECEIPT_FIELDS:
            expected.add(_A2_RESTORE_RECEIPT_ARCHIVE)
            archives.append(AUTONOMY_TRANSACTION / _A2_RESTORE_RECEIPT_ARCHIVE)
        if set(manifest) & _FINITE_RECEIPT_FIELDS:
            expected.add(_FINITE_RECEIPT_ARCHIVE)
            archives.append(AUTONOMY_TRANSACTION / _FINITE_RECEIPT_ARCHIVE)
        if set(manifest) & _PAID_RECEIPT_FIELDS:
            expected.add(_PAID_RECEIPT_ARCHIVE)
            archives.append(AUTONOMY_TRANSACTION / _PAID_RECEIPT_ARCHIVE)
        if set(manifest) & _GATEWAY_MANIFEST_FIELDS:
            expected.add(_GATEWAY_GRANT_ARCHIVE)
            archives.append(AUTONOMY_TRANSACTION / _GATEWAY_GRANT_ARCHIVE)
        if set(manifest) & _COMPONENT_MANIFEST_FIELDS:
            component_archives = _component_archive_names(manifest)
            expected.update(component_archives)
            archives.extend(
                AUTONOMY_TRANSACTION / name for name in component_archives
            )
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
        try:
            completed = subprocess.run(
                command,
                cwd=release,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=10,
            )
        except subprocess.TimeoutExpired:
            # An absent read-only status witness is not an admission proof.
            # Keep transient startup latency inside the existing bounded wait;
            # never retry a mutation or suppress permission/interruption errors.
            return False
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
        self._predecessor_receipt: GatewayPredecessorReceipt | None = None

    # ------------------------------------------------------------------
    # Closed compiler adapter.  The publication compiler is a separate pure
    # module exposing one frozen candidate: exact before-images plus a tuple
    # of GatewayArtifact(path, kind, content, sha256, byte_count).  This small
    # adapter translates those actual fields onto the owner's existing internal
    # map and refuses anything that drifts from the bytes this host qualified
    # itself.  No flattened attribute expectation is invented here.
    # ------------------------------------------------------------------

    def derive_capability_profile_digests(
        self, release_sha: str, profile_ids: tuple[str, ...]
    ) -> dict[str, str]:
        from control_plane import executive_installed_peer as installed
        from ops.executive_os.mcp_component_update import (
            derive_sealed_capability_profile_digests,
        )
        return derive_sealed_capability_profile_digests(
            release_sha, profile_ids,
            installed._Budget(installed._SERVICE_BUDGET_SECONDS))

    def _compile_gateway_candidates(
        self,
        prior_mcp_config_bytes: bytes,
        prior_mcp_plist_bytes: bytes,
        *,
        publication_document: Mapping[str, Any],
        helper_hashes: Mapping[str, str],
        expected_sha: str,
        bundle_digest: str,
        capability_profile_digests: dict[str, str] | None = None,
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
                capability_profile_digests=capability_profile_digests,
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
        try:
            value = _release_manifest_json(expected_sha)
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
        templates = self._gateway_templates(receipt["launch_config"])
        document = {
            "schema": assets.LAUNCH_SCHEMA,
            "release_sha": expected_sha,
            "source_tree": tree_sha,
            "release_bundle_digest": bundle_digest,
            "web_client_id": receipt["web_client_id"],
            "executive_resource": resource,
            "launch_config": receipt["launch_config"],
            "launch_config_sha256": receipt["launch_config_sha256"],
            "commission_templates": templates,
        }
        return receipt_bytes, document, bundle_digest

    def _gateway_templates(self, launch_config: str) -> tuple[dict[str, Any], ...]:
        """Derive exact templates for the sealed v1 or finite v2 enrollment.

        All fields and optional-field presence come from the same qualified
        Launch receipt. Profile selection never supplies new grant authority.
        """
        from control_plane import ceo_request
        from ops.executive_os.os_release_assets import _decode_launch_bindings

        try:
            bindings = _decode_launch_bindings(json.loads(launch_config))
        except (TypeError, ValueError) as exc:
            raise GatewayPublicationError("gateway_template_refused") from exc
        if bindings is None:
            raise GatewayPublicationError("gateway_template_refused")
        templates = []
        for values in bindings:
            projects = values.get("projects") if type(values) is dict else None
            profiles = values.get("profiles") if type(values) is dict else None
            if (
                type(projects) is not list
                or len(projects) != 1
                or type(projects[0]) is not dict
                or type(profiles) is not list
                or len(profiles) not in (1, 2)
                or any(type(profile) is not dict for profile in profiles)
            ):
                raise GatewayPublicationError("gateway_template_refused")
            profile_refs = [profile.get("ref") for profile in profiles]
            if profile_refs not in (
                ["research_only"], ["research_only", "native_research_only"]
            ):
                raise GatewayPublicationError("gateway_template_refused")
            if len(profile_refs) == 2 and (
                type(values.get("attemptLimit")) is not int
                or values["attemptLimit"] != 1
                or values.get("allowedWritePaths", []) != []
                or values.get("validation", {}) != {}
            ):
                raise GatewayPublicationError("gateway_template_refused")
            priority = values.get("priority")
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
                any(profile not in ceo_request.EXECUTION_PROFILES for profile in profile_refs)
                or type(priority) is not int
                or not ceo_request.MIN_PRIORITY <= priority <= ceo_request.MAX_PRIORITY
                or type(attempt_limit) is not int
                or not ceo_request.MIN_ATTEMPT_LIMIT
                <= attempt_limit
                <= ceo_request.MAX_ATTEMPT_LIMIT
            ):
                raise GatewayPublicationError("gateway_template_refused")
            templates.extend({**copy.deepcopy(template), "execution_profile": profile}
                             for profile in profile_refs)
        return tuple(templates)

    def _gateway_template(self, launch_config: str) -> dict[str, Any]:
        """Compatibility entry for the unchanged single-choice form only."""
        templates = self._gateway_templates(launch_config)
        if len(templates) != 1:
            raise GatewayPublicationError("gateway_template_refused")
        return templates[0]

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

    def observe_studio(self, expected_sha: str) -> GatewayStudioEvidence:
        from integrations.studio_direct_mcp import private_service

        home, studio_gid = self._studio_account_identity()
        studio_uid = OS_GATEWAY_STUDIO_UID
        base = home / _GATEWAY_STUDIO_BASE_REL
        plist_path = home / _GATEWAY_STUDIO_PLIST_REL
        release = SYSTEM_ROOT / "releases" / expected_sha
        source = release / "integrations/studio_direct_mcp"
        config_path = base / "config.json"

        # Source basenames derive only from this already qualified Root
        # release. All Studio-owned bytes below are observed through held
        # descriptors by the single closed reader, never pathname hashing.
        from ops.executive_os.os_gateway_studio_reader import (
            StudioObservationError,
            observe_studio_files,
        )
        try:
            source_files = private_service._check_source_files(source)
            incoming = {
                item.name: private_service._sha256_file(item) for item in source_files
            }
            self._require_studio_stopped()
            observed = observe_studio_files(
                home=home,
                uid=studio_uid,
                gid=studio_gid,
                source_file_names=tuple(item.name for item in source_files),
            )
        except (StudioObservationError, SystemExit) as exc:
            raise GatewayPublicationError("gateway_studio_invalid") from exc
        manifest_raw = observed.manifest_bytes
        config_raw = observed.config_bytes
        agent_plist_raw = observed.plist_bytes
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
            or sha256_bytes(config_raw) != manifest["configHash"]
            or sha256_bytes(agent_plist_raw) != manifest["plistHash"]
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

        if observed.installed_file_hashes != files:
            raise GatewayPublicationError("gateway_studio_invalid")
        node_hash = observed.node_sha256
        backend_hash = observed.backend_sha256
        if (
            node_hash != manifest["nodeHash"]
            or backend_hash != manifest["backendHash"]
            or observed.dependency_tree_sha256 != dependency
        ):
            raise GatewayPublicationError("gateway_studio_invalid")

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
            # Match the normal installer's exact canonical macOS ancestor.
            # No other admin-group directory acquires release custody.
            group_valid = info.st_gid == 0 or (
                current == Path("/Library/Application Support")
                and info.st_gid == 80
                and stat.S_IMODE(info.st_mode) == 0o755
            )
            if (
                stat.S_ISLNK(info.st_mode)
                or not stat.S_ISDIR(info.st_mode)
                or info.st_uid != 0
                or not group_valid
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

    @staticmethod
    def _gateway_receipt_history_path(receipt_sha256: str) -> Path:
        if type(receipt_sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", receipt_sha256) is None:
            raise GatewayPublicationError("gateway_receipt_invalid")
        return CONFIG_ROOT / ("os-gateway-publication-" + receipt_sha256 + ".json")

    @staticmethod
    def _gateway_receipt_bytes(path: Path, *, mode: int) -> tuple[bytes, os.stat_result]:
        raw, info = _read_root_file(path, modes=frozenset({mode}), uid=0, gid=0)
        # The incumbent reader owns root custody. Join its descriptor's
        # observation back to the same unchanged leaf after the bounded read.
        # A renamed same-byte replacement is not the admitted predecessor.
        if _gateway_receipt_identity(info) != _gateway_receipt_identity(path.lstat()):
            raise TransactionEffectUnknown()
        return raw, info

    def gateway_receipt_admission(
        self, request: GatewayPublicationRequest
    ) -> GatewayPredecessorReceipt | None:
        """Default absence law, or an explicit exact completed predecessor.

        This is still the same publication owner. A successor cannot select a
        path, rewrite its predecessor, or adopt an occupied transaction. The
        permanent archive name is derived from the qualified receipt bytes.
        """
        expected = request.predecessor_receipt_sha256
        if expected is None:
            self.require_gateway_receipt_absent()
            return None
        if (type(expected) is not str or re.fullmatch(r"[0-9a-f]{64}", expected) is None
                or request.prior_grant_absent is not False
                or type(request.prior_grant_sha256) is not str
                or re.fullmatch(r"[0-9a-f]{64}", request.prior_grant_sha256) is None):
            raise GatewayPublicationError("gateway_receipt_conflict")
        try:
            raw, info = self._gateway_receipt_bytes(OS_GATEWAY_RECEIPT, mode=0o444)
            payload = json.loads(raw)
        except (HostControlError, OSError, ValueError, UnicodeError, TransactionEffectUnknown) as exc:
            raise GatewayPublicationError("gateway_receipt_invalid") from exc
        if sha256_bytes(raw) != expected:
            raise GatewayPublicationError("gateway_receipt_conflict")
        if (type(payload) is not dict or raw != _encoded_json(payload)
                or type(payload.get("expected_sha")) is not str
                or _SHA_RE.fullmatch(payload["expected_sha"]) is None
                or payload["expected_sha"] == request.expected_sha
                or type(payload.get("transaction_id")) is not str
                or re.fullmatch(r"autonomy-[0-9a-f]{12}", payload["transaction_id"]) is None
                or type(payload.get("release_bundle_digest")) is not str
                or re.fullmatch(r"[0-9a-f]{64}", payload["release_bundle_digest"]) is None
                or type(payload.get("prior_commission_grant_present")) is not bool):
            raise GatewayPublicationError("gateway_receipt_invalid")
        validate_gateway_receipt_document(
            payload, transaction_id=payload["transaction_id"],
            expected_sha=payload["expected_sha"], bundle_digest=payload["release_bundle_digest"],
            mcp_config_sha256=request.prior_mcp_config_sha256,
            mcp_plist_sha256=request.prior_mcp_plist_sha256,
            grant_sha256=request.prior_grant_sha256,
            prior_grant_present=payload["prior_commission_grant_present"],
            predecessor_receipt_sha256=payload.get("predecessor_receipt_sha256"),
        )
        history = self._gateway_receipt_history_path(expected)
        if history.exists() or history.is_symlink():
            raise GatewayPublicationError("gateway_receipt_conflict")
        return GatewayPredecessorReceipt(raw, tuple(_gateway_receipt_identity(info)), payload)

    def qualify_gateway_predecessor(
        self, predecessor: GatewayPredecessorReceipt, preparation: GatewayPreparation
    ) -> None:
        self._qualify_gateway_predecessor_release(predecessor, preparation.prior_release)

    def _qualify_gateway_predecessor_release(
        self, predecessor: GatewayPredecessorReceipt, prior_release: str
    ) -> None:
        document = predecessor.document
        if document["expected_sha"] != prior_release:
            raise GatewayPublicationError("gateway_receipt_invalid")
        tree = self._gateway_release_tree(prior_release)
        _raw, _launch, bundle = self.qualify_launch_publication(prior_release, tree)
        if bundle != document["release_bundle_digest"]:
            raise GatewayPublicationError("gateway_receipt_invalid")
        try:
            self._require_predecessor_receipt_current(
                sha256_bytes(predecessor.raw), list(predecessor.identity),
            )
        except TransactionEffectUnknown as exc:
            raise GatewayPublicationError("gateway_receipt_conflict") from exc

    def _require_predecessor_receipt_current(self, receipt_sha256: str, identity: list[int]) -> None:
        try:
            raw, info = self._gateway_receipt_bytes(OS_GATEWAY_RECEIPT, mode=0o444)
            if sha256_bytes(raw) != receipt_sha256 or _gateway_receipt_identity(info) != identity:
                raise ValueError("predecessor receipt changed")
        except (HostControlError, OSError, ValueError) as exc:
            raise TransactionEffectUnknown() from exc

    def _predecessor_receipt_archive(self, manifest: Mapping[str, Any], *, permanent: bool) -> bytes:
        """Qualify retained bytes; reconciliation never creates either archive."""
        expected = manifest["gateway_predecessor_receipt_sha256"]
        path = (self._gateway_receipt_history_path(expected) if permanent
                else AUTONOMY_TRANSACTION / _GATEWAY_RECEIPT_ARCHIVE)
        try:
            raw, info = self._gateway_receipt_bytes(path, mode=0o444 if permanent else 0o400)
            if (sha256_bytes(raw) != expected
                    or (permanent and _gateway_receipt_identity(info)
                        != manifest["gateway_predecessor_archive_identity"])):
                raise ValueError("retained predecessor differs")
        except (HostControlError, OSError, ValueError) as exc:
            raise TransactionEffectUnknown() from exc
        return raw

    def _retain_gateway_predecessor(self, transaction: TransactionContext) -> None:
        manifest = self._manifest()
        if not _GATEWAY_SUCCESSOR_FIELDS <= set(manifest):
            return
        self._recheck_gateway_bound(transaction)
        raw = self._predecessor_receipt_archive(manifest, permanent=False)
        path = self._gateway_receipt_history_path(manifest["gateway_predecessor_receipt_sha256"])
        # The kernel-exclusive rename preserves a late occupant. A lost
        # publication acknowledgement retains this original marker and never
        # acquires archive identity retroactively.
        identity = self._publish_gateway_receipt_file(
            transaction, path, raw, replace_predecessor=False,
        )
        if self._sealed_gateway is None:
            raise TransactionEffectUnknown()
        self._sealed_gateway["gateway_predecessor_archive_identity"] = identity
        self._persist_phase(transaction, "PREDECESSOR_RECEIPT_RETAINED")

    def _publish_gateway_receipt_file(
        self, transaction: TransactionContext, destination: Path, payload: bytes,
        *, replace_predecessor: bool,
    ) -> list[int]:
        """Stage once under the existing config mutex, then publish once.

        History uses the incumbent kernel no-replace rename. The successor
        receipt replaces only its retained predecessor, rechecked after all
        staging and fsync work. This serializes admitted publication owners;
        it does not claim an inode-CAS syscall against an unrelated root writer.
        """
        from ops.executive_os.capacity_host_artifacts import _rename_exclusive

        parent = descriptor = -1
        stage = ""
        staged_identity: tuple[int, int] | None = None
        renamed = False
        try:
            self._config_root_safe()
            parent = self._publication_mutex()

            def require_parent() -> None:
                # The mutex acquisition can block. Rejoin the held directory
                # to the trusted canonical name AFTER acquisition, and again
                # after staging, before either canonical publication.
                self._config_root_safe()
                held, named = os.fstat(parent), CONFIG_ROOT.lstat()
                if (not stat.S_ISDIR(held.st_mode)
                        or (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino)
                        or held.st_uid != _CONFIG_ROOT_UID
                        or held.st_gid != _CONFIG_ROOT_GID):
                    raise TransactionEffectUnknown()

            require_parent()
            if destination.parent != CONFIG_ROOT:
                raise TransactionEffectUnknown()
            manifest = self._manifest()
            if (not _GATEWAY_SUCCESSOR_FIELDS <= set(manifest)
                    or manifest.get("operation") != OS_GATEWAY_PUBLICATION
                    or manifest.get("transaction_id") != transaction.transaction_id
                    or manifest.get("expected_sha") != transaction.expected_sha):
                raise TransactionEffectUnknown()
            if replace_predecessor:
                if (destination != OS_GATEWAY_RECEIPT
                        or not _gateway_receipt_identity_valid(
                            manifest["gateway_predecessor_archive_identity"])):
                    raise TransactionEffectUnknown()
            elif (destination != self._gateway_receipt_history_path(
                        manifest["gateway_predecessor_receipt_sha256"])
                    or manifest.get("phase") != "LOCKED"
                    or manifest["gateway_predecessor_archive_identity"] is not None
                    or payload != self._predecessor_receipt_archive(manifest, permanent=False)):
                raise TransactionEffectUnknown()

            stage = f".{destination.name}.{os.getpid()}.{secrets.token_hex(8)}.stage"
            descriptor = os.open(
                stage, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600, dir_fd=parent,
            )
            opened = os.fstat(descriptor)
            staged_identity = (opened.st_dev, opened.st_ino)
            pending = memoryview(payload)
            while pending:
                count = os.write(descriptor, pending)
                if count <= 0:
                    raise OSError("short gateway receipt write")
                pending = pending[count:]
            os.fchown(descriptor, _CONFIG_ROOT_UID, _CONFIG_ROOT_GID)
            os.fchmod(descriptor, 0o444)
            os.fsync(descriptor)
            staged = os.fstat(descriptor)
            if not _gateway_receipt_identity_valid(_gateway_receipt_identity(staged)):
                raise TransactionEffectUnknown()
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.read(descriptor, len(payload) + 1) != payload:
                raise TransactionEffectUnknown()
            named = os.stat(stage, dir_fd=parent, follow_symlinks=False)
            if _gateway_receipt_identity(named) != _gateway_receipt_identity(staged):
                raise TransactionEffectUnknown()

            require_parent()
            self._recheck_gateway_bound(transaction)
            if self._manifest() != manifest:
                raise TransactionEffectUnknown()
            if replace_predecessor:
                self._predecessor_receipt_archive(manifest, permanent=False)
                self._predecessor_receipt_archive(manifest, permanent=True)
                if _receipt_metadata(OS_GATEWAY_RECEIPT) != ReceiptMetadata(
                    uid=0, gid=0, mode=0o444, nlink=1, is_regular=True,
                    is_symlink=False, has_acl=False,
                ):
                    raise TransactionEffectUnknown()
                # No staging, metadata mutation or fsync separates this final
                # predecessor read from the descriptor-relative replacement.
                self._require_predecessor_receipt_current(
                    manifest["gateway_predecessor_receipt_sha256"],
                    manifest["gateway_predecessor_receipt_identity"],
                )
                os.replace(stage, destination.name, src_dir_fd=parent, dst_dir_fd=parent)
            else:
                _rename_exclusive(parent, stage, parent, destination.name)
            renamed = True
            os.fsync(parent)
            require_parent()
            readback, published = self._gateway_receipt_bytes(destination, mode=0o444)
            if (readback != payload
                    or _gateway_receipt_identity(published)
                    != _gateway_receipt_identity(os.fstat(descriptor))):
                raise TransactionEffectUnknown()
            # Rename can change metadata; retain the observed POST-rename
            # identity, never the private stage's earlier timestamps.
            return _gateway_receipt_identity(published)
        except TransactionEffectUnknown:
            raise
        except Exception as exc:
            raise TransactionEffectUnknown() from exc
        finally:
            if not renamed and parent >= 0 and stage and staged_identity is not None:
                # Remove only this still-private stage. Any possibly published
                # canonical archive/receipt and its original marker survive.
                try:
                    named = os.stat(stage, dir_fd=parent, follow_symlinks=False)
                    held = os.fstat(descriptor)
                    if (stat.S_ISREG(named.st_mode) and named.st_nlink == 1
                            and (named.st_dev, named.st_ino) == staged_identity
                            and (held.st_dev, held.st_ino) == staged_identity):
                        os.unlink(stage, dir_fd=parent)
                        os.fsync(parent)
                except OSError:
                    pass
            if descriptor >= 0:
                os.close(descriptor)
            if parent >= 0:
                os.close(parent)

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
        self._verify_mcp_auth_audit_directories(manifest)

    def _observe_mcp_auth_audit_directories(self, config_bytes: bytes) -> Mapping[str, Any]:
        from ops.executive_os import mcp_auth_audit_directories as mcp_audit
        try:
            return mcp_audit.observe(mcp_audit.required_names(config_bytes))
        except Exception as exc:
            raise GatewayPublicationError("gateway_audit_directory_invalid") from exc

    def _establish_mcp_auth_audit_directories(self, transaction: TransactionContext) -> Mapping[str, Any]:
        from ops.executive_os import mcp_auth_audit_directories as mcp_audit
        if self._transaction_owner_fd is None or self._active_transaction is not transaction:
            raise TransactionEffectUnknown()
        self._verify_published_inode(self._transaction_owner_fd)
        manifest = self._manifest()
        required_phase = ("PREDECESSOR_RECEIPT_RETAINED"
                          if _GATEWAY_SUCCESSOR_FIELDS <= set(manifest) else "LOCKED")
        if (manifest.get("operation") != OS_GATEWAY_PUBLICATION
                or manifest.get("transaction_id") != transaction.transaction_id
                or manifest.get("phase") != required_phase
                or manifest.get(_MCP_AUDIT_AFTER_FIELD) is not None
                or not _MCP_AUDIT_FIELDS <= set(manifest)):
            raise TransactionEffectUnknown()
        config = self._gateway_root_file(OS_GATEWAY_MCP_CONFIG, code="gateway_target_invalid")
        if (sha256_bytes(config) != manifest["gateway_prior_mcp_config_sha256"]
                or self._observe_mcp_auth_audit_directories(config) != manifest[_MCP_AUDIT_BEFORE_FIELD]):
            raise TransactionEffectUnknown()
        return mcp_audit.establish(manifest[_MCP_AUDIT_BEFORE_FIELD])

    def _verify_mcp_auth_audit_directories(self, manifest: Mapping[str, Any]) -> None:
        if not _MCP_AUDIT_FIELDS & set(manifest):
            return  # Existing historical markers retain their original contract.
        from ops.executive_os import mcp_auth_audit_directories as mcp_audit
        try:
            after = manifest[_MCP_AUDIT_AFTER_FIELD]
            mcp_audit.validate_transition(manifest[_MCP_AUDIT_BEFORE_FIELD], after)
            current = self._gateway_root_file(OS_GATEWAY_MCP_CONFIG, code="gateway_target_invalid")
            if set(mcp_audit.required_names(current)) != set(after["leaves"]):
                raise ValueError("MCP audit policy selection changed")
            mcp_audit.verify(after)
        except Exception as exc:
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
        if phase not in {"AUDIT_DIRECTORY_READY", "PREDECESSOR_RECEIPT_RETAINED"}:
            super()._persist_phase(transaction, phase, operation=operation)
            return
        if self._transaction_owner_fd is None or self._active_transaction != transaction:
            raise TransactionEffectUnknown()
        self._verify_published_inode(self._transaction_owner_fd)
        current = self._manifest()
        value = self._manifest_document(transaction, phase, operation=OS_GATEWAY_PUBLICATION)
        retaining = phase == "PREDECESSOR_RECEIPT_RETAINED"
        changed_field = "gateway_predecessor_archive_identity" if retaining else _GATEWAY_AUDIT_AFTER_FIELD
        changed_fields = {changed_field}
        if not retaining and _MCP_AUDIT_FIELDS <= set(current):
            changed_fields.add(_MCP_AUDIT_AFTER_FIELD)
        prior_phase = ("PREDECESSOR_RECEIPT_RETAINED"
                       if not retaining and _GATEWAY_SUCCESSOR_FIELDS <= set(current) else "LOCKED")
        if (
            current.get("operation") != OS_GATEWAY_PUBLICATION
            or current.get("phase") != prior_phase
            or operation not in (None, OS_GATEWAY_PUBLICATION)
            or (retaining and (not _GATEWAY_SUCCESSOR_FIELDS <= set(current)
                               or current.get(changed_field) is not None))
            or {key: item for key, item in current.items()
                if key not in {"phase", *changed_fields}}
            != {key: item for key, item in value.items()
                if key not in {"phase", *changed_fields}}
        ):
            raise TransactionEffectUnknown()
        if retaining:
            self._predecessor_receipt_archive(value, permanent=True)
        else:
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
        if self._predecessor_receipt is not None:
            _atomic_file(generation / _GATEWAY_RECEIPT_ARCHIVE, self._predecessor_receipt.raw,
                         mode=0o400, uid=0, gid=0, replace=False)
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
        if _GATEWAY_SUCCESSOR_FIELDS <= set(manifest):
            self._require_predecessor_receipt_current(
                manifest["gateway_predecessor_receipt_sha256"],
                manifest["gateway_predecessor_receipt_identity"],
            )
            if manifest["gateway_predecessor_archive_identity"] is not None:
                self._predecessor_receipt_archive(manifest, permanent=True)
        if manifest.get(_MCP_AUDIT_AFTER_FIELD) is not None:
            self._verify_mcp_auth_audit_directories(manifest)

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
        if self._observe_mcp_auth_audit_directories(preparation.candidate["mcp_config_bytes"]) != manifest.get(_MCP_AUDIT_BEFORE_FIELD):
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
        manifest = self._manifest()
        if _GATEWAY_SUCCESSOR_FIELDS <= set(manifest):
            self._publish_gateway_receipt_file(
                transaction, OS_GATEWAY_RECEIPT, encoded, replace_predecessor=True,
            )
            return
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
                predecessor_receipt_sha256=manifest.get("gateway_predecessor_receipt_sha256"),
            )
        except (HostControlError, GatewayPublicationError) as exc:
            raise TransactionEffectUnknown() from exc
        # Close the receipt-write interval against target metadata drift.
        # A retained receipt with a still-present marker is not completion.
        self._qualify_published_gateway(manifest)
        # The whole publication is complete ONLY with its canonical audit
        # prerequisite still qualified and bound to THIS original intent.
        self._verify_gateway_audit_directory(manifest)
        if _GATEWAY_SUCCESSOR_FIELDS <= set(manifest):
            self._predecessor_receipt_archive(manifest, permanent=False)
            self._predecessor_receipt_archive(manifest, permanent=True)
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
        archives = (*self._archive_paths(), AUTONOMY_TRANSACTION / _GATEWAY_GRANT_ARCHIVE)
        if _GATEWAY_SUCCESSOR_FIELDS <= set(manifest):
            expected.add(_GATEWAY_RECEIPT_ARCHIVE)
            archives += (AUTONOMY_TRANSACTION / _GATEWAY_RECEIPT_ARCHIVE,)
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
    predecessor_receipt_sha256: str | None = None,
) -> dict[str, Any]:
    """The ONE fixed terminal receipt: original id plus exact target hashes."""

    value = {
        "schema_version": (OS_GATEWAY_RECEIPT_SCHEMA if predecessor_receipt_sha256 is None
                           else OS_GATEWAY_SUCCESSOR_RECEIPT_SCHEMA),
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
    if predecessor_receipt_sha256 is not None:
        value["predecessor_receipt_sha256"] = predecessor_receipt_sha256
    return value


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
    predecessor_receipt_sha256: str | None = None,
) -> None:
    keys = _GATEWAY_RECEIPT_KEYS
    schema = OS_GATEWAY_RECEIPT_SCHEMA
    if predecessor_receipt_sha256 is not None:
        if (type(predecessor_receipt_sha256) is not str
                or re.fullmatch(r"[0-9a-f]{64}", predecessor_receipt_sha256) is None
                or prior_grant_present is not True):
            raise GatewayPublicationError("gateway_receipt_invalid")
        keys = keys | {"predecessor_receipt_sha256"}
        schema = OS_GATEWAY_SUCCESSOR_RECEIPT_SCHEMA
    if (
        type(payload) is not dict
        or set(payload) != keys
        or payload["schema_version"] != schema
        or payload.get("predecessor_receipt_sha256") != predecessor_receipt_sha256
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
    host: ProductionGatewayPublicationHost, request: GatewayPublicationRequest,
    *, predecessor: GatewayPredecessorReceipt | None = None,
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
    # Join the actual old receipt/config/grant before deriving any successor
    # configuration. The existing final check still runs before durable intent.
    if predecessor is not None:
        host._qualify_gateway_predecessor_release(predecessor, prior_release)
    from ops.executive_os.mcp_component_update import _mission_capability_profile_digests
    try:
        capability_profile_digests = _mission_capability_profile_digests(
            host, request.expected_sha, prior_mcp_config)
    except Exception as exc:
        raise GatewayPublicationError("gateway_capability_profiles_invalid") from exc
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
    templates = launch_document["commission_templates"]
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
        "grants": [{"principal_scope": scope, "template": template}
                   for template in templates],
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
        capability_profile_digests=capability_profile_digests,
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
        commission_templates=templates,
        helper_hashes=helper_hashes,
        capability_profile_digests=capability_profile_digests,
    )
    mcp_auth_audit = host._observe_mcp_auth_audit_directories(candidate["mcp_config_bytes"])
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
        commission_templates=templates,
        derived_policy=derived_policy,
        audit_directory=audit_directory,
        mcp_auth_audit=mcp_auth_audit,
        studio=studio,
    )


# ---------------------------------------------------------------------------
# The Control component update: one closed, root-only composition that
# retargets the EXISTING installed Control source onto an already-staged
# target release, through the ONE existing ``AUTONOMY_TRANSACTION`` owner.
# ---------------------------------------------------------------------------


class ComponentUpdateRefused(RuntimeError):
    """Refused before any installed-file, launchd or receipt effect.

    A refusal raised AFTER the transaction marker exists is never a zero-effect
    refusal: it retains the original transaction and names the phase that was
    still incomplete, so the caller reports an uncertain original operation
    rather than a clean one that never happened.
    """

    def __init__(
        self, code: str, *, phase: str | None = None, transaction_id: str | None = None
    ) -> None:
        super().__init__(code)
        self.code = code
        self.phase = phase
        self.transaction_id = transaction_id

    @property
    def incomplete(self) -> bool:
        """True when the original transaction was already claimed."""

        return self.transaction_id is not None


_COMPONENT_REFUSAL_CODES = frozenset(
    {
        "control_component_release_seal_invalid",
        "control_component_target_release_not_staged",
        "control_component_admin_checkout_unavailable",
        "control_component_interpreter_unqualified",
        "control_component_control_config_unreadable",
        "control_component_plist_unreadable",
        "control_component_source_mismatch",
        "control_component_schema_incompatible",
        "control_component_transaction_occupied",
        "control_component_transaction_absent",
        "control_component_authority_receipt_invalid",
        "control_component_authority_receipt_armed",
        "control_component_receipt_invalid",
        "control_component_receipt_preimage_mismatch",
        "control_component_worker_live",
        "control_component_worker_state_unknown",
        "control_component_worker_not_disabled",
        "control_component_control_state_mixed",
        "control_component_control_state_unknown",
        "control_component_launchd_state_unknown",
        "control_component_owner_not_quiescent",
        "control_component_service_uids_live",
        "control_component_plan_digest_mismatch",
        "control_component_hermes_read_selector_incomplete",
        "control_component_hermes_read_input_invalid",
        "control_component_native_conversation_selector_incomplete",
        "control_component_native_conversation_input_invalid",
        "control_component_native_conversation_binding_conflict",
        "control_component_selection_conflict",
        "control_component_hermes_read_binding_invalid",
        "control_component_hermes_read_binding_conflict",
        "control_component_binding_config_not_switched",
    }
)
# The phases from which a same-operation reconciliation may still perform the
# ONE control-observation publication this transaction owes.  The publication
# phase itself is NOT admissible: an attempted publication is never repeated.
_CONTROL_COMPONENT_PUBLICATION_ADMISSIBLE_PHASES = frozenset(
    {"CONTROL_COMPONENT_TARGETS_PROVEN", "CONTROL_COMPONENT_RECEIPT_REPLACED"}
)
# The one receipt-preserving projection: every field of the existing DISARMED
# authority receipt except the attested source release, the configuration
# digest correlation and the transaction label is preserved byte for byte.
_COMPONENT_RECEIPT_CORRELATION_FIELDS = frozenset(
    {
        "release_sha",
        "control_config_sha256",
        "prior_control_config_sha256",
        "transaction_id",
    }
)
_COMPONENT_CEO_PROJECTION_CORRELATION_FIELDS = frozenset(
    {"release_sha", "installed_sha", "transaction_id"}
)


def _component_refusal(code: str) -> ComponentUpdateRefused:
    if code not in _COMPONENT_REFUSAL_CODES:
        raise ValueError("unknown control component refusal")
    return ComponentUpdateRefused(code)


def _component_archive_names(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    """The sealed archives of one component transaction.

    The legacy transaction format is preserved exactly when the operation
    carries no selection: the three coordinated selection archives exist
    only for a transaction that sealed them.
    """

    names = list(_COMPONENT_ARCHIVES)
    if type(manifest.get("component_binding")) is dict:
        member = manifest["component_binding"]
        _require_component_binding_member(member)
        names.extend(_COMPONENT_NATIVE_BINDING_ARCHIVES
                     if member.get("input_kind") == "native_conversation"
                     else _COMPONENT_BINDING_ARCHIVES)
    return tuple(names)


def _require_component_binding_member(value: Any) -> None:
    """One closed selection member of a component marker.

    It is a STRUCTURED member, not a digest: it carries hashes, EXPLICIT
    presence, the derived destination and the ordered effect.  Every field
    is checked against its own closed shape, and the destination must be the
    one DERIVED from the candidate digest, so a marker can never name an
    artifact this operation did not compose.
    """

    from ops.executive_os import control_component_update as compiler

    if type(value) is not dict:
        raise TransactionEffectUnknown()
    native = value.get("input_kind") == "native_conversation"
    expected_keys = _COMPONENT_BINDING_MANIFEST_KEYS | ({"input_kind"} if native else set())
    if set(value) != expected_keys or native and value.get("prior_selector_present") is not True:
        raise TransactionEffectUnknown()
    for field in ("destination_present", "prior_selector_present", "execution_present"):
        if type(value.get(field)) is not bool:
            raise TransactionEffectUnknown()
    for field in ("bindings_count", "remote_transports_count"):
        count = value.get(field)
        if type(count) is not int or type(count) is bool or count < 0:
            raise TransactionEffectUnknown()
    for field in ("input_sha256", "candidate_sha256"):
        if re.fullmatch(r"[0-9a-f]{64}", str(value.get(field, ""))) is None:
            raise TransactionEffectUnknown()
    if value.get("prior_selector_present"):
        if re.fullmatch(r"[0-9a-f]{64}", str(value.get("prior_binding_sha256", ""))) is None:
            raise TransactionEffectUnknown()
    elif value.get("prior_binding_sha256") != "":
        raise TransactionEffectUnknown()
    destination = value.get("destination")
    if type(destination) is not str:
        raise TransactionEffectUnknown()
    try:
        derived = compiler.binding_destination(str(value.get("candidate_sha256")))
    except Exception as exc:
        raise TransactionEffectUnknown() from exc
    if destination != derived:
        raise TransactionEffectUnknown()
    if value.get("effect") != compiler.binding_effect(destination):
        raise TransactionEffectUnknown()


def _component_receipt_payload(raw: bytes, *, code: str) -> dict[str, Any]:
    """One receipt document, parsed strictly from its EXACT raw bytes.

    The incumbent receipt readers reject a duplicate field, so the document
    derived from one raw snapshot is exactly the document those bytes carry.
    A malformed, empty or truncated receipt is a REFUSAL, never an absence:
    the two states lead to different correlations and are never conflated.
    """

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate receipt field")
            value[key] = item
        return value

    try:
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise _component_refusal(code) from exc
    if type(document) is not dict:
        raise _component_refusal(code)
    return document


def _component_receipt_metadata() -> ReceiptMetadata:
    """The metadata of receipt bytes the incumbent root reader has proved.

    ``_read_root_file`` proves the regular file, the root owner, the root
    group, mode 0444, the single link and the absent ACL of every byte it
    returns, so the metadata of those exact bytes is fixed.
    """

    return ReceiptMetadata(
        uid=0,
        gid=0,
        mode=0o444,
        nlink=1,
        is_regular=True,
        is_symlink=False,
        has_acl=False,
    )


def _component_run(
    argv: Sequence[str], *, timeout: float, stdin_bytes: bytes | None = None
) -> tuple[int, bytes]:
    """One bounded subprocess observation.

    This is the ONLY process seam of the Control component update's Git owner.
    It never offers a credential, never writes, and never interprets its own
    output.
    """

    if stdin_bytes is None:
        completed = subprocess.run(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=timeout,
        )
    else:
        completed = subprocess.run(
            list(argv),
            input=stdin_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=timeout,
        )
    return completed.returncode, completed.stdout


def _component_git_argv(checkout: Path, *args: str) -> list[str]:
    """The ONE fixed Control-principal Git owner.

    Git refuses a repository whose owner is neither the effective UID nor the
    invoking principal ("dubious ownership").  The administrative checkout is
    owned by the Control principal, so its Git facts are read AS that
    principal, exactly as the installer reads them.  No ``safe.directory`` and
    no global trust exception is ever granted, and the observation is
    credentialless: no credential, prompt or remote is ever offered.
    """

    return [
        "/usr/bin/sudo",
        "-u",
        CONTROL_USER,
        "/usr/bin/env",
        "-i",
        f"HOME={RUNTIME_ROOT / 'control' / 'home'}",
        "PATH=/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG=C.UTF-8",
        "LC_ALL=C.UTF-8",
        "GIT_CONFIG_GLOBAL=/dev/null",
        "GIT_CONFIG_NOSYSTEM=1",
        "GIT_NO_LAZY_FETCH=1",
        "GIT_NO_REPLACE_OBJECTS=1",
        "GIT_TERMINAL_PROMPT=0",
        "/usr/bin/git",
        "-C",
        os.fspath(checkout),
        *args,
    ]


def correlate_component_authority_receipt(
    receipt: Mapping[str, Any],
    *,
    target_sha: str,
    prior_control_sha256: str,
    target_control_sha256: str,
    transaction_id: str,
) -> dict[str, Any]:
    """Correlate one existing DISARMED authority receipt onto the new source.

    No authority, state, evidence, policy, scope or timestamp changes here.
    Only the attested source release, the configuration-digest correlation and
    the transaction label move; every other field of the receipt is preserved
    byte for byte and is re-proved by the incumbent validator afterwards.
    """

    value = copy.deepcopy(dict(receipt))
    preserved = {
        key: item
        for key, item in value.items()
        if key not in _COMPONENT_RECEIPT_CORRELATION_FIELDS
    }
    value.update(
        release_sha=target_sha,
        control_config_sha256=target_control_sha256,
        prior_control_config_sha256=prior_control_sha256,
        transaction_id=transaction_id,
    )
    for key, item in preserved.items():
        if value.get(key) != item:
            raise _component_refusal("control_component_authority_receipt_invalid")
    return value


def correlate_component_ceo_receipt(
    receipt: Mapping[str, Any], *, target_sha: str, transaction_id: str
) -> dict[str, Any]:
    """Correlate one existing DISARMED CEO-submit receipt onto the new source.

    Only the source identifiers and the transaction label inside the closed
    projection move.  The authority-bearing projection fields, the receipt
    state, its operation, its timestamp and its tool version are preserved
    exactly, and the incumbent receipt validator must still accept it.
    """

    value = copy.deepcopy(dict(receipt))
    projection = value.get("projection")
    if type(projection) is not dict:
        raise _component_refusal("control_component_receipt_invalid")
    preserved = {
        key: item
        for key, item in projection.items()
        if key not in _COMPONENT_CEO_PROJECTION_CORRELATION_FIELDS
    }
    updated = dict(projection)
    updated.update(
        release_sha=target_sha,
        installed_sha=target_sha,
        transaction_id=transaction_id,
    )
    for key, item in preserved.items():
        if updated.get(key) != item:
            raise _component_refusal("control_component_receipt_invalid")
    value["projection"] = updated
    value["transaction_id"] = transaction_id
    value["projection_digest"] = ceo_submit_projection_digest(updated)
    if not validate_ceo_submit_receipt_document(value, armed=False):
        raise _component_refusal("control_component_receipt_invalid")
    return value


class ProductionControlComponentHost(ProductionCeoSubmitHost):
    """Root-only Control component update inside the ONE existing owner.

    The update retargets the already-installed Control source onto an
    already-staged target release.  It reuses ``AUTONOMY_TRANSACTION``, that
    marker's manifest, the generation seal, the publication mutex and the
    completion path: there is no second lock, no second marker, no separate
    controller and no separate readback.  It never writes the MCP component
    update's own lock, never writes ``worker-codex.json`` and never acts on
    the Relay, MCP, Backup or privileged broker.

    Only the Control boundary is booted out and bootstrapped.  The Worker
    daemon is never started, stopped, enabled or disarmed: it must already be
    absent AND disabled, and its inert plist is retargeted only so that the
    installed source of the two roles stays symmetric.
    """

    def __init__(self) -> None:
        super().__init__()
        self._component_candidate: Any = None
        self._component_prior_archives: dict[str, bytes] = {}
        self._component_target_autonomy_bytes = b""
        self._component_target_ceo_bytes = b""
        self._component_target_component_bytes = b""
        self._component_plan_sha256: str | None = None
        self._component_observed_at: str | None = None
        self._component_prior_seal: str | None = None
        self._component_target_seal: str | None = None
        self._component_autonomy_metadata: ReceiptMetadata | None = None
        self._component_mode_bound: str | None = None
        self._component_control_launchd_disabled: bool | None = None
        self._component_worker_launchd_disabled: bool | None = None
        self._component_receipt_preimages_bound: dict[
            str, tuple[bool, str, bytes]
        ] = {}
        # The EXPLICIT presence of every receipt this operation may replace.
        # Presence is never inferred from the byte length of an archived
        # preimage: an empty receipt is present, and only a proven absence
        # is absent.
        self._component_prior_receipt_presence: dict[str, bool] = {}
        # The retained interpreter qualification and the ONE budget it was
        # observed under.  The same budget rechecks it before any effect.
        self._component_interpreter_observed: Any = None
        self._component_interpreter_budget: Any = None
        # An optional retained operation deadline.  When present it composes
        # with the installed peer's own local budget in exact integer
        # nanoseconds; when absent the peer's own 25 s budget is used.
        self._component_operation_deadline_monotonic_ns: int | None = None
        # The OPTIONAL Hermes host-read selection of this operation.  Every
        # member is None for a source-only update, and the historical
        # behaviour is then byte-for-byte unchanged.
        self._component_binding_metadata: dict[str, Any] | None = None
        self._component_binding_candidate_bytes: bytes | None = None
        self._component_binding_input: tuple[str, str] | None = None
        self._component_binding_prior_raw: bytes = b""
        self._component_binding_prior_selector_present: bool = False

    # -- fixed installed reads ------------------------------------------------

    @staticmethod
    def _component_root_file(path: Path, *, code: str) -> bytes:
        """Read one root-owned installed file through the owner's closed proof."""

        try:
            raw, _info = _read_root_file(path, modes=frozenset({0o644}), uid=0, gid=0)
        except HostControlError as exc:
            raise _component_refusal(code) from exc
        return raw

    def _component_control_config_bytes(self) -> bytes:
        """Read the installed Control configuration bytes exactly."""

        try:
            _value, raw = _root_json(
                CONTROL_CONFIG,
                modes=frozenset({0o440}),
                gid=grp.getgrnam(CONTROL_GROUP).gr_gid,
            )
        except (HostControlError, OSError, KeyError) as exc:
            raise _component_refusal(
                "control_component_control_config_unreadable"
            ) from exc
        return raw

    def _component_release_seal(self, sha: str, *, target: bool = False) -> str:
        """Prove one installed release is sealed at its exact commit."""

        if _SHA_RE.fullmatch(sha) is None:
            raise _component_refusal("control_component_release_seal_invalid")
        try:
            raw = _release_manifest_bytes(sha)
            manifest = json.loads(raw.decode("utf-8"))
        except (HostControlError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _component_refusal(
                "control_component_target_release_not_staged"
                if target
                else "control_component_release_seal_invalid"
            ) from exc
        tree = manifest.get("tree_sha") if type(manifest) is dict else None
        if (
            type(manifest) is not dict
            or manifest.get("commit_sha") != sha
            or type(tree) is not str
            or _SHA_RE.fullmatch(tree) is None
        ):
            raise _component_refusal("control_component_release_seal_invalid")
        try:
            release_manifest.verify(SYSTEM_ROOT / "releases" / sha, sha, tree)
        except (release_manifest.ReleaseManifestError, OSError) as exc:
            raise _component_refusal(
                "control_component_release_seal_invalid"
            ) from exc
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _component_prior_release(control_plist: Mapping[str, Any]) -> str:
        """The prior release identity the installed Control plist actually names."""

        root = control_plist.get("WorkingDirectory")
        prefix = os.fspath(SYSTEM_ROOT / "releases") + "/"
        if type(root) is not str or not root.startswith(prefix):
            raise _component_refusal("control_component_source_mismatch")
        sha = root[len(prefix):]
        if _SHA_RE.fullmatch(sha) is None:
            raise _component_refusal("control_component_source_mismatch")
        return sha

    def _component_plist_document(self, path: Path) -> dict[str, Any]:
        raw = self._component_root_file(
            path, code="control_component_plist_unreadable"
        )
        try:
            value = plistlib.loads(raw)
        except (plistlib.InvalidFileException, ValueError, TypeError) as exc:
            raise _component_refusal("control_component_plist_unreadable") from exc
        if type(value) is not dict:
            raise _component_refusal("control_component_plist_unreadable")
        return value

    @staticmethod
    def _component_plist_matches(
        document: Mapping[str, Any], *, prior_root: str, script: str
    ) -> None:
        """Prove one installed plist names the installed release and its entry."""

        arguments = document.get("ProgramArguments")
        if (
            document.get("WorkingDirectory") != prior_root
            or type(arguments) is not list
            or not arguments
            or not all(type(item) is str for item in arguments)
            or arguments[0] != os.fspath(PINNED_PYTHON)
            or os.fspath(Path(prior_root) / script) not in arguments
        ):
            raise _component_refusal("control_component_source_mismatch")

    def _component_interpreter_observation(self) -> tuple[Any, Any]:
        """Qualify the pinned interpreter through the installed-peer owner.

        The mode and owner of the pinned executable are NOT a qualification:
        they say nothing about which bytes would run.  The installed peer's
        own runtime qualification covers the executable hashes, the pinned
        version, the code signature and the whole ancestor closure, and it
        observes them under ONE budget.  That observation and that budget are
        retained here so the SAME budget can recheck the runtime immediately
        before the first effect.
        """

        from control_plane import executive_installed_peer as installed

        budget = installed._Budget(
            installed._SERVICE_BUDGET_SECONDS,
            deadline_monotonic_ns=self._component_operation_deadline_monotonic_ns,
        )
        try:
            observation = installed._verify_python_runtime(budget)
        except Exception as exc:
            raise _component_refusal(
                "control_component_interpreter_unqualified"
            ) from exc
        self._component_interpreter_observed = observation
        self._component_interpreter_budget = budget
        return observation, budget

    def _component_recheck_interpreter(self) -> None:
        """Re-prove the retained interpreter qualification before an effect.

        The retained observation is rechecked under the SAME budget it was
        observed under.  A drifted runtime is never carried forward into an
        effect, and no boolean success is ever invented.
        """

        from control_plane import executive_installed_peer as installed

        observation = self._component_interpreter_observed
        budget = self._component_interpreter_budget
        if observation is None or budget is None:
            raise TransactionEffectUnknown()
        try:
            installed._recheck_python_runtime(observation, budget)
        except Exception as exc:
            raise TransactionEffectUnknown() from exc

    def _component_label_loaded(self, label: str, *, code: str) -> bool:
        try:
            return self._loaded_observe_only(label)
        except ArmAdmissionError as exc:
            raise _component_refusal(code) from exc
        except Exception as exc:
            raise _component_refusal(code) from exc

    def _component_disabled_override(self, label: str) -> bool | None:
        """The persistent launchd override for one fixed label, or None."""

        try:
            return self._read_launchd_disabled_override(label, allow_absent=True)
        except TransactionEffectUnknown as exc:
            raise _component_refusal(
                "control_component_launchd_state_unknown"
            ) from exc

    def _component_mode(self) -> tuple[str, bool, bool]:
        """The closed input state of this operation, and its disabled preimages.

        Exactly two states exist.  LIVE: the Control service is registered
        and enabled, and the Worker is already absent AND disabled.  OFFLINE:
        both are genuinely absent AND explicitly disabled.  Every other
        combination -- unknown, mixed or mismatched -- refuses before any
        effect, and nothing is ever stopped or disarmed to fit.
        """

        control_loaded = self._component_label_loaded(
            CONTROL_LABEL, code="control_component_control_state_unknown"
        )
        control_disabled = self._component_disabled_override(CONTROL_LABEL)
        worker_loaded = self._component_label_loaded(
            WORKER_LABEL, code="control_component_worker_state_unknown"
        )
        worker_disabled = self._component_disabled_override(WORKER_LABEL)
        if worker_loaded:
            raise _component_refusal("control_component_worker_live")
        if worker_disabled is not True:
            raise _component_refusal("control_component_worker_not_disabled")
        if control_loaded:
            if control_disabled is True:
                # Registered AND explicitly disabled: neither closed mode.
                raise _component_refusal("control_component_control_state_mixed")
            return _COMPONENT_LIVE_MODE, bool(control_disabled), bool(worker_disabled)
        if control_disabled is not True:
            # Absent but NOT explicitly disabled: neither closed mode.
            raise _component_refusal("control_component_control_state_mixed")
        return _COMPONENT_OFFLINE_MODE, bool(control_disabled), bool(worker_disabled)

    def _component_git(self, checkout: Path, *args: str) -> str:
        """One bounded, credentialless Git observation of the fixed checkout.

        The observation is made by the Control principal, which owns the
        checkout.  Git refuses a repository owned by another principal, and
        this owner never grants a ``safe.directory`` or any other trust
        exception to work around that refusal.
        """

        argv = _component_git_argv(checkout, *args)
        try:
            code, out = _component_run(argv, timeout=_CONTROL_COMPONENT_GIT_TIMEOUT)
        except (OSError, subprocess.SubprocessError) as exc:
            raise _component_refusal(
                "control_component_admin_checkout_unavailable"
            ) from exc
        if code != 0 or len(out) > _CONTROL_ADMIN_CHECKOUT_MAX_BYTES:
            raise _component_refusal(
                "control_component_admin_checkout_unavailable"
            )
        try:
            return out.decode("utf-8", errors="strict").strip()
        except UnicodeDecodeError as exc:
            raise _component_refusal(
                "control_component_admin_checkout_unavailable"
            ) from exc

    def _component_admin_git_runner(
        self,
        checkout: Path,
        *args: str,
        maximum: int = _CONTROL_ADMIN_CHECKOUT_MAX_BYTES,
        input_bytes: bytes | None = None,
        deadline: float | None = None,
    ) -> bytes:
        """The installer's own Git observation, owned by the Control principal.

        The installer's administrative-checkout qualifier shells out to Git
        with its own runner.  Here that runner is the Control-principal Git
        owner, so the installer's EXACT ownership and source-closure
        qualifiers are applied to a repository Git is willing to read.
        """

        from ops.executive_os import admin_checkout as qualifier

        timeout = _CONTROL_COMPONENT_GIT_TIMEOUT
        if deadline is not None:
            timeout = min(timeout, max(deadline - time.monotonic(), 0.0))
        if timeout <= 0:
            raise qualifier.AdminCheckoutError("Git observation exceeded its bound")
        argv = _component_git_argv(checkout, *args)
        try:
            code, out = _component_run(argv, timeout=timeout, stdin_bytes=input_bytes)
        except (OSError, subprocess.SubprocessError) as exc:
            raise qualifier.AdminCheckoutError("Git observation failed") from exc
        if code != 0:
            raise qualifier.AdminCheckoutError("Git observation failed")
        if len(out) > maximum:
            raise qualifier.AdminCheckoutError("Git observation exceeded its bound")
        return out

    def _component_admin_closure(self, checkout: Path, target_sha: str) -> None:
        """Prove the local source closure of the administrative checkout.

        The installer's own qualifiers decide this: no partial-clone
        configuration, no promisor remote, no remote at all, and every object
        reachable from the target commit present locally.  They are applied
        here with the Control-principal Git owner as their runner.
        """

        from ops.executive_os import admin_checkout as qualifier

        original = qualifier._run_git
        qualifier._run_git = self._component_admin_git_runner
        try:
            qualifier._require_direct_object_store(checkout / ".git")
            qualifier._require_no_partial_config(checkout)
            qualifier._require_complete_closure(checkout, target_sha)
        except Exception as exc:
            raise _component_refusal(
                "control_component_admin_checkout_unavailable"
            ) from exc
        finally:
            qualifier._run_git = original

    def _component_admin_checkout(self, target_sha: str) -> str:
        """Prove the fixed administrative checkout holds the exact target source.

        The checkout is installer-owned and credentialless: it is a real
        directory owned by the control principal, its Git directory is a real
        directory, its HEAD is the exact target commit, it carries no remote
        and its reachable object closure is complete.  This is a read-only
        observation; the installer owns its preparation and any repair of it.
        """

        checkout = _CONTROL_ADMIN_CHECKOUT_ROOT / target_sha
        try:
            info = checkout.lstat()
            git_info = (checkout / ".git").lstat()
            control_uid = pwd.getpwnam(CONTROL_USER).pw_uid
        except (OSError, KeyError) as exc:
            raise _component_refusal(
                "control_component_admin_checkout_unavailable"
            ) from exc
        if (
            not stat.S_ISDIR(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or not stat.S_ISDIR(git_info.st_mode)
            or stat.S_ISLNK(git_info.st_mode)
            or info.st_uid != control_uid
            or stat.S_IMODE(info.st_mode) & 0o022
        ):
            raise _component_refusal(
                "control_component_admin_checkout_unavailable"
            )
        head = self._component_git(checkout, "rev-parse", "--verify", "HEAD^{commit}")
        if head != target_sha:
            raise _component_refusal(
                "control_component_admin_checkout_unavailable"
            )
        if self._component_git(checkout, "remote"):
            raise _component_refusal(
                "control_component_admin_checkout_unavailable"
            )
        self._component_admin_closure(checkout, target_sha)
        return head

    def _component_autonomy_receipt(
        self,
        prior_sha: str,
        configs: ConfigEvidence,
        snapshot: tuple[bool, str, bytes],
    ) -> tuple[dict[str, Any], ReceiptMetadata]:
        """Validate the EXISTING disarmed authority receipt.

        The bounded first path requires existing DISARMED authority: an armed
        receipt cannot survive a source change without an authority migration,
        and this operation never migrates or refreshes authority.

        The validated document is derived from the SAME raw snapshot that is
        archived and compared against, so the semantic validation, the
        archived preimage, the presence flag and the correlation all name one
        set of bytes.  A receipt that moves between the validation and the
        capture can therefore never become an unjoined archive: the
        compare-and-swap refuses the moved receipt instead.
        """

        present, _digest, raw = snapshot
        if not present:
            raise _component_refusal(
                "control_component_authority_receipt_invalid"
            )
        payload = _component_receipt_payload(
            raw, code="control_component_authority_receipt_invalid"
        )
        metadata = _component_receipt_metadata()
        if payload.get("state") != "DISARMED":
            raise _component_refusal("control_component_authority_receipt_armed")
        readiness = payload.get("provider_readiness_receipt_sha256")
        if type(readiness) is not str:
            raise _component_refusal(
                "control_component_authority_receipt_invalid"
            )
        try:
            validate_receipt_document(
                payload,
                metadata=metadata,
                expected=AutonomyExpectation(
                    release_sha=prior_sha,
                    control_config_sha256=configs.control_sha256,
                    worker_config_sha256=configs.worker_sha256,
                    provider_readiness_receipt_sha256=readiness,
                    capability_policy_digest=CAPABILITY_POLICY_DIGEST,
                    execution_profile_digest=EXECUTION_PROFILE_DIGEST,
                    native_helper_grant_digest=NATIVE_HELPER_GRANT_DIGEST,
                    security_config_digest=SECURITY_CONFIG_DIGEST,
                ),
                now=None,
                require_current=False,
            )
        except (AutonomyRefusal, TypeError, ValueError) as exc:
            raise _component_refusal(
                "control_component_authority_receipt_invalid"
            ) from exc
        return dict(payload), metadata

    def _component_ceo_receipt(
        self, snapshot: tuple[bool, str, bytes]
    ) -> dict[str, Any] | None:
        """The EXACT bytes of the EXISTING disarmed CEO-submit receipt.

        ``None`` means the receipt is proven ABSENT.  A receipt that is
        present but malformed, empty, unreadable or misqualified is a
        REFUSAL: it is never silently treated as an absent receipt, because
        the absent receipt and the unreadable one lead to different
        correlations.
        """

        present, _digest, raw = snapshot
        if not present:
            return None
        receipt = _component_receipt_payload(
            raw, code="control_component_receipt_invalid"
        )
        if receipt.get("state") != "CEO_SUBMIT_DISARMED":
            raise _component_refusal("control_component_authority_receipt_armed")
        if not validate_ceo_submit_receipt_document(receipt, armed=False):
            raise _component_refusal("control_component_receipt_invalid")
        return dict(receipt)

    # -- the observation ------------------------------------------------------

    def _component_receipt_bytes(self, path: Path) -> tuple[bool, bytes]:
        """The EXACT prior bytes of one receipt this operation may replace.

        The read is the incumbent's own root-file proof: a regular file,
        root owned, root grouped, mode 0444, one link, no ACL and no
        symlink.  Its ABSENCE is proven by an explicit FileNotFoundError and
        is never inferred from the byte length, so an empty receipt stays
        present and distinct from a missing one.

        The digest is always of the raw bytes that were on disk, never of a
        re-encoded parse of them: a receipt whose serialisation differs from
        the canonical one is still the receipt that is being replaced, and
        only its exact bytes may be restored.
        """

        try:
            raw, _info = _read_root_file(
                path, modes=frozenset({0o444}), uid=0, gid=0
            )
        except FileNotFoundError:
            return False, b""
        except HostControlError as exc:
            # The incumbent reader reports an absent path through the
            # FileNotFoundError it raised; anything else is an unreadable or
            # an unowned receipt, which is a refusal and never an absence.
            if isinstance(exc.__cause__, FileNotFoundError):
                return False, b""
            raise _component_refusal("control_component_receipt_invalid") from exc
        return True, raw

    def _component_receipt_preimages(self) -> dict[str, tuple[bool, str, bytes]]:
        """The exact prior state of every receipt this operation may replace."""

        preimages: dict[str, tuple[bool, str, bytes]] = {}
        for name, path in (
            ("authority_receipt", AUTONOMY_RECEIPT),
            ("ceo_submit_receipt", CEO_SUBMIT_RECEIPT),
            ("component_receipt", CONTROL_COMPONENT_RECEIPT),
        ):
            present, raw = self._component_receipt_bytes(path)
            preimages[name] = (present, sha256_bytes(raw), raw)
        return preimages

    # -- the ONE Hermes host-read selection ----------------------------------

    @staticmethod
    def _component_binding_bytes(path: Path) -> tuple[bool, bytes]:
        """The EXACT bytes of one published binding artifact.

        The read is the incumbent's own root-file proof: a regular file,
        root owned, root grouped, mode 0444, one link, no ACL and no
        symlink.  Its ABSENCE is proven by an explicit FileNotFoundError and
        is never inferred from the byte length, so an empty artifact stays
        present and distinct from a missing one.
        """

        try:
            raw, _info = _read_root_file(
                path,
                modes=frozenset({0o444}),
                uid=_CONFIG_ROOT_UID,
                gid=_CONFIG_ROOT_GID,
            )
        except FileNotFoundError:
            return False, b""
        except HostControlError as exc:
            if isinstance(exc.__cause__, FileNotFoundError):
                return False, b""
            raise _component_refusal(
                "control_component_hermes_read_binding_conflict"
            ) from exc
        return True, raw

    def _component_binding_selection(
        self, hermes_read: tuple[str, str], control: Mapping[str, Any], *,
        input_kind: str | None = None,
    ) -> dict[str, Any]:
        """Qualify ONE Hermes host-read selection and compose its candidate.

        The input is read through the incumbent's own bounded, no-follow,
        identity-joined pinned read and is bound to the EXACT digest the
        caller supplied.  The read member is qualified by the incumbent's own
        validator and the prior selected binding -- when the Control
        configuration carries BOTH selector coordinates -- by the incumbent
        v1/v2/v3 parser.  Nothing here writes, exports or transmits a
        credential, an endpoint or a key.
        """

        from control_plane import executive_fabric_composition as composition
        from ops.executive_os import control_component_update as compiler

        input_path, input_sha256 = hermes_read
        try:
            input_raw, _identity = composition._read_pinned(
                composition._absolute_path(input_path), input_sha256
            )
            input_document = composition._document(input_raw)
            if type(input_document) is not dict:
                raise composition.FabricCompositionError(
                    "Hermes host observation differs from its closed schema"
                )
            # The EXISTING validator qualifies the read member: its schema,
            # its host reference, its source pins and its TLS transport.
            # There is no second validator here.
            if input_kind is None:
                composition.HermesHostObservationBinding.from_document(input_document)
            elif input_kind != "native_conversation":
                raise composition.FabricCompositionError("Unknown component selection kind")
        except (composition.FabricCompositionError, OSError, ValueError) as exc:
            raise _component_refusal(
                "control_component_hermes_read_input_invalid"
            ) from exc

        selector_present = (
            "fabric_bindings_path" in control or "fabric_bindings_sha256" in control
        )
        prior_bindings: tuple[Mapping[str, Any], ...] = ()
        prior_transports: tuple[Mapping[str, Any], ...] = ()
        prior_secretary_conversation = None
        prior_meta_conversation = None
        prior_native_conversation = None
        prior_document = {}
        prior_parts = None
        prior_raw = b""
        prior_binding_sha256 = ""
        if selector_present:
            if (
                "fabric_bindings_path" not in control
                or "fabric_bindings_sha256" not in control
            ):
                # A PARTIAL selector is a refusal, never an absence.
                raise _component_refusal(
                    "control_component_hermes_read_binding_invalid"
                )
            prior_path = control["fabric_bindings_path"]
            prior_digest = control["fabric_bindings_sha256"]
            if (
                type(prior_path) is not str
                or type(prior_digest) is not str
                or re.fullmatch(r"[0-9a-f]{64}", prior_digest) is None
            ):
                raise _component_refusal(
                    "control_component_hermes_read_binding_invalid"
                )
            try:
                prior_raw, _prior_identity = composition._read_pinned(
                    composition._absolute_path(prior_path), prior_digest
                )
                # The incumbent closed parser qualifies the complete prior binding.
                prior_parts = composition._composition_parts(prior_raw)
                prior_document = composition._document(prior_raw)
            except (composition.FabricCompositionError, OSError, ValueError) as exc:
                raise _component_refusal(
                    "control_component_hermes_read_binding_invalid"
                ) from exc
            prior_bindings = tuple(prior_document.get("bindings") or ())
            prior_transports = tuple(prior_document.get("remote_transports") or ())
            prior_secretary_conversation = prior_document.get("hermes_secretary_conversation")
            prior_meta_conversation = prior_document.get("hermes_meta_conversation")
            prior_native_conversation = prior_document.get("native_conversation")
            prior_binding_sha256 = sha256_bytes(prior_raw)
            if "canonical_paid_fabric" in control and (
                prior_bindings or prior_transports
            ):
                # The installed paid source cannot replace or mix an
                # EXECUTION owner.  The existing exclusion is preserved and
                # rows are never deleted to satisfy it.
                raise _component_refusal(
                    "control_component_hermes_read_binding_conflict"
                )

        if input_kind == "native_conversation":
            try:
                if (not selector_present or prior_parts is None
                        or prior_document.get("schema_version") not in (
                            composition.CONVERSATION_CONFIG_SCHEMA_VERSION,
                            composition.NATIVE_CONFIG_SCHEMA_VERSION)
                        or prior_secretary_conversation is None or prior_meta_conversation is None
                        or prior_native_conversation is not None
                        and prior_native_conversation != input_document):
                    raise composition.FabricCompositionError("Original native selection cannot be replaced")
                # These are expected facts, not a live Worker/account admission.
                # The original Runtime binding still joins its own registry.
                composition.NativeOperatorHostSelection.from_document(input_document, prior_parts[2])
                prior_native_conversation = input_document
                input_document = prior_document["hermes_role_metadata_read"]
            except (composition.FabricCompositionError, KeyError, ValueError) as exc:
                raise _component_refusal("control_component_native_conversation_binding_conflict") from exc

        composed = compiler.compose_binding_candidate(
            input_document=input_document,
            prior_bindings=prior_bindings,
            prior_remote_transports=prior_transports,
            prior_secretary_conversation=prior_secretary_conversation,
            prior_meta_conversation=prior_meta_conversation,
            prior_native_conversation=prior_native_conversation,
        )
        try:
            # Use the actual consumer's byte ceiling before the transaction
            # can be claimed. Pretty-printing and the added read member can
            # expand an otherwise valid prior binding beyond that ceiling.
            if not 0 < len(composed) <= composition.MAX_CONFIG_BYTES:
                raise composition.FabricCompositionError(
                    "Composed Fabric binding exceeds the consumer byte limit"
                )
            # The composed document is proved loadable by the incumbent
            # parser: the Control's own loader will read exactly these bytes.
            composition._composition(composed)
        except composition.FabricCompositionError as exc:
            raise _component_refusal(
                "control_component_hermes_read_binding_conflict"
            ) from exc
        candidate_sha256 = sha256_bytes(composed)
        destination = compiler.binding_destination(candidate_sha256)
        if os.fspath(CONFIG_ROOT) != compiler.CONFIG_ROOT_PATH:
            raise _component_refusal(
                "control_component_hermes_read_binding_conflict"
            )
        present, existing = self._component_binding_bytes(Path(destination))
        if present and existing != composed:
            # The derived destination exists with DIFFERENT bytes.  It is
            # never overwritten and never adopted.
            raise _component_refusal(
                "control_component_hermes_read_binding_conflict"
            )
        return {
            "input_document": input_document,
            "input_kind": input_kind,
            "input_raw": input_raw,
            "input_sha256": input_sha256,
            "prior_bindings": prior_bindings,
            "prior_remote_transports": prior_transports,
            "prior_secretary_conversation": prior_secretary_conversation,
            "prior_meta_conversation": prior_meta_conversation,
            "prior_native_conversation": prior_native_conversation,
            "prior_raw": prior_raw,
            "prior_binding_sha256": prior_binding_sha256,
            "prior_selector_present": selector_present,
            "destination_present": present,
            "candidate_bytes": composed,
            "candidate_sha256": candidate_sha256,
            "destination": destination,
        }

    def observe_control_component_update(
        self, *, target_sha: str, hermes_read: tuple[str, str] | None = None,
        native_conversation: tuple[str, str] | None = None,
    ) -> dict[str, Any]:
        """Read-only observation: the plan and the exact candidate it binds.

        Every precondition is proved here, before any marker, installed file,
        receipt or launchd effect exists.  A false precondition is a typed
        refusal with zero cutover.

        The OPTIONAL Hermes host-read selection is qualified here as well:
        the input, the prior selected binding and the composed candidate are
        all proved while the operation is still read-only.
        """

        from ops.executive_os import control_component_update as compiler

        if _SHA_RE.fullmatch(target_sha) is None:
            raise _component_refusal("control_component_release_seal_invalid")

        control_plist_bytes = self._component_root_file(
            CONTROL_PLIST, code="control_component_plist_unreadable"
        )
        worker_plist_bytes = self._component_root_file(
            WORKER_PLIST, code="control_component_plist_unreadable"
        )
        control_plist_document = self._component_plist_document(CONTROL_PLIST)
        worker_plist_document = self._component_plist_document(WORKER_PLIST)
        prior_sha = self._component_prior_release(control_plist_document)
        if prior_sha == target_sha:
            raise _component_refusal("control_component_source_mismatch")
        prior_release_root = os.fspath(SYSTEM_ROOT / "releases" / prior_sha)
        target_release_root = os.fspath(SYSTEM_ROOT / "releases" / target_sha)

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
            raise _component_refusal(
                "control_component_control_config_unreadable"
            ) from exc
        configs = ConfigEvidence(
            control_sha256=control_digest,
            worker_sha256=worker_digest,
            control=control,
            worker=worker,
            control_bytes=control_raw,
            worker_bytes=worker_raw,
        )
        if control.get("proof_base_sha") != prior_sha:
            raise _component_refusal("control_component_source_mismatch")

        prior_seal = self._component_release_seal(prior_sha)
        target_seal = self._component_release_seal(target_sha, target=True)
        admin_checkout_commit = self._component_admin_checkout(target_sha)

        self._component_plist_matches(
            control_plist_document,
            prior_root=prior_release_root,
            script="scripts/executive_os_phase1c_control_wrapper.py",
        )
        self._component_plist_matches(
            worker_plist_document,
            prior_root=prior_release_root,
            script="scripts/executive_os_phase1c_worker.py",
        )

        # The incumbent authority receipt must exist and be DISARMED, and the
        # incumbent arming flags must all be false.  ``ceo_ingress_app_armed``
        # is transport admission, never CEO-submit authority, so it is not
        # consulted here.
        if (
            control.get("ceo_submit_armed") is not False
            or control.get("coo_autonomy_armed") is not False
            or control.get("coo_operator_harness_armed") is not False
            or worker.get("operator_harness_armed") is not False
        ):
            raise _component_refusal("control_component_authority_receipt_armed")
        # Every receipt this operation may replace is bound by ONE raw
        # snapshot: its presence, its exact bytes, its semantic validation
        # and the later correlation all name the same bytes.  The snapshot is
        # taken BEFORE the validation, so a receipt that moves afterwards is
        # an unbound later receipt that the compare-and-swap refuses; it can
        # never become an unjoined archive.
        receipt_preimages = self._component_receipt_preimages()
        self._component_receipt_preimages_bound = receipt_preimages
        self._component_prior_receipt_presence = {
            name: bool(value[0]) for name, value in receipt_preimages.items()
        }
        autonomy_receipt, autonomy_metadata = self._component_autonomy_receipt(
            prior_sha, configs, receipt_preimages["authority_receipt"]
        )
        ceo_receipt = self._component_ceo_receipt(
            receipt_preimages["ceo_submit_receipt"]
        )

        # No incumbent global transaction may exist.
        try:
            self.require_transaction_absent()
        except Exception as exc:
            raise _component_refusal(
                "control_component_transaction_occupied"
            ) from exc

        # The existing owner must be quiescent: no live runtime attempt.
        try:
            self.require_runtime_quiescent(configs)
        except Exception as exc:
            raise _component_refusal(
                "control_component_owner_not_quiescent"
            ) from exc

        # The closed input state of this operation: the Control boundary is
        # either live and enabled, or genuinely absent and explicitly
        # disabled; the Worker must already be absent AND disabled.  A live
        # or unknown Worker is a pre-effect refusal: it is never stopped or
        # disarmed to fit.  A mixed or mismatched Control boundary matches
        # neither closed mode and refuses here too.
        mode, control_disabled, worker_disabled = self._component_mode()

        try:
            selection = None
            binding = None
            if hermes_read is not None and native_conversation is not None:
                raise _component_refusal("control_component_selection_conflict")
            if hermes_read is not None or native_conversation is not None:
                binding = (self._component_binding_selection(
                    native_conversation, control, input_kind="native_conversation")
                    if native_conversation is not None
                    else self._component_binding_selection(hermes_read, control))
                selection = compiler.BindingSelectionInputs(
                    input_document=binding["input_document"],
                    input_kind=binding.get("input_kind"),
                    prior_bindings=binding["prior_bindings"],
                    prior_remote_transports=binding["prior_remote_transports"],
                    prior_secretary_conversation=binding["prior_secretary_conversation"],
                    prior_meta_conversation=binding["prior_meta_conversation"],
                    prior_native_conversation=binding["prior_native_conversation"],
                    input_sha256=binding["input_sha256"],
                    prior_binding_sha256=binding["prior_binding_sha256"],
                    prior_selector_present=binding["prior_selector_present"],
                    destination_present=binding["destination_present"],
                )
            candidate = compiler.compile_candidate(
                control_raw,
                control_plist_bytes,
                worker_plist_bytes,
                target_sha=target_sha,
                prior_sha=prior_sha,
                worker_config_sha256=worker_digest,
                prior_release_root=prior_release_root,
                target_release_root=target_release_root,
                selection=selection,
            )
        except compiler.ComponentError as exc:
            raise _component_refusal(
                "control_component_schema_incompatible"
            ) from exc

        # The pinned interpreter is qualified by the installed peer's own
        # runtime owner.  Its observation and its budget are retained so the
        # SAME budget can recheck the runtime before the first effect.  The
        # observation is the LAST qualification of this read-only pass, so the
        # budget it opens is spent on the recheck and not on the release and
        # checkout proofs that precede it.
        self._component_interpreter_observation()

        preconditions = {key: True for key in compiler.preconditions_for_mode(mode)}
        document = compiler.plan_document(
            candidate,
            mode=mode,
            preconditions=preconditions,
            prior_release_manifest_sha256=prior_seal,
            target_release_manifest_sha256=target_seal,
            admin_checkout_commit=admin_checkout_commit,
            receipts={
                name: compiler.ReceiptPreimage(
                    path=compiler_path,
                    present=present,
                    sha256=digest,
                )
                for name, (present, digest, _raw), compiler_path in (
                    (
                        "authority_receipt",
                        receipt_preimages["authority_receipt"],
                        compiler.AUTHORITY_RECEIPT_PATH,
                    ),
                    (
                        "ceo_submit_receipt",
                        receipt_preimages["ceo_submit_receipt"],
                        compiler.CEO_SUBMIT_RECEIPT_PATH,
                    ),
                    (
                        "component_receipt",
                        receipt_preimages["component_receipt"],
                        compiler.COMPONENT_RECEIPT_PATH,
                    ),
                )
            },
            launchd_disabled={
                "control": control_disabled,
                "worker": worker_disabled,
            },
        )
        return {
            "plan": document,
            "candidate": candidate,
            "binding": binding,
            "prior_configs": configs,
            "candidate_configs": CandidateConfigs(
                control=json.loads(candidate.control_config_after.decode("utf-8")),
                worker=worker,
                control_bytes=candidate.control_config_after,
                worker_bytes=worker_raw,
                control_sha256=candidate.control_config_after_sha256,
                worker_sha256=worker_digest,
            ),
            "autonomy_receipt": autonomy_receipt,
            "autonomy_receipt_metadata": autonomy_metadata,
            "ceo_receipt": ceo_receipt,
            "mode": mode,
            "control_launchd_disabled": control_disabled,
            "worker_launchd_disabled": worker_disabled,
            "receipt_preimages": receipt_preimages,
            "prior_release_root": prior_release_root,
            "target_release_root": target_release_root,
            "prior_seal": prior_seal,
            "target_seal": target_seal,
            "prior_control_plist": control_plist_bytes,
            "prior_worker_plist": worker_plist_bytes,
        }

    # -- the transaction ------------------------------------------------------

    def new_transaction_id(self) -> str:
        # A fresh update may never lock/adopt a marker that appeared after its
        # absence preflight.
        return f"autonomy-{secrets.token_hex(6)}"

    def _manifest_document(
        self, transaction: TransactionContext, phase: str, *, operation: str
    ) -> dict[str, Any]:
        value = super()._manifest_document(transaction, phase, operation=operation)
        if operation != CONTROL_COMPONENT_UPDATE or self._component_candidate is None:
            raise TransactionEffectUnknown()
        candidate = self._component_candidate
        archives = self._component_prior_archives
        value.update(
            component_plan_sha256=str(
                self._component_plan_sha256 or ""
            ),
            component_prior_release_seal_sha256=str(
                self._component_prior_seal or ""
            ),
            component_target_release_seal_sha256=str(
                self._component_target_seal or ""
            ),
            component_observed_at=str(self._component_observed_at or ""),
            component_prior_control_plist_sha256=candidate.control_plist_before_sha256,
            component_target_control_plist_sha256=candidate.control_plist_after_sha256,
            component_prior_worker_plist_sha256=candidate.worker_plist_before_sha256,
            component_target_worker_plist_sha256=candidate.worker_plist_after_sha256,
            component_prior_autonomy_receipt_present=bool(
                self._component_prior_receipt_presence.get("authority_receipt")
            ),
            component_prior_autonomy_receipt_sha256=sha256_bytes(
                archives.get("prior-component-autonomy-receipt.json", b"")
            ),
            component_target_autonomy_receipt_sha256=sha256_bytes(
                self._component_target_autonomy_bytes
            ),
            component_prior_ceo_receipt_present=bool(
                self._component_prior_receipt_presence.get("ceo_submit_receipt")
            ),
            component_prior_ceo_receipt_sha256=sha256_bytes(
                archives.get("prior-component-ceo-submit-receipt.json", b"")
            ),
            component_target_ceo_receipt_sha256=sha256_bytes(
                self._component_target_ceo_bytes
            ),
            component_prior_component_receipt_present=bool(
                self._component_prior_receipt_presence.get("component_receipt")
            ),
            component_prior_component_receipt_sha256=sha256_bytes(
                archives.get("prior-component-receipt.json", b"")
            ),
            component_target_component_receipt_sha256=sha256_bytes(
                self._component_target_component_bytes
            ),
            component_mode=str(self._component_mode_bound or ""),
            component_prior_control_launchd_disabled=bool(
                self._component_control_launchd_disabled
            ),
            component_prior_worker_launchd_disabled=bool(
                self._component_worker_launchd_disabled
            ),
        )
        if self._component_binding_metadata is not None:
            # The OPTIONAL structured selection member.  It is absent for a
            # source-only update, and the legacy marker format is preserved
            # exactly in that case.
            value["component_binding"] = dict(self._component_binding_metadata)
        value["phase"] = phase
        return value

    def _seal_generation(
        self, generation: Path, transaction: TransactionContext, *, operation: str
    ) -> None:
        if (
            operation != CONTROL_COMPONENT_UPDATE
            or self._component_candidate is None
            or not self._component_prior_archives
        ):
            raise TransactionEffectUnknown()
        # The plain global-owner seal carries both unchanged config preimages.
        ProductionTransactionHost._seal_generation(
            self, generation, transaction, operation=operation
        )
        archives = _component_archive_names(
            {"component_binding": self._component_binding_metadata}
            if self._component_binding_metadata is not None else {})
        for name in archives:
            _atomic_file(
                generation / name,
                self._component_prior_archives.get(name, b""),
                mode=0o400,
                uid=0,
                gid=0,
                replace=False,
            )
        manifest = self._manifest_document(transaction, "LOCKED", operation=operation)
        _atomic_file(
            generation / _TRANSACTION_MANIFEST_NAME,
            _encoded_json(manifest),
            mode=0o400,
            uid=0,
            gid=0,
            replace=True,
        )
        _fsync_directory(generation)

    def _component_archives(self, manifest: Mapping[str, Any]) -> dict[str, bytes]:
        """Read back the sealed preimages of this operation, exactly."""

        archives: dict[str, bytes] = {}
        for name in ("prior-control.json", "prior-worker.json"):
            raw, _info = _read_root_file(
                AUTONOMY_TRANSACTION / name, modes=frozenset({0o400}), uid=0, gid=0
            )
            archives[name] = raw
        for name in _component_archive_names(manifest):
            raw, _info = _read_root_file(
                AUTONOMY_TRANSACTION / name, modes=frozenset({0o400}), uid=0, gid=0
            )
            archives[name] = raw
        return archives

    def _recheck_component_bound(self, transaction: TransactionContext) -> None:
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
            manifest.get("operation") != CONTROL_COMPONENT_UPDATE
            or manifest.get("transaction_id") != transaction.transaction_id
            or manifest.get("expected_sha") != transaction.expected_sha
            or not _COMPONENT_MANIFEST_FIELDS <= set(manifest)
        ):
            raise TransactionEffectUnknown()

    def _recheck_component_preimages(
        self, transaction: TransactionContext, observation: Mapping[str, Any]
    ) -> None:
        """Every sealed preimage must still be exactly the sealed preimage."""

        self._recheck_component_bound(transaction)
        manifest = self._manifest()
        expected = self._manifest_document(
            transaction, "LOCKED", operation=CONTROL_COMPONENT_UPDATE
        )
        if manifest != expected:
            raise TransactionEffectUnknown()
        current = self._configs()
        if (
            current[2] != transaction.prior_configs.control_sha256
            or current[3] != transaction.prior_configs.worker_sha256
        ):
            raise TransactionEffectUnknown()
        for path, field in (
            (CONTROL_PLIST, "component_prior_control_plist_sha256"),
            (WORKER_PLIST, "component_prior_worker_plist_sha256"),
        ):
            raw = self._component_root_file(
                path, code="control_component_plist_unreadable"
            )
            if sha256_bytes(raw) != manifest[field]:
                raise TransactionEffectUnknown()
        # Every receipt this operation may replace must still be exactly the
        # sealed prior bytes, and the launchd preimages must still be the
        # observed ones.  A receipt that moved after the seal is an unbound
        # later receipt: it is never overwritten.
        for name, path in (
            ("authority_receipt", AUTONOMY_RECEIPT),
            ("ceo_submit_receipt", CEO_SUBMIT_RECEIPT),
            ("component_receipt", CONTROL_COMPONENT_RECEIPT),
        ):
            present, raw = self._component_receipt_bytes(path)
            field = {
                "authority_receipt": "component_prior_autonomy_receipt_sha256",
                "ceo_submit_receipt": "component_prior_ceo_receipt_sha256",
                "component_receipt": "component_prior_component_receipt_sha256",
            }[name]
            presence_field = {
                "authority_receipt": "component_prior_autonomy_receipt_present",
                "ceo_submit_receipt": "component_prior_ceo_receipt_present",
                "component_receipt": "component_prior_component_receipt_present",
            }[name]
            if (
                present is not manifest[presence_field]
                or sha256_bytes(raw) != manifest[field]
            ):
                raise TransactionEffectUnknown()
        for label, field in (
            (CONTROL_LABEL, "component_prior_control_launchd_disabled"),
            (WORKER_LABEL, "component_prior_worker_launchd_disabled"),
        ):
            # An absent launchd row means the launchd default, which is the
            # same state as an explicit "enabled" row.
            if bool(self._component_disabled_override(label)) is not manifest[field]:
                raise TransactionEffectUnknown()
        # The OPTIONAL selection preimages are rechecked too: the input, the
        # prior selected binding and the derived destination.
        member = manifest.get("component_binding")
        if type(member) is dict:
            self._recheck_component_binding_preimages(member)
        # The target source is re-proved under the claimed transaction.
        self._recheck_component_target_source(transaction)

    def _recheck_component_binding_preimages(self, member: Mapping[str, Any]) -> None:
        """Every sealed selection preimage must still be exactly the sealed one.

        The qualified input, the prior selected binding and the derived
        destination are all compared against the SEALED bytes.  A binding
        that moved after the seal is never adopted and a destination that
        appeared after the approved observation is never overwritten.
        """

        from control_plane import executive_fabric_composition as composition

        payload = self._component_binding_candidate_bytes
        if payload is None:
            raise TransactionEffectUnknown()
        if sha256_bytes(payload) != member["candidate_sha256"]:
            raise TransactionEffectUnknown()
        # The exact qualified input must still be the sealed input.
        selector = self._component_binding_input
        if selector is None:
            raise TransactionEffectUnknown()
        input_path, input_sha256 = selector
        try:
            input_raw, _identity = composition._read_pinned(
                composition._absolute_path(input_path), input_sha256
            )
        except (composition.FabricCompositionError, OSError, ValueError) as exc:
            raise TransactionEffectUnknown() from exc
        if sha256_bytes(input_raw) != member["input_sha256"]:
            raise TransactionEffectUnknown()
        # The prior selected binding must still be exactly the sealed bytes.
        if bool(member["prior_selector_present"]):
            try:
                prior_raw, _prior_identity = composition._read_pinned(
                    composition._absolute_path(self._component_binding_prior_path()),
                    str(member["prior_binding_sha256"]),
                )
            except (composition.FabricCompositionError, OSError, ValueError) as exc:
                raise TransactionEffectUnknown() from exc
            if sha256_bytes(prior_raw) != member["prior_binding_sha256"]:
                raise TransactionEffectUnknown()
        # The derived destination is either still absent, or still the exact
        # sealed identity and bytes.
        present, raw = self._component_binding_bytes(
            Path(str(member["destination"]))
        )
        if bool(member["destination_present"]):
            if not present or raw != payload:
                raise TransactionEffectUnknown()
        elif present:
            # The destination appeared after the approved observation: it is
            # never overwritten and never adopted.
            raise TransactionEffectUnknown()

    def _component_binding_prior_path(self) -> str:
        """The path of the prior selected binding, as the Control names it."""

        try:
            _control, _worker, _cd, _wd, _cr, _wr = self._configs()
        except (HostControlError, KeyError, OSError) as exc:
            raise TransactionEffectUnknown() from exc
        path = _control.get("fabric_bindings_path")
        if type(path) is not str:
            raise TransactionEffectUnknown()
        return path

    def _recheck_component_target_source(self, transaction: TransactionContext) -> None:
        """The target source must still be sealed and still present.

        The recheck happens under the claimed transaction, before any effect:
        the sealed target release and the administrative checkout that backs
        it are re-proved against the values the marker bound.
        """

        self._recheck_component_bound(transaction)
        manifest = self._manifest()
        target_seal = self._component_release_seal(
            str(transaction.expected_sha), target=True
        )
        if target_seal != manifest["component_target_release_seal_sha256"]:
            raise TransactionEffectUnknown()
        if self._component_admin_checkout(str(transaction.expected_sha)) != (
            str(transaction.expected_sha)
        ):
            raise TransactionEffectUnknown()

    def _publish_component_binding_artifact(
        self, destination: Path, payload: bytes
    ) -> None:
        """Publish ONE immutable binding artifact under the qualified root.

        The publication is a no-replace rename of a privately staged file
        into the qualified configuration root, taken under the current
        configuration publication mutex.  It never replaces an existing
        name, never copies, never deletes and never emulates the exclusive
        rename: an occupied destination is a refusal, not a repair.

        The owner is the incumbent ``capacity_host_artifacts._rename_exclusive``
        and the ancestors are the incumbent qualified chain, so the artifact
        is published exactly the way every other canonical installed file is
        published.
        """

        from control_plane import executive_fabric_composition as composition
        from ops.executive_os.capacity_host_artifacts import (
            CapacityHostArtifactError,
            _rename_exclusive,
        )

        parent = -1
        stage = ""
        stage_ino: int | None = None
        created = False
        renamed = False
        try:
            self._config_root_safe()
            try:
                composition._trusted_parent_chain(CONFIG_ROOT)
            except composition.FabricCompositionError as exc:
                raise TransactionEffectUnknown() from exc
            parent = os.open(
                CONFIG_ROOT,
                os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
            )
            try:
                fcntl.flock(parent, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (BlockingIOError, OSError) as exc:
                # The current configuration publication mutex is occupied.
                raise TransactionEffectUnknown() from exc
            held = os.fstat(parent)
            visible = CONFIG_ROOT.lstat()
            if (
                (held.st_dev, held.st_ino) != (visible.st_dev, visible.st_ino)
                or held.st_uid != _CONFIG_ROOT_UID
                or held.st_gid != _CONFIG_ROOT_GID
                or not stat.S_ISDIR(held.st_mode)
            ):
                raise TransactionEffectUnknown()
            name = os.fspath(destination)
            if os.path.dirname(name) != os.fspath(CONFIG_ROOT):
                raise TransactionEffectUnknown()
            base = os.path.basename(name)
            stage = f".{base}.{os.getpid()}.{secrets.token_hex(8)}.stage"
            descriptor = os.open(
                stage,
                os.O_RDWR
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=parent,
            )
            created = True
            try:
                pending = memoryview(payload)
                while pending:
                    count = os.write(descriptor, pending)
                    if count <= 0:
                        raise OSError("short binding artifact write")
                    pending = pending[count:]
                os.fchown(descriptor, _CONFIG_ROOT_UID, _CONFIG_ROOT_GID)
                os.fchmod(descriptor, 0o444)
                os.fsync(descriptor)
                info = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != _CONFIG_ROOT_UID
                    or info.st_gid != _CONFIG_ROOT_GID
                    or stat.S_IMODE(info.st_mode) != 0o444
                    or info.st_nlink != 1
                ):
                    raise TransactionEffectUnknown()
                stage_ino = info.st_ino
                # The staged bytes are observed on the SAME descriptor.
                os.lseek(descriptor, 0, os.SEEK_SET)
                observed = os.read(descriptor, len(payload) + 1)
                if observed != payload:
                    raise TransactionEffectUnknown()
            finally:
                os.close(descriptor)
            # The ONE exclusive, no-replace rename.  A destination that
            # appeared after the approved observation refuses here: it is
            # never overwritten and never adopted.
            _rename_exclusive(parent, stage, parent, base)
            renamed = True
            os.fsync(parent)
        except CapacityHostArtifactError as exc:
            raise TransactionEffectUnknown() from exc
        except TransactionEffectUnknown:
            raise
        except Exception as exc:
            raise TransactionEffectUnknown() from exc
        finally:
            if created and not renamed and parent >= 0 and stage:
                # The private stage is removed ONLY when it is provably still
                # this operation's own private file and the canonical
                # destination is still absent.  A publication whose effect
                # cannot be proven is never repaired by a second write.
                try:
                    staged = os.stat(
                        stage, dir_fd=parent, follow_symlinks=False
                    )
                    if stage_ino is not None and staged.st_ino == stage_ino:
                        try:
                            occupied = os.stat(
                                os.path.basename(str(destination)),
                                dir_fd=parent,
                                follow_symlinks=False,
                            ).st_ino
                        except FileNotFoundError:
                            occupied = None
                        if occupied != staged.st_ino:
                            os.unlink(stage, dir_fd=parent)
                            os.fsync(parent)
                except OSError:
                    pass
            if parent >= 0:
                os.close(parent)

    def _publish_component_binding(self, transaction: TransactionContext) -> None:
        """Publish the ONE immutable binding artifact, or adopt an identical one.

        A destination that was already observed and sealed as present is
        ADOPTED without a write: no new filename, no retry rename, no
        overwrite and no second publication.  A destination that appears
        after the approved observation refuses without overwrite and without
        adoption.
        """

        self._recheck_component_bound(transaction)
        manifest = self._manifest()
        member = manifest.get("component_binding")
        payload = self._component_binding_candidate_bytes
        if type(member) is not dict or payload is None:
            raise TransactionEffectUnknown()
        if sha256_bytes(payload) != member["candidate_sha256"]:
            raise TransactionEffectUnknown()
        destination = Path(str(member["destination"]))
        if bool(member["destination_present"]):
            present, raw = self._component_binding_bytes(destination)
            if not present or raw != payload:
                raise TransactionEffectUnknown()
            return
        self._publish_component_binding_artifact(destination, payload)
        # The exact postimage is qualified after the publication.
        present, raw = self._component_binding_bytes(destination)
        if not present or raw != payload:
            raise TransactionEffectUnknown()

    def _component_requalify_binding(self) -> None:
        """The installed Control configuration must name the published binding.

        The selected binding is re-read through the SAME qualified artifact
        owner that published it, so a binding that drifted after the
        publication prevents completion instead of being discovered later.
        """

        manifest = self._manifest()
        member = manifest.get("component_binding")
        if type(member) is not dict:
            return
        try:
            _control, _worker, _cd, _wd, _cr, _wr = self._configs()
        except (HostControlError, KeyError, OSError) as exc:
            raise TransactionEffectUnknown() from exc
        control = json.loads(_cr.decode("utf-8")) if _cr else {}
        if (
            control.get("fabric_bindings_path") != member["destination"]
            or control.get("fabric_bindings_sha256") != member["candidate_sha256"]
        ):
            raise TransactionEffectUnknown()
        present, raw = self._component_binding_bytes(
            Path(str(member["destination"]))
        )
        if not present or sha256_bytes(raw) != member["candidate_sha256"]:
            raise TransactionEffectUnknown()

    def _component_service_uids_quiescent(self) -> None:
        """The fixed service-UID census of the stopped boundary.

        The census is the incumbent owner's own: it observes the process
        table and the launchd attribution and never sweeps, signals or
        accepts a caller-selected UID, PID or timeout.  A bootout is
        asynchronous, so a Control process that is still exiting is observed
        again within one bounded window instead of being declared live.
        """

        deadline = time.monotonic() + _CONTROL_COMPONENT_UID_CENSUS_TIMEOUT
        while True:
            try:
                self.require_service_uids_quiescent()
                return
            except ArmAdmissionError as exc:
                if (
                    exc.code != "service_uid_process_live"
                    or time.monotonic() >= deadline
                ):
                    raise _component_refusal(
                        "control_component_service_uids_live"
                    ) from exc
                time.sleep(0.25)

    def _recheck_component_quiescence(self, transaction: TransactionContext) -> None:
        """Re-prove the stopped boundary: runtime, custody and the Worker."""

        self._recheck_component_bound(transaction)
        try:
            configs = ConfigEvidence(
                control_sha256=transaction.prior_configs.control_sha256,
                worker_sha256=transaction.prior_configs.worker_sha256,
                control=transaction.prior_configs.control,
                worker=transaction.prior_configs.worker,
            )
            self.require_runtime_quiescent(configs)
        except Exception as exc:
            raise TransactionEffectUnknown() from exc
        try:
            self._component_service_uids_quiescent()
        except ComponentUpdateRefused as exc:
            raise TransactionEffectUnknown() from exc
        # The fixed absence: BOTH boundaries are absent at the stopped
        # boundary, and the Worker is still explicitly disabled.
        if self._component_label_loaded(
            CONTROL_LABEL, code="control_component_control_state_unknown"
        ):
            raise TransactionEffectUnknown()
        if self._component_label_loaded(
            WORKER_LABEL, code="control_component_worker_state_unknown"
        ):
            raise TransactionEffectUnknown()
        if self._component_disabled_override(WORKER_LABEL) is not True:
            raise TransactionEffectUnknown()

    def _replace_component_target(
        self,
        transaction: TransactionContext,
        path: Path,
        *,
        prior_field: str,
        target_field: str,
        payload: bytes,
        phase: str,
    ) -> None:
        """One exact-CAS replacement of one installed file."""

        self._recheck_component_bound(transaction)
        manifest = self._manifest()
        raw = self._component_root_file(
            path, code="control_component_plist_unreadable"
        )
        if sha256_bytes(raw) != manifest[prior_field]:
            raise TransactionEffectUnknown()
        if sha256_bytes(payload) != manifest[target_field]:
            raise TransactionEffectUnknown()
        _atomic_file(path, payload, mode=0o644, uid=0, gid=0, replace=True)
        written = self._component_root_file(
            path, code="control_component_plist_unreadable"
        )
        if written != payload:
            raise TransactionEffectUnknown()
        self._persist_phase(transaction, phase)

    def _publish_control_component_config(
        self, transaction: TransactionContext, candidate: Any
    ) -> None:
        """Publish the bounded Control configuration candidate."""

        control_candidate, _worker_candidate = self._candidate_paths(
            transaction.transaction_id
        )
        _atomic_file(
            control_candidate,
            candidate.control_config_after,
            mode=0o440,
            uid=0,
            gid=grp.getgrnam(CONTROL_GROUP).gr_gid,
            replace=False,
        )
        self.replace_control_config(transaction)

    def _component_validate_correlated_receipt(
        self, transaction: TransactionContext, payload: bytes
    ) -> None:
        """Re-prove the correlated receipt through the incumbent validator.

        The correlation preserves every authority, state, evidence, policy,
        scope and timestamp field of the existing DISARMED receipt; only the
        attested source release, the configuration digest correlation and the
        transaction label move.  The incumbent validator must still accept the
        result before it may be published.
        """

        try:
            document = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TransactionEffectUnknown() from exc
        if type(document) is not dict:
            raise TransactionEffectUnknown()
        readiness = document.get("provider_readiness_receipt_sha256")
        if type(readiness) is not str:
            raise TransactionEffectUnknown()
        try:
            validate_receipt_document(
                document,
                metadata=self._component_autonomy_metadata,
                expected=AutonomyExpectation(
                    release_sha=transaction.expected_sha,
                    control_config_sha256=transaction.candidates.control_sha256,
                    worker_config_sha256=transaction.candidates.worker_sha256,
                    provider_readiness_receipt_sha256=readiness,
                    capability_policy_digest=CAPABILITY_POLICY_DIGEST,
                    execution_profile_digest=EXECUTION_PROFILE_DIGEST,
                    native_helper_grant_digest=NATIVE_HELPER_GRANT_DIGEST,
                    security_config_digest=SECURITY_CONFIG_DIGEST,
                ),
                now=None,
                require_current=False,
            )
        except (AutonomyRefusal, TypeError, ValueError) as exc:
            raise TransactionEffectUnknown() from exc

    def _component_receipt_cas(self, path: Path, *, prior_field: str) -> bool:
        """The exact prior-byte compare-and-swap of one receipt.

        The receipt on disk must still be EXACTLY the sealed prior bytes.  A
        receipt that moved after the seal is an unbound later receipt: it is
        never overwritten.  The returned value says whether the receipt was
        present before this replacement.
        """

        manifest = self._manifest()
        present, raw = self._component_receipt_bytes(path)
        if (
            present is not manifest[prior_field.replace("_sha256", "_present")]
            or sha256_bytes(raw) != manifest[prior_field]
        ):
            raise TransactionEffectUnknown()
        return present

    def _publish_control_component_receipts(self, transaction: TransactionContext) -> None:
        """Publish the correlated receipts.  No authority is granted or refreshed."""

        self._recheck_component_bound(transaction)
        self._component_validate_correlated_receipt(
            transaction, self._component_target_autonomy_bytes
        )
        # The exact prior-byte compare-and-swap happens immediately before the
        # replacement, never after it.
        self._component_receipt_cas(
            AUTONOMY_RECEIPT,
            prior_field="component_prior_autonomy_receipt_sha256",
        )
        _atomic_file(
            AUTONOMY_RECEIPT,
            self._component_target_autonomy_bytes,
            mode=0o444,
            uid=0,
            gid=0,
            replace=True,
        )
        written, _info = _read_root_file(
            AUTONOMY_RECEIPT, modes=frozenset({0o444}), uid=0, gid=0
        )
        if written != self._component_target_autonomy_bytes:
            raise TransactionEffectUnknown()
        if not self._component_target_ceo_bytes:
            return
        replace = self._component_receipt_cas(
            CEO_SUBMIT_RECEIPT,
            prior_field="component_prior_ceo_receipt_sha256",
        )
        _atomic_file(
            CEO_SUBMIT_RECEIPT,
            self._component_target_ceo_bytes,
            mode=0o444,
            uid=0,
            gid=0,
            replace=replace,
        )
        written, _info = _read_root_file(
            CEO_SUBMIT_RECEIPT, modes=frozenset({0o444}), uid=0, gid=0
        )
        if written != self._component_target_ceo_bytes:
            raise TransactionEffectUnknown()

    def _component_enable_control(self) -> None:
        """One fixed, one-shot Control enable.

        The incumbent stop leaves the Control service explicitly disabled, so
        the offline mode must re-enable it exactly once before it can be
        bootstrapped.  The disabled override is read back after the effect: a
        lost response is never a silent success, and the enable is never
        repeated.
        """

        release = SYSTEM_ROOT / "releases" / self._active_transaction.expected_sha
        try:
            self._run_fixed(
                ["/bin/launchctl", "enable", f"system/{CONTROL_LABEL}"],
                cwd=release,
                timeout=45.0,
            )
        except Exception as exc:
            # The command may have crossed the launchd effect boundary even
            # when its response is unavailable.  The transaction is retained.
            raise TransactionEffectUnknown() from exc
        try:
            disabled = self._read_launchd_disabled_override(
                CONTROL_LABEL, allow_absent=True
            )
        except TransactionEffectUnknown as exc:
            raise TransactionEffectUnknown() from exc
        if disabled is not False:
            raise TransactionEffectUnknown()

    def _component_bootout_control(self) -> None:
        """One fixed Control bootout.  A source switch is never kickstart-only."""

        release = SYSTEM_ROOT / "releases" / self._active_transaction.expected_sha
        try:
            self._run_fixed(
                ["/bin/launchctl", "bootout", f"system/{CONTROL_LABEL}"],
                cwd=release,
                timeout=45.0,
            )
        except Exception:
            # The response may have been lost across the effect boundary.  The
            # absence is proved by observation, never by an exit code.
            pass
        try:
            loaded = self._loaded_observe_only(CONTROL_LABEL)
        except ArmAdmissionError as exc:
            raise TransactionEffectUnknown() from exc
        if loaded:
            raise TransactionEffectUnknown()

    def _component_bootstrap_control(self) -> None:
        """One fixed Control bootstrap of the VERIFIED new plist."""

        release = SYSTEM_ROOT / "releases" / self._active_transaction.expected_sha
        self._require_control_plist_safe()
        try:
            self._run_fixed(
                ["/bin/launchctl", "bootstrap", "system", os.fspath(CONTROL_PLIST)],
                cwd=release,
                timeout=45.0,
            )
        except Exception as exc:
            raise TransactionEffectUnknown() from exc
        try:
            loaded = self._loaded_observe_only(CONTROL_LABEL)
        except ArmAdmissionError as exc:
            raise TransactionEffectUnknown() from exc
        if not loaded:
            raise TransactionEffectUnknown()

    def write_control_component_receipt(
        self, transaction: TransactionContext, receipt: Mapping[str, Any]
    ) -> None:
        """Publish the one bounded receipt of this update."""

        if (
            self._transaction_owner_fd is None
            or self._active_transaction is None
            or self._active_transaction.transaction_id != transaction.transaction_id
        ):
            raise TransactionEffectUnknown()
        self._verify_published_inode(self._transaction_owner_fd)
        encoded = _encoded_json(receipt)
        # The exact prior-byte compare-and-swap happens immediately before the
        # replacement: a component receipt that moved after the seal is an
        # unbound later receipt and is never overwritten.
        replace = self._component_receipt_cas(
            CONTROL_COMPONENT_RECEIPT,
            prior_field="component_prior_component_receipt_sha256",
        )
        if replace:
            metadata = _receipt_metadata(CONTROL_COMPONENT_RECEIPT)
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
            CONTROL_COMPONENT_RECEIPT,
            encoded,
            mode=0o444,
            uid=0,
            gid=0,
            replace=replace,
        )
        readback, _info = _read_root_file(
            CONTROL_COMPONENT_RECEIPT, modes=frozenset({0o444}), uid=0, gid=0
        )
        if readback != encoded:
            raise TransactionEffectUnknown()


def _component_receipt_document(
    *,
    transaction_id: str,
    target_sha: str,
    prior_sha: str,
    candidate: Any,
    prior_seal: str,
    target_seal: str,
    plan_sha256: str,
    observed_at: str,
    mode: str,
) -> dict[str, Any]:
    from ops.executive_os import control_component_update as compiler

    return {
        "schema": CONTROL_COMPONENT_RECEIPT_SCHEMA,
        "transaction_id": transaction_id,
        "target_sha": target_sha,
        "prior_sha": prior_sha,
        "plan_sha256": plan_sha256,
        "mode": mode,
        "control_config_sha256": candidate.control_config_after_sha256,
        "prior_control_config_sha256": candidate.control_config_before_sha256,
        "control_plist_sha256": candidate.control_plist_after_sha256,
        "worker_plist_sha256": candidate.worker_plist_after_sha256,
        "worker_config_sha256": candidate.worker_config_sha256,
        "prior_release_seal_sha256": prior_seal,
        "target_release_seal_sha256": target_seal,
        "effects": list(compiler.effects_for_mode(mode)),
        "observed_at": observed_at,
        "tool_version": TOOL_VERSION,
    }


def _component_incomplete(
    host: ProductionControlComponentHost,
    transaction_id: str,
    exc: ComponentUpdateRefused,
) -> ComponentUpdateRefused:
    """Classify a refusal raised after the original transaction was claimed.

    The original transaction and its preimages are retained and the phase
    that was still incomplete is named.  Nothing is rolled back, nothing is
    replayed, and the result is never presented as a zero-effect refusal.
    """

    phase: str | None = None
    try:
        phase = str(host._manifest().get("phase"))
    except Exception:
        phase = None
    return ComponentUpdateRefused(
        exc.code,
        phase=phase,
        transaction_id=transaction_id,
    )


def execute_control_component_update(
    host: ProductionControlComponentHost,
    *,
    target_sha: str,
    plan_sha256: str,
    hermes_read: tuple[str, str] | None = None,
    native_conversation: tuple[str, str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Publish exactly the approved Control component plan.

    The plan is recompiled from the LIVE installed state and its digest must
    match the operator's digest exactly.  The marker is then claimed on the
    ONE existing global owner, the preimages are sealed, and the effects are
    dispatched in the fixed order: one Control bootout, the stopped-boundary
    proof, the ONE immutable binding publication when the operation carries
    a Hermes host-read selection, the bounded target publications and the
    validated receipt correlations, one Control bootstrap of the verified new
    plist, the wrapper-attested consumed-config proof, the requalification of
    the selected binding, and the control observation published by the SAME
    held owner.
    """

    from ops.executive_os import control_component_update as compiler

    host.effective_uid()
    options = dict(target_sha=target_sha, hermes_read=hermes_read)
    if native_conversation is not None:
        options["native_conversation"] = native_conversation
    observation = host.observe_control_component_update(**options)
    document = observation["plan"]
    if compiler.plan_digest(document) != plan_sha256:
        raise _component_refusal("control_component_plan_digest_mismatch")
    candidate = observation["candidate"]
    transaction_id = host.new_transaction_id()
    target_autonomy = correlate_component_authority_receipt(
        observation["autonomy_receipt"],
        target_sha=target_sha,
        prior_control_sha256=observation["prior_configs"].control_sha256,
        target_control_sha256=candidate.control_config_after_sha256,
        transaction_id=transaction_id,
    )
    target_ceo = (
        correlate_component_ceo_receipt(
            observation["ceo_receipt"],
            target_sha=target_sha,
            transaction_id=transaction_id,
        )
        if observation["ceo_receipt"] is not None
        else None
    )
    transaction = TransactionContext(
        transaction_id=transaction_id,
        expected_sha=target_sha,
        prior_configs=observation["prior_configs"],
        candidates=observation["candidate_configs"],
        admission=None,
    )
    host._component_candidate = candidate
    host._component_plan_sha256 = plan_sha256
    host._component_prior_seal = observation["prior_seal"]
    host._component_target_seal = observation["target_seal"]
    host._component_observed_at = _receipt_timestamp(
        now if now is not None else datetime.now(UTC)
    )
    host._component_autonomy_metadata = observation["autonomy_receipt_metadata"]
    host._component_target_autonomy_bytes = _encoded_json(target_autonomy)
    host._component_target_ceo_bytes = (
        _encoded_json(target_ceo) if target_ceo is not None else b""
    )
    # The mode and its two disabled preimages are bound in the sealed marker.
    host._component_mode_bound = observation["mode"]
    host._component_control_launchd_disabled = observation["control_launchd_disabled"]
    host._component_worker_launchd_disabled = observation["worker_launchd_disabled"]
    # The archived preimages are the EXACT bytes that were on disk, never a
    # re-encoded parse of them.
    receipt_preimages = observation["receipt_preimages"]
    host._component_prior_archives = {
        "prior-component-autonomy-receipt.json": receipt_preimages[
            "authority_receipt"
        ][2],
        "prior-component-ceo-submit-receipt.json": receipt_preimages[
            "ceo_submit_receipt"
        ][2],
        "prior-component-receipt.json": receipt_preimages["component_receipt"][2],
        "prior-control-plist.plist": observation["prior_control_plist"],
        "prior-worker-plist.plist": observation["prior_worker_plist"],
    }
    # The OPTIONAL selection: its qualified input, the ORIGINAL bytes of the
    # prior selected binding and the exact merged candidate are sealed with
    # the rest of the preimages, before the canonical marker can become
    # visible.
    binding = observation["binding"]
    if binding is not None:
        if candidate.selection is None:  # pragma: no cover - the closed pair
            raise TransactionEffectUnknown()
        host._component_binding_metadata = dict(candidate.selection.document())
        host._component_binding_candidate_bytes = binding["candidate_bytes"]
        host._component_binding_input = (
            native_conversation if native_conversation is not None else hermes_read
        )
        host._component_binding_prior_raw = binding["prior_raw"]
        host._component_binding_prior_selector_present = bool(
            binding["prior_selector_present"]
        )
        host._component_prior_archives.update(
            {
                "prior-component-binding-selection.json": binding["prior_raw"],
                ("prior-component-native-conversation-input.json"
                 if candidate.selection.input_kind == "native_conversation"
                 else "prior-component-hermes-read-input.json"): binding["input_raw"],
                "component-binding-candidate.json": binding["candidate_bytes"],
            }
        )
    # The one receipt this update owes is derived from the retained manifest
    # and the recompiled candidate, so it is byte-identical to the document
    # the original operation owed.
    host._component_target_component_bytes = _encoded_json(
        _component_receipt_document(
            transaction_id=transaction_id,
            target_sha=target_sha,
            prior_sha=candidate.prior_sha,
            candidate=candidate,
            prior_seal=observation["prior_seal"],
            target_seal=observation["target_seal"],
            plan_sha256=plan_sha256,
            observed_at=host._component_observed_at,
            mode=observation["mode"],
        )
    )
    host._active_transaction = transaction
    try:
        host._create_marker(transaction, operation=CONTROL_COMPONENT_UPDATE)
    except FileExistsError as exc:
        host._active_transaction = None
        raise _component_refusal("control_component_transaction_occupied") from exc
    try:
        # The retained interpreter qualification is rechecked under the SAME
        # budget it was observed under, before the first effect.  The recheck
        # follows the marker claim directly, so the budget it spends is the
        # budget the observation opened.
        host._component_recheck_interpreter()
        host._recheck_component_preimages(transaction, observation)
        if observation["mode"] == _COMPONENT_LIVE_MODE:
            # One Control bootout.  The source switch cannot be kickstart-only:
            # kickstart would reuse the already-loaded job definition and keep
            # running the prior release.
            host._persist_phase(transaction, "CONTROL_BOOTOUT_RECORDED")
            host._component_bootout_control()
        else:
            # The offline mode's Control is ALREADY absent.  There is no
            # bootout to dispatch and no bootout to record: the absence is
            # proved by observation alone.
            if host._component_label_loaded(
                CONTROL_LABEL, code="control_component_control_state_unknown"
            ):
                raise TransactionEffectUnknown()
        host._recheck_component_quiescence(transaction)
        host._persist_phase(transaction, "CONTROL_ABSENT_PROVEN")
        if host._component_binding_metadata is not None:
            # The ONE immutable binding publication.  It happens AFTER the
            # stopped-boundary proof and BEFORE the Control configuration may
            # name it, and it is published exactly once.
            host._persist_phase(
                transaction, "CONTROL_COMPONENT_BINDING_PUBLICATION_STARTED"
            )
            host._publish_component_binding(transaction)
            host._persist_phase(transaction, "CONTROL_COMPONENT_BINDING_PROVEN")
        # The bounded target publications and the validated receipt
        # correlations.
        host._replace_component_target(
            transaction,
            CONTROL_PLIST,
            prior_field="component_prior_control_plist_sha256",
            target_field="component_target_control_plist_sha256",
            payload=candidate.control_plist_after,
            phase="CONTROL_PLIST_REPLACED",
        )
        host._replace_component_target(
            transaction,
            WORKER_PLIST,
            prior_field="component_prior_worker_plist_sha256",
            target_field="component_target_worker_plist_sha256",
            payload=candidate.worker_plist_after,
            phase="WORKER_PLIST_REPLACED",
        )
        host._publish_control_component_config(transaction, candidate)
        host._publish_control_component_receipts(transaction)
        host._persist_phase(transaction, "AUTHORITY_RECEIPT_CORRELATED")
        if observation["mode"] == _COMPONENT_OFFLINE_MODE:
            # The incumbent stop left the Control explicitly disabled, so it
            # must be enabled exactly once before it can be bootstrapped.
            host._persist_phase(transaction, "CONTROL_ENABLE_RECORDED")
            host._component_enable_control()
            host._persist_phase(transaction, "CONTROL_ENABLED_PROVEN")
        # One Control bootstrap of the VERIFIED new plist.
        host._persist_phase(transaction, "CONTROL_BOOTSTRAP_RECORDED")
        host._component_bootstrap_control()
        # The wrapper-attested consumed-config proof: the live pid, the boot
        # identity, the target release and the exact consumed configuration.
        host.prove_control_admission_bound(
            target_sha, candidate.control_config_after_sha256
        )
        # The selected binding is requalified through the SAME qualified
        # pinned read the Control's own loader uses: a binding that drifted
        # after the publication prevents completion.
        host._component_requalify_binding()
        host._persist_phase(transaction, "CONTROL_COMPONENT_TARGETS_PROVEN")
        receipt = _component_receipt_document(
            transaction_id=transaction.transaction_id,
            target_sha=target_sha,
            prior_sha=candidate.prior_sha,
            candidate=candidate,
            prior_seal=observation["prior_seal"],
            target_seal=observation["target_seal"],
            plan_sha256=plan_sha256,
            observed_at=host._component_observed_at,
            mode=observation["mode"],
        )
        host.write_control_component_receipt(transaction, receipt)
        host._persist_phase(transaction, "CONTROL_COMPONENT_RECEIPT_REPLACED")
        host.complete_transaction(transaction)
    except ComponentUpdateRefused as exc:
        # The marker exists: this refusal is NOT a zero-effect refusal.  The
        # original transaction and its preimages are retained and the phase
        # that was still incomplete is named, so the caller reports an
        # uncertain original operation instead of a clean one.
        raise _component_incomplete(host, transaction.transaction_id, exc) from exc
    except TransactionEffectUnknown:
        raise
    except Exception as exc:
        raise TransactionEffectUnknown() from exc
    return {
        "ok": True,
        "outcome": "UPDATED",
        "target_sha": target_sha,
        "plan_sha256": plan_sha256,
        "transaction_id": transaction.transaction_id,
    }


def reconcile_control_component_update(
    host: ProductionControlComponentHost, *, target_sha: str
) -> dict[str, Any]:
    """Prove one interrupted update to its exact retained postimages.

    Reconciliation NEVER republishes a target, NEVER re-dispatches a recorded
    bootout or bootstrap and NEVER rolls back.  It recompiles the candidate
    from the ARCHIVED preimages, proves every retained postimage exactly, and
    completes the marker only when all of them hold.

    Once the transaction owner is claimed, EVERY qualification or read
    failure is an INCOMPLETE or EFFECT_UNKNOWN outcome.  The original marker
    and its preimages are retained, and the caller is never told that an
    already claimed transaction had no effect.
    """

    host.effective_uid()
    if not host._transaction_present():
        raise _component_refusal("control_component_transaction_absent")
    host._claim_transaction_owner()
    # EVERY step that follows the claim happens INSIDE the retained
    # transaction's own classification.  The manifest read, the component
    # checks, the qualified transaction identity and the delegated
    # reconciliation are one guarded region: a malformed or unexpected
    # manifest can no longer escape as a generic zero-effect refusal, because
    # the original transaction was already claimed.
    #
    # Until the transaction identity is qualified, EVERY unexpected error
    # leaves the ORIGINAL operation uncertain and is reported as
    # ``TransactionEffectUnknown``.  Once the identity is qualified, a
    # ``ComponentUpdateRefused`` is the incumbent's own INCOMPLETE
    # classification and names the phase that was still incomplete.
    transaction_id: str | None = None
    try:
        manifest = host._manifest()
        if (
            manifest.get("operation") != CONTROL_COMPONENT_UPDATE
            or manifest.get("expected_sha") != target_sha
            or manifest.get("phase") not in _COMPONENT_PHASES
            or not _COMPONENT_MANIFEST_FIELDS <= set(manifest)
        ):
            raise TransactionEffectUnknown()
        transaction_id = str(manifest["transaction_id"])
        return _reconcile_control_component_update(
            host, manifest, target_sha
        )
    except ComponentUpdateRefused as exc:
        # The original transaction was already claimed: this is NOT a
        # zero-effect refusal.  The marker and its preimages are retained,
        # the incomplete phase is named, and nothing is replayed or rolled
        # back.
        if transaction_id is None:
            # The original transaction identity is not qualified yet, so no
            # incomplete phase of an identified transaction can be named.
            raise TransactionEffectUnknown() from exc
        raise _component_incomplete(host, transaction_id, exc) from exc
    except TransactionEffectUnknown:
        raise
    except Exception as exc:
        # A qualification or a read that fails after the claim leaves the
        # ORIGINAL transaction uncertain: nothing is replayed, nothing is
        # rolled back and nothing is reported as a clean refusal.
        raise TransactionEffectUnknown() from exc


def _reconcile_control_component_update(
    host: ProductionControlComponentHost,
    manifest: Mapping[str, Any],
    target_sha: str,
) -> dict[str, Any]:
    """The retained-postimage proof of one claimed Control component update."""

    from ops.executive_os import control_component_update as compiler

    archives = host._component_archives(manifest)
    # The OPTIONAL selection is reconstructed from the SEALED bytes of the
    # original operation.  A reconciliation never takes a replacement input
    # and never reads a new external selection.
    member = manifest.get("component_binding")
    selection = None
    binding_payload: bytes | None = None
    if type(member) is dict:
        from control_plane import executive_fabric_composition as composition

        try:
            native_input = member.get("input_kind") == "native_conversation"
            input_raw = archives["prior-component-native-conversation-input.json"
                                 if native_input else "prior-component-hermes-read-input.json"]
            prior_raw = archives["prior-component-binding-selection.json"]
            candidate_raw = archives["component-binding-candidate.json"]
            # Recovery joins every original archive to its sealed bytes,
            # including serialization that composition does not preserve.
            if sha256_bytes(input_raw) != member["input_sha256"]:
                raise TransactionEffectUnknown()
            if (
                not 0 < len(candidate_raw) <= composition.MAX_CONFIG_BYTES
                or sha256_bytes(candidate_raw) != member["candidate_sha256"]
            ):
                raise TransactionEffectUnknown()
            candidate_document = composition._document(candidate_raw)
            if type(candidate_document) is not dict:
                raise TransactionEffectUnknown()
            input_document = composition._document(input_raw)
            if type(input_document) is not dict:
                raise composition.FabricCompositionError(
                    "Hermes host observation differs from its closed schema"
                )
            prior_document = {}
            if member["prior_selector_present"]:
                if not prior_raw or sha256_bytes(prior_raw) != member["prior_binding_sha256"]:
                    raise TransactionEffectUnknown()
                prior_document = composition._document(prior_raw)
                if type(prior_document) is not dict:
                    raise TransactionEffectUnknown()
                prior_bindings = tuple(prior_document.get("bindings") or ())
                prior_transports = tuple(
                    prior_document.get("remote_transports") or ()
                )
            else:
                if prior_raw != b"" or member["prior_binding_sha256"] != "":
                    raise TransactionEffectUnknown()
                prior_bindings = ()
                prior_transports = ()
            # The original sealed candidate identifies its composition policy.
            # Historical v3 transactions retain their original bytes even when
            # an older writer omitted a prior conversation. New v4/v5/v6 candidates
            # preserve the complete matching prior family; never reinterpret a
            # claimed transaction from fresh installed selections.
            prior_secretary_conversation = None
            prior_meta_conversation = None
            prior_native_conversation = None
            candidate_schema = candidate_document.get("schema_version")
            if native_input:
                if (not member["prior_selector_present"]
                        or candidate_schema != composition.NATIVE_CONFIG_SCHEMA_VERSION
                        or prior_document.get("schema_version") not in (
                            composition.CONVERSATION_CONFIG_SCHEMA_VERSION,
                            composition.NATIVE_CONFIG_SCHEMA_VERSION)):
                    raise TransactionEffectUnknown()
                prior_parts = composition._composition_parts(prior_raw)
                if (prior_document.get("native_conversation") is not None
                        and prior_document["native_conversation"] != input_document):
                    raise TransactionEffectUnknown()
                composition.NativeOperatorHostSelection.from_document(input_document, prior_parts[2])
                prior_native_conversation = input_document
                input_document = prior_document["hermes_role_metadata_read"]
                prior_secretary_conversation = prior_document["hermes_secretary_conversation"]
                prior_meta_conversation = prior_document["hermes_meta_conversation"]
                composition._composition_parts(candidate_raw)
            elif candidate_schema in (
                composition.SECRETARY_CONFIG_SCHEMA_VERSION,
                composition.CONVERSATION_CONFIG_SCHEMA_VERSION,
                composition.NATIVE_CONFIG_SCHEMA_VERSION,
            ):
                if prior_document.get("schema_version") != candidate_schema:
                    raise TransactionEffectUnknown()
                prior_secretary_conversation = prior_document.get("hermes_secretary_conversation")
                if type(prior_secretary_conversation) is not dict:
                    raise TransactionEffectUnknown()
                if candidate_schema in (composition.CONVERSATION_CONFIG_SCHEMA_VERSION,
                                        composition.NATIVE_CONFIG_SCHEMA_VERSION):
                    prior_meta_conversation = prior_document.get("hermes_meta_conversation")
                    if type(prior_meta_conversation) is not dict:
                        raise TransactionEffectUnknown()
                if candidate_schema == composition.NATIVE_CONFIG_SCHEMA_VERSION:
                    prior_native_conversation = prior_document.get("native_conversation")
                    if type(prior_native_conversation) is not dict:
                        raise TransactionEffectUnknown()
            elif candidate_schema != composition.HOST_READ_CONFIG_SCHEMA_VERSION:
                raise TransactionEffectUnknown()
            binding_payload = compiler.compose_binding_candidate(
                input_document=input_document,
                prior_bindings=prior_bindings,
                prior_remote_transports=prior_transports,
                prior_secretary_conversation=prior_secretary_conversation,
                prior_meta_conversation=prior_meta_conversation,
                prior_native_conversation=prior_native_conversation,
            )
        except (composition.FabricCompositionError, KeyError, OSError, ValueError) as exc:
            raise TransactionEffectUnknown() from exc
        if (
            sha256_bytes(binding_payload) != member["candidate_sha256"]
            or candidate_raw != binding_payload
        ):
            raise TransactionEffectUnknown()
        if compiler.binding_destination(str(member["candidate_sha256"])) != member[
            "destination"
        ]:
            raise TransactionEffectUnknown()
        selection = compiler.BindingSelectionInputs(
            input_document=input_document,
            prior_bindings=prior_bindings,
            prior_remote_transports=prior_transports,
            prior_secretary_conversation=prior_secretary_conversation,
            prior_meta_conversation=prior_meta_conversation,
            prior_native_conversation=prior_native_conversation,
            input_kind=member.get("input_kind"),
            input_sha256=str(member["input_sha256"]),
            prior_binding_sha256=str(member["prior_binding_sha256"]),
            prior_selector_present=bool(member["prior_selector_present"]),
            destination_present=bool(member["destination_present"]),
        )
        host._component_binding_metadata = dict(member)
        host._component_binding_candidate_bytes = binding_payload
        host._component_binding_prior_raw = prior_raw
        host._component_binding_prior_selector_present = bool(
            member["prior_selector_present"]
        )
    prior_control_plist = archives["prior-control-plist.plist"]
    prior_worker_plist = archives["prior-worker-plist.plist"]
    prior_control_config = archives["prior-control.json"]
    prior_worker_config = archives["prior-worker.json"]
    try:
        prior_plist_document = plistlib.loads(prior_control_plist)
    except (plistlib.InvalidFileException, ValueError, TypeError) as exc:
        raise TransactionEffectUnknown() from exc
    prior_sha = ProductionControlComponentHost._component_prior_release(
        prior_plist_document
    )
    prior_release_root = os.fspath(SYSTEM_ROOT / "releases" / prior_sha)
    target_release_root = os.fspath(SYSTEM_ROOT / "releases" / target_sha)
    # BOTH actual configurations are re-read through the incumbent qualified
    # configuration owner.  The retained manifest is never a substitute for
    # the installed Worker configuration: the Worker must still carry the
    # exact bytes and the exact digest this operation left untouched, so a
    # Worker that drifted after the interruption is refused here, before any
    # publication, lifecycle effect or closeout.
    try:
        (
            _control_document,
            _worker_document,
            control_digest,
            worker_digest,
            _control_raw,
            worker_raw,
        ) = host._configs()
    except (HostControlError, KeyError, OSError, ValueError) as exc:
        raise TransactionEffectUnknown() from exc
    if control_digest != manifest["target_control_sha256"]:
        if type(member) is dict:
            # The immutable binding artifact was published, but the Control
            # configuration was never switched to it.  The ORIGINAL operation
            # is INCOMPLETE: the artifact stays inert, nothing is resumed,
            # nothing is republished and no lifecycle effect is dispatched.
            raise ComponentUpdateRefused(
                "control_component_binding_config_not_switched"
            )
        raise TransactionEffectUnknown()
    if worker_digest != manifest["target_worker_sha256"]:
        raise TransactionEffectUnknown()
    if worker_raw != prior_worker_config:
        raise TransactionEffectUnknown()
    try:
        candidate = compiler.compile_candidate(
            prior_control_config,
            prior_control_plist,
            prior_worker_plist,
            target_sha=target_sha,
            prior_sha=prior_sha,
            worker_config_sha256=worker_digest,
            prior_release_root=prior_release_root,
            target_release_root=target_release_root,
            selection=selection,
        )
    except compiler.ComponentError as exc:
        raise TransactionEffectUnknown() from exc
    if type(member) is dict and (
        candidate.selection is None or candidate.selection.document() != member
    ):
        # Counts and execution presence must describe the exact recovered
        # rows; a well-shaped marker alone is not proof of their contents.
        raise TransactionEffectUnknown()
    if (
        candidate.control_config_after_sha256 != manifest["target_control_sha256"]
        or candidate.control_plist_after_sha256
        != manifest["component_target_control_plist_sha256"]
        or candidate.worker_plist_after_sha256
        != manifest["component_target_worker_plist_sha256"]
    ):
        raise TransactionEffectUnknown()
    # The target release and the administrative checkout are qualified
    # FRESH: an interrupted update is only reconciled against a target source
    # that is still sealed and still present.  A qualification that cannot be
    # made leaves the ORIGINAL transaction uncertain: nothing is replayed and
    # nothing is rolled back.
    try:
        target_seal = host._component_release_seal(target_sha, target=True)
    except ComponentUpdateRefused as exc:
        raise TransactionEffectUnknown() from exc
    if target_seal != manifest["component_target_release_seal_sha256"]:
        raise TransactionEffectUnknown()
    try:
        admin_checkout_commit = host._component_admin_checkout(target_sha)
    except ComponentUpdateRefused as exc:
        raise TransactionEffectUnknown() from exc
    if admin_checkout_commit != target_sha:
        raise TransactionEffectUnknown()
    # Every retained postimage must hold exactly.
    for path, field in (
        (CONTROL_PLIST, "component_target_control_plist_sha256"),
        (WORKER_PLIST, "component_target_worker_plist_sha256"),
    ):
        raw = host._component_root_file(
            path, code="control_component_plist_unreadable"
        )
        if sha256_bytes(raw) != manifest[field]:
            raise TransactionEffectUnknown()
    if type(member) is dict:
        # The ONE immutable binding artifact is proved at its ORIGINAL
        # derived destination.  A reconciliation NEVER re-enters the
        # canonical publication: it inspects the original destination and
        # the exact retained postimage, and nothing else.
        present, raw = host._component_binding_bytes(
            Path(str(member["destination"]))
        )
        phase = str(manifest.get("phase"))
        if not present:
            if phase == "CONTROL_COMPONENT_BINDING_PUBLICATION_STARTED":
                # The publication was never completed: the ORIGINAL operation
                # is INCOMPLETE and nothing is republished.
                raise ComponentUpdateRefused(
                    "control_component_hermes_read_binding_conflict"
                )
            raise TransactionEffectUnknown()
        if raw != binding_payload:
            # A conflicting postimage is never adopted and never overwritten.
            raise TransactionEffectUnknown()
        # The selected binding is requalified through the SAME qualified
        # pinned read the Control's own loader uses.
        host._component_requalify_binding()
    autonomy_raw, _info = _read_root_file(
        AUTONOMY_RECEIPT, modes=frozenset({0o444}), uid=0, gid=0
    )
    if sha256_bytes(autonomy_raw) != manifest[
        "component_target_autonomy_receipt_sha256"
    ]:
        raise TransactionEffectUnknown()
    # The CEO-submit receipt is read through the SAME qualified receipt owner
    # that produced the sealed preimage.  There is NO direct ambient path
    # check here: an ``exists()``/``is_symlink()`` probe bypasses the owner,
    # observes whatever the live host happens to carry, and cannot tell an
    # absent receipt from an unreadable one.  The explicit (presence, bytes)
    # pair names the SAME snapshot the sealed preimage named, and that ONE
    # snapshot is reused below instead of being read again.
    try:
        ceo_present, ceo_raw = host._component_receipt_bytes(CEO_SUBMIT_RECEIPT)
    except ComponentUpdateRefused as exc:
        raise TransactionEffectUnknown() from exc
    if manifest["component_prior_ceo_receipt_present"]:
        if not ceo_present:
            raise TransactionEffectUnknown()
        if sha256_bytes(ceo_raw) != manifest["component_target_ceo_receipt_sha256"]:
            raise TransactionEffectUnknown()
    elif ceo_present:
        raise TransactionEffectUnknown()
    # The lifecycle is qualified FRESH and is NEVER replayed: the Control is
    # running the target source, the Worker is still absent and disabled, and
    # the Control is not disabled.
    mode = str(manifest["component_mode"])
    if host._component_label_loaded(
        WORKER_LABEL, code="control_component_worker_state_unknown"
    ):
        raise TransactionEffectUnknown()
    if host._component_disabled_override(WORKER_LABEL) is not True:
        raise TransactionEffectUnknown()
    control_disabled = host._component_disabled_override(CONTROL_LABEL)
    if mode == _COMPONENT_OFFLINE_MODE:
        if control_disabled is not False:
            raise TransactionEffectUnknown()
    elif control_disabled is True:
        raise TransactionEffectUnknown()
    # The live Control service must be running the target source and must have
    # consumed the exact configuration.
    if not host._component_label_loaded(
        CONTROL_LABEL, code="control_component_control_state_unknown"
    ):
        raise TransactionEffectUnknown()
    if not host._ceo_admission_probe(
        target_sha, candidate.control_config_after_sha256
    ):
        raise TransactionEffectUnknown()
    # The runtime is qualified FRESH and rechecked under the SAME budget
    # immediately before the first effect this reconciliation still owes.
    try:
        host._component_interpreter_observation()
    except ComponentUpdateRefused as exc:
        raise TransactionEffectUnknown() from exc
    host._component_recheck_interpreter()
    transaction = TransactionContext(
        transaction_id=str(manifest["transaction_id"]),
        expected_sha=target_sha,
        prior_configs=ConfigEvidence(
            control_sha256=str(manifest["prior_control_sha256"]),
            worker_sha256=str(manifest["prior_worker_sha256"]),
            control=json.loads(prior_control_config.decode("utf-8")),
            worker=json.loads(prior_worker_config.decode("utf-8")),
            control_bytes=prior_control_config,
            worker_bytes=prior_worker_config,
        ),
        candidates=CandidateConfigs(
            control=json.loads(candidate.control_config_after.decode("utf-8")),
            worker=json.loads(worker_raw.decode("utf-8")),
            control_bytes=candidate.control_config_after,
            worker_bytes=worker_raw,
            control_sha256=candidate.control_config_after_sha256,
            worker_sha256=worker_digest,
        ),
        admission=None,
    )
    host._active_transaction = transaction
    host._component_candidate = candidate
    host._component_plan_sha256 = str(manifest["component_plan_sha256"])
    host._component_prior_seal = str(manifest["component_prior_release_seal_sha256"])
    host._component_target_seal = str(manifest["component_target_release_seal_sha256"])
    host._component_observed_at = str(manifest["component_observed_at"])
    host._component_prior_archives = archives
    # The EXPLICIT presence of every receipt the original operation bound.
    # It is read back from the retained manifest, never inferred from the
    # byte length of an archived preimage.
    host._component_prior_receipt_presence = {
        "authority_receipt": bool(
            manifest["component_prior_autonomy_receipt_present"]
        ),
        "ceo_submit_receipt": bool(
            manifest["component_prior_ceo_receipt_present"]
        ),
        "component_receipt": bool(
            manifest["component_prior_component_receipt_present"]
        ),
    }
    host._component_mode_bound = mode
    host._component_control_launchd_disabled = bool(
        manifest["component_prior_control_launchd_disabled"]
    )
    host._component_worker_launchd_disabled = bool(
        manifest["component_prior_worker_launchd_disabled"]
    )
    host._component_target_autonomy_bytes = autonomy_raw
    # The SAME qualified snapshot that was proved above, never a second read
    # of the same receipt: the correlated bytes and the sealed digest name
    # one set of bytes.
    host._component_target_ceo_bytes = ceo_raw if ceo_present else b""
    # The retained component receipt is compared against the byte-identical
    # document the original operation owed, derived from the retained
    # manifest and the recompiled candidate.
    receipt = _component_receipt_document(
        transaction_id=transaction.transaction_id,
        target_sha=target_sha,
        prior_sha=prior_sha,
        candidate=candidate,
        prior_seal=str(manifest["component_prior_release_seal_sha256"]),
        target_seal=str(manifest["component_target_release_seal_sha256"]),
        plan_sha256=str(manifest["component_plan_sha256"]),
        observed_at=str(manifest["component_observed_at"]),
        mode=mode,
    )
    receipt_bytes = _encoded_json(receipt)
    if sha256_bytes(receipt_bytes) != manifest[
        "component_target_component_receipt_sha256"
    ]:
        raise TransactionEffectUnknown()
    host._component_target_component_bytes = receipt_bytes
    receipt_present, receipt_raw = host._component_receipt_bytes(
        CONTROL_COMPONENT_RECEIPT
    )
    if receipt_present:
        if receipt_raw != receipt_bytes:
            # An unbound later receipt is never overwritten.
            raise TransactionEffectUnknown()
        if manifest.get("phase") == "CONTROL_COMPONENT_TARGETS_PROVEN":
            # The receipt was written by the original operation before the
            # phase was recorded.  The phase is advanced; nothing is
            # republished.
            host._persist_phase(transaction, "CONTROL_COMPONENT_RECEIPT_REPLACED")
    elif manifest.get("phase") == "CONTROL_COMPONENT_RECEIPT_REPLACED":
        # The marker says the receipt was replaced and it is not there: the
        # retained postimage does not hold.
        raise TransactionEffectUnknown()
    elif manifest.get("phase") == "CONTROL_COMPONENT_TARGETS_PROVEN":
        # The bounded receipt was not written yet.  Its bytes are derived from
        # the retained manifest and the recompiled candidate, so it is the
        # byte-identical document the original operation owed.
        host.write_control_component_receipt(transaction, receipt)
        host._persist_phase(transaction, "CONTROL_COMPONENT_RECEIPT_REPLACED")
    # The ONE control observation this transaction still owes.  The incumbent
    # publisher performs it exactly once and refuses a second attempt.
    host._component_observation_recovery_owner = (
        os.getpid(),
        host._transaction_owner_fd,
        transaction.transaction_id,
        target_sha,
    )
    from ops.executive_os.control_observation import publish_for_transaction

    publish_for_transaction(host, transaction)
    host.complete_transaction(transaction)
    return {
        "ok": True,
        "outcome": "RECONCILED",
        "target_sha": target_sha,
        "transaction_id": transaction.transaction_id,
    }


def _run_control_component_command(
    host: ProductionControlComponentHost,
    args: argparse.Namespace,
    *,
    now: datetime,
) -> int:
    """The closed root-only Control component CLI: typed refusals, sanitized documents."""

    from ops.executive_os import control_component_update as compiler

    try:
        if args.command == "plan-control-component":
            document = compiler.plan(
                host,
                target_sha=args.expected_sha,
                hermes_read_input=getattr(
                    args, "hermes_role_metadata_read_input", None
                ),
                hermes_read_sha256=getattr(
                    args, "hermes_role_metadata_read_sha256", None
                ),
                native_conversation_input=getattr(args, "native_conversation_input", None),
                native_conversation_sha256=getattr(args, "native_conversation_sha256", None),
            )
        elif args.command == "apply-control-component":
            document = compiler.apply(
                host,
                target_sha=args.expected_sha,
                plan_sha256=args.plan_sha256,
                hermes_read_input=getattr(
                    args, "hermes_role_metadata_read_input", None
                ),
                hermes_read_sha256=getattr(
                    args, "hermes_role_metadata_read_sha256", None
                ),
                native_conversation_input=getattr(args, "native_conversation_input", None),
                native_conversation_sha256=getattr(args, "native_conversation_sha256", None),
            )
        else:
            document = compiler.reconcile(host, target_sha=args.expected_sha)
    except compiler.ComponentError as exc:
        # A supplied or observed state that cannot produce this component
        # update.  It is a typed refusal with zero cutover.
        print(
            json.dumps(
                {"ok": False, "outcome": "REFUSED", "code": exc.code},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 1
    except ComponentUpdateRefused as exc:
        if exc.incomplete:
            # The original transaction was already claimed: this is NOT a
            # zero-effect refusal.  The transaction and its preimages are
            # retained, the incomplete phase is named, and nothing is rolled
            # back or replayed.
            print(
                json.dumps(
                    {
                        "ok": False,
                        "outcome": "INCOMPLETE",
                        "code": exc.code,
                        "phase": exc.phase,
                        "transaction_id": exc.transaction_id,
                        "note": "the original transaction marker and its preimages are "
                        "retained; nothing is replayed and no rollback is performed",
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            return 2
        print(
            json.dumps(
                {"ok": False, "outcome": "REFUSED", "code": exc.code},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 1
    except TransactionEffectUnknown as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "outcome": "EFFECT_UNKNOWN",
                    "code": str(exc) or "control_component_effect_unknown",
                    "note": "the original transaction marker and its preimages are "
                    "retained; nothing is replayed and no rollback is performed",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "outcome": "REFUSED",
                    "code": "CONTROL_COMPONENT_UNEXPECTED_"
                    + type(exc).__name__.upper(),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 1
    print(json.dumps(document, sort_keys=True, separators=(",", ":")))
    return 0 if document.get("ok") else 3

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
    commission_templates: Sequence[Mapping[str, Any]],
    helper_hashes: Mapping[str, str],
    capability_profile_digests: dict[str, str] | None = None,
) -> None:
    """Hold the publication's own preservation law before any target write.

    The two JSON targets must be the owner's canonical document encoding, the
    MCP postimage must remain a valid installed configuration that preserves
    every current policy block and the same enrolled web identity, the plist
    postimage must join the fixed release entry point and config path, and the
    grant postimage must be the ONE exact existing grant document: the
    derived canonical OS submit policy and exact ordered receipt-derived
    templates carrying the Root-derived namespace scope.
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
    from ops.executive_os.mcp_component_update import _apply_capability_profile_digests
    expected = copy.deepcopy(prior)
    try:
        _apply_capability_profile_digests(prior, expected, capability_profile_digests)
    except (TypeError, ValueError) as exc:
        raise GatewayPublicationError("gateway_capability_profiles_invalid") from exc
    if (config.get("coo") != expected.get("coo")
            or ("coo" in config) != ("coo" in expected)
            or config.get("selected_child_target") != prior.get("selected_child_target")
            or ("selected_child_target" in config) != ("selected_child_target" in prior)):
        raise GatewayPublicationError("gateway_target_invalid")
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
        or compiler_canonical(grant["grants"]) != compiler_canonical([
            {"principal_scope": derived_scope, "template": dict(template)}
            for template in commission_templates
        ])
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
    predecessor = host.gateway_receipt_admission(request)
    host.require_transaction_absent()
    preparation = prepare_gateway_publication(host, request, predecessor=predecessor)
    if predecessor is not None:
        host.qualify_gateway_predecessor(predecessor, preparation)
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
        _MCP_AUDIT_BEFORE_FIELD: preparation.mcp_auth_audit,
        _MCP_AUDIT_AFTER_FIELD: None,
    }
    host._prior_grant_bytes = preparation.prior_grant_bytes
    host._predecessor_receipt = predecessor
    if predecessor is not None:
        host._sealed_gateway.update({
            "gateway_predecessor_receipt_sha256": sha256_bytes(predecessor.raw),
            "gateway_predecessor_receipt_identity": list(predecessor.identity),
            "gateway_predecessor_archive_identity": None,
        })
    host._active_transaction = transaction
    try:
        host._create_marker(transaction, operation=OS_GATEWAY_PUBLICATION)
    except FileExistsError as exc:
        host._active_transaction = None
        raise GatewayPublicationError("gateway_transaction_incomplete") from exc
    try:
        host._recheck_gateway_preimages(transaction, preparation)
        host._retain_gateway_predecessor(transaction)
        # The canonical audit prerequisite is created strictly from the
        # RETAINED intent, already sealed before any effect.
        host._sealed_gateway[_GATEWAY_AUDIT_AFTER_FIELD] = (
            host._establish_gateway_audit_directory(host._manifest())
        )
        host._sealed_gateway[_MCP_AUDIT_AFTER_FIELD] = (
            host._establish_mcp_auth_audit_directories(transaction)
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
            predecessor_receipt_sha256=request.predecessor_receipt_sha256,
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
    provenance, proves every target postimage and the retained terminal
    receipt, and completes the marker only when all of them hold exactly.
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
    if _MCP_AUDIT_FIELDS <= set(manifest):
        host._sealed_gateway.update({field: manifest[field] for field in _MCP_AUDIT_FIELDS})
    if _GATEWAY_SUCCESSOR_FIELDS <= set(manifest):
        host._sealed_gateway.update({field: manifest[field] for field in _GATEWAY_SUCCESSOR_FIELDS})
        host._predecessor_receipt_archive(manifest, permanent=False)
        host._predecessor_receipt_archive(manifest, permanent=True)
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
    # The manifest does not retain the original terminal bytes or prove that
    # issuance never began. Missing receipt bytes therefore remain UNKNOWN,
    # including a write whose phase acknowledgement was lost. Reconciliation
    # cannot manufacture replacement proof from postimages or a fresh time.
    if not receipt_present:
        raise TransactionEffectUnknown()
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
            predecessor_receipt_sha256=manifest.get("gateway_predecessor_receipt_sha256"),
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
                predecessor_receipt_sha256=args.expected_predecessor_receipt_sha256,
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

    if args.command in A2_CONTROL_RESTORATION_COMMANDS:
        from ops.executive_os.a2_control_restoration import run_command
        return run_command(args, host=host)

    if args.command in {'finite-control-stage', 'finite-control-stage-reconcile',
                        'finite-control-retire', 'finite-control-retire-reconcile'}:
        from ops.executive_os.attended_control_staging import run_command
        return run_command(args, host=host)

    if args.command in {'paid-control-stage','paid-control-stage-reconcile'}:
        from ops.executive_os.paid_control_staging import run_command
        return run_command(args,host=host)

    if args.command in OS_GATEWAY_COMMANDS:
        gateway_host = ProductionGatewayPublicationHost() if host is None else host
        return _run_gateway_command(gateway_host, args, now=current)

    if args.command in CONTROL_COMPONENT_COMMANDS:
        component_host = (
            ProductionControlComponentHost() if host is None else host
        )
        return _run_control_component_command(component_host, args, now=current)

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
