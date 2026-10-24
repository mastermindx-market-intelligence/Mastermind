"""Preserve a quiescent runtime while the existing host acceptance proves a release.

This is an opt-in acceptance owner, not a scheduler or an admission API. Its
v1 descriptor permits one predecessor proof quota recovery. V2 preserves a
terminal dispatch through a prior PASS chain without granting that recovery.
Only passing acceptance publishes an exact queued-root compatibility receipt.
The v5-to-v7 mode retires one installed unstarted supersede_preproof_v1
preparation whose source release has completed the offline v5->v6->v7
transitions: it seals the Root upgrade evidence beside a fresh v7 working
prestate instead of relabelling the selected v5 lineage.
"""
from __future__ import annotations

import argparse
from contextlib import closing, contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys
import tempfile
from typing import Any

_RELEASE = Path(__file__).resolve().parents[2]
if str(_RELEASE) not in sys.path:
    sys.path.insert(0, str(_RELEASE))
from control_plane.fs_security import has_macos_acl

SYSTEM_ROOT = Path("/Library/Application Support/MastermindExecutive")
_MACOS_VAR_ALIAS = Path("/var")
_MACOS_VAR_PHYSICAL = Path("/private/var")
SCHEMA = "mastermind.executive_acceptance_maintenance/v1"
SCHEMA_V2 = "mastermind.executive_acceptance_maintenance/v2"
# Same-schema supersession is separate from the schema-migration V3 contract.
SCHEMA_SUPERSEDE = "mastermind.executive_acceptance_maintenance/supersede_unstarted_v1"
SCHEMA_PREJOB = "mastermind.executive_acceptance_maintenance/supersede_prejob_v1"
SCHEMA_PREPROOF = "mastermind.executive_acceptance_maintenance/supersede_preproof_v1"
# One installed supersede_preproof_v1 release that was itself never started is
# retired by its own explicit selector; it never widens the older selectors.
SCHEMA_UNSTARTED_PREPROOF = (
    "mastermind.executive_acceptance_maintenance/supersede_unstarted_preproof_v1")
# One installed supersede_preproof_v1 preparation whose source release has
# since completed the offline v5->v6->v7 transitions is retired by its own
# explicit selector. The working v7 prestate never relabels the selected v5
# lineage, and this mode never widens the older selectors.
SCHEMA_UNSTARTED_PREPROOF_V5_TO_V7 = (
    "mastermind.executive_acceptance_maintenance/"
    "supersede_unstarted_preproof_v5_to_v7_v1")
_TERMINAL_CARRY_SCHEMAS = {SCHEMA_V2, SCHEMA_SUPERSEDE, SCHEMA_PREJOB, SCHEMA_PREPROOF,
                           SCHEMA_UNSTARTED_PREPROOF, SCHEMA_UNSTARTED_PREPROOF_V5_TO_V7}
_TRUSTED_UID = 0
_TRUSTED_GID = 0
# The artifact inventory can exceed 16 MiB on an otherwise quiescent host.
# Keep every other maintenance document on its existing budget, and apply
# the same finite limit before either publishing or parsing a document.
_MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
_MAX_INVENTORY_BYTES = 64 * 1024 * 1024
# Maximum release nodes on one predecessor path, including a prospective
# successor. Keep recursion finite without rejecting ordinary release history.
_MAX_CARRY_DEPTH = 64
# Selected unstarted releases form a separate sealed lineage; include the
# prospective successor in its finite budget as well.
_MAX_SUPERSEDE_DEPTH = 64
_SHA = re.compile(r"[0-9a-f]{40}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
# The interrupted pre-Job group receipt is written by ``Acceptance`` (acceptance.py,
# ``protected-group-membership.json``); keep these key sets equal to that producer.
_GROUP_RECEIPT_KEYS = frozenset({
    "passed", "effective_members", "attended_worker_membership", "control_definition_sha256",
    "primary_gid_census", "name_members", "uuid_members", "nested_groups",
})
# The pre-``control_definition_sha256`` / pre-``attended_worker_membership`` generation of the same
# receipt (Oct 11, e.g. interrupted release 0123ad5a). It is admitted only on the historical path,
# whose single ``historical=True`` site is ``validate_prior_carry_binding``. That walk also visits a
# candidate's own selected link once at acceptance start (``Maintenance.__init__``); the strict
# ``validate_superseded_binding`` call that follows it, like ``prepare``'s, refuses this form.
_LEGACY_GROUP_RECEIPT_KEYS = frozenset({
    "passed", "effective_members", "primary_gid_census", "name_members", "uuid_members",
    "nested_groups",
})
# ``_attended_worker_membership`` returns None without a ``fabric_attended_probe`` stanza.
_ATTENDED_MEMBERSHIP_KEYS = frozenset({
    "worker_user", "worker_uid", "worker_group", "worker_gid", "provider_home", "worker_id",
    "worker_config_path", "worker_config_sha256", "bindings_sha256", "physical_binding_sha256",
})
_ATTENDED_ACCOUNT = re.compile(r"_mastermind_[a-z0-9_]+")
_WORKER_HOMES = Path("/private/var/db/mastermind-executive/workers")
_TERMINAL ={"COMPLETED", "FAILED", "LOST", "CANCELLED", "RATE_LIMITED"}
_HEARTBEAT = {"last_seen_at_ms", "updated_at_ms", "version"}
_QUOTA_MUTABLE = _HEARTBEAT | {"status", "held_attempt_id", "fence_counter"}
_JOB_MUTABLE = {"status", "assigned_worker_id", "assigned_quota_class",
                "current_attempt_id", "attempt_count", "checkpoint", "result", "updated_at"}
_DESCRIPTOR_KEYS = {"schema_version", "predecessor_sha", "successor_sha", "root_job_id",
                    "root_identity_sha256", "root_event_id", "root_event_sha256",
                    "recovery_job_id", "recovery_attempt_id", "recovery_job_sha256",
                    "worker_id", "quota_class", "baseline_sha256", "backup_sha256",
                    "inventory_sha256", "prior_canary_sha256"}

_DESCRIPTOR_V2_KEYS = (_DESCRIPTOR_KEYS - {
    "recovery_job_id", "recovery_attempt_id", "recovery_job_sha256",
}) | {
    "frozen_base_sha", "prior_descriptor_sha256", "prior_carry_sha256",
    "prior_summary_sha256", "template_proof_job_id", "template_proof_job_sha256",
    "terminal_job_id", "terminal_attempt_id", "terminal_marker_event_id",
    "terminal_marker_event_sha256", "terminal_state_sha256",
    "assignment_seal_sha256", "predecessor_quota_sha256",
}

_DESCRIPTOR_SUPERSEDE_KEYS = _DESCRIPTOR_V2_KEYS | {
    "superseded_unstarted_sha", "superseded_descriptor_sha256",
}
_DESCRIPTOR_PREJOB_KEYS = _DESCRIPTOR_V2_KEYS | {
    "interrupted_prejob_sha", "superseded_descriptor_sha256", "prejob_evidence_sha256",
}
_DESCRIPTOR_PREPROOF_KEYS = _DESCRIPTOR_V2_KEYS | {
    "interrupted_preproof_sha", "superseded_descriptor_sha256", "preproof_evidence_sha256",
}
_DESCRIPTOR_UNSTARTED_PREPROOF_KEYS = _DESCRIPTOR_V2_KEYS | {
    "superseded_unstarted_preproof_sha", "superseded_descriptor_sha256",
}
_DESCRIPTOR_UNSTARTED_PREPROOF_V5_TO_V7_KEYS = _DESCRIPTOR_V2_KEYS | {
    "superseded_unstarted_preproof_sha", "superseded_descriptor_sha256",
    "schema_upgrade_evidence_sha256", "source_control_config_sha256",
}

class MaintenanceError(RuntimeError):
    pass


# Required pre-proof receipts; any other name under an interrupted acceptance dir
# (including host-status.txt or a second probe) refuses with "interrupted acceptance
# is not a pre-proof prefix".
_PREPROOF_CORE_RECEIPTS = frozenset({
    "assignment-root-nonlistability.json",
    "awaiting-canary-status.json",
    "failure-control-status.json",
    "launchd-principals.json",
    "nonexecutive-launchd-before.json",
    "protected-group-membership.json",
    "secret-canary-envelope.json",
    "worker-broker-startup.json",
})
_PREPROOF_PROBE = re.compile(r"control-environment-probe-[1-9][0-9]{0,9}\.json")
_PREPROOF_OPTIONAL_ARTIFACTS = frozenset({"host-service-status-failure.txt"})
_MAX_PREPROOF_FAILURE_ARTIFACT_BYTES = 256 * 1024
#: keep equal to the producer in acceptance.py
_PREPROOF_RECEIPT_KEYS = {
    # Acceptance._assert_worker_cannot_list_assignment_roots
    "assignment-root-nonlistability.json": frozenset({
        "passed", "workspace_root_listing", "run_root_listing"}),
    # Acceptance.start_and_attest_services
    "launchd-principals.json": frozenset({"control", "worker"}),
    # Acceptance.install_secret_canary_receipt
    "secret-canary-envelope.json": frozenset({
        "schema_version", "secret_canary", "control_environment_probe",
        "control_environment_probe_sha256"}),
    # scripts.executive_os_phase1c_env_probe.main (persisted by Acceptance._assert_environment_boundary)
    "control-environment-probe": frozenset({
        "schema_version", "passed", "control_process_identity", "worker_principal",
        "config_sha256", "release_manifest_sha256", "sentinel_value_sha256",
        "process_identity_sha256", "checks"}),
}
#: keep equal to the producer in acceptance.py
_PREPROOF_RECEIPT_VALUE_TYPES = {
    "assignment-root-nonlistability.json": {
        "passed": bool, "workspace_root_listing": str, "run_root_listing": str},
    "launchd-principals.json": {"control": dict, "worker": dict},
    "secret-canary-envelope.json": {
        "schema_version": str, "secret_canary": dict,
        "control_environment_probe": dict, "control_environment_probe_sha256": str},
    "control-environment-probe": {
        "schema_version": str, "passed": bool,
        "control_process_identity": dict, "worker_principal": dict,
        "config_sha256": str, "release_manifest_sha256": str,
        "sentinel_value_sha256": str, "process_identity_sha256": str,
        "checks": dict},
}
# Producer-written schema markers (accepted only when the receipt carries it).
_PREPROOF_SCHEMAS = {
    "secret-canary-envelope.json": "mastermind.executive_secret_canary_envelope/v1",
    "control-environment-probe": "mastermind.executive_control_env_probe/v1",
}

# The v5-to-v7 working bundle keeps the six sealed preparation documents and
# adds exactly two Root-sealed migration documents. Keep these names equal to
# the publication in ``_prepare_v5_to_v7``; the selected v5 lineage keeps its
# own six-document namespace untouched.
_V5_TO_V7_EVIDENCE_NAME = "schema-upgrade-evidence.json"
_V5_TO_V7_SOURCE_CONTROL_NAME = "source-control.json"
_V5_TO_V7_BUNDLE_NAMES = frozenset({
    "descriptor.json", "preparing.json", "baseline.json", "inventory.json",
    "prior-secret-canary.json", "prestate.sqlite3",
    _V5_TO_V7_EVIDENCE_NAME, _V5_TO_V7_SOURCE_CONTROL_NAME,
})
_V5_TO_V7_RESTORE_EVIDENCE_NAME = "acceptance-restore-evidence.json"
_V5_TO_V7_RESTORE_EVIDENCE_SCHEMA = (
    "mastermind.executive_acceptance_maintenance/v5_to_v7_restore_evidence_v1")
#: the four fixed Control receipt names of one v7 acceptance run, in run order
_V5_TO_V7_RESTORE_RECEIPTS = (
    "backup-created.json", "backup-verified.json", "restore-drill.json",
    "restore-applied.json",
)
#: one qualified original backup/manifest identity record produced by the
#: evidence owner; the original address lives only in ``path``
_V5_TO_V7_ORIGIN_RECORD_KEYS = frozenset({
    "path", "device", "inode", "uid", "gid", "mode", "nlink",
    "size", "mtime_ns", "ctime_ns", "sha256"})
#: the exact closed shape of the Root-sealed restore evidence of one accepted
#: v5-to-v7 run; the digest of this document is the schema-specific carry pin
_V5_TO_V7_RESTORE_EVIDENCE_KEYS = frozenset({
    "schema_version", "proof_job_ids", "acceptance_summary_sha256", "receipt_sha256",
    "backup", "origins", "verification", "restore_drill", "current_runtime_database",
    "schema_upgrade_evidence_sha256"})
#: the four receipt digest names inside the restore evidence, in run order
_V5_TO_V7_RECEIPT_DIGEST_KEYS = frozenset(
    name for name in _V5_TO_V7_RESTORE_RECEIPTS)
#: the runtime's own canonical offline custody names; each is checked against
#: the producer in control_plane.executive_backup before any lock is taken
_SERVICE_LOCK = "executive-service.lock"
_SERVICE_MARKER = "executive-service.running"
_SCHEMA_UPGRADE_BARRIER = "executive-schema-upgrade.in-progress.json"

def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()

def _file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def bundle_path(sha: str) -> Path:
    if not isinstance(sha, str) or _SHA.fullmatch(sha) is None:
        raise MaintenanceError("invalid maintenance release")
    return SYSTEM_ROOT / "acceptance-maintenance" / sha

def _identity(info: os.stat_result) -> tuple:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

def _sealed_ancestors(path: Path) -> list:
    ancestors = []
    for parent in path.parents:
        info = parent.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != _TRUSTED_UID
                or info.st_mode & 0o022 or has_macos_acl(parent)):
            raise MaintenanceError("maintenance ancestor is not sealed")
        ancestors.append((parent, _identity(info)))
    return ancestors

def _document_limit(path: Path) -> int:
    return _MAX_INVENTORY_BYTES if path.name == "inventory.json" else _MAX_DOCUMENT_BYTES

def sealed_json(path: Path) -> dict[str, Any]:
    """Read a root-owned immutable document through a stable no-follow FD."""
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise MaintenanceError("maintenance document path is not canonical")
    ancestors = _sealed_ancestors(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != _TRUSTED_UID
                or before.st_nlink != 1 or stat.S_IMODE(before.st_mode) not in {0o400, 0o444}
                or has_macos_acl(path)):
            raise MaintenanceError("maintenance document is not sealed")
        maximum = _document_limit(path)
        if before.st_size > maximum:
            raise MaintenanceError("maintenance document exceeds size limit")
        with os.fdopen(os.dup(fd), "rb") as stream:
            raw = stream.read(maximum + 1)
        if len(raw) > maximum:
            raise MaintenanceError("maintenance document exceeds size limit")
        value = json.loads(raw)
        if (_identity(before) != _identity(os.fstat(fd))
                or _identity(before) != _identity(path.lstat())
                or any(_identity(p.lstat()) != identity for p, identity in ancestors)):
            raise MaintenanceError("maintenance document changed during read")
    finally:
        os.close(fd)
    if not isinstance(value, dict):
        raise MaintenanceError("maintenance document is not an object")
    return value

def descriptor_for(sha: str) -> dict[str, Any] | None:
    path = bundle_path(sha) / "descriptor.json"
    if not path.exists() and not path.is_symlink():
        return None
    value = sealed_json(path)
    schema = value.get("schema_version")
    keys = _DESCRIPTOR_KEYS if schema == SCHEMA else (
        _DESCRIPTOR_V2_KEYS if schema == SCHEMA_V2 else (
            _DESCRIPTOR_SUPERSEDE_KEYS if schema == SCHEMA_SUPERSEDE else (
                _DESCRIPTOR_PREJOB_KEYS if schema == SCHEMA_PREJOB else (
                    _DESCRIPTOR_PREPROOF_KEYS if schema == SCHEMA_PREPROOF else (
                        _DESCRIPTOR_UNSTARTED_PREPROOF_KEYS
                        if schema == SCHEMA_UNSTARTED_PREPROOF else (
                            _DESCRIPTOR_UNSTARTED_PREPROOF_V5_TO_V7_KEYS
                            if schema == SCHEMA_UNSTARTED_PREPROOF_V5_TO_V7 else set()))
            )
        )
    ))
    if not keys or set(value) != keys:
        raise MaintenanceError("maintenance descriptor schema mismatch")
    if (value["successor_sha"] != sha or not isinstance(value["predecessor_sha"], str)
            or _SHA.fullmatch(value["predecessor_sha"]) is None
            or value["predecessor_sha"] == sha):
        raise MaintenanceError("maintenance descriptor release mismatch")
    if schema in _TERMINAL_CARRY_SCHEMAS and (
        not isinstance(value["frozen_base_sha"], str)
        or _SHA.fullmatch(value["frozen_base_sha"]) is None
    ):
        raise MaintenanceError("maintenance frozen base is invalid")
    if schema == SCHEMA_SUPERSEDE and (
        not isinstance(value["superseded_unstarted_sha"], str)
        or _SHA.fullmatch(value["superseded_unstarted_sha"]) is None
        or value["superseded_unstarted_sha"] in {sha, value["predecessor_sha"]}
    ):
        raise MaintenanceError("maintenance superseded release is invalid")
    if schema == SCHEMA_PREJOB and (
        not isinstance(value["interrupted_prejob_sha"], str)
        or _SHA.fullmatch(value["interrupted_prejob_sha"]) is None
        or value["interrupted_prejob_sha"] in {sha, value["predecessor_sha"]}
    ):
        raise MaintenanceError("maintenance interrupted release is invalid")
    if schema == SCHEMA_PREPROOF and (
        not isinstance(value["interrupted_preproof_sha"], str)
        or _SHA.fullmatch(value["interrupted_preproof_sha"]) is None
        or value["interrupted_preproof_sha"] in {sha, value["predecessor_sha"]}
    ):
        raise MaintenanceError("maintenance interrupted release is invalid")
    if schema in {SCHEMA_UNSTARTED_PREPROOF, SCHEMA_UNSTARTED_PREPROOF_V5_TO_V7} and (
        not isinstance(value["superseded_unstarted_preproof_sha"], str)
        or _SHA.fullmatch(value["superseded_unstarted_preproof_sha"]) is None
        or value["superseded_unstarted_preproof_sha"] in {sha, value["predecessor_sha"]}
    ):
        raise MaintenanceError("maintenance superseded release is invalid")
    for key in (key for key in keys if key.endswith("_sha256")):
        if not isinstance(value[key], str) or _DIGEST.fullmatch(value[key]) is None:
            raise MaintenanceError("maintenance descriptor digest is invalid")
    for key in (key for key in keys if key.endswith(("_job_id", "_attempt_id"))
                or key in {"worker_id", "quota_class"}):
        if not isinstance(value[key], str) or not value[key] or len(value[key]) > 128:
            raise MaintenanceError("maintenance descriptor identity is invalid")
    for key in (key for key in keys if key.endswith("_event_id")):
        if type(value[key]) is not int or value[key] <= 0:
            raise MaintenanceError("maintenance descriptor event is invalid")
    return value

def root_identity(job: Any) -> str:
    return digest({k: v for k, v in job.to_dict().items() if k not in _JOB_MUTABLE})

def frozen_binding(job: Any, current: dict, store: Any) -> dict:
    """Return a predecessor base for only the exact PASS-qualified root.

    Every other binding field retains the current service value. Normal
    dispatch, source custody and arming gates continue to own all effects.
    """
    if job.constraints.get("base_sha") == current["base_sha"]:
        return current
    descriptor = descriptor_for(current["base_sha"])
    if descriptor is None or job.job_id != descriptor["root_job_id"]:
        return current
    if root_identity(job) != descriptor["root_identity_sha256"]:
        raise MaintenanceError("preserved root identity drifted")
    _summary, raw = summary_document(current["base_sha"])
    validate_carry_receipt(current["base_sha"], hashlib.sha256(raw).hexdigest())
    with store.read() as conn:
        event = conn.execute("SELECT * FROM events WHERE event_id=?", (descriptor["root_event_id"],)).fetchone()
    if event is None or digest(dict(event)) != descriptor["root_event_sha256"]:
        raise MaintenanceError("preserved root admission event drifted")
    from control_plane.executive_runtime import JobRegistry
    if JobRegistry(store).validated_cycle_block(job.job_id) is not None:
        # A preserved terminal root receives no historical dispatch binding.
        return current
    # CEO-submit admits while the harness is closed. Later global arming
    # enables capacity, but must not promote this root's admitted profile.
    if (job.constraints.get("operator_harness_armed") is not False
            or type(current.get("operator_harness_armed")) is not bool):
        raise MaintenanceError("preserved root harness admission drifted")
    expected = dict(current, base_sha=descriptor.get("frozen_base_sha", descriptor["predecessor_sha"]),
                    operator_harness_armed=False)
    if any(job.constraints.get(k) != v for k, v in expected.items()):
        raise MaintenanceError("preserved root non-base binding drifted")
    return expected

def summary_document(sha: str) -> tuple[dict, bytes]:
    # Reuse the current arming owner's exact control-principal file contract.
    import pwd
    import grp
    from ops.executive_os.autonomy_control import (
        _root_json, validate_acceptance_document, CONTROL_USER, CONTROL_GROUP, RUNTIME_ROOT,
        ArmAdmissionError, HostControlError,
    )
    try:
        value, raw = _root_json(
            RUNTIME_ROOT/"control"/"acceptance"/sha/"acceptance-summary.json",
            modes=frozenset({0o400}), uid=pwd.getpwnam(CONTROL_USER).pw_uid,
            gid=grp.getgrnam(CONTROL_GROUP).gr_gid)
        validate_acceptance_document(value, expected_sha=sha)
        return value, raw
    except (ArmAdmissionError, HostControlError, OSError, KeyError, ValueError) as exc:
        raise MaintenanceError("maintenance acceptance summary is invalid") from exc

def validate_carry_receipt(
    sha: str, summary_sha256: str, *, _seen: frozenset[str] = frozenset()
) -> None:
    if sha in _seen:
        raise MaintenanceError("maintenance carry chain is cyclic")
    if len(_seen) >= _MAX_CARRY_DEPTH:
        raise MaintenanceError("maintenance carry chain is too deep")
    descriptor = descriptor_for(sha)
    if descriptor is None:
        return
    receipt = sealed_json(bundle_path(sha)/"carry-forward.json")
    # The v5-to-v7 carry additionally pins its sealed upgrade evidence and the
    # sealed restore evidence of its own accepted run; no bare PASS receipt is
    # ever admitted for that schema.
    expected_keys = {"schema_version", "passed", "descriptor_sha256",
                     "acceptance_summary_sha256", "baseline_preserved"}
    if descriptor["schema_version"] == SCHEMA_UNSTARTED_PREPROOF_V5_TO_V7:
        expected_keys |= {"schema_upgrade_evidence_sha256",
                          "acceptance_restore_evidence_sha256"}
    if (set(receipt) != expected_keys
            or receipt["schema_version"] != descriptor["schema_version"] or receipt["passed"] is not True
            or receipt["baseline_preserved"] is not True
            or receipt["descriptor_sha256"] != digest(descriptor)
            or receipt["acceptance_summary_sha256"] != summary_sha256):
        raise MaintenanceError("preserved root has no matching maintenance PASS receipt")
    if descriptor["schema_version"] == SCHEMA_UNSTARTED_PREPROOF_V5_TO_V7 and (
            receipt["schema_upgrade_evidence_sha256"] != descriptor["schema_upgrade_evidence_sha256"]
            or digest(sealed_json(bundle_path(sha)/_V5_TO_V7_EVIDENCE_NAME))
            != descriptor["schema_upgrade_evidence_sha256"]
            or digest(sealed_json(bundle_path(sha)/_V5_TO_V7_RESTORE_EVIDENCE_NAME))
            != receipt["acceptance_restore_evidence_sha256"]):
        raise MaintenanceError("preserved root has no matching maintenance PASS receipt")
    if descriptor["schema_version"] == SCHEMA_UNSTARTED_PREPROOF_V5_TO_V7:
        # A Root self-hash re-seal is never a carry: before any future route may
        # treat this link as its PASS predecessor, the accepted run is
        # re-derived from its own sealed history through the retained owner.
        _validate_v5_to_v7_carry_history(descriptor, receipt, summary_sha256)
    validate_prior_carry_binding(descriptor, _seen=_seen)


