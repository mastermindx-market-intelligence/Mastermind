"""Strict cause evidence, grant custody and one-use allocation for the
human-authorized bounded current-pin recovery capability.

This module owns three closed things and nothing else:

1. *Cause evidence.*  A separate, versioned, sanitized document that claims the
   retained adverse terminal effect was caused by an *ordinary* provider
   failure.  Ordinary cause may only be established by a producer whose exact
   installed source was reviewed and found to emit complete, bounded,
   structured failure evidence.  :data:`PRODUCER_QUALIFICATION` is that
   source-review output.  For the pinned ``codex`` 0.159.2 release it is
   deliberately EMPTY: ``exec_events.rs`` reduces every stream failure to
   ``ThreadErrorEvent { message: String }`` and
   ``event_processor_with_jsonl_output.rs`` discards the structured error
   before emitting, so no producer of this source can prove ordinary cause.
   Legacy ``provider_turn_failed`` / ``rate_limited`` words and capacity or
   model vocabulary are diagnostic only and are never promoted to cause.

   The table is not a configuration input.  No CLI flag, config key,
   environment value, receipt field, or raw JSON attribute can extend it, and
   no production path can mint qualified ordinary cause. The separate
   internal incident issuer is bound below to the separately authorized
   exact incident.

2. *Grant custody.*  One immutable root-owned grant document at a fixed
   internal location, bound to the authority reference, the exact installed
   source, the fixed company worker identity, the pinned credential metadata,
   the production model, the designated successor request id, an exact budget
   of one, and a finite 30..60 minute window.

3. *One-use allocation.*  A durable create-only consumption record keyed by
   the ORIGINAL predecessor receipt digest and scope, claimed before any
   inference.  There is no refund, no rewrite and no second key: a concurrent
   claim, a different predecessor, or a regrant all refuse.

This module performs no provider call, no process execution and no service
effect.  It is consumed by the existing Executive readiness transaction and by
broker reconciliation; it never replaces either.
"""
from __future__ import annotations

import dataclasses
import contextlib
import hashlib
import json
import os
import re
import stat
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping

try:
    from ops.executive_os import provider_readiness as _readiness
    from ops.executive_os.provider_worker_slots import get_slot
except ModuleNotFoundError:  # pragma: no cover - installed direct-script mode
    import provider_readiness as _readiness  # type: ignore[no-redef]
    from provider_worker_slots import get_slot  # type: ignore[no-redef]


RECOVERY_EVIDENCE_SCHEMA = "mastermind.executive_provider_recovery_cause/v1"
RECOVERY_GRANT_SCHEMA = "mastermind.executive_provider_recovery_grant/v1"
RECOVERY_ALLOCATION_SCHEMA = "mastermind.executive_provider_recovery_allocation/v1"
OBSERVATION_SCHEMA = "mastermind.executive_provider_recovery_observation/v1"

# Immutable authority reference.  The grant must name exactly this value; a
# digest or schema alone is never authority.
RECOVERY_AUTHORITY_REFERENCE = (
    "mastermind.current_pin_recovery/v1"
    "#authorize-the-bounded-recovery-policy@2026-10-12"
)

# Fixed internal custody location.  Never caller-selectable.
RECOVERY_STATE_ROOT = Path(
    "/var/db/mastermind-executive/provider-recovery/current-pin"
)
RECOVERY_GRANT_PATH = RECOVERY_STATE_ROOT / "grant.json"
RECOVERY_ALLOCATION_PATH = RECOVERY_STATE_ROOT / "allocation.json"

# Exact-incident recovery.  The incident grant and its issuance
# commitment live under the SAME existing recovery state root and reuse the
# SAME fixed allocation path; only their immutable document schemas differ.
# This names a separate policy class, not the ordinary-only human decision.
INCIDENT_AUTHORITY_REFERENCE = "mastermind.due10_incident_recovery/v1"
INCIDENT_POLICY_SCHEMA = "mastermind.executive_provider_incident_policy/v1"
INCIDENT_GRANT_SCHEMA = "mastermind.executive_provider_incident_grant/v1"
INCIDENT_COMMITMENT_SCHEMA = "mastermind.executive_provider_incident_commitment/v1"
# The closed v2 commitment schema of the dormant forward protocol.  This
# module owns the constant; provider_incident_forward re-exports it, so v1
# schema dispatch below never imports the optional forward module.
COMMITMENT_V2_SCHEMA = "mastermind.executive_provider_incident_commitment/v2"
INCIDENT_ALLOCATION_SCHEMA = "mastermind.executive_provider_incident_allocation/v1"
INCIDENT_RECOVERY_CLASS = "due10_incident"
INCIDENT_ISSUER_ACTION = "executive.worker_auth.issue_due10_incident_grant"
RECOVERY_INCIDENT_GRANT_PATH = RECOVERY_STATE_ROOT / "incident-grant.json"
RECOVERY_INCIDENT_COMMITMENT_PATH = RECOVERY_STATE_ROOT / "incident-commitment.json"

# Truthful historical classification.  Metadata proximity is not causation and
# no historical raw messages were retained, so the incident grant can never
# claim an established request-to-readiness causal link or a proven no-denial.
INCIDENT_HISTORICAL_CAUSE = "UNKNOWN"
INCIDENT_CAUSAL_LINK = "NOT_ESTABLISHED"

# Fixed designated evidence of the one retained incident. No environment,
# config, CLI, JSON or receipt field can install or alter its source policy.
# The separate reviewed human authorization below does not establish either
# historical cause or request-to-readiness attribution.
INCIDENT_DESIGNATED_EVIDENCE = {
    "original_request_id": "codex01-current-v5-company-01a1230a-20261011-10",
    "original_request_sha256":
        "612e85ce922cc9f97f2399d2a1d99e0250795026d86b3101ce32303df48e7863",
    "original_release_sha": "a858ac249296ffaa7bf523863dea5917bbbc1f24",
    "original_terminal_sha256":
        "1ed264ba7e356cd5f673056a8275aca5492016e9e5fb0f4b2f02f6768bcbdde3",
    "original_terminal_bytes": 785,
    "original_broker_exit_code": 65,
    "readiness_receipt_sha256":
        "05d9505d022dd82deca57b093759c6d44b4d2a1ddb09afd613b12b18a4b12b1a",
    "readiness_receipt_bytes": 3457,
    "canary_id": "canary-127d79f1f6bb",
    "canary_exit_code": 1,
}
# Retained diagnostic vocabulary that, if it ever appears in the retained
# canary evidence, excludes admission outright.  Absence of these terms is NOT
# proof that no denial occurred; raw messages were not retained.
INCIDENT_DENIAL_TERMS = frozenset(
    {"denied", "forbidden", "permission", "unauthorized"}
)

_GRANT_MAX_BYTES = 16 * 1024
MIN_GRANT_LIFETIME = timedelta(minutes=30)
MAX_GRANT_LIFETIME = timedelta(minutes=60)
# The whole capability is bounded to exactly one qualification attempt.
RECOVERY_BUDGET = 1
# Custody owner.  Production requires the dedicated root principal; the module
# constants exist so the same custody code can be exercised offline.
CUSTODY_UID = 0
CUSTODY_GID = 0

ORDINARY_FAILURE_CLASS = "ordinary_provider_turn_failed"
_FAILURE_CLASSES = frozenset({ORDINARY_FAILURE_CLASS})
RECOVERY_TERMINAL_EVENT_CLASS = "provider_turn_failed"
RECOVERY_REFUSAL = "provider_turn_failed"
RECOVERY_REFUSAL_EXIT_CODE = 1
MAX_EVENTS_TOTAL = 4096
MAX_EVENT_TYPES = 16

REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

_CREDENTIAL_LSTAT_FIELDS = frozenset(
    {"device", "inode", "uid", "gid", "mode", "size", "mtime_ns", "ctime_ns", "nlink"}
)

_EVIDENCE_FIELDS = frozenset(
    {
        "schema_version",
        "authority_reference",
        "producer",
        "original_request_id",
        "original_request_sha256",
        "original_terminal_sha256",
        "original_release_sha",
        "original_receipt_sha256",
        "original_result_completed",
        "original_canary_exit_code",
        "original_broker_exit_code",
        "original_timed_out",
        "original_signalled",
        "original_cancelled",
        "original_unknown_effect",
        "original_reserved",
        "original_denied",
        "observed_at",
    }
)
_PRODUCER_FIELDS = frozenset(
    {
        "producer_id",
        "failure_class",
        "codex_version",
        "codex_sha256",
        "event_schema",
        "event_types_seen",
        "events_total",
        "truncated",
        "conflicting_events",
        "malformed_events",
        "denial_refusal",
        "structured_error_code",
        "raw_message_digest",
    }
)
_GRANT_FIELDS = frozenset(
    {
        "schema_version",
        "authority_reference",
        "installed_source",
        "executive_source",
        "worker",
        "credential_lstat",
        "model",
        "cause_evidence",
        "successor_request_id",
        "budget",
        "granted_at",
        "expires_at",
    }
)
_GRANT_SOURCE_FIELDS = frozenset({"path", "version", "sha256", "team_identifier"})
_GRANT_WORKER_FIELDS = frozenset(
    {
        "worker_user",
        "worker_uid",
        "worker_gid",
        "provider_home",
        "workspace_binding_class",
        "expected_credential_kind",
    }
)
_ALLOCATION_FIELDS = frozenset(
    {
        "schema_version",
        "allocation_class",
        "authority_reference",
        "predecessor_receipt_sha256",
        "predecessor_request_id",
        "predecessor_request_sha256",
        "grant_sha256",
        "executive_source",
        "successor_request_id",
        "worker_uid",
        "worker_gid",
        "provider_home",
        "codex_version",
        "codex_sha256",
        "credential_lstat",
        "budget",
        "consumed",
        "claimed_at",
    }
)
_OBSERVATION_FIELDS = frozenset(
    {
        "schema_version",
        "observation_only",
        "readiness_issued",
        "observation_status",
        "refusal",
        "observed_at",
        "successor_request_id",
        "slot_id",
        "workspace_binding_class",
        "expected_credential_kind",
        "configured_model",
        "codex_binary",
        "executive_source",
        "credential_lstat",
        "provider_identity",
        "ordinary_usage_allowed",
        "model_catalog",
    }
)
_OBSERVATION_CATALOG_FIELDS = frozenset(
    {"listed_in_returned_page", "complete"}
)
_INCIDENT_EVIDENCE_FIELDS = frozenset(INCIDENT_DESIGNATED_EVIDENCE)
_INCIDENT_GRANT_FIELDS = frozenset(
    {
        "schema_version",
        "authority_reference",
        "incident_class",
        "historical_cause",
        "causal_link",
        "raw_provider_messages_retained",
        "authorization",
        "evidence",
        "installed_source",
        "executive_source",
        "worker",
        "credential_lstat",
        "model",
        "issuer_request_id",
        "issuer_request_sha256",
        "successor_request_id",
        "budget",
        "granted_at",
        "expires_at",
    }
)
_INCIDENT_AUTHORIZATION_FIELDS = frozenset({
    "schema_version", "policy_id", "question_sha256", "answer_sha256", "provenance_sha256",
})
_INCIDENT_COMMITMENT_FIELDS = frozenset(
    {
        "schema_version",
        "authorization",
        "incident_class",
        "grant_sha256",
        "issuer_request_id",
        "issuer_request_sha256",
        "successor_request_id",
        "created_at",
    }
)
_INCIDENT_ALLOCATION_FIELDS = _ALLOCATION_FIELDS | {
    "policy_id",
    "issuer_request_id",
    "issuer_request_sha256",
    "commitment_sha256",
}


