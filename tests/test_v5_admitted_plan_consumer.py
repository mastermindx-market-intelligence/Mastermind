"""Canonical v5 admission through the existing root-plan display owners.

Workers, signed result seals and Control Room custody are explicit fixtures.
No provider, installed service, socket, new reader or admission path is used.
"""
from __future__ import annotations

import json
from contextlib import contextmanager

import pytest

from control_plane import executive_runtime as er
from control_plane.fabric_plan_projection import FabricPlanProjectionError, project_admitted_plan
from tests import test_project_execution_mixed_plan as producer
from tests import test_workspace_admitted_plan_read as workspace
from tests.test_runtime_admitted_plan_read import _bound

router = producer.router
mixed = producer.mixed


def _admit(e, count):
    steps = [producer.step(index, e.members[0 if index == 0 else 1],
                           depends=index > 0) for index in range(count)]
    if count > 2:
        steps[-1]["prerequisite_step_ids"] = [f"STEP-{index}" for index in range(count - 1)]
    command = producer.seal(e, steps)
    e.admitted_children = e.runtime.jobs.admit_cycle_plan(e.root.job_id, command_id=command)
    return steps


def _snapshot(e):
    with _bound(e.runtime) as (reader, namespace, _):
        with reader.observe_bounded_read() as observation:
            snapshot = observation.read_admitted_plan_bounded(e.root.job_id)
        assert observation.receipt.state == "SAME"
        assert namespace.entries == namespace.exits and not namespace.active
        assert snapshot.plan["schema_version"] == "mastermind.execution_plan/v5"
        assert snapshot.admission["schema_version"] == "mastermind.coo_plan_admission/v3"
        return snapshot, observation.receipt


def _assert_plan(e, view, steps):
    assert view["root_job_id"] == e.root.job_id
    assert view["plan_attempt_id"] == e.dispatch.attempt.attempt_id
    assert view["plan_schema_version"] == "mastermind.execution_plan/v5"
    assert view["admission_schema_version"] == "mastermind.coo_plan_admission/v3"
    assert view["policy_sha"] == er.CooCyclePolicy.load(version=2).policy_sha256
    assert [step["step_id"] for step in view["steps"]] == [step["step_id"] for step in steps]
    assert [step["prerequisite_step_ids"] for step in view["steps"]] == [
        step["prerequisite_step_ids"] for step in steps]
    assert all(set(step) == {
        "ordinal", "step_id", "objective", "business_impact",
        "review_required", "prerequisite_step_ids"} for step in view["steps"])


@pytest.mark.parametrize("count", [2, 9, 15])
def test_v5_root_plan_reaches_existing_bounded_projection(mixed, count):
    e = mixed
    steps = _admit(e, count)
    snapshot, receipt = _snapshot(e)
    view = project_admitted_plan(snapshot, receipt)
    _assert_plan(e, view, steps)
    assert view["plan_digest"] == snapshot.admission["plan_digest"]
    assert view["reservation_digest"] == snapshot.admission["reservation_digest"]


def _owner(e, tmp_path, monkeypatch):
    # Reuse the real Workspace/cache/custody fixture with this already admitted
    # Runtime; do not create a substitute planner or rewrite retained material.
    monkeypatch.setattr(workspace, "_completed_planner",
                        lambda _: (e.runtime, e.planner, e.dispatch.attempt))
    return workspace.owner_fixture(tmp_path)


@pytest.mark.parametrize("count", [2, 15])
def test_v5_root_plan_reaches_existing_workspace_route(mixed, tmp_path, monkeypatch, count):
    e = mixed
    steps = _admit(e, count)
    with _owner(e, tmp_path, monkeypatch) as owner:
        before = owner["namespace"].entries
        envelope = workspace.call(owner)
        body = envelope["result"]
        assert body["availability"] == "AVAILABLE", body["reason_codes"]
        assert body["selection"] == owner["selection"]
        assert body["source_observation"]["state"] == "SAME"
        _assert_plan(e, body["plan"], steps)
        assert owner["namespace"].entries == before + 1 == owner["namespace"].exits
        assert not owner["namespace"].active
        # The unchanged actual owner envelope is available to the source-level
        # TypeScript decoder qualification, without translating IDs or receipts.
        (tmp_path / "actual-workspace-plan.json").write_text(
            json.dumps(envelope, sort_keys=True, allow_nan=False), encoding="utf-8")


@pytest.mark.parametrize("target,mutation", [
    ("plan", "missing"), ("plan", "foreign"),
    ("admission", "missing"), ("admission", "foreign"),
    ("admission", "legacy_version"),
])
def test_v5_root_projection_rejects_crossed_coordinator_or_version(mixed, target, mutation):
    e = mixed
    _admit(e, 2)
    snapshot, receipt = _snapshot(e)
    material = getattr(snapshot, target)
    if mutation == "missing":
        material.pop("coordinator_job_id")
    elif mutation == "foreign":
        material["coordinator_job_id"] = "JOB-999999"
    else:
        material["schema_version"] = "mastermind.coo_plan_admission/v2"
    with pytest.raises(FabricPlanProjectionError) as error:
        project_admitted_plan(snapshot, receipt)
    assert error.value.code == "SOURCE_UNAVAILABLE"


