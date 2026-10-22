"""Dormant one-transition forward recovery protocol for the exact DUE10 issuer.

This module owns the INACTIVE prospective forward transition only.  It adds no
scheduler, queue, listener, alternate issuer identity or second derivation of
the incident grant: the same fixed custody paths, the same shared one-use
allocation and the existing authenticated root broker remain the only owners.

Production is dormant by construction:

* :data:`PRODUCTION_FORWARD_RECOVERY_POLICY` is ``None``.  No caller, config
  file, environment value, receipt field or CLI argument can install a policy.
* The forward host-guard producer is deliberately NOT composed.  The broker is
  constructed without one, so every real admission attempt refuses with a
  typed host-guard-unavailable result before any reservation exists.  Only an
  explicitly injected test collaborator may supply qualified current host
  observations for offline protocol tests; no production interface can select
  it.

Canonical identity: D is the exact original canonical broker request digest.
The retained outer host evidence-file digest W is never a request identity and
is accepted nowhere in this module.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import re
import stat
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Mapping

from control_plane.executive_privileged_action import (
    PrivilegedActionRequest,
    PrivilegedActionStatusRequest,
    canonical_request_bytes,
)

try:
    from ops.executive_os import provider_recovery as recovery
except ModuleNotFoundError:  # pragma: no cover - installed direct-script mode
    import provider_recovery as recovery  # type: ignore[no-redef]


FORWARD_REQUEST_SCHEMA = "mastermind.executive_incident_forward_recovery_request.v1"
FORWARD_STATUS_SCHEMA = "mastermind.executive_incident_forward_recovery_status_request.v1"
FORWARD_RECOVERY_ACTION = "executive.worker_auth.forward_recover_due10_incident_issuer"
FORWARD_EFFECT_CLASS = "CREDENTIAL_ADMIN_INCIDENT_FORWARD_RECOVERY"
FORWARD_POLICY_SCHEMA = "mastermind.executive_provider_forward_recovery_policy/v1"
FORWARD_RESERVATION_SCHEMA = "mastermind.executive_provider_forward_reservation/v1"
FORWARD_GUARD_SCHEMA = "mastermind.executive_provider_forward_inflight/v1"
# Single source of law: the commitment schema constant is owned by
# provider_recovery so its v1/v2 dispatch never imports this module.
COMMITMENT_V2_SCHEMA = recovery.COMMITMENT_V2_SCHEMA

# Exact fixed target of the one prospective transition.  D below is the
# canonical ORIGINAL broker request digest; it is never an evidence-file
# digest, and no file-wrapper digest may substitute for it anywhere.
ORIGINAL_ISSUER_REQUEST_ID = "codex01-due10-incident-issuer-20261013-01a104e6"
ORIGINAL_REQUEST_SHA256 = (
    "01a23557c386a79ffd0f7a15724514898237a53847cbb7a177c24e3a8a8526ad"
)
ORIGINAL_MARKER_SHA256 = (
    "3fcc0b56ff7757cd70d0dec34aa9821bb4bfd01ab0d27eb41bfc125c782ee0fb"
)
ORIGINAL_RELEASE_SHA = "54e8659730141fc130ebbeb214dbb50f3edb04a7"
SUCCESSOR_REQUEST_ID = "codex01-due10-incident-qualification-20261013-01a104e6"

REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_UTC_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")

FORWARD_REQUEST_ARG_KEYS = frozenset(
    {
        "original_request_sha256",
        "original_marker_sha256",
        "original_release_sha",
        "successor_request_id",
        "expected_current_release_sha",
        "expected_current_manifest_sha256",
    }
)

# Three deterministic broker evidence files for the SAME operation, indexed by
# the original issuer id under the existing privileged receipt directory.
# Paths are internal and never caller-selectable.
RESERVATION_SUFFIX = ".forward-reservation.json"
GUARD_SUFFIX = ".forward-inflight.json"
TERMINAL_SUFFIX = ".forward-terminal.json"
_MAX_FORWARD_BYTES = 64 * 1024

_FORWARD_RESERVATION_FIELDS = frozenset(
    {
        "schema_version",
        "policy_amendment",
        "original_issuer_request_id",
        "original_request_sha256",
        "original_marker_sha256",
        "original_release_sha",
        "successor_request_id",
        "forward_request_sha256",
        "repaired_executive_source",
        "evidence",
        "reserved_at",
        "proposed_grant",
        "proposed_grant_sha256",
    }
)
_FORWARD_GUARD_FIELDS = frozenset(
    {
        "schema_version",
        "original_issuer_request_id",
        "forward_request_sha256",
        "reservation_sha256",
        "release_sha",
        "started_at",
    }
)
_FORWARD_POLICY_FIELDS = frozenset(
    {
        "policy_id",
        "question_sha256",
        "answer_sha256",
        "provenance_sha256",
        "original_issuer_request_id",
        "original_request_sha256",
        "original_marker_sha256",
        "original_release_sha",
        "successor_request_id",
    }
)
_COMMITMENT_V2_FIELDS = frozenset(
    {
        "schema_version",
        "authorization",
        "incident_class",
        "grant_sha256",
        "issuer_request_id",
        "issuer_request_sha256",
        "successor_request_id",
        "created_at",
        "forward_recovery",
    }
)
_FORWARD_RECOVERY_COMMITMENT_FIELDS = frozenset(
    {
        "amendment_authorization",
        "original_marker_sha256",
        "original_release_sha",
        "forward_request_sha256",
        "reservation_sha256",
        "repaired_executive_source",
    }
)



class ForwardRecoveryError(RuntimeError):
    """A bounded, non-secret forward-protocol refusal."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclasses.dataclass(frozen=True)
class _ForwardGuardRequest:
    """Private invocation inputs, never a serializable host-proof report.

    A future trusted producer must bind the actual uninterrupted maintenance
    and listener-origin custody to this invocation and its exact connection.
    It may not create that custody from these public expected values. No
    production producer is composed by this module.
    """

    original_request_id: str
    original_request_sha256: str
    original_marker_sha256: str
    original_release_sha: str
    successor_request_id: str
    forward_request_sha256: str
    policy_binding: tuple[tuple[str, str], ...]
    sealed_source: tuple[tuple[str, str], ...]
    peer_uid: int
    connection: Any
    invocation_token: object
    deadline_monotonic_ns: int


@dataclasses.dataclass(frozen=True)
class _ForwardHostObservation:
    """Digest of this stage's nonsecret observations, never standing authority.

    Only the held trusted context can qualify the actual observation. This
    value cannot reconstruct that context or authorize another invocation.
    """

    observation_sha256: str


class _ForwardHostContext(ABC):
    """Private trusted-code collaborator held until settlement and cleanup.

    Implementations must preserve the same real custody interval, revalidate
    current source/boot/peer/broker/listener at each call, and drain only their
    own observation resources on exit. They must never clean durable forward
    evidence or manufacture an interval from a prior JSON report. This base
    class implements no producer and grants no authority.
    """

    @abstractmethod
    def __enter__(self) -> "_ForwardHostContext":
        raise NotImplementedError

    @abstractmethod
    def revalidate(
        self, request: _ForwardGuardRequest, *, stage: str,
        reservation_sha256: str | None,
    ) -> _ForwardHostObservation:
        raise NotImplementedError

    @abstractmethod
    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        raise NotImplementedError


