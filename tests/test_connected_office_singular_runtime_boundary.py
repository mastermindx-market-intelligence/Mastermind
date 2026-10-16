"""Executable boundary evidence, not a fleet implementation or a new read API.

The connected-office inventory must preserve, not weaken, Steward's singular
current-operator query. These synthetic fixtures exercise the real query. A
plural lane consumer belongs to a separately admitted owner-native vertical.
"""
from dataclasses import replace
import json

import pytest

from control_plane.executive_steward import (
    CapacityState,
    EffectState,
    ExecutiveStewardSnapshot,
    Freshness,
    QueryStatus,
    ResponsibilityFact,
    RuntimeFact,
    Seat,
    SourceOwner,
    SourceRef,
)

WORK = "WS:CHAIRMAN-CONTROL-ROOM"
ROOT = "JOB-office-synthetic-root"
OBSERVED = "2026-09-06T12:00:00Z"


def _source(owner: SourceOwner, key: str) -> SourceRef:
    # CURRENT is fixture input, not a wall-clock or installed-source assertion.
    return SourceRef(owner, f"synthetic:{key}", OBSERVED, Freshness.CURRENT)


def _responsibility() -> ResponsibilityFact:
    return ResponsibilityFact(
        responsibility_ref=WORK,
        title="Synthetic connected-office boundary fixture",
        accountable_seat=Seat.CEO,
        state="active",
        root_job_id=ROOT,
        source=_source(SourceOwner.AGENT_OS, "responsibility"),
    )


def _lane(label: str) -> RuntimeFact:
    return RuntimeFact(
        responsibility_ref=WORK,
        root_job_id=ROOT,
        seat=Seat.WORKER,
        attempt_id=f"synthetic-attempt-{label}",
        worker_id=f"synthetic-worker-{label}",
        status="RUNNING",
        session_alias=f"synthetic-session-{label}",
        runtime_binding_id=f"synthetic-binding-{label}",
        binding_generation=1,
        continuation_state="synthetic-bound",
        effect_state=EffectState.NONE,
        capacity_state=CapacityState.UNKNOWN,
        previous_attempt_id=None,
        movement_reason_code=None,
        executive_source=_source(SourceOwner.EXECUTIVE_OS, f"executive-{label}"),
        binding_source=_source(SourceOwner.RUNTIME_BINDING, f"binding-{label}"),
        reasoning_surface="codex",
        account_label=f"synthetic-account-{label}",
        host_ref="synthetic-host",
        provider_session_id_present=True,
    )


def _snapshot(*lanes: RuntimeFact) -> ExecutiveStewardSnapshot:
    return ExecutiveStewardSnapshot(
        responsibilities=(_responsibility(),), runtimes=tuple(lanes)
    )


def _codes(result) -> set[str]:
    return {issue.code for issue in result.issues}


def test_single_exact_current_worker_is_the_positive_control():
    lane = _lane("a")
    result = _snapshot(lane).get_current_runtime(WORK, Seat.WORKER)
    assert result.status is QueryStatus.OK
    assert result.data == lane
    assert not result.issues


@pytest.mark.parametrize("reverse", [False, True])
def test_parallel_workers_are_not_a_singular_current_operator(reverse):
    lanes = (_lane("a"), _lane("b"))
    if reverse:
        lanes = tuple(reversed(lanes))
    snapshot = _snapshot(*lanes)
    result = snapshot.get_current_runtime(WORK, Seat.WORKER)
    assert result.status is QueryStatus.REFUSED
    assert result.data is None
    assert "ambiguous_runtime_join" in _codes(result)
    assert len(snapshot.runtimes) == 2  # evidence exists; query is not an inventory


def test_larger_binding_generation_does_not_elect_a_writer():
    previous = _lane("a")
    newer = replace(previous, runtime_binding_id="synthetic-binding-next", binding_generation=2)
    result = _snapshot(previous, newer).get_current_runtime(WORK, Seat.WORKER)
    assert result.status is QueryStatus.REFUSED
    assert result.data is None
    assert "ambiguous_runtime_join" in _codes(result)


def test_different_account_labels_do_not_resolve_same_seat_cardinality():
    first = _lane("a")
    second = replace(_lane("b"), account_label="synthetic-other-provider-account")
    result = _snapshot(first, second).get_current_runtime(WORK, Seat.WORKER)
    assert result.status is QueryStatus.REFUSED
    assert "ambiguous_runtime_join" in _codes(result)


def test_effect_unknown_evidence_remains_but_cannot_be_asserted_as_operator():
    lane = replace(_lane("a"), effect_state=EffectState.EFFECT_UNKNOWN)
    snapshot = _snapshot(lane)
    result = snapshot.get_current_runtime(WORK, Seat.WORKER)
    assert result.status is QueryStatus.REFUSED
    assert result.data is None
    assert "reconciliation_required" in _codes(result)
    assert snapshot.runtimes == (lane,)


@pytest.mark.parametrize("source_name", ["executive_source", "binding_source"])
def test_stale_evidence_is_not_refreshed_by_querying_it(source_name):
    lane = _lane("a")
    stale = replace(getattr(lane, source_name), freshness=Freshness.STALE)
    lane = replace(lane, **{source_name: stale})
    result = _snapshot(lane).get_current_runtime(WORK, Seat.WORKER)
    assert result.status is QueryStatus.DEGRADED
    assert result.data is None
    assert "stale_runtime_join" in _codes(result)
    assert getattr(lane, source_name).observed_at == OBSERVED


def test_mismatched_root_is_not_folded_into_office_inventory_identity():
    lane = replace(_lane("a"), root_job_id="JOB-synthetic-foreign-root")
    result = _snapshot(lane).get_current_runtime(WORK, Seat.WORKER)
    assert result.status is QueryStatus.REFUSED
    assert result.data is None
    assert "runtime_root_mismatch" in _codes(result)


def test_ceo_and_worker_seats_remain_separate():
    worker = _lane("a")
    ceo = replace(_lane("b"), seat=Seat.CEO)
    snapshot = _snapshot(worker, ceo)
    assert snapshot.get_current_runtime(WORK, Seat.WORKER).data == worker
    assert snapshot.get_current_runtime(WORK, Seat.CEO).data == ceo


def test_absent_runtime_is_unknown_not_idle_capacity():
    result = _snapshot().get_current_runtime(WORK, Seat.WORKER)
    assert result.status is QueryStatus.UNKNOWN
    assert result.data is None
    assert "runtime_unknown" in _codes(result)


def test_inventory_cardinality_does_not_depend_on_input_order():
    first = _snapshot(_lane("a"), _lane("b")).get_current_runtime(WORK, Seat.WORKER)
    second = _snapshot(_lane("b"), _lane("a")).get_current_runtime(WORK, Seat.WORKER)
    assert first.to_dict() == second.to_dict()


if __name__ == "__main__":
    positive = _snapshot(_lane("a")).get_current_runtime(WORK, Seat.WORKER)
    parallel = _snapshot(_lane("a"), _lane("b")).get_current_runtime(WORK, Seat.WORKER)
    print(json.dumps({
        "proof_class": "SYNTHETIC_CURRENT_SOURCE_BOUNDARY_ONLY",
        "single_worker_status": positive.status.value,
        "parallel_worker_status": parallel.status.value,
        "parallel_worker_issue_codes": sorted(_codes(parallel)),
        "parallel_worker_data_is_null": parallel.data is None,
        "full_office_proven": False,
    }, sort_keys=True))