def test_v5_workspace_rechecks_its_hierarchy_policy_after_physical_close(
        mixed, tmp_path, monkeypatch):
    e = mixed
    _admit(e, 2)
    original_observe = er.Runtime.observe_bounded_read
    original_policy = er.CooCyclePolicy.load
    closed = [False]
    versions = []

    def policy(path=None, *, version=1):
        versions.append(version)
        if closed[0] and version == 2:
            raise ValueError("fixture hierarchy policy became unavailable")
        return original_policy(path, version=version)

    @contextmanager
    def observe(runtime):
        with original_observe(runtime) as observation:
            yield observation
        closed[0] = True

    with _owner(e, tmp_path, monkeypatch) as owner:
        monkeypatch.setattr(er.CooCyclePolicy, "load", policy)
        monkeypatch.setattr(er.Runtime, "observe_bounded_read", observe)
        workspace.assert_unavailable(workspace.call(owner), "SOURCE_UNAVAILABLE")
        assert closed[0] and versions[-1] == 2
        assert owner["namespace"].entries == owner["namespace"].exits


def test_v5_selected_child_capture_keeps_the_original_plan_and_parent(
        mixed, tmp_path, monkeypatch):
    e = mixed
    _admit(e, 2)
    original = e.admitted_children[0]
    with _owner(e, tmp_path, monkeypatch) as owner:
        before = owner["namespace"].entries
        captured = workspace.service(owner).capture_selected_child_target(
            work_ref=owner["selection"]["work_ref"], root_job_id=e.root.job_id,
            child_job_ids=[original.job_id])
        (child,) = captured["children"]
        assert child["job_id"] == original.job_id
        assert child["root_job_id"] == child["parent_job_id"] == e.root.job_id
        assert child["plan_step_id"] == "STEP-0"
        assert child["plan_attempt_id"] == e.dispatch.attempt.attempt_id
        assert child["attempt_ordinal"] == 1
        assert captured["source"]["plan_attempt_id"] == e.dispatch.attempt.attempt_id
        assert captured["source"]["plan_digest"] == child["plan_digest"]
        assert captured["source"]["policy_sha"] == er.CooCyclePolicy.load(version=2).policy_sha256
        assert captured["source"]["observation_state"] == "SAME"
        assert owner["namespace"].entries == before + 1 == owner["namespace"].exits
        assert not owner["namespace"].active
    assert len(e.runtime.attempts.list_attempts()) == 1


def test_legacy_workspace_read_does_not_require_an_unrelated_hierarchy_policy(
        tmp_path, monkeypatch):
    original_policy = er.CooCyclePolicy.load

    def policy(path=None, *, version=1):
        if version == 2:
            raise ValueError("fixture unrelated hierarchy policy unavailable")
        return original_policy(path, version=version)

    with workspace.owner_fixture(tmp_path) as owner:
        monkeypatch.setattr(er.CooCyclePolicy, "load", policy)
        result = workspace.call(owner)
        assert result["result"]["availability"] == "AVAILABLE"
        assert owner["namespace"].entries == owner["namespace"].exits


@pytest.mark.parametrize("count", [2, 15])
def test_v5_root_plan_reaches_existing_autonomy_policy_consumer(
        mixed, tmp_path, monkeypatch, count):
    import asyncio
    from tests import test_workspace_autonomy_policy_adapter as autonomy
    from control_plane.workspace_autonomy_policy_adapter import read_autonomy_policy

    e = mixed
    _admit(e, count)
    with _owner(e, tmp_path, monkeypatch) as owner:
        authorize, _ = autonomy.authorizer()
        existing = workspace.service(owner, authorize)
        before = owner["namespace"].entries
        response = asyncio.run(read_autonomy_policy(existing, autonomy.frame(owner)))
        body = response["result"]
        assert response["ok"] and body["availability"] == "AVAILABLE", body["reason_codes"]
        policy = er.CooCyclePolicy.load(version=2)
        assert body["selection"] == owner["selection"]
        assert body["policy"]["scope"] == "ADMITTED_ROOT"
        assert body["policy"]["policy_sha"] == policy.policy_sha256
        assert body["policy"]["source_sha256"] == policy.source_sha256
        assert body["policy"]["limits"] == policy.to_dict()
        assert body["source_observation"]["state"] == "SAME"
        assert body["source_observation"]["runtime"]["state"] == "SAME"
        assert owner["namespace"].entries == before + 1 == owner["namespace"].exits
        assert not owner["namespace"].active
        assert len(e.runtime.attempts.list_attempts()) == 1