class RecoveryError(RuntimeError):
    """A bounded, non-secret current-pin recovery refusal."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclasses.dataclass(frozen=True)
class ProducerQualification:
    """Closed output of one source review, not a runtime configuration.

    ``producers`` lists the producer identifiers whose exact installed source
    was reviewed and found to emit complete bounded structured ordinary-cause
    evidence.  ``vocabularies`` lists the only event types each qualified
    producer may report.  An empty table means no producer of any installed
    source can establish ordinary cause.
    """

    producers: tuple[str, ...]
    vocabularies: Mapping[str, tuple[str, ...]]
    terminal_events: Mapping[str, str]
    source_review_reference: str
    # A reviewed producer must prove the exact terminal-request/readiness
    # linkage, not merely assert a permitted event vocabulary. There is no
    # production verifier in this release and no configuration path to one.
    evidence_verifier: Callable[[Mapping[str, Any]], bool] | None = None

    def qualifies(self, producer_id: str) -> bool:
        return producer_id in self.producers

    def vocabulary(self, producer_id: str) -> tuple[str, ...]:
        return tuple(self.vocabularies.get(producer_id, ()))

    def terminal_event(self, producer_id: str) -> str | None:
        """Return the reviewed event type that closes a turn for one producer."""

        return self.terminal_events.get(producer_id)


# Source review of the pinned production release.  codex rust-v0.159.2
# ``exec_events.rs`` declares ``ThreadErrorEvent { pub message: String }`` and
# ``event_processor_with_jsonl_output.rs`` renders that single message (or the
# literal fallback "turn failed") while dropping the structured error, so the
# emitted JSONL cannot distinguish an ordinary provider failure from a denial,
# a cancellation, or any other terminal state.  No producer of this source is
# qualified, therefore the production current-pin admission stays closed.
PRODUCER_QUALIFICATION = ProducerQualification(
    producers=(),
    vocabularies=types.MappingProxyType({}),
    terminal_events=types.MappingProxyType({}),
    source_review_reference=(
        "openai/codex rust-v0.159.2 exec_events.rs ThreadErrorEvent{message:String}; "
        "event_processor_with_jsonl_output.rs discards structured error info"
    ),
)


@dataclasses.dataclass(frozen=True)
class IncidentPolicy:
    """Immutable, closed activation record for the one exact DUE10 incident.

    Every field is a fixed designated fact of the retained incident.  The
    policy is never an ordinary qualification table, never extends the
    ordinary producer review, and can never be assembled from caller
    evidence, dates, budgets, paths or source selectors.
    """

    policy_id: str
    question_sha256: str
    answer_sha256: str
    provenance_sha256: str
    original_request_id: str
    original_request_sha256: str
    original_release_sha: str
    original_terminal_sha256: str
    original_terminal_bytes: int
    original_broker_exit_code: int
    readiness_receipt_sha256: str
    readiness_receipt_bytes: int
    canary_id: str
    canary_exit_code: int

    def authorization_binding(self) -> dict[str, Any]:
        # These are retained provenance references supplied only by reviewed
        # installed source after a real decision, not cryptographic chat proof.
        return {
            "schema_version": INCIDENT_POLICY_SCHEMA,
            "policy_id": self.policy_id,
            "question_sha256": self.question_sha256,
            "answer_sha256": self.answer_sha256,
            "provenance_sha256": self.provenance_sha256,
        }

    def designated_evidence(self) -> dict[str, Any]:
        return {
            "original_request_id": self.original_request_id,
            "original_request_sha256": self.original_request_sha256,
            "original_release_sha": self.original_release_sha,
            "original_terminal_sha256": self.original_terminal_sha256,
            "original_terminal_bytes": self.original_terminal_bytes,
            "original_broker_exit_code": self.original_broker_exit_code,
            "readiness_receipt_sha256": self.readiness_receipt_sha256,
            "readiness_receipt_bytes": self.readiness_receipt_bytes,
            "canary_id": self.canary_id,
            "canary_exit_code": self.canary_exit_code,
        }


# Source-reviewed authorization for exactly this designated incident. The
# retained human question and answer explicitly accept both historical unknowns.
# Digests reference retained provenance; they are not a cryptographic chat
# attestation. No caller, environment, config or receipt field can replace this
# policy. Importing it creates no grant, successor, clock, allocation or effect;
# the authenticated broker and installed host gates still own issuance/use.
PRODUCTION_INCIDENT_POLICY: IncidentPolicy | None = IncidentPolicy(
    policy_id="due10-dual-unknown-one-attempt-20261013",
    question_sha256="660ddac062ace661a01984e4abddc0d36145c17226c352134ca4883eb7f82b0b",
    answer_sha256="590b9e4398dbd11400728d7c566e29bc4afd6c574a39a464f6581eae60b75028",
    provenance_sha256="b55221d99bbd31a90d68b9ea9c59a43d3b3191595a8fe2ce99dfdef2e7bcd2de",
    **INCIDENT_DESIGNATED_EVIDENCE,
)


def _require_exact_fields(
    value: Any, expected: frozenset[str], code: str
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or frozenset(value) != expected:
        raise RecoveryError(code)
    return dict(value)


def _hex_digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX64_RE.fullmatch(value) is None:
        raise RecoveryError(code)
    return value


def _request_id(value: Any, code: str) -> str:
    if not isinstance(value, str) or REQUEST_ID_RE.fullmatch(value) is None:
        raise RecoveryError(code)
    return value


def _strict_int(value: Any, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RecoveryError(code)
    return value


def _exact_bool(value: Any, expected: bool, code: str) -> bool:
    if value is not expected:
        raise RecoveryError(code)
    return expected


def _cause_producer(value: Any) -> dict[str, Any]:
    producer = _require_exact_fields(value, _PRODUCER_FIELDS, "recovery_cause_producer_malformed")
    if not isinstance(producer["producer_id"], str) or not 0 < len(producer["producer_id"]) <= 64:
        raise RecoveryError("recovery_cause_producer_malformed")
    if not isinstance(producer["failure_class"], str) or not 0 < len(producer["failure_class"]) <= 64:
        raise RecoveryError("recovery_cause_producer_malformed")
    if not isinstance(producer["event_schema"], str) or not 0 < len(producer["event_schema"]) <= 64:
        raise RecoveryError("recovery_cause_producer_malformed")
    if producer["codex_version"] != _readiness.CODEX_VERSION:
        raise RecoveryError("recovery_cause_producer_malformed")
    if producer["codex_sha256"] != _readiness.CODEX_SHA256:
        raise RecoveryError("recovery_cause_producer_malformed")
    seen = producer["event_types_seen"]
    if (
        not isinstance(seen, list)
        or not seen
        or len(seen) > MAX_EVENT_TYPES
        or any(not isinstance(item, str) or not 0 < len(item) <= 64 for item in seen)
        or seen != sorted(set(seen))
    ):
        raise RecoveryError("recovery_cause_producer_malformed")
    total = _strict_int(producer["events_total"], "recovery_cause_producer_malformed")
    if not 1 <= total <= MAX_EVENTS_TOTAL or total < len(seen):
        raise RecoveryError("recovery_cause_producer_malformed")
    malformed = _strict_int(
        producer["malformed_events"], "recovery_cause_producer_malformed"
    )
    if not 0 <= malformed <= total:
        raise RecoveryError("recovery_cause_producer_malformed")
    # Shape only.  Whether these are actually clean is a separate, later gate so
    # an unqualified producer is still reported as cause-unproven.
    if not isinstance(producer["truncated"], bool):
        raise RecoveryError("recovery_cause_producer_malformed")
    if not isinstance(producer["conflicting_events"], list) or any(
        not isinstance(item, str) or not 0 < len(item) <= 64
        for item in producer["conflicting_events"]
    ):
        raise RecoveryError("recovery_cause_producer_malformed")
    for nullable in ("denial_refusal", "structured_error_code", "raw_message_digest"):
        value = producer[nullable]
        if value is not None and (not isinstance(value, str) or not 0 < len(value) <= 128):
            raise RecoveryError("recovery_cause_producer_malformed")
    return producer


def validate_cause_document(value: Any) -> dict[str, Any]:
    """Return the normalized cause document, or raise a bounded refusal.

    Only structure, types and closed values are checked here.  Producer
    qualification is a separate, later gate so that an unqualified producer is
    always reported as ``recovery_failure_cause_unproven``.
    """

    document = _require_exact_fields(
        value, _EVIDENCE_FIELDS, "recovery_cause_fields_malformed"
    )
    if document["schema_version"] != RECOVERY_EVIDENCE_SCHEMA:
        raise RecoveryError("recovery_cause_schema_malformed")
    if document["authority_reference"] != RECOVERY_AUTHORITY_REFERENCE:
        raise RecoveryError("recovery_cause_authority_mismatch")
    _request_id(document["original_request_id"], "recovery_cause_identity_malformed")
    _hex_digest(document["original_request_sha256"], "recovery_cause_identity_malformed")
    _hex_digest(document["original_terminal_sha256"], "recovery_cause_identity_malformed")
    if not isinstance(document["original_release_sha"], str) or re.fullmatch(
        r"[0-9a-f]{40}", document["original_release_sha"]
    ) is None:
        raise RecoveryError("recovery_cause_identity_malformed")
    _hex_digest(document["original_receipt_sha256"], "recovery_cause_identity_malformed")
    _exact_bool(document["original_result_completed"], True, "recovery_cause_outcome_malformed")
    if _strict_int(
        document["original_canary_exit_code"], "recovery_cause_outcome_malformed"
    ) != RECOVERY_REFUSAL_EXIT_CODE:
        raise RecoveryError("recovery_cause_outcome_malformed")
    if _strict_int(
        document["original_broker_exit_code"], "recovery_cause_outcome_malformed"
    ) <= 0:
        raise RecoveryError("recovery_cause_outcome_malformed")
    for field in (
        "original_timed_out",
        "original_signalled",
        "original_cancelled",
        "original_unknown_effect",
        "original_reserved",
        "original_denied",
    ):
        _exact_bool(document[field], False, "recovery_cause_outcome_malformed")
    try:
        _readiness._timestamp(document["observed_at"], code="recovery_cause_identity_malformed")
    except _readiness.ReadinessError as exc:
        raise RecoveryError("recovery_cause_identity_malformed") from exc
    producer = _cause_producer(document["producer"])
    return {**document, "producer": producer}


def evaluate_cause(
    value: Any,
    *,
    qualification: ProducerQualification = PRODUCER_QUALIFICATION,
) -> dict[str, Any]:
    """Validate cause evidence and return it, or raise a bounded refusal.

    ``qualification`` is the closed source-review table.  Production callers
    use the default, which is empty, so every production submission stops at
    ``recovery_failure_cause_unproven`` before any claim, archive, reservation
    or inference.  The parameter exists so the allocation, archive and CAS
    machinery can be exercised offline against a reviewed test table; it is
    never reachable from argv, config, environment, or any receipt field.
    """

    document = validate_cause_document(value)
    producer = document["producer"]
    if producer["denial_refusal"] is not None or document["original_denied"] is not False:
        raise RecoveryError("recovery_cause_denial_excluded")
    if producer["failure_class"] not in _FAILURE_CLASSES:
        raise RecoveryError("recovery_cause_class_uncertain")
    if not qualification.qualifies(producer["producer_id"]):
        # The pinned production source cannot establish ordinary cause.  This is
        # the terminal production answer for every current-exec submission.
        raise RecoveryError("recovery_failure_cause_unproven")
    if (
        producer["truncated"] is not False
        or producer["conflicting_events"]
        or producer["malformed_events"] != 0
        or producer["structured_error_code"] is not None
        or producer["raw_message_digest"] is not None
    ):
        raise RecoveryError("recovery_cause_coverage_incomplete")
    vocabulary = qualification.vocabulary(producer["producer_id"])
    unknown = [item for item in producer["event_types_seen"] if item not in vocabulary]
    if unknown:
        raise RecoveryError("recovery_cause_event_unreviewed")
    terminal_event = qualification.terminal_event(producer["producer_id"])
    if terminal_event is None or terminal_event not in producer["event_types_seen"]:
        raise RecoveryError("recovery_cause_terminal_event_absent")
    if qualification.evidence_verifier is None:
        raise RecoveryError("recovery_failure_link_unproven")
    try:
        linked = qualification.evidence_verifier(document)
    except Exception as exc:
        raise RecoveryError("recovery_failure_link_unproven") from exc
    if linked is not True:
        raise RecoveryError("recovery_failure_link_unproven")
    return document


def _executive_source(value: Any) -> dict[str, Any]:
    source = _require_exact_fields(value, frozenset({"release_sha", "manifest_sha256"}),
                                   "recovery_executive_source_malformed")
    if not isinstance(source["release_sha"], str) or re.fullmatch(
        r"[0-9a-f]{40}", source["release_sha"]
    ) is None:
        raise RecoveryError("recovery_executive_source_malformed")
    _hex_digest(source["manifest_sha256"], "recovery_executive_source_malformed")
    return source


def current_executive_source() -> dict[str, str]:
    """Derive the loaded, sealed Executive release; no caller source selector."""
    from control_plane import executive_privileged_broker as broker
    from ops.executive_os import release_manifest

    root = Path(__file__).resolve(strict=True).parents[2]
    if root.parent != broker._RELEASE_PREFIX or re.fullmatch(r"[0-9a-f]{40}", root.name) is None:
        raise RecoveryError("recovery_executive_source_uninstalled")
    manifest_path = root / release_manifest.MANIFEST_NAME
    try:
        raw = manifest_path.read_bytes()
        document = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
        tree = document.get("tree_sha")
        if not isinstance(tree, str) or re.fullmatch(r"[0-9a-f]{40}", tree) is None:
            raise RecoveryError("recovery_executive_source_malformed")
        release_manifest.verify(root, root.name, tree)
        if manifest_path.read_bytes() != raw:
            raise RecoveryError("recovery_executive_source_changed")
    except (OSError, ValueError, release_manifest.ReleaseManifestError) as exc:
        raise RecoveryError("recovery_executive_source_unverified") from exc
    return {"release_sha": root.name, "manifest_sha256": hashlib.sha256(raw).hexdigest()}


def validate_original_terminal(cause: Mapping[str, Any]) -> dict[str, Any]:
    """Join actual original broker terminal bytes; this alone is not cause proof."""
    from control_plane import executive_privileged_broker as broker

    request_id = _request_id(cause["original_request_id"], "recovery_cause_identity_malformed")
    receipt_root = broker._RECEIPT_ROOT
    path = receipt_root / (request_id + ".json")
    try:
        for directory in (receipt_root.parent.parent, receipt_root.parent,
                          receipt_root, receipt_root / "inflight", receipt_root / "reconciled"):
            broker._assert_root_owned_nonwritable(directory, directory=True)
            _readiness._assert_no_macos_acl(directory)
        for directory in ("inflight", "reconciled"):
            other = receipt_root / directory / path.name
            try:
                other.lstat()
            except FileNotFoundError:
                continue
            raise RecoveryError("recovery_original_request_unsettled")
        raw, info = broker._read_stable_bounded_bytes(path)
        if (info.st_uid != CUSTODY_UID or info.st_gid != CUSTODY_GID or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600):
            raise RecoveryError("recovery_original_request_custody_unsafe")
        _readiness._assert_no_macos_acl(path)
        if hashlib.sha256(raw).hexdigest() != cause["original_terminal_sha256"]:
            raise RecoveryError("recovery_original_request_preimage_mismatch")
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
        result = broker.validate_terminal_receipt(value,
            expected_request_id=request_id,
            expected_request_sha256=cause["original_request_sha256"],
            expected_release_sha=cause["original_release_sha"],
            expected_action="executive.worker_auth.verify_ready")
        if result["outcome"] != "FAILED" or result["exit_code"] <= 0:
            raise RecoveryError("recovery_original_request_not_adverse")
        if result["exit_code"] != cause["original_broker_exit_code"]:
            raise RecoveryError("recovery_original_request_exit_mismatch")
        observed = _readiness._timestamp(cause["observed_at"], code="recovery_cause_identity_malformed")
        started = _readiness._timestamp(result["started_at"], code="recovery_cause_identity_malformed")
        finished = _readiness._timestamp(result["finished_at"], code="recovery_cause_identity_malformed")
        if not started - _readiness.MAX_CLOCK_SKEW <= observed <= finished + _readiness.MAX_CLOCK_SKEW:
            raise RecoveryError("recovery_original_request_clock_conflict")
    except (OSError, ValueError, broker.BrokerTrustError) as exc:
        raise RecoveryError("recovery_original_request_unverified") from exc
    return result


def _credential_lstat(value: Any, code: str) -> dict[str, Any]:
    metadata = _require_exact_fields(value, _CREDENTIAL_LSTAT_FIELDS, code)
    for field in sorted(_CREDENTIAL_LSTAT_FIELDS):
        if type(metadata[field]) is not int or metadata[field] < 0:
            raise RecoveryError(code)
    if metadata["uid"] != _readiness.WORKER_UID or metadata["gid"] != _readiness.WORKER_GID:
        raise RecoveryError(code)
    if metadata["mode"] != 0o600 or metadata["nlink"] != 1:
        raise RecoveryError(code)
    if metadata["device"] <= 0 or metadata["inode"] <= 0 or metadata["size"] <= 0:
        raise RecoveryError(code)
    return metadata


def _grant_source(value: Any) -> dict[str, Any]:
    source = _require_exact_fields(value, _GRANT_SOURCE_FIELDS, "recovery_grant_source_mismatch")
    if (
        source["path"] != os.fspath(_readiness.CODEX_BINARY)
        or source["version"] != _readiness.CODEX_VERSION
        or source["sha256"] != _readiness.CODEX_SHA256
        or source["team_identifier"] != _readiness.CODEX_TEAM_ID
    ):
        raise RecoveryError("recovery_grant_source_mismatch")
    return source


def _grant_worker(value: Any) -> dict[str, Any]:
    worker = _require_exact_fields(value, _GRANT_WORKER_FIELDS, "recovery_grant_worker_mismatch")
    expected_home = os.fspath(_readiness.AUTH_PATH.parent)
    if (
        worker["worker_user"] != get_slot("codex-01").worker_user
        or worker["worker_uid"] != _readiness.WORKER_UID
        or worker["worker_gid"] != _readiness.WORKER_GID
        or worker["provider_home"] != expected_home
        or worker["workspace_binding_class"] != _readiness.COMPANY_WORKSPACE_BINDING_CLASS
        or worker["expected_credential_kind"] != "device-auth"
    ):
        raise RecoveryError("recovery_grant_worker_mismatch")
    return worker


def _validate_historical_grant_document(value: Any) -> dict[str, Any]:
    """Validate immutable evidence structure, without granting admission now."""

    grant = _require_exact_fields(value, _GRANT_FIELDS, "recovery_grant_fields_malformed")
    if grant["schema_version"] != RECOVERY_GRANT_SCHEMA:
        raise RecoveryError("recovery_grant_schema_malformed")
    if grant["authority_reference"] != RECOVERY_AUTHORITY_REFERENCE:
        raise RecoveryError("recovery_grant_authority_mismatch")
    _grant_source(grant["installed_source"])
    _executive_source(grant["executive_source"])
    _grant_worker(grant["worker"])
    _credential_lstat(grant["credential_lstat"], "recovery_grant_credential_mismatch")
    if grant["model"] != _readiness.PRODUCTION_MODEL:
        raise RecoveryError("recovery_grant_model_mismatch")
    budget = grant["budget"]
    if isinstance(budget, bool) or not isinstance(budget, int) or budget != RECOVERY_BUDGET:
        raise RecoveryError("recovery_grant_budget_invalid")
    _request_id(grant["successor_request_id"], "recovery_grant_successor_malformed")
    # The embedded cause evidence must still validate on its own terms, so a
    # grant can never carry weaker evidence than the live validator accepts.
    try:
        cause = validate_cause_document(grant["cause_evidence"])
    except RecoveryError as exc:
        raise RecoveryError("recovery_grant_cause_mismatch") from exc
    try:
        granted_at = _readiness._timestamp(
            grant["granted_at"], code="recovery_grant_window_invalid"
        )
        expires_at = _readiness._timestamp(
            grant["expires_at"], code="recovery_grant_window_invalid"
        )
    except _readiness.ReadinessError as exc:
        raise RecoveryError("recovery_grant_window_invalid") from exc
    lifetime = expires_at - granted_at
    if not MIN_GRANT_LIFETIME <= lifetime <= MAX_GRANT_LIFETIME:
        raise RecoveryError("recovery_grant_window_invalid")
    return {**grant, "cause_evidence": cause}


def validate_grant_document(
    value: Any, *, now: datetime | None = None
) -> dict[str, Any]:
    """Validate immutable evidence and the current live admission window."""
    grant = _validate_historical_grant_document(value)
    granted_at = _readiness._timestamp(grant["granted_at"], code="recovery_grant_window_invalid")
    expires_at = _readiness._timestamp(grant["expires_at"], code="recovery_grant_window_invalid")
    current = datetime.now(UTC) if now is None else now
    if granted_at > current:
        raise RecoveryError("recovery_grant_window_invalid")
    if expires_at <= current:
        raise RecoveryError("recovery_grant_expired")
    return grant


def _directory_identity(info: os.stat_result) -> tuple[int, ...]:
    # Directory size/timestamps/link count change when this installer creates
    # its child. Ownership, permissions and inode identity must never change.
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)


def _check_recovery_directory(path: Path, descriptor: int, *, private: bool) -> None:
    before = os.fstat(descriptor)
    if (not stat.S_ISDIR(before.st_mode)
            or before.st_uid != CUSTODY_UID or before.st_gid != CUSTODY_GID
            or (stat.S_IMODE(before.st_mode) != 0o700 if private
                else bool(stat.S_IMODE(before.st_mode) & 0o022))):
        raise RecoveryError("recovery_custody_parent_unsafe")
    if _directory_identity(path.lstat()) != _directory_identity(before):
        raise RecoveryError("recovery_custody_parent_changed")
    _readiness._assert_no_macos_acl(path)
    if (_directory_identity(path.lstat()) != _directory_identity(before)
            or _directory_identity(os.fstat(descriptor)) != _directory_identity(before)):
        raise RecoveryError("recovery_custody_parent_changed")


@contextlib.contextmanager
def _recovery_directory_chain(*, create_missing: bool = False):
    """Hold the fixed chain below the already-qualified Executive state root.

    Only the installer may create missing private directories. Existing
    directories are checked, never normalized; no custody document is touched.
    Darwin's system-owned /var alias is outside this existing state-root join.
    """
    records: list[tuple[Path, int, bool]] = []
    identities: list[tuple[int, ...]] = []

    def revalidate() -> None:
        for (path, descriptor, private), identity in zip(records, identities):
            _check_recovery_directory(path, descriptor, private=private)
            if _directory_identity(os.fstat(descriptor)) != identity:
                raise RecoveryError("recovery_custody_parent_changed")

    try:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        root = RECOVERY_STATE_ROOT.parent.parent
        descriptor = os.open(root, flags)
        records.append((root, descriptor, False))
        identities.append(_directory_identity(os.fstat(descriptor)))
        revalidate()
        for path in (RECOVERY_STATE_ROOT.parent, RECOVERY_STATE_ROOT):
            revalidate()
            parent_descriptor = records[-1][1]
            created = False
            try:
                os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
            except FileNotFoundError:
                if not create_missing:
                    raise RecoveryError("recovery_custody_parent_missing") from None
                # A concurrent occupant must refuse rather than be adopted.
                os.mkdir(path.name, mode=0o700, dir_fd=parent_descriptor)
                created = True
            descriptor = os.open(path.name, flags, dir_fd=parent_descriptor)
            records.append((path, descriptor, True))
            identities.append(_directory_identity(os.fstat(descriptor)))
            revalidate()
            if created:
                os.fsync(descriptor)
                os.fsync(parent_descriptor)
                revalidate()
        yield records[-1][1]
        revalidate()
    except FileNotFoundError as exc:
        raise RecoveryError("recovery_custody_parent_missing") from exc
    except (OSError, _readiness.ReadinessError) as exc:
        raise RecoveryError("recovery_custody_unreadable") from exc
    finally:
        for _path, descriptor, _private in reversed(records):
            os.close(descriptor)


def prepare_recovery_custody() -> None:
    """Installer-only creation of the two fixed missing custody directories.

    This does not admit an issuer, alter an existing marker, or authorize
    recovery of any earlier unknown operation.
    """
    if os.geteuid() != CUSTODY_UID:
        raise RecoveryError("recovery_custody_installer_owner_mismatch")
    with _recovery_directory_chain(create_missing=True):
        pass


def preflight_recovery_custody() -> None:
    """Read-only custody and empty-slot check before a fresh issuer marker.

    Missing parents are not empty records. Any occupant blocks fresh issuance;
    a matching grant is not a terminal replay receipt or a resume capability.
    Post-preflight races still meet the unchanged create-only write path.
    """
    slots = (RECOVERY_GRANT_PATH, RECOVERY_INCIDENT_GRANT_PATH,
             RECOVERY_INCIDENT_COMMITMENT_PATH, RECOVERY_ALLOCATION_PATH)
    with _recovery_directory_chain() as descriptor:
        for path in slots:
            if path.parent != RECOVERY_STATE_ROOT:
                raise RecoveryError("recovery_custody_path_unreviewed")
            try:
                os.stat(path.name, dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise RecoveryError("recovery_custody_slot_occupied")


def _validate_state_directory(path: Path) -> None:
    """Require the fixed root-owned custody chain, without following symlinks."""

    if path not in (
        RECOVERY_GRANT_PATH,
        RECOVERY_ALLOCATION_PATH,
        RECOVERY_INCIDENT_GRANT_PATH,
        RECOVERY_INCIDENT_COMMITMENT_PATH,
    ):
        raise RecoveryError("recovery_custody_path_unreviewed")
    for ancestor in (
        RECOVERY_STATE_ROOT.parent.parent,
        RECOVERY_STATE_ROOT.parent,
        RECOVERY_STATE_ROOT,
    ):
        info = ancestor.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != CUSTODY_UID
            or info.st_gid != CUSTODY_GID
            or (stat.S_IMODE(info.st_mode) & 0o022) != 0
        ):
            raise RecoveryError("recovery_custody_parent_unsafe")
        _readiness._assert_no_macos_acl(ancestor)


def _read_custody_bytes(path: Path, *, maximum: int) -> bytes:
    _validate_state_directory(path)
    info = path.lstat()
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or info.st_uid != CUSTODY_UID
        or info.st_gid != CUSTODY_GID
        or stat.S_IMODE(info.st_mode) != 0o400
        or info.st_nlink != 1
    ):
        raise RecoveryError("recovery_custody_metadata_unsafe")
    if info.st_size <= 0 or info.st_size > maximum:
        raise RecoveryError("recovery_custody_size_invalid")
    _readiness._assert_no_macos_acl(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        def identity(value):
            return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
                    value.st_gid, value.st_nlink, value.st_size,
                    value.st_mtime_ns, value.st_ctime_ns)
        if identity(before) != identity(info):
            raise RecoveryError("recovery_custody_changed_during_read")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining > 0:
            part = os.read(descriptor, min(4096, remaining))
            if not part:
                break
            chunks.append(part)
            remaining -= len(part)
        raw = b"".join(chunks)
        after = os.fstat(descriptor)
    except OSError as exc:
        raise RecoveryError("recovery_custody_unreadable") from exc
    finally:
        os.close(descriptor)
    after_path = path.lstat()
    if (
        len(raw) != before.st_size
        or identity(before) != identity(after)
        or identity(after) != identity(after_path)
    ):
        raise RecoveryError("recovery_custody_changed_during_read")
    return raw


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RecoveryError("recovery_custody_duplicate_keys")
        result[key] = value
    return result


def _read_custody_document(
    raw: bytes, *, schema: str
) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except RecoveryError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RecoveryError("recovery_custody_unreadable") from exc
    if not isinstance(value, dict):
        raise RecoveryError("recovery_custody_unreadable")
    if value.get("schema_version") != schema:
        raise RecoveryError("recovery_custody_schema_malformed")
    return value


def read_grant(
    path: Path | None = None,
    *,
    expected_digest: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Read and fully validate one root-owned grant at its fixed location.

    ``expected_digest`` is the caller-supplied preimage.  A matching digest is
    necessary but never sufficient: full custody, schema, canonical field and
    type checks all run regardless.
    """

    return validate_grant_document(_read_grant_document(path, expected_digest=expected_digest), now=now)


