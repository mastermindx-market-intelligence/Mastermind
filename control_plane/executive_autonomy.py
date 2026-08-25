"""Secret-free receipt law for the Executive OS autonomy boundary.

This module is deliberately pure with respect to Executive lifecycle and host
mutation.  It validates one root-written operational receipt against exact
caller-supplied config and capability identities.  It never opens provider
credentials, starts a process, reads Runtime state, or edits configuration.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping


RECEIPT_SCHEMA_VERSION = "mastermind.executive_autonomy_state/v1"
TOOL_VERSION = "1.0.0"
WORKSPACE_BINDING_CLASS = "company-workspace-admin-attested"
MIN_ADMISSION_MARGIN = timedelta(minutes=30)
MAX_RECEIPT_BYTES = 64 * 1024
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

UNARMED = "UNARMED"
ARMED_READY = "ARMED_READY"
ARMED_DEGRADED = "ARMED_DEGRADED"
TRANSACTION_INCOMPLETE = "TRANSACTION_INCOMPLETE"
CONFIG_DRIFT = "CONFIG_DRIFT"
READINESS_EXPIRED = "READINESS_EXPIRED"
EFFECT_UNKNOWN = "EFFECT_UNKNOWN"

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_TRANSACTION_RE = re.compile(r"^autonomy-[0-9a-f]{12}$")
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_CREDENTIAL_KINDS = frozenset(
    {"service-account", "personal-access-token", "device-auth"}
)
_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "state",
        "release_sha",
        "acceptance_receipt_sha256",
        "gate_b_receipt_sha256",
        "provider_readiness_receipt_sha256",
        "readiness_observed_at",
        "credential_expires_at",
        "readiness_expires_at",
        "expected_credential_kind",
        "workspace_binding_class",
        "prior_control_config_sha256",
        "prior_worker_config_sha256",
        "control_config_sha256",
        "worker_config_sha256",
        "capability_policy_digest",
        "execution_profile_digest",
        "native_helper_grant_digest",
        "security_config_digest",
        "transaction_id",
        "observed_at",
        "tool_version",
        "predicates",
    }
)
_PREDICATE_FIELDS = frozenset(
    {
        "acceptance_passed",
        "configs_validated",
        "gate_b_passed",
        "provider_readiness_passed",
        "runtime_quiescent",
        "service_uids_quiescent",
    }
)
_REFUSAL_CODES = frozenset(
    {
        "non_canonical_json",
        "receipt_not_object",
        "receipt_fields_mismatch",
        "receipt_schema_mismatch",
        "receipt_state_invalid",
        "receipt_release_invalid",
        "release_sha_mismatch",
        "receipt_digest_invalid",
        "acceptance_digest_mismatch",
        "gate_b_digest_mismatch",
        "provider_readiness_digest_mismatch",
        "prior_control_config_digest_invalid",
        "prior_worker_config_digest_invalid",
        "control_config_digest_mismatch",
        "worker_config_digest_mismatch",
        "capability_policy_digest_mismatch",
        "execution_profile_digest_mismatch",
        "native_helper_digest_mismatch",
        "security_config_digest_mismatch",
        "credential_kind_invalid",
        "workspace_binding_mismatch",
        "transaction_id_invalid",
        "tool_version_mismatch",
        "receipt_predicates_invalid",
        "receipt_predicates_failed",
        "receipt_timestamp_malformed",
        "receipt_timestamp_in_future",
        "readiness_timestamp_order_invalid",
        "readiness_expiry_bounds_invalid",
        "readiness_expired",
        "readiness_margin_insufficient",
        "receipt_owner_mismatch",
        "receipt_group_mismatch",
        "receipt_mode_mismatch",
        "receipt_link_count_mismatch",
        "receipt_not_regular",
        "receipt_acl_unsafe",
        "receipt_unavailable",
        "receipt_too_large",
        "receipt_not_utf8_json",
        "receipt_not_armed",
        "runtime_role_invalid",
    }
)


class AutonomyRefusal(RuntimeError):
    """A closed, secret-free autonomy refusal."""

    def __init__(self, code: str):
        if code not in _REFUSAL_CODES:
            raise ValueError("unknown autonomy refusal code")
        self.code = code
        super().__init__(code)


@dataclasses.dataclass(frozen=True)
class ReceiptMetadata:
    uid: int
    gid: int
    mode: int
    nlink: int
    is_regular: bool
    is_symlink: bool
    has_acl: bool


@dataclasses.dataclass(frozen=True)
class AutonomyExpectation:
    release_sha: str
    control_config_sha256: str
    worker_config_sha256: str
    provider_readiness_receipt_sha256: str
    capability_policy_digest: str
    execution_profile_digest: str
    native_helper_grant_digest: str
    security_config_digest: str


@dataclasses.dataclass(frozen=True)
class ArmBinding:
    state: str
    release_sha: str
    control_config_sha256: str
    worker_config_sha256: str
    provider_readiness_receipt_sha256: str
    readiness_observed_at: datetime
    credential_expires_at: datetime
    readiness_expires_at: datetime
    expected_credential_kind: str
    workspace_binding_class: str
    transaction_id: str
    observed_at: datetime


@dataclasses.dataclass(frozen=True)
class StatusEvidence:
    transaction_present: bool
    control_armed: bool
    worker_armed: bool
    receipt_state: str | None
    receipt_matches: bool
    config_drift: bool
    identity_reconciled: bool
    service_state: str
    readiness_expires_at: datetime | None


def canonical_sha256(value: Any) -> str:
    try:
        payload = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise AutonomyRefusal("non_canonical_json") from exc
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise AutonomyRefusal("receipt_unavailable") from exc
    return digest.hexdigest()


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or _TIMESTAMP_RE.fullmatch(value) is None:
        raise AutonomyRefusal("receipt_timestamp_malformed")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise AutonomyRefusal("receipt_timestamp_malformed") from exc


def _require_digest(value: Any, *, invalid_code: str = "receipt_digest_invalid") -> str:
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        raise AutonomyRefusal(invalid_code)
    return value


def _validate_metadata(metadata: ReceiptMetadata) -> None:
    if metadata.is_symlink or not metadata.is_regular:
        raise AutonomyRefusal("receipt_not_regular")
    if metadata.uid != 0:
        raise AutonomyRefusal("receipt_owner_mismatch")
    if metadata.gid != 0:
        raise AutonomyRefusal("receipt_group_mismatch")
    if metadata.mode != 0o444:
        raise AutonomyRefusal("receipt_mode_mismatch")
    if metadata.nlink != 1:
        raise AutonomyRefusal("receipt_link_count_mismatch")
    if metadata.has_acl:
        raise AutonomyRefusal("receipt_acl_unsafe")


def validate_receipt_document(
    payload: Mapping[str, Any],
    *,
    metadata: ReceiptMetadata,
    expected: AutonomyExpectation,
    now: datetime | None = None,
    require_current: bool = True,
) -> ArmBinding:
    """Validate one armed or shrink-only receipt against exact identities."""

    _validate_metadata(metadata)
    if not isinstance(payload, Mapping):
        raise AutonomyRefusal("receipt_not_object")
    if set(payload) != _RECEIPT_FIELDS:
        raise AutonomyRefusal("receipt_fields_mismatch")
    if payload.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        raise AutonomyRefusal("receipt_schema_mismatch")
    state = payload.get("state")
    if state not in {"ARMED", "DISARMED"}:
        raise AutonomyRefusal("receipt_state_invalid")
    release_sha = payload.get("release_sha")
    if not isinstance(release_sha, str) or _SHA_RE.fullmatch(release_sha) is None:
        raise AutonomyRefusal("receipt_release_invalid")
    if release_sha != expected.release_sha:
        raise AutonomyRefusal("release_sha_mismatch")

    digest_checks = (
        ("acceptance_receipt_sha256", None, "acceptance_digest_mismatch"),
        ("gate_b_receipt_sha256", None, "gate_b_digest_mismatch"),
        (
            "provider_readiness_receipt_sha256",
            expected.provider_readiness_receipt_sha256,
            "provider_readiness_digest_mismatch",
        ),
        (
            "prior_control_config_sha256",
            None,
            "prior_control_config_digest_invalid",
        ),
        (
            "prior_worker_config_sha256",
            None,
            "prior_worker_config_digest_invalid",
        ),
        (
            "control_config_sha256",
            expected.control_config_sha256,
            "control_config_digest_mismatch",
        ),
        (
            "worker_config_sha256",
            expected.worker_config_sha256,
            "worker_config_digest_mismatch",
        ),
        (
            "capability_policy_digest",
            expected.capability_policy_digest,
            "capability_policy_digest_mismatch",
        ),
        (
            "execution_profile_digest",
            expected.execution_profile_digest,
            "execution_profile_digest_mismatch",
        ),
        (
            "native_helper_grant_digest",
            expected.native_helper_grant_digest,
            "native_helper_digest_mismatch",
        ),
        (
            "security_config_digest",
            expected.security_config_digest,
            "security_config_digest_mismatch",
        ),
    )
    for field, wanted, mismatch_code in digest_checks:
        value = _require_digest(payload.get(field))
        if wanted is not None and value != wanted:
            raise AutonomyRefusal(mismatch_code)

    kind = payload.get("expected_credential_kind")
    if state == "ARMED" and kind not in _CREDENTIAL_KINDS:
        raise AutonomyRefusal("credential_kind_invalid")
    if state == "DISARMED" and kind != "none":
        raise AutonomyRefusal("credential_kind_invalid")
    binding_class = payload.get("workspace_binding_class")
    if state == "ARMED" and binding_class != WORKSPACE_BINDING_CLASS:
        raise AutonomyRefusal("workspace_binding_mismatch")
    if state == "DISARMED" and binding_class != "none":
        raise AutonomyRefusal("workspace_binding_mismatch")
    transaction_id = payload.get("transaction_id")
    if not isinstance(transaction_id, str) or _TRANSACTION_RE.fullmatch(transaction_id) is None:
        raise AutonomyRefusal("transaction_id_invalid")
    if payload.get("tool_version") != TOOL_VERSION:
        raise AutonomyRefusal("tool_version_mismatch")

    predicates = payload.get("predicates")
    if not isinstance(predicates, Mapping) or set(predicates) != _PREDICATE_FIELDS:
        raise AutonomyRefusal("receipt_predicates_invalid")
    if state == "ARMED":
        if any(value is not True for value in predicates.values()):
            raise AutonomyRefusal("receipt_predicates_failed")
    else:
        expected_disarmed = {
            "acceptance_passed": False,
            "configs_validated": True,
            "gate_b_passed": False,
            "provider_readiness_passed": False,
            "runtime_quiescent": False,
            "service_uids_quiescent": True,
        }
        if dict(predicates) != expected_disarmed:
            raise AutonomyRefusal("receipt_predicates_failed")

    current = datetime.now(UTC) if now is None else now.astimezone(UTC)
    observed_at = _timestamp(payload.get("observed_at"))
    readiness_observed_at = _timestamp(payload.get("readiness_observed_at"))
    credential_expires_at = _timestamp(payload.get("credential_expires_at"))
    readiness_expires_at = _timestamp(payload.get("readiness_expires_at"))
    if observed_at > current:
        raise AutonomyRefusal("receipt_timestamp_in_future")
    if readiness_observed_at > observed_at:
        raise AutonomyRefusal("readiness_timestamp_order_invalid")
    if readiness_expires_at > credential_expires_at:
        raise AutonomyRefusal("readiness_expiry_bounds_invalid")
    if require_current:
        if readiness_expires_at <= current:
            raise AutonomyRefusal("readiness_expired")
        if readiness_expires_at < current + MIN_ADMISSION_MARGIN:
            raise AutonomyRefusal("readiness_margin_insufficient")

    return ArmBinding(
        state=str(state),
        release_sha=release_sha,
        control_config_sha256=str(payload["control_config_sha256"]),
        worker_config_sha256=str(payload["worker_config_sha256"]),
        provider_readiness_receipt_sha256=str(
            payload["provider_readiness_receipt_sha256"]
        ),
        readiness_observed_at=readiness_observed_at,
        credential_expires_at=credential_expires_at,
        readiness_expires_at=readiness_expires_at,
        expected_credential_kind=str(kind),
        workspace_binding_class=str(binding_class),
        transaction_id=transaction_id,
        observed_at=observed_at,
    )


def validate_runtime_guard_document(
    payload: Mapping[str, Any],
    *,
    metadata: ReceiptMetadata,
    role: str,
    own_config_sha256: str,
    release_sha: str,
    now: datetime | None = None,
) -> ArmBinding:
    """Validate the root receipt at one service's pre-effect boundary."""

    if role not in {"control", "worker"}:
        raise AutonomyRefusal("runtime_role_invalid")
    if payload.get("state") != "ARMED":
        raise AutonomyRefusal("receipt_not_armed")
    _require_digest(own_config_sha256)
    control_digest = (
        own_config_sha256
        if role == "control"
        else _require_digest(payload.get("control_config_sha256"))
    )
    worker_digest = (
        own_config_sha256
        if role == "worker"
        else _require_digest(payload.get("worker_config_sha256"))
    )
    expectation = AutonomyExpectation(
        release_sha=release_sha,
        control_config_sha256=control_digest,
        worker_config_sha256=worker_digest,
        provider_readiness_receipt_sha256=_require_digest(
            payload.get("provider_readiness_receipt_sha256")
        ),
        capability_policy_digest=CAPABILITY_POLICY_DIGEST,
        execution_profile_digest=EXECUTION_PROFILE_DIGEST,
        native_helper_grant_digest=NATIVE_HELPER_GRANT_DIGEST,
        security_config_digest=SECURITY_CONFIG_DIGEST,
    )
    return validate_receipt_document(
        payload,
        metadata=metadata,
        expected=expectation,
        now=now,
        require_current=True,
    )


