"""Deterministic Capacity-C2 placement-commitment contract.

This module is pure.  It validates one protected Capacity-C1 selection,
derives the one root-bound commitment command, and builds/validates the
closed Event payload that the existing Executive Runtime transaction owns.
It performs no I/O and owns no Job, Attempt, Worker, quota, lease, Event,
RuntimeBinding, provider session, queue, retry plane, or persistence.
"""
from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from control_plane.executive_orchestration_principal import (
    OrchestrationPrincipalError,
    digest,
    validate_placement_snapshot,
)
from control_plane.executive_placement_selection import validate_placement_selection


COMMITMENT_SCHEMA = "mastermind.capacity_placement_commitment/v1"
COMMAND_SCHEMA = "mastermind.capacity_placement_commitment_command/v1"
EVENT_TYPE = "CAPACITY_PLACEMENT_COMMITTED"

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMAND_ID_RE = re.compile(r"^CAP-C2-[0-9a-f]{32}$")

_PLAN_KEYS = frozenset(
    {
        "schema_version",
        "root_job_id",
        "expected_job_revision",
        "responsibility_ref",
        "selection_document_digest",
        "selection_evidence_digest",
        "selected_worker_id",
        "selected_quota_class",
        "committed_placement_snapshot_digest",
        "commitment_command_id",
        "command_fingerprint",
    }
)
_EVENT_KEYS = frozenset(
    {
        "schema_version",
        "root_job_id",
        "expected_job_revision",
        "responsibility_ref",
        "responsibility_job_created_command_id",
        "responsibility_authority_fingerprint",
        "selection_document_digest",
        "selection_evidence_digest",
        "selected_worker_id",
        "selected_quota_class",
        "committed_attempt_id",
        "committed_placement_snapshot_digest",
        "commitment_command_id",
        "command_fingerprint",
        "commitment_evidence_digest",
    }
)
FORBIDDEN_EVENT_KEYS = frozenset(
    {
        "runtime_binding_id",
        "runtime_binding_generation",
        "provider_session_id",
        "native_handle",
        "account_label",
        "provider",
        "model",
        "actor",
        "actor_binding",
        "slack_principal",
    }
)