def _validate_v5_to_v7_carry_history(descriptor: dict, receipt: dict,
                                     summary_sha256: str) -> None:
    """Re-derive one accepted v5-to-v7 run from its own sealed history.

    Reached by every future carry route through ``validate_carry_receipt``.
    The genuine sealed schema PASS carry, the exact digest of the real accepted
    summary and the pinned restore evidence are gated first; then the exact
    closed shapes, the four raw receipt hashes, the actual qualified backup
    origins, the original tool release/material/source-control pins, the
    admitted instance marker and the proof lineage are re-proven before the
    retained history owner re-derives the immutable migration chain, the
    qualified proof backup and its verification and drill. The current live
    database is never compared with the initial migration target, no current
    database, quiescence, lock or marker state is required, and the
    finish-observed database identity stays exactly the historical observation
    it was sealed as. The unchanged selected/deeper v5 walk still runs in the
    ``historical`` mode carried by the caller's chain validation.
    """
    if (not isinstance(receipt, dict) or receipt.get("passed") is not True
            or receipt.get("baseline_preserved") is not True
            or receipt.get("acceptance_summary_sha256") != summary_sha256):
        raise MaintenanceError("preserved root has no matching maintenance PASS receipt")
    successor = descriptor["successor_sha"]
    bundle = bundle_path(successor)
    if (sealed_json(bundle/"run-started.json")
            != {"schema_version": descriptor["schema_version"],
                "descriptor_sha256": digest(descriptor)}):
        raise MaintenanceError("preserved root has no matching maintenance PASS receipt")
    _summary, summary_raw = summary_document(successor)
    if hashlib.sha256(summary_raw).hexdigest() != summary_sha256:
        raise MaintenanceError("preserved root has no matching maintenance PASS receipt")
    material = sealed_json(bundle/_V5_TO_V7_EVIDENCE_NAME)
    source_control = sealed_bytes(bundle/_V5_TO_V7_SOURCE_CONTROL_NAME, _MAX_DOCUMENT_BYTES)
    if (digest(material) != descriptor["schema_upgrade_evidence_sha256"]
            or hashlib.sha256(source_control).hexdigest()
            != descriptor["source_control_config_sha256"]):
        raise MaintenanceError("preserved root has no matching maintenance PASS receipt")
    runtime_root, backup_root = _validate_v5_to_v7_material(material)
    evidence = sealed_json(bundle/_V5_TO_V7_RESTORE_EVIDENCE_NAME)
    if set(evidence) != set(_V5_TO_V7_RESTORE_EVIDENCE_KEYS):
        raise MaintenanceError("preserved root has no matching maintenance PASS receipt")
    if (evidence["schema_version"] != _V5_TO_V7_RESTORE_EVIDENCE_SCHEMA
            or evidence["schema_upgrade_evidence_sha256"]
            != descriptor["schema_upgrade_evidence_sha256"]
            or evidence["acceptance_summary_sha256"] != summary_sha256
            or set(evidence["receipt_sha256"]) != set(_V5_TO_V7_RECEIPT_DIGEST_KEYS)
            or any(not isinstance(digest_value, str)
                   or _DIGEST.fullmatch(digest_value) is None
                   for digest_value in evidence["receipt_sha256"].values())):
        raise MaintenanceError("preserved root has no matching maintenance PASS receipt")
    proof_ids = evidence["proof_job_ids"]
    if (not isinstance(proof_ids, list) or len(proof_ids) != 2
            or len(set(proof_ids)) != 2
            or any(not isinstance(job_id, str) or not job_id or len(job_id) > 128
                   for job_id in proof_ids)):
        raise MaintenanceError("preserved root has no matching maintenance PASS receipt")
    if [_summary.get('success_job_id'), _summary.get('interrupted_requeued_job_id')] != proof_ids:
        raise MaintenanceError("maintenance PASS summary proof jobs drifted")
    backup = evidence["backup"]
    if (not isinstance(backup, dict)
            or set(backup) != {"name", "database_sha256", "manifest_sha256"}
            or not isinstance(backup["name"], str)
            or backup["name"] != Path(backup["name"]).name
            or not backup["name"] or "/" in backup["name"] or backup["name"] in {".", ".."}
            or not isinstance(backup["database_sha256"], str)
            or _DIGEST.fullmatch(backup["database_sha256"]) is None
            or not isinstance(backup["manifest_sha256"], str)
            or _DIGEST.fullmatch(backup["manifest_sha256"]) is None):
        raise MaintenanceError("preserved root has no matching maintenance PASS receipt")
    if not isinstance(evidence["origins"], dict) or set(evidence["origins"]) != {
            "database", "manifest"}:
        raise MaintenanceError("preserved root has no matching maintenance PASS receipt")
    origins = {key: _v5_to_v7_origin_record(evidence["origins"][key])
               for key in ("database", "manifest")}
    if (origins["database"]["sha256"] != backup["database_sha256"]
            or origins["manifest"]["sha256"] != backup["manifest_sha256"]
            or Path(origins["database"]["path"]).name != backup["name"]
            or Path(origins["database"]["path"]).parent != backup_root
            or Path(origins["manifest"]["path"]).parent != backup_root
            or not isinstance(evidence["verification"], dict)
            or not isinstance(evidence["restore_drill"], dict)):
        raise MaintenanceError("preserved root has no matching maintenance PASS receipt")
    observed = evidence["current_runtime_database"]
    if (not isinstance(observed, dict)
            or set(observed) != {"path", "device", "inode"}
            or not isinstance(observed["path"], str)
            or observed["path"] != os.fspath(
                runtime_root/"data/control_plane/executive.sqlite3")
            or type(observed["device"]) is not int or observed["device"] < 0
            or type(observed["inode"]) is not int or observed["inode"] <= 0):
        raise MaintenanceError("preserved root has no matching maintenance PASS receipt")
    # The four raw receipt preimages still hash exactly to the pinned values.
    import pwd
    import grp
    from ops.executive_os.autonomy_control import (
        RUNTIME_ROOT, CONTROL_USER, CONTROL_GROUP, _root_json, HostControlError,
    )
    uid = pwd.getpwnam(CONTROL_USER).pw_uid
    gid = grp.getgrnam(CONTROL_GROUP).gr_gid
    receipts = _v7_restore_receipts(successor)
    for name in _V5_TO_V7_RESTORE_RECEIPTS:
        if receipts[name+':sha256'] != evidence['receipt_sha256'][name]:
            raise MaintenanceError("preserved root has no matching maintenance PASS receipt")
    created, verified, drill, applied = [receipts[name] for name in _V5_TO_V7_RESTORE_RECEIPTS]
    if _validate_v7_restore_receipts(created, verified, drill, applied,
            backup_root=backup_root,
            database=runtime_root/'data/control_plane/executive.sqlite3') != backup['name']:
        raise MaintenanceError("qualified proof backup origin drifted")
    if (os.fspath(_runtime_owner_path(Path(created['database_path']))) != origins['database']['path']
            or os.fspath(_runtime_owner_path(Path(created['manifest_path']))) != origins['manifest']['path']):
        raise MaintenanceError("qualified proof backup receipt addresses drifted")
    normalized_verified = _json_data(verified)
    for key in ('database_path', 'manifest_path'):
        normalized_verified[key] = os.fspath(_runtime_owner_path(Path(verified[key])))
    if (normalized_verified != evidence['verification']
            or _json_data(drill) != evidence['restore_drill']):
        raise MaintenanceError("retained proof receipts differ from their sealed semantics")
    _qualified_backup_manifest(created, backup_root, uid, gid)
    with _RootConfig() as current_config:
        configured_root = _canonical_root_path(current_config.value.get("runtime_root"))
    if _runtime_owner_path(configured_root) != runtime_root:
        raise MaintenanceError("preserved root has no matching maintenance PASS receipt")
    with _evidence_owner().open_retained_v5_to_v7_evidence(
            runtime_root, _v5_to_v7_tool_release(material),
            pinned_material=material) as retained:
        if _json_data(retained.material) != material:
            raise MaintenanceError("preserved v5-to-v7 history is not the sealed original")
        verified_copy = retained.verify_v7_acceptance_backup(
            backup["name"], backup["database_sha256"], backup["manifest_sha256"])
        derived = getattr(verified_copy, "origin_identities", None)
        if not isinstance(derived, dict) or set(derived) != {"database", "manifest"}:
            raise MaintenanceError("qualified proof backup origin is invalid")
        if {key: _v5_to_v7_origin_record(derived[key])
                for key in ("database", "manifest")} != origins:
            raise MaintenanceError("qualified proof backup origin drifted from the sealed run")
        verification = dict(_json_data(verified_copy.verification))
        # Only the two explicit copy-address fields are renormalized to the
        # qualified original addresses; every deterministic field compares.
        verification["database_path"] = origins["database"]["path"]
        verification["manifest_path"] = origins["manifest"]["path"]
        if (_json_data(verification) != _json_data(evidence["verification"])
                or _json_data(verified_copy.restore_drill)
                != _json_data(evidence["restore_drill"])):
            raise MaintenanceError("qualified proof backup verification drifted")
        baseline = sealed_json(bundle/"baseline.json")
        if digest(baseline) != descriptor["baseline_sha256"]:
            raise MaintenanceError("preserved root has no matching maintenance PASS receipt")
        _verify_restore_physical(applied, Path(verified_copy.database))
        verify_preserved(baseline, snapshot(Path(verified_copy.database), immutable=True),
                         descriptor, proof_ids)
        retained.check()


def validate_prior_carry_binding(descriptor: dict, *, _seen: frozenset[str] = frozenset()) -> None:
    if descriptor["schema_version"] in _TERMINAL_CARRY_SCHEMAS:
        prior, _summary, material = prior_carry_material(
            descriptor["predecessor_sha"], _seen=_seen | {descriptor["successor_sha"]}
        )
        if any(descriptor[key] != material[key] for key in material):
            raise MaintenanceError("maintenance predecessor carry changed")
        if any(descriptor[key] != prior[key] for key in
               ("root_job_id", "root_identity_sha256", "root_event_id", "root_event_sha256")):
            raise MaintenanceError("maintenance predecessor root binding changed")

    if descriptor["schema_version"] in {SCHEMA_SUPERSEDE, SCHEMA_PREJOB, SCHEMA_PREPROOF,
                                        SCHEMA_UNSTARTED_PREPROOF,
                                        SCHEMA_UNSTARTED_PREPROOF_V5_TO_V7}:
        validate_superseded_binding(descriptor, historical=True)


def prior_carry_material(sha: str, *, _seen: frozenset[str] = frozenset()) -> tuple[dict, dict, dict]:
    prior = descriptor_for(sha)
    if prior is None:
        raise MaintenanceError("terminal carry requires a prior preservation descriptor")
    summary, raw = summary_document(sha)
    summary_digest = hashlib.sha256(raw).hexdigest()
    validate_carry_receipt(sha, summary_digest, _seen=_seen)
    carry = sealed_json(bundle_path(sha)/"carry-forward.json")
    return prior, summary, {
        "prior_descriptor_sha256": digest(prior),
        "prior_carry_sha256": digest(carry),
        "prior_summary_sha256": summary_digest,
        "frozen_base_sha": prior.get("frozen_base_sha", prior["predecessor_sha"]),
    }


def recovery_permitted(job: Any, attempt_id: str, sha: str, worker_id: str, quota_class: str) -> bool:
    descriptor = descriptor_for(sha)
    if descriptor is None or descriptor["schema_version"] != SCHEMA:
        return False
    active = sealed_json(bundle_path(sha) / "run-started.json")
    return bool(active == {"schema_version": SCHEMA, "descriptor_sha256": digest(descriptor)}
                and not ((bundle_path(sha) / "carry-forward.json").exists()
                         or (bundle_path(sha) / "carry-forward.json").is_symlink())
                and descriptor["recovery_job_id"] == job.job_id
                and descriptor["recovery_attempt_id"] == attempt_id
                and descriptor["worker_id"] == worker_id
                and descriptor["quota_class"] == quota_class
                and digest(job.to_dict()) == descriptor["recovery_job_sha256"]
                and job.constraints.get("base_sha") == descriptor["predecessor_sha"])

def snapshot(database: Path, *, immutable: bool = False) -> dict:
    uri = database.as_uri() + "?mode=ro" + ("&immutable=1" if immutable else "")
    with closing(sqlite3.connect(uri, uri=True)) as conn, conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN")
        if conn.execute("PRAGMA quick_check").fetchall()[0][0] != "ok" or conn.execute("PRAGMA foreign_key_check").fetchall():
            raise MaintenanceError("runtime integrity check failed")
        schema = [list(row) for row in conn.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name")]
        tables = {}
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            name = row[0]
            if re.fullmatch(r"[a-z_]+", name) is None:
                raise MaintenanceError("unexpected runtime table name")
            # Canonical row sorting also covers optional schema-owned tables.
            tables[name] = sorted(
                (dict(item) for item in conn.execute('SELECT * FROM "' + name + '"')),
                key=lambda item: json.dumps(item, sort_keys=True, allow_nan=False))
        return {"schema": schema, "tables": tables}

def _key(row: dict, table: str) -> Any:
    keys = {"jobs": ("job_id",), "attempts": ("attempt_id",), "events": ("event_id",),
            "workers": ("worker_id",), "worker_quota_classes": ("worker_id", "quota_class"),
            "harness_session_epochs": ("session_epoch_id",),
            "process_generations": ("process_generation_id",)}
    return tuple(row[k] for k in keys[table])

def _validate_recovery_event(event: dict, job_id: str, attempt_id: str, descriptor: dict) -> None:
    from control_plane.executive_runtime import WorkerRegistry, RuntimeProofError
    try:
        WorkerRegistry._validate_proof_recovery_receipt(
            json.loads(event["payload_json"]), job_id=job_id, lost_attempt_id=attempt_id,
            worker_id=descriptor["worker_id"], quota_class=descriptor["quota_class"])
    except (RuntimeProofError, ValueError, KeyError, TypeError) as exc:
        raise MaintenanceError("maintenance recovery receipt is invalid") from exc
    if (event["aggregate_type"] != "quota_class"
            or event["aggregate_id"] != descriptor["worker_id"]+":"+descriptor["quota_class"]
            or event["actor"] != "executive-control-service"
            or event["worker_id"] != descriptor["worker_id"] or event["quota_class"] != descriptor["quota_class"]
            or event["command_id"] != "proof-capacity-recover:"+job_id+":"+attempt_id):
        raise MaintenanceError("maintenance recovery event identity mismatch")

def verify_preserved(before: dict, after: dict, descriptor: dict, proof_ids: list[str]) -> None:
    """All old history stays exact; additions must be the observed proof lineage."""
    if before["schema"] != after["schema"] or set(before["tables"]) != set(after["tables"]):
        raise MaintenanceError("runtime schema changed during acceptance")
    bt, at = before["tables"], after["tables"]
    new = {}
    mutable = {"workers": _HEARTBEAT, "worker_quota_classes": _QUOTA_MUTABLE}
    appendable = {"jobs", "attempts", "events", "harness_session_epochs", "process_generations"}
    for table in bt:
        if table not in appendable | set(mutable):
            if digest(bt[table]) != digest(at[table]):
                raise MaintenanceError("unrelated runtime table changed")
            continue
        old = {_key(row, table): row for row in bt[table]}
        now = {_key(row, table): row for row in at[table]}
        for key, row in old.items():
            if key not in now or {k:v for k,v in row.items() if k not in mutable.get(table,set())} != {
                    k:v for k,v in now.get(key,{}).items() if k not in mutable.get(table,set())}:
                raise MaintenanceError("baseline runtime row changed: " + table)
        new[table] = [row for key,row in now.items() if key not in old]
        if table in mutable and new[table]:
            raise MaintenanceError("maintenance unexpectedly registered capacity")
    if len(proof_ids) != 2 or len(set(proof_ids)) != 2 or {r["job_id"] for r in new["jobs"]} != set(proof_ids):
        raise MaintenanceError("maintenance proof job lineage mismatch")
    if any(r["status"] != "COMPLETED" or r["orchestration_role"] is not None for r in new["jobs"]):
        raise MaintenanceError("maintenance proof did not complete")
    v2 = descriptor["schema_version"] in _TERMINAL_CARRY_SCHEMAS
    template_id = descriptor["template_proof_job_id" if v2 else "recovery_job_id"]
    predecessor_proof = next(r for r in bt["jobs"] if r["job_id"] == template_id)
    proof_fields = ("objective", "department", "priority", "authority_level", "attempt_limit",
                    "requested_authorities_json", "allowed_write_paths_json", "validation_commands_json")
    for job in new["jobs"]:
        constraints = json.loads(predecessor_proof["constraints_json"])
        constraints["base_sha"] = descriptor["successor_sha"]
        if (any(job[field] != predecessor_proof[field] for field in proof_fields)
                or json.loads(job["constraints_json"]) != constraints):
            raise MaintenanceError("maintenance job is not the fixed successor proof")
    attempts = {r["attempt_id"]:r for r in new["attempts"]}
    if len(attempts) != 3 or any(
            r["job_id"] not in proof_ids or r["status"] not in _TERMINAL
            or r["worker_id"] != descriptor["worker_id"] or r["quota_class"] != descriptor["quota_class"]
            for r in attempts.values()):
        raise MaintenanceError("maintenance attempt lineage mismatch")
    for job_id, statuses in zip(proof_ids, [("COMPLETED",), ("LOST", "COMPLETED")]):
        lineage = sorted((r for r in attempts.values() if r["job_id"] == job_id),
                         key=lambda r: r["attempt_number"])
        job = next(r for r in new["jobs"] if r["job_id"] == job_id)
        if (tuple(r["status"] for r in lineage) != statuses
                or [r["attempt_number"] for r in lineage] != list(range(1,len(statuses)+1))
                or job["attempt_count"] != len(statuses)
                or job["current_attempt_id"] != lineage[-1]["attempt_id"]):
            raise MaintenanceError("maintenance proof topology mismatch")
    if new["harness_session_epochs"] or new["process_generations"]:
        raise MaintenanceError("sealed proof unexpectedly created operator harness history")
    recovery = []
    fences = {}
    event_families = {
        "JOB_CREATED", "JOB_CLAIMED", "ATTEMPT_PROCESS_RECORDED", "ATTEMPT_RUNNING",
        "ATTEMPT_HEARTBEAT", "JOB_CHECKPOINTED", "ATTEMPT_PROCESS_EXITED", "JOB_COMPLETED",
        "ATTEMPT_ADOPTED", "ATTEMPT_LOST", "JOB_REQUEUED", "PROOF_WORKSPACE_ROTATED",
        "PROOF_CAPACITY_RECOVERED",
    }
    for event in new["events"]:
        if event["event_type"] not in event_families:
            raise MaintenanceError("event outside acceptance event families")
        if (not v2 and event["event_type"] == "PROOF_CAPACITY_RECOVERED"
                and event["job_id"] == descriptor["recovery_job_id"]
                and event["attempt_id"] == descriptor["recovery_attempt_id"]
                and event["worker_id"] == descriptor["worker_id"] and event["quota_class"] == descriptor["quota_class"]):
            _validate_recovery_event(event,descriptor["recovery_job_id"],
                                     descriptor["recovery_attempt_id"],descriptor)
            recovery.append(event)
            continue
        if event["job_id"] not in proof_ids or (event["attempt_id"] is not None and event["attempt_id"] not in attempts):
            raise MaintenanceError("event outside maintenance proof lineage")
        if event["event_type"] in {"JOB_CLAIMED", "ATTEMPT_ADOPTED"}:
            if event["worker_id"] != descriptor["worker_id"] or event["quota_class"] != descriptor["quota_class"]:
                raise MaintenanceError("maintenance fence names foreign capacity")
            try:
                fence = json.loads(event["payload_json"])["fence_generation"]
            except (ValueError, KeyError, TypeError) as exc:
                raise MaintenanceError("maintenance fence event is malformed") from exc
            if type(fence) is not int or fence <= 0:
                raise MaintenanceError("maintenance fence event is invalid")
            fences.setdefault((event["worker_id"],event["quota_class"]), []).append(
                (event["event_id"], fence))
    if sum(e["event_type"] == "PROOF_CAPACITY_RECOVERED" for e in new["events"]) != (1 if v2 else 2):
        raise MaintenanceError("maintenance recovery event count mismatch")
    if len(recovery) != (0 if v2 else 1):
        raise MaintenanceError("maintenance predecessor recovery is not unique")
    lost = next(r for r in attempts.values() if r["job_id"] == proof_ids[1] and r["status"] == "LOST")
    current_recoveries = [r for r in new["events"] if r["event_type"] == "PROOF_CAPACITY_RECOVERED"
                          and r["job_id"] == proof_ids[1] and r["attempt_id"] == lost["attempt_id"]]
    if len(current_recoveries) != 1:
        raise MaintenanceError("maintenance current proof recovery is not unique")
    _validate_recovery_event(current_recoveries[0],proof_ids[1],lost["attempt_id"],descriptor)
    for attempt in attempts.values():
        owned = [e for e in new["events"] if e["attempt_id"] == attempt["attempt_id"]]
        claims = [e for e in owned if e["event_type"] == "JOB_CLAIMED"]
        adoptions = [e for e in owned if e["event_type"] == "ATTEMPT_ADOPTED"]
        if (len(claims) != 1 or len(adoptions) > 1
                or (adoptions and attempt["attempt_id"] != lost["attempt_id"])):
            raise MaintenanceError("maintenance attempt fence lineage mismatch")
        last = max(claims+adoptions,key=lambda e:e["event_id"])
        if attempt["fence_generation"] != json.loads(last["payload_json"])["fence_generation"]:
            raise MaintenanceError("maintenance final attempt fence mismatch")
    old_quotas = {_key(r,"worker_quota_classes"): r for r in bt["worker_quota_classes"]}
    for row in at["worker_quota_classes"]:
        key = _key(row,"worker_quota_classes")
        old = old_quotas[key]
        sequence = [f for _,f in sorted(fences.get(key, []))]
        if sequence != list(range(old["fence_counter"]+1, old["fence_counter"]+len(sequence)+1)):
            raise MaintenanceError("maintenance quota fence chain has a gap")
        target = key == (descriptor["worker_id"],descriptor["quota_class"])
        expected_status = "AVAILABLE" if sequence or target else old["status"]
        if (row["fence_counter"] != old["fence_counter"]+len(sequence)
                or row["held_attempt_id"] is not None or row["status"] != expected_status):
            raise MaintenanceError("maintenance final quota state mismatch")

def inventory(roots: list[Path]) -> dict:
    """Preserve existing artifacts, including link text without following links."""
    result = {}
    for root in roots:
        root = root.resolve(strict=True)
        if not root.exists():
            raise MaintenanceError("maintenance artifact root is absent")
        for path in [root, *sorted(root.rglob("*"))]:
            info = path.lstat()
            if stat.S_ISDIR(info.st_mode):
                content = {"directory": True, "device":info.st_dev, "inode":info.st_ino}
            elif stat.S_ISLNK(info.st_mode):
                content = {"link": os.readlink(path)}
            elif stat.S_ISREG(info.st_mode):
                content = {"sha256": _file_digest(path)}
            else:
                raise MaintenanceError("special file in preserved artifact tree")
            if has_macos_acl(path, expected_identity=info, allow_symlink=stat.S_ISLNK(info.st_mode)):
                raise MaintenanceError("preserved artifact has an ACL")
            if not stat.S_ISDIR(info.st_mode):
                content["nlink"] = info.st_nlink
            result[str(path)] = {"uid":info.st_uid, "gid":info.st_gid,
                                 "mode":stat.S_IMODE(info.st_mode), **content}
    return result

def verify_inventory(baseline: dict) -> None:
    for name, expected in baseline.items():
        path = Path(name)
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            content = {"directory":True,"device":info.st_dev,"inode":info.st_ino}
        elif stat.S_ISLNK(info.st_mode):
            content = {"link":os.readlink(path)}
        elif stat.S_ISREG(info.st_mode):
            content = {"sha256":_file_digest(path)}
        else:
            raise MaintenanceError("preserved artifact became a special file")
        if has_macos_acl(path, expected_identity=info, allow_symlink=stat.S_ISLNK(info.st_mode)):
            raise MaintenanceError("preserved artifact gained an ACL")
        if not stat.S_ISDIR(info.st_mode):
            content["nlink"] = info.st_nlink
        if {"uid":info.st_uid,"gid":info.st_gid,"mode":stat.S_IMODE(info.st_mode),**content} != expected:
            raise MaintenanceError("preserved artifact changed")

def write_sealed(path: Path, value: dict, *, public: bool = False) -> None:
    data = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+"\n").encode()
    if len(data) > _document_limit(path):
        raise MaintenanceError("maintenance document exceeds size limit")
    fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(os.dup(fd),"wb") as stream:
            stream.write(data)
            stream.flush()
        os.fchmod(fd, 0o444 if public else 0o400)
        os.fsync(fd)
    finally:
        os.close(fd)
    parent = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)

def write_sealed_bytes(path: Path, raw: bytes) -> None:
    """Seal one exact raw preimage; JSON whitespace is never rewritten."""
    if not isinstance(raw, bytes) or len(raw) > _document_limit(path):
        raise MaintenanceError("maintenance document exceeds size limit")
    fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(os.dup(fd),"wb") as stream:
            stream.write(raw)
            stream.flush()
        os.fchmod(fd, 0o400)
        os.fsync(fd)
    finally:
        os.close(fd)
    parent = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)