def _macos_acl(path: Path) -> bool:
    if sys.platform != "darwin":
        return False
    completed = subprocess.run(
        ["/usr/bin/stat", "-f", "%Sp", os.fspath(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AutonomyRefusal("receipt_acl_unsafe")
    return completed.stdout.strip().endswith("+")


def load_receipt_file(
    path: str | Path,
) -> tuple[dict[str, Any], ReceiptMetadata]:
    """Open one bounded root receipt without following a final symlink."""

    receipt_path = Path(path)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = -1
    try:
        descriptor = os.open(receipt_path, flags)
        info = os.fstat(descriptor)
        metadata = ReceiptMetadata(
            uid=int(info.st_uid),
            gid=int(info.st_gid),
            mode=stat.S_IMODE(info.st_mode),
            nlink=int(info.st_nlink),
            is_regular=stat.S_ISREG(info.st_mode),
            is_symlink=False,
            has_acl=_macos_acl(receipt_path),
        )
        raw = os.read(descriptor, MAX_RECEIPT_BYTES + 1)
        if len(raw) > MAX_RECEIPT_BYTES:
            raise AutonomyRefusal("receipt_too_large")
        if os.read(descriptor, 1):
            raise AutonomyRefusal("receipt_too_large")
    except AutonomyRefusal:
        raise
    except OSError as exc:
        raise AutonomyRefusal("receipt_unavailable") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AutonomyRefusal("receipt_not_utf8_json") from exc
    if not isinstance(payload, dict):
        raise AutonomyRefusal("receipt_not_object")
    return payload, metadata


def validate_receipt_file(
    path: str | Path,
    *,
    expected: AutonomyExpectation,
    now: datetime | None = None,
    require_current: bool = True,
) -> ArmBinding:
    """Open and validate a bounded receipt without following a final symlink."""

    payload, metadata = load_receipt_file(path)
    return validate_receipt_document(
        payload,
        metadata=metadata,
        expected=expected,
        now=now,
        require_current=require_current,
    )


def validate_runtime_guard_file(
    path: str | Path,
    *,
    role: str,
    own_config_sha256: str,
    release_sha: str,
    now: datetime | None = None,
) -> ArmBinding:
    payload, metadata = load_receipt_file(path)
    return validate_runtime_guard_document(
        payload,
        metadata=metadata,
        role=role,
        own_config_sha256=own_config_sha256,
        release_sha=release_sha,
        now=now,
    )


def classify_status(evidence: StatusEvidence, *, now: datetime | None = None) -> str:
    """Return exactly one closed status using the frozen unsafe precedence."""

    current = datetime.now(UTC) if now is None else now.astimezone(UTC)
    if evidence.transaction_present:
        return TRANSACTION_INCOMPLETE

    mixed_arms = evidence.control_armed is not evidence.worker_armed
    receipt_drift = False
    if evidence.control_armed and evidence.worker_armed:
        receipt_drift = (
            evidence.receipt_state != "ARMED" or not evidence.receipt_matches
        )
    elif evidence.receipt_state not in {None, "DISARMED"}:
        receipt_drift = True
    elif evidence.receipt_state == "DISARMED" and not evidence.receipt_matches:
        receipt_drift = True
    if mixed_arms or evidence.config_drift or receipt_drift:
        return CONFIG_DRIFT

    if not evidence.identity_reconciled or evidence.service_state not in {
        "READY",
        "STOPPED",
        "DEGRADED",
    }:
        return EFFECT_UNKNOWN

    if not evidence.control_armed:
        return UNARMED
    if evidence.readiness_expires_at is None:
        return CONFIG_DRIFT
    deadline = evidence.readiness_expires_at.astimezone(UTC)
    if deadline <= current:
        return READINESS_EXPIRED
    if (
        deadline < current + MIN_ADMISSION_MARGIN
        or evidence.service_state != "READY"
    ):
        return ARMED_DEGRADED
    return ARMED_READY


__all__ = [
    "ARMED_DEGRADED",
    "ARMED_READY",
    "CAPABILITY_POLICY_DIGEST",
    "CONFIG_DRIFT",
    "EFFECT_UNKNOWN",
    "EXECUTION_PROFILE_DIGEST",
    "MIN_ADMISSION_MARGIN",
    "NATIVE_HELPER_GRANT_DIGEST",
    "READINESS_EXPIRED",
    "RECEIPT_SCHEMA_VERSION",
    "SECURITY_CONFIG_DIGEST",
    "TOOL_VERSION",
    "TRANSACTION_INCOMPLETE",
    "UNARMED",
    "WORKSPACE_BINDING_CLASS",
    "ArmBinding",
    "AutonomyExpectation",
    "AutonomyRefusal",
    "ReceiptMetadata",
    "StatusEvidence",
    "canonical_sha256",
    "classify_status",
    "load_receipt_file",
    "sha256_file",
    "validate_receipt_document",
    "validate_receipt_file",
    "validate_runtime_guard_document",
    "validate_runtime_guard_file",
]
