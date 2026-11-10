"""Finite original admission/placement composition, using the actual Runtime."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from control_plane.child_request_execution_composition import (
    compose_child_execution, placement_command_id,
)
from control_plane.executive_runtime import StateConflict
from tests.test_mmos_admission_to_t3_native_e2e import (
    _runtime, _handoff_request, _t3_spec,
)


def test_wait_admits_no_placement_or_ready_handle(tmp_path, monkeypatch):
    runtime, _ = _runtime(tmp_path)
    monkeypatch.setenv("MMOS_CHILD_ROOT_READY_LIMIT", "1")
    runtime.jobs.admit_child_execution_request(_handoff_request("occupant"))
    request = _handoff_request("waiting")
    before = [job.job_id for job in runtime.jobs.list_jobs()]
    result = compose_child_execution(runtime, request=request, spec=_t3_spec(request))
    assert result.admission.state == "WAIT"
    assert result.admission.wait_reason == "CHILD_QUEUE_ROOT_READY_FULL"
    assert result.placement_job is None
    assert result.placement_created is result.ready_to_claim is False
    assert [job.job_id for job in runtime.jobs.list_jobs()] == before
    assert runtime.store.get_event_by_command_id(placement_command_id(request)) is None


def test_spliced_request_refuses_before_either_admission_or_placement(tmp_path):
    runtime, _ = _runtime(tmp_path)
    request = _handoff_request("original")
    foreign = _handoff_request("foreign")
    with pytest.raises(StateConflict, match="admitted request"):
        compose_child_execution(runtime, request=request, spec=_t3_spec(foreign))
    assert runtime.jobs.list_jobs() == []


@pytest.mark.parametrize("drift", ["route", "registry", "quota", "root_cap", "branch", "policy"])
def test_same_admission_cannot_silently_reconcile_changed_placement(tmp_path, drift):
    runtime, _ = _runtime(tmp_path)
    request = _handoff_request("original")
    first = compose_child_execution(runtime, request=request, spec=_t3_spec(request), branch="original")
    changed = _t3_spec(request)
    branch = "original"
    if drift == "route":
        changed["route"]["adapter_id"] = "codex-cli"
    elif drift == "registry":
        changed["registry_revision"] = "new-registry"
    elif drift == "quota":
        changed["shared_quota_resource_refs"] = ["codex:other"]
    elif drift == "root_cap":
        changed["root_concurrency_limit"] = 2
    elif drift == "branch":
        branch = "replacement"
    elif drift == "policy":
        changed["authority_policy_hash"] = "a" * 64
    with pytest.raises(StateConflict, match="placement.*changed"):
        compose_child_execution(runtime, request=request, spec=changed, branch=branch)
    jobs = runtime.jobs.list_jobs()
    assert len(jobs) == 2
    assert runtime.jobs.get_job(first.placement_job.job_id) == first.placement_job


def test_semantically_identical_normalized_replay_uses_original_job(tmp_path):
    runtime, _ = _runtime(tmp_path)
    request = _handoff_request("original")
    first = compose_child_execution(runtime, request=request, spec=_t3_spec(request))
    replay = compose_child_execution(runtime, request=request,
        spec=first.placement_job.constraints["child_placement"])
    assert replay.admission.state == "REPLAY"
    assert replay.placement_job == first.placement_job
    assert replay.placement_created is False
    assert len(runtime.jobs.list_jobs()) == 2


def test_concurrent_different_placement_has_one_winner_and_one_conflict(tmp_path):
    runtime, _ = _runtime(tmp_path)
    request = _handoff_request("same-request")
    gate = Barrier(2)

    def invoke(branch):
        gate.wait()
        try:
            return compose_child_execution(runtime, request=request,
                spec=_t3_spec(request), branch=branch)
        except StateConflict as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(invoke, ["one", "two"]))
    winners = [o for o in outcomes if not isinstance(o, StateConflict)]
    conflicts = [o for o in outcomes if isinstance(o, StateConflict)]
    assert len(winners) == len(conflicts) == 1
    assert winners[0].placement_created is True
    assert "placement" in str(conflicts[0]) and "changed" in str(conflicts[0])
    assert len(runtime.jobs.list_jobs()) == 2


def test_unrelated_command_owner_is_not_adopted_as_placement(tmp_path):
    runtime, _ = _runtime(tmp_path)
    request = _handoff_request("original")
    unrelated = runtime.jobs.create_job("Different owned work",
        constraints={"child_placement": _t3_spec(request)},
        command_id=placement_command_id(request))
    with pytest.raises(StateConflict, match="placement.*owner"):
        compose_child_execution(runtime, request=request, spec=_t3_spec(request))
    assert runtime.jobs.get_job(unrelated.job_id).objective == "Different owned work"