def _read_historical_grant(*, expected_digest: str) -> dict[str, Any]:
    """Read fixed immutable grant evidence for reconstruction/reconciliation only.

    No current-window admission is granted. Live qualification and reservation
    must continue to use read_grant; there is no caller-selected expiry bypass.
    """
    return _validate_historical_grant_document(
        _read_grant_document(None, expected_digest=expected_digest)
    )


def _read_grant_document(path: Path | None, *, expected_digest: str) -> dict[str, Any]:
    if path is None:
        path = RECOVERY_GRANT_PATH
    _hex_digest(expected_digest, "recovery_grant_digest_malformed")
    raw = _read_custody_bytes(path, maximum=_GRANT_MAX_BYTES)
    if hashlib.sha256(raw).hexdigest() != expected_digest:
        raise RecoveryError("recovery_grant_digest_mismatch")
    return _read_custody_document(raw, schema=RECOVERY_GRANT_SCHEMA)


def read_grant_digest(path: Path | None = None) -> str:
    """Return the digest of one custody-checked grant without parsing it.

    Reconciliation uses this to reconstruct a designated successor request it
    can then verify byte-for-byte against the recorded target digest.  A
    missing, drifted or unreadable grant refuses; it is never guessed.
    """

    if path is None:
        path = RECOVERY_GRANT_PATH
    return hashlib.sha256(
        _read_custody_bytes(path, maximum=_GRANT_MAX_BYTES)
    ).hexdigest()