def sealed_bytes(path: Path, limit: int) -> bytes:
    """Read exact sealed raw bytes through a stable no-follow FD."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != _TRUSTED_UID
                or info.st_gid != _TRUSTED_GID or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o400 or info.st_size > limit
                or has_macos_acl(path)):
            raise MaintenanceError("maintenance document is not sealed")
        chunks = []
        while sum(len(chunk) for chunk in chunks) <= limit:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        raw = b"".join(chunks)
        if len(raw) > limit or os.read(fd, 1):
            raise MaintenanceError("maintenance document exceeds size limit")
        if (_identity(info) != _identity(os.fstat(fd))
                or _identity(info) != _identity(path.lstat())):
            raise MaintenanceError("maintenance document changed during read")
    finally:
        os.close(fd)
    return raw

def _json_data(value: Any) -> Any:
    """Canonical JSON roundtrip; an unknown type raises instead of coercing."""
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


def _canonical_root_path(value: Any) -> Path:
    """One absolute, dot-free, canonical-looking configured root path."""
    if (not isinstance(value, str) or not value
            or not Path(value).is_absolute() or ".." in Path(value).parts
            or "." in Path(value).parts):
        raise MaintenanceError("maintenance configured root is not absolute canonical data")
    return Path(value)


def _validate_v5_to_v7_material(material: Any) -> tuple[Path, Path]:
    """Validate the frozen stable evidence chain and return its actual roots.

    The stable record is exactly the immutable origin chain, the actual runtime
    and backup roots, the real Control identity and the original migration tool
    release. The mutable whole-config bytes, the working proof digests and the
    owner's TEMP paths are deliberately absent from it and are never required
    here, so a re-derived chain in a later phase can only equal the sealed
    original by being the same migration evidence.
    """
    owner = _evidence_owner()
    spent_ctime = (isinstance(material, dict)
                   and material.get("schema_version") == owner.SPENT_CTIME_MATERIAL_SCHEMA_VERSION)
    recovered = (isinstance(material, dict)
                 and material.get("schema_version") == owner.RECOVERED_MATERIAL_SCHEMA_VERSION)
    if (not isinstance(material, dict)
            or set(material) != {"schema_version", "phase", "host", "origin_records", "chain"}
            or material["schema_version"] not in {owner.MATERIAL_SCHEMA_VERSION,
                                                  owner.RECOVERED_MATERIAL_SCHEMA_VERSION,
                                                  owner.SPENT_CTIME_MATERIAL_SCHEMA_VERSION}
            or material["phase"] != owner.EVIDENCE_PHASE_INITIAL
            or not isinstance(material["origin_records"], list)
            or len(material["origin_records"]) != (16 if spent_ctime else 14 if recovered else 12)):
        raise MaintenanceError("schema upgrade evidence material is malformed")
    host = material["host"]
    if (not isinstance(host, dict)
            or set(host) != {"runtime_root", "backup_root", "control_uid", "control_gid"}):
        raise MaintenanceError("schema upgrade evidence host is malformed")
    runtime_root = _canonical_root_path(host["runtime_root"])
    backup_root = _canonical_root_path(host["backup_root"])
    for key in ("control_uid", "control_gid"):
        if type(host[key]) is not int or host[key] <= 0:
            raise MaintenanceError("schema upgrade evidence material is malformed")
    chain = material.get("chain")
    if not isinstance(chain, dict) or not chain:
        raise MaintenanceError("schema upgrade evidence material is malformed")
    release = chain.get("tool_release")
    if (not isinstance(release, dict)
            or set(release) != {"root", "sha", "tree_sha", "manifest_sha256"}
            or not isinstance(release["root"], str) or not release["root"]
            or not isinstance(release["sha"], str) or _SHA.fullmatch(release["sha"]) is None
            or not isinstance(release["tree_sha"], str)
            or _SHA.fullmatch(release["tree_sha"]) is None
            or not isinstance(release["manifest_sha256"], str)
            or _DIGEST.fullmatch(release["manifest_sha256"]) is None):
        raise MaintenanceError("schema upgrade evidence tool release is malformed")
    return runtime_root, backup_root


def _bind_pre_census_selected(evidence, selected_sha, selected, source_control):
    """Join recovery's held Root attestation to the real selected lineage."""
    owner = _evidence_owner()
    if evidence.material["schema_version"] not in {owner.RECOVERED_MATERIAL_SCHEMA_VERSION,
                                                  owner.SPENT_CTIME_MATERIAL_SCHEMA_VERSION}:
        return
    qualification = evidence.pre_census_qualification
    raw = (bundle_path(selected_sha)/"descriptor.json").read_bytes()
    expected = dict(sha=selected_sha,
        descriptor_raw_sha256=hashlib.sha256(raw).hexdigest(),
        descriptor_sha256=digest(selected), source_backup_sha256=selected["backup_sha256"],
        baseline_sha256=selected["baseline_sha256"], inventory_sha256=selected["inventory_sha256"],
        prior_canary_sha256=selected["prior_canary_sha256"])
    if (not isinstance(qualification, dict)
            or qualification["selected_source"] != expected
            or qualification["source_control_config"]["sha256"]
            != hashlib.sha256(source_control).hexdigest()):
        raise MaintenanceError("recovery qualification selected source or control preimage differs")


def _runtime_owner_path(path: Path, guard=None) -> Path:
    """Only the incumbent fixed /var alias for Control runtime/backup paths."""
    path = _canonical_root_path(os.fspath(path))
    logical = _MACOS_VAR_ALIAS / "db/mastermind-executive"
    physical = _MACOS_VAR_PHYSICAL / "db/mastermind-executive"
    if sys.platform == "darwin" and (path == logical or logical in path.parents
                                     or path == physical or physical in path.parents):
        info = _MACOS_VAR_ALIAS.lstat()
        target = os.readlink(_MACOS_VAR_ALIAS)
        if (not stat.S_ISLNK(info.st_mode) or info.st_uid != _TRUSTED_UID
                or target not in ("private/var", os.fspath(_MACOS_VAR_PHYSICAL))):
            raise MaintenanceError("Runtime /var alias is not trusted")
        observation = (_identity(info), target)
        if guard is not None:
            if guard.aliases.get(_MACOS_VAR_ALIAS, observation) != observation:
                raise MaintenanceError("retained Runtime alias changed")
            guard.aliases[_MACOS_VAR_ALIAS] = observation
        if path == logical or logical in path.parents:
            return physical / path.relative_to(logical)
    return path


def _v5_to_v7_tool_release(material: Any) -> str:
    """The ORIGINAL migration tool release sha pinned inside the material.

    This is the release whose retained manifest and source the genuine helper
    validates; it is never the working descriptor's proof successor.
    """
    _validate_v5_to_v7_material(material)
    return material["chain"]["tool_release"]["sha"]


def _v5_to_v7_origin_record(record: Any) -> dict:
    """One closed original identity record; ``mode`` is a permission int."""
    if not isinstance(record, dict) or set(record) != set(_V5_TO_V7_ORIGIN_RECORD_KEYS):
        raise MaintenanceError("qualified proof backup origin is invalid")
    if (not isinstance(record["path"], str)
            or not Path(record["path"]).is_absolute()
            or ".." in Path(record["path"]).parts
            or type(record["device"]) is not int or type(record["inode"]) is not int
            or record["device"] < 0 or record["inode"] <= 0
            or type(record["uid"]) is not int or type(record["gid"]) is not int
            or record["uid"] < 0 or record["gid"] < 0
            or type(record["mode"]) is not int or not 0 <= record["mode"] <= 0o7777
            or type(record["nlink"]) is not int or record["nlink"] != 1
            or type(record["size"]) is not int or record["size"] < 0
            or type(record["mtime_ns"]) is not int or type(record["ctime_ns"]) is not int
            or not isinstance(record["sha256"], str)
            or _DIGEST.fullmatch(record["sha256"]) is None):
        raise MaintenanceError("qualified proof backup origin is invalid")
    return dict(record)


class _RootConfig:
    """The fixed Root control config held through a stable no-follow identity.

    The exact ``SYSTEM_ROOT/config/control.json`` preimage is read through the
    existing guarded control-principal owner (Root-owned, Control-group,
    mode 0440, single link, no ACL) and its held descriptor, named identity,
    sealed ancestors and raw bytes stay pinned so every final edge — preflight
    return, the atomic rename and the runmarker — re-proves the same preimage.
    """

    def __init__(self):
        import grp
        from ops.executive_os.autonomy_control import (
            CONTROL_GROUP, HostControlError, _root_json,
        )
        self.path = SYSTEM_ROOT / "config" / "control.json"
        if not self.path.is_absolute() or self.path.resolve(strict=True) != self.path:
            raise MaintenanceError("Executive control config path is not canonical")
        self.gid = grp.getgrnam(CONTROL_GROUP).gr_gid
        self.ancestors = _sealed_ancestors(self.path)
        self.fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(self.fd)
            self.initial = _identity(info)
            if (not stat.S_ISREG(info.st_mode)
                    or info.st_uid != _TRUSTED_UID
                    or info.st_gid != self.gid
                    or info.st_nlink != 1
                    or stat.S_IMODE(info.st_mode) != 0o440
                    or has_macos_acl(self.path)):
                raise MaintenanceError(
                    "Executive control config is not the sealed Root-owned preimage")
            try:
                value, self.raw = _root_json(
                    self.path, modes=frozenset({0o440}),
                    uid=_TRUSTED_UID, gid=self.gid)
            except (HostControlError, OSError, KeyError, ValueError) as exc:
                raise MaintenanceError(
                    "Executive control config is unavailable") from exc
            if len(self.raw) > _MAX_DOCUMENT_BYTES:
                raise MaintenanceError("Executive control config exceeds its document budget")
            if not isinstance(value, dict):
                raise MaintenanceError("Executive control config is not an object")
            self.value = value
        except BaseException:
            os.close(self.fd)
            self.fd = None
            raise

    def check(self) -> dict:
        """Re-pin the held, named, ancestor and raw-byte identity at one edge."""
        import grp
        from ops.executive_os.autonomy_control import (
            CONTROL_GROUP, HostControlError, _root_json,
        )
        if self.fd is None:
            raise MaintenanceError("Executive control config is no longer held")
        if (_identity(os.fstat(self.fd)) != self.initial
                or _identity(self.path.lstat()) != self.initial
                or self.path.resolve(strict=True) != self.path
                or any(_identity(parent.lstat()) != identity
                       for parent, identity in self.ancestors)):
            raise MaintenanceError("Executive control config changed while held")
        gid = grp.getgrnam(CONTROL_GROUP).gr_gid
        if gid != self.gid:
            raise MaintenanceError("Executive control config custody group drifted")
        try:
            _value, raw = _root_json(self.path, modes=frozenset({0o440}),
                                     uid=_TRUSTED_UID, gid=self.gid)
        except (HostControlError, OSError, KeyError, ValueError) as exc:
            raise MaintenanceError("Executive control config is unavailable") from exc
        if raw != self.raw:
            raise MaintenanceError("Executive control config changed while held")
        return self.value

    def close(self) -> None:
        fd, self.fd = self.fd, None
        if fd is not None:
            os.close(fd)

    def __enter__(self) -> "_RootConfig":
        try:
            self.check()
        except BaseException:
            self.close()
            raise
        return self

    def __exit__(self, kind, error, traceback) -> bool:
        self.close()
        return False


def require_disarmed(config: dict) -> None:
    if any(config.get(k) is not False for k in
           ("ceo_submit_armed", "coo_autonomy_armed", "coo_operator_harness_armed")):
        raise MaintenanceError("maintenance requires all control intake arms closed")

def require_stopped() -> None:
    for label in ("com.mastermind.executive.control", "com.mastermind.executive.worker.codex"):
        try:
            probe = subprocess.run(
                ["/bin/launchctl", "print", "system/" + label],
                capture_output=True, timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise MaintenanceError("Executive service absence could not be verified") from exc
        absent = f'Could not find service "{label}" in domain for system\n'.encode("ascii")
        if (probe.returncode != 113 or probe.stdout != b""
                or probe.stderr not in (absent, b"Bad request.\n" + absent)):
            raise MaintenanceError("maintenance requires exact launchctl service absence")


class _ServiceAdmissionLock:
    """Hold the runtime's own canonical offline service lock for v5-to-v7 work.

    This is the existing ``data/control_plane/executive-service.lock`` beside
    the authoritative database, derived from the qualified actual config —
    never a new store or a replacement verifier. The lock file must already
    exist as a control-owned single-link 0600 regular file with no ACL; it is
    opened ``O_NOFOLLOW`` (never created, chowned, rewritten or removed) and
    locked with one nonblocking ``flock`` held through every snapshot, initial
    evidence API call, final rename or runmarker. The canonical service marker
    and the schema-upgrade barrier must stay absent and are rechecked at the
    final edge. This is not a full process census: exclusive Root custody
    against noncooperating direct SQLite writers remains the caller's separate
    requirement, and the lock is released before any Control-owned offline
    migration or before normal Service startup.
    """

    def __init__(self, config: dict, *, _pre_census_barrier=None):
        self._config = config
        self._pre_census_barrier = _pre_census_barrier
        if _pre_census_barrier is not None:
            # This is a retained observation created by the existing backup
            # owner's Root-only context, never a caller boolean or path DTO.
            from control_plane import executive_backup as backup
            if (os.geteuid() != 0 or not isinstance(
                    _pre_census_barrier, backup._PreCensusBarrierObservation)):
                raise MaintenanceError("retained barrier requires the actual Root owner")
            _pre_census_barrier.check()
        self.state: Path | None = None
        self.alias: tuple | None = None
        self.lock_fd: int | None = None
        self.state_fd: int | None = None
        self.lock_initial: tuple | None = None
        self.state_initial: tuple | None = None
        self.control_uid: int | None = None
        self.control_gid: int | None = None
        self.ancestry = _UnstartedPreproofGuard()

    def _control_identity(self) -> tuple[int, int]:
        # Exact account provenance from the actual qualified owner accounts;
        # never the caller's effective UID.
        import pwd
        import grp
        from ops.executive_os.autonomy_control import CONTROL_USER, CONTROL_GROUP
        user, group = pwd.getpwnam(CONTROL_USER), grp.getgrnam(CONTROL_GROUP)
        if (user.pw_name != CONTROL_USER or group.gr_name != CONTROL_GROUP
                or user.pw_gid != group.gr_gid or type(user.pw_uid) is not int
                or type(group.gr_gid) is not int or user.pw_uid <= 0 or group.gr_gid <= 0):
            raise MaintenanceError("Executive Control identity is ambiguous")
        return user.pw_uid, group.gr_gid

    def _state_directory(self) -> Path:
        from control_plane.executive_backup import (
            _UPGRADE_BARRIER_NAME as backup_barrier_name,
        )
        if backup_barrier_name != _SCHEMA_UPGRADE_BARRIER:
            raise MaintenanceError("Executive schema upgrade barrier name drifted")
        root = _canonical_root_path(self._config.get("runtime_root"))
        state = root / "data/control_plane"
        # Only the exact configured logical runtime root — the authoritative
        # database lives beneath it at data/control_plane — is mapped through
        # the closed /var alias to its physical spelling. Any other spelling is
        # never mapped and never generically resolved.
        if (sys.platform == "darwin"
                and root == _MACOS_VAR_ALIAS / "db/mastermind-executive/control/db"):
            info = _MACOS_VAR_ALIAS.lstat()
            target = os.readlink(_MACOS_VAR_ALIAS)
            if (not stat.S_ISLNK(info.st_mode) or info.st_uid != _TRUSTED_UID
                    or target not in ("private/var", os.fspath(_MACOS_VAR_PHYSICAL))):
                raise MaintenanceError("Runtime /var alias is not trusted")
            self.alias = (_identity(info), target)
            state = _MACOS_VAR_PHYSICAL / state.relative_to(_MACOS_VAR_ALIAS)
        return state

    def __enter__(self) -> "_ServiceAdmissionLock":
        from control_plane.executive_backup import (
            DEFAULT_SERVICE_LOCK_NAME, DEFAULT_SERVICE_MARKER_NAME,
        )
        if DEFAULT_SERVICE_LOCK_NAME != _SERVICE_LOCK or DEFAULT_SERVICE_MARKER_NAME != _SERVICE_MARKER:
            raise MaintenanceError("Executive service custody names drifted")
        self.control_uid, self.control_gid = self._control_identity()
        self.state = self._state_directory()
        try:
            anchored_state = self.ancestry._hold(self.state, directory=True)
        except BaseException:
            self.ancestry.close()
            raise
        state_info = os.fstat(anchored_state)
        if (not stat.S_ISDIR(state_info.st_mode)
                or stat.S_IMODE(state_info.st_mode) != 0o700
                or state_info.st_uid != self.control_uid
                or state_info.st_gid != self.control_gid
                or has_macos_acl(self.state, descriptor=anchored_state, expected_identity=state_info)):
            self.ancestry.close()
            raise MaintenanceError("Executive service state directory is not sealed")
        self.state_fd = os.dup(anchored_state)
        try:
            self.state_initial = _identity(os.fstat(self.state_fd))
            lock = self.state / _SERVICE_LOCK
            # require_existing: a missing lock refuses and is never created.
            # O_NOFOLLOW|O_NONBLOCK keeps the existing regular file the only
            # thing this descriptor can name.
            self.lock_fd = os.open(
                _SERVICE_LOCK,
                os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0),
                dir_fd=self.state_fd)
            try:
                self.lock_initial = _identity(os.fstat(self.lock_fd))
                if (not stat.S_ISREG(os.fstat(self.lock_fd).st_mode)
                        or os.fstat(self.lock_fd).st_uid != self.control_uid
                        or os.fstat(self.lock_fd).st_gid != self.control_gid
                        or os.fstat(self.lock_fd).st_nlink != 1
                        or stat.S_IMODE(os.fstat(self.lock_fd).st_mode) != 0o600
                        or has_macos_acl(lock, descriptor=self.lock_fd, expected_identity=os.fstat(self.lock_fd))):
                    raise MaintenanceError("Executive service admission lock is not the sealed control-owned file")
                if _identity(lock.lstat()) != self.lock_initial:
                    raise MaintenanceError("Executive service admission lock changed during acquisition")
                try:
                    fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    raise MaintenanceError("Executive service admission lock is occupied") from exc
                self.check()
            except BaseException:
                os.close(self.lock_fd)
                self.lock_fd = None
                raise
        except BaseException:
            os.close(self.state_fd)
            self.state_fd = None
            self.ancestry.close()
            raise
        return self

    def check(self) -> None:
        """Re-pin held/named/ancestor identity and required absence at one edge."""
        from control_plane.executive_backup import _UPGRADE_BARRIER_NAME
        if self.lock_fd is None or self.state_fd is None or self.state is None:
            raise MaintenanceError("Executive service admission lock is not held")
        self.ancestry.check()
        lock = self.state / _SERVICE_LOCK
        if _identity(os.fstat(self.lock_fd)) != self.lock_initial:
            raise MaintenanceError("Executive service admission lock changed while held")
        if _identity(lock.lstat()) != self.lock_initial:
            raise MaintenanceError("Executive service admission lock name changed while held")
        if (_identity(os.fstat(self.state_fd)) != self.state_initial
                or _identity(self.state.lstat()) != self.state_initial):
            raise MaintenanceError("Executive service state directory changed while held")
        for absent_name in (_SERVICE_MARKER, _UPGRADE_BARRIER_NAME):
            if absent_name == _UPGRADE_BARRIER_NAME and self._pre_census_barrier is not None:
                self._pre_census_barrier.check()
                if self._pre_census_barrier.identity['path'] != str(self.state / absent_name):
                    raise MaintenanceError("retained barrier differs from the canonical state")
                continue
            if os.path.lexists(self.state / absent_name):
                raise MaintenanceError(
                    "Executive " + absent_name + " is present; v5-to-v7 admission refuses")
        if self.alias is not None:
            info = _MACOS_VAR_ALIAS.lstat()
            if (_identity(info), os.readlink(_MACOS_VAR_ALIAS)) != self.alias:
                raise MaintenanceError("retained Runtime alias changed")

    def _accept_qualification_creation(self, path: Path, before_names: set[str]) -> None:
        """Admit exactly our own initially private O_EXCL child publication.

        Creating that one child changes directory timestamps; inode, custody,
        all ancestors and the exact name transition remain qualified. This
        private operation is unavailable to normal maintenance callers.
        """
        if (self._pre_census_barrier is None or self.state_fd is None
                or path.parent != self.state):
            raise MaintenanceError("qualification publication has no retained custody")
        info = os.fstat(self.state_fd)
        stable = lambda value: (value.st_dev, value.st_ino, value.st_mode,
                                value.st_uid, value.st_gid)
        if (stable(info) != stable(self.ancestry.nodes[self.state][1])
                or stable(path.parent.lstat()) != stable(info)
                or set(os.listdir(self.state_fd)) != before_names | {path.name}):
            raise MaintenanceError("qualification publication changed the state namespace")
        self.state_initial = _identity(info)
        self.check()

    def __exit__(self, kind, error, traceback) -> bool:
        lock_fd, self.lock_fd = self.lock_fd, None
        state_fd, self.state_fd = self.state_fd, None
        try:
            if lock_fd is not None:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            try:
                if lock_fd is not None:
                    os.close(lock_fd)
            finally:
                try:
                    if state_fd is not None:
                        os.close(state_fd)
                finally:
                    self.ancestry.close()
        return False


def _quiescent_database(config: dict, lock, guard) -> Path:
    """Qualify the original DB without letting a SQLite reader create sidecars."""
    if (not isinstance(lock, _ServiceAdmissionLock) or lock.state is None
            or lock._config != config):
        raise MaintenanceError("quiescent verification requires the actual canonical lock")
    lock.check()
    database = lock.state / "executive.sqlite3"
    for suffix in ("-wal", "-shm", "-journal"):
        if os.path.lexists(database.with_name(database.name + suffix)):
            raise MaintenanceError("quiescent maintenance database retains a sidecar")
    fd = guard._hold(database, directory=False, exact=True)
    info = os.fstat(fd)
    if (info.st_uid != lock.control_uid or info.st_gid != lock.control_gid
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
            or has_macos_acl(database, descriptor=fd, expected_identity=info)):
        raise MaintenanceError("quiescent maintenance database custody is invalid")
    guard.check()
    return database


def _verification_runtime(database: Path):
    """Use unchanged Runtime decoders on a qualified private verification copy."""
    from control_plane.executive_runtime import Runtime, RuntimeStore
    return Runtime.from_store(RuntimeStore(
        root=database.parent, database_path=database,
        create=False, existing_writable=False))


def _full_v5_digest(database: Path) -> str:
    from control_plane import executive_backup as backup
    with backup._readonly_database(database) as connection:
        return backup.full_v5_content_digest(connection)


def _selected_v5_backup(selected_sha: str, selected: dict, guard,
                        source_digest: str | None = None) -> Path:
    path = bundle_path(selected_sha) / "prestate.sqlite3"
    baseline = sealed_backup_snapshot(path, selected["backup_sha256"])
    if digest(baseline) != selected["baseline_sha256"]:
        raise MaintenanceError("selected v5 backup baseline drifted")
    guard.file(path)
    if source_digest is not None and _full_v5_digest(path) != source_digest:
        raise MaintenanceError("selected v5 backup full content differs from migration source")
    guard.check()
    return path


@contextmanager
def _v5_preflight_runtime(selected_sha: str, selected: dict, database: Path, guard):
    """Transient Root verification copy; never a published backup or authority."""
    source = _selected_v5_backup(selected_sha, selected, guard)
    if (snapshot(database, immutable=True) != snapshot(source, immutable=True)
            or _full_v5_digest(database) != _full_v5_digest(source)):
        raise MaintenanceError("live v5 source differs from the complete selected backup")
    fd = guard._hold(source, directory=False, exact=True)
    info = os.fstat(fd)
    with tempfile.TemporaryDirectory(prefix="mastermind-maintenance-v5-verification-") as name:
        directory = Path(name)
        directory.chmod(0o700)
        copy = directory / "verification.sqlite3"
        out = os.open(copy, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        observed = hashlib.sha256()
        try:
            offset = 0
            while offset < info.st_size:
                block = os.pread(fd, min(1024 * 1024, info.st_size - offset), offset)
                if not block:
                    raise MaintenanceError("selected verification copy was truncated")
                observed.update(block)
                view = memoryview(block)
                while view:
                    written = os.write(out, view)
                    if written <= 0:
                        raise MaintenanceError("selected verification copy failed")
                    view = view[written:]
                offset += len(block)
            os.fsync(out)
        finally:
            os.close(out)
        guard.check()
        if (observed.hexdigest() != selected["backup_sha256"]
                or _file_digest(copy) != selected["backup_sha256"]):
            raise MaintenanceError("selected verification copy digest mismatch")
        yield _verification_runtime(copy)
        if _file_digest(copy) != selected["backup_sha256"]:
            raise MaintenanceError("selected verification copy changed during decoding")
        guard.check()

def terminal_assignment(config: dict, job: Any, attempt: Any) -> dict:
    """Read the existing control-owned revocation receipt; grant no new effect."""
    import pwd
    from ops.executive_os.autonomy_control import _root_json, CONTROL_USER, HostControlError
    from control_plane.executive_worker_broker import uid_sweep_receipt_is_passing

    path = Path(config["receipts_root"])/attempt.attempt_id/"assignment-seal-receipt.json"
    control_uid = pwd.getpwnam(CONTROL_USER).pw_uid
    try:
        value, raw = _root_json(
            path, modes=frozenset({0o600}), uid=control_uid,
        )
    except (HostControlError, OSError, KeyError, ValueError) as exc:
        raise MaintenanceError("terminal assignment receipt is unavailable") from exc
    if (
        value.get("schema_version") != "mastermind.executive_assignment_seal/v1"
        or value.get("passed") is not True or value.get("job_id") != job.job_id
        or value.get("control_uid") != control_uid
        or value.get("attempt_id") != attempt.attempt_id
        or not uid_sweep_receipt_is_passing(value.get("uid_sweep"))
        or value["uid_sweep"].get("worker_uid") != config["worker_uid"]
        or not isinstance(value.get("paths"), dict)
    ):
        raise MaintenanceError("terminal assignment receipt is invalid")
    expected = {
        "workspace": str(Path(job.worktree).resolve(strict=True)),
        "run": str((Path(config["worker_runs_root"])/attempt.attempt_id).resolve(strict=True)),
    }
    if set(value["paths"]) != set(expected) or any(
        not isinstance(value["paths"][key], dict)
        or value["paths"][key].get("worker_traversal_revoked") is not True
        or not isinstance(value["paths"][key].get("after"), dict)
        or value["paths"][key]["after"].get("path") != path
        for key, path in expected.items()
    ):
        raise MaintenanceError("terminal assignment path binding drifted")
    for key, name in expected.items():
        target = Path(name)
        info = target.lstat()
        identity = dict(path=name, device=info.st_dev, inode=info.st_ino,
                        uid=info.st_uid, gid=info.st_gid, mode=stat.S_IMODE(info.st_mode),
                        mtime_ns=info.st_mtime_ns)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != control_uid
                or stat.S_IMODE(info.st_mode) != 0o700
                or has_macos_acl(target, expected_identity=info)
                or value["paths"][key]["after"] != identity):
            raise MaintenanceError("terminal assignment filesystem identity drifted")
    return {"assignment_seal_sha256": hashlib.sha256(raw).hexdigest()}


