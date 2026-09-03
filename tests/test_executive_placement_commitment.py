from __future__ import annotations

import dataclasses
import inspect
import json
from pathlib import Path

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


def _source(owner: SourceOwner, ref: str) -> SourceRef:
    return SourceRef(
        owner=owner,
        ref=ref,
        observed_at="2026-09-03T00:00:00Z",
        freshness=Freshness.CURRENT,
    )


def _selection(*, worker_id: str = "worker-1") -> dict:
    responsibility = ResponsibilityFact(
        responsibility_ref="WS:CAP-C2",
        title="Atomic placement commitment",
        accountable_seat=Seat.CEO,
        state="waiting_capacity",
        root_job_id=None,
        source=_source(SourceOwner.AGENT_OS, "agentos/workstreams/WS-CAP-C2.md"),
    )
    demand = c1.PlacementDemand(
        required_capabilities=frozenset({"executive"}),
        quota_class="standard",
        provider="codex",
        allowed_modes=frozenset({c1.PlacementMode.NEW_SESSION_MATERIALIZATION}),
    )
    candidate = c1.PlacementCandidateFact(
        worker_id=worker_id,
        provider="codex",
        account_label="codex-ceo-a",
        quota_class="standard",
        capabilities=frozenset({"executive"}),
        observed_at_ms=1_788_400_000_000,
        occupancy=c1.OccupancyState.FREE,
        occupancy_source=_source(SourceOwner.RUNTIME_BINDING, f"binding-{worker_id}"),
        capacity_state=CapacityState.AVAILABLE,
        capacity_source=_source(SourceOwner.CAPACITY, f"capacity-{worker_id}"),
        host_source_closure_proven=True,
        closure_source=_source(SourceOwner.CAPACITY, f"closure-{worker_id}"),
        effect_state=EffectState.NONE,
        mode=c1.PlacementMode.NEW_SESSION_MATERIALIZATION,
        creation_surface_accessible=True,
        session_creation_allowed=True,
    )
    decision = c1.select_placement(
        responsibility=responsibility,
        demand=demand,
        candidates=(candidate,),
    )
    assert decision.state is c1.SelectionState.SELECTED
    return decision.to_dict()


def _plan(*, selection: dict | None = None, revision: int = 0) -> c2.PlacementCommitmentPlan:
    return c2.build_commitment_plan(
        root_job_id="job-root-1",
        expected_job_revision=revision,
        placement_selection=selection or _selection(),
    )


def _event(plan: c2.PlacementCommitmentPlan | None = None) -> dict:
    return c2.build_commitment_event_payload(
        plan=plan or _plan(),
        committed_attempt_id="attempt-1",
        responsibility_job_created_command_id="CEO-ROOT-1",
        responsibility_authority_fingerprint="a" * 64,
    )


