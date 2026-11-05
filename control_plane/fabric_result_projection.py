"""control_plane.fabric_result_projection — the shared pure Fabric role result projector.

This module is the ONE shared, transport-agnostic, pure projection owner for
``mastermind.fabric_role_result_view.v1``.  The B (Workspace) and C (consumer)
integration commissions BOTH reuse this one function over the ACTUAL
:class:`control_plane.executive_runtime.BoundedRoleResultSnapshot` and its
finalized :class:`~control_plane.executive_runtime.RuntimeReadObservationReceipt`.

Design laws
-----------
* **Actual owner types only.**  The accepted snapshot/completion/root-metadata
  and receipt are the real frozen Runtime dataclasses; this module defines no
  shadow DTO, adapts no Mapping lookalike, and copies no canonical validator.
  When the Runtime source is too old to carry the bounded role-result seam the
  guarded import degrades to a typed refusal, never to a fake input shape.
* **Pure.**  No acquisition, file/socket/SQL/Runtime-path open, clock, store,
  authorization decision, or caller budget.  Canonical meaning is reused from
  :mod:`control_plane.executive_orchestration_result` (``validate_envelope`` /
  ``canonical_digest``) — never re-derived under a new law.
* **Two independent documents.**  ``complete`` and ``content_over_budget``
  share one identity/digest/count header and differ only in availability,
  content completeness, ``content``, and ``omitted``.  Every mutable nested
  value is deep-copied per document: no input aliases and no aliases between
  the two returned documents.
* **Trust through assembly, not crypto.**  The caller assembles both inputs
  after the Runtime observation with-block has physically closed.  ``SAME``
  state, equal nonnegative integer data-version samples (bool refused), and
  exact non-null 32-lowercase-hex source-identity equality are required;
  ``None == None``, ``UNKNOWN``, ``CONFLICT``, unfinalized, and foreign
  receipts do not qualify.
* **No newest-revision evidence.**  ``review.latest_revision_currentness`` is
  always ``UNPROVEN`` here; a positive later-revision claim needs another
  existing owner and stays outside this projection.  ``reviewed_result_digest``
  is the target ROLE RESULT digest, distinct from the envelope selector.
* **Display only.**  This is derived view data, never a second canonical
  result schema, and the helper itself makes no permission decision.
"""
from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping
from typing import Any

from control_plane import executive_orchestration_result as result_owner

try:  # The actual Runtime owner seam; absent in older source trees.
    from control_plane.executive_runtime import (
        RUNTIME_READ_OBSERVATION_SCHEMA,
        BoundedRoleResultRootMetadata,
        BoundedRoleResultSnapshot,
        RuntimeReadObservationReceipt,
        ValidatedRoleCompletion,
    )
except ImportError:  # older Runtime source without the bounded seam
    RUNTIME_READ_OBSERVATION_SCHEMA = None
    BoundedRoleResultRootMetadata = None
    BoundedRoleResultSnapshot = None
    RuntimeReadObservationReceipt = None
    ValidatedRoleCompletion = None

#: Closed wire schema string for this shared projection document.
FABRIC_ROLE_RESULT_VIEW_SCHEMA = "mastermind.fabric_role_result_view.v1"

_HEX64_RE = re.compile(r"[0-9a-f]{64}")
_SOURCE_IDENTITY_RE = re.compile(r"[0-9a-f]{32}")
# The root creation command is the strict v2 ceo-intent command over its
# source id; the Runtime mints and validates this exact closed form.
_CREATION_COMMAND_RE = re.compile(r"ceo-intent:[A-Za-z0-9][A-Za-z0-9._-]{2,63}")

_TERMINAL_ROLES = frozenset(result_owner.ROLES)
_GENERATION_KEYS = frozenset(
    {"schema", "state", "source_identity", "before", "after"}
)


class FabricResultProjectionError(Exception):
    """A typed closed refusal raised by :func:`project_fabric_role_result`.

    Carries one closed ``code`` plus a bounded fixed ``message``; raw
    diagnostics from underlying owners are never embedded, so public consumers
    never see them.  Callers translate this to their OWN public refusal
    vocabulary; the codes below are this helper's entire closed vocabulary.
    """