def terminal_carry_fields(
    runtime: Any, root: Any, config: dict, before: dict, predecessor: str,
    successor: str | None = None,
) -> tuple[Any, dict]:
    """Qualify one inert failed planner using existing Runtime evidence owners."""
    from control_plane.executive_runtime import RuntimeProofError
    # Preparation must validate the same path that acceptance will traverse,
    # before publishing a bundle that could only fail the depth/cycle guard.
    if successor is None:
        prior, summary, material = prior_carry_material(predecessor)
    else:
        prior, summary, material = prior_carry_material(
            predecessor, _seen=frozenset({successor}))
    if (
        prior["root_job_id"] != root.job_id
        or prior["root_identity_sha256"] != root_identity(root)
        or root.constraints.get("base_sha") != material["frozen_base_sha"]
    ):
        raise MaintenanceError("terminal carry root differs from prior qualified root")
    tables = before["tables"]
    children = [row for row in tables["jobs"] if row["root_job_id"] == root.job_id and row["job_id"] != root.job_id]
    if len(children) != 1:
        raise MaintenanceError("terminal carry requires one exact failed planner")
    job = runtime.jobs.get_job(children[0]["job_id"])
    attempts = runtime.attempts.list_attempts(job.job_id)
    if (
        job.parent_job_id != root.job_id or job.depth != 1
        or job.orchestration_role != "plan" or job.status.value != "FAILED"
        or job.attempt_count != 1 or len(attempts) != 1
        or attempts[0].status.value != "FAILED"
        or attempts[0].attempt_id != job.current_attempt_id
    ):
        raise MaintenanceError("terminal carry planner is not one failed attempt")
    attempt = attempts[0]
    if any(getattr(attempt, key) is not None for key in
           ("pid", "pgid", "process_start_identity", "boot_id", "provider_session_id")):
        raise MaintenanceError("terminal carry contains provider process identity")
    if any(row["attempt_id"] == attempt.attempt_id for table in
           ("harness_session_epochs", "process_generations") for row in tables[table]):
        raise MaintenanceError("terminal carry contains native harness history")
    try:
        pending = runtime.jobs.pending_cycle_dispatch_effect_unknown(root.job_id)
        block = runtime.jobs.validated_cycle_block(root.job_id)
        effects = [row for row in tables["events"] if row["job_id"] == root.job_id
                   and row["event_type"] in {"COO_DISPATCH_EFFECT_UNKNOWN", "COO_DISPATCH_RECONCILED"}]
        markers = [row for row in effects if row["event_type"] == "COO_DISPATCH_EFFECT_UNKNOWN"]
        if len(markers) != 1:
            raise MaintenanceError("terminal carry requires one original dispatch marker")
        marker = markers[0]
        original = json.loads(marker["payload_json"])
        if (original["selected_job_id"] != job.job_id or original["attempt_id"] != attempt.attempt_id
                or original["dispatch_command_id"] != f"coo-cycle:{root.job_id}:dispatch:{job.job_id}:attempt:1"):
            raise MaintenanceError("terminal carry dispatch differs from its failed planner")
        if pending is not None:
            if block is not None or len(effects) != 1 or pending != original:
                raise MaintenanceError("terminal carry pending dispatch history is inconsistent")
            outcome = runtime.attempts.terminal_cycle_dispatch_outcome(
                job.job_id, command_id=pending["dispatch_command_id"],
            )
            if outcome.attempt.attempt_id != attempt.attempt_id:
                raise MaintenanceError("terminal carry observation changed")
            terminal_history = {}
        else:
            resolutions = [row for row in effects if row["event_type"] == "COO_DISPATCH_RECONCILED"]
            blocks = [row for row in tables["events"]
                      if row["job_id"] == root.job_id and row["event_type"] == "COO_CYCLE_BLOCKED"]
            if (block is None or block[1]["reason"] != "plan_terminal_adverse"
                    or block[1]["selected_job_id"] != job.job_id
                    or len(effects) != 2 or len(resolutions) != 1 or len(blocks) != 1
                    or resolutions[0]["command_id"] != original["dispatch_command_id"] + ":reconciled"
                    or not marker["event_id"] < resolutions[0]["event_id"] < blocks[0]["event_id"]):
                raise MaintenanceError("terminal carry requires exact reconciliation and adverse-plan block")
            outcome = runtime.attempts.reconciled_terminal_cycle_dispatch_outcome(
                job.job_id, command_id=original["dispatch_command_id"],
            )
            if outcome.attempt.attempt_id != attempt.attempt_id:
                raise MaintenanceError("terminal carry reconciled observation changed")
            terminal_history = {"dispatch_effects": sorted(effects, key=lambda row: row["event_id"]),
                                "cycle_block": blocks[0]}
    except RuntimeProofError as exc:
        raise MaintenanceError("terminal carry Runtime evidence is invalid") from exc
    admissions = [row for row in tables["events"] if row["event_id"] == prior["root_event_id"]]
    if len(markers) != 1 or len(admissions) != 1:
        raise MaintenanceError("terminal carry admission or marker is not unique")
    marker, admission = markers[0], admissions[0]
    if digest(admission) != prior["root_event_sha256"]:
        raise MaintenanceError("terminal carry root admission drifted")
    proof = runtime.jobs.get_job(summary["success_job_id"])
    if (proof is None or proof.status.value != "COMPLETED"
            or proof.orchestration_role is not None
            or proof.constraints.get("base_sha") != predecessor):
        raise MaintenanceError("terminal carry proof template is not the accepted predecessor proof")
    quotas = [row for row in tables["worker_quota_classes"]
              if row["worker_id"] == config["worker_id"] and row["quota_class"] == config["quota_class"]]
    if len(quotas) != 1 or quotas[0]["status"] != "AVAILABLE" or quotas[0]["held_attempt_id"] is not None:
        raise MaintenanceError("terminal carry requires available predecessor proof capacity")
    fields = {
        **material, **terminal_assignment(config, job, attempt),
        "template_proof_job_id": proof.job_id, "template_proof_job_sha256": digest(proof.to_dict()),
        "terminal_job_id": job.job_id, "terminal_attempt_id": attempt.attempt_id,
        "terminal_marker_event_id": marker["event_id"], "terminal_marker_event_sha256": digest(marker),
        "terminal_state_sha256": digest({"job": children[0], "attempts": [
            row for row in tables["attempts"] if row["job_id"] == job.job_id
        ], **terminal_history}),
        "predecessor_quota_sha256": digest(quotas[0]),
    }
    return proof, fields



def _require_absent(path: Path) -> None:
    """Only an exact missing leaf beneath an existing canonical parent is absence."""
    if not path.is_absolute() or path.parent.resolve(strict=True) != path.parent:
        raise MaintenanceError("superseded acceptance parent is not canonical")
    try:
        path.lstat()
    except FileNotFoundError:
        return
    raise MaintenanceError("superseded release already has acceptance state")



def _require_runtime_acceptance_absent(path: Path) -> None:
    """Admit only the OS /var alias at the trusted Runtime absence-check seam."""
    expected_parent = _MACOS_VAR_ALIAS / "db/mastermind-executive/control/acceptance"
    if (sys.platform != "darwin" or path.parent != expected_parent
            or _SHA.fullmatch(path.name) is None):
        _require_absent(path)
        return
    alias_info = _MACOS_VAR_ALIAS.lstat()
    if not stat.S_ISLNK(alias_info.st_mode) or alias_info.st_uid != _TRUSTED_UID:
        raise MaintenanceError("Runtime /var alias is not trusted")
    target = os.readlink(_MACOS_VAR_ALIAS)
    if target not in ("private/var", os.fspath(_MACOS_VAR_PHYSICAL)):
        raise MaintenanceError("Runtime /var alias target is not canonical")
    physical = _MACOS_VAR_PHYSICAL / path.relative_to(_MACOS_VAR_ALIAS)
    # Do not resolve arbitrary ancestors into acceptance: the unchanged guard
    # rejects every further alias and still requires an exact missing leaf.
    _require_absent(physical)
    if (_identity(_MACOS_VAR_ALIAS.lstat()) != _identity(alias_info)
            or os.readlink(_MACOS_VAR_ALIAS) != target):
        raise MaintenanceError("Runtime /var alias changed during absence check")


def legacy_backup_sidecars(path: Path) -> tuple:
    """Observe only the sealed legacy WAL/SHM metadata; read no sidecar bytes."""
    observed = []
    for suffix, size in (("-wal", 0), ("-shm", 32768)):
        sidecar = path.with_name(path.name + suffix)
        try:
            info = sidecar.lstat()
        except FileNotFoundError:
            observed.append(None)
            continue
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != _TRUSTED_UID
                or info.st_gid != _TRUSTED_GID or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o400 or info.st_size != size
                or has_macos_acl(sidecar)):
            raise MaintenanceError("legacy backup sidecar is not sealed or has unexpected size")
        fd = os.open(sidecar, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            if (_identity(info) != _identity(os.fstat(fd))
                    or _identity(info) != _identity(sidecar.lstat())):
                raise MaintenanceError("legacy backup sidecar changed during observation")
        finally:
            os.close(fd)
        observed.append(_identity(info))
    if (observed[0] is None) != (observed[1] is None):
        raise MaintenanceError("legacy backup sidecars must be one exact sealed pair")
    return tuple(observed)


def sealed_backup_snapshot(path: Path, expected_digest: str) -> dict:
    """Validate the sealed backup bytes and its full semantic prestate."""
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise MaintenanceError("maintenance backup path is not canonical")
    ancestors = _sealed_ancestors(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != _TRUSTED_UID
                or before.st_nlink != 1 or stat.S_IMODE(before.st_mode) != 0o400
                or has_macos_acl(path)):
            raise MaintenanceError("maintenance backup is not sealed")
        if _file_digest(path) != expected_digest:
            raise MaintenanceError("maintenance backup digest mismatch")
        # The immutable read ignores sidecars only after proving the WAL is
        # empty. The SHM contents are neither read nor trusted as state.
        sidecars = legacy_backup_sidecars(path)
        value = snapshot(path, immutable=True)
        if (_identity(before) != _identity(os.fstat(fd))
                or _identity(before) != _identity(path.lstat())
                or any(_identity(p.lstat()) != identity for p, identity in ancestors)
                or legacy_backup_sidecars(path) != sidecars):
            raise MaintenanceError("maintenance backup changed during read")
        return value
    finally:
        os.close(fd)


def _attended_membership_shape_valid(value: Any) -> bool:
    """Shape of ``Acceptance._attended_worker_membership``: None, or exactly its ten fields."""
    if value is None:
        return True
    if type(value) is not dict or set(value) != _ATTENDED_MEMBERSHIP_KEYS:
        return False
    for key in ("worker_uid", "worker_gid"):
        if type(value[key]) is not int or not 400 <= value[key] < 500:
            return False
    for key in ("worker_user", "worker_group"):
        name = value[key]
        if (type(name) is not str or len(name) > 31
                or _ATTENDED_ACCOUNT.fullmatch(name) is None):
            return False
    worker_id, config_path = value["worker_id"], value["worker_config_path"]
    if (type(worker_id) is not str or not worker_id
            or type(config_path) is not str or not Path(config_path).is_absolute()
            or value["provider_home"] != os.fspath(_WORKER_HOMES / worker_id / "provider-home")):
        return False
    return all(type(value[key]) is str and _DIGEST.fullmatch(value[key]) is not None
               for key in ("worker_config_sha256", "bindings_sha256", "physical_binding_sha256"))


def _group_receipt_valid(value: dict, *, historical: bool) -> bool:
    """Protected-group receipt shape: the current eight-key form; with ``historical`` also the
    legacy six-key form. Exactly two generations are admitted; any other shape is refused."""
    current = (set(value) == _GROUP_RECEIPT_KEYS
               and value["passed"] is True and isinstance(value["effective_members"], dict)
               and isinstance(value["control_definition_sha256"], str)
               and _DIGEST.fullmatch(value["control_definition_sha256"]) is not None
               and _attended_membership_shape_valid(value["attended_worker_membership"])
               and value["primary_gid_census"] == "COMPLETE"
               and value["name_members"] == value["uuid_members"] == "EXACT"
               and value["nested_groups"] == "ABSENT")
    legacy = (historical and set(value) == _LEGACY_GROUP_RECEIPT_KEYS
              and value["passed"] is True and isinstance(value["effective_members"], dict)
              and value["primary_gid_census"] == "COMPLETE"
              and value["name_members"] == value["uuid_members"] == "EXACT"
              and value["nested_groups"] == "ABSENT")
    return current or legacy


def prejob_evidence(sha: str, *, historical: bool = False) -> str:
    """Hash only the two control-owned receipts preceding service attestation.

    This is evidence of an interrupted prefix, never a successful acceptance.
    No receipt, marker, service or Runtime state is modified. ``historical`` re-validates an
    already-sealed link and additionally admits the legacy six-key group receipt. Only the
    carry-chain walk sets it; ``prepare`` and the strict check in ``Maintenance.__init__`` leave
    it unset and so require the current eight-key form.
    """
    import pwd
    import grp
    from ops.executive_os.autonomy_control import (
        RUNTIME_ROOT, CONTROL_USER, CONTROL_GROUP, _root_json, HostControlError,
    )
    if _SHA.fullmatch(sha) is None:
        raise MaintenanceError("invalid interrupted release")
    uid = pwd.getpwnam(CONTROL_USER).pw_uid
    gid = grp.getgrnam(CONTROL_GROUP).gr_gid
    logical = RUNTIME_ROOT / "control/acceptance" / sha
    path = logical
    alias = None
    if (sys.platform == "darwin" and logical.parent ==
            _MACOS_VAR_ALIAS / "db/mastermind-executive/control/acceptance"):
        info = _MACOS_VAR_ALIAS.lstat()
        target = os.readlink(_MACOS_VAR_ALIAS)
        if (not stat.S_ISLNK(info.st_mode) or info.st_uid != _TRUSTED_UID
                or target not in ("private/var", os.fspath(_MACOS_VAR_PHYSICAL))):
            raise MaintenanceError("Runtime /var alias is not trusted")
        alias = (_identity(info), target)
        path = _MACOS_VAR_PHYSICAL / logical.relative_to(_MACOS_VAR_ALIAS)
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise MaintenanceError("interrupted acceptance path is not canonical")
    directories = []
    for directory in (path.parent, path):
        info = directory.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != uid or info.st_gid != gid
                or stat.S_IMODE(info.st_mode) != 0o700 or has_macos_acl(directory)):
            raise MaintenanceError("interrupted acceptance directory identity drifted")
        directories.append((directory, _identity(info)))
    names = {"nonexecutive-launchd-before.json", "protected-group-membership.json"}
    if {item.name for item in path.iterdir()} != names:
        raise MaintenanceError("interrupted acceptance passed the pre-Job boundary")
    manifest = {}
    files = []
    for name in sorted(names):
        receipt = path / name
        initial = receipt.lstat()
        try:
            value, raw = _root_json(receipt, modes=frozenset({0o400}), uid=uid, gid=gid)
        except HostControlError as exc:
            raise MaintenanceError("interrupted acceptance receipt is unsafe") from exc
        if _identity(receipt.lstat()) != _identity(initial):
            raise MaintenanceError("interrupted acceptance receipt changed")
        files.append((receipt, _identity(initial)))
        if name == "nonexecutive-launchd-before.json":
            valid = (set(value) == {"sha256", "labels_excluded"}
                     and isinstance(value["sha256"], str)
                     and _DIGEST.fullmatch(value["sha256"]) is not None
                     and type(value["labels_excluded"]) is int and value["labels_excluded"] == 2)
        else:
            valid = _group_receipt_valid(value, historical=historical)
        if not valid:
            raise MaintenanceError("interrupted acceptance receipt schema drifted")
        manifest[name] = hashlib.sha256(raw).hexdigest()
    if (any(_identity(p.lstat()) != identity for p, identity in directories + files)
            or {item.name for item in path.iterdir()} != names
            or (alias is not None and
                (_identity(_MACOS_VAR_ALIAS.lstat()), os.readlink(_MACOS_VAR_ALIAS)) != alias)):
        raise MaintenanceError("interrupted acceptance namespace changed")
    return digest(manifest)