def read_allocation(path: Path | None = None) -> dict[str, Any] | None:
    """Return the durable allocation record, or ``None`` when none was claimed."""

    if path is None:
        path = RECOVERY_ALLOCATION_PATH
    try:
        path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise RecoveryError("recovery_custody_unreadable") from exc
    raw = _read_custody_bytes(path, maximum=_GRANT_MAX_BYTES)
    record = _read_custody_json(raw)
    if record.get("schema_version") == INCIDENT_ALLOCATION_SCHEMA:
        return _validate_incident_allocation_document(record)
    if record.get("schema_version") != RECOVERY_ALLOCATION_SCHEMA:
        raise RecoveryError("recovery_custody_schema_malformed")
    _require_exact_fields(record, _ALLOCATION_FIELDS, "recovery_allocation_fields_malformed")
    if record["allocation_class"] != "current_pin_recovery":
        raise RecoveryError("recovery_allocation_fields_malformed")
    if record["authority_reference"] != RECOVERY_AUTHORITY_REFERENCE:
        raise RecoveryError("recovery_allocation_fields_malformed")
    for field in ("predecessor_receipt_sha256", "predecessor_request_sha256", "grant_sha256"):
        _hex_digest(record[field], "recovery_allocation_fields_malformed")
    _request_id(record["predecessor_request_id"], "recovery_allocation_fields_malformed")
    _request_id(record["successor_request_id"], "recovery_allocation_fields_malformed")
    if (record["worker_uid"], record["worker_gid"]) != (
        _readiness.WORKER_UID,
        _readiness.WORKER_GID,
    ) or record["provider_home"] != os.fspath(_readiness.AUTH_PATH.parent):
        raise RecoveryError("recovery_allocation_fields_malformed")
    if (record["codex_version"], record["codex_sha256"]) != (
        _readiness.CODEX_VERSION,
        _readiness.CODEX_SHA256,
    ):
        raise RecoveryError("recovery_allocation_fields_malformed")
    _credential_lstat(record["credential_lstat"], "recovery_allocation_fields_malformed")
    _executive_source(record["executive_source"])
    if (type(record["budget"]) is not int or record["budget"] != RECOVERY_BUDGET
            or record["consumed"] is not True):
        raise RecoveryError("recovery_allocation_not_consumed")
    _readiness._timestamp(record["claimed_at"], code="recovery_allocation_fields_malformed")
    return record

def _read_custody_json(raw: bytes) -> dict[str, Any]:
    """Parse custody bytes with duplicate-key rejection but any known schema."""

    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except RecoveryError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RecoveryError("recovery_custody_unreadable") from exc
    if not isinstance(value, dict):
        raise RecoveryError("recovery_custody_unreadable")
    return value


def validate_incident_authorization(value: Any) -> dict[str, Any]:
    binding = _require_exact_fields(
        value, _INCIDENT_AUTHORIZATION_FIELDS, "incident_authorization_malformed"
    )
    if binding["schema_version"] != INCIDENT_POLICY_SCHEMA:
        raise RecoveryError("incident_authorization_malformed")
    _request_id(binding["policy_id"], "incident_authorization_malformed")
    for field in ("question_sha256", "answer_sha256", "provenance_sha256"):
        _hex_digest(binding[field], "incident_authorization_malformed")
    return binding


def require_current_incident_policy(grant: Mapping[str, Any]) -> None:
    policy = PRODUCTION_INCIDENT_POLICY
    if policy is None:
        raise RecoveryError("incident_policy_dormant")
    designated = validate_incident_policy(policy)
    if (grant["authorization"] != policy.authorization_binding()
            or grant["evidence"] != designated):
        raise RecoveryError("incident_policy_binding_mismatch")