class _ForwardBudget:
    """One non-renewable handler endpoint including acquisition and cleanup.

    The future production context additionally owns the earlier real
    maintenance interval; this handler budget is not proof of that interval.
    The producer must preserve the incumbent earlier deadline if it is tighter.
    """

    def __init__(self, seconds: int) -> None:
        if type(seconds) is not int or not 1 <= seconds <= 900:
            raise ForwardRecoveryError("forward_deadline_invalid")
        self.last = time.monotonic_ns()
        self.endpoint = self.last + seconds * 1_000_000_000

    def check(self) -> None:
        now = time.monotonic_ns()
        if now < self.last or now >= self.endpoint:
            raise ForwardRecoveryError("forward_deadline_expired")
        self.last = now


@dataclasses.dataclass(frozen=True)
class ForwardRecoveryPolicy:
    """Immutable closed amendment record for the one forward transition.

    It binds the exact original issuer identity I, the canonical request
    digest D, the retained marker digest M, the original release R and the
    designated successor Q, plus the retained future human
    question/answer/provenance digests.  A policy whose bindings differ from
    the fixed constants is malformed, never an alternative authorization.
    """

    policy_id: str
    question_sha256: str
    answer_sha256: str
    provenance_sha256: str
    original_issuer_request_id: str
    original_request_sha256: str
    original_marker_sha256: str
    original_release_sha: str
    successor_request_id: str

    def amendment_authorization(self) -> dict[str, Any]:
        return {
            "schema_version": FORWARD_POLICY_SCHEMA,
            "policy_id": self.policy_id,
            "question_sha256": self.question_sha256,
            "answer_sha256": self.answer_sha256,
            "provenance_sha256": self.provenance_sha256,
        }

    def bindings(self) -> dict[str, str]:
        return {
            "original_issuer_request_id": self.original_issuer_request_id,
            "original_request_sha256": self.original_request_sha256,
            "original_marker_sha256": self.original_marker_sha256,
            "original_release_sha": self.original_release_sha,
            "successor_request_id": self.successor_request_id,
        }


# Production MUST remain None.  Importing this module creates no grant,
# reservation, window, allocation or effect; the authenticated root broker,
# the composed host guard (absent in production) and a later separately
# reviewed authority-owned policy still own every admission.
PRODUCTION_FORWARD_RECOVERY_POLICY: ForwardRecoveryPolicy | None = None


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ForwardRecoveryError(code)
    return value


def _request_id(value: Any, code: str) -> str:
    if not isinstance(value, str) or REQUEST_ID_RE.fullmatch(value) is None:
        raise ForwardRecoveryError(code)
    return value