def test_selected_c1_document_derives_one_deterministic_commitment_plan() -> None:
    selection = _selection()
    first = _plan(selection=selection)
    second = _plan(selection=json.loads(json.dumps(selection)))

    assert first == second
    assert first.schema_version == c2.COMMAND_SCHEMA
    assert first.root_job_id == "job-root-1"
    assert first.responsibility_ref == "WS:CAP-C2"
    assert first.selected_worker_id == "worker-1"
    assert first.selected_quota_class == "standard"
    assert first.commitment_command_id == f"CAP-C2-{first.command_fingerprint[:32]}"
    assert set(first.to_dict()) == {
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


def test_mapping_order_does_not_change_commitment_identity() -> None:
    selection = _selection()
    reordered = dict(reversed(list(selection.items())))
    assert _plan(selection=selection) == _plan(selection=reordered)


def test_selection_content_and_expected_revision_are_bound_into_command() -> None:
    original = _plan()
    changed_worker = _plan(selection=_selection(worker_id="worker-2"))
    changed_revision = _plan(revision=1)

    assert original.commitment_command_id != changed_worker.commitment_command_id
    assert original.command_fingerprint != changed_worker.command_fingerprint
    assert original.commitment_command_id != changed_revision.commitment_command_id


def test_non_selected_c1_outcome_is_refused_before_a_commitment_plan() -> None:
    selection = _selection()
    selection["state"] = "waiting_capacity"
    selection["selected"] = None
    selection["selected_mode"] = None
    with pytest.raises(c2.PlacementCommitmentError) as excinfo:
        _plan(selection=selection)
    assert excinfo.value.code in {
        "PLACEMENT_SELECTION_INVALID",
        "PLACEMENT_SELECTION_NOT_SELECTED",
    }


def test_c1_wire_must_remain_explicitly_non_committing() -> None:
    selection = _selection()
    selection["selection_is_commitment"] = True
    with pytest.raises(c2.PlacementCommitmentError) as excinfo:
        _plan(selection=selection)
    assert excinfo.value.code in {
        "PLACEMENT_SELECTION_INVALID",
        "PLACEMENT_SELECTION_ALREADY_COMMITTED",
    }


def test_event_payload_is_closed_secret_safe_and_contains_no_runtime_binding() -> None:
    payload = _event()

    assert payload["schema_version"] == c2.COMMITMENT_SCHEMA
    assert payload["root_job_id"] == "job-root-1"
    assert payload["selected_worker_id"] == "worker-1"
    assert payload["selected_quota_class"] == "standard"
    assert payload["committed_attempt_id"] == "attempt-1"
    assert not (set(payload) & c2.FORBIDDEN_EVENT_KEYS)
    assert "codex-ceo-a" not in json.dumps(payload, sort_keys=True)
    assert "provider_session" not in json.dumps(payload, sort_keys=True)


def test_event_replay_revalidates_the_current_plan_and_attempt() -> None:
    plan = _plan()
    payload = _event(plan)
    assert c2.validate_commitment_event_payload(
        payload, plan=plan, expected_attempt_id="attempt-1"
    ) == payload

    with pytest.raises(c2.PlacementCommitmentError) as excinfo:
        c2.validate_commitment_event_payload(
            payload, plan=plan, expected_attempt_id="attempt-2"
        )
    assert excinfo.value.code == "COMMITTED_ATTEMPT_MISMATCH"


def test_changed_replay_payload_conflicts_instead_of_becoming_a_second_event() -> None:
    plan = _plan()
    payload = _event(plan)
    payload["selected_worker_id"] = "worker-2"
    with pytest.raises(c2.PlacementCommitmentError) as excinfo:
        c2.validate_commitment_event_payload(
            payload, plan=plan, expected_attempt_id="attempt-1"
        )
    assert excinfo.value.code == "COMMITMENT_EVENT_REPLAY_CONFLICT"


def test_event_evidence_digest_binds_every_receipt_fact() -> None:
    plan = _plan()
    payload = _event(plan)
    tampered = dict(payload)
    tampered["responsibility_job_created_command_id"] = "CEO-ROOT-2"
    with pytest.raises(c2.PlacementCommitmentError) as excinfo:
        c2.validate_commitment_event_payload(
            tampered, plan=plan, expected_attempt_id="attempt-1"
        )
    assert excinfo.value.code == "COMMITMENT_EVENT_REPLAY_CONFLICT"


def test_plan_is_frozen_and_contains_no_original_mutable_selection() -> None:
    selection = _selection()
    plan = _plan(selection=selection)
    selection["selected"]["worker_id"] = "worker-mutated-after-build"

    assert plan.selected_worker_id == "worker-1"
    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.selected_worker_id = "worker-2"  # type: ignore[misc]


def test_caller_cannot_supply_command_id_or_attempt_to_plan_builder() -> None:
    parameters = inspect.signature(c2.build_commitment_plan).parameters
    assert set(parameters) == {
        "root_job_id",
        "expected_job_revision",
        "placement_selection",
    }
    assert "command_id" not in parameters
    assert "attempt_id" not in parameters
    assert "runtime_binding" not in parameters


def test_invalid_identity_and_revision_fail_with_fixed_codes() -> None:
    selection = _selection()
    with pytest.raises(c2.PlacementCommitmentError) as root_error:
        c2.build_commitment_plan(
            root_job_id="../secret",
            expected_job_revision=0,
            placement_selection=selection,
        )
    assert root_error.value.code == "ROOT_JOB_ID_INVALID"

    with pytest.raises(c2.PlacementCommitmentError) as revision_error:
        c2.build_commitment_plan(
            root_job_id="job-root-1",
            expected_job_revision=True,
            placement_selection=selection,
        )
    assert revision_error.value.code == "EXPECTED_JOB_REVISION_INVALID"


def test_module_is_pure_and_does_not_import_runtime_provider_or_transport() -> None:
    source = Path(c2.__file__).read_text(encoding="utf-8")
    forbidden = (
        "sqlite3",
        "executive_service",
        "runtime_binding",
        "slack",
        "provider_session",
        "subprocess",
        "socket",
    )
    for token in forbidden:
        assert f"import {token}" not in source
        assert f"from {token}" not in source


def test_wire_serialization_is_canonical_and_deterministic() -> None:
    plan = _plan()
    first = json.dumps(plan.to_dict(), sort_keys=True, separators=(",", ":"))
    second = json.dumps(_plan().to_dict(), sort_keys=True, separators=(",", ":"))
    assert first == second
    assert "RuntimeBinding" not in first
    assert "account_label" not in first