def preproof_evidence(sha: str) -> tuple[str, dict]:
    """Hash the eight control-owned pre-proof receipts (and exactly one probe),
    plus any bounded optional failure artifact, returning the manifest digest and
    the parsed secret-canary envelope. No receipt, marker, service or Runtime
    state is modified. The selected release must have run ``start_and_attest_services``
    (replacing the live secret-canary receipt with its own envelope), but no Job;
    anything after that boundary refuses with ``interrupted acceptance is not a
    pre-proof prefix``.
    """
    import pwd
    import grp
    from ops.executive_os.autonomy_control import (
        RUNTIME_ROOT, CONTROL_USER, CONTROL_GROUP, _root_json, HostControlError,
    )
    if _SHA.fullmatch(sha) is None:
        raise MaintenanceError("invalid interrupted release")
    uid = pwd.getpwnam(CONTROL_USER).pw_uid
    gid = grp.getgrnam(CONTROL_GROUP).gr_gid
    logical = RUNTIME_ROOT / "control/acceptance" / sha
    path = logical
    alias = None
    if (sys.platform == "darwin" and logical.parent ==
            _MACOS_VAR_ALIAS / "db/mastermind-executive/control/acceptance"):
        info = _MACOS_VAR_ALIAS.lstat()
        target = os.readlink(_MACOS_VAR_ALIAS)
        if (not stat.S_ISLNK(info.st_mode) or info.st_uid != _TRUSTED_UID
                or target not in ("private/var", os.fspath(_MACOS_VAR_PHYSICAL))):
            raise MaintenanceError("Runtime /var alias is not trusted")
        alias = (_identity(info), target)
        path = _MACOS_VAR_PHYSICAL / logical.relative_to(_MACOS_VAR_ALIAS)
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise MaintenanceError("interrupted acceptance path is not canonical")
    directories = []
    for directory in (path.parent, path):
        info = directory.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != uid or info.st_gid != gid
                or stat.S_IMODE(info.st_mode) != stat.S_IRWXU or has_macos_acl(directory)):
            raise MaintenanceError("interrupted acceptance directory identity drifted")
        directories.append((directory, _identity(info)))
    names = {item.name for item in path.iterdir()}
    probe_names = sorted(name for name in names if _PREPROOF_PROBE.fullmatch(name))
    # Exactly one probe, every core receipt present, and any remaining name is
    # either the bounded optional artifact or a name explicitly refused above.
    optional_allowed = _PREPROOF_CORE_RECEIPTS | _PREPROOF_OPTIONAL_ARTIFACTS | set(probe_names)
    if (len(probe_names) != 1
            or not _PREPROOF_CORE_RECEIPTS | set(probe_names) <= names
            or not names <= optional_allowed):
        raise MaintenanceError("interrupted acceptance is not a pre-proof prefix")
    manifest: dict[str, str] = {}
    files: list = []
    envelope_value: dict | None = None
    def _nondict() -> "MaintenanceError":
        return MaintenanceError("interrupted acceptance receipt schema drifted")
    for core_name in sorted(_PREPROOF_CORE_RECEIPTS | set(probe_names)):
        receipt = path / core_name
        initial = receipt.lstat()
        try:
            value, raw = _root_json(receipt, modes=frozenset({0o400}), uid=uid, gid=gid)
        except HostControlError as exc:
            raise MaintenanceError("interrupted acceptance receipt is unsafe") from exc
        if _identity(receipt.lstat()) != _identity(initial):
            raise MaintenanceError("interrupted acceptance receipt changed")
        files.append((receipt, _identity(initial)))
        if core_name == "nonexecutive-launchd-before.json":
            valid = (set(value) == {"sha256", "labels_excluded"}
                     and isinstance(value["sha256"], str)
                     and _DIGEST.fullmatch(value["sha256"]) is not None
                     and type(value["labels_excluded"]) is int and value["labels_excluded"] == 2)
        elif core_name == "protected-group-membership.json":
            valid = _group_receipt_valid(value, historical=False)
        elif core_name == "secret-canary-envelope.json":
            if type(value) is not dict:
                raise _nondict()
            expected_keys = _PREPROOF_RECEIPT_KEYS["secret-canary-envelope.json"]
            expected_types = _PREPROOF_RECEIPT_VALUE_TYPES["secret-canary-envelope.json"]
            if set(value) != expected_keys:
                raise _nondict()
            if any(type(value[key]) is not expected_types[key] for key in expected_keys):
                raise _nondict()
            # Compare the parsed schema marker only; never print the envelope.
            if value["schema_version"] != _PREPROOF_SCHEMAS["secret-canary-envelope.json"]:
                raise _nondict()
            envelope_value = value
            valid = True
        elif core_name == "awaiting-canary-status.json":
            # Acceptance.start_and_attest_services persists the verbatim Control
            # status response ({"ok": true, "result": {...}}) and refuses unless
            # result.service_state is AWAITING_CANARY before it records the
            # envelope, so a genuine pre-proof prefix always carries that state.
            if type(value) is not dict:
                raise _nondict()
            control_result = value.get("result")
            if (value.get("ok") is not True or type(control_result) is not dict
                    or control_result.get("service_state") != "AWAITING_CANARY"):
                raise MaintenanceError("interrupted acceptance did not reach AWAITING_CANARY")
            valid = True
        elif core_name in {"failure-control-status.json", "worker-broker-startup.json"}:
            # Receipts persisted from a Control response or broker status write
            # the parsed value verbatim; the bounded checked shape is only the
            # top level dict.
            valid = type(value) is dict
        elif core_name == "launchd-principals.json":
            if type(value) is not dict:
                raise _nondict()
            if set(value) != _PREPROOF_RECEIPT_KEYS["launchd-principals.json"]:
                raise _nondict()
            if any(type(value[key]) is not dict for key in value):
                raise _nondict()
            valid = True
        elif core_name == "assignment-root-nonlistability.json":
            if type(value) is not dict:
                raise _nondict()
            if set(value) != _PREPROOF_RECEIPT_KEYS["assignment-root-nonlistability.json"]:
                raise _nondict()
            if any(type(value[key]) is not _PREPROOF_RECEIPT_VALUE_TYPES["assignment-root-nonlistability.json"][key]
                   for key in value):
                raise _nondict()
            valid = True
        else:
            # Exactly one probe name, already enforced above.
            if type(value) is not dict:
                raise _nondict()
            expected_keys = _PREPROOF_RECEIPT_KEYS["control-environment-probe"]
            expected_types = _PREPROOF_RECEIPT_VALUE_TYPES["control-environment-probe"]
            if set(value) != expected_keys:
                raise _nondict()
            if any(type(value[key]) is not expected_types[key] for key in expected_keys):
                raise _nondict()
            if value["schema_version"] != _PREPROOF_SCHEMAS["control-environment-probe"]:
                raise _nondict()
            valid = True
        if not valid:
            raise MaintenanceError("interrupted acceptance receipt schema drifted")
        manifest[core_name] = hashlib.sha256(raw).hexdigest()
    for artifact in sorted(_PREPROOF_OPTIONAL_ARTIFACTS):
        optional = path / artifact
        # Presence is the directory entry, not exists(): exists() follows a
        # symlink, so a dangling one would be skipped instead of refused.
        if artifact not in names:
            continue
        try:
            initial = optional.lstat()
        except FileNotFoundError:
            raise MaintenanceError("interrupted acceptance namespace changed") from None
        if not stat.S_ISREG(initial.st_mode):
            # Symlink (dangling or not), FIFO, directory or device: refuse
            # before any open, which could follow it or block on it.
            raise MaintenanceError("interrupted acceptance receipt is unsafe")
        fd = os.open(optional, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            before = os.fstat(fd)
        finally:
            os.close(fd)
        if (_identity(before) != _identity(initial)
                or not stat.S_ISREG(before.st_mode) or before.st_uid != uid
                or before.st_gid != gid or before.st_nlink != 1
                or stat.S_IMODE(before.st_mode) != 0o400
                or has_macos_acl(optional)
                or before.st_size > _MAX_PREPROOF_FAILURE_ARTIFACT_BYTES):
            raise MaintenanceError("interrupted acceptance receipt is unsafe")
        files.append((optional, _identity(before)))
        with optional.open("rb") as stream:
            raw = stream.read(before.st_size)
        if len(raw) != before.st_size:
            raise MaintenanceError("interrupted acceptance receipt is unsafe")
        if _identity(optional.lstat()) != _identity(before):
            raise MaintenanceError("interrupted acceptance receipt is unsafe")
        manifest[artifact] = hashlib.sha256(raw).hexdigest()
    if (any(_identity(p.lstat()) != identity for p, identity in directories + files)
            or {item.name for item in path.iterdir()} != names
            or (alias is not None and
                (_identity(_MACOS_VAR_ALIAS.lstat()), os.readlink(_MACOS_VAR_ALIAS)) != alias)):
        raise MaintenanceError("interrupted acceptance namespace changed")
    if envelope_value is None:
        raise MaintenanceError("interrupted acceptance is not a pre-proof prefix")
    return digest(manifest), envelope_value


def _unstarted_preproof_v5_to_v7_view(descriptor: Any) -> dict:
    """Project one closed v5-to-v7 descriptor onto its internal old-mode view.

    The view exists only to re-enter the unchanged selected/deeper pre-proof
    validators, the sealed canary walk and the retained identity guard with
    the original v5 semantics. It is derived from the actual selected v5
    descriptor and the verified source state, is never sealed, published or
    hashed, and never demands the selected v5 hashes equal the working v7
    prestate.
    """
    if (not isinstance(descriptor, dict)
            or descriptor.get("schema_version") != SCHEMA_UNSTARTED_PREPROOF_V5_TO_V7
            or set(descriptor) != _DESCRIPTOR_UNSTARTED_PREPROOF_V5_TO_V7_KEYS):
        raise MaintenanceError("invalid v5-to-v7 supersession view")
    selected_sha = descriptor["superseded_unstarted_preproof_sha"]
    selected = descriptor_for(selected_sha)
    if (selected is None or selected["schema_version"] != SCHEMA_PREPROOF
            or digest(selected) != descriptor["superseded_descriptor_sha256"]):
        raise MaintenanceError("superseded descriptor or accepted ancestor mismatch")
    working = {"schema_version", "successor_sha", "backup_sha256",
               "baseline_sha256", "inventory_sha256"}
    if any(selected[key] != descriptor[key] for key in _DESCRIPTOR_V2_KEYS - working):
        raise MaintenanceError("superseded sealed binding differs from successor")
    return _v5_to_v7_view_candidate(
        selected, selected_sha, descriptor["superseded_descriptor_sha256"],
        descriptor["successor_sha"], baseline_sha256=selected["baseline_sha256"],
        inventory_sha256=selected["inventory_sha256"],
        prior_canary_sha256=selected["prior_canary_sha256"])


def validate_superseded_binding(descriptor: dict, *, before: dict | None = None,
                                 artifacts: dict | None = None,
                                 prior_canary: dict | None = None,
                                 historical: bool = False) -> None:
    """Validate the entire selected unstarted lineage against one accepted ancestor.

    No provider recovery, schema translation, or partial-acceptance replay is
    granted. Future carry validation retains this immutable selected binding,
    but compares live prestate only before this successor starts acceptance.
    ``historical`` is set only by the carry-chain walk (``validate_prior_carry_binding``). At
    acceptance start that walk also visits the candidate's own selected link; the strict call that
    follows it, like ``prepare``'s, leaves ``historical`` unset, so a candidate must pass without it.
    A v5-to-v7 descriptor enters only through its internal old-mode view, so
    its selected link still admits exactly one original unstarted
    ``supersede_preproof_v1`` preparation and nothing newer.
    """
    if descriptor["schema_version"] == SCHEMA_UNSTARTED_PREPROOF_V5_TO_V7:
        descriptor = _unstarted_preproof_v5_to_v7_view(descriptor)
    if descriptor["schema_version"] not in {SCHEMA_SUPERSEDE, SCHEMA_PREJOB, SCHEMA_PREPROOF,
                                            SCHEMA_UNSTARTED_PREPROOF}:
        raise MaintenanceError("invalid supersession schema")
    seen = {descriptor["successor_sha"]}
    while True:
        preproof = descriptor["schema_version"] == SCHEMA_PREPROOF
        unstarted_preproof = descriptor["schema_version"] == SCHEMA_UNSTARTED_PREPROOF
        prejob = descriptor["schema_version"] == SCHEMA_PREJOB
        if unstarted_preproof:
            selected_sha = descriptor["superseded_unstarted_preproof_sha"]
        elif preproof:
            selected_sha = descriptor["interrupted_preproof_sha"]
        elif prejob:
            selected_sha = descriptor["interrupted_prejob_sha"]
        else:
            selected_sha = descriptor["superseded_unstarted_sha"]
        if selected_sha in seen:
            raise MaintenanceError("unstarted supersession chain is cyclic")
        if len(seen) >= _MAX_SUPERSEDE_DEPTH:
            raise MaintenanceError("unstarted supersession chain is too deep")
        seen.add(selected_sha)
        selected = _validate_superseded_link(
            descriptor, before=before, artifacts=artifacts, prior_canary=prior_canary,
            historical=historical)
        # (iv) After a PREPROOF link validates with prior_canary provided, every
        # deeper link's expected canary is the selected bundle's sealed prior
        # canary. Re-read it once, require digest == descriptor.prior_canary_sha256,
        # and propagate the parsed value forward. SUPERSEDE / PREJOB inner links
        # inherit that exact canary as today (since all selected bundles in the
        # interrupted run were sealed with the same envelope). An unstarted
        # pre-proof link inherits it the same way: its selected bundle is sealed
        # with that exact envelope.
        if (preproof or unstarted_preproof) and prior_canary is not None:
            next_canary = sealed_json(bundle_path(selected_sha)/"prior-secret-canary.json")
            if digest(next_canary) != selected["prior_canary_sha256"]:
                raise MaintenanceError("superseded sealed baseline drifted")
            prior_canary = next_canary
        if selected["schema_version"] == SCHEMA_V2:
            return
        descriptor = selected


def _validate_superseded_link(descriptor: dict, *, before: dict | None,
                              artifacts: dict | None, prior_canary: dict | None,
                              historical: bool = False) -> dict:
    schema = descriptor["schema_version"]
    preproof = schema == SCHEMA_PREPROOF
    unstarted_preproof = schema == SCHEMA_UNSTARTED_PREPROOF
    prejob = schema == SCHEMA_PREJOB
    if unstarted_preproof:
        selected_sha = descriptor["superseded_unstarted_preproof_sha"]
    elif preproof:
        selected_sha = descriptor["interrupted_preproof_sha"]
    elif prejob:
        selected_sha = descriptor["interrupted_prejob_sha"]
    else:
        selected_sha = descriptor["superseded_unstarted_sha"]
    selected = descriptor_for(selected_sha)
    if unstarted_preproof:
        # Only this mode selects an original supersede_preproof_v1 release, and
        # only while it is still the untouched preparation: the exact six-entry
        # namespace below admits no run marker, acceptance leaf or carry
        # receipt, and never any newer selected type.
        allowed = {SCHEMA_PREPROOF}
    elif preproof:
        allowed = {SCHEMA_V2, SCHEMA_SUPERSEDE, SCHEMA_PREJOB, SCHEMA_PREPROOF}
    elif prejob:
        allowed = {SCHEMA_V2, SCHEMA_SUPERSEDE, SCHEMA_PREJOB}
    else:
        allowed = {SCHEMA_V2, SCHEMA_SUPERSEDE}
    if (selected is None or selected["schema_version"] not in allowed
            or digest(selected) != descriptor["superseded_descriptor_sha256"]
            or selected["predecessor_sha"] != descriptor["predecessor_sha"]):
        raise MaintenanceError("superseded descriptor or accepted ancestor mismatch")
    # Every V2 semantic carry field stays exactly bound; only release identity
    # and the successor's newly created backup bytes may differ.
    shared = _DESCRIPTOR_V2_KEYS - {"schema_version", "successor_sha", "backup_sha256"}
    if preproof:
        # The pre-proof link's canary rule binds the envelope digest instead of
        # the shared prior_canary_sha256, which for PREPROOF holds the live receipt.
        shared = shared - {"prior_canary_sha256"}
    if any(selected[key] != descriptor[key] for key in shared):
        raise MaintenanceError("superseded sealed binding differs from successor")
    bundle = bundle_path(selected_sha)
    expected = {"descriptor.json", "preparing.json", "baseline.json", "inventory.json",
                "prior-secret-canary.json", "prestate.sqlite3"}
    if prejob or preproof:
        expected.add("run-started.json")
    entries = {entry.name for entry in bundle.iterdir()}
    legacy_pair = {"prestate.sqlite3-wal", "prestate.sqlite3-shm"}
    if entries not in (expected, expected | legacy_pair):
        raise MaintenanceError("superseded bundle contains acceptance or partial state")
    if sealed_json(bundle/"preparing.json") != {"schema_version": selected["schema_version"]}:
        raise MaintenanceError("superseded preparation state is invalid")
    from ops.executive_os.autonomy_control import RUNTIME_ROOT
    if prejob:
        if (sealed_json(bundle/"run-started.json") != {
                "schema_version": selected["schema_version"], "descriptor_sha256": digest(selected)}
                or prejob_evidence(selected_sha, historical=historical)
                != descriptor["prejob_evidence_sha256"]):
            raise MaintenanceError("interrupted pre-Job evidence drifted")
    elif preproof:
        if (sealed_json(bundle/"run-started.json") != {
                "schema_version": selected["schema_version"], "descriptor_sha256": digest(selected)}):
            raise MaintenanceError("interrupted pre-proof evidence drifted")
        evidence, envelope = preproof_evidence(selected_sha)
        if evidence != descriptor["preproof_evidence_sha256"]:
            raise MaintenanceError("interrupted pre-proof evidence drifted")
    else:
        _require_runtime_acceptance_absent(RUNTIME_ROOT/"control"/"acceptance"/selected_sha)
    baseline = sealed_json(bundle/"baseline.json")
    inventory_value = sealed_json(bundle/"inventory.json")
    canary = sealed_json(bundle/"prior-secret-canary.json")
    if preproof:
        # (i) envelope digest binds the descriptor's prior_canary_sha256 value,
        # (ii) on strict calls prior_canary must equal envelope parsed, and
        # (iii) the sealed prior-secret-canary.json must still digest to the
        # selected descriptor's own prior_canary_sha256. The legacy canary vs.
        # prior_canary comparison is replaced by the envelope check above.
        if (digest(baseline) != selected["baseline_sha256"]
                or digest(inventory_value) != selected["inventory_sha256"]
                or digest(canary) != selected["prior_canary_sha256"]
                or sealed_backup_snapshot(bundle/"prestate.sqlite3", selected["backup_sha256"]) != baseline
                or (before is not None and baseline != before)
                or (artifacts is not None and inventory_value != artifacts)):
            raise MaintenanceError("superseded sealed baseline drifted")
        if digest(envelope) != descriptor["prior_canary_sha256"]:
            raise MaintenanceError("interrupted pre-proof canary binding drifted")
        if prior_canary is not None and prior_canary != envelope:
            raise MaintenanceError("interrupted pre-proof canary binding drifted")
    else:
        if (digest(baseline) != selected["baseline_sha256"]
                or digest(inventory_value) != selected["inventory_sha256"]
                or digest(canary) != selected["prior_canary_sha256"]
                or sealed_backup_snapshot(bundle/"prestate.sqlite3", selected["backup_sha256"]) != baseline
                or (before is not None and baseline != before)
                or (artifacts is not None and inventory_value != artifacts)
                or (prior_canary is not None and canary != prior_canary)):
            raise MaintenanceError("superseded sealed baseline drifted")
    versions = [row.get("version") for row in baseline["tables"].get("schema_migrations", [])]
    if not versions or any(type(version) is not int for version in versions) or max(versions) != 5:
        raise MaintenanceError("supersession requires unchanged schema v5")
    return selected



class _UnstartedPreproofGuard:
    """Retain identities, not payloads or authority, under exclusive Root custody.

    Semantic validation remains in the incumbent readers. Ancestors retain
    their named inode/type/custody; admitted namespaces and leaves retain their
    complete stat identity. This is not a lock against another Root writer.
    """
    def __init__(self):
        self.nodes = {}
        self.namespaces = {}
        self.absences = {}
        self.aliases = {}

    def __enter__(self):
        return self

    def close(self):
        nodes, self.nodes = self.nodes, {}
        for node in reversed(list(nodes.values())):
            os.close(node[0])

    def __exit__(self, kind, error, traceback):
        self.close()
        return False

    @staticmethod
    def _ancestor_identity(info):
        # Creating our own private candidate changes a shared parent's times,
        # size and link count. Its named inode/type/custody must stay fixed.
        return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)

    def _hold(self, path: Path, *, directory: bool, exact: bool = False):
        if (not path.is_absolute() or '..' in path.parts or '.' in path.parts):
            raise MaintenanceError("retained supersession path is not absolute canonical data")
        if path in self.nodes:
            fd, initial, parent_fd, name, full = self.nodes[path]
            if exact and not full:
                self.nodes[path] = (fd, initial, parent_fd, name, True)
            self.check()
            return fd
        if path == Path('/'):
            parent_fd, name = None, '/'
        else:
            parent_fd = self._hold(path.parent, directory=True)
            name = path.name
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        if directory:
            flags |= os.O_DIRECTORY
        fd = os.open(name, flags, dir_fd=parent_fd)
        try:
            initial = os.fstat(fd)
            named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if (_identity(initial) != _identity(named)
                    or not (stat.S_ISDIR(initial.st_mode) if directory
                            else stat.S_ISREG(initial.st_mode))):
                raise MaintenanceError("retained supersession entry is unsafe")
            self.nodes[path] = (fd, initial, parent_fd, name, exact)
        except BaseException:
            os.close(fd)
            raise
        return fd

    def file(self, path: Path):
        self._hold(self._runtime_path(path), directory=False, exact=True)

    def tree(self, path: Path):
        """Hold only immediate admitted entries; never read backup/sidecar bytes."""
        fd = self._hold(path, directory=True, exact=True)
        names = tuple(sorted(os.listdir(fd)))
        if path in self.namespaces and names != self.namespaces[path]:
            raise MaintenanceError("retained supersession namespace changed")
        self.namespaces[path] = names
        for name in names:
            self.file(path / name)
        self.check()

    def _runtime_path(self, logical: Path):
        expected_parent = _MACOS_VAR_ALIAS / 'db/mastermind-executive/control/acceptance'
        expected_canary = (_MACOS_VAR_ALIAS /
                           'db/mastermind-executive/control/canaries/secret-canary.json')
        if (sys.platform == 'darwin' and (
                (logical.parent == expected_parent and _SHA.fullmatch(logical.name) is not None)
                or logical == expected_canary)):
            info = _MACOS_VAR_ALIAS.lstat()
            target = os.readlink(_MACOS_VAR_ALIAS)
            if (not stat.S_ISLNK(info.st_mode) or info.st_uid != _TRUSTED_UID
                    or target not in ('private/var', os.fspath(_MACOS_VAR_PHYSICAL))):
                raise MaintenanceError("Runtime /var alias is not trusted")
            observation = (_identity(info), target)
            if (_MACOS_VAR_ALIAS in self.aliases
                    and self.aliases[_MACOS_VAR_ALIAS] != observation):
                raise MaintenanceError("retained Runtime alias changed")
            self.aliases[_MACOS_VAR_ALIAS] = observation
            return _MACOS_VAR_PHYSICAL / logical.relative_to(_MACOS_VAR_ALIAS)
        return logical

    def absent(self, logical: Path):
        path = self._runtime_path(logical)
        fd = self._hold(path.parent, directory=True)
        self.absences[path] = fd
        self.check()

    def lineage(self, descriptor: dict):
        from ops.executive_os.autonomy_control import RUNTIME_ROOT
        keys = {SCHEMA_SUPERSEDE: 'superseded_unstarted_sha',
                SCHEMA_PREJOB: 'interrupted_prejob_sha',
                SCHEMA_PREPROOF: 'interrupted_preproof_sha',
                SCHEMA_UNSTARTED_PREPROOF: 'superseded_unstarted_preproof_sha'}
        seen = {descriptor['successor_sha']}
        while descriptor['schema_version'] in keys:
            schema = descriptor['schema_version']
            selected_sha = descriptor[keys[schema]]
            if selected_sha in seen or len(seen) >= _MAX_SUPERSEDE_DEPTH:
                raise MaintenanceError("retained supersession chain is cyclic or too deep")
            seen.add(selected_sha)
            self.tree(bundle_path(selected_sha))
            logical = RUNTIME_ROOT / 'control/acceptance' / selected_sha
            if schema in {SCHEMA_PREJOB, SCHEMA_PREPROOF}:
                self.tree(self._runtime_path(logical))
            else:
                self.absent(logical)
            descriptor = descriptor_for(selected_sha)
            if descriptor is None:
                raise MaintenanceError("retained supersession descriptor disappeared")
            self.check()

    def check(self):
        for path, (fd, initial, parent_fd, name, full) in self.nodes.items():
            held = os.fstat(fd)
            named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            identity = _identity if full else self._ancestor_identity
            if identity(held) != identity(initial) or identity(named) != identity(initial):
                raise MaintenanceError("retained supersession identity changed")
        for path, names in self.namespaces.items():
            if tuple(sorted(os.listdir(self.nodes[path][0]))) != names:
                raise MaintenanceError("retained supersession namespace changed")
        for path, parent_fd in self.absences.items():
            try:
                os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise MaintenanceError("superseded release already has acceptance state")
        for path, observation in self.aliases.items():
            if (_identity(path.lstat()), os.readlink(path)) != observation:
                raise MaintenanceError("retained Runtime alias changed")


def _requalify_unstarted_preproof(descriptor, config, database, before, artifacts,
                                 prior_canary, guard):
    """Fresh semantic reads followed by retained identity checks at the write edge."""
    from control_plane.executive_runtime import Runtime
    guard.check()
    current = snapshot(database)
    if current != before:
        raise MaintenanceError("maintenance live baseline changed before publication")
    canary = json.loads(Path(config['secret_canary_receipt_path']).read_text())
    if canary != prior_canary or digest(canary) != descriptor['prior_canary_sha256']:
        raise MaintenanceError("maintenance live canary changed before publication")
    guard.lineage(descriptor)
    validate_superseded_binding(descriptor, before=current, artifacts=artifacts,
                                 prior_canary=canary)
    runtime = Runtime.at(config['runtime_root'], create=False)
    root = runtime.jobs.get_job(descriptor['root_job_id'])
    if root is None:
        raise MaintenanceError("terminal carry root disappeared")
    _proof, fields = terminal_carry_fields(
        runtime, root, config, current, descriptor['predecessor_sha'], descriptor['successor_sha'])
    if any(descriptor[key] != value for key, value in fields.items()):
        raise MaintenanceError("terminal carry semantic evidence changed")
    if snapshot(database) != current:
        raise MaintenanceError("maintenance live baseline changed during terminal validation")
    verify_inventory(artifacts)
    roots = [Path(config[key]) for key in
             ('proof_workspace_root', 'worker_runs_root', 'receipts_root', 'backup_root')]
    roots.append(Path(config['runtime_root']).parent.parent / 'canary-fixtures')
    if inventory(roots) != artifacts:
        raise MaintenanceError("maintenance live inventory changed before publication")
    guard.check()


def _v5_to_v7_selector(args: argparse.Namespace) -> str | None:
    selected = getattr(args, "supersede_unstarted_preproof_v5_to_v7_sha", None)
    if selected is not None and (not isinstance(selected, str)
                                 or _SHA.fullmatch(selected) is None):
        raise MaintenanceError("invalid selected v5 release")
    return selected


def _v5_to_v7_gates(args: argparse.Namespace, config: dict, selected_sha: str) -> None:
    """Admission gates shared by the source-only preflight and issuance.

    The installed release must still be the selected v5 one, every control
    intake arm and the worker harness must stay closed, the services must be
    stopped, and exactly the new selector may be present — never an old
    selector, a recovery grant or a mixed action.
    """
    if os.geteuid() != 0 or sys.platform != "darwin":
        raise MaintenanceError("maintenance preparation requires root on macOS")
    require_stopped()
    require_disarmed(config)
    worker_config = json.loads((SYSTEM_ROOT/"config/worker-codex.json").read_text())
    if worker_config.get("operator_harness_armed") is not False:
        raise MaintenanceError("maintenance requires closed worker harness")
    if (any(bool(getattr(args, name, None)) for name in
            ("supersede_unstarted_sha", "supersede_prejob_sha", "supersede_preproof_sha",
             "supersede_unstarted_preproof_sha"))
            or getattr(args, "recovery_job_id", None) or getattr(args, "recovery_attempt_id", None)):
        raise MaintenanceError("the v5-to-v7 selector admits no mixed action, recovery or old selector")
    selected_digest = getattr(args, "superseded_descriptor_sha256", None)
    if (not isinstance(selected_digest, str) or _DIGEST.fullmatch(selected_digest) is None
            or selected_sha in {args.predecessor_sha, args.successor_sha}
            or not getattr(args, "carry_terminal_dispatch", False)):
        raise MaintenanceError("supersession requires distinct terminal-carry releases")
    if config["proof_base_sha"] != selected_sha:
        raise MaintenanceError("predecessor differs from installed release")


def _v5_to_v7_view_candidate(selected: dict, selected_sha: str, selected_digest: str,
                             successor_sha: str, *, baseline_sha256: str,
                             inventory_sha256: str, prior_canary_sha256: str) -> dict:
    """Derive the internal old-mode view from the selected v5 descriptor alone.

    Only the selected descriptor's own retained v5 fields plus the verified
    source snapshot/inventory/canary digests enter the view; no working v7
    hash ever replaces a selected v5 hash.
    """
    if (selected["schema_version"] != SCHEMA_PREPROOF
            or digest(selected) != selected_digest
            or selected_sha == successor_sha
            or _SHA.fullmatch(selected_sha) is None
            or _DIGEST.fullmatch(baseline_sha256) is None
            or _DIGEST.fullmatch(inventory_sha256) is None
            or _DIGEST.fullmatch(prior_canary_sha256) is None):
        raise MaintenanceError("superseded descriptor or accepted ancestor mismatch")
    return dict({key: selected[key] for key in _DESCRIPTOR_V2_KEYS},
                schema_version=SCHEMA_UNSTARTED_PREPROOF,
                successor_sha=successor_sha,
                superseded_unstarted_preproof_sha=selected_sha,
                superseded_descriptor_sha256=selected_digest,
                baseline_sha256=baseline_sha256,
                inventory_sha256=inventory_sha256,
                prior_canary_sha256=prior_canary_sha256)


def _v5_to_v7_working_inventory(source_inventory: dict, additions: Any,
                                roots: list[Path]) -> dict:
    """Extend the exact old source inventory with the qualified additions."""
    if (not isinstance(additions, dict) or len(additions) != 8
            or any(not isinstance(entry, dict)
                   or set(entry) != {"uid", "gid", "mode", "nlink", "sha256"}
                   or not isinstance(entry["uid"], int) or not isinstance(entry["gid"], int)
                   or not isinstance(entry["mode"], int) or not isinstance(entry["nlink"], int)
                   or not isinstance(entry["sha256"], str)
                   or _DIGEST.fullmatch(entry["sha256"]) is None
                   for entry in additions.values())):
        raise MaintenanceError("schema upgrade inventory additions are malformed")
    roots = [_runtime_owner_path(root) for root in roots]
    working = dict(source_inventory)
    for name, entry in additions.items():
        path = Path(name)
        if (not isinstance(name, str) or not path.is_absolute() or ".." in path.parts
                or "." in path.parts or name in working
                or not any(path == root or root in path.parents for root in roots)):
            raise MaintenanceError("schema upgrade inventory addition is outside the preserved roots")
        working[name] = dict(entry)
    return working


def _qualified_backup_manifest(created: dict, backup_root: Path, uid: int,
                               gid: int) -> dict:
    """Bind the receipt's backup identity to the actual backup manifest."""
    from ops.executive_os.autonomy_control import _root_json, HostControlError
    manifest_path = _runtime_owner_path(Path(created["manifest_path"]))
    try:
        manifest, _raw = _root_json(manifest_path, modes=frozenset({0o600}), uid=uid, gid=gid)
    except (HostControlError, OSError, KeyError, ValueError) as exc:
        raise MaintenanceError("maintenance proof backup manifest is unavailable") from exc
    if (not isinstance(manifest, dict)
            or manifest.get("backup_id") != created["backup_id"]
            or manifest.get("created_at") != created["created_at"]
            or manifest.get("database") != {
                "filename": Path(created["database_path"]).name,
                "sha256": created["database_sha256"],
                "size_bytes": created["database_size"]}
            or manifest_path.parent != backup_root):
        raise MaintenanceError("maintenance proof backup manifest drifted from its receipt")
    return manifest