class PlacementCommitmentError(ValueError):
    """A fixed, secret-safe C2 command or receipt refusal."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _token(value: Any, *, code: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise PlacementCommitmentError(code)
    return value


def _digest_token(value: Any, *, code: str) -> str:
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        raise PlacementCommitmentError(code)
    return value


def _canonical_selection(value: Any) -> dict[str, Any]:
    try:
        selection = validate_placement_selection(value)
    except (TypeError, ValueError, OrchestrationPrincipalError) as exc:
        raise PlacementCommitmentError("PLACEMENT_SELECTION_INVALID") from exc
    if selection.get("state") != "selected":
        raise PlacementCommitmentError("PLACEMENT_SELECTION_NOT_SELECTED")
    if selection.get("selection_is_commitment") is not False:
        raise PlacementCommitmentError("PLACEMENT_SELECTION_ALREADY_COMMITTED")
    selected = selection.get("selected")
    try:
        validate_placement_snapshot(selected)
    except (TypeError, ValueError, OrchestrationPrincipalError) as exc:
        raise PlacementCommitmentError("PLACEMENT_SNAPSHOT_INVALID") from exc
    return selection


@dataclasses.dataclass(frozen=True, slots=True)
class PlacementCommitmentPlan:
    """Immutable C2 facts passed to the existing Runtime mutation owner.

    ``expected_job_revision`` is an optimistic-concurrency precondition, not
    part of the stable command identity.  The exact selected snapshot is held
    as a private in-memory value for the future claim transaction; command and
    Event wires expose only its canonical digest.
    """

    root_job_id: str
    expected_job_revision: int
    responsibility_ref: str
    selection_document_digest: str
    selection_evidence_digest: str
    selected_worker_id: str
    selected_quota_class: str
    committed_placement_snapshot: Mapping[str, Any] = dataclasses.field(
        repr=False,
        compare=False,
        hash=False,
    )
    committed_placement_snapshot_digest: str
    commitment_command_id: str
    command_fingerprint: str
    schema_version: str = COMMAND_SCHEMA

    def __post_init__(self) -> None:
        _token(self.root_job_id, code="ROOT_JOB_ID_INVALID")
        if type(self.expected_job_revision) is not int or self.expected_job_revision < 0:
            raise PlacementCommitmentError("EXPECTED_JOB_REVISION_INVALID")
        _token(self.responsibility_ref, code="RESPONSIBILITY_REF_INVALID")
        _digest_token(
            self.selection_document_digest,
            code="SELECTION_DOCUMENT_DIGEST_INVALID",
        )
        _digest_token(
            self.selection_evidence_digest,
            code="SELECTION_EVIDENCE_DIGEST_INVALID",
        )
        _token(self.selected_worker_id, code="SELECTED_WORKER_ID_INVALID")
        _token(self.selected_quota_class, code="SELECTED_QUOTA_CLASS_INVALID")
        try:
            snapshot = validate_placement_snapshot(
                self.committed_placement_snapshot
            )
        except (TypeError, ValueError, OrchestrationPrincipalError) as exc:
            raise PlacementCommitmentError("PLACEMENT_SNAPSHOT_INVALID") from exc
        _digest_token(
            self.committed_placement_snapshot_digest,
            code="PLACEMENT_SNAPSHOT_DIGEST_INVALID",
        )
        if (
            snapshot["worker_id"] != self.selected_worker_id
            or snapshot["quota_class"] != self.selected_quota_class
            or digest(snapshot) != self.committed_placement_snapshot_digest
        ):
            raise PlacementCommitmentError("PLACEMENT_SNAPSHOT_MISMATCH")
        object.__setattr__(
            self,
            "committed_placement_snapshot",
            MappingProxyType(snapshot),
        )
        if _COMMAND_ID_RE.fullmatch(self.commitment_command_id) is None:
            raise PlacementCommitmentError("COMMITMENT_COMMAND_ID_INVALID")
        _digest_token(self.command_fingerprint, code="COMMAND_FINGERPRINT_INVALID")
        if self.schema_version != COMMAND_SCHEMA:
            raise PlacementCommitmentError("COMMITMENT_COMMAND_SCHEMA_INVALID")
        semantics = self.command_semantics()
        expected_fingerprint = digest(semantics)
        if self.command_fingerprint != expected_fingerprint:
            raise PlacementCommitmentError("COMMAND_FINGERPRINT_MISMATCH")
        if self.commitment_command_id != f"CAP-C2-{expected_fingerprint[:32]}":
            raise PlacementCommitmentError("COMMITMENT_COMMAND_ID_MISMATCH")

    def command_semantics(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "root_job_id": self.root_job_id,
            "responsibility_ref": self.responsibility_ref,
            "selection_document_digest": self.selection_document_digest,
            "selection_evidence_digest": self.selection_evidence_digest,
            "selected_worker_id": self.selected_worker_id,
            "selected_quota_class": self.selected_quota_class,
            "committed_placement_snapshot_digest": (
                self.committed_placement_snapshot_digest
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        value = dict(self.command_semantics())
        value["expected_job_revision"] = self.expected_job_revision
        value["commitment_command_id"] = self.commitment_command_id
        value["command_fingerprint"] = self.command_fingerprint
        if set(value) != _PLAN_KEYS:
            raise PlacementCommitmentError("COMMITMENT_PLAN_SHAPE_INVALID")
        return value


def build_commitment_plan(
    *,
    root_job_id: str,
    expected_job_revision: int,
    placement_selection: Any,
) -> PlacementCommitmentPlan:
    """Validate one C1 wire and derive stable root-plus-selection identity."""

    root = _token(root_job_id, code="ROOT_JOB_ID_INVALID")
    if type(expected_job_revision) is not int or expected_job_revision < 0:
        raise PlacementCommitmentError("EXPECTED_JOB_REVISION_INVALID")
    selection = _canonical_selection(placement_selection)
    selected = validate_placement_snapshot(selection["selected"])
    responsibility_ref = _token(
        selection["responsibility_ref"], code="RESPONSIBILITY_REF_INVALID"
    )
    semantics = {
        "schema_version": COMMAND_SCHEMA,
        "root_job_id": root,
        "responsibility_ref": responsibility_ref,
        "selection_document_digest": digest(selection),
        "selection_evidence_digest": digest(selection["evidence"]),
        "selected_worker_id": selected["worker_id"],
        "selected_quota_class": selected["quota_class"],
        "committed_placement_snapshot_digest": digest(selected),
    }
    fingerprint = digest(semantics)
    return PlacementCommitmentPlan(
        root_job_id=root,
        expected_job_revision=expected_job_revision,
        responsibility_ref=responsibility_ref,
        selection_document_digest=semantics["selection_document_digest"],
        selection_evidence_digest=semantics["selection_evidence_digest"],
        selected_worker_id=semantics["selected_worker_id"],
        selected_quota_class=semantics["selected_quota_class"],
        committed_placement_snapshot=selected,
        committed_placement_snapshot_digest=semantics[
            "committed_placement_snapshot_digest"
        ],
        commitment_command_id=f"CAP-C2-{fingerprint[:32]}",
        command_fingerprint=fingerprint,
    )


def build_commitment_event_payload(
    *,
    plan: PlacementCommitmentPlan,
    committed_attempt_id: str,
    responsibility_job_created_command_id: str,
    responsibility_authority_fingerprint: str,
) -> dict[str, Any]:
    """Build the closed Event payload after the Runtime claim has succeeded.

    The Event retains the accepted pre-claim Job revision so a changed-revision
    call reaches the stable command but conflicts with the immutable receipt.
    """

    attempt_id = _token(committed_attempt_id, code="COMMITTED_ATTEMPT_ID_INVALID")
    created_command_id = _token(
        responsibility_job_created_command_id,
        code="RESPONSIBILITY_CREATED_COMMAND_ID_INVALID",
    )
    authority_fingerprint = _digest_token(
        responsibility_authority_fingerprint,
        code="RESPONSIBILITY_AUTHORITY_FINGERPRINT_INVALID",
    )
    evidence = {
        "root_job_id": plan.root_job_id,
        "expected_job_revision": plan.expected_job_revision,
        "responsibility_ref": plan.responsibility_ref,
        "responsibility_job_created_command_id": created_command_id,
        "responsibility_authority_fingerprint": authority_fingerprint,
        "selection_document_digest": plan.selection_document_digest,
        "selection_evidence_digest": plan.selection_evidence_digest,
        "selected_worker_id": plan.selected_worker_id,
        "selected_quota_class": plan.selected_quota_class,
        "committed_attempt_id": attempt_id,
        "committed_placement_snapshot_digest": (
            plan.committed_placement_snapshot_digest
        ),
        "commitment_command_id": plan.commitment_command_id,
        "command_fingerprint": plan.command_fingerprint,
    }
    payload = {
        "schema_version": COMMITMENT_SCHEMA,
        **evidence,
        "commitment_evidence_digest": digest(evidence),
    }
    if set(payload) != _EVENT_KEYS or set(payload) & FORBIDDEN_EVENT_KEYS:
        raise PlacementCommitmentError("COMMITMENT_EVENT_SHAPE_INVALID")
    return payload


def validate_commitment_event_payload(
    value: Any,
    *,
    plan: PlacementCommitmentPlan,
    expected_attempt_id: str,
    expected_responsibility_job_created_command_id: str,
    expected_responsibility_authority_fingerprint: str,
) -> dict[str, Any]:
    """Validate replay against current Runtime-owned root and claim facts.

    Every mutable authority expectation is supplied by the current Runtime
    reread.  Historical Event fields are evidence only and may never validate
    themselves merely because their internal digest is coherent.
    """

    if not isinstance(value, Mapping) or set(value) != _EVENT_KEYS:
        raise PlacementCommitmentError("COMMITMENT_EVENT_SHAPE_INVALID")
    if set(value) & FORBIDDEN_EVENT_KEYS:
        raise PlacementCommitmentError("COMMITMENT_EVENT_FORBIDDEN_FIELD")
    if value.get("schema_version") != COMMITMENT_SCHEMA:
        raise PlacementCommitmentError("COMMITMENT_EVENT_SCHEMA_INVALID")
    attempt_id = _token(
        value.get("committed_attempt_id"), code="COMMITTED_ATTEMPT_ID_INVALID"
    )
    current_attempt_id = _token(
        expected_attempt_id, code="COMMITTED_ATTEMPT_ID_INVALID"
    )
    if attempt_id != current_attempt_id:
        raise PlacementCommitmentError("COMMITTED_ATTEMPT_MISMATCH")
    current_created_command_id = _token(
        expected_responsibility_job_created_command_id,
        code="RESPONSIBILITY_CREATED_COMMAND_ID_INVALID",
    )
    current_authority_fingerprint = _digest_token(
        expected_responsibility_authority_fingerprint,
        code="RESPONSIBILITY_AUTHORITY_FINGERPRINT_INVALID",
    )
    expected = build_commitment_event_payload(
        plan=plan,
        committed_attempt_id=current_attempt_id,
        responsibility_job_created_command_id=current_created_command_id,
        responsibility_authority_fingerprint=current_authority_fingerprint,
    )
    if dict(value) != expected:
        raise PlacementCommitmentError("COMMITMENT_EVENT_REPLAY_CONFLICT")
    return expected


__all__ = [
    "COMMAND_SCHEMA",
    "COMMITMENT_SCHEMA",
    "EVENT_TYPE",
    "FORBIDDEN_EVENT_KEYS",
    "PlacementCommitmentError",
    "PlacementCommitmentPlan",
    "build_commitment_event_payload",
    "build_commitment_plan",
    "validate_commitment_event_payload",
]
