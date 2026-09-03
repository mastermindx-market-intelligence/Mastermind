"""Pure Capacity-C2 V2 alias-carrier placement-commitment contract.

The source responsibility remains a COO-owned aggregation root.  C2 binds its
current protected Capacity-C1 selection to one separate, alias-scoped CEO
carrier.  This module derives and validates immutable plan/Event wires only;
the existing Executive Runtime remains the sole Job, Attempt, Worker, quota,
transaction, and Event owner.

``validated_target_facts`` and ``validated_runtime_facts`` are closed
projections for private Runtime adapters.  Exact-key validation does not make
ordinary caller data authoritative: C2-R1 must construct both projections from
the SessionTargetRegistry and one current Runtime transaction, never expose
them on a public service route, and never recycle a historical Event as current
expectations.  Inside the existing Runtime ``BEGIN IMMEDIATE`` transaction and
before any claim, Event, quota, or other write, C2-R1 must look up the current
``(SESSION_ALIAS, CARRIER_GENERATION)`` carrier.  If none exists, the current
validated target fingerprint may continue through the normal C2-R1 claim logic.
If one exists, its persisted target fingerprint must match the current plan;
an A/B mismatch raises exactly ``TARGET_DEFINITION_CONFLICT`` and rolls back
with zero writes, no succession, and no effect.
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

COMMITMENT_SCHEMA = "mastermind.capacity_placement_commitment/v2"
COMMAND_SCHEMA = "mastermind.capacity_placement_commitment_command/v2"
CARRIER_COMMAND_SCHEMA = "mastermind.sol_session_carrier_command/v1"
EVENT_TYPE = "CAPACITY_PLACEMENT_COMMITTED"

SESSION_ALIAS = "EXECUTIVE-CEO-CODEX-A"
CARRIER_GENERATION = 1

TARGET_DEFINITION_FINGERPRINT_KEYS = frozenset(
    {
        "session_alias",
        "target_seat",
        "reasoning_surface",
        "wake_transport",
        "allowed_transports",
        "workstream",
    }
)

_PLACEMENT_MODE_TO_DISPOSITION = MappingProxyType(
    {
        "new_session_materialization": "created",
        "existing_session_reuse": "reused",
    }
)

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMAND_ID_RE = re.compile(r"^CAP-C2-[0-9a-f]{32}$")
_CARRIER_COMMAND_ID_RE = re.compile(r"^SOL-CARRIER-[0-9a-f]{32}$")

_PLAN_KEYS = frozenset(
    {
        "schema_version",
        "source_root_job_id",
        "expected_source_root_revision",
        "responsibility_ref",
        "placement_mode",
        "selection_document_digest",
        "selection_evidence_digest",
        "selected_worker_id",
        "selected_quota_class",
        "committed_placement_snapshot_digest",
        "session_alias",
        "target_definition_fingerprint",
        "carrier_generation",
        "carrier_job_created_command_id",
        "commitment_command_id",
        "command_fingerprint",
    }
)

RUNTIME_FACT_KEYS = frozenset(
    {
        "source_root_job_id",
        "source_root_revision",
        "source_job_created_command_id",
        "source_authority_fingerprint",
        "session_alias",
        "target_definition_fingerprint",
        "carrier_generation",
        "carrier_job_id",
        "carrier_job_created_command_id",
        "carrier_authority_fingerprint",
        "carrier_disposition",
        "committed_carrier_attempt_id",
        "carrier_worker_id",
        "carrier_quota_class",
        "carrier_placement_snapshot_digest",
    }
)

_EVENT_KEYS = frozenset(
    {
        "schema_version",
        "source_root_job_id",
        "source_job_created_command_id",
        "source_authority_fingerprint",
        "responsibility_ref",
        "placement_mode",
        "selection_document_digest",
        "selection_evidence_digest",
        "selected_worker_id",
        "selected_quota_class",
        "committed_placement_snapshot_digest",
        "session_alias",
        "target_definition_fingerprint",
        "carrier_generation",
        "carrier_job_id",
        "carrier_job_created_command_id",
        "carrier_authority_fingerprint",
        "carrier_disposition",
        "committed_carrier_attempt_id",
        "commitment_command_id",
        "command_fingerprint",
        "commitment_evidence_digest",
    }
)

FORBIDDEN_EVENT_KEYS = frozenset(
    {
        # Superseded V1/root-claim and aggregation-handoff vocabulary.
        "root_job_id",
        "expected_job_revision",
        "responsibility_job_created_command_id",
        "responsibility_authority_fingerprint",
        "aggregation_handoff_command_id",
        "aggregation_handoff_digest",
        "plan_attempt_id",
        "plan_digest",
        "committed_attempt_id",
        # Provider, process, actor, binding, and arming identity never crosses C2.
        "runtime_binding_id",
        "runtime_binding_generation",
        "provider_session_id",
        "native_handle",
        "session_epoch_id",
        "process_generation_id",
        "pid",
        "pgid",
        "process_start_identity",
        "boot_id",
        "account_label",
        "provider",
        "model",
        "model_output",
        "actor",
        "actor_binding",
        "slack_principal",
        "target_enabled",
        "production_armed",
        "arming_state",
    }
)


class PlacementCommitmentError(ValueError):
    """A fixed, secret-safe C2 command, adapter, or receipt refusal."""

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


def _revision(value: Any, *, code: str) -> int:
    if type(value) is not int or value < 0:
        raise PlacementCommitmentError(code)
    return value


def _generation(value: Any, *, code: str) -> int:
    if type(value) is not int or value < 1:
        raise PlacementCommitmentError(code)
    return value


def _canonical_target_definition(value: Any) -> dict[str, Any]:
    """Validate the exact six-field projection from SessionTargetRegistry.

    Arming, root overlays, unrelated targets, and policy metadata are excluded
    at the trusted adapter boundary rather than silently ignored here.
    """

    if not isinstance(value, Mapping):
        raise PlacementCommitmentError("TARGET_DEFINITION_SHAPE_INVALID")
    target = dict(value)
    if set(target) != TARGET_DEFINITION_FINGERPRINT_KEYS:
        raise PlacementCommitmentError("TARGET_DEFINITION_SHAPE_INVALID")
    try:
        session_alias = _token(
            target["session_alias"], code="TARGET_DEFINITION_INVALID"
        )
        target_seat = _token(target["target_seat"], code="TARGET_DEFINITION_INVALID")
        reasoning_surface = _token(
            target["reasoning_surface"], code="TARGET_DEFINITION_INVALID"
        )
        wake_transport = _token(
            target["wake_transport"], code="TARGET_DEFINITION_INVALID"
        )
        workstream = _token(target["workstream"], code="TARGET_DEFINITION_INVALID")
        allowed_raw = target["allowed_transports"]
        if not isinstance(allowed_raw, list) or not allowed_raw:
            raise PlacementCommitmentError("TARGET_DEFINITION_INVALID")
        allowed_transports = [
            _token(item, code="TARGET_DEFINITION_INVALID") for item in allowed_raw
        ]
        if len(set(allowed_transports)) != len(allowed_transports):
            raise PlacementCommitmentError("TARGET_DEFINITION_INVALID")
    except KeyError as exc:  # Exact shape above makes this defensive only.
        raise PlacementCommitmentError("TARGET_DEFINITION_SHAPE_INVALID") from exc
    return {
        "session_alias": session_alias,
        "target_seat": target_seat,
        "reasoning_surface": reasoning_surface,
        "wake_transport": wake_transport,
        "allowed_transports": allowed_transports,
        "workstream": workstream,
    }


def fingerprint_target_definition(value: Any) -> str:
    """Hash exactly the protected six-field target-definition projection."""

    return digest(_canonical_target_definition(value))


def _canonical_selection(value: Any) -> tuple[dict[str, Any], dict[str, Any], str]:
    try:
        selection = validate_placement_selection(value)
    except (TypeError, ValueError, OrchestrationPrincipalError) as exc:
        raise PlacementCommitmentError("PLACEMENT_SELECTION_INVALID") from exc
    if selection.get("state") != "selected":
        raise PlacementCommitmentError("PLACEMENT_SELECTION_NOT_SELECTED")
    if selection.get("selection_is_commitment") is not False:
        raise PlacementCommitmentError("PLACEMENT_SELECTION_ALREADY_COMMITTED")
    placement_mode = selection.get("selected_mode")
    if (
        not isinstance(placement_mode, str)
        or placement_mode not in _PLACEMENT_MODE_TO_DISPOSITION
    ):
        raise PlacementCommitmentError("PLACEMENT_MODE_INVALID")
    selected = selection.get("selected")
    try:
        snapshot = validate_placement_snapshot(selected)
    except (TypeError, ValueError, OrchestrationPrincipalError) as exc:
        raise PlacementCommitmentError("PLACEMENT_SNAPSHOT_INVALID") from exc
    return selection, snapshot, placement_mode


def _carrier_command_semantics(
    *,
    session_alias: str,
    target_definition_fingerprint: str,
    carrier_generation: int,
) -> dict[str, Any]:
    return {
        "schema_version": CARRIER_COMMAND_SCHEMA,
        "session_alias": session_alias,
        "target_definition_fingerprint": target_definition_fingerprint,
        "carrier_generation": carrier_generation,
    }


def _carrier_command_id(semantics: Mapping[str, Any]) -> str:
    return f"SOL-CARRIER-{digest(dict(semantics))[:32]}"


@dataclasses.dataclass(frozen=True, slots=True, init=False)
class PlacementCommitmentPlan:
    """Immutable C2 V2 plan passed to the existing Runtime mutation owner.

    ``expected_source_root_revision`` is an optimistic precondition, not stable
    command identity.  The exact selected placement snapshot is plan-private;
    only its digest crosses the plan and Event wires.
    """

    source_root_job_id: str
    expected_source_root_revision: int
    responsibility_ref: str
    placement_mode: str
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
    session_alias: str
    target_definition_fingerprint: str
    carrier_generation: int
    carrier_job_created_command_id: str
    commitment_command_id: str
    command_fingerprint: str
    schema_version: str = COMMAND_SCHEMA

    def __post_init__(self) -> None:
        _token(self.source_root_job_id, code="SOURCE_ROOT_JOB_ID_INVALID")
        _revision(
            self.expected_source_root_revision,
            code="EXPECTED_SOURCE_ROOT_REVISION_INVALID",
        )
        _token(self.responsibility_ref, code="RESPONSIBILITY_REF_INVALID")
        if (
            not isinstance(self.placement_mode, str)
            or self.placement_mode not in _PLACEMENT_MODE_TO_DISPOSITION
        ):
            raise PlacementCommitmentError("PLACEMENT_MODE_INVALID")
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
            snapshot = validate_placement_snapshot(self.committed_placement_snapshot)
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

        if self.session_alias != SESSION_ALIAS:
            raise PlacementCommitmentError("SESSION_ALIAS_CONFLICT")
        _digest_token(
            self.target_definition_fingerprint,
            code="TARGET_DEFINITION_FINGERPRINT_INVALID",
        )
        _generation(self.carrier_generation, code="CARRIER_GENERATION_INVALID")
        if self.carrier_generation != CARRIER_GENERATION:
            raise PlacementCommitmentError("CARRIER_GENERATION_INVALID")
        if (
            _CARRIER_COMMAND_ID_RE.fullmatch(self.carrier_job_created_command_id)
            is None
        ):
            raise PlacementCommitmentError("CARRIER_COMMAND_ID_INVALID")
        expected_carrier_command = _carrier_command_id(self.carrier_command_semantics())
        if self.carrier_job_created_command_id != expected_carrier_command:
            raise PlacementCommitmentError("CARRIER_COMMAND_ID_MISMATCH")

        if self.schema_version != COMMAND_SCHEMA:
            raise PlacementCommitmentError("COMMITMENT_COMMAND_SCHEMA_INVALID")
        if _COMMAND_ID_RE.fullmatch(self.commitment_command_id) is None:
            raise PlacementCommitmentError("COMMITMENT_COMMAND_ID_INVALID")
        _digest_token(self.command_fingerprint, code="COMMAND_FINGERPRINT_INVALID")
        expected_fingerprint = digest(self.command_semantics())
        if self.command_fingerprint != expected_fingerprint:
            raise PlacementCommitmentError("COMMAND_FINGERPRINT_MISMATCH")
        if self.commitment_command_id != f"CAP-C2-{expected_fingerprint[:32]}":
            raise PlacementCommitmentError("COMMITMENT_COMMAND_ID_MISMATCH")

    def carrier_command_semantics(self) -> dict[str, Any]:
        return _carrier_command_semantics(
            session_alias=self.session_alias,
            target_definition_fingerprint=self.target_definition_fingerprint,
            carrier_generation=self.carrier_generation,
        )

    def command_semantics(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_root_job_id": self.source_root_job_id,
            "responsibility_ref": self.responsibility_ref,
            "placement_mode": self.placement_mode,
            "selection_document_digest": self.selection_document_digest,
            "selection_evidence_digest": self.selection_evidence_digest,
            "selected_worker_id": self.selected_worker_id,
            "selected_quota_class": self.selected_quota_class,
            "committed_placement_snapshot_digest": (
                self.committed_placement_snapshot_digest
            ),
            "session_alias": self.session_alias,
            "target_definition_fingerprint": (self.target_definition_fingerprint),
            "carrier_generation": self.carrier_generation,
            "carrier_job_created_command_id": (self.carrier_job_created_command_id),
        }

    def to_dict(self) -> dict[str, Any]:
        value = dict(self.command_semantics())
        value["expected_source_root_revision"] = self.expected_source_root_revision
        value["commitment_command_id"] = self.commitment_command_id
        value["command_fingerprint"] = self.command_fingerprint
        if set(value) != _PLAN_KEYS:
            raise PlacementCommitmentError("COMMITMENT_PLAN_SHAPE_INVALID")
        return value


def build_commitment_plan(
    *,
    source_root_job_id: str,
    expected_source_root_revision: int,
    placement_selection: Any,
    validated_target_facts: Any,
) -> PlacementCommitmentPlan:
    """Bind one current C1 selection to the protected alias carrier identity."""

    source_root = _token(source_root_job_id, code="SOURCE_ROOT_JOB_ID_INVALID")
    revision = _revision(
        expected_source_root_revision,
        code="EXPECTED_SOURCE_ROOT_REVISION_INVALID",
    )
    target = _canonical_target_definition(validated_target_facts)
    if target["session_alias"] != SESSION_ALIAS:
        raise PlacementCommitmentError("TARGET_DEFINITION_CONFLICT")
    target_fingerprint = digest(target)

    selection, selected, placement_mode = _canonical_selection(placement_selection)
    responsibility_ref = _token(
        selection["responsibility_ref"], code="RESPONSIBILITY_REF_INVALID"
    )
    carrier_semantics = _carrier_command_semantics(
        session_alias=SESSION_ALIAS,
        target_definition_fingerprint=target_fingerprint,
        carrier_generation=CARRIER_GENERATION,
    )
    carrier_command = _carrier_command_id(carrier_semantics)
    semantics = {
        "schema_version": COMMAND_SCHEMA,
        "source_root_job_id": source_root,
        "responsibility_ref": responsibility_ref,
        "placement_mode": placement_mode,
        "selection_document_digest": digest(selection),
        "selection_evidence_digest": digest(selection["evidence"]),
        "selected_worker_id": selected["worker_id"],
        "selected_quota_class": selected["quota_class"],
        "committed_placement_snapshot_digest": digest(selected),
        "session_alias": SESSION_ALIAS,
        "target_definition_fingerprint": target_fingerprint,
        "carrier_generation": CARRIER_GENERATION,
        "carrier_job_created_command_id": carrier_command,
    }
    fingerprint = digest(semantics)
    plan = object.__new__(PlacementCommitmentPlan)
    values = {
        "source_root_job_id": source_root,
        "expected_source_root_revision": revision,
        "responsibility_ref": responsibility_ref,
        "placement_mode": placement_mode,
        "selection_document_digest": semantics["selection_document_digest"],
        "selection_evidence_digest": semantics["selection_evidence_digest"],
        "selected_worker_id": selected["worker_id"],
        "selected_quota_class": selected["quota_class"],
        "committed_placement_snapshot": selected,
        "committed_placement_snapshot_digest": semantics[
            "committed_placement_snapshot_digest"
        ],
        "session_alias": SESSION_ALIAS,
        "target_definition_fingerprint": target_fingerprint,
        "carrier_generation": CARRIER_GENERATION,
        "carrier_job_created_command_id": carrier_command,
        "commitment_command_id": f"CAP-C2-{fingerprint[:32]}",
        "command_fingerprint": fingerprint,
        "schema_version": COMMAND_SCHEMA,
    }
    for field, value in values.items():
        object.__setattr__(plan, field, value)
    plan.__post_init__()
    return plan


def _canonical_runtime_facts(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise PlacementCommitmentError("RUNTIME_FACTS_SHAPE_INVALID")
    facts = dict(value)
    if set(facts) != RUNTIME_FACT_KEYS:
        raise PlacementCommitmentError("RUNTIME_FACTS_SHAPE_INVALID")
    disposition = facts["carrier_disposition"]
    if not isinstance(disposition, str) or disposition not in frozenset(
        _PLACEMENT_MODE_TO_DISPOSITION.values()
    ):
        raise PlacementCommitmentError("CARRIER_DISPOSITION_INVALID")
    return {
        "source_root_job_id": _token(
            facts["source_root_job_id"], code="SOURCE_ROOT_JOB_ID_INVALID"
        ),
        "source_root_revision": _revision(
            facts["source_root_revision"],
            code="SOURCE_ROOT_REVISION_INVALID",
        ),
        "source_job_created_command_id": _token(
            facts["source_job_created_command_id"],
            code="SOURCE_JOB_CREATED_COMMAND_ID_INVALID",
        ),
        "source_authority_fingerprint": _digest_token(
            facts["source_authority_fingerprint"],
            code="SOURCE_AUTHORITY_FINGERPRINT_INVALID",
        ),
        "session_alias": _token(facts["session_alias"], code="SESSION_ALIAS_INVALID"),
        "target_definition_fingerprint": _digest_token(
            facts["target_definition_fingerprint"],
            code="TARGET_DEFINITION_FINGERPRINT_INVALID",
        ),
        "carrier_generation": _generation(
            facts["carrier_generation"], code="CARRIER_GENERATION_INVALID"
        ),
        "carrier_job_id": _token(
            facts["carrier_job_id"], code="CARRIER_JOB_ID_INVALID"
        ),
        "carrier_job_created_command_id": _carrier_command_token(
            facts["carrier_job_created_command_id"]
        ),
        "carrier_authority_fingerprint": _digest_token(
            facts["carrier_authority_fingerprint"],
            code="CARRIER_AUTHORITY_FINGERPRINT_INVALID",
        ),
        "carrier_disposition": disposition,
        "committed_carrier_attempt_id": _token(
            facts["committed_carrier_attempt_id"],
            code="COMMITTED_CARRIER_ATTEMPT_ID_INVALID",
        ),
        "carrier_worker_id": _token(
            facts["carrier_worker_id"], code="CARRIER_WORKER_ID_INVALID"
        ),
        "carrier_quota_class": _token(
            facts["carrier_quota_class"],
            code="CARRIER_QUOTA_CLASS_INVALID",
        ),
        "carrier_placement_snapshot_digest": _digest_token(
            facts["carrier_placement_snapshot_digest"],
            code="CARRIER_PLACEMENT_SNAPSHOT_DIGEST_INVALID",
        ),
    }


def _carrier_command_token(value: Any) -> str:
    if not isinstance(value, str) or _CARRIER_COMMAND_ID_RE.fullmatch(value) is None:
        raise PlacementCommitmentError("CARRIER_COMMAND_ID_INVALID")
    return value


def _runtime_facts_for_plan(
    value: Any,
    *,
    plan: PlacementCommitmentPlan,
    conflict_code: str,
) -> dict[str, Any]:
    facts = _canonical_runtime_facts(value)
    if facts["target_definition_fingerprint"] != plan.target_definition_fingerprint:
        raise PlacementCommitmentError("TARGET_DEFINITION_CONFLICT")
    expected = {
        "source_root_job_id": plan.source_root_job_id,
        "source_root_revision": plan.expected_source_root_revision,
        "session_alias": plan.session_alias,
        "carrier_generation": plan.carrier_generation,
        "carrier_job_created_command_id": plan.carrier_job_created_command_id,
        "carrier_disposition": _PLACEMENT_MODE_TO_DISPOSITION[plan.placement_mode],
        "carrier_worker_id": plan.selected_worker_id,
        "carrier_quota_class": plan.selected_quota_class,
        "carrier_placement_snapshot_digest": (plan.committed_placement_snapshot_digest),
    }
    if any(facts[key] != expected[key] for key in expected):
        raise PlacementCommitmentError(conflict_code)
    if (
        facts["carrier_job_id"] == plan.source_root_job_id
        or facts["carrier_job_created_command_id"]
        == facts["source_job_created_command_id"]
    ):
        raise PlacementCommitmentError(conflict_code)
    return facts


def _event_payload(
    *,
    plan: PlacementCommitmentPlan,
    runtime_facts: Mapping[str, Any],
) -> dict[str, Any]:
    evidence = {
        "source_root_job_id": plan.source_root_job_id,
        "source_job_created_command_id": runtime_facts["source_job_created_command_id"],
        "source_authority_fingerprint": runtime_facts["source_authority_fingerprint"],
        "responsibility_ref": plan.responsibility_ref,
        "placement_mode": plan.placement_mode,
        "selection_document_digest": plan.selection_document_digest,
        "selection_evidence_digest": plan.selection_evidence_digest,
        "selected_worker_id": plan.selected_worker_id,
        "selected_quota_class": plan.selected_quota_class,
        "committed_placement_snapshot_digest": (
            plan.committed_placement_snapshot_digest
        ),
        "session_alias": plan.session_alias,
        "target_definition_fingerprint": plan.target_definition_fingerprint,
        "carrier_generation": plan.carrier_generation,
        "carrier_job_id": runtime_facts["carrier_job_id"],
        "carrier_job_created_command_id": (plan.carrier_job_created_command_id),
        "carrier_authority_fingerprint": runtime_facts["carrier_authority_fingerprint"],
        "carrier_disposition": runtime_facts["carrier_disposition"],
        "committed_carrier_attempt_id": runtime_facts["committed_carrier_attempt_id"],
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


def build_commitment_event_payload(
    *,
    plan: PlacementCommitmentPlan,
    validated_runtime_facts: Any,
) -> dict[str, Any]:
    """Build one V2 Event after the private Runtime transaction succeeds.

    The input-only carrier Worker/quota/snapshot facts must equal the C1 plan;
    the Event carries one canonical copy of those committed facts.
    """

    if not isinstance(plan, PlacementCommitmentPlan):
        raise PlacementCommitmentError("COMMITMENT_PLAN_INVALID")
    facts = _runtime_facts_for_plan(
        validated_runtime_facts,
        plan=plan,
        conflict_code="RUNTIME_FACTS_CONFLICT",
    )
    return _event_payload(plan=plan, runtime_facts=facts)


def validate_commitment_event_payload(
    value: Any,
    *,
    plan: PlacementCommitmentPlan,
    validated_runtime_facts: Any,
) -> dict[str, Any]:
    """Revalidate a historical Event against one fresh Runtime projection.

    The caller must rebuild ``plan`` from current source/C1/target truth and the
    private Runtime adapter must freshly derive ``validated_runtime_facts``.
    The Event and its hashes never authenticate themselves.
    """

    if not isinstance(value, Mapping):
        raise PlacementCommitmentError("COMMITMENT_EVENT_SHAPE_INVALID")
    if set(value) & FORBIDDEN_EVENT_KEYS:
        raise PlacementCommitmentError("COMMITMENT_EVENT_FORBIDDEN_FIELD")
    if set(value) != _EVENT_KEYS:
        raise PlacementCommitmentError("COMMITMENT_EVENT_SHAPE_INVALID")
    if value.get("schema_version") != COMMITMENT_SCHEMA:
        raise PlacementCommitmentError("COMMITMENT_EVENT_SCHEMA_INVALID")
    if not isinstance(plan, PlacementCommitmentPlan):
        raise PlacementCommitmentError("COMMITMENT_PLAN_INVALID")
    try:
        facts = _runtime_facts_for_plan(
            validated_runtime_facts,
            plan=plan,
            conflict_code="COMMITMENT_EVENT_REPLAY_CONFLICT",
        )
    except PlacementCommitmentError as exc:
        if exc.code in {
            "RUNTIME_FACTS_SHAPE_INVALID",
            "TARGET_DEFINITION_CONFLICT",
        }:
            raise
        raise PlacementCommitmentError("COMMITMENT_EVENT_REPLAY_CONFLICT") from exc
    expected = _event_payload(plan=plan, runtime_facts=facts)
    if dict(value) != expected:
        raise PlacementCommitmentError("COMMITMENT_EVENT_REPLAY_CONFLICT")
    return expected


__all__ = [
    "CARRIER_COMMAND_SCHEMA",
    "CARRIER_GENERATION",
    "COMMAND_SCHEMA",
    "COMMITMENT_SCHEMA",
    "EVENT_TYPE",
    "FORBIDDEN_EVENT_KEYS",
    "RUNTIME_FACT_KEYS",
    "SESSION_ALIAS",
    "TARGET_DEFINITION_FINGERPRINT_KEYS",
    "PlacementCommitmentError",
    "PlacementCommitmentPlan",
    "build_commitment_event_payload",
    "build_commitment_plan",
    "fingerprint_target_definition",
    "validate_commitment_event_payload",
]