def _v7_restore_receipts(successor_sha) -> dict:
    """Read the four fixed Control receipts through the existing root owner."""
    import pwd
    import grp
    import dataclasses
    from ops.executive_os.autonomy_control import (
        RUNTIME_ROOT, CONTROL_USER, CONTROL_GROUP, _root_json, HostControlError,
    )
    from control_plane import executive_backup as backup
    uid = pwd.getpwnam(CONTROL_USER).pw_uid
    gid = grp.getgrnam(CONTROL_GROUP).gr_gid
    shapes = {
        "backup-created.json": (frozenset({"ok", "result"}),
                                frozenset(field.name for field in dataclasses.fields(backup.BackupReceipt))),
        "backup-verified.json": (frozenset({"ok", "result"}),
                                 frozenset(field.name for field in dataclasses.fields(backup.BackupVerification))),
        "restore-drill.json": (None,
                               frozenset(field.name for field in dataclasses.fields(backup.RestoreDrillReceipt))),
        "restore-applied.json": (None,
                                 frozenset(field.name for field in dataclasses.fields(backup.RestoreReceipt))),
    }
    documents: dict[str, Any] = {}
    for name in _V5_TO_V7_RESTORE_RECEIPTS:
        envelope_keys, result_keys = shapes[name]
        try:
            value, raw = _root_json(
                RUNTIME_ROOT/"control/acceptance"/successor_sha/name,
                modes=frozenset({0o400}), uid=uid, gid=gid)
        except (HostControlError, OSError, KeyError, ValueError) as exc:
            raise MaintenanceError("maintenance restore receipt is unavailable") from exc
        if envelope_keys is not None:
            if (set(value) != envelope_keys or value.get("ok") is not True
                    or not isinstance(value.get("result"), dict)
                    or set(value["result"]) != result_keys):
                raise MaintenanceError("maintenance restore receipt schema drifted")
            documents[name] = value["result"]
        else:
            if not isinstance(value, dict) or set(value) != result_keys:
                raise MaintenanceError("maintenance restore receipt schema drifted")
            documents[name] = value
        documents[name + ":sha256"] = hashlib.sha256(raw).hexdigest()
    return documents


def _validate_v7_restore_receipts(created: dict, verified: dict, drill: dict,
                                  applied: dict, *, backup_root: Path,
                                  database: Path) -> str:
    """Bind the four fixed receipts; return the qualified proof backup name.

    The actual v7 producer format is required: the restore binds the qualified
    proof backup, the created receipt carries the full original backup and
    manifest paths beneath the actual configured backup root, the restored
    database is the genuine configured authoritative store, and no receipt ever
    invents an inode for the live store.
    """
    created_path = created["database_path"]
    manifest_path = created.get("manifest_path")
    if (not isinstance(created_path, str)
            or not isinstance(created["database_sha256"], str)
            or _DIGEST.fullmatch(created["database_sha256"]) is None
            or not isinstance(created["manifest_sha256"], str)
            or _DIGEST.fullmatch(created["manifest_sha256"]) is None
            or not isinstance(manifest_path, str)):
        raise MaintenanceError("maintenance proof backup receipt is invalid")
    if not isinstance(created.get("backup_id"), str) or not created["backup_id"]:
        raise MaintenanceError("maintenance proof backup receipt is invalid")
    # The full original addresses join the actual configured backup root; a
    # basename or a foreign directory is never a qualified proof backup.
    backup_root = _runtime_owner_path(backup_root)
    database = _runtime_owner_path(database)
    backup_file = _runtime_owner_path(Path(created_path))
    manifest_file = _runtime_owner_path(Path(manifest_path))
    if (not backup_file.is_absolute() or not manifest_file.is_absolute()
            or backup_file.parent != backup_root or manifest_file.parent != backup_root
            or backup_file.name == manifest_file.name
            or backup_file.name in {".", ".."}):
        raise MaintenanceError("maintenance proof backup path is not under the backup root")
    verified_manifest_path = verified.get("manifest_path")
    verified_manifest_sha = verified.get("manifest_sha256")
    if (not isinstance(verified_manifest_path, str) or not verified_manifest_sha
            or verified_manifest_sha != created["manifest_sha256"]):
        raise MaintenanceError("maintenance proof backup receipts disagree")
    if (created["database_sha256"] != verified["database_sha256"]
            or created["manifest_sha256"] != verified["manifest_sha256"]
            or _runtime_owner_path(Path(verified['database_path'])) != backup_file
            or _runtime_owner_path(Path(verified_manifest_path)) != manifest_file):
        raise MaintenanceError("maintenance proof backup receipts disagree")
    if (drill["database_sha256"] != created["database_sha256"]
            or drill["runtime_schema_version"] != 7
            or drill["integrity_check"] != "ok" or drill["foreign_key_check"] != "ok"):
        raise MaintenanceError("maintenance restore drill receipt is invalid")
    for field in ("restored_sha256", "source_backup_sha256", "final_runtime_sha256",
                  "manifest_sha256", "physical_history_digest"):
        value = applied[field]
        if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
            raise MaintenanceError("maintenance restore receipt is missing the v7 producer format")
    if (applied["restored_sha256"] != applied["final_runtime_sha256"]
            or applied["source_backup_sha256"] != created["database_sha256"]
            or applied["manifest_sha256"] != created["manifest_sha256"]
            or _runtime_owner_path(Path(applied["restored_database_path"])) != database):
        raise MaintenanceError("maintenance restore receipt does not bind the qualified proof backup")
    return backup_file.name


def _verify_restore_physical(applied: dict, proof_backup: Path, current: Path | None = None):
    from control_plane import executive_backup as backup
    with backup._readonly_database(proof_backup) as connection:
        physical = backup.physical_history_digest(connection)
        invalidated = connection.execute(
            "SELECT COUNT(*) FROM attempts WHERE execution_mode='OPERATOR_HARNESS' "
            "AND status IN ('CLAIMED','RUNNING','CHECKPOINTED','CANCEL_REQUESTED')"
        ).fetchone()[0]
    if (applied.get('physical_history_digest') != physical
            or type(applied.get('ohf_invalidated_attempts')) is not int
            or applied['ohf_invalidated_attempts'] != invalidated):
        raise MaintenanceError("restore physical history or TX-9 count drifted")
    if current is not None:
        # A normal consistent read transaction includes a running Service's WAL.
        # The physical projection excludes worker heartbeats and OHF invalidation.
        with closing(sqlite3.connect(current.as_uri()+'?mode=ro', uri=True)) as connection:
            connection.execute('BEGIN')
            if backup.physical_history_digest(connection) != physical:
                raise MaintenanceError("postrestore physical history drifted")


def _evidence_owner():
    try:
        from ops.executive_os import schema_upgrade_evidence
    except ImportError as exc:
        raise MaintenanceError(
            "schema upgrade evidence owner is unavailable") from exc
    for name in ("open_v5_to_v7_evidence", "open_retained_v5_to_v7_evidence"):
        if not hasattr(schema_upgrade_evidence, name):
            raise MaintenanceError("schema upgrade evidence owner is unavailable")
    return schema_upgrade_evidence


def _v5_to_v7_projection_digests(evidence: Any, database: Path) -> None:
    """Compare the full v5 projection over source, target and current."""
    from control_plane import executive_backup as backup
    with backup._readonly_database(Path(evidence.source_v5_database)) as connection:
        source = backup.full_v5_content_digest(connection)
    with backup._readonly_database(Path(evidence.target_v7_database)) as connection:
        target = backup.full_v5_content_digest(connection)
    with backup._readonly_database(database) as connection:
        current = backup.full_v5_content_digest(connection)
    observed = evidence.source_v5_content_digest
    if (not isinstance(observed, str) or _DIGEST.fullmatch(observed) is None
            or source != observed or target != observed or current != observed):
        raise MaintenanceError("full v5 content projection drifted across the schema upgrade")


def _v5_to_v7_queued_root(runtime: Any, root: Any, before: dict) -> list[dict]:
    if (root is None or root.status.value != "QUEUED"
            or root.orchestration_role != "aggregation" or root.attempt_count != 0
            or root.current_attempt_id is not None or root.parent_job_id is not None
            or root.root_job_id != root.job_id or root.depth != 0
            or root.constraints.get("operator_harness_armed") is not False
            or not root.orchestration_provenance_digest):
        raise MaintenanceError("preserved root is not an untouched strict-v2 queued root")
    tables = before["tables"]
    if (any(r["status"] not in _TERMINAL for r in tables["attempts"])
            or any(r["held_attempt_id"] is not None for r in tables["worker_quota_classes"])):
        raise MaintenanceError("maintenance runtime is not quiescent")
    events = [r for r in tables["events"]
              if r["job_id"] == root.job_id and r["event_type"] == "JOB_CREATED"]
    if len(events) != 1:
        raise MaintenanceError("preserved root admission is not unique")
    return events


def _qualify_v5_source_only(args: argparse.Namespace, config: dict, *, lock=None,
                            config_holder=None) -> dict:
    """Nonissuing source check; only transient private verification copies write."""
    from control_plane import executive_backup as backup
    selected_sha = _v5_to_v7_selector(args)
    if selected_sha is None:
        raise MaintenanceError("source-only qualification requires the v5-to-v7 selector")
    _v5_to_v7_gates(args, config, selected_sha)
    selected = descriptor_for(selected_sha)
    if selected is None:
        raise MaintenanceError("superseded descriptor or accepted ancestor mismatch")
    with _UnstartedPreproofGuard() as guard:
        database = _quiescent_database(config, lock, guard)
        before = snapshot(database, immutable=True)
        with _v5_preflight_runtime(selected_sha, selected, database, guard) as runtime:
            root = runtime.jobs.get_job(args.root_job_id)
            events = _v5_to_v7_queued_root(runtime, root, before)
            terminal_carry_fields(runtime, root, config, before,
                                  args.predecessor_sha, args.successor_sha)
            artifact_roots = [Path(config[key]) for key in
                ("proof_workspace_root", "worker_runs_root", "receipts_root", "backup_root")]
            artifact_roots.append(Path(config["runtime_root"]).parent.parent/"canary-fixtures")
            artifacts = inventory(artifact_roots)
            canary_path = Path(config["secret_canary_receipt_path"])
            guard.file(canary_path)
            canary_value = json.loads(canary_path.read_text())
            view = _v5_to_v7_view_candidate(
                selected, selected_sha, args.superseded_descriptor_sha256, args.successor_sha,
                baseline_sha256=digest(before), inventory_sha256=digest(artifacts),
                prior_canary_sha256=digest(canary_value))
            guard.lineage(view)
            validate_superseded_binding(view, before=before, artifacts=artifacts,
                                         prior_canary=canary_value)
            release = backup._prove_upgrade_release(args.successor_sha)
            terminal_carry_fields(runtime, root, config, before,
                                  args.predecessor_sha, args.successor_sha)
            if (snapshot(database, immutable=True) != before
                    or _full_v5_digest(database) != _full_v5_digest(
                        bundle_path(selected_sha)/"prestate.sqlite3")
                    or inventory(artifact_roots) != artifacts
                    or json.loads(canary_path.read_text()) != canary_value):
                raise MaintenanceError("maintenance live source changed during qualification")
            validate_superseded_binding(view, before=before, artifacts=artifacts,
                                         prior_canary=canary_value)
            _quiescent_database(config, lock, guard)
            if config_holder is None:
                raise MaintenanceError("qualified control config is not held")
            config_holder.check()
            guard.check()
            return {
                "action": "qualify-v5-source-only",
                "schema_version": SCHEMA_UNSTARTED_PREPROOF_V5_TO_V7,
                "selected_sha": selected_sha,
                "superseded_descriptor_sha256": args.superseded_descriptor_sha256,
                "predecessor_sha": args.predecessor_sha, "successor_sha": args.successor_sha,
                "source_baseline_sha256": digest(before),
                "source_inventory_sha256": digest(artifacts),
                "source_canary_sha256": digest(canary_value),
                "root_event_id": events[0]["event_id"],
                "staged_release_sha": release["release_sha"],
            }


def _requalify_unstarted_preproof_v5_to_v7(descriptor, config, database, before, artifacts,
                                           source_canary, guard, directory, lock=None,
                                           evidence=None):
    """Fresh semantic reads followed by retained identity checks at the write edge.

    The retained source/deeper v5 evidence is re-entered through the internal
    old-mode view without any live v7 comparison, the working v7 prestate and
    inventory are re-read fresh, and the terminal carry fields are re-derived
    from the current read-only Runtime before anything is published.
    """
    if evidence is None:
        raise MaintenanceError("INITIAL schema evidence must be held through publication")
    database = _quiescent_database(config, lock, guard)
    evidence.check()
    current = snapshot(database, immutable=True)
    if current != before:
        raise MaintenanceError("maintenance live baseline changed before publication")
    if json.loads(Path(config['secret_canary_receipt_path']).read_text()) != source_canary:
        raise MaintenanceError("maintenance live canary changed before publication")
    view = _unstarted_preproof_v5_to_v7_view(descriptor)
    selected = descriptor_for(descriptor['superseded_unstarted_preproof_sha'])
    _selected_v5_backup(descriptor['superseded_unstarted_preproof_sha'], selected,
                        guard, evidence.source_v5_content_digest)
    _v5_to_v7_projection_digests(evidence, database)
    if snapshot(Path(evidence.target_v7_database), immutable=True) != current:
        raise MaintenanceError("INITIAL target copy differs from authoritative state")
    guard.lineage(view)
    validate_superseded_binding(view, prior_canary=source_canary)
    runtime = _verification_runtime(Path(evidence.target_v7_database))
    root = runtime.jobs.get_job(descriptor['root_job_id'])
    if root is None:
        raise MaintenanceError("terminal carry root disappeared")
    _proof, fields = terminal_carry_fields(
        runtime, root, config, current, descriptor['predecessor_sha'], descriptor['successor_sha'])
    if any(descriptor[key] != value for key, value in fields.items()):
        raise MaintenanceError("terminal carry semantic evidence changed")
    if snapshot(database, immutable=True) != current:
        raise MaintenanceError("maintenance live baseline changed during terminal validation")
    verify_inventory(artifacts)
    roots = [Path(config[key]) for key in
             ('proof_workspace_root', 'worker_runs_root', 'receipts_root', 'backup_root')]
    roots.append(Path(config['runtime_root']).parent.parent / 'canary-fixtures')
    if inventory(roots) != artifacts:
        raise MaintenanceError("maintenance live inventory changed before publication")
    if {entry.name for entry in directory.iterdir()} != set(_V5_TO_V7_BUNDLE_NAMES):
        raise MaintenanceError("v5-to-v7 preparation bundle is not the closed working namespace")
    guard.tree(directory)
    if evidence is not None:
        evidence.check()
    if lock is not None:
        lock.check()
    guard.check()


def _prepare_v5_to_v7(args: argparse.Namespace, config: dict, guard, *, lock=None,
                      config_holder=None) -> Path:
    selected_sha = _v5_to_v7_selector(args)
    if selected_sha is None:
        raise MaintenanceError("v5-to-v7 issuance requires its own selector")
    _v5_to_v7_gates(args, config, selected_sha)
    _quiescent_database(config, lock, guard)
    with _evidence_owner().open_v5_to_v7_evidence(
            Path(config["runtime_root"]), args.successor_sha) as evidence:
        return _issue_v5_to_v7(args, config, guard, lock=lock,
                               config_holder=config_holder, evidence=evidence)