def validate_incident_policy(value: Any) -> dict[str, Any]:
    """Return the designated evidence of one well-formed incident policy.

    Structural and closed-value checks only: this never activates anything and
    never compares the policy to caller-supplied evidence. Live consumption
    separately requires the exact configured policy and authenticated issuance.
    """

    if not isinstance(value, IncidentPolicy):
        raise RecoveryError("incident_policy_malformed")
    validate_incident_authorization(value.authorization_binding())
    evidence = value.designated_evidence()
    _request_id(evidence["original_request_id"], "incident_policy_malformed")
    for field in ("original_request_sha256", "original_terminal_sha256",
                  "readiness_receipt_sha256"):
        _hex_digest(evidence[field], "incident_policy_malformed")
    if not isinstance(evidence["original_release_sha"], str) or re.fullmatch(
        r"[0-9a-f]{40}", evidence["original_release_sha"]
    ) is None:
        raise RecoveryError("incident_policy_malformed")
    for field in ("original_terminal_bytes", "readiness_receipt_bytes"):
        if type(evidence[field]) is not int or evidence[field] <= 0:
            raise RecoveryError("incident_policy_malformed")
    if (type(evidence["original_broker_exit_code"]) is not int
            or evidence["original_broker_exit_code"] <= 0):
        raise RecoveryError("incident_policy_malformed")
    if (type(evidence["canary_exit_code"]) is not int
            or evidence["canary_exit_code"] != RECOVERY_REFUSAL_EXIT_CODE):
        raise RecoveryError("incident_policy_malformed")
    if (not isinstance(evidence["canary_id"], str)
            or _readiness.CANARY_ID_RE.fullmatch(evidence["canary_id"]) is None):
        raise RecoveryError("incident_policy_malformed")
    return evidence


def refuse_evidenced_incident_denial(document: Any) -> None:
    """Exclude admission when retained evidence actually shows a denial.

    This is an exclusion only.  Retained clean terms are never promoted into a
    claim that no denial occurred, because no historical raw messages exist.
    """

    if not isinstance(document, Mapping):
        return
    canary = document.get("inference_canary")
    terms = canary.get("provider_error_terms") if isinstance(canary, Mapping) else None
    if isinstance(terms, list) and any(term in INCIDENT_DENIAL_TERMS for term in terms):
        raise RecoveryError("incident_denial_evidenced")


