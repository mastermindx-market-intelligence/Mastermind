from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json

import pytest

from control_plane import executive_placement_commitment as c2
from control_plane import executive_placement_selection as c1
from control_plane.executive_steward import (
    CapacityState,
    EffectState,
    Freshness,
    ResponsibilityFact,
    Seat,
    SourceOwner,
    SourceRef,
)

_TARGET_FINGERPRINT_KEYS = {
    "session_alias",
    "target_seat",
    "reasoning_surface",
    "wake_transport",
    "allowed_transports",
    "workstream",
}
_STABLE_SEMANTIC_KEYS = {
    "schema_version",
    "source_root_job_id",
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
}
_PLAN_WIRE_KEYS = {
    *_STABLE_SEMANTIC_KEYS,
    "expected_source_root_revision",
    "commitment_command_id",
    "command_fingerprint",
}
_RUNTIME_FACT_KEYS = {
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
_EVENT_EVIDENCE_KEYS = {
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
}
_EVENT_KEYS = {
    "schema_version",
    *_EVENT_EVIDENCE_KEYS,
    "commitment_evidence_digest",
}
_SUPERSEDED_FIELDS = {
    "root_job_id",
    "expected_job_revision",
    "responsibility_job_created_command_id",
    "responsibility_authority_fingerprint",
    "aggregation_handoff_command_id",
    "aggregation_handoff_digest",
    "plan_attempt_id",
    "plan_digest",
    "committed_attempt_id",
}
_REMOVED_V6_EVENT_FIELDS = {
    "expected_source_root_revision",
    "source_root_job_created_command_id",
    "source_root_authority_fingerprint",
    "carrier_attempt_id",
}
_FORBIDDEN_EVENT_FIELDS = {
    *_SUPERSEDED_FIELDS,
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

_TARGET_FINGERPRINT = "f6636381fe18d7a05224d9e9fc5105d6d6727acc895b306f46659c40f6b6b7a5"
_CARRIER_COMMAND = "SOL-CARRIER-b84e2db087de11ea3b496b7b86b09070"
_SOURCE_AUTHORITY_FINGERPRINT = "a" * 64
_CARRIER_AUTHORITY_FINGERPRINT = "b" * 64
_UNSET = object()


def _independent_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source(owner: SourceOwner, ref: str) -> SourceRef:
    return SourceRef(
        owner=owner,
        ref=ref,
        observed_at="2026-09-03T00:00:00Z",
        freshness=Freshness.CURRENT,
    )


def _selection(
    *,
    mode: c1.PlacementMode = c1.PlacementMode.NEW_SESSION_MATERIALIZATION,
    worker_id: str = "worker-1",
    quota_class: str = "standard",
) -> dict:
    responsibility = ResponsibilityFact(
        responsibility_ref="WS:CAP-C2",
        title="Atomic alias-carrier placement commitment",
        accountable_seat=Seat.CEO,
        state="waiting_capacity",
        root_job_id=None,
        source=_source(SourceOwner.AGENT_OS, "agentos-workstream-cap-c2"),
    )
    demand = c1.PlacementDemand(
        required_capabilities=frozenset({"executive"}),
        quota_class=quota_class,
        provider="codex",
        allowed_modes=frozenset({mode}),
    )
    is_new = mode is c1.PlacementMode.NEW_SESSION_MATERIALIZATION
    candidate = c1.PlacementCandidateFact(
        worker_id=worker_id,
        provider="codex",
        account_label="codex-ceo-a",
        quota_class=quota_class,
        capabilities=frozenset({"executive"}),
        observed_at_ms=1_788_400_000_000,
        occupancy=c1.OccupancyState.FREE,
        occupancy_source=_source(SourceOwner.RUNTIME_BINDING, "binding-current"),
        capacity_state=CapacityState.AVAILABLE,
        capacity_source=_source(SourceOwner.CAPACITY, "capacity-current"),
        host_source_closure_proven=True,
        closure_source=_source(SourceOwner.CAPACITY, "closure-current"),
        effect_state=EffectState.NONE,
        mode=mode,
        creation_surface_accessible=True if is_new else None,
        session_creation_allowed=True if is_new else None,
    )
    decision = c1.select_placement(
        responsibility=responsibility,
        demand=demand,
        candidates=(candidate,),
    )
    assert decision.state is c1.SelectionState.SELECTED
    return decision.to_dict()


def _target_facts(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "session_alias": "EXECUTIVE-CEO-CODEX-A",
        "target_seat": "ceo",
        "reasoning_surface": "codex",
        "wake_transport": "codex-app-server",
        "allowed_transports": ["codex-app-server"],
        "workstream": "executive",
    }
    value.update(changes)
    return value


def _plan(
    *,
    source_root_job_id: str = "job-source-1",
    revision: int = 7,
    selection: object = _UNSET,
    target_facts: object = _UNSET,
) -> c2.PlacementCommitmentPlan:
    return c2.build_commitment_plan(
        source_root_job_id=source_root_job_id,
        expected_source_root_revision=revision,
        placement_selection=_selection() if selection is _UNSET else selection,
        validated_target_facts=(
            _target_facts() if target_facts is _UNSET else target_facts
        ),
    )


def _runtime_facts(
    plan: c2.PlacementCommitmentPlan | None = None,
    **changes: object,
) -> dict[str, object]:
    bound = plan or _plan()
    value: dict[str, object] = {
        "source_root_job_id": bound.source_root_job_id,
        "source_root_revision": bound.expected_source_root_revision,
        "source_job_created_command_id": "CEO-V2-ROOT-CREATED-1",
        "source_authority_fingerprint": _SOURCE_AUTHORITY_FINGERPRINT,
        "session_alias": bound.session_alias,
        "target_definition_fingerprint": bound.target_definition_fingerprint,
        "carrier_generation": bound.carrier_generation,
        "carrier_job_id": "job-ceo-carrier-1",
        "carrier_job_created_command_id": bound.carrier_job_created_command_id,
        "carrier_authority_fingerprint": _CARRIER_AUTHORITY_FINGERPRINT,
        "carrier_disposition": {
            "new_session_materialization": "created",
            "existing_session_reuse": "reused",
        }[bound.placement_mode],
        "committed_carrier_attempt_id": "attempt-ceo-carrier-1",
        "carrier_worker_id": bound.selected_worker_id,
        "carrier_quota_class": bound.selected_quota_class,
        "carrier_placement_snapshot_digest": (
            bound.committed_placement_snapshot_digest
        ),
    }
    value.update(changes)
    return value


def _event(
    plan: c2.PlacementCommitmentPlan | None = None,
    runtime_facts: object = _UNSET,
) -> dict:
    bound = plan or _plan()
    return c2.build_commitment_event_payload(
        plan=bound,
        validated_runtime_facts=(
            _runtime_facts(bound) if runtime_facts is _UNSET else runtime_facts
        ),
    )


def _validate(
    payload: object,
    *,
    plan: c2.PlacementCommitmentPlan | None = None,
    runtime_facts: object = _UNSET,
) -> dict:
    bound = plan or _plan()
    return c2.validate_commitment_event_payload(
        payload,
        plan=bound,
        validated_runtime_facts=(
            _runtime_facts(bound) if runtime_facts is _UNSET else runtime_facts
        ),
    )


def test_v2_schemas_constants_and_literal_wire_shapes_are_pinned() -> None:
    plan = _plan()
    payload = _event(plan)

    assert c2.COMMAND_SCHEMA == "mastermind.capacity_placement_commitment_command/v2"
    assert c2.COMMITMENT_SCHEMA == "mastermind.capacity_placement_commitment/v2"
    assert c2.CARRIER_COMMAND_SCHEMA == "mastermind.sol_session_carrier_command/v1"
    assert c2.SESSION_ALIAS == "EXECUTIVE-CEO-CODEX-A"
    assert c2.CARRIER_GENERATION == 1
    assert c2.TARGET_DEFINITION_FINGERPRINT_KEYS == frozenset(_TARGET_FINGERPRINT_KEYS)
    assert set(plan.command_semantics()) == _STABLE_SEMANTIC_KEYS
    assert set(plan.to_dict()) == _PLAN_WIRE_KEYS
    assert set(payload) == _EVENT_KEYS
    assert not (_SUPERSEDED_FIELDS & set(plan.to_dict()))
    assert not (_SUPERSEDED_FIELDS & set(payload))
    assert not (_REMOVED_V6_EVENT_FIELDS & set(payload))


def test_target_fingerprint_and_carrier_command_use_exact_independent_domains() -> None:
    target = _target_facts()
    target_semantics = {key: target[key] for key in _TARGET_FINGERPRINT_KEYS}
    assert _independent_digest(target_semantics) == _TARGET_FINGERPRINT
    assert c2.fingerprint_target_definition(target) == _TARGET_FINGERPRINT

    plan = _plan(target_facts=dict(reversed(list(target.items()))))
    carrier_semantics = {
        "schema_version": "mastermind.sol_session_carrier_command/v1",
        "session_alias": "EXECUTIVE-CEO-CODEX-A",
        "target_definition_fingerprint": _TARGET_FINGERPRINT,
        "carrier_generation": 1,
    }
    assert plan.carrier_command_semantics() == carrier_semantics
    assert _independent_digest(carrier_semantics) == (
        "b84e2db087de11ea3b496b7b86b09070586742064b5b848b8e9098c9b5e3b9a1"
    )
    assert plan.carrier_job_created_command_id == _CARRIER_COMMAND


def test_target_projection_rejects_missing_extra_and_non_mapping_values() -> None:
    missing = _target_facts()
    del missing["workstream"]
    extra = _target_facts(target_enabled=False)

    for value in (missing, extra, None, [], "target"):
        with pytest.raises(c2.PlacementCommitmentError) as excinfo:
            _plan(target_facts=value)
        assert excinfo.value.code == "TARGET_DEFINITION_SHAPE_INVALID"


@pytest.mark.parametrize(
    ("field", "changed"),
    (
        ("session_alias", "EXECUTIVE-CEO-A"),
        ("target_seat", "coo"),
        ("reasoning_surface", "chatgpt-sol"),
        ("wake_transport", "chatgpt-gui"),
        ("allowed_transports", ["chatgpt-gui"]),
        ("workstream", "prophet"),
    ),
)
def test_generation_one_target_definition_drift_is_a_fixed_conflict(
    field: str,
    changed: object,
) -> None:
    accepted = _plan()
    with pytest.raises(c2.PlacementCommitmentError) as excinfo:
        _plan(target_facts=_target_facts(**{field: changed}))
    assert excinfo.value.code == "TARGET_DEFINITION_CONFLICT"
    assert accepted.carrier_generation == 1
    assert accepted.carrier_job_created_command_id == _CARRIER_COMMAND


@pytest.mark.parametrize(
    "allowed_transports",
    (
        ["codex-app-server", "chatgpt-gui"],
        ["chatgpt-gui", "codex-app-server"],
        ["codex-app-server", "codex-app-server"],
    ),
)
def test_allowed_transport_extra_order_or_duplicate_cannot_mint_a_carrier(
    allowed_transports: list[str],
) -> None:
    accepted = _plan()
    with pytest.raises(c2.PlacementCommitmentError) as excinfo:
        _plan(target_facts=_target_facts(allowed_transports=allowed_transports))
    assert excinfo.value.code == "TARGET_DEFINITION_CONFLICT"
    assert accepted.carrier_generation == 1
    assert accepted.carrier_job_created_command_id == _CARRIER_COMMAND


def test_target_conflict_precedes_any_alternate_carrier_command_derivation(
    monkeypatch,
) -> None:
    def unexpected_carrier_derivation(*args, **kwargs):
        pytest.fail("target drift reached carrier command derivation")

    monkeypatch.setattr(c2, "_carrier_command_id", unexpected_carrier_derivation)
    with pytest.raises(c2.PlacementCommitmentError) as excinfo:
        _plan(target_facts=_target_facts(reasoning_surface="chatgpt-sol"))
    assert excinfo.value.code == "TARGET_DEFINITION_CONFLICT"


def test_builder_public_surfaces_have_no_caller_carrier_or_handoff_channel() -> None:
    plan_parameters = inspect.signature(c2.build_commitment_plan).parameters
    event_parameters = inspect.signature(c2.build_commitment_event_payload).parameters
    replay_parameters = inspect.signature(
        c2.validate_commitment_event_payload
    ).parameters

    assert set(plan_parameters) == {
        "source_root_job_id",
        "expected_source_root_revision",
        "placement_selection",
        "validated_target_facts",
    }
    assert set(event_parameters) == {"plan", "validated_runtime_facts"}
    assert set(replay_parameters) == {"value", "plan", "validated_runtime_facts"}
    for parameters in (plan_parameters, event_parameters, replay_parameters):
        assert all(
            parameter.default is inspect.Parameter.empty
            for parameter in parameters.values()
        )
    assert not (_SUPERSEDED_FIELDS & set(plan_parameters))
    assert not {
        "placement_mode",
        "selected_worker_id",
        "selected_quota_class",
        "session_alias",
        "target_definition_fingerprint",
        "carrier_generation",
        "carrier_job_id",
        "committed_carrier_attempt_id",
        "carrier_job_created_command_id",
        "carrier_disposition",
    } & set(plan_parameters)


def test_selected_c1_document_derives_exact_stable_commitment_semantics() -> None:
    selection = _selection()
    plan = _plan(selection=selection)
    expected = {
        "schema_version": "mastermind.capacity_placement_commitment_command/v2",
        "source_root_job_id": "job-source-1",
        "responsibility_ref": "WS:CAP-C2",
        "placement_mode": "new_session_materialization",
        "selection_document_digest": _independent_digest(selection),
        "selection_evidence_digest": _independent_digest(selection["evidence"]),
        "selected_worker_id": "worker-1",
        "selected_quota_class": "standard",
        "committed_placement_snapshot_digest": _independent_digest(
            selection["selected"]
        ),
        "session_alias": "EXECUTIVE-CEO-CODEX-A",
        "target_definition_fingerprint": _TARGET_FINGERPRINT,
        "carrier_generation": 1,
        "carrier_job_created_command_id": _CARRIER_COMMAND,
    }
    expected_fingerprint = _independent_digest(expected)

    assert plan.command_semantics() == expected
    assert plan.command_fingerprint == expected_fingerprint
    assert plan.commitment_command_id == f"CAP-C2-{expected_fingerprint[:32]}"
    assert "expected_source_root_revision" not in plan.command_semantics()


def test_c1_wire_is_recomputed_through_the_only_selector_exactly_once(
    monkeypatch,
) -> None:
    selection = _selection()
    calls = 0
    protected_selector = c1.select_placement

    def observed_selector(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls > 1:
            pytest.fail("duplicate selector execution")
        return protected_selector(*args, **kwargs)

    monkeypatch.setattr(c1, "select_placement", observed_selector)
    assert _plan(selection=selection).selected_worker_id == "worker-1"
    assert calls == 1


def test_mapping_order_does_not_change_plan_or_identity() -> None:
    selection = _selection()
    reordered_selection = dict(reversed(list(selection.items())))
    reordered_target = dict(reversed(list(_target_facts().items())))
    assert _plan(selection=selection) == _plan(
        selection=reordered_selection,
        target_facts=reordered_target,
    )


def test_carrier_identity_converges_across_roots_while_commitment_does_not() -> None:
    first = _plan(source_root_job_id="job-source-1")
    second = _plan(source_root_job_id="job-source-2")

    assert first.carrier_job_created_command_id == _CARRIER_COMMAND
    assert second.carrier_job_created_command_id == _CARRIER_COMMAND
    assert first.carrier_command_semantics() == second.carrier_command_semantics()
    assert first.commitment_command_id != second.commitment_command_id
    assert first.command_fingerprint != second.command_fingerprint


def test_revision_is_nonidentity_precondition_but_is_retained_in_wire() -> None:
    first = _plan(revision=7)
    moved = _plan(revision=8)

    assert first.commitment_command_id == moved.commitment_command_id
    assert first.command_fingerprint == moved.command_fingerprint
    assert first.to_dict()["expected_source_root_revision"] == 7
    assert moved.to_dict()["expected_source_root_revision"] == 8


@pytest.mark.parametrize(
    ("mode", "disposition"),
    (
        (c1.PlacementMode.NEW_SESSION_MATERIALIZATION, "created"),
        (c1.PlacementMode.EXISTING_SESSION_REUSE, "reused"),
    ),
)
def test_new_and_reuse_have_exact_non_interchangeable_mapping(
    mode: c1.PlacementMode,
    disposition: str,
) -> None:
    plan = _plan(selection=_selection(mode=mode))
    facts = _runtime_facts(plan)
    payload = _event(plan, facts)

    assert plan.placement_mode == mode.value
    assert facts["carrier_disposition"] == disposition
    assert payload["carrier_disposition"] == disposition
    assert payload["placement_mode"] == mode.value


def test_new_and_reuse_produce_distinct_commitment_not_carrier_commands() -> None:
    new = _plan(selection=_selection(mode=c1.PlacementMode.NEW_SESSION_MATERIALIZATION))
    reuse = _plan(selection=_selection(mode=c1.PlacementMode.EXISTING_SESSION_REUSE))

    assert new.carrier_job_created_command_id == reuse.carrier_job_created_command_id
    assert new.commitment_command_id != reuse.commitment_command_id


def test_plan_owns_private_immutable_exact_snapshot_but_wire_only_has_digest() -> None:
    selection = _selection()
    plan = _plan(selection=selection)
    expected_snapshot = {
        "schema_version": "mastermind.executive_placement_snapshot/v1",
        "worker_id": "worker-1",
        "quota_class": "standard",
        "provider": "codex",
        "account_label": "codex-ceo-a",
        "observed_at_ms": 1_788_400_000_000,
    }

    selection["selected"]["worker_id"] = "worker-mutated-after-build"

    assert dict(plan.committed_placement_snapshot) == expected_snapshot
    assert plan.committed_placement_snapshot_digest == _independent_digest(
        expected_snapshot
    )
    assert "committed_placement_snapshot" not in plan.to_dict()
    with pytest.raises(TypeError):
        plan.committed_placement_snapshot["worker_id"] = "worker-2"  # type: ignore[index]


@pytest.mark.parametrize(
    ("mutator", "accepted_codes"),
    (
        (
            lambda value: value.update(
                state="waiting_capacity", selected=None, selected_mode=None
            ),
            {"PLACEMENT_SELECTION_INVALID", "PLACEMENT_SELECTION_NOT_SELECTED"},
        ),
        (
            lambda value: value.update(selection_is_commitment=True),
            {
                "PLACEMENT_SELECTION_INVALID",
                "PLACEMENT_SELECTION_ALREADY_COMMITTED",
            },
        ),
        (
            lambda value: value.update(selected_mode="future_mode"),
            {"PLACEMENT_SELECTION_INVALID", "PLACEMENT_MODE_INVALID"},
        ),
    ),
)
def test_non_selected_committing_or_unknown_mode_c1_is_refused(
    mutator,
    accepted_codes: set[str],
) -> None:
    selection = _selection()
    mutator(selection)
    with pytest.raises(c2.PlacementCommitmentError) as excinfo:
        _plan(selection=selection)
    assert excinfo.value.code in accepted_codes


def test_plan_is_builder_only_and_frozen_against_mode_or_carrier_forgery() -> None:
    assert not inspect.signature(c2.PlacementCommitmentPlan).parameters
    assert "_from_validated" not in vars(c2.PlacementCommitmentPlan)
    with pytest.raises(TypeError):
        c2.PlacementCommitmentPlan(
            placement_mode="existing_session_reuse",
        )

    plan = _plan()
    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.placement_mode = "existing_session_reuse"  # type: ignore[misc]
    with pytest.raises(TypeError):
        dataclasses.replace(
            plan,
            placement_mode="existing_session_reuse",
            command_fingerprint="c" * 64,
            commitment_command_id="CAP-C2-" + "c" * 32,
        )


def test_runtime_facts_are_one_exact_closed_trusted_projection() -> None:
    plan = _plan()
    facts = _runtime_facts(plan)
    assert set(facts) == _RUNTIME_FACT_KEYS
    assert c2.RUNTIME_FACT_KEYS == frozenset(_RUNTIME_FACT_KEYS)

    missing = dict(facts)
    del missing["carrier_job_id"]
    extra = {**facts, "runtime_binding_id": "bind-forged"}
    for value in (missing, extra, None, [], "receipt"):
        with pytest.raises(c2.PlacementCommitmentError) as excinfo:
            _event(plan, value)
        assert excinfo.value.code == "RUNTIME_FACTS_SHAPE_INVALID"


def test_event_binds_source_and_carrier_receipts_without_duplicate_placement() -> None:
    plan = _plan()
    payload = _event(plan)

    assert payload == {
        "schema_version": "mastermind.capacity_placement_commitment/v2",
        "source_root_job_id": "job-source-1",
        "source_job_created_command_id": "CEO-V2-ROOT-CREATED-1",
        "source_authority_fingerprint": _SOURCE_AUTHORITY_FINGERPRINT,
        "responsibility_ref": "WS:CAP-C2",
        "placement_mode": "new_session_materialization",
        "selection_document_digest": plan.selection_document_digest,
        "selection_evidence_digest": plan.selection_evidence_digest,
        "selected_worker_id": "worker-1",
        "selected_quota_class": "standard",
        "committed_placement_snapshot_digest": (
            plan.committed_placement_snapshot_digest
        ),
        "session_alias": "EXECUTIVE-CEO-CODEX-A",
        "target_definition_fingerprint": _TARGET_FINGERPRINT,
        "carrier_generation": 1,
        "carrier_job_id": "job-ceo-carrier-1",
        "carrier_job_created_command_id": _CARRIER_COMMAND,
        "carrier_authority_fingerprint": _CARRIER_AUTHORITY_FINGERPRINT,
        "carrier_disposition": "created",
        "committed_carrier_attempt_id": "attempt-ceo-carrier-1",
        "commitment_command_id": plan.commitment_command_id,
        "command_fingerprint": plan.command_fingerprint,
        "commitment_evidence_digest": payload["commitment_evidence_digest"],
    }
    evidence = {key: payload[key] for key in _EVENT_EVIDENCE_KEYS}
    assert payload["commitment_evidence_digest"] == _independent_digest(evidence)
    assert "expected_source_root_revision" not in payload
    assert not {
        "carrier_worker_id",
        "carrier_quota_class",
        "carrier_placement_snapshot_digest",
    } & set(payload)


@pytest.mark.parametrize(
    ("field", "changed"),
    (
        ("source_root_job_id", "job-source-2"),
        ("source_root_revision", 8),
        ("session_alias", "EXECUTIVE-CEO-A"),
        ("target_definition_fingerprint", "c" * 64),
        ("carrier_generation", 2),
        ("carrier_job_created_command_id", "SOL-CARRIER-" + "d" * 32),
        ("carrier_disposition", "reused"),
        ("carrier_worker_id", "worker-2"),
        ("carrier_quota_class", "priority"),
        ("carrier_placement_snapshot_digest", "e" * 64),
    ),
)
def test_event_builder_refuses_runtime_facts_that_conflict_with_plan(
    field: str,
    changed: object,
) -> None:
    plan = _plan()
    with pytest.raises(c2.PlacementCommitmentError) as excinfo:
        _event(plan, _runtime_facts(plan, **{field: changed}))
    assert excinfo.value.code == "RUNTIME_FACTS_CONFLICT"


@pytest.mark.parametrize(
    "mode",
    (
        c1.PlacementMode.NEW_SESSION_MATERIALIZATION,
        c1.PlacementMode.EXISTING_SESSION_REUSE,
    ),
)
@pytest.mark.parametrize(
    "collapsed_identity",
    ("job_id", "job_created_command_id"),
)
def test_source_responsibility_and_alias_carrier_must_be_separate_jobs(
    mode: c1.PlacementMode,
    collapsed_identity: str,
) -> None:
    plan = _plan(selection=_selection(mode=mode))
    historical = _event(plan)
    facts = _runtime_facts(plan)
    if collapsed_identity == "job_id":
        facts["carrier_job_id"] = plan.source_root_job_id
    else:
        facts["source_job_created_command_id"] = plan.carrier_job_created_command_id

    with pytest.raises(c2.PlacementCommitmentError) as excinfo:
        _event(plan, facts)
    assert excinfo.value.code == "RUNTIME_FACTS_CONFLICT"

    with pytest.raises(c2.PlacementCommitmentError) as excinfo:
        _validate(historical, plan=plan, runtime_facts=facts)
    assert excinfo.value.code == "COMMITMENT_EVENT_REPLAY_CONFLICT"


def test_identical_replay_rebuilds_byte_identical_event_from_current_truth() -> None:
    plan = _plan()
    facts = _runtime_facts(plan)
    payload = _event(plan, facts)
    assert _validate(payload, plan=plan, runtime_facts=facts) == payload


def test_revision_movement_changes_precondition_but_not_immutable_event_bytes() -> None:
    accepted = _plan(revision=7)
    accepted_facts = _runtime_facts(accepted)
    historical = _event(accepted, accepted_facts)
    current = _plan(revision=8)
    current_facts = _runtime_facts(current)
    current_event = _event(current, current_facts)

    assert current.commitment_command_id == accepted.commitment_command_id
    assert current.command_fingerprint == accepted.command_fingerprint
    assert json.dumps(current_event, sort_keys=True, separators=(",", ":")) == (
        json.dumps(historical, sort_keys=True, separators=(",", ":"))
    )
    assert (
        _validate(historical, plan=current, runtime_facts=current_facts) == historical
    )


@pytest.mark.parametrize(("plan_revision", "runtime_revision"), ((8, 7), (7, 8)))
def test_stale_runtime_revision_still_refuses_at_private_boundary(
    plan_revision: int,
    runtime_revision: int,
) -> None:
    current = _plan(revision=plan_revision)
    historical = _event(current)
    stale_facts = _runtime_facts(current, source_root_revision=runtime_revision)
    with pytest.raises(c2.PlacementCommitmentError) as excinfo:
        _event(current, stale_facts)
    assert excinfo.value.code == "RUNTIME_FACTS_CONFLICT"

    with pytest.raises(c2.PlacementCommitmentError) as excinfo:
        _validate(historical, plan=current, runtime_facts=stale_facts)
    assert excinfo.value.code == "COMMITMENT_EVENT_REPLAY_CONFLICT"


@pytest.mark.parametrize(
    ("field", "changed"),
    (
        ("source_root_job_id", "job-source-2"),
        ("source_root_revision", 8),
        ("source_job_created_command_id", "CEO-V2-ROOT-CREATED-2"),
        ("source_authority_fingerprint", "c" * 64),
        ("session_alias", "EXECUTIVE-CEO-A"),
        ("target_definition_fingerprint", "c" * 64),
        ("carrier_generation", 2),
        ("carrier_job_id", "job-ceo-carrier-2"),
        ("carrier_job_created_command_id", "SOL-CARRIER-" + "d" * 32),
        ("carrier_authority_fingerprint", "c" * 64),
        ("carrier_disposition", "reused"),
        ("committed_carrier_attempt_id", "attempt-ceo-carrier-2"),
        ("carrier_worker_id", "worker-2"),
        ("carrier_quota_class", "priority"),
        ("carrier_placement_snapshot_digest", "e" * 64),
    ),
)
def test_replay_refuses_each_current_runtime_drift(
    field: str,
    changed: object,
) -> None:
    plan = _plan()
    historical = _event(plan)
    with pytest.raises(c2.PlacementCommitmentError) as excinfo:
        _validate(
            historical,
            plan=plan,
            runtime_facts=_runtime_facts(plan, **{field: changed}),
        )
    assert excinfo.value.code == "COMMITMENT_EVENT_REPLAY_CONFLICT"


@pytest.mark.parametrize(
    ("field", "changed"),
    (
        ("source_root_job_id", "job-source-2"),
        ("source_job_created_command_id", "CEO-V2-ROOT-CREATED-2"),
        ("source_authority_fingerprint", "c" * 64),
        ("placement_mode", "existing_session_reuse"),
        ("selected_worker_id", "worker-2"),
        ("selected_quota_class", "priority"),
        ("committed_placement_snapshot_digest", "e" * 64),
        ("session_alias", "EXECUTIVE-CEO-A"),
        ("target_definition_fingerprint", "c" * 64),
        ("carrier_generation", 2),
        ("carrier_job_id", "job-ceo-carrier-2"),
        ("carrier_job_created_command_id", "SOL-CARRIER-" + "d" * 32),
        ("carrier_authority_fingerprint", "c" * 64),
        ("carrier_disposition", "reused"),
        ("committed_carrier_attempt_id", "attempt-ceo-carrier-2"),
    ),
)
def test_forged_event_fact_cannot_self_authenticate_after_digest_rewrite(
    field: str,
    changed: object,
) -> None:
    payload = _event()
    payload[field] = changed
    evidence = {key: payload[key] for key in _EVENT_EVIDENCE_KEYS}
    payload["commitment_evidence_digest"] = _independent_digest(evidence)

    with pytest.raises(c2.PlacementCommitmentError) as excinfo:
        _validate(payload)
    assert excinfo.value.code == "COMMITMENT_EVENT_REPLAY_CONFLICT"


def test_forged_target_cluster_with_all_hashes_rewritten_still_conflicts() -> None:
    payload = _event()
    forged_target = "c" * 64
    carrier_semantics = {
        "schema_version": "mastermind.sol_session_carrier_command/v1",
        "session_alias": "EXECUTIVE-CEO-CODEX-A",
        "target_definition_fingerprint": forged_target,
        "carrier_generation": 1,
    }
    payload["target_definition_fingerprint"] = forged_target
    payload["carrier_job_created_command_id"] = (
        f"SOL-CARRIER-{_independent_digest(carrier_semantics)[:32]}"
    )
    command_semantics = {key: payload[key] for key in _STABLE_SEMANTIC_KEYS}
    command_semantics["schema_version"] = (
        "mastermind.capacity_placement_commitment_command/v2"
    )
    payload["command_fingerprint"] = _independent_digest(command_semantics)
    payload["commitment_command_id"] = f"CAP-C2-{payload['command_fingerprint'][:32]}"
    evidence = {key: payload[key] for key in _EVENT_EVIDENCE_KEYS}
    payload["commitment_evidence_digest"] = _independent_digest(evidence)

    with pytest.raises(c2.PlacementCommitmentError) as excinfo:
        _validate(payload)
    assert excinfo.value.code == "COMMITMENT_EVENT_REPLAY_CONFLICT"


@pytest.mark.parametrize("field", tuple(sorted(_FORBIDDEN_EVENT_FIELDS)))
def test_forbidden_event_field_is_refused_before_generic_shape(field: str) -> None:
    payload = _event()
    payload[field] = "forged"
    with pytest.raises(c2.PlacementCommitmentError) as excinfo:
        _validate(payload)
    assert excinfo.value.code == "COMMITMENT_EVENT_FORBIDDEN_FIELD"


@pytest.mark.parametrize(
    ("current_name", "superseded_name"),
    (
        ("source_job_created_command_id", "source_root_job_created_command_id"),
        ("source_authority_fingerprint", "source_root_authority_fingerprint"),
        ("committed_carrier_attempt_id", "carrier_attempt_id"),
    ),
)
def test_runtime_projection_rejects_each_superseded_fact_name(
    current_name: str,
    superseded_name: str,
) -> None:
    facts = _runtime_facts()
    facts[superseded_name] = facts.pop(current_name)
    with pytest.raises(c2.PlacementCommitmentError) as excinfo:
        _event(runtime_facts=facts)
    assert excinfo.value.code == "RUNTIME_FACTS_SHAPE_INVALID"


@pytest.mark.parametrize(
    ("current_name", "superseded_name"),
    (
        ("source_job_created_command_id", "source_root_job_created_command_id"),
        ("source_authority_fingerprint", "source_root_authority_fingerprint"),
        ("committed_carrier_attempt_id", "carrier_attempt_id"),
    ),
)
def test_event_rejects_each_superseded_fact_name(
    current_name: str,
    superseded_name: str,
) -> None:
    payload = _event()
    payload[superseded_name] = payload.pop(current_name)
    with pytest.raises(c2.PlacementCommitmentError) as excinfo:
        _validate(payload)
    assert excinfo.value.code == "COMMITMENT_EVENT_SHAPE_INVALID"


def test_event_rejects_removed_optimistic_revision_as_unknown_wire_field() -> None:
    payload = {**_event(), "expected_source_root_revision": 7}
    with pytest.raises(c2.PlacementCommitmentError) as excinfo:
        _validate(payload)
    assert excinfo.value.code == "COMMITMENT_EVENT_SHAPE_INVALID"


def test_v1_payload_is_not_accepted_or_upgraded() -> None:
    payload = _event()
    payload["schema_version"] = "mastermind.capacity_placement_commitment/v1"
    with pytest.raises(c2.PlacementCommitmentError) as excinfo:
        _validate(payload)
    assert excinfo.value.code == "COMMITMENT_EVENT_SCHEMA_INVALID"


def test_event_missing_or_unknown_field_is_refused() -> None:
    missing = _event()
    del missing["carrier_job_id"]
    unknown = {**_event(), "unknown": "field"}
    for payload in (missing, unknown):
        with pytest.raises(c2.PlacementCommitmentError) as excinfo:
            _validate(payload)
        assert excinfo.value.code == "COMMITMENT_EVENT_SHAPE_INVALID"


def test_runtime_and_secret_identity_do_not_leak_into_plan_or_event() -> None:
    plan = _plan()
    payload = _event(plan)
    encoded = json.dumps(
        {"plan": plan.to_dict(), "event": payload},
        sort_keys=True,
    )

    assert c2.FORBIDDEN_EVENT_KEYS == frozenset(_FORBIDDEN_EVENT_FIELDS)
    assert not (_FORBIDDEN_EVENT_FIELDS & set(payload))
    assert "codex-ceo-a" not in encoded
    assert '"provider"' not in encoded
    assert "provider_session" not in encoded
    assert "runtime_binding" not in encoded


def test_aggregation_handoff_cannot_resurrect_through_public_contract() -> None:
    plan = _plan()
    payload = _event(plan)
    runtime_facts = _runtime_facts(plan)
    public_text = json.dumps(
        {
            "plan": plan.to_dict(),
            "event": payload,
            "runtime_fact_keys": sorted(runtime_facts),
            "plan_signature": sorted(
                inspect.signature(c2.build_commitment_plan).parameters
            ),
            "event_signature": sorted(
                inspect.signature(c2.build_commitment_event_payload).parameters
            ),
            "replay_signature": sorted(
                inspect.signature(c2.validate_commitment_event_payload).parameters
            ),
        },
        sort_keys=True,
    )
    for field in (
        "aggregation_handoff_command_id",
        "aggregation_handoff_digest",
        "plan_attempt_id",
        "plan_digest",
    ):
        assert field not in public_text