# ---------------------------------------------------------------------------
# the frozen return document pair
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class FabricRoleResultProjection:
    """Independent ``complete`` and ``content_over_budget`` wire documents."""

    complete: dict[str, Any]
    content_over_budget: dict[str, Any]


# ---------------------------------------------------------------------------
# closed validation helpers
# ---------------------------------------------------------------------------


def _refuse(code: str, message: str) -> None:
    raise FabricResultProjectionError(code, message)


def _identifier(value: Any, *, field: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > 128
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        _refuse("input_invalid", f"{field} is not a closed Runtime identifier")
    return value


def _hex64(value: Any, *, field: str, code: str = "input_invalid") -> str:
    if type(value) is not str or _HEX64_RE.fullmatch(value) is None:
        _refuse(code, f"{field} must be lowercase 64-character hex")
    return value


def _source_identity(value: Any, *, field: str) -> str:
    if value is None:
        _refuse("source_identity_invalid", f"{field} is missing")
    if type(value) is not str or _SOURCE_IDENTITY_RE.fullmatch(value) is None:
        _refuse("source_identity_invalid", f"{field} must be 32 lowercase hex characters")
    return value


def _copy_json(value: Any, *, field: str) -> Any:
    """Deep-copy canonical JSON material; refuse anything non-canonical."""

    if isinstance(value, dict):
        return {str(key): _copy_json(item, field=field) for key, item in value.items()}
    if isinstance(value, list):
        return [_copy_json(item, field=field) for item in value]
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    _refuse("input_invalid", f"{field} contains non-canonical non-JSON material")
    raise AssertionError("unreachable")  # pragma: no cover


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------


def project_fabric_role_result(
    snapshot: "BoundedRoleResultSnapshot | Any",
    receipt: "RuntimeReadObservationReceipt | Any",
) -> FabricRoleResultProjection:
    """Project one actual bounded role-result snapshot into the shared wire view.

    Pure and closed: no I/O, no clock, no Runtime re-entry, no budget, no
    permission decision.  Foreign, malformed, unfinalized, or non-matching
    inputs raise :class:`FabricResultProjectionError`.
    """

    # 1. Actual owner types (a shadow or Mapping lookalike is a foreign input).
    if BoundedRoleResultSnapshot is None or not isinstance(
        snapshot, BoundedRoleResultSnapshot
    ):
        _refuse("input_invalid", "snapshot must be a BoundedRoleResultSnapshot")
    if RuntimeReadObservationReceipt is None or not isinstance(
        receipt, RuntimeReadObservationReceipt
    ):
        _refuse(
            "input_invalid", "receipt must be a finalized Runtime observation receipt"
        )
    if not isinstance(snapshot.completion, ValidatedRoleCompletion):
        _refuse("input_invalid", "snapshot.completion must be a ValidatedRoleCompletion")
    if not isinstance(snapshot.root_metadata, BoundedRoleResultRootMetadata):
        _refuse(
            "input_invalid",
            "snapshot.root_metadata must be a BoundedRoleResultRootMetadata",
        )

    # 2. Snapshot selection scalars.
    _identifier(snapshot.root_job_id, field="snapshot.root_job_id")
    _identifier(snapshot.job_id, field="snapshot.job_id")
    _identifier(snapshot.attempt_id, field="snapshot.attempt_id")
    _hex64(snapshot.result_envelope_digest, field="snapshot.result_envelope_digest")
    _source_identity(
        snapshot.observation_source_identity,
        field="snapshot.observation_source_identity",
    )

    # 3. Finalized receipt: exact schema, SAME state, integer samples, identity.
    if receipt.schema != RUNTIME_READ_OBSERVATION_SCHEMA:
        _refuse("receipt_invalid", "receipt schema is not the Runtime read observation schema")
    if receipt.state != "SAME":
        _refuse("state_conflict", "receipt state is not SAME")
    for sample, field in ((receipt.before, "receipt.before"), (receipt.after, "receipt.after")):
        if type(sample) is not int or sample < 0:
            _refuse("receipt_invalid", f"{field} must be a non-negative integer")
    if receipt.before != receipt.after:
        _refuse("state_conflict", "receipt data version samples do not match")
    _source_identity(
        receipt.source_identity, field="receipt.source_identity"
    )
    if receipt.source_identity != snapshot.observation_source_identity:
        _refuse(
            "source_identity_mismatch",
            "receipt.source_identity does not equal snapshot.observation_source_identity",
        )

    # 4. Root metadata: the strict v2 aggregation self-root's frozen provenance.
    metadata = snapshot.root_metadata
    if (
        metadata.job_id != snapshot.root_job_id
        or metadata.root_job_id != snapshot.root_job_id
    ):
        _refuse("selection_invalid", "root metadata identity disagrees with the selected root")
    if metadata.orchestration_role != "aggregation":
        _refuse("root_metadata_invalid", "root orchestration role is not aggregation")
    if (
        type(metadata.creation_command_id) is not str
        or _CREATION_COMMAND_RE.fullmatch(metadata.creation_command_id) is None
    ):
        _refuse("root_metadata_invalid", "root creation command is not a strict v2 ceo-intent command")
    if metadata.work_ref is not None and (
        type(metadata.work_ref) is not str
        or not metadata.work_ref
        or metadata.work_ref != metadata.work_ref.strip()
    ):
        _refuse("root_metadata_invalid", "root work_ref must be null or non-empty text")
    _hex64(
        metadata.orchestration_provenance_digest,
        field="root_metadata.orchestration_provenance_digest",
        code="root_metadata_invalid",
    )
    _hex64(
        metadata.source_digest,
        field="root_metadata.source_digest",
        code="root_metadata_invalid",
    )

    # 5. Completion identity: the exact selected Job, its current Attempt.
    completion = snapshot.completion
    try:
        job, attempt = completion.job, completion.attempt
        role = job.orchestration_role
        current_attempt_id = job.current_attempt_id
        attempt_id, attempt_job_id, worker_id = (
            attempt.attempt_id,
            attempt.job_id,
            attempt.worker_id,
        )
    except AttributeError:
        _refuse("input_invalid", "completion is not the actual validated material")
    if role not in _TERMINAL_ROLES:
        _refuse("input_invalid", "selected Job orchestration role is not closed")
    if job.job_id != snapshot.job_id:
        _refuse("selection_invalid", "selected Job is not the snapshot Job")
    if job.root_job_id != snapshot.root_job_id:
        _refuse("selection_invalid", "selected Job root disagrees with the snapshot root")
    if current_attempt_id != snapshot.attempt_id or attempt_id != snapshot.attempt_id:
        _refuse("selection_invalid", "selected current Attempt is not the snapshot Attempt")
    if attempt_job_id != snapshot.job_id:
        _refuse("selection_invalid", "selected Attempt belongs to another Job")

    # 6. Nullable work_ref agrees with the canonical dialogue source when present.
    dialogue_source = completion.dialogue_source
    if (
        dialogue_source is not None
        and metadata.work_ref != dialogue_source.work_ref
    ):
        _refuse(
            "root_metadata_invalid",
            "root work_ref disagrees with the canonical dialogue source",
        )

    # 7. Canonical meaning is reused, never re-derived: one validate_envelope
    #    pass, then digest equality against snapshot, completion, and the
    #    sealed terminal receipt.  Raw diagnostics are never surfaced.
    try:
        validated = result_owner.validate_envelope(
            completion.result_envelope,
            expected_job_id=snapshot.job_id,
            expected_run_id=snapshot.attempt_id,
            expected_worker_id=str(worker_id),
            expected_role=role,
            expected_root_job_id=snapshot.root_job_id,
        )
    except Exception:
        _refuse("validation_failed", "canonical envelope validation refused")
    envelope_digest = result_owner.canonical_digest(validated)
    if envelope_digest != snapshot.result_envelope_digest:
        _refuse("digest_mismatch", "canonical envelope digest disagrees with the snapshot digest")
    if envelope_digest != completion.result_digest:
        _refuse("digest_mismatch", "canonical envelope digest disagrees with the completion digest")
    role_result_digest = result_owner.canonical_digest(validated["role_result"])
    if role_result_digest != completion.role_result_digest:
        _refuse("digest_mismatch", "canonical role-result digest disagrees with the completion digest")
    terminal = completion.terminal_receipt
    if not isinstance(terminal, Mapping) or (
        terminal.get("job_id") != snapshot.job_id
        or terminal.get("attempt_id") != snapshot.attempt_id
        or terminal.get("status") != "COMPLETED"
        or terminal.get("result_envelope_digest") != snapshot.result_envelope_digest
    ):
        _refuse("digest_mismatch", "terminal receipt disagrees with the selection")
    try:
        terminal_envelope_matches = (
            result_owner.canonical_bytes(terminal.get("result_envelope"))
            == result_owner.canonical_bytes(validated)
        )
    except result_owner.OrchestrationResultError:
        terminal_envelope_matches = False
    if not terminal_envelope_matches:
        _refuse("digest_mismatch", "terminal envelope disagrees with the canonical completion")

    # 8. Review block and exact counts.  next_actions is the OUTER canonical
    #    envelope field: an integer count, zero included.
    next_actions_count = len(validated["next_actions"])
    if role == "review":
        review_result = validated["role_result"]
        findings = review_result["findings"]
        severity_counts = {"total": len(findings), "blocking": 0, "warning": 0, "info": 0}
        for finding in findings:
            severity_counts[finding["severity"]] += 1
        review = {
            "verdict": review_result["verdict"],
            "reviewed_job_id": review_result["reviewed_job_id"],
            "reviewed_attempt_id": review_result["reviewed_attempt_id"],
            "reviewed_result_digest": review_result["reviewed_result_digest"],
            "latest_revision_currentness": "UNPROVEN",
        }
        findings_counts: Any = severity_counts
    else:
        review = None
        findings_counts = None

    # 9. The two independent closed documents.
    def _document(availability: str, content: Any, omitted: list[str]) -> dict[str, Any]:
        counts = {
            "findings": _copy_json(findings_counts, field="counts.findings"),
            "next_actions": next_actions_count,
        }
        return {
            "schema": FABRIC_ROLE_RESULT_VIEW_SCHEMA,
            "selection": {
                "root_job_id": snapshot.root_job_id,
                "job_id": snapshot.job_id,
                "attempt_id": snapshot.attempt_id,
                "result_envelope_digest": snapshot.result_envelope_digest,
            },
            "role": role,
            "execution_status": "COMPLETED",
            "acceptance": "NOT_PROJECTED",
            "role_result_digest": role_result_digest,
            "generation": _generation_copy(receipt),
            "availability": availability,
            "content_complete": availability == "AVAILABLE",
            "review": _copy_json(review, field="review"),
            "counts": counts,
            "content": content,
            "omitted": omitted,
        }

    complete = _document(
        "AVAILABLE",
        {
            "role_result": _copy_json(validated["role_result"], field="content.role_result"),
            "summary": _copy_json(validated["summary"], field="content.summary"),
            "next_actions": _copy_json(validated["next_actions"], field="content.next_actions"),
        },
        [],
    )
    content_over_budget = _document("CONTENT_OVER_BUDGET", None, ["role_result", "summary", "next_actions"])
    return FabricRoleResultProjection(complete=complete, content_over_budget=content_over_budget)


def _generation_copy(receipt: Any) -> dict[str, Any]:
    """One independent copy of the finalized receipt's exact public dictionary."""

    generation = dict(receipt.to_dict())
    if set(generation) != _GENERATION_KEYS:
        _refuse("input_invalid", "finalized receipt public dictionary is not the closed shape")
    return generation