def _issue_v5_to_v7(args: argparse.Namespace, config: dict, guard, *, lock=None,
                      config_holder=None, evidence=None) -> Path:
    """Issue one v5-to-v7 descriptor over the migrated working v7 prestate.

    The actual source v5 preparation is never relabelled or overwritten: the
    new bundle seals a fresh Root v7 backup, the exact v7 baseline and the
    merged working inventory beside the sealed upgrade evidence and the raw
    source control preimage, while the selected lineage keeps its own v5
    seals and its unchanged admission rules. The canonical admission lock and
    the held qualified config preimage are re-pinned at the last edge before
    the atomic rename, and the lock is released before any Control-owned
    offline migration or normal Service startup.
    """
    from control_plane.executive_runtime import Runtime
    from control_plane import executive_backup as backup
    evidence_owner = _evidence_owner()
    selected_sha = _v5_to_v7_selector(args)
    if selected_sha is None:
        raise MaintenanceError("v5-to-v7 issuance requires its own selector")
    _v5_to_v7_gates(args, config, selected_sha)
    # Staged successor code/asset identity only; this proves no config
    # selection and grants no new authority.
    backup._prove_upgrade_release(args.successor_sha)
    database = _quiescent_database(config, lock, guard)
    evidence.check()
    before = snapshot(database, immutable=True)
    runtime = _verification_runtime(Path(evidence.target_v7_database))
    root = runtime.jobs.get_job(args.root_job_id)
    events = _v5_to_v7_queued_root(runtime, root, before)
    _proof, extra = terminal_carry_fields(
        runtime, root, config, before, args.predecessor_sha, args.successor_sha)
    selected = descriptor_for(selected_sha)
    if selected is None:
        raise MaintenanceError("superseded descriptor or accepted ancestor mismatch")
    source_bundle = bundle_path(selected_sha)
    source_baseline = sealed_json(source_bundle/"baseline.json")
    source_inventory = sealed_json(source_bundle/"inventory.json")
    source_canary = sealed_json(source_bundle/"prior-secret-canary.json")
    if (digest(source_baseline) != selected["baseline_sha256"]
            or digest(source_inventory) != selected["inventory_sha256"]
            or digest(source_canary) != selected["prior_canary_sha256"]
            or source_canary != json.loads(Path(config["secret_canary_receipt_path"]).read_text())):
        raise MaintenanceError("superseded sealed baseline drifted")
    # The live v7 terminal evidence must still bind the selected v5 fields;
    # real semantic drift through the migrations refuses here.
    shared = _DESCRIPTOR_V2_KEYS - {"schema_version", "successor_sha", "backup_sha256",
                                    "baseline_sha256", "inventory_sha256",
                                    "prior_canary_sha256"}
    working_fields = dict(root_job_id=root.job_id, root_identity_sha256=root_identity(root),
                          root_event_id=events[0]["event_id"],
                          root_event_sha256=digest(events[0]), **extra)
    if any(selected[key] != value for key, value in working_fields.items() if key in shared):
        raise MaintenanceError("superseded sealed binding differs from successor")
    view = _v5_to_v7_view_candidate(
        selected, selected_sha, args.superseded_descriptor_sha256, args.successor_sha,
        baseline_sha256=digest(source_baseline), inventory_sha256=digest(source_inventory),
        prior_canary_sha256=digest(source_canary))
    guard.lineage(view)
    validate_superseded_binding(view, prior_canary=source_canary)
    guard.check()
    working_roots = [Path(config[key]) for key in
                     ("proof_workspace_root", "worker_runs_root", "receipts_root", "backup_root")]
    working_roots.append(Path(config["runtime_root"]).parent.parent/"canary-fixtures")
    material = evidence.material
    config_bytes = evidence.control_config_bytes
    if (not isinstance(config_bytes, bytes) or not config_bytes):
        raise MaintenanceError("schema upgrade evidence is malformed")
    # The stable chain is validated exactly as it will be re-derived later;
    # the actual runtime and backup roots and the real Control identity are
    # part of that frozen record.
    evidence_runtime_root, _evidence_backup_root = _validate_v5_to_v7_material(material)
    if evidence_runtime_root != _runtime_owner_path(Path(config["runtime_root"]), guard):
        raise MaintenanceError("schema upgrade evidence runtime root drifted")
    _bind_pre_census_selected(evidence, selected_sha, selected, config_bytes)
    # The separately qualified current Root config preimage is what the
    # owner observed; issuance happens while the installed release is still
    # the selected v5 one, so this is the same preimage this process holds.
    if config_holder is not None and config_bytes != config_holder.raw:
        raise MaintenanceError("schema upgrade evidence control config drifted")
    # The verified source v5 copy must equal the selected preparation's
    # own sealed baseline, and the strict target must equal the live v7.
    if (snapshot(Path(evidence.source_v5_database), immutable=True) != source_baseline
            or snapshot(Path(evidence.target_v7_database), immutable=True) != before):
        raise MaintenanceError("maintenance prestate drifted")
    _selected_v5_backup(selected_sha, selected, guard, evidence.source_v5_content_digest)
    _v5_to_v7_projection_digests(evidence, database)
    artifacts = _v5_to_v7_working_inventory(source_inventory,
                                            evidence.inventory_additions, working_roots)
    if inventory(working_roots) != artifacts:
        raise MaintenanceError("maintenance live inventory changed before publication")
    parent = bundle_path(args.successor_sha).parent
    parent.mkdir(mode=0o755, exist_ok=True)
    parent_info = parent.lstat()
    if parent_info.st_uid != _TRUSTED_UID or not stat.S_ISDIR(parent_info.st_mode) or parent.is_symlink():
        raise MaintenanceError("maintenance bundle parent is not root-owned")
    os.chmod(parent, 0o755)
    _sealed_ancestors(parent/"unused")
    final_bundle = bundle_path(args.successor_sha)
    if final_bundle.exists() or final_bundle.is_symlink():
        raise MaintenanceError("maintenance descriptor already exists; reconcile the existing operation")
    guard.absent(final_bundle)
    bundle = Path(tempfile.mkdtemp(prefix=".preparing-"+args.successor_sha+"-",dir=parent))
    write_sealed(bundle/"preparing.json",{"schema_version":SCHEMA_UNSTARTED_PREPROOF_V5_TO_V7})
    backup_path = bundle/"prestate.sqlite3"
    fd = os.open(backup_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    os.close(fd)
    with closing(sqlite3.connect(Path(evidence.target_v7_database).as_uri()+"?mode=ro&immutable=1", uri=True)) as source, closing(sqlite3.connect(backup_path)) as destination:
        with destination:
            source.backup(destination)
    os.chmod(backup_path,0o400)
    with backup_path.open("rb") as stream:
        os.fsync(stream.fileno())
    if snapshot(backup_path, immutable=True) != before or snapshot(database, immutable=True) != before:
        raise MaintenanceError("runtime changed during maintenance preparation")
    write_sealed(bundle/"prior-secret-canary.json",source_canary)
    write_sealed(bundle/"baseline.json",before)
    write_sealed(bundle/"inventory.json",artifacts)
    descriptor = dict(schema_version=SCHEMA_UNSTARTED_PREPROOF_V5_TO_V7,
        predecessor_sha=args.predecessor_sha,
        successor_sha=args.successor_sha,
        root_job_id=root.job_id,root_identity_sha256=root_identity(root),
        root_event_id=events[0]["event_id"],root_event_sha256=digest(events[0]),
        worker_id=config["worker_id"],quota_class=config["quota_class"],
        baseline_sha256=digest(before),backup_sha256=_file_digest(backup_path),
        inventory_sha256=digest(artifacts),prior_canary_sha256=digest(source_canary),
        superseded_unstarted_preproof_sha=selected_sha,
        superseded_descriptor_sha256=args.superseded_descriptor_sha256,
        schema_upgrade_evidence_sha256=digest(material),
        source_control_config_sha256=hashlib.sha256(config_bytes).hexdigest(),
        **extra)
    write_sealed(bundle/_V5_TO_V7_EVIDENCE_NAME,material)
    write_sealed_bytes(bundle/_V5_TO_V7_SOURCE_CONTROL_NAME,config_bytes)
    write_sealed(bundle/"descriptor.json",descriptor,public=True)
    os.chmod(bundle,0o755)
    directory_fd = os.open(bundle,os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    # A final namespace is published only when every baseline file is durable.
    # Failed preparation directories remain private evidence and are never
    # read by the service, nor deleted by an automatic retry.
    _requalify_unstarted_preproof_v5_to_v7(descriptor, config, database, before,
                                           artifacts, source_canary, guard, bundle,
                                           evidence=evidence, lock=lock)
    # Occupied/replaced/ancestor/alias/marker/barrier/config are re-checked
    # at this exact edge, immediately before the atomic publication.
    if lock is not None:
        lock.check()
    if config_holder is not None:
        config_holder.check()
    os.rename(bundle,final_bundle)
    directory_fd = os.open(parent,os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    descriptor_for(args.successor_sha)
    return final_bundle


def _require_pre_census_stopped() -> None:
    """Preserve the supported readside stop boundary, never stop MCP."""
    require_stopped()
    label = 'com.mastermind.executive.sol-state-relay'
    result = subprocess.run(['/bin/launchctl', 'print', 'system/' + label],
                            capture_output=True, timeout=10)
    absent = f'Could not find service "{label}" in domain for system\n'.encode('ascii')
    if result.returncode != 113 or result.stdout or result.stderr not in (absent, b"Bad request.\n" + absent):
        raise MaintenanceError("Executive relay absence could not be verified")


def _pre_census_absences(database: Path, *, own_qualification: bool = False) -> None:
    from control_plane import executive_backup as backup
    names = (backup._UPGRADE_V5_TO_V6_PREFLIGHT_NAME,
             backup._UPGRADE_V5_TO_V6_COMPLETION_NAME,
             backup._UPGRADE_V6_TO_V7_PREFLIGHT_NAME,
             backup._UPGRADE_V6_TO_V7_COMPLETION_NAME,
             backup.PRE_CENSUS_CONTINUATION_NAME,
             backup.SPENT_PRE_CENSUS_CTIME_RECONCILIATION_NAME,
             backup.SPENT_PRE_CENSUS_CTIME_CONTINUATION_NAME)
    if not own_qualification:
        names += (backup.PRE_CENSUS_QUALIFICATION_NAME,)
    if any(os.path.lexists(database.parent / name) for name in names):
        raise MaintenanceError("pre-census qualification already has receipts or reservation")
    if any(name.startswith('.executive.sqlite3.restore-') for name in os.listdir(database.parent)):
        raise MaintenanceError("pre-census qualification found unresolved restore residue")


def _current_v5_qualification(database: Path, guard) -> dict:
    """Current physical DATA and full semantic proof, never historical prestate."""
    from control_plane import executive_backup as backup
    fd = guard._hold(database, directory=False, exact=True)
    info = os.fstat(fd)
    observed, offset = hashlib.sha256(), 0
    while offset < info.st_size:
        part = os.pread(fd, min(1024 * 1024, info.st_size - offset), offset)
        if not part:
            raise MaintenanceError("current v5 database was truncated")
        observed.update(part)
        offset += len(part)
    with backup._readonly_database(database) as connection:
        _pages, _size, vector = backup._verify_connection(connection, expected_schema_version=5)
        schema = backup.normalized_schema_digest(connection)
        content = backup.full_v5_content_digest(connection)
    guard.check()
    record = dict(path=str(database), device=info.st_dev, inode=info.st_ino,
                  uid=info.st_uid, gid=info.st_gid, mode=stat.S_IMODE(info.st_mode),
                  nlink=info.st_nlink, size=info.st_size, mtime_ns=info.st_mtime_ns,
                  ctime_ns=info.st_ctime_ns, sha256=observed.hexdigest())
    return dict(database=record, normalized_schema_digest=schema,
                full_v5_content_digest=content,
                migration_vector=[item.to_dict() for item in vector])


def _issue_pre_census_qualification(args: argparse.Namespace) -> dict:
    """Issue one Root-to-Control proof for the original operation's safe PRESENT.

    The qualification is deliberately separate from a migration descriptor.
    The original barrier is retained unchanged, its phase remains unknown,
    and only the Control owner may reserve the one-use continuation later.
    """
    from datetime import datetime, timezone
    from control_plane import executive_backup as backup
    if os.geteuid() != 0 or sys.platform != 'darwin':
        raise MaintenanceError("pre-census qualification requires Root on macOS")
    if getattr(args, 'qualify_v5_source_only', False):
        raise MaintenanceError("pre-census qualification cannot mix source-only actions")
    selected_sha = _v5_to_v7_selector(args)
    if selected_sha is None:
        raise MaintenanceError("pre-census qualification requires exact selected v5 source")
    with _RootConfig() as config_holder:
        config = config_holder.value
        _v5_to_v7_gates(args, config, selected_sha)
        _require_pre_census_stopped()
        database = _runtime_owner_path(Path(config['runtime_root']) /
                                       'data/control_plane/executive.sqlite3')
        with backup._open_pre_census_barrier_for_root_issuer(database) as barrier:
            # Optional selectors constrain the actual observed leaf; they do
            # not supply its UUID, expected payload or authority.
            if (getattr(args, 'expected_operation_id', None) not in (None, barrier.payload['operation_id'])
                    or getattr(args, 'expected_barrier_sha256', None) not in (None, barrier.identity['sha256'])):
                raise MaintenanceError("retained barrier CAS selector differs")
            with _ServiceAdmissionLock(config, _pre_census_barrier=barrier) as lock, _UnstartedPreproofGuard() as guard:
                database = _quiescent_database(config, lock, guard)
                _pre_census_absences(database)
                proof = _qualify_v5_source_only(args, config, lock=lock,
                                                 config_holder=config_holder)
                selected = descriptor_for(selected_sha)
                if selected is None:
                    raise MaintenanceError("selected source disappeared")
                view = _v5_to_v7_view_candidate(selected, selected_sha,
                    args.superseded_descriptor_sha256, args.successor_sha,
                    baseline_sha256=proof['source_baseline_sha256'],
                    inventory_sha256=proof['source_inventory_sha256'],
                    prior_canary_sha256=proof['source_canary_sha256'])
                guard.lineage(view)
                guard.file(Path(config['secret_canary_receipt_path']))
                source = _current_v5_qualification(database, guard)
                _selected_v5_backup(selected_sha, selected, guard, source['full_v5_content_digest'])
                descriptor_path = bundle_path(selected_sha)/'descriptor.json'
                descriptor_fd = guard._hold(descriptor_path, directory=False, exact=True)
                raw_descriptor = os.pread(descriptor_fd, _MAX_DOCUMENT_BYTES + 1, 0)
                if len(raw_descriptor) > _MAX_DOCUMENT_BYTES:
                    raise MaintenanceError("selected descriptor exceeds its bound")
                old = barrier.payload
                old_tool = dict(root=old['tool_release_root'], sha=old['release_sha'],
                                tree_sha=old['tool_release_tree_sha'],
                                manifest_sha256=old['tool_release_manifest_sha256'])
                old_seal = _evidence_owner()._verify_pinned_release(
                    Path(old_tool['root']), old_tool['sha'], old_tool['tree_sha'])
                if any(old_seal.get(key) != old_tool[value] for key, value in (
                        ('commit_sha', 'sha'), ('tree_sha', 'tree_sha'),
                        ('manifest_sha256', 'manifest_sha256'))):
                    raise MaintenanceError("original retained migration tool seal differs")
                release = backup._prove_upgrade_release(args.successor_sha)
                new_tool = dict(root=release['release_root'], sha=release['release_sha'],
                                tree_sha=release['release_tree_sha'],
                                manifest_sha256=release['release_manifest_sha256'])
                backup_root = _runtime_owner_path(Path(config['backup_root']), guard)
                payload = dict(schema_version=backup.PRE_CENSUS_QUALIFICATION_SCHEMA,
                    operation_id=old['operation_id'],
                    original_barrier=dict(payload=dict(old), identity=dict(barrier.identity)),
                    original_tool=old_tool, recovery_tool=new_tool, **source,
                    selected_source=dict(sha=selected_sha,
                        descriptor_raw_sha256=hashlib.sha256(raw_descriptor).hexdigest(),
                        descriptor_sha256=digest(selected), source_backup_sha256=selected['backup_sha256'],
                        baseline_sha256=selected['baseline_sha256'],
                        inventory_sha256=selected['inventory_sha256'],
                        prior_canary_sha256=selected['prior_canary_sha256']),
                    source_control_config=dict(path=str(config_holder.path),
                        sha256=hashlib.sha256(config_holder.raw).hexdigest()),
                    host=dict(runtime_root=str(database.parents[2]), backup_root=str(backup_root),
                              control_uid=lock.control_uid, control_gid=lock.control_gid),
                    backup_inventory_sha256=digest(inventory([backup_root])),
                    created_at=datetime.now(timezone.utc).isoformat())
                backup._validate_pre_census_qualification(payload)
                raw = backup._upgrade_receipt_bytes(payload)
                if len(raw) > 64 * 1024:
                    raise MaintenanceError("Root qualification exceeds the protocol bound")
                destination = database.parent / backup.PRE_CENSUS_QUALIFICATION_NAME
                # All source predicates precede creation. Until the final
                # chmod, an interrupted child remains Root-private and is not
                # a Control-readable qualification. It is never auto-deleted.
                before_names = set(os.listdir(lock.state_fd))
                fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                             os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
                try:
                    lock._accept_qualification_creation(destination, before_names)
                    data = memoryview(raw)
                    while data:
                        size = os.write(fd, data)
                        if size <= 0:
                            raise MaintenanceError("Root qualification write was incomplete")
                        data = data[size:]
                    os.fchown(fd, _TRUSTED_UID, lock.control_gid)
                    os.fsync(fd)
                    # Re-derive the complete sealed-source predicates at the
                    # publication boundary; do not replay this on failure.
                    final_proof = _qualify_v5_source_only(args, config, lock=lock,
                                                          config_holder=config_holder)
                    if (final_proof != proof or _current_v5_qualification(database, guard) != source
                            or digest(inventory([backup_root])) != payload['backup_inventory_sha256']
                            or os.path.lexists(database.parent / backup.PRE_CENSUS_CONTINUATION_NAME)):
                        raise MaintenanceError("safe-present source changed before qualification")
                    _pre_census_absences(database, own_qualification=True)
                    final_old_seal = _evidence_owner()._verify_pinned_release(
                        Path(old_tool['root']), old_tool['sha'], old_tool['tree_sha'])
                    if final_old_seal != old_seal:
                        raise MaintenanceError("original migration tool changed before qualification")
                    _require_pre_census_stopped()
                    barrier.check(); config_holder.check(); guard.check(); lock.check()
                    os.fchmod(fd, 0o440)
                    os.fsync(fd)
                finally:
                    os.close(fd)
                backup._fsync_directory(database.parent)
                identity = backup._pre_census_artifact_identity(destination,
                    uid=_TRUSTED_UID, gid=lock.control_gid, mode=0o440)
                barrier.check(); guard.check(); lock.check(); config_holder.check()
                return dict(action='qualify-v5-pre-census-continuation',
                            operation_id=old['operation_id'], qualification_identity=identity)


def _spent_ctime_absences(database: Path, *, own_reconciliation=False) -> None:
    """The old three origins are retained; no later-phase residue is adopted."""
    from control_plane import executive_backup as backup
    forbidden = (backup._UPGRADE_V5_TO_V6_PREFLIGHT_NAME,
                 backup._UPGRADE_V5_TO_V6_COMPLETION_NAME,
                 backup._UPGRADE_V6_TO_V7_PREFLIGHT_NAME,
                 backup._UPGRADE_V6_TO_V7_COMPLETION_NAME,
                 backup.SPENT_PRE_CENSUS_CTIME_CONTINUATION_NAME)
    if not own_reconciliation:
        forbidden += (backup.SPENT_PRE_CENSUS_CTIME_RECONCILIATION_NAME,)
    if any(os.path.lexists(database.parent/name) for name in forbidden):
        raise MaintenanceError("spent ctime admission already has receipts or reservation")
    if (any(os.path.lexists(database.with_name(database.name + suffix))
            for suffix in ("-wal", "-shm", "-journal"))
            or any(name.startswith('.executive.sqlite3.restore-')
                   for name in os.listdir(database.parent))):
        raise MaintenanceError("spent ctime admission has sidecars or restore residue")


def _issue_spent_pre_census_ctime_reconciliation(args: argparse.Namespace) -> dict:
    """Publish one fresh PRESENT proof, retaining the old qualification and intent.

    This closed action does not prove a historical checkpoint phase, migrate,
    checkpoint, clear quarantine, or issue a maintenance descriptor.  A partial
    publication remains spent; no failure path deletes or regenerates it.
    """
    from datetime import datetime, timezone
    from control_plane import executive_backup as backup
    if os.geteuid() != 0 or sys.platform != 'darwin':
        raise MaintenanceError("spent ctime reconciliation requires Root on macOS")
    if (getattr(args, 'qualify_v5_source_only', False)
            or getattr(args, 'qualify_v5_pre_census_continuation', False)):
        raise MaintenanceError("spent ctime reconciliation cannot mix actions")
    selected_sha = _v5_to_v7_selector(args)
    if selected_sha is None:
        raise MaintenanceError("spent ctime reconciliation requires exact selected v5 source")
    with _RootConfig() as config_holder:
        config = config_holder.value
        _v5_to_v7_gates(args, config, selected_sha)
        _require_pre_census_stopped()
        database = _runtime_owner_path(Path(config['runtime_root']) /
                                       'data/control_plane/executive.sqlite3')
        with backup._open_spent_pre_census_for_root_issuer(database) as retained:
            barrier = retained.barrier
            qualification, spent = retained.qualification, retained.spent_continuation
            q = backup._validate_pre_census_qualification(qualification.payload)
            for selector, actual in (
                    ('expected_operation_id', barrier.payload['operation_id']),
                    ('expected_barrier_sha256', barrier.identity['sha256']),
                    ('expected_spent_continuation_sha256', spent.identity['sha256'])):
                if getattr(args, selector, None) not in (None, actual):
                    raise MaintenanceError("spent ctime original operation CAS differs")
            with _ServiceAdmissionLock(config, _pre_census_barrier=barrier) as lock, _UnstartedPreproofGuard() as guard:
                database = _quiescent_database(config, lock, guard)
                backup_root = _runtime_owner_path(Path(config['backup_root']), guard)
                _spent_ctime_absences(database)

                def requalify():
                    proof = _qualify_v5_source_only(args, config, lock=lock,
                                                    config_holder=config_holder)
                    selected = descriptor_for(selected_sha)
                    if selected is None:
                        raise MaintenanceError("spent ctime selected source disappeared")
                    view = _v5_to_v7_view_candidate(selected, selected_sha,
                        args.superseded_descriptor_sha256, args.successor_sha,
                        baseline_sha256=proof['source_baseline_sha256'],
                        inventory_sha256=proof['source_inventory_sha256'],
                        prior_canary_sha256=proof['source_canary_sha256'])
                    guard.lineage(view)
                    guard.file(Path(config['secret_canary_receipt_path']))
                    source = _current_v5_qualification(database, guard)
                    backup._validate_spent_pre_census_ctime_origin(q['database'], source['database'])
                    if any(source[key] != q[key] for key in
                           ('normalized_schema_digest', 'full_v5_content_digest', 'migration_vector')):
                        raise MaintenanceError("spent ctime full v5 source differs")
                    _selected_v5_backup(selected_sha, selected, guard, source['full_v5_content_digest'])
                    descriptor_path = bundle_path(selected_sha)/'descriptor.json'
                    descriptor_fd = guard._hold(descriptor_path, directory=False, exact=True)
                    raw = os.pread(descriptor_fd, _MAX_DOCUMENT_BYTES + 1, 0)
                    if len(raw) > _MAX_DOCUMENT_BYTES:
                        raise MaintenanceError("spent ctime selected descriptor exceeds bound")
                    selected_source = dict(sha=selected_sha,
                        descriptor_raw_sha256=hashlib.sha256(raw).hexdigest(),
                        descriptor_sha256=digest(selected), source_backup_sha256=selected['backup_sha256'],
                        baseline_sha256=selected['baseline_sha256'], inventory_sha256=selected['inventory_sha256'],
                        prior_canary_sha256=selected['prior_canary_sha256'])
                    if (q['selected_source'] != selected_source
                            or q['source_control_config'] != dict(path=str(config_holder.path),
                                sha256=hashlib.sha256(config_holder.raw).hexdigest())
                            or q['host'] != dict(runtime_root=str(database.parents[2]), backup_root=str(backup_root),
                                control_uid=lock.control_uid, control_gid=lock.control_gid)
                            or q['backup_inventory_sha256'] != digest(inventory([backup_root]))):
                        raise MaintenanceError("spent ctime Root source commitments differ")
                    seals = []
                    for tool in (q['original_tool'], q['recovery_tool']):
                        seal = _evidence_owner()._verify_pinned_release(
                            Path(tool['root']), tool['sha'], tool['tree_sha'])
                        if any(seal.get(key) != tool[field] for key, field in (
                                ('commit_sha', 'sha'), ('tree_sha', 'tree_sha'),
                                ('manifest_sha256', 'manifest_sha256'))):
                            raise MaintenanceError("spent ctime historical tool seal differs")
                        seals.append(seal)
                    release = backup._prove_upgrade_release(args.successor_sha)
                    tool = dict(root=release['release_root'], sha=release['release_sha'],
                                tree_sha=release['release_tree_sha'], manifest_sha256=release['release_manifest_sha256'])
                    retained.check(); config_holder.check(); guard.check(); lock.check()
                    return proof, source, seals, tool

                proof, source, seals, tool = requalify()
                payload = dict(schema_version=backup.SPENT_PRE_CENSUS_CTIME_RECONCILIATION_SCHEMA,
                    operation_id=barrier.payload['operation_id'], original_barrier_identity=barrier.identity,
                    qualification_identity=qualification.identity, spent_continuation_identity=spent.identity,
                    recovery_tool=tool, database=source['database'], created_at=datetime.now(timezone.utc).isoformat())
                backup._validate_spent_pre_census_ctime_reconciliation(payload,
                    barrier_payload=barrier.payload, barrier_identity=barrier.identity,
                    qualification_payload=q, qualification_identity=qualification.identity,
                    spent_continuation_payload=spent.payload, spent_continuation_identity=spent.identity)
                raw = backup._upgrade_receipt_bytes(payload)
                if len(raw) > 64 * 1024:
                    raise MaintenanceError("spent ctime reconciliation exceeds bound")
                destination = database.parent/backup.SPENT_PRE_CENSUS_CTIME_RECONCILIATION_NAME
                before_names = set(os.listdir(lock.state_fd))
                fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                             os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
                try:
                    lock._accept_qualification_creation(destination, before_names)
                    data = memoryview(raw)
                    while data:
                        count = os.write(fd, data)
                        if count <= 0:
                            raise MaintenanceError("spent ctime reconciliation write incomplete")
                        data = data[count:]
                    os.fchown(fd, _TRUSTED_UID, lock.control_gid); os.fsync(fd)
                    if requalify() != (proof, source, seals, tool):
                        raise MaintenanceError("spent ctime source changed before publication")
                    _spent_ctime_absences(database, own_reconciliation=True)
                    _require_pre_census_stopped()
                    retained.check(); guard.check(); lock.check(); config_holder.check()
                    os.fchmod(fd, 0o440); os.fsync(fd)
                finally:
                    os.close(fd)
                backup._fsync_directory(database.parent)
                identity = backup._pre_census_artifact_identity(destination,
                    uid=_TRUSTED_UID, gid=lock.control_gid, mode=0o440)
                retained.check(); guard.check(); lock.check(); config_holder.check()
                return dict(action='reconcile-spent-v5-pre-census-ctime',
                            operation_id=payload['operation_id'], reconciliation_identity=identity)


def prepare(args: argparse.Namespace) -> Path:
    if getattr(args, 'reconcile_spent_v5_pre_census_ctime', False):
        result = _issue_spent_pre_census_ctime_reconciliation(args)
        print(json.dumps(result, sort_keys=True))
        return result
    if getattr(args, 'expected_spent_continuation_sha256', None) is not None:
        raise MaintenanceError("spent intent CAS requires the explicit ctime reconciliation action")
    if getattr(args, 'qualify_v5_pre_census_continuation', False):
        result = _issue_pre_census_qualification(args)
        print(json.dumps(result, sort_keys=True))
        return result
    if (getattr(args, 'expected_operation_id', None) is not None
            or getattr(args, 'expected_barrier_sha256', None) is not None
            or getattr(args, 'expected_spent_continuation_sha256', None) is not None):
        raise MaintenanceError("barrier CAS selectors require the explicit qualification action")
    qualify = bool(getattr(args, "qualify_v5_source_only", False))
    v5_to_v7_sha = getattr(args, "supersede_unstarted_preproof_v5_to_v7_sha", None)
    if qualify and v5_to_v7_sha is None:
        raise MaintenanceError("source-only qualification requires the v5-to-v7 selector")
    if v5_to_v7_sha is not None or qualify:
        # The fixed Root control config is qualified through its guarded owner
        # before the canonical lock is opened, and its held identity is re-pinned
        # at the final edge of whichever action runs.
        with _RootConfig() as config_holder:
            config = config_holder.value
            with _ServiceAdmissionLock(config) as lock:
                if qualify:
                    result = _qualify_v5_source_only(args, config, lock=lock,
                                                     config_holder=config_holder)
                    print(json.dumps(result, sort_keys=True))
                    return result
                with _UnstartedPreproofGuard() as guard:
                    return _prepare_v5_to_v7(args, config, guard, lock=lock,
                                             config_holder=config_holder)
    if getattr(args, 'supersede_unstarted_preproof_sha', None):
        with _UnstartedPreproofGuard() as guard:
            return _prepare(args, guard=guard)
    return _prepare(args)

def _prepare(args: argparse.Namespace, *, guard=None) -> Path:
    if os.geteuid() != 0 or sys.platform != "darwin":
        raise MaintenanceError("maintenance preparation requires root on macOS")
    require_stopped()
    config = json.loads((SYSTEM_ROOT/"config/control.json").read_text())
    require_disarmed(config)
    worker_config = json.loads((SYSTEM_ROOT/"config/worker-codex.json").read_text())
    if worker_config.get("operator_harness_armed") is not False:
        raise MaintenanceError("maintenance requires closed worker harness")
    unstarted_sha = getattr(args, "supersede_unstarted_sha", None)
    prejob_sha = getattr(args, "supersede_prejob_sha", None)
    preproof_sha = getattr(args, "supersede_preproof_sha", None)
    unstarted_preproof_sha = getattr(args, "supersede_unstarted_preproof_sha", None)
    if getattr(args, "supersede_unstarted_preproof_v5_to_v7_sha", None) is not None:
        raise MaintenanceError("select one supersession mode")
    supplied = [bool(unstarted_sha), bool(prejob_sha), bool(preproof_sha),
                bool(unstarted_preproof_sha)]
    if sum(supplied) > 1:
        raise MaintenanceError("select one supersession mode")
    selected_sha = unstarted_preproof_sha or preproof_sha or prejob_sha or unstarted_sha
    selected_digest = getattr(args, "superseded_descriptor_sha256", None)
    if bool(selected_sha) != bool(selected_digest):
        raise MaintenanceError("supersession requires an exact selected release and descriptor digest")
    if selected_sha and (not getattr(args, "carry_terminal_dispatch", False)
                         or not isinstance(selected_digest, str)
                         or _DIGEST.fullmatch(selected_digest) is None
                         or selected_sha in {args.predecessor_sha, args.successor_sha}):
        raise MaintenanceError("supersession requires distinct terminal-carry releases")
    if config["proof_base_sha"] != (selected_sha or args.predecessor_sha):
        raise MaintenanceError("predecessor differs from installed release")
    database = Path(config["runtime_root"])/"data/control_plane/executive.sqlite3"
    before = snapshot(database)
    from control_plane.executive_runtime import Runtime
    runtime = Runtime.at(config["runtime_root"], create=False)
    root = runtime.jobs.get_job(args.root_job_id)
    terminal_carry = getattr(args, "carry_terminal_dispatch", False)
    if terminal_carry and (args.recovery_job_id or args.recovery_attempt_id):
        raise MaintenanceError("terminal carry cannot grant predecessor recovery")
    if not terminal_carry and (not args.recovery_job_id or not args.recovery_attempt_id):
        raise MaintenanceError("v1 maintenance requires an exact predecessor recovery")
    proof = None if terminal_carry else runtime.jobs.get_job(args.recovery_job_id)
    if (root is None or (not terminal_carry and proof is None) or root.status.value != "QUEUED"
            or root.orchestration_role != "aggregation" or root.attempt_count != 0
            or root.current_attempt_id is not None or root.parent_job_id is not None
            or root.root_job_id != root.job_id or root.depth != 0
            or (not terminal_carry and root.constraints.get("base_sha") != args.predecessor_sha)
            or root.constraints.get("operator_harness_armed") is not False
            or not root.orchestration_provenance_digest):
        raise MaintenanceError("preserved root is not an untouched strict-v2 queued root")
    tables = before["tables"]
    if (any(r["status"] not in _TERMINAL for r in tables["attempts"])
            or any(r["held_attempt_id"] is not None for r in tables["worker_quota_classes"])
            or (not terminal_carry and any(r["parent_job_id"] == root.job_id for r in tables["jobs"]))):
        raise MaintenanceError("maintenance runtime is not quiescent")
    extra = {}
    if terminal_carry:
        proof, extra = terminal_carry_fields(
            runtime, root, config, before, args.predecessor_sha, args.successor_sha)
    else:
        runtime.workers.proof_capacity_recovery_snapshot(
            proof.job_id,args.recovery_attempt_id,worker_id=config["worker_id"],quota_class=config["quota_class"])
    events = [r for r in tables["events"] if r["job_id"]==root.job_id and r["event_type"]=="JOB_CREATED"]
    if len(events) != 1:
        raise MaintenanceError("preserved root admission is not unique")
    artifact_roots = [Path(config[k]) for k in ("proof_workspace_root","worker_runs_root","receipts_root","backup_root")]
    artifact_roots.append(Path(config["runtime_root"]).parent.parent/"canary-fixtures")
    artifacts = inventory(artifact_roots)
    prior_canary = Path(config["secret_canary_receipt_path"])
    if guard is not None:
        guard.file(prior_canary)
    prior_canary_value = json.loads(prior_canary.read_text())
    schema = (SCHEMA_UNSTARTED_PREPROOF if unstarted_preproof_sha else
              SCHEMA_PREPROOF if preproof_sha else (
        SCHEMA_PREJOB if prejob_sha else (
            SCHEMA_SUPERSEDE if selected_sha else (SCHEMA_V2 if terminal_carry else SCHEMA))))
    if selected_sha:
        # Qualify every selected seal and the actual prestate before any new
        # preparation directory or marker is written.
        selected_fields = dict(superseded_descriptor_sha256=selected_digest)
        if prejob_sha:
            selected_fields.update(interrupted_prejob_sha=prejob_sha,
                                   prejob_evidence_sha256=prejob_evidence(prejob_sha))
        elif preproof_sha:
            digest_evidence, _envelope = preproof_evidence(preproof_sha)
            selected_fields.update(interrupted_preproof_sha=preproof_sha,
                                   preproof_evidence_sha256=digest_evidence)
        elif unstarted_preproof_sha:
            # The selected pre-proof release never started: its own sealed
            # descriptor still carries the deeper interrupted evidence, and the
            # walk re-asserts it before any new publication.
            selected_fields["superseded_unstarted_preproof_sha"] = unstarted_preproof_sha
        else:
            selected_fields["superseded_unstarted_sha"] = selected_sha
        candidate = dict(schema_version=schema, predecessor_sha=args.predecessor_sha,
            successor_sha=args.successor_sha, root_job_id=root.job_id,
            root_identity_sha256=root_identity(root), root_event_id=events[0]["event_id"],
            root_event_sha256=digest(events[0]), worker_id=config["worker_id"],
            quota_class=config["quota_class"], baseline_sha256=digest(before),
            inventory_sha256=digest(artifacts), prior_canary_sha256=digest(prior_canary_value),
            **selected_fields, **extra)
        if guard is not None:
            guard.lineage(candidate)
        validate_superseded_binding(candidate, before=before, artifacts=artifacts,
                                     prior_canary=prior_canary_value)
        if guard is not None:
            guard.check()
        extra.update(selected_fields)
    parent = bundle_path(args.successor_sha).parent
    parent.mkdir(mode=0o755, exist_ok=True)
    parent_info = parent.lstat()
    if parent_info.st_uid != _TRUSTED_UID or not stat.S_ISDIR(parent_info.st_mode) or parent.is_symlink():
        raise MaintenanceError("maintenance bundle parent is not root-owned")
    os.chmod(parent, 0o755)
    _sealed_ancestors(parent/"unused")
    final_bundle = bundle_path(args.successor_sha)
    if final_bundle.exists() or final_bundle.is_symlink():
        raise MaintenanceError("maintenance descriptor already exists; reconcile the existing operation")
    if guard is not None:
        guard.absent(final_bundle)
    bundle = Path(tempfile.mkdtemp(prefix=".preparing-"+args.successor_sha+"-",dir=parent))
    write_sealed(bundle/"preparing.json",{"schema_version":schema})
    backup = bundle/"prestate.sqlite3"
    fd = os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    os.close(fd)
    with sqlite3.connect(database.as_uri()+"?mode=ro",uri=True) as source, sqlite3.connect(backup) as destination:
        source.backup(destination)
    os.chmod(backup,0o400)
    with backup.open("rb") as stream:
        os.fsync(stream.fileno())
    if snapshot(backup, immutable=True) != before or snapshot(database) != before:
        raise MaintenanceError("runtime changed during maintenance preparation")
    write_sealed(bundle/"prior-secret-canary.json",prior_canary_value)
    write_sealed(bundle/"baseline.json",before)
    write_sealed(bundle/"inventory.json",artifacts)
    descriptor = dict(schema_version=schema,predecessor_sha=args.predecessor_sha,
        successor_sha=args.successor_sha,root_job_id=root.job_id,root_identity_sha256=root_identity(root),
        root_event_id=events[0]["event_id"],root_event_sha256=digest(events[0]),
        worker_id=config["worker_id"],quota_class=config["quota_class"],
        baseline_sha256=digest(before),backup_sha256=_file_digest(backup),inventory_sha256=digest(artifacts),
        prior_canary_sha256=digest(prior_canary_value))
    descriptor.update(extra if terminal_carry else {
        "recovery_job_id": proof.job_id, "recovery_attempt_id": args.recovery_attempt_id,
        "recovery_job_sha256": digest(proof.to_dict()),
    })
    write_sealed(bundle/"descriptor.json",descriptor,public=True)
    os.chmod(bundle,0o755)
    directory_fd = os.open(bundle,os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    # A final namespace is published only when every baseline file is durable.
    # Failed preparation directories remain private evidence and are never read
    # by the service, nor deleted by an automatic retry.
    if guard is not None:
        _requalify_unstarted_preproof(descriptor, config, database, before, artifacts,
                                      prior_canary_value, guard)
    os.rename(bundle,final_bundle)
    directory_fd = os.open(parent,os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    descriptor_for(args.successor_sha)
    return final_bundle

class Maintenance:
    def __init__(self, sha: str, expected_digest: str, config: dict):
        selected = descriptor_for(sha)
        if selected is None or digest(selected) != expected_digest:
            raise MaintenanceError("maintenance descriptor digest mismatch")
        if selected['schema_version'] == SCHEMA_UNSTARTED_PREPROOF:
            with _UnstartedPreproofGuard() as guard:
                guard.tree(bundle_path(sha))
                guard.file(Path(config['secret_canary_receipt_path']))
                guard.lineage(selected)
                self._initialize(sha, expected_digest, config, guard=guard)
        elif selected['schema_version'] == SCHEMA_UNSTARTED_PREPROOF_V5_TO_V7:
            # The canonical admission lock is held from the first snapshot
            # through the runmarker and released before normal Service
            # startup; the retained evidence walk never requires it.
            with _RootConfig() as current_config:
                if config != current_config.value:
                    raise MaintenanceError("admission config differs from the qualified Root preimage")
                with _UnstartedPreproofGuard() as guard, _ServiceAdmissionLock(current_config.value) as lock:
                    guard.tree(bundle_path(sha))
                    guard.file(Path(config['secret_canary_receipt_path']))
                    guard.lineage(_unstarted_preproof_v5_to_v7_view(selected))
                    self._initialize_v5_to_v7(sha, expected_digest, current_config,
                                              guard=guard, lock=lock)
        else:
            self._initialize(sha, expected_digest, config)

    def _initialize_v5_to_v7(self, sha, expected_digest, config_holder, *, guard, lock):
        """INITIAL evidence and verification-copy decoders stay held to the marker."""
        config = config_holder.value
        self.config = config
        self.bundle = bundle_path(sha)
        self.descriptor = descriptor_for(sha)
        if (self.descriptor is None or digest(self.descriptor) != expected_digest
                or self.descriptor['schema_version'] != SCHEMA_UNSTARTED_PREPROOF_V5_TO_V7):
            raise MaintenanceError("maintenance descriptor schema dispatch changed")
        require_disarmed(config)
        require_stopped()
        self.database = _quiescent_database(config, lock, guard)
        self.before = sealed_json(self.bundle/"baseline.json")
        self.inventory = sealed_json(self.bundle/"inventory.json")
        prior_canary = sealed_json(self.bundle/"prior-secret-canary.json")
        material = sealed_json(self.bundle/_V5_TO_V7_EVIDENCE_NAME)
        source_control = sealed_bytes(self.bundle/_V5_TO_V7_SOURCE_CONTROL_NAME,
                                      _MAX_DOCUMENT_BYTES)
        if (digest(self.before) != self.descriptor['baseline_sha256']
                or digest(self.inventory) != self.descriptor['inventory_sha256']
                or digest(prior_canary) != self.descriptor['prior_canary_sha256']
                or digest(material) != self.descriptor['schema_upgrade_evidence_sha256']
                or hashlib.sha256(source_control).hexdigest()
                != self.descriptor['source_control_config_sha256']
                or sealed_backup_snapshot(self.bundle/'prestate.sqlite3',
                                           self.descriptor['backup_sha256']) != self.before
                or json.loads(Path(config['secret_canary_receipt_path']).read_text()) != prior_canary):
            raise MaintenanceError("maintenance prestate drifted")
        selected_sha = self.descriptor['superseded_unstarted_preproof_sha']
        selected = descriptor_for(selected_sha)
        source_inventory = sealed_json(bundle_path(selected_sha)/'inventory.json')
        roots = [Path(config[key]) for key in
                 ('proof_workspace_root', 'worker_runs_root', 'receipts_root', 'backup_root')]
        roots.append(Path(config['runtime_root']).parent.parent/'canary-fixtures')
        with _evidence_owner().open_v5_to_v7_evidence(
                Path(config['runtime_root']), _v5_to_v7_tool_release(material)) as initial:
            if (_json_data(initial.material) != material
                    or initial.control_config_bytes != config_holder.raw
                    or _validate_v5_to_v7_material(material)[0]
                    != _runtime_owner_path(Path(config['runtime_root']), guard)
                    or snapshot(self.database, immutable=True) != self.before
                    or snapshot(Path(initial.target_v7_database), immutable=True) != self.before
                    or snapshot(Path(initial.source_v5_database), immutable=True)
                    != sealed_json(bundle_path(selected_sha)/'baseline.json')):
                raise MaintenanceError("maintenance INITIAL evidence drifted")
            _bind_pre_census_selected(initial, selected_sha, selected, source_control)
            _selected_v5_backup(selected_sha, selected, guard, initial.source_v5_content_digest)
            _v5_to_v7_projection_digests(initial, self.database)
            additions = _v5_to_v7_working_inventory(source_inventory,
                                                    initial.inventory_additions, roots)
            if additions != self.inventory or inventory(roots) != additions:
                raise MaintenanceError("schema upgrade inventory additions drifted")
            validate_prior_carry_binding(self.descriptor)
            _requalify_unstarted_preproof_v5_to_v7(
                self.descriptor, config, self.database, self.before, self.inventory,
                prior_canary, guard, self.bundle, lock=lock, evidence=initial)
            config_holder.check()
            initial.check()
            lock.check()
            guard.check()
            write_sealed(self.bundle/'run-started.json',
                         {'schema_version': self.descriptor['schema_version'],
                          'descriptor_sha256': digest(self.descriptor)}, public=True)

    def _initialize(self, sha: str, expected_digest: str, config: dict, *, guard=None,
                    v5_to_v7: bool = False, lock=None):
        if v5_to_v7:
            raise MaintenanceError("v5-to-v7 admission requires its INITIAL owner")
        self.config = config
        self.bundle = bundle_path(sha)
        self.descriptor = descriptor_for(sha)
        if self.descriptor is None or digest(self.descriptor) != expected_digest:
            raise MaintenanceError("maintenance descriptor digest mismatch")
        # Expected-digest-before-dispatch and later schema/guard agreement:
        # a header that flips schema between reads cannot skip its own guard.
        if ((self.descriptor['schema_version'] == SCHEMA_UNSTARTED_PREPROOF)
                != (guard is not None and not v5_to_v7)
                or ((self.descriptor['schema_version'] == SCHEMA_UNSTARTED_PREPROOF_V5_TO_V7)
                    != (guard is not None and v5_to_v7))):
            raise MaintenanceError("maintenance descriptor schema dispatch changed")
        validate_prior_carry_binding(self.descriptor)
        require_disarmed(config)
        require_stopped()
        self.database = Path(config["runtime_root"])/"data/control_plane/executive.sqlite3"
        self.before = sealed_json(self.bundle/"baseline.json")
        self.inventory = sealed_json(self.bundle/"inventory.json")
        prior_canary = sealed_json(self.bundle/"prior-secret-canary.json")
        if v5_to_v7:
            material = sealed_json(self.bundle/_V5_TO_V7_EVIDENCE_NAME)
            source_control = sealed_bytes(self.bundle/_V5_TO_V7_SOURCE_CONTROL_NAME,
                                          _MAX_DOCUMENT_BYTES)
        if (digest(prior_canary) != self.descriptor["prior_canary_sha256"]
                or digest(json.loads(Path(config["secret_canary_receipt_path"]).read_text())) != self.descriptor["prior_canary_sha256"]
                or digest(self.before) != self.descriptor["baseline_sha256"]
                or digest(self.inventory) != self.descriptor["inventory_sha256"]
                or _file_digest(self.bundle/"prestate.sqlite3") != self.descriptor["backup_sha256"]
                or snapshot(self.database) != self.before):
            raise MaintenanceError("maintenance prestate drifted")
        if v5_to_v7 and (digest(material) != self.descriptor["schema_upgrade_evidence_sha256"]
                or hashlib.sha256(source_control).hexdigest()
                != self.descriptor["source_control_config_sha256"]):
            raise MaintenanceError("maintenance prestate drifted")
        verify_inventory(self.inventory)
        if self.descriptor["schema_version"] in {SCHEMA_SUPERSEDE, SCHEMA_PREJOB, SCHEMA_PREPROOF,
                                                 SCHEMA_UNSTARTED_PREPROOF}:
            validate_superseded_binding(self.descriptor, before=self.before,
                                         artifacts=self.inventory, prior_canary=prior_canary)
        if v5_to_v7:
            # The retained source/deeper evidence never compares a selected v5
            # hash against the working v7 prestate; the working prestate was
            # already proven current above.
            validate_superseded_binding(_unstarted_preproof_v5_to_v7_view(self.descriptor),
                                         prior_canary=prior_canary)
            if {entry.name for entry in self.bundle.iterdir()} != set(_V5_TO_V7_BUNDLE_NAMES):
                raise MaintenanceError("v5-to-v7 preparation bundle is not the closed working namespace")
        if self.descriptor["schema_version"] in _TERMINAL_CARRY_SCHEMAS:
            from control_plane.executive_runtime import Runtime
            runtime = Runtime.at(config["runtime_root"], create=False)
            root = runtime.jobs.get_job(self.descriptor["root_job_id"])
            if root is None:
                raise MaintenanceError("terminal carry root disappeared")
            _proof, fields = terminal_carry_fields(
                runtime, root, config, self.before, self.descriptor["predecessor_sha"],
            )
            if any(self.descriptor[key] != value for key, value in fields.items()):
                raise MaintenanceError("terminal carry semantic evidence changed")
        def _runmarker():
            write_sealed(self.bundle/"run-started.json",
                         {"schema_version":self.descriptor["schema_version"],"descriptor_sha256":digest(self.descriptor)},public=True)

        if guard is not None and not v5_to_v7:
            _requalify_unstarted_preproof(self.descriptor, config, self.database, self.before,
                                          self.inventory, prior_canary, guard)
        if guard is None or not v5_to_v7:
            _runmarker()

    @property
    def predecessor_recovery_required(self) -> bool:
        return self.descriptor["schema_version"] == SCHEMA

    def verify(self, proof_ids: list[str]) -> None:
        verify_preserved(self.before,snapshot(self.database),self.descriptor,proof_ids)
        verify_inventory(self.inventory)

    def finish(self, proof_ids: list[str], summary: Path) -> None:
        self.verify(proof_ids)
        _value, raw = summary_document(self.descriptor["successor_sha"])
        if self.descriptor["schema_version"] == SCHEMA_UNSTARTED_PREPROOF_V5_TO_V7:
            # The first finish creates the first carry, so it cannot require
            # that nonexistent carry: it proves its own admitted instance and
            # the four real restore receipts before the retained walk.
            self._finish_v5_to_v7(proof_ids, hashlib.sha256(raw).hexdigest())
            return
        write_sealed(self.bundle/"carry-forward.json",dict(
            schema_version=self.descriptor["schema_version"],passed=True,baseline_preserved=True,
            descriptor_sha256=digest(self.descriptor),acceptance_summary_sha256=hashlib.sha256(raw).hexdigest()),public=True)

    def _restore_receipts(self) -> dict:
        return _v7_restore_receipts(self.descriptor['successor_sha'])

    def _finish_v5_to_v7(self, proof_ids: list[str], summary_sha256: str) -> None:
        """Seal the first restore evidence, then the schema-specific PASS carry.

        Every non-circular gate — the admitted instance, run marker,
        descriptor, sealed material and source-config bindings, the real
        current-run PASS summary and all four actual Control 0400 receipts —
        is proven before the retained history owner is opened. The acceptance
        run restarted the Service during backup_restore, so this path never
        requires a stopped service, sidecar absence, a quiescent database or a
        raw-hash match on the live store: it uses the consistent snapshots, the
        unchanged preserved contract and the pinned receipts, and it observes
        the postrestore authority explicitly through a no-follow descriptor
        bracketing the whole finish window.
        """
        import pwd
        import grp
        from ops.executive_os.autonomy_control import CONTROL_USER, CONTROL_GROUP
        restore_path = self.bundle/_V5_TO_V7_RESTORE_EVIDENCE_NAME
        if os.path.lexists(restore_path):
            raise MaintenanceError("acceptance restore evidence already sealed; reconcile the existing operation")
        if (sealed_json(self.bundle/"run-started.json")
                != {"schema_version": self.descriptor["schema_version"],
                    "descriptor_sha256": digest(self.descriptor)}
                or sealed_json(self.bundle/"descriptor.json") != self.descriptor
                or digest(self.before) != self.descriptor["baseline_sha256"]
                or digest(self.inventory) != self.descriptor["inventory_sha256"]
                or digest(sealed_json(self.bundle/_V5_TO_V7_EVIDENCE_NAME))
                != self.descriptor["schema_upgrade_evidence_sha256"]
                or hashlib.sha256(sealed_bytes(self.bundle/_V5_TO_V7_SOURCE_CONTROL_NAME,
                                               _MAX_DOCUMENT_BYTES)).hexdigest()
                != self.descriptor["source_control_config_sha256"]):
            raise MaintenanceError("maintenance admitted instance binding drifted")
        # The real current-run PASS summary and the four real Control receipts
        # are read before any retained history is opened.
        _summary_value, summary_raw = summary_document(self.descriptor["successor_sha"])
        if (hashlib.sha256(summary_raw).hexdigest() != summary_sha256
                or [_summary_value.get('success_job_id'),
                    _summary_value.get('interrupted_requeued_job_id')] != proof_ids):
            raise MaintenanceError("maintenance PASS summary proof jobs drifted")
        receipts = self._restore_receipts()
        created = receipts["backup-created.json"]
        verified = receipts["backup-verified.json"]
        drill = receipts["restore-drill.json"]
        applied = receipts["restore-applied.json"]
        uid = pwd.getpwnam(CONTROL_USER).pw_uid
        gid = grp.getgrnam(CONTROL_GROUP).gr_gid
        runtime_root = Path(self.config["runtime_root"])
        database = _runtime_owner_path(self.database)
        backup_root = _runtime_owner_path(_canonical_root_path(self.config.get("backup_root")))
        backup_name = _validate_v7_restore_receipts(created, verified, drill, applied,
                                                    backup_root=backup_root,
                                                    database=database)
        _qualified_backup_manifest(created, backup_root, uid, gid)
        material = sealed_json(self.bundle/_V5_TO_V7_EVIDENCE_NAME)
        _validate_v5_to_v7_material(material)

        live_guard = _UnstartedPreproofGuard()
        def _observe() -> tuple:
            physical = _runtime_owner_path(database, live_guard)
            fd = live_guard._hold(physical, directory=False)
            info = os.fstat(fd)
            if (info.st_uid != uid or info.st_gid != gid or info.st_nlink != 1
                    or stat.S_IMODE(info.st_mode) != 0o600
                    or has_macos_acl(physical, descriptor=fd, expected_identity=info)):
                raise MaintenanceError("postrestore runtime database custody is invalid")
            live_guard.check()
            return (info.st_dev, info.st_ino, info.st_nlink, info.st_mode)

        try:
            observed = _observe()
            current = snapshot(database)
            verify_preserved(self.before, current, self.descriptor, proof_ids)
            evidence_owner = _evidence_owner()
            with evidence_owner.open_retained_v5_to_v7_evidence(
                    runtime_root, _v5_to_v7_tool_release(material),
                    pinned_material=material) as retained:
                # The stable material is exactly the original INITIAL record in
                # both contexts; the runtime phase stays HISTORICAL and the sealed
                # evidence is never rewritten here.
                if _json_data(retained.material) != material:
                    raise MaintenanceError("sealed schema upgrade evidence is not the original")
                verified_copy = retained.verify_v7_acceptance_backup(
                    backup_name, created["database_sha256"], created["manifest_sha256"])
                derived = getattr(verified_copy, "origin_identities", None)
                if not isinstance(derived, dict) or set(derived) != {"database", "manifest"}:
                    raise MaintenanceError("qualified proof backup origin is invalid")
                origins = {key: _v5_to_v7_origin_record(derived[key])
                           for key in ("database", "manifest")}
                if (origins["database"]["sha256"] != created["database_sha256"]
                        or origins["manifest"]["sha256"] != created["manifest_sha256"]
                        or Path(origins["database"]["path"]).name != backup_name
                        or Path(origins["database"]["path"]).parent != backup_root
                        or Path(origins["manifest"]["path"]).parent != backup_root):
                    raise MaintenanceError("qualified proof backup origin is invalid")
                # Plain detached JSON dicts: the frozen wire never exposes .to_dict
                # objects here, and tuples normalize only at this JSON boundary.
                normalized = dict(_json_data(verified_copy.verification))
                # Only the two explicitly named copy-address fields are normalized
                # to the qualified original addresses; every other field compares.
                normalized["database_path"] = origins["database"]["path"]
                normalized["manifest_path"] = origins["manifest"]["path"]
                verified = dict(verified)
                for key in ('database_path', 'manifest_path'):
                    verified[key] = os.fspath(_runtime_owner_path(Path(verified[key])))
                if _json_data(normalized) != _json_data(verified):
                    raise MaintenanceError("qualified proof backup verification drifted")
                if _json_data(verified_copy.restore_drill) != _json_data(drill):
                    raise MaintenanceError("qualified proof backup restore drill drifted")
                if (origins['database']['path'] != os.fspath(_runtime_owner_path(Path(created['database_path'])))
                        or origins['manifest']['path'] != os.fspath(_runtime_owner_path(Path(created['manifest_path'])))):
                    raise MaintenanceError("qualified proof backup addresses drifted")
                _verify_restore_physical(applied, Path(verified_copy.database), database)
                verify_preserved(self.before, snapshot(Path(verified_copy.database), immutable=True),
                                 self.descriptor, proof_ids)
                retained.check()
                if _observe() != observed:
                    raise MaintenanceError("postrestore runtime database changed during finish")
                current = snapshot(database)
                verify_preserved(self.before, current, self.descriptor, proof_ids)
                restore_evidence = {
                    "schema_version": _V5_TO_V7_RESTORE_EVIDENCE_SCHEMA,
                    "proof_job_ids": list(proof_ids),
                    "acceptance_summary_sha256": summary_sha256,
                    "receipt_sha256": {name: receipts[name + ":sha256"]
                                       for name in _V5_TO_V7_RESTORE_RECEIPTS},
                    "backup": {"name": backup_name,
                               "database_sha256": created["database_sha256"],
                               "manifest_sha256": created["manifest_sha256"]},
                    "origins": {"database": dict(origins["database"]),
                                "manifest": dict(origins["manifest"])},
                    "verification": normalized,
                    "restore_drill": _json_data(drill),
                    "current_runtime_database": {"path": os.fspath(database),
                                                 "device": observed[0], "inode": observed[1]},
                    "schema_upgrade_evidence_sha256": self.descriptor["schema_upgrade_evidence_sha256"],
                }
                if set(restore_evidence) != set(_V5_TO_V7_RESTORE_EVIDENCE_KEYS):
                    raise MaintenanceError("maintenance restore evidence is not the closed shape")
                # The qualified origins are re-checked through the sealed write
                # edge: retained FD/check state still covers them here.
                retained.check()
                if _observe() != observed:
                    raise MaintenanceError("postrestore runtime generation changed before sealing")
                write_sealed(restore_path, restore_evidence)
                retained.check()
                if _observe() != observed:
                    raise MaintenanceError("postrestore runtime generation changed before carry")
                write_sealed(self.bundle/"carry-forward.json",dict(
                    schema_version=self.descriptor["schema_version"],passed=True,baseline_preserved=True,
                    descriptor_sha256=digest(self.descriptor),
                    acceptance_summary_sha256=summary_sha256,
                    schema_upgrade_evidence_sha256=self.descriptor["schema_upgrade_evidence_sha256"],
                    acceptance_restore_evidence_sha256=digest(restore_evidence)),public=True)
                retained.check()
        finally:
            live_guard.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predecessor-sha",required=True)
    parser.add_argument("--successor-sha",required=True)
    parser.add_argument("--root-job-id",required=True)
    parser.add_argument("--recovery-job-id")
    parser.add_argument("--recovery-attempt-id")
    parser.add_argument("--carry-terminal-dispatch", action="store_true",
                        help="Preserve one failed planner and prior PASS chain; grant no predecessor recovery.")
    parser.add_argument("--supersede-unstarted-sha",
                        help="Explicitly retire an installed unstarted V2 release on unchanged schema v5.")
    parser.add_argument("--supersede-prejob-sha",
                        help="Preserve an interrupted V2 pre-Job prefix; never replay its acceptance.")
    parser.add_argument("--supersede-preproof-sha",
                        help="Preserve an acceptance interrupted after service and canary activation but before any proof Job; never replay it.")
    parser.add_argument("--supersede-unstarted-preproof-sha",
                        help="Retire one installed unstarted supersede_preproof_v1 preparation on unchanged schema v5; never replay its acceptance.")
    parser.add_argument("--supersede-unstarted-preproof-v5-to-v7-sha",
                        help="Retire one installed unstarted supersede_preproof_v1 preparation whose source release completed the offline v5->v6->v7 transitions; never relabel or replay its acceptance.")
    parser.add_argument("--qualify-v5-source-only", action="store_true",
                        help="Read-only v5 source qualification paired only with --supersede-unstarted-preproof-v5-to-v7-sha; writes nothing and grants no write authority.")
    parser.add_argument("--qualify-v5-pre-census-continuation", action="store_true",
                        help="Issue one control-readable Root safe-present qualification for the retained original pre-census operation; never migrate, clear its barrier or issue a successor descriptor.")
    parser.add_argument("--reconcile-spent-v5-pre-census-ctime", action="store_true",
                        help="Issue one fixed fresh ctime-only same-operation reconciliation; never replay the spent continuation or checkpoint.")
    parser.add_argument("--expected-spent-continuation-sha256",
                        help="Optional CAS against the immutable spent Control continuation.")
    parser.add_argument("--expected-operation-id",
                        help="Optional CAS comparison against the actual retained barrier UUID.")
    parser.add_argument("--expected-barrier-sha256",
                        help="Optional CAS comparison against the actual retained barrier bytes.")
    parser.add_argument("--superseded-descriptor-sha256",
                        help="Exact selected V2 descriptor digest; predecessor remains its accepted ancestor.")
    args = parser.parse_args()
    try:
        bundle = prepare(args)
        if (getattr(args, "qualify_v5_source_only", False)
                or getattr(args, "qualify_v5_pre_census_continuation", False)
                or getattr(args, "reconcile_spent_v5_pre_census_ctime", False)):
            return 0
        descriptor = descriptor_for(args.successor_sha)
        print(json.dumps({"bundle":str(bundle),"descriptor_sha256":digest(descriptor)}))
        return 0
    except (MaintenanceError,OSError,ValueError) as exc:
        print("maintenance error: "+str(exc),file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