def _utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _canonical(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def validate_forward_policy(value: Any) -> dict[str, Any]:
    """Return the amendment binding of one well-formed forward policy."""

    if not isinstance(value, ForwardRecoveryPolicy):
        raise ForwardRecoveryError("forward_policy_malformed")
    if frozenset(vars(value)) != _FORWARD_POLICY_FIELDS:
        raise ForwardRecoveryError("forward_policy_malformed")
    _request_id(value.policy_id, "forward_policy_malformed")
    for field in ("question_sha256", "answer_sha256", "provenance_sha256"):
        _digest(getattr(value, field), "forward_policy_malformed")
    expected = {
        "original_issuer_request_id": ORIGINAL_ISSUER_REQUEST_ID,
        "original_request_sha256": ORIGINAL_REQUEST_SHA256,
        "original_marker_sha256": ORIGINAL_MARKER_SHA256,
        "original_release_sha": ORIGINAL_RELEASE_SHA,
        "successor_request_id": SUCCESSOR_REQUEST_ID,
    }
    if value.bindings() != expected:
        raise ForwardRecoveryError("forward_policy_binding_mismatch")
    return value.amendment_authorization()


def validate_forward_request(raw: Mapping[str, Any]) -> tuple[PrivilegedActionRequest, str]:
    """Validate the closed forward request and return it with its digest F.

    Every identity argument must equal the fixed installed constant; the two
    source selectors are caller-supplied CAS expectations compared to actual
    current source, never a source authority.  The outer evidence-file digest
    W is not a request identity and is refused wherever D is required.
    """
    if not isinstance(raw, Mapping):
        raise ForwardRecoveryError("forward_request_malformed")
    if frozenset(raw) != {"schema", "request_id", "action", "args"}:
        raise ForwardRecoveryError("forward_request_malformed")
    if raw["schema"] != FORWARD_REQUEST_SCHEMA or raw["action"] != FORWARD_RECOVERY_ACTION:
        raise ForwardRecoveryError("forward_request_schema_mismatch")
    request_id = _request_id(raw.get("request_id"), "forward_request_malformed")
    if request_id != ORIGINAL_ISSUER_REQUEST_ID:
        raise ForwardRecoveryError("forward_request_identity_mismatch")
    args = raw.get("args")
    if not isinstance(args, Mapping) or frozenset(args) != FORWARD_REQUEST_ARG_KEYS:
        raise ForwardRecoveryError("forward_request_arguments_malformed")
    expected_args = {
        "original_request_sha256": ORIGINAL_REQUEST_SHA256,
        "original_marker_sha256": ORIGINAL_MARKER_SHA256,
        "original_release_sha": ORIGINAL_RELEASE_SHA,
        "successor_request_id": SUCCESSOR_REQUEST_ID,
    }
    for key, value in expected_args.items():
        if args[key] != value:
            raise ForwardRecoveryError("forward_request_identity_mismatch")
    if (type(args["expected_current_release_sha"]) is not str
            or type(args["expected_current_manifest_sha256"]) is not str
            or _SHA40_RE.fullmatch(args["expected_current_release_sha"]) is None
            or _SHA256_RE.fullmatch(args["expected_current_manifest_sha256"]) is None):
        raise ForwardRecoveryError("forward_request_source_selector_malformed")
    request = PrivilegedActionRequest(
        schema=FORWARD_REQUEST_SCHEMA,
        request_id=request_id,
        action=FORWARD_RECOVERY_ACTION,
        args=tuple(sorted(args.items())),
    )
    return request, hashlib.sha256(canonical_request_bytes(request)).hexdigest()


def validate_forward_status_request(raw: Mapping[str, Any]) -> PrivilegedActionStatusRequest:
    if not isinstance(raw, Mapping) or frozenset(raw) != {"schema", "request_id"}:
        raise ForwardRecoveryError("forward_status_request_malformed")
    if raw.get("schema") != FORWARD_STATUS_SCHEMA:
        raise ForwardRecoveryError("forward_status_request_schema_mismatch")
    request_id = _request_id(raw.get("request_id"), "forward_status_request_malformed")
    if request_id != ORIGINAL_ISSUER_REQUEST_ID:
        raise ForwardRecoveryError("forward_status_request_identity_mismatch")
    return PrivilegedActionStatusRequest(schema=FORWARD_STATUS_SCHEMA, request_id=request_id)


def reservation_path(receipt_root: Path) -> Path:
    return Path(receipt_root) / (ORIGINAL_ISSUER_REQUEST_ID + RESERVATION_SUFFIX)


def guard_path(receipt_root: Path) -> Path:
    return Path(receipt_root) / (ORIGINAL_ISSUER_REQUEST_ID + GUARD_SUFFIX)


def terminal_path(receipt_root: Path) -> Path:
    return Path(receipt_root) / (ORIGINAL_ISSUER_REQUEST_ID + TERMINAL_SUFFIX)


def _strict_forward_document(
    path: Path
) -> tuple[dict[str, Any], bytes] | None:
    """Read one forward evidence file strictly, or return None when absent.

    A present-but-unreadable entry is never absence: it refuses.
    """
    from control_plane import executive_privileged_broker as broker_module

    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ForwardRecoveryError("forward_evidence_unreadable") from exc
    # Never open a non-regular entry: a FIFO or device would block or leak.
    if not stat.S_ISREG(info.st_mode):
        raise ForwardRecoveryError("forward_evidence_not_regular")
    for directory in (path.parent.parent.parent, path.parent.parent, path.parent,
                      path.parent / "inflight", path.parent / "reconciled"):
        try:
            broker_module._assert_root_owned_nonwritable(directory, directory=True)
        except broker_module.BrokerTrustError as exc:
            raise ForwardRecoveryError("forward_evidence_custody_unsafe") from exc
        try:
            recovery._readiness._assert_no_macos_acl(directory)
        except recovery._readiness.ReadinessError as exc:
            raise ForwardRecoveryError("forward_evidence_custody_unsafe") from exc
    try:
        raw, info = broker_module._read_stable_bounded_bytes(path)
    except broker_module.BrokerTrustError as exc:
        # An empty, oversize, unreadable or mid-read-changed occupant is
        # existing evidence that refuses; it is never a missing producer.
        raise ForwardRecoveryError("forward_evidence_unreadable") from exc
    if (info.st_uid != recovery.CUSTODY_UID
            or info.st_gid != recovery.CUSTODY_GID
            or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
        raise ForwardRecoveryError("forward_evidence_custody_unsafe")
    try:
        recovery._readiness._assert_no_macos_acl(path)
    except recovery._readiness.ReadinessError as exc:
        raise ForwardRecoveryError("forward_evidence_custody_unsafe") from exc
    if broker_module._stable_file_identity(path.lstat()) != (
        broker_module._stable_file_identity(info)
    ):
        raise ForwardRecoveryError("forward_evidence_custody_changed")
    if len(raw) > _MAX_FORWARD_BYTES:
        raise ForwardRecoveryError("forward_evidence_size_invalid")
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"),
                           object_pairs_hook=recovery._reject_duplicate_keys)
    except (UnicodeError, ValueError, recovery.RecoveryError) as exc:
        raise ForwardRecoveryError("forward_evidence_unreadable") from exc
    if not isinstance(value, dict):
        raise ForwardRecoveryError("forward_evidence_unreadable")
    return value, raw


def forward_slots_state(env: Any) -> dict[str, tuple[dict[str, Any], bytes] | None]:
    root = Path(env.receipt_root)
    return {
        "reservation": _strict_forward_document(reservation_path(root)),
        "guard": _strict_forward_document(guard_path(root)),
        "terminal": _strict_forward_document(terminal_path(root)),
    }


def _terminal_at(receipt_root: Path, request_id: str) -> dict[str, Any] | None:
    from control_plane import executive_privileged_broker as broker_module

    path = Path(receipt_root) / f"{request_id}.json"
    value = broker_module._read_optional_bounded_json(path)
    if value is None:
        return None
    return broker_module.validate_terminal_receipt(
        value, expected_request_id=request_id
    )


def _reconciliation_at(env: Any, request_id: str) -> dict[str, Any] | None:
    from control_plane import executive_privileged_broker as broker_module

    path = Path(env.receipt_root) / "reconciled" / f"{request_id}.json"
    try:
        path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ForwardRecoveryError("forward_evidence_unreadable") from exc
    return broker_module._read_strict_reconciliation_record_file(
        path,
        expected_request_id=request_id,
        require_root_metadata=getattr(env, "require_root", False),
    )


def _inflight_at(receipt_root: Path, request_id: str) -> dict[str, Any] | None:
    from control_plane import executive_privileged_broker as broker_module

    path = Path(receipt_root) / "inflight" / f"{request_id}.json"
    value = broker_module._read_optional_bounded_json(path)
    if value is None:
        return None
    if (value.get("schema") != broker_module.INFLIGHT_SCHEMA
            or value.get("request_id") != request_id):
        raise ForwardRecoveryError("forward_evidence_unreadable")
    return value


def validate_original_marker(env: Any) -> tuple[dict[str, Any], bytes]:
    """Revalidate the exact original in-flight marker bytes and bindings.

    The original marker is never removed and its bytes must still hash to the
    retained digest M while binding request digest D, original release R and
    the original issuer action.  Consumer-side validation additionally checks
    the custody metadata against the configured custody principal.
    """
    from control_plane import executive_privileged_broker as broker_module

    path = (Path(env.receipt_root) / "inflight"
            / (ORIGINAL_ISSUER_REQUEST_ID + ".json"))
    try:
        marker, raw = broker_module._read_strict_inflight_marker_file(
            path,
            expected_request_id=ORIGINAL_ISSUER_REQUEST_ID,
            require_root_metadata=getattr(env, "require_root", False),
        )
    except FileNotFoundError as exc:
        raise ForwardRecoveryError("forward_original_marker_absent") from exc
    except (broker_module.BrokerTrustError, OSError) as exc:
        raise ForwardRecoveryError("forward_original_marker_unreadable") from exc
    custody_uid = getattr(env, "custody_uid", None)
    if custody_uid is not None:
        _info = path.lstat()
        if (_info.st_uid != custody_uid
                or _info.st_gid != getattr(env, "custody_gid", custody_uid)
                or stat.S_IMODE(_info.st_mode) != 0o600
                or _info.st_nlink != 1):
            raise ForwardRecoveryError("forward_original_marker_custody_unsafe")
    if marker["request_sha256"] != ORIGINAL_REQUEST_SHA256:
        raise ForwardRecoveryError("forward_original_request_mismatch")
    if marker["release_sha"] != ORIGINAL_RELEASE_SHA:
        raise ForwardRecoveryError("forward_original_release_mismatch")
    if marker["action"] != recovery.INCIDENT_ISSUER_ACTION:
        raise ForwardRecoveryError("forward_original_action_mismatch")
    if hashlib.sha256(raw).hexdigest() != ORIGINAL_MARKER_SHA256:
        raise ForwardRecoveryError("forward_original_marker_mismatch")
    return marker, raw


def validate_original_absence_and_successor(env: Any) -> None:
    """Require original terminal/reconciliation absence and a quiet successor.

    These are current conflict checks only; they are never historical
    no-effect proof and never emit NOT_APPLIED.
    """
    from control_plane import executive_privileged_broker as broker_module

    if _terminal_at(env.receipt_root, ORIGINAL_ISSUER_REQUEST_ID) is not None:
        raise ForwardRecoveryError("forward_original_terminal_present")
    if _reconciliation_at(env, ORIGINAL_ISSUER_REQUEST_ID) is not None:
        raise ForwardRecoveryError("forward_original_reconciliation_present")
    if _terminal_at(env.receipt_root, SUCCESSOR_REQUEST_ID) is not None:
        raise ForwardRecoveryError("forward_successor_terminal_present")
    if _reconciliation_at(env, SUCCESSOR_REQUEST_ID) is not None:
        raise ForwardRecoveryError("forward_successor_reconciliation_present")
    if _inflight_at(env.receipt_root, SUCCESSOR_REQUEST_ID) is not None:
        raise ForwardRecoveryError("forward_successor_inflight_present")


def _incident_observation(env: Any) -> dict[str, Any]:
    """Reacquire the complete current incident evidence observation."""
    observer = getattr(env, "_reconciliation_observer", None)
    if not callable(observer):
        raise ForwardRecoveryError("forward_observation_incomplete")
    evidence = observer()
    required = {
        "readiness_receipt_sha256",
        "readiness_document",
        "readiness_transaction_lock_present",
        "verify_ready_processes",
        "current_auth_identity",
        "current_binary_identity",
    }
    if not isinstance(evidence, Mapping) or frozenset(evidence) != required:
        raise ForwardRecoveryError("forward_observation_incomplete")
    if evidence["readiness_transaction_lock_present"] is not False:
        raise ForwardRecoveryError("forward_readiness_lock_present")
    processes = evidence["verify_ready_processes"]
    if (not isinstance(processes, (tuple, list))
            or any(not isinstance(item, str) for item in processes)
            or len(processes) != 0):
        raise ForwardRecoveryError("forward_qualification_process_active")
    return evidence


def validate_live_predicates(env: Any, *, policy_binding: dict[str, Any],
                             source: Mapping[str, str]) -> dict[str, Any]:
    """Reacquire every existing incident/evidence/pinned-identity predicate."""

    policy = PRODUCTION_FORWARD_RECOVERY_POLICY
    if policy is None:
        raise ForwardRecoveryError("forward_policy_dormant")
    if validate_forward_policy(policy) != policy_binding:
        raise ForwardRecoveryError("forward_policy_binding_mismatch")
    incident = recovery.PRODUCTION_INCIDENT_POLICY
    if incident is None:
        raise ForwardRecoveryError("incident_policy_dormant")
    try:
        designated = recovery.validate_incident_policy(incident)
    except recovery.RecoveryError as exc:
        raise ForwardRecoveryError(exc.code) from exc
    if recovery.read_allocation() is not None:
        raise ForwardRecoveryError("forward_allocation_already_consumed")
    # The exact original marker bytes, custody and I/D/R/action binding are
    # part of the read-only preflight, BEFORE any reservation can exist.
    validate_original_marker(env)
    validate_original_absence_and_successor(env)
    evidence = _incident_observation(env)
    if evidence["readiness_receipt_sha256"] != designated["readiness_receipt_sha256"]:
        raise ForwardRecoveryError("forward_predecessor_digest_mismatch")
    binary_identity = evidence["current_binary_identity"]
    if (not isinstance(binary_identity, Mapping)
            or binary_identity.get("path") != recovery.os.fspath(recovery._readiness.CODEX_BINARY)
            or binary_identity.get("version") != recovery._readiness.CODEX_VERSION
            or binary_identity.get("sha256") != recovery._readiness.CODEX_SHA256
            or binary_identity.get("team_identifier") != recovery._readiness.CODEX_TEAM_ID):
        raise ForwardRecoveryError("forward_provider_identity_not_pinned")
    document = evidence["readiness_document"]
    try:
        recovery.validate_incident_designated_readiness(
            document, designated,
            auth_identity=evidence["current_auth_identity"],
            binary_identity=binary_identity,
        )
        recovery.refuse_evidenced_incident_denial(document)
        recovery.validate_incident_designated_terminal(designated)
    except recovery.RecoveryError as exc:
        raise ForwardRecoveryError(exc.code) from exc
    current = recovery.current_executive_source()
    if current != dict(source) or current["release_sha"] != env.config.release_root.name:
        raise ForwardRecoveryError("forward_executive_source_changed")
    return evidence


def derive_prospective_grant(
    broker: Any, *, policy_binding: dict[str, Any], source: Mapping[str, str],
    evidence: Mapping[str, Any], designated: Mapping[str, Any],
    started_at: str, issuer_request_sha256: str,
) -> tuple[dict[str, Any], bytes, str]:
    """Derive the prospective v1-shaped incident grant from fresh observations.

    granted_at/expires_at are NEW prospective times inside the existing finite
    bounds; they never claim to reproduce an original grant.
    """
    lifetime = recovery.MIN_GRANT_LIFETIME + (
        (recovery.MAX_GRANT_LIFETIME - recovery.MIN_GRANT_LIFETIME) / 2
    )
    grant = {
        "schema_version": recovery.INCIDENT_GRANT_SCHEMA,
        "authority_reference": recovery.INCIDENT_AUTHORITY_REFERENCE,
        "incident_class": recovery.INCIDENT_RECOVERY_CLASS,
        "historical_cause": recovery.INCIDENT_HISTORICAL_CAUSE,
        "causal_link": recovery.INCIDENT_CAUSAL_LINK,
        "raw_provider_messages_retained": False,
        "authorization": dict(
            recovery.PRODUCTION_INCIDENT_POLICY.authorization_binding()
        ),
        "evidence": dict(designated),
        "installed_source": {
            "path": recovery.os.fspath(recovery._readiness.CODEX_BINARY),
            "version": recovery._readiness.CODEX_VERSION,
            "sha256": recovery._readiness.CODEX_SHA256,
            "team_identifier": recovery._readiness.CODEX_TEAM_ID,
        },
        "executive_source": dict(source),
        "worker": {
            "worker_user": recovery.get_slot("codex-01").worker_user,
            "worker_uid": recovery._readiness.WORKER_UID,
            "worker_gid": recovery._readiness.WORKER_GID,
            "provider_home": recovery.os.fspath(recovery._readiness.AUTH_PATH.parent),
            "workspace_binding_class":
                recovery._readiness.COMPANY_WORKSPACE_BINDING_CLASS,
            "expected_credential_kind": "device-auth",
        },
        "credential_lstat": dict(evidence["current_auth_identity"]),
        "model": recovery._readiness.PRODUCTION_MODEL,
        "issuer_request_id": ORIGINAL_ISSUER_REQUEST_ID,
        "issuer_request_sha256": issuer_request_sha256,
        "successor_request_id": SUCCESSOR_REQUEST_ID,
        "budget": recovery.RECOVERY_BUDGET,
        "granted_at": started_at,
        "expires_at": recovery._readiness._iso(
            dt.datetime.now(dt.UTC) + lifetime
        ),
    }
    validated = recovery._validate_incident_grant_document(grant)
    grant_bytes = _canonical(validated)
    return validated, grant_bytes, hashlib.sha256(grant_bytes).hexdigest()


def build_reservation(
    *, policy_binding: dict[str, Any], forward_request_sha256: str,
    source: Mapping[str, str], evidence: Mapping[str, Any],
    reserved_at: str, host_observation_sha256: str,
    grant: Mapping[str, Any], grant_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": FORWARD_RESERVATION_SCHEMA,
        "policy_amendment": dict(policy_binding),
        "original_issuer_request_id": ORIGINAL_ISSUER_REQUEST_ID,
        "original_request_sha256": ORIGINAL_REQUEST_SHA256,
        "original_marker_sha256": ORIGINAL_MARKER_SHA256,
        "original_release_sha": ORIGINAL_RELEASE_SHA,
        "successor_request_id": SUCCESSOR_REQUEST_ID,
        "forward_request_sha256": forward_request_sha256,
        "repaired_executive_source": dict(source),
        "evidence": {
            "readiness_receipt_sha256": evidence["readiness_receipt_sha256"],
            "host_observation_sha256": host_observation_sha256,
        },
        "reserved_at": reserved_at,
        "proposed_grant": grant,
        "proposed_grant_sha256": grant_sha256,
    }


def validate_reservation_document(
    value: Any, *, expected: Mapping[str, Any], expected_bytes_sha256: str
) -> None:
    if frozenset(value) != _FORWARD_RESERVATION_FIELDS:
        raise ForwardRecoveryError("forward_reservation_malformed")
    if value["schema_version"] != FORWARD_RESERVATION_SCHEMA:
        raise ForwardRecoveryError("forward_reservation_malformed")
    if _canonical(value) != _canonical(dict(expected)):
        raise ForwardRecoveryError("forward_reservation_mismatch")
    if hashlib.sha256(_canonical(value)).hexdigest() != expected_bytes_sha256:
        raise ForwardRecoveryError("forward_reservation_mismatch")


def validate_guard_document(value: Any, *, expected: Mapping[str, Any]) -> None:
    if frozenset(value) != _FORWARD_GUARD_FIELDS:
        raise ForwardRecoveryError("forward_guard_malformed")
    if value["schema_version"] != FORWARD_GUARD_SCHEMA:
        raise ForwardRecoveryError("forward_guard_malformed")
    if value != dict(expected):
        raise ForwardRecoveryError("forward_guard_mismatch")


def validate_v2_commitment_structure(
    value: Any, *, commitment_bytes: bytes
) -> None:
    """Validate the closed v2 commitment shape alone, without grant joins."""
    if frozenset(value) != _COMMITMENT_V2_FIELDS:
        raise ForwardRecoveryError("incident_commitment_mismatch")
    if value["schema_version"] != COMMITMENT_V2_SCHEMA:
        raise ForwardRecoveryError("incident_commitment_mismatch")
    if value["incident_class"] != recovery.INCIDENT_RECOVERY_CLASS:
        raise ForwardRecoveryError("recovery_grant_schema_malformed")
    if (value["issuer_request_id"] != ORIGINAL_ISSUER_REQUEST_ID
            or value["issuer_request_sha256"] != ORIGINAL_REQUEST_SHA256
            or value["successor_request_id"] != SUCCESSOR_REQUEST_ID):
        raise ForwardRecoveryError("incident_commitment_mismatch")
    recovery.validate_incident_authorization(value["authorization"])
    _digest(value["grant_sha256"], "recovery_grant_fields_malformed")
    _digest(value["issuer_request_sha256"], "recovery_grant_fields_malformed")
    _request_id(value["issuer_request_id"], "recovery_grant_successor_malformed")
    _request_id(value["successor_request_id"], "recovery_grant_successor_malformed")
    recovery._readiness._timestamp(
        value["created_at"], code="recovery_grant_window_invalid"
    )
    forward_join = value["forward_recovery"]
    if not isinstance(forward_join, Mapping) or frozenset(forward_join) != (
        _FORWARD_RECOVERY_COMMITMENT_FIELDS
    ):
        raise ForwardRecoveryError("incident_commitment_mismatch")
    policy = PRODUCTION_FORWARD_RECOVERY_POLICY
    if policy is not None and forward_join["amendment_authorization"] != (
        policy.amendment_authorization()
    ):
        raise ForwardRecoveryError("forward_policy_binding_mismatch")
    _digest(forward_join["original_marker_sha256"], "incident_commitment_mismatch")
    if forward_join["original_marker_sha256"] != ORIGINAL_MARKER_SHA256:
        raise ForwardRecoveryError("incident_commitment_mismatch")
    if forward_join["original_release_sha"] != ORIGINAL_RELEASE_SHA:
        raise ForwardRecoveryError("incident_commitment_mismatch")
    _digest(forward_join["forward_request_sha256"], "incident_commitment_mismatch")
    _digest(forward_join["reservation_sha256"], "incident_commitment_mismatch")
    if not isinstance(forward_join["repaired_executive_source"], Mapping):
        raise ForwardRecoveryError("incident_commitment_mismatch")
    del commitment_bytes


def validate_v2_commitment_document(
    value: Any, *, commitment_bytes: bytes, grant: Mapping[str, Any],
    grant_sha256: str,
) -> dict[str, Any]:
    """Validate the closed v2 commitment against its grant; no admission yet."""
    validate_v2_commitment_structure(value, commitment_bytes=commitment_bytes)
    if value["authorization"] != grant["authorization"]:
        raise ForwardRecoveryError("incident_commitment_mismatch")
    if value["grant_sha256"] != grant_sha256:
        raise ForwardRecoveryError("incident_commitment_mismatch")
    if value["issuer_request_id"] != grant["issuer_request_id"]:
        raise ForwardRecoveryError("incident_commitment_mismatch")
    if value["issuer_request_sha256"] != grant["issuer_request_sha256"]:
        raise ForwardRecoveryError("incident_commitment_mismatch")
    if value["successor_request_id"] != grant["successor_request_id"]:
        raise ForwardRecoveryError("incident_commitment_mismatch")
    forward_join = value["forward_recovery"]
    if forward_join["repaired_executive_source"] != dict(grant["executive_source"]):
        raise ForwardRecoveryError("incident_commitment_mismatch")
    return dict(value)


def validate_complete_forward_join(
    env: Any, *, grant: Mapping[str, Any], grant_sha256: str,
    commitment: Mapping[str, Any], commitment_bytes: bytes,
) -> dict[str, Any]:
    """Validate the entire closed join and return the admission evidence.

    Required: exact permanent reservation still present and matching
    I/D/M/R/Q/F, the proposed grant bytes and the repaired source; unchanged
    original marker STILL present; no original terminal or reconciliation;
    forward terminal SUCCEEDED for I/F/forward-action/repaired-release with
    stdout binding the exact commitment bytes; forward-inflight guard ABSENT.
    """
    from control_plane import executive_privileged_broker as broker_module

    state = forward_slots_state(env)
    reservation = state["reservation"]
    if reservation is None:
        raise ForwardRecoveryError("forward_reservation_absent")
    reservation_value, reservation_raw = reservation
    if frozenset(reservation_value) != _FORWARD_RESERVATION_FIELDS:
        raise ForwardRecoveryError("forward_reservation_malformed")
    if reservation_value["schema_version"] != FORWARD_RESERVATION_SCHEMA:
        raise ForwardRecoveryError("forward_reservation_malformed")
    repaired_source = reservation_value.get("repaired_executive_source")
    if (not isinstance(repaired_source, Mapping)
            or frozenset(repaired_source) != {"release_sha", "manifest_sha256"}
            or not isinstance(repaired_source["release_sha"], str)
            or _SHA40_RE.fullmatch(repaired_source["release_sha"]) is None
            or not isinstance(repaired_source["manifest_sha256"], str)
            or _SHA256_RE.fullmatch(repaired_source["manifest_sha256"]) is None):
        raise ForwardRecoveryError("forward_reservation_malformed")
    if repaired_source != dict(grant["executive_source"]):
        raise ForwardRecoveryError("forward_reservation_mismatch")
    # Reconstruct the canonical forward request from the exact I/D/M/R/Q
    # constants and the reservation's repaired source CAS selectors, then
    # require the reconstructed digest everywhere F is claimed.  An internally
    # consistent evidence triple whose F is D (or any wrapper digest) can
    # never pass, because the claim is compared to the recomputed preimage.
    canonical_forward_request = PrivilegedActionRequest(
        schema=FORWARD_REQUEST_SCHEMA,
        request_id=ORIGINAL_ISSUER_REQUEST_ID,
        action=FORWARD_RECOVERY_ACTION,
        args=tuple(sorted({
            "original_request_sha256": ORIGINAL_REQUEST_SHA256,
            "original_marker_sha256": ORIGINAL_MARKER_SHA256,
            "original_release_sha": ORIGINAL_RELEASE_SHA,
            "successor_request_id": SUCCESSOR_REQUEST_ID,
            "expected_current_release_sha": repaired_source["release_sha"],
            "expected_current_manifest_sha256": repaired_source["manifest_sha256"],
        }.items())),
    )
    canonical_forward_sha256 = hashlib.sha256(
        canonical_request_bytes(canonical_forward_request)
    ).hexdigest()
    if canonical_forward_sha256 == ORIGINAL_REQUEST_SHA256:
        raise ForwardRecoveryError("forward_request_identity_mismatch")
    expected_bindings = {
        "original_issuer_request_id": ORIGINAL_ISSUER_REQUEST_ID,
        "original_request_sha256": ORIGINAL_REQUEST_SHA256,
        "original_marker_sha256": ORIGINAL_MARKER_SHA256,
        "original_release_sha": ORIGINAL_RELEASE_SHA,
        "successor_request_id": SUCCESSOR_REQUEST_ID,
        "forward_request_sha256": canonical_forward_sha256,
    }
    for key, value in expected_bindings.items():
        if reservation_value.get(key) != value:
            raise ForwardRecoveryError("forward_reservation_mismatch")
    if reservation_value.get("proposed_grant_sha256") != grant_sha256:
        raise ForwardRecoveryError("forward_reservation_grant_mismatch")
    if reservation_value.get("proposed_grant") != dict(grant):
        raise ForwardRecoveryError("forward_reservation_grant_mismatch")
    if reservation_value.get("policy_amendment") != commitment["forward_recovery"][
        "amendment_authorization"
    ]:
        raise ForwardRecoveryError("forward_reservation_mismatch")
    preparation = reservation_value.get("evidence")
    if (not isinstance(preparation, dict) or set(preparation) != {
            "readiness_receipt_sha256", "host_observation_sha256"}):
        raise ForwardRecoveryError("forward_reservation_evidence_malformed")
    for value in preparation.values():
        _digest(value, "forward_reservation_evidence_malformed")
    if preparation["readiness_receipt_sha256"] != grant["evidence"]["readiness_receipt_sha256"]:
        raise ForwardRecoveryError("forward_reservation_evidence_mismatch")
    reservation_sha256 = hashlib.sha256(reservation_raw).hexdigest()
    if commitment["forward_recovery"]["reservation_sha256"] != reservation_sha256:
        raise ForwardRecoveryError("incident_commitment_mismatch")
    if commitment["forward_recovery"]["forward_request_sha256"] != (
        canonical_forward_sha256
    ):
        raise ForwardRecoveryError("incident_commitment_mismatch")

    validate_original_marker(env)
    if _terminal_at(env.receipt_root, ORIGINAL_ISSUER_REQUEST_ID) is not None:
        raise ForwardRecoveryError("forward_original_terminal_present")
    if _reconciliation_at(env, ORIGINAL_ISSUER_REQUEST_ID) is not None:
        raise ForwardRecoveryError("forward_original_reconciliation_present")

    if state["guard"] is not None:
        raise ForwardRecoveryError("forward_guard_retained")

    terminal = state["terminal"]
    if terminal is None:
        raise ForwardRecoveryError("forward_terminal_absent")
    terminal_value, terminal_raw = terminal
    try:
        receipt = broker_module.validate_terminal_receipt(
            terminal_value,
            expected_request_id=ORIGINAL_ISSUER_REQUEST_ID,
            expected_request_sha256=canonical_forward_sha256,
            expected_release_sha=grant["executive_source"]["release_sha"],
            expected_action=FORWARD_RECOVERY_ACTION,
        )
    except broker_module.BrokerTrustError as exc:
        raise ForwardRecoveryError("forward_terminal_unverified") from exc
    if receipt["outcome"] != "SUCCEEDED" or receipt["exit_code"] != 0:
        raise ForwardRecoveryError("forward_terminal_not_successful")
    if (receipt["stdout_sha256"] != hashlib.sha256(commitment_bytes).hexdigest()
            or receipt["stdout_bytes"] != len(commitment_bytes)):
        raise ForwardRecoveryError("incident_commitment_digest_mismatch")
    return {
        "terminal": receipt,
        "commitment_sha256": hashlib.sha256(commitment_bytes).hexdigest(),
        "reservation_sha256": reservation_sha256,
        "grant_sha256": grant_sha256,
    }


def forward_state(env: Any) -> tuple[str, dict[str, Any]]:
    """Derive the read-only forward state from files; it never repairs them."""
    state = forward_slots_state(env)
    reservation, guard, terminal = (
        state["reservation"], state["guard"], state["terminal"]
    )
    if reservation is None and guard is None and terminal is None:
        return "NOT_RESERVED", {}
    if terminal is not None and guard is None:
        from control_plane import executive_privileged_broker as broker_module

        try:
            terminal_value, _raw = terminal
            receipt = broker_module.validate_terminal_receipt(
                terminal_value, expected_request_id=ORIGINAL_ISSUER_REQUEST_ID
            )
        except Exception:  # noqa: BLE001 - unreadable evidence stays UNKNOWN
            return "RESERVED_OR_UNKNOWN", {}
        if receipt.get("outcome") != "SUCCEEDED" or receipt.get("exit_code") != 0:
            return "RESERVED_OR_UNKNOWN", {}
        try:
            join = complete_join_from_custody(env)
        except Exception:  # noqa: BLE001
            return "RESERVED_OR_UNKNOWN", {}
        return "SUCCEEDED", join
    return "RESERVED_OR_UNKNOWN", {}


def complete_join_from_custody(env: Any) -> dict[str, Any]:
    """Reconstruct and validate the whole closed join from custody files."""
    grant, grant_bytes = recovery.read_incident_grant_with_bytes()
    grant_sha256 = hashlib.sha256(grant_bytes).hexdigest()
    commitment, commitment_bytes = recovery.read_incident_commitment()
    if commitment.get("schema_version") != COMMITMENT_V2_SCHEMA:
        raise ForwardRecoveryError("incident_commitment_mismatch")
    validate_v2_commitment_document(
        commitment, commitment_bytes=commitment_bytes,
        grant=grant, grant_sha256=grant_sha256,
    )
    return validate_complete_forward_join(
        env, grant=grant, grant_sha256=grant_sha256,
        commitment=commitment, commitment_bytes=commitment_bytes,
    )


def handle_forward_recovery(
    broker: Any, raw_request: Mapping[str, Any], *, peer_uid: int,
    connection: Any = None,
) -> tuple[dict[str, Any], bool]:
    """Run the one dormant prospective transition inside the root broker.

    Everything before the reservation is read-only and refuses with a typed
    ForwardRecoveryError.  After the reservation, every error or uncertainty
    becomes EffectUnknown: the evidence is retained, the transition is burned,
    and no resume, refund, regrant or retry exists.
    """
    from control_plane import executive_privileged_broker as broker_module

    budget = _ForwardBudget(broker.config.timeout_seconds)
    policy = PRODUCTION_FORWARD_RECOVERY_POLICY
    if policy is None:
        raise ForwardRecoveryError("forward_policy_dormant")
    policy_binding = validate_forward_policy(policy)
    incident = recovery.PRODUCTION_INCIDENT_POLICY
    if incident is None:
        raise ForwardRecoveryError("incident_policy_dormant")
    try:
        designated = recovery.validate_incident_policy(incident)
    except recovery.RecoveryError as exc:
        raise ForwardRecoveryError(exc.code) from exc

    request, forward_request_sha256 = validate_forward_request(raw_request)
    args = request.args_dict()
    if args["expected_current_release_sha"] != broker.config.release_root.name:
        raise ForwardRecoveryError("forward_running_release_mismatch")
    try:
        source = recovery.current_executive_source()
    except recovery.RecoveryError as exc:
        raise ForwardRecoveryError(exc.code) from exc
    if source["release_sha"] != broker.config.release_root.name:
        raise ForwardRecoveryError("forward_executive_source_uninstalled")
    if args["expected_current_manifest_sha256"] != source["manifest_sha256"]:
        raise ForwardRecoveryError("forward_source_cas_mismatch")

    factory = getattr(broker, "_forward_host_guard", None)
    if factory is None:
        raise broker_module.ForwardHostGuardUnavailableError(
            "forward host custody context is not composed"
        )
    binding = _ForwardGuardRequest(
        ORIGINAL_ISSUER_REQUEST_ID, ORIGINAL_REQUEST_SHA256,
        ORIGINAL_MARKER_SHA256, ORIGINAL_RELEASE_SHA, SUCCESSOR_REQUEST_ID,
        forward_request_sha256, tuple(sorted(policy_binding.items())),
        tuple(sorted(source.items())), peer_uid, connection, object(),
        budget.endpoint,
    )
    reservation_attempted = False

    def mark_reservation() -> None:
        nonlocal reservation_attempted
        # Set BEFORE open/create, including errors with an uncertain write.
        reservation_attempted = True

    try:
        budget.check()
        context = factory(binding)
        if not isinstance(context, _ForwardHostContext):
            raise broker_module.ForwardHostGuardUnavailableError(
                "forward producer did not return a private custody context"
            )
        result = None
        with context as active:
            if active is not context:
                raise broker_module.ForwardHostGuardUnavailableError(
                    "forward custody context identity changed"
                )

            def revalidate(
                stage: str, reservation_sha256: str | None = None,
            ) -> _ForwardHostObservation:
                budget.check()
                observation = context.revalidate(
                    binding, stage=stage, reservation_sha256=reservation_sha256,
                )
                if type(observation) is not _ForwardHostObservation:
                    raise ForwardRecoveryError("forward_host_guard_result_invalid")
                _digest(observation.observation_sha256,
                        "forward_host_guard_result_invalid")
                budget.check()
                return observation

            result = _handle_guarded_forward(
                broker, policy_binding=policy_binding, source=source,
                designated=designated, incident=incident,
                forward_request_sha256=forward_request_sha256,
                revalidate=revalidate, mark_reservation=mark_reservation,
            )
        # Context cleanup is inside the same endpoint and effect boundary.
        budget.check()
        if result is None:
            raise ForwardRecoveryError("forward_host_guard_suppressed_failure")
        return result
    except BaseException as exc:
        if reservation_attempted:
            if isinstance(exc, broker_module.EffectUnknownError):
                raise
            raise broker_module.EffectUnknownError(
                "forward context failed after reservation attempt; preserve "
                "all evidence and do not resume"
            ) from exc
        if isinstance(exc, (ForwardRecoveryError,
                            broker_module.ForwardHostGuardUnavailableError)):
            raise
        raise broker_module.ForwardHostGuardUnavailableError(
            "forward custody acquisition or cleanup failed before reservation"
        ) from exc


def _handle_guarded_forward(
    broker: Any, *, policy_binding: dict[str, Any], source: Mapping[str, str],
    designated: Mapping[str, Any], incident: Any, forward_request_sha256: str,
    revalidate: Any, mark_reservation: Any,
) -> tuple[dict[str, Any], bool]:
    from control_plane import executive_privileged_broker as broker_module

    revalidate("before_preflight")
    try:
        recovery.preflight_recovery_custody()
    except recovery.RecoveryError as exc:
        raise ForwardRecoveryError(exc.code) from exc

    evidence = validate_live_predicates(
        broker, policy_binding=policy_binding, source=source
    )
    slots = forward_slots_state(broker)
    if any(value is not None for value in slots.values()):
        raise ForwardRecoveryError("forward_slot_occupied")

    started_at = _utc_now()
    grant, grant_bytes, grant_sha256 = derive_prospective_grant(
        broker, policy_binding=policy_binding, source=source, evidence=evidence,
        designated=designated, started_at=started_at,
        issuer_request_sha256=ORIGINAL_REQUEST_SHA256,
    )
    # Reacquire both host and existing incident predicates immediately before
    # the irreversible attempt; neither the earlier sample nor derivation is
    # a lease on current state. The prospective window is never renewed.
    host_observation = revalidate("before_reservation")
    evidence = validate_live_predicates(
        broker, policy_binding=policy_binding, source=source,
    )
    recovery.validate_incident_grant_document(grant)
    reservation = build_reservation(
        policy_binding=policy_binding,
        forward_request_sha256=forward_request_sha256,
        source=source, evidence=evidence, reserved_at=started_at,
        host_observation_sha256=host_observation.observation_sha256,
        grant=grant, grant_sha256=grant_sha256,
    )
    reservation_bytes = _canonical(reservation)
    reservation_sha256 = hashlib.sha256(reservation_bytes).hexdigest()
    commitment = {
        "schema_version": COMMITMENT_V2_SCHEMA,
        "authorization": dict(incident.authorization_binding()),
        "incident_class": recovery.INCIDENT_RECOVERY_CLASS,
        "grant_sha256": grant_sha256,
        "issuer_request_id": ORIGINAL_ISSUER_REQUEST_ID,
        "issuer_request_sha256": ORIGINAL_REQUEST_SHA256,
        "successor_request_id": SUCCESSOR_REQUEST_ID,
        "created_at": started_at,
        "forward_recovery": {
            "amendment_authorization": dict(policy_binding),
            "original_marker_sha256": ORIGINAL_MARKER_SHA256,
            "original_release_sha": ORIGINAL_RELEASE_SHA,
            "forward_request_sha256": forward_request_sha256,
            "reservation_sha256": reservation_sha256,
            "repaired_executive_source": dict(source),
        },
    }
    commitment_bytes = _canonical(commitment)

    # -- Reservation: the single permanent consumption of this transition. --
    revalidate("before_reservation_attempt", reservation_sha256)
    mark_reservation()
    try:
        broker_module._write_exclusive_json(
            reservation_path(broker.receipt_root), reservation
        )
    except FileExistsError:
        # Ambiguous creation: never adopt, resume, repair or delete.
        raise broker_module.EffectUnknownError(
            "forward reservation creation is ambiguous; the same operation is "
            "retained and cannot resume"
        ) from None
    except OSError as exc:
        raise broker_module.EffectUnknownError(
            "forward reservation write failed; the transition is burned"
        ) from exc
    try:
        written = _strict_forward_document(reservation_path(broker.receipt_root))
        if written is None:
            raise ForwardRecoveryError("forward_reservation_lost")
        validate_reservation_document(
            written[0], expected=reservation,
            expected_bytes_sha256=reservation_sha256,
        )
    except ForwardRecoveryError as exc:
        raise broker_module.EffectUnknownError(
            f"forward reservation is partial or ambiguous: {exc.code}"
        ) from exc

    # -- Distinct forward-in-flight guard. --
    guard = {
        "schema_version": FORWARD_GUARD_SCHEMA,
        "original_issuer_request_id": ORIGINAL_ISSUER_REQUEST_ID,
        "forward_request_sha256": forward_request_sha256,
        "reservation_sha256": reservation_sha256,
        "release_sha": broker.config.release_root.name,
        "started_at": started_at,
    }
    try:
        broker_module._write_exclusive_json(guard_path(broker.receipt_root), guard)
    except (FileExistsError, OSError) as exc:
        raise broker_module.EffectUnknownError(
            "forward guard creation failed; the reservation is consumed and "
            "cannot resume"
        ) from exc

    def _unknown(message: str, exc: Exception) -> broker_module.EffectUnknownError:
        return broker_module.EffectUnknownError(
            f"{message}: {getattr(exc, 'code', exc)}"
        )

    try:
        written_guard = _strict_forward_document(guard_path(broker.receipt_root))
        if written_guard is None:
            raise ForwardRecoveryError("forward_guard_lost")
        validate_guard_document(written_guard[0], expected=guard)
        validate_live_predicates(
            broker, policy_binding=policy_binding, source=source
        )
        validate_original_marker(broker)
        revalidate("before_grant", reservation_sha256)
        recovery.write_custody_document(
            recovery.RECOVERY_INCIDENT_GRANT_PATH, grant_bytes
        )
        recovery.write_custody_document(
            recovery.RECOVERY_INCIDENT_COMMITMENT_PATH, commitment_bytes
        )
        stored_grant = recovery._read_custody_bytes(
            recovery.RECOVERY_INCIDENT_GRANT_PATH, maximum=65536
        )
        stored_commitment = recovery._read_custody_bytes(
            recovery.RECOVERY_INCIDENT_COMMITMENT_PATH, maximum=65536
        )
        if stored_grant != grant_bytes or stored_commitment != commitment_bytes:
            raise ForwardRecoveryError("forward_custody_readback_mismatch")
        validate_live_predicates(
            broker, policy_binding=policy_binding, source=source
        )
        validate_original_marker(broker)
    except (recovery.RecoveryError, ForwardRecoveryError) as exc:
        raise _unknown(
            "forward guarded write stage failed after reservation", exc
        ) from exc
    except broker_module.BrokerTrustError as exc:
        raise _unknown(
            "forward live predicate drift after reservation", exc
        ) from exc
    except OSError as exc:
        raise _unknown(
            "forward custody write failed after reservation", exc
        ) from exc

    revalidate("before_terminal", reservation_sha256)
    receipt = {
        "schema": broker_module.RECEIPT_SCHEMA,
        "request_id": ORIGINAL_ISSUER_REQUEST_ID,
        "request_sha256": forward_request_sha256,
        "action": FORWARD_RECOVERY_ACTION,
        "effect_class": FORWARD_EFFECT_CLASS,
        "started_at": started_at,
        "finished_at": _utc_now(),
        "exit_code": 0,
        "outcome": "SUCCEEDED",
        "release_sha": broker.config.release_root.name,
        "broker_version": broker.config.broker_version,
        "stdout_bytes": len(commitment_bytes),
        "stdout_sha256": hashlib.sha256(commitment_bytes).hexdigest(),
        "stdout_excerpt": broker_module._sanitize_terminal_excerpt(
            commitment_bytes.decode("utf-8", "replace")
        ),
        "stderr_bytes": 0,
        "stderr_sha256": hashlib.sha256(b"").hexdigest(),
        "stderr_excerpt": "",
    }
    try:
        broker_module._write_exclusive_json(
            terminal_path(broker.receipt_root), receipt
        )
        written = _strict_forward_document(terminal_path(broker.receipt_root))
        if written is None:
            raise ForwardRecoveryError("forward_terminal_lost")
        broker_module.validate_terminal_receipt(
            written[0], expected_request_id=ORIGINAL_ISSUER_REQUEST_ID
        )
        if written[0] != receipt:
            raise ForwardRecoveryError("forward_terminal_readback_mismatch")
    except (ForwardRecoveryError, OSError) as exc:
        raise _unknown(
            "forward terminal stage failed after the commitment", exc
        ) from exc

    # Terminal-then-settlement: remove ONLY the new forward guard.
    revalidate("before_settlement", reservation_sha256)
    try:
        guard_path(broker.receipt_root).unlink()
        broker_module._fsync_directory(broker.receipt_root)
    except OSError as exc:
        raise broker_module.EffectUnknownError(
            "forward terminal exists but guard settlement failed; consumers "
            "stay refused"
        ) from exc
    revalidate("after_settlement", reservation_sha256)
    return receipt, False