def validate_incident_designated_terminal(designated: Mapping[str, Any]) -> dict[str, Any]:
    """Join the designated original terminal bytes from the fixed broker store.

    Custody walk, settled-marker absence, exact byte digest and length, and the
    canonical FAILED receipt shape with the designated broker exit code.  No
    timing-proximity claim is made: metadata proximity is not causation and the
    incident grant never asserts one.
    """

    from control_plane import executive_privileged_broker as broker

    request_id = _request_id(
        designated["original_request_id"], "incident_evidence_malformed"
    )
    receipt_root = broker._RECEIPT_ROOT
    path = receipt_root / (request_id + ".json")
    try:
        for directory in (receipt_root.parent.parent, receipt_root.parent,
                          receipt_root, receipt_root / "inflight",
                          receipt_root / "reconciled"):
            broker._assert_root_owned_nonwritable(directory, directory=True)
            _readiness._assert_no_macos_acl(directory)
        for directory in ("inflight", "reconciled"):
            other = receipt_root / directory / path.name
            try:
                other.lstat()
            except FileNotFoundError:
                continue
            raise RecoveryError("recovery_original_request_unsettled")
        raw, info = broker._read_stable_bounded_bytes(path)
        if (info.st_uid != CUSTODY_UID or info.st_gid != CUSTODY_GID
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
            raise RecoveryError("recovery_original_request_custody_unsafe")
        _readiness._assert_no_macos_acl(path)
        if (hashlib.sha256(raw).hexdigest() != designated["original_terminal_sha256"]
                or len(raw) != designated["original_terminal_bytes"]):
            raise RecoveryError("recovery_original_request_preimage_mismatch")
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
        result = broker.validate_terminal_receipt(
            value,
            expected_request_id=request_id,
            expected_request_sha256=designated["original_request_sha256"],
            expected_release_sha=designated["original_release_sha"],
            expected_action="executive.worker_auth.verify_ready",
        )
        if result["outcome"] != "FAILED":
            raise RecoveryError("recovery_original_request_not_adverse")
        if result["exit_code"] != designated["original_broker_exit_code"]:
            raise RecoveryError("recovery_original_request_exit_mismatch")
    except (OSError, ValueError, broker.BrokerTrustError) as exc:
        raise RecoveryError("recovery_original_request_unverified") from exc
    return result


def validate_incident_designated_readiness(
    document: Any,
    designated: Mapping[str, Any],
    *,
    auth_identity: Mapping[str, Any],
    binary_identity: Mapping[str, Any],
    worker_uid: int = _readiness.WORKER_UID,
    worker_gid: int = _readiness.WORKER_GID,
) -> None:
    """Check the retained readiness predecessor against the designated policy.

    Closed terminal-adverse shape only: the pinned binary, the current
    credential identity, the designated canary identity, exit and refusal
    class.  This is evidence consistency, never a causal proof.
    """

    if (not isinstance(document, Mapping)
            or frozenset(document) != _readiness._RECEIPT_FIELDS
            or document.get("schema_version") != _readiness.SCHEMA_VERSION
            or document.get("passed") is not False
            or document.get("refusal") != RECOVERY_REFUSAL
            or document.get("expected_credential_kind") != "device-auth"
            or document.get("workspace_binding_class")
            != _readiness.COMPANY_WORKSPACE_BINDING_CLASS
            or document.get("forced_chatgpt_workspace_id_applied") is not False):
        raise RecoveryError("recovery_predecessor_not_terminal_adverse")
    _readiness._deadline_fields(
        observed_at=document.get("observed_at"),
        credential_expires_at=document.get("credential_expires_at"),
        readiness_expires_at=document.get("readiness_expires_at"),
        allow_expired_readiness=True,
    )
    _readiness._assert_worker_identity(
        auth_identity, worker_uid=worker_uid, worker_gid=worker_gid
    )
    if dict(document.get("credential_lstat") or {}) != dict(auth_identity):
        raise RecoveryError("recovery_predecessor_credential_mismatch")
    if dict(document.get("codex_binary") or {}) != dict(binary_identity):
        raise RecoveryError("recovery_predecessor_source_mismatch")
    identity, canary = document.get("provider_identity"), document.get("inference_canary")
    if not isinstance(identity, Mapping) or not isinstance(canary, Mapping):
        raise RecoveryError("recovery_predecessor_not_terminal_adverse")
    safe_identity = _readiness._safe_identity(identity)
    safe_canary = _readiness._safe_canary(canary, binary_identity=binary_identity)
    if (safe_identity["refusal"] is not None
            or safe_identity["codex_binary"] != dict(binary_identity)
            or safe_identity["credential_lstat"] != dict(auth_identity)
            or safe_identity["expected_credential_kind"] != "device-auth"
            or safe_identity["workspace_binding_class"]
            != _readiness.COMPANY_WORKSPACE_BINDING_CLASS):
        raise RecoveryError("recovery_predecessor_identity_mismatch")
    if (safe_canary["passed"] is not False
            or type(safe_canary["exit_code"]) is not int
            or safe_canary["exit_code"] != designated["canary_exit_code"]
            or safe_canary["timed_out"] is not False
            or safe_canary["terminal_event_class"] != RECOVERY_TERMINAL_EVENT_CLASS
            or safe_canary["result_valid"] is not False
            or safe_canary["refusal"] != RECOVERY_REFUSAL
            or safe_canary["canary_id"] != designated["canary_id"]
            or safe_canary["model"] != _readiness.PRODUCTION_MODEL):
        raise RecoveryError("recovery_predecessor_effect_not_closed")

    def _component_time(value: Any) -> Any:
        try:
            return _readiness._timestamp(
                value, code="recovery_predecessor_timestamp_malformed"
            )
        except _readiness.ReadinessError as exc:
            raise RecoveryError("recovery_predecessor_timestamp_malformed") from exc

    observed = _component_time(document["observed_at"])
    for component in (safe_identity, safe_canary):
        if abs(_component_time(component["observed_at"]) - observed) > _readiness.MAX_CLOCK_SKEW:
            raise RecoveryError("recovery_predecessor_timestamp_conflict")


def _validate_incident_evidence(value: Any) -> dict[str, Any]:
    evidence = _require_exact_fields(
        value, _INCIDENT_EVIDENCE_FIELDS, "incident_evidence_malformed"
    )
    _request_id(evidence["original_request_id"], "incident_evidence_malformed")
    for field in ("original_request_sha256", "original_terminal_sha256",
                  "readiness_receipt_sha256"):
        _hex_digest(evidence[field], "incident_evidence_malformed")
    if not isinstance(evidence["original_release_sha"], str) or re.fullmatch(
        r"[0-9a-f]{40}", evidence["original_release_sha"]
    ) is None:
        raise RecoveryError("incident_evidence_malformed")
    for field in ("original_terminal_bytes", "readiness_receipt_bytes",
                  "original_broker_exit_code", "canary_exit_code"):
        if type(evidence[field]) is not int:
            raise RecoveryError("incident_evidence_malformed")
    if (not isinstance(evidence["canary_id"], str)
            or _readiness.CANARY_ID_RE.fullmatch(evidence["canary_id"]) is None):
        raise RecoveryError("incident_evidence_malformed")
    return evidence


def _validate_incident_grant_document(value: Any) -> dict[str, Any]:
    """Validate the immutable incident grant structure; no admission is granted."""

    grant = _require_exact_fields(
        value, _INCIDENT_GRANT_FIELDS, "recovery_grant_fields_malformed"
    )
    if grant["schema_version"] != INCIDENT_GRANT_SCHEMA:
        raise RecoveryError("recovery_grant_schema_malformed")
    if grant["authority_reference"] != INCIDENT_AUTHORITY_REFERENCE:
        raise RecoveryError("recovery_grant_authority_mismatch")
    if grant["incident_class"] != INCIDENT_RECOVERY_CLASS:
        raise RecoveryError("recovery_grant_schema_malformed")
    # Truthful historical classification is mandatory: an incident grant can
    # never manufacture ordinary cause evidence or assert a proven no-denial.
    if grant["historical_cause"] != INCIDENT_HISTORICAL_CAUSE:
        raise RecoveryError("incident_history_mislabelled")
    if grant["causal_link"] != INCIDENT_CAUSAL_LINK:
        raise RecoveryError("incident_history_mislabelled")
    if grant["raw_provider_messages_retained"] is not False:
        raise RecoveryError("incident_history_mislabelled")
    validate_incident_authorization(grant["authorization"])
    _validate_incident_evidence(grant["evidence"])
    _grant_source(grant["installed_source"])
    _executive_source(grant["executive_source"])
    _grant_worker(grant["worker"])
    _credential_lstat(grant["credential_lstat"], "recovery_grant_credential_mismatch")
    if grant["model"] != _readiness.PRODUCTION_MODEL:
        raise RecoveryError("recovery_grant_model_mismatch")
    budget = grant["budget"]
    if isinstance(budget, bool) or not isinstance(budget, int) or budget != RECOVERY_BUDGET:
        raise RecoveryError("recovery_grant_budget_invalid")
    _request_id(grant["successor_request_id"], "recovery_grant_successor_malformed")
    _request_id(grant["issuer_request_id"], "recovery_grant_successor_malformed")
    _hex_digest(grant["issuer_request_sha256"], "recovery_grant_fields_malformed")
    try:
        granted_at = _readiness._timestamp(
            grant["granted_at"], code="recovery_grant_window_invalid"
        )
        expires_at = _readiness._timestamp(
            grant["expires_at"], code="recovery_grant_window_invalid"
        )
    except _readiness.ReadinessError as exc:
        raise RecoveryError("recovery_grant_window_invalid") from exc
    if not MIN_GRANT_LIFETIME <= expires_at - granted_at <= MAX_GRANT_LIFETIME:
        raise RecoveryError("recovery_grant_window_invalid")
    return grant


def validate_incident_grant_document(
    value: Any, *, now: datetime | None = None
) -> dict[str, Any]:
    """Validate the immutable incident grant and its current live window."""

    grant = _validate_incident_grant_document(value)
    granted_at = _readiness._timestamp(grant["granted_at"], code="recovery_grant_window_invalid")
    expires_at = _readiness._timestamp(grant["expires_at"], code="recovery_grant_window_invalid")
    current = datetime.now(UTC) if now is None else now
    if granted_at > current:
        raise RecoveryError("recovery_grant_window_invalid")
    if expires_at <= current:
        raise RecoveryError("recovery_grant_expired")
    return grant


def _read_incident_grant_document(*, expected_digest: str) -> dict[str, Any]:
    _hex_digest(expected_digest, "recovery_grant_digest_malformed")
    raw = _read_custody_bytes(RECOVERY_INCIDENT_GRANT_PATH, maximum=_GRANT_MAX_BYTES)
    if hashlib.sha256(raw).hexdigest() != expected_digest:
        raise RecoveryError("recovery_grant_digest_mismatch")
    return _read_custody_document(raw, schema=INCIDENT_GRANT_SCHEMA)


def read_incident_grant(*, expected_digest: str, now: datetime | None = None) -> dict[str, Any]:
    """Read the custody-checked incident grant and enforce its live window."""

    return validate_incident_grant_document(
        _read_incident_grant_document(expected_digest=expected_digest), now=now
    )


def _read_incident_historical_grant(*, expected_digest: str) -> dict[str, Any]:
    """Read immutable incident grant evidence for reconstruction only.

    No live window admission, no issuance join and no new inference.
    """

    return _validate_incident_grant_document(
        _read_incident_grant_document(expected_digest=expected_digest)
    )


def historical_recovery_grants() -> list[tuple[str, dict[str, Any]]]:
    records = []
    for path, reader in (
        (RECOVERY_GRANT_PATH, _read_historical_grant),
        (RECOVERY_INCIDENT_GRANT_PATH, _read_incident_historical_grant),
    ):
        try:
            digest = read_grant_digest(path)
        except FileNotFoundError:
            continue
        records.append((digest, reader(expected_digest=digest)))
    return records


def read_historical_recovery_grant(*, expected_digest: str) -> dict[str, Any]:
    _hex_digest(expected_digest, "recovery_grant_digest_malformed")
    matches = [grant for digest, grant in historical_recovery_grants()
               if digest == expected_digest]
    if len(matches) != 1:
        raise RecoveryError("recovery_grant_digest_mismatch")
    return matches[0]


def validate_recovery_history(grant: Mapping[str, Any], *, grant_sha256: str) -> str:
    if grant["schema_version"] == INCIDENT_GRANT_SCHEMA:
        validate_incident_issuance_join(grant, grant_sha256=grant_sha256)
        validate_incident_designated_terminal(grant["evidence"])
        return grant["evidence"]["readiness_receipt_sha256"]
    validate_original_terminal(grant["cause_evidence"])
    return grant["cause_evidence"]["original_receipt_sha256"]


def read_grant_for_admission(
    *, expected_digest: str, now: datetime | None = None
) -> tuple[str, dict[str, Any]]:
    """Resolve the recovery grant digest to its typed document class.

    Both fixed grant files live under the same custody root.  The caller's
    digest preimage selects the class; nothing else does.  Ordinary custody
    failures stay ordinary failures and never silently fall through to the
    incident path.
    """

    _hex_digest(expected_digest, "recovery_grant_digest_malformed")
    ordinary_refusal: RecoveryError | None = None
    try:
        return "ordinary", read_grant(expected_digest=expected_digest, now=now)
    except RecoveryError as exc:
        if exc.code != "recovery_grant_digest_mismatch":
            raise
        ordinary_refusal = exc
    except FileNotFoundError:
        ordinary_refusal = None
    try:
        return "incident", read_incident_grant(
            expected_digest=expected_digest, now=now
        )
    except FileNotFoundError:
        if ordinary_refusal is not None:
            raise ordinary_refusal from None
        raise RecoveryError("recovery_grant_digest_mismatch") from None


def read_incident_commitment() -> tuple[dict[str, Any], bytes]:
    """Return the custody-checked issuance commitment and its exact bytes.

    Dispatch is strictly by the CLOSED commitment schema: v1 keeps the exact
    original law; the dormant forward protocol's v2 document is validated by
    its own closed validator.  Every other schema stays malformed.
    """

    raw = _read_custody_bytes(
        RECOVERY_INCIDENT_COMMITMENT_PATH, maximum=_GRANT_MAX_BYTES
    )
    parsed = _read_custody_json(raw)
    if parsed.get("schema_version") == COMMITMENT_V2_SCHEMA:
        # v2 documents alone resolve the optional forward module; the v1 path
        # above never imports it.  An unavailable module typed-refuses.
        try:
            forward = _forward_module()
        except ImportError as exc:
            raise RecoveryError("recovery_custody_schema_malformed") from exc
        commitment = _require_exact_fields(
            parsed, forward._COMMITMENT_V2_FIELDS,
            "recovery_grant_fields_malformed",
        )
        try:
            forward.validate_v2_commitment_structure(
                commitment, commitment_bytes=raw,
            )
        except forward.ForwardRecoveryError as exc:
            raise RecoveryError("recovery_custody_schema_malformed") from exc
        return commitment, raw
    commitment = _read_custody_document(raw, schema=INCIDENT_COMMITMENT_SCHEMA)
    _require_exact_fields(
        commitment, _INCIDENT_COMMITMENT_FIELDS, "recovery_grant_fields_malformed"
    )
    if commitment["incident_class"] != INCIDENT_RECOVERY_CLASS:
        raise RecoveryError("recovery_grant_schema_malformed")
    validate_incident_authorization(commitment["authorization"])
    _hex_digest(commitment["grant_sha256"], "recovery_grant_fields_malformed")
    _hex_digest(commitment["issuer_request_sha256"], "recovery_grant_fields_malformed")
    _request_id(commitment["issuer_request_id"], "recovery_grant_successor_malformed")
    _request_id(commitment["successor_request_id"], "recovery_grant_successor_malformed")
    _readiness._timestamp(commitment["created_at"], code="recovery_grant_window_invalid")
    return commitment, raw


def _forward_module():
    from ops.executive_os import provider_incident_forward as forward

    return forward


def read_incident_grant_with_bytes() -> tuple[dict[str, Any], bytes]:
    """Custody-checked historical incident grant together with its bytes."""

    raw = _read_custody_bytes(
        RECOVERY_INCIDENT_GRANT_PATH, maximum=_GRANT_MAX_BYTES
    )
    grant = _validate_incident_grant_document(
        _read_custody_document(raw, schema=INCIDENT_GRANT_SCHEMA)
    )
    return grant, raw


def validate_incident_issuance_join(
    grant: Mapping[str, Any], *, grant_sha256: str
) -> dict[str, Any]:
    """Join one incident grant to its complete actual issuance terminal.

    Live law: a dormant forward policy refuses, so live admission can never
    consume a v2 join.  Read-only historical inspection of already-consumed
    evidence uses :func:`_validate_incident_issuance_join_historical`, which
    is private and not caller-selectable from any admission path.
    """
    return _incident_issuance_join(grant, grant_sha256=grant_sha256, historical=False)


def _validate_incident_issuance_join_historical(
    grant: Mapping[str, Any], *, grant_sha256: str
) -> dict[str, Any]:
    """Private historical verifier for already-consumed incident evidence.

    Identical to the live join except that the live forward-policy activation
    predicate is skipped, so a consumed allocation stays readable after the
    amendment is deactivated.  Everything else — custody, commitment, grant,
    reservation, terminal, guard and identity joins — runs unchanged, and no
    admission path selects this verifier.
    """
    return _incident_issuance_join(grant, grant_sha256=grant_sha256, historical=True)


def _incident_issuance_join(
    grant: Mapping[str, Any], *, grant_sha256: str, historical: bool
) -> dict[str, Any]:
    """Shared join body; ``historical`` skips only the live policy predicate."""

    from control_plane import executive_privileged_broker as broker

    try:
        issuer_request_id = _request_id(
            grant["issuer_request_id"], "recovery_grant_successor_malformed"
        )
        commitment, commitment_raw = read_incident_commitment()
        if commitment.get("schema_version") == COMMITMENT_V2_SCHEMA:
            return _validate_v2_issuance_join(
                grant, grant_sha256=grant_sha256,
                commitment=commitment, commitment_raw=commitment_raw,
                historical=historical,
            )
        if commitment["authorization"] != grant["authorization"]:
            raise RecoveryError("incident_commitment_mismatch")
        if commitment["grant_sha256"] != grant_sha256:
            raise RecoveryError("incident_commitment_mismatch")
        if commitment["successor_request_id"] != grant["successor_request_id"]:
            raise RecoveryError("incident_commitment_mismatch")
        if commitment["issuer_request_id"] != issuer_request_id:
            raise RecoveryError("incident_commitment_mismatch")
        if commitment["issuer_request_sha256"] != grant["issuer_request_sha256"]:
            raise RecoveryError("incident_commitment_mismatch")
        receipt_root = broker._RECEIPT_ROOT
        for directory in (receipt_root.parent.parent, receipt_root.parent,
                          receipt_root, receipt_root / "inflight",
                          receipt_root / "reconciled"):
            broker._assert_root_owned_nonwritable(directory, directory=True)
            _readiness._assert_no_macos_acl(directory)
        for directory in ("inflight", "reconciled"):
            other = receipt_root / directory / (issuer_request_id + ".json")
            try:
                other.lstat()
            except FileNotFoundError:
                continue
            raise RecoveryError("incident_issuance_unsettled")
        terminal_path = receipt_root / (issuer_request_id + ".json")
        raw, info = broker._read_stable_bounded_bytes(terminal_path)
        if (info.st_uid != CUSTODY_UID or info.st_gid != CUSTODY_GID
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
            raise RecoveryError("recovery_original_request_custody_unsafe")
        _readiness._assert_no_macos_acl(terminal_path)
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
        result = broker.validate_terminal_receipt(
            value,
            expected_request_id=issuer_request_id,
            expected_request_sha256=grant["issuer_request_sha256"],
            expected_release_sha=grant["executive_source"]["release_sha"],
            expected_action=INCIDENT_ISSUER_ACTION,
        )
        if result["outcome"] != "SUCCEEDED" or result["exit_code"] != 0:
            raise RecoveryError("incident_issuance_not_successful")
        if (result["stdout_sha256"] != hashlib.sha256(commitment_raw).hexdigest()
                or result["stdout_bytes"] != len(commitment_raw)):
            raise RecoveryError("incident_commitment_digest_mismatch")
    except (OSError, ValueError, broker.BrokerTrustError) as exc:
        raise RecoveryError("incident_issuance_unverified") from exc
    return {"terminal": result, "commitment_sha256": hashlib.sha256(commitment_raw).hexdigest()}


def _validate_v2_issuance_join(
    grant: Mapping[str, Any],
    *,
    grant_sha256: str,
    commitment: Mapping[str, Any],
    commitment_raw: bytes,
    historical: bool = False,
) -> dict[str, Any]:
    """Closed v2 forward-protocol issuance join; v1 law is untouched.

    Requires the exact live forward policy amendment, the complete permanent
    reservation, the still-present unchanged original marker with no original
    terminal or reconciliation, the exclusive SUCCEEDED forward terminal whose
    stdout binds the exact v2 commitment bytes, and an ABSENT forward guard.
    Returns the same existing join result shape as v1.  ``historical`` skips
    only the live-policy predicate for read-only inspection of already
    consumed evidence; it is never selectable from live admission.
    """
    from control_plane import executive_privileged_broker as broker

    from types import SimpleNamespace
    try:
        forward = _forward_module()
    except ImportError as exc:
        raise RecoveryError("recovery_custody_schema_malformed") from exc
    try:
        if not historical:
            policy = forward.PRODUCTION_FORWARD_RECOVERY_POLICY
            if policy is None:
                raise RecoveryError("forward_policy_dormant")
            if commitment["forward_recovery"]["amendment_authorization"] != (
                policy.amendment_authorization()
            ):
                raise RecoveryError("forward_policy_binding_mismatch")
        forward.validate_v2_commitment_document(
            commitment, commitment_bytes=commitment_raw,
            grant=grant, grant_sha256=grant_sha256,
        )
        env = SimpleNamespace(
            receipt_root=broker._RECEIPT_ROOT,
            require_root=False,
            custody_uid=CUSTODY_UID,
            custody_gid=CUSTODY_GID,
        )
        join = forward.validate_complete_forward_join(
            env, grant=grant, grant_sha256=grant_sha256,
            commitment=commitment, commitment_bytes=commitment_raw,
        )
    except RecoveryError:
        raise
    except (forward.ForwardRecoveryError, broker.BrokerTrustError, OSError,
            ValueError) as exc:
        raise RecoveryError("incident_issuance_unverified") from exc
    return {
        "terminal": join["terminal"],
        "commitment_sha256": join["commitment_sha256"],
    }


def admit_recovery_context(
    grant: Mapping[str, Any],
    *,
    grant_sha256: str,
    qualification: ProducerQualification | None = None,
) -> dict[str, Any]:
    """Typed common admission for both recovery grant classes.

    Ordinary grants still go through :func:`evaluate_cause` and the empty
    production producer table.  Incident grants go through the exact incident
    validator plus the complete issuer terminal join.  No fake ordinary
    document is manufactured for an incident and no producer qualification is
    required for it: its authorization is the authority-owned policy binding,
    not derived cause.
    """

    schema = grant.get("schema_version") if isinstance(grant, Mapping) else None
    if schema == RECOVERY_GRANT_SCHEMA:
        kwargs = {} if qualification is None else {"qualification": qualification}
        cause = evaluate_cause(grant["cause_evidence"], **kwargs)
        return {
            "admission_class": "ordinary",
            "cause": cause,
            "original_receipt_sha256": cause["original_receipt_sha256"],
        }
    if schema == INCIDENT_GRANT_SCHEMA:
        _validate_incident_grant_document(grant)
        require_current_incident_policy(grant)
        validate_incident_designated_terminal(grant["evidence"])
        validate_incident_issuance_join(grant, grant_sha256=grant_sha256)
        return {
            "admission_class": "incident",
            "cause": None,
            "original_receipt_sha256":
                grant["evidence"]["readiness_receipt_sha256"],
        }
    raise RecoveryError("recovery_grant_schema_malformed")


def write_custody_document(path: Path, payload: bytes) -> str:
    """Create one immutable custody document exclusively, root-owned, fsync'd.

    Mode 0400, one link, no ACL, create-only: a partial issuance can never be
    replaced by a retry.  Returns the digest of the written bytes.
    """

    _validate_state_directory(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o400)
    except FileExistsError:
        raise
    except OSError as exc:
        raise RecoveryError("recovery_allocation_unwritable") from exc
    try:
        os.fchown(descriptor, CUSTODY_UID, CUSTODY_GID)
        os.fchmod(descriptor, 0o400)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise RecoveryError("recovery_allocation_short_write")
            view = view[written:]
        os.fsync(descriptor)
    except OSError as exc:
        raise RecoveryError("recovery_allocation_unwritable") from exc
    finally:
        os.close(descriptor)
    _readiness._fsync_directory(path.parent)
    return hashlib.sha256(payload).hexdigest()


def _validate_incident_allocation_document(value: Any) -> dict[str, Any]:
    record = _require_exact_fields(
        value, _INCIDENT_ALLOCATION_FIELDS, "recovery_allocation_fields_malformed"
    )
    if record["allocation_class"] != INCIDENT_RECOVERY_CLASS:
        raise RecoveryError("recovery_allocation_fields_malformed")
    if record["authority_reference"] != INCIDENT_AUTHORITY_REFERENCE:
        raise RecoveryError("recovery_allocation_fields_malformed")
    for field in ("predecessor_receipt_sha256", "predecessor_request_sha256",
                  "grant_sha256", "commitment_sha256"):
        _hex_digest(record[field], "recovery_allocation_fields_malformed")
    for field in ("predecessor_request_id", "successor_request_id",
                  "issuer_request_id"):
        _request_id(record[field], "recovery_allocation_fields_malformed")
    _hex_digest(record["issuer_request_sha256"], "recovery_allocation_fields_malformed")
    if (record["worker_uid"], record["worker_gid"]) != (
        _readiness.WORKER_UID,
        _readiness.WORKER_GID,
    ) or record["provider_home"] != os.fspath(_readiness.AUTH_PATH.parent):
        raise RecoveryError("recovery_allocation_fields_malformed")
    if (record["codex_version"], record["codex_sha256"]) != (
        _readiness.CODEX_VERSION,
        _readiness.CODEX_SHA256,
    ):
        raise RecoveryError("recovery_allocation_fields_malformed")
    _credential_lstat(record["credential_lstat"], "recovery_allocation_fields_malformed")
    _executive_source(record["executive_source"])
    if (type(record["budget"]) is not int or record["budget"] != RECOVERY_BUDGET
            or record["consumed"] is not True):
        raise RecoveryError("recovery_allocation_not_consumed")
    _readiness._timestamp(record["claimed_at"], code="recovery_allocation_fields_malformed")
    grant = _read_incident_historical_grant(expected_digest=record["grant_sha256"])
    join = _validate_incident_issuance_join_historical(
        grant, grant_sha256=record["grant_sha256"]
    )
    expected = {
        "policy_id": grant["authorization"]["policy_id"],
        "issuer_request_id": grant["issuer_request_id"],
        "issuer_request_sha256": grant["issuer_request_sha256"],
        "commitment_sha256": join["commitment_sha256"],
        "successor_request_id": grant["successor_request_id"],
        "predecessor_request_id": grant["evidence"]["original_request_id"],
        "predecessor_request_sha256": grant["evidence"]["original_request_sha256"],
        "predecessor_receipt_sha256": grant["evidence"]["readiness_receipt_sha256"],
        "executive_source": grant["executive_source"],
        "credential_lstat": grant["credential_lstat"],
    }
    if any(record[key] != value for key, value in expected.items()):
        raise RecoveryError("recovery_allocation_scope_conflict")
    return record


def _claim_incident_allocation(
    path: Path,
    *,
    grant: Mapping[str, Any],
    grant_sha256: str,
    predecessor_receipt_sha256: str,
) -> dict[str, Any]:
    """Consume the single allocation with the truthful incident schema.

    Same fixed O_EXCL path, same one-use semantics, same no-refund rule as
    :func:`claim_allocation`; only the record schema and its truthful fields
    differ.
    """

    _hex_digest(predecessor_receipt_sha256, "recovery_predecessor_digest_malformed")
    _validate_state_directory(path)
    # Existing custody is classified historically by the caller, including
    # after policy deactivation.  An absent slot still requires the live join:
    # earlier admission is not authority to create a new allocation now.
    try:
        path.lstat()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise RecoveryError("recovery_allocation_unreadable") from exc
    else:
        raise FileExistsError(path)
    join = validate_incident_issuance_join(grant, grant_sha256=grant_sha256)
    evidence = grant["evidence"]
    if predecessor_receipt_sha256 != evidence["readiness_receipt_sha256"]:
        raise RecoveryError("recovery_allocation_scope_conflict")
    record = {
        "schema_version": INCIDENT_ALLOCATION_SCHEMA,
        "allocation_class": INCIDENT_RECOVERY_CLASS,
        "authority_reference": INCIDENT_AUTHORITY_REFERENCE,
        "predecessor_receipt_sha256": predecessor_receipt_sha256,
        "predecessor_request_id": evidence["original_request_id"],
        "predecessor_request_sha256": evidence["original_request_sha256"],
        "grant_sha256": grant_sha256,
        "executive_source": dict(grant["executive_source"]),
        "successor_request_id": grant["successor_request_id"],
        "policy_id": grant["authorization"]["policy_id"],
        "issuer_request_id": grant["issuer_request_id"],
        "issuer_request_sha256": grant["issuer_request_sha256"],
        "commitment_sha256": join["commitment_sha256"],
        "worker_uid": _readiness.WORKER_UID,
        "worker_gid": _readiness.WORKER_GID,
        "provider_home": os.fspath(_readiness.AUTH_PATH.parent),
        "codex_version": _readiness.CODEX_VERSION,
        "codex_sha256": _readiness.CODEX_SHA256,
        "credential_lstat": dict(grant["credential_lstat"]),
        "budget": RECOVERY_BUDGET,
        "consumed": True,
        "claimed_at": _readiness.now_iso(),
    }
    payload = (
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    write_custody_document(path, payload)
    return record



def claim_allocation(
    path: Path,
    *,
    grant: Mapping[str, Any],
    grant_sha256: str,
    predecessor_receipt_sha256: str,
) -> dict[str, Any]:
    """Durably consume the single allocation, or refuse without any effect.

    The record is keyed by the ORIGINAL predecessor receipt digest and scope,
    never by the successor request or grant id alone.  Creation is exclusive
    and fsync'd; a concurrent claim, a different predecessor, or a regrant all
    refuse.  There is deliberately no refund, delete or rewrite path.
    """

    _hex_digest(predecessor_receipt_sha256, "recovery_predecessor_digest_malformed")
    _validate_state_directory(path)
    cause = grant["cause_evidence"]
    record = {
        "schema_version": RECOVERY_ALLOCATION_SCHEMA,
        "allocation_class": "current_pin_recovery",
        "authority_reference": RECOVERY_AUTHORITY_REFERENCE,
        "predecessor_receipt_sha256": predecessor_receipt_sha256,
        "predecessor_request_id": cause["original_request_id"],
        "predecessor_request_sha256": cause["original_request_sha256"],
        "grant_sha256": grant_sha256,
        "executive_source": dict(grant["executive_source"]),
        "successor_request_id": grant["successor_request_id"],
        "worker_uid": _readiness.WORKER_UID,
        "worker_gid": _readiness.WORKER_GID,
        "provider_home": os.fspath(_readiness.AUTH_PATH.parent),
        "codex_version": _readiness.CODEX_VERSION,
        "codex_sha256": _readiness.CODEX_SHA256,
        "credential_lstat": dict(grant["credential_lstat"]),
        "budget": RECOVERY_BUDGET,
        "consumed": True,
        "claimed_at": _readiness.now_iso(),
    }
    payload = (
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o400)
    except FileExistsError:
        raise
    except OSError as exc:
        raise RecoveryError("recovery_allocation_unwritable") from exc
    try:
        os.fchown(descriptor, CUSTODY_UID, CUSTODY_GID)
        os.fchmod(descriptor, 0o400)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise RecoveryError("recovery_allocation_short_write")
            view = view[written:]
        os.fsync(descriptor)
    except OSError as exc:
        raise RecoveryError("recovery_allocation_unwritable") from exc
    finally:
        os.close(descriptor)
    _readiness._fsync_directory(path.parent)
    return record


def claim_or_refuse_allocation(
    path: Path,
    *,
    grant: Mapping[str, Any],
    grant_sha256: str,
    predecessor_receipt_sha256: str,
) -> dict[str, Any]:
    """Claim the allocation, or classify an existing record as a refusal.

    A record bound to a different predecessor is a scope conflict: a new key
    can never create a second allocation.  A record bound to the same
    predecessor is an already-consumed budget, so a regrant refuses too.
    """

    incident = (
        isinstance(grant, Mapping)
        and grant.get("schema_version") == INCIDENT_GRANT_SCHEMA
    )
    try:
        if incident:
            return _claim_incident_allocation(
                path,
                grant=grant,
                grant_sha256=grant_sha256,
                predecessor_receipt_sha256=predecessor_receipt_sha256,
            )
        return claim_allocation(
            path,
            grant=grant,
            grant_sha256=grant_sha256,
            predecessor_receipt_sha256=predecessor_receipt_sha256,
        )
    except FileExistsError:
        existing = read_allocation(path)
        if existing is None:
            raise RecoveryError("recovery_allocation_unreadable") from None
        if existing["allocation_class"] != (
            INCIDENT_RECOVERY_CLASS if incident else "current_pin_recovery"
        ):
            raise RecoveryError("recovery_allocation_scope_conflict") from None
        if existing["predecessor_receipt_sha256"] != predecessor_receipt_sha256:
            raise RecoveryError("recovery_allocation_scope_conflict") from None
        if existing["grant_sha256"] != grant_sha256:
            raise RecoveryError("recovery_allocation_scope_conflict") from None
        raise RecoveryError("recovery_allocation_already_claimed") from None


def validate_observation_document(
    value: Any,
    *,
    successor_request_id: str,
    expected_kind: str,
    workspace_binding_class: str,
    auth_identity: Mapping[str, Any],
    binary_identity: Mapping[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate one internal, transaction-bound recovery observation.

    The document is a prerequisite observation only.  It is never a readiness
    receipt, never reusable across requests, and it must match the live
    source, credential and designated request at reservation time.
    """

    observation = _require_exact_fields(
        value, _OBSERVATION_FIELDS, "recovery_observation_fields_malformed"
    )
    if observation["schema_version"] != OBSERVATION_SCHEMA:
        raise RecoveryError("recovery_observation_schema_malformed")
    if observation["observation_only"] is not True or observation["readiness_issued"] is not False:
        raise RecoveryError("recovery_observation_schema_malformed")
    if observation["observation_status"] != "observed" or observation["refusal"] is not None:
        raise RecoveryError("recovery_observation_refused")
    if observation["successor_request_id"] != successor_request_id:
        raise RecoveryError("recovery_observation_request_mismatch")
    if observation["workspace_binding_class"] != workspace_binding_class:
        raise RecoveryError("recovery_observation_source_mismatch")
    if observation["expected_credential_kind"] != expected_kind:
        raise RecoveryError("recovery_observation_source_mismatch")
    if observation["slot_id"] != "codex-01":
        raise RecoveryError("recovery_observation_source_mismatch")
    if observation["codex_binary"] != dict(binary_identity):
        raise RecoveryError("recovery_observation_source_mismatch")
    if _executive_source(observation["executive_source"]) != current_executive_source():
        raise RecoveryError("recovery_executive_source_mismatch")
    if observation["credential_lstat"] != dict(auth_identity):
        raise RecoveryError("recovery_observation_credential_mismatch")
    if observation["configured_model"] != _readiness.PRODUCTION_MODEL:
        raise RecoveryError("recovery_model_mismatch")
    if observation["ordinary_usage_allowed"] is not True:
        raise RecoveryError("recovery_ordinary_usage_not_permitted")
    catalog = observation["model_catalog"]
    if not isinstance(catalog, Mapping) or frozenset(catalog) != _OBSERVATION_CATALOG_FIELDS:
        raise RecoveryError("recovery_observation_fields_malformed")
    if catalog.get("listed_in_returned_page") is not True or catalog.get("complete") is not True:
        raise RecoveryError("recovery_model_catalog_incomplete")
    try:
        observed = _readiness._timestamp(
            observation["observed_at"], code="recovery_observation_schema_malformed"
        )
    except _readiness.ReadinessError as exc:
        raise RecoveryError("recovery_observation_schema_malformed") from exc
    current = datetime.now(UTC) if now is None else now
    if abs(current - observed) > _readiness.MAX_CLOCK_SKEW:
        raise RecoveryError("recovery_observation_stale")
    return dict(observation)


def validate_current_pin_recovery_predecessor_document(
    document: Any,
    *,
    grant: Mapping[str, Any],
    auth_identity: Mapping[str, Any],
    binary_identity: Mapping[str, Any],
    expected_kind: str,
    workspace_binding_class: str,
    worker_uid: int = _readiness.WORKER_UID,
    worker_gid: int = _readiness.WORKER_GID,
) -> None:
    """Verify the retained adverse predecessor against its own grant.

    Closed terminal effect only: integer exit 1, no timeout, signal,
    cancellation, unknown effect or reservation, on the same installed source,
    credential metadata, model and workspace the grant pinned.  Ordinary cause
    is deliberately NOT re-derived here; the grant already carries the reviewed
    cause evidence and production cannot qualify any producer anyway.
    """

    if grant.get("schema_version") == INCIDENT_GRANT_SCHEMA:
        validate_incident_designated_readiness(
            document, grant["evidence"], auth_identity=auth_identity,
            binary_identity=binary_identity, worker_uid=worker_uid, worker_gid=worker_gid,
        )
        refuse_evidenced_incident_denial(document)
    cause = grant.get("cause_evidence")
    if (expected_kind != "device-auth"
            or workspace_binding_class != _readiness.COMPANY_WORKSPACE_BINDING_CLASS
            or (worker_uid, worker_gid) != (_readiness.WORKER_UID, _readiness.WORKER_GID)):
        raise RecoveryError("recovery_predecessor_kind_mismatch")
    if (not isinstance(document, Mapping)
            or frozenset(document) != _readiness._RECEIPT_FIELDS
            or document.get("schema_version") != _readiness.SCHEMA_VERSION
            or document.get("passed") is not False
            or document.get("refusal") != RECOVERY_REFUSAL
            or document.get("expected_credential_kind") != expected_kind
            or document.get("workspace_binding_class") != workspace_binding_class
            or document.get("forced_chatgpt_workspace_id_applied") is not False):
        raise RecoveryError("recovery_predecessor_not_terminal_adverse")
    _readiness._deadline_fields(
        observed_at=document.get("observed_at"),
        credential_expires_at=document.get("credential_expires_at"),
        readiness_expires_at=document.get("readiness_expires_at"),
        allow_expired_readiness=True,
    )
    _readiness._assert_worker_identity(
        auth_identity, worker_uid=worker_uid, worker_gid=worker_gid
    )
    if dict(document.get("credential_lstat") or {}) != dict(auth_identity):
        raise RecoveryError("recovery_predecessor_credential_mismatch")
    if dict(document.get("credential_lstat") or {}) != dict(grant["credential_lstat"]):
        raise RecoveryError("recovery_predecessor_credential_mismatch")
    if dict(document.get("codex_binary") or {}) != dict(binary_identity):
        raise RecoveryError("recovery_predecessor_source_mismatch")
    predecessor_source = {
        field: document.get("codex_binary", {}).get(field)
        for field in sorted(_GRANT_SOURCE_FIELDS)
    }
    if predecessor_source != dict(grant["installed_source"]):
        raise RecoveryError("recovery_predecessor_source_mismatch")
    identity, canary = document.get("provider_identity"), document.get("inference_canary")
    if not isinstance(identity, Mapping) or not isinstance(canary, Mapping):
        raise RecoveryError("recovery_predecessor_not_terminal_adverse")
    safe_identity = _readiness._safe_identity(identity)
    safe_canary = _readiness._safe_canary(canary, binary_identity=binary_identity)
    if (safe_identity["refusal"] is not None
            or safe_identity["codex_binary"] != dict(binary_identity)
            or safe_identity["credential_lstat"] != dict(auth_identity)
            or safe_identity["expected_credential_kind"] != expected_kind
            or safe_identity["workspace_binding_class"] != workspace_binding_class):
        raise RecoveryError("recovery_predecessor_identity_mismatch")
    effect_not_closed = (safe_canary["passed"] is not False
            or type(safe_canary["exit_code"]) is not int
            or safe_canary["exit_code"] != RECOVERY_REFUSAL_EXIT_CODE
            or safe_canary["timed_out"] is not False
            or safe_canary["terminal_event_class"] != RECOVERY_TERMINAL_EVENT_CLASS
            or safe_canary["result_valid"] is not False
            or safe_canary["refusal"] != RECOVERY_REFUSAL
            or safe_canary["model"] != _readiness.PRODUCTION_MODEL)
    if cause is not None and safe_canary["exit_code"] != cause["original_canary_exit_code"]:
        effect_not_closed = True
    if effect_not_closed:
        raise RecoveryError("recovery_predecessor_effect_not_closed")
    def _predecessor_time(value: Any) -> Any:
        try:
            return _readiness._timestamp(
                value, code="recovery_predecessor_timestamp_malformed"
            )
        except _readiness.ReadinessError as exc:
            raise RecoveryError("recovery_predecessor_timestamp_malformed") from exc

    observed = _predecessor_time(document["observed_at"])
    for component in (safe_identity, safe_canary):
        if abs(_predecessor_time(component["observed_at"]) - observed) > _readiness.MAX_CLOCK_SKEW:
            raise RecoveryError("recovery_predecessor_timestamp_conflict")
    if cause is not None and abs(
        observed - _predecessor_time(cause["observed_at"])
    ) > _readiness.MAX_CLOCK_SKEW:
        raise RecoveryError("recovery_predecessor_timestamp_conflict")


__all__ = [
    "CUSTODY_GID",
    "CUSTODY_UID",
    "MAX_GRANT_LIFETIME",
    "MIN_GRANT_LIFETIME",
    "OBSERVATION_SCHEMA",
    "PRODUCER_QUALIFICATION",
    "RECOVERY_ALLOCATION_PATH",
    "RECOVERY_ALLOCATION_SCHEMA",
    "RECOVERY_AUTHORITY_REFERENCE",
    "RECOVERY_BUDGET",
    "RECOVERY_EVIDENCE_SCHEMA",
    "RECOVERY_GRANT_PATH",
    "RECOVERY_GRANT_SCHEMA",
    "RECOVERY_STATE_ROOT",
    "INCIDENT_DESIGNATED_EVIDENCE",
    "INCIDENT_GRANT_SCHEMA",
    "INCIDENT_ISSUER_ACTION",
    "IncidentPolicy",
    "PRODUCTION_INCIDENT_POLICY",
    "ProducerQualification",
    "RECOVERY_INCIDENT_COMMITMENT_PATH",
    "RECOVERY_INCIDENT_GRANT_PATH",
    "RecoveryError",
    "admit_recovery_context",
    "claim_or_refuse_allocation",
    "evaluate_cause",
    "read_allocation",
    "read_grant",
    "read_grant_digest",
    "read_grant_for_admission",
    "read_incident_grant",
    "refuse_evidenced_incident_denial",
    "validate_incident_policy",
    "write_custody_document",
    "validate_cause_document",
    "validate_current_pin_recovery_predecessor_document",
    "validate_grant_document",
    "validate_observation_document",
]
