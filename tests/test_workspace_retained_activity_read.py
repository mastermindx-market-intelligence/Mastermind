"""Original COO principal, CCR, Runtime and OHF activity source on one fixture.

This suite neither launches providers nor touches the installed Executive DB.
"""
from __future__ import annotations

import asyncio
import copy
import json
from contextlib import contextmanager
from dataclasses import replace

import pytest

from common import executive_workspace_activity_contract as activity
from common import executive_workspace_contract as wire
from control_plane.workspace_read_service import WorkspaceReadService
from control_plane import executive_runtime as er
from control_plane.operator_activity_projection import project_retained_operator_activity
from tests import test_interactive_tx5_runtime as tx5
from tests.test_runtime_admitted_plan_read import _bound
from tests.test_workspace_read_service import cache_fixture, frame
from tests.test_mission_workspace import _owner_observation_inputs
from scripts import chairman_control_room as ccr
from tests.test_executive_coo_host import setup as actual_coo_fixture

WORK_REF = "WS:ONE"
SENSITIVE = "PRIVATE-OPERATOR-MODEL-TOOL-SECRET"

@contextmanager
def owner_fixture(tmp_path, monkeypatch):
    previous = tx5._intent
    monkeypatch.setattr(
        tx5, "_intent",
        lambda intent_id: {**previous(intent_id), "workstream": WORK_REF},
    )
    writer, root, child, dispatch, epoch, generation = tx5._started_interactive(
        tmp_path / "runtime"
    )
    operation = tx5.OperationId(f"ohf-op:turn:{dispatch.attempt.attempt_id}:1")
    turn = tx5._reserve_turn(writer, dispatch, epoch, generation, 1)
    tx5._acknowledge_turn(writer, dispatch, turn, operation)
    tx5._record_candidate(writer, dispatch, turn)
    with _bound(writer) as (reader, namespace, binding):
        owners, clock, cache = cache_fixture(tmp_path)
        doc = _owner_observation_inputs()["control_room"]
        doc = json.loads(
            json.dumps(doc).replace("JOB-1", root.job_id).replace("2026-09-20", "2026-09-21")
        )
        doc["generated_at"] = owners[0].state_cache["doc"]["generated_at"]
        doc["autonomy"]["generated_at"] = doc["generated_at"]
        doc["autonomy"]["schema"] = "mastermind.autonomy_control_room.v1"
        row = doc["autonomy"]["responsibilities"][0]
        row["freshness"] = "current"
        row["validity"] = owners[0].state_cache["doc"]["autonomy"]["responsibilities"][0]["validity"]
        owners[0].state_cache["doc"] = doc
        owners[0].state_cache.pop("source_validity_bounds", None)
        with owners[0].state_lock:
            ccr._publish_source_validity(owners[0], doc, tuple(clock), tuple(clock))
        (tmp_path / "coo").mkdir()
        coo, mutable, principal, path = actual_coo_fixture(tmp_path / "coo")
        mutable["missions"][0]["work_ref"] = WORK_REF
        principal = {**principal, "policy_id": "bsc-workspace-read-test",
                     "resource": wire.RESOURCE, "scopes": [wire.SCOPE]}
        membership = coo.source.for_workspace_read_principal
        def authorize(value):
            return type(value) is dict and value == principal
        authorize.binding_digest = lambda value: "f" * 64 if authorize(value) else None
        selected = activity.selection({
            "work_ref": WORK_REF, "root_job_id": root.job_id,
            "job_id": child.job_id, "attempt_id": dispatch.attempt.attempt_id,
        })
        service = WorkspaceReadService(
            cache=cache, runtime=writer, authorize=authorize,
            armed={}, runtime_identity={"db_present": True},
            bounded_runtime=lambda runtime: reader if runtime is writer else pytest.fail("wrong Runtime"),
            activity_membership=membership,
        )
        request = {**frame(), "schema": activity.FRAME_SCHEMA,
                   "operation": activity.OPERATION, "selection": selected, "principal": principal}
        yield locals()


@pytest.fixture
def owner(tmp_path, monkeypatch):
    with owner_fixture(tmp_path, monkeypatch) as scope:
        yield scope


def _run(owner, **changes):
    payload = dict(owner["request"], **changes)
    return asyncio.run(owner["service"].handle_frame(payload))


def test_original_coo_and_real_harness_writer_to_bounded_workspace_projection(owner):
    assert owner["coo"].source.for_workspace_read_principal(owner["principal"], WORK_REF)[0]["enabled"] is True
    before = owner["namespace"].entries
    result = _run(owner)
    assert result["ok"] is True
    body = result["result"]
    assert body["availability"] == "AVAILABLE"
    assert body["selection"] == owner["selected"]
    assert body["source_observation"]["state"] == "SAME"
    assert body["activity"]["availability"] == "RETAINED"
    assert body["activity"]["source"]["live_worker_count"] is None
    assert body["activity"]["rows"][0]["category"] == "TURN_COMPLETED"
    assert len(body["activity"]["rows"]) == 1
    assert len(json.dumps(result)) < activity.MAX_RESPONSE_BYTES
    assert SENSITIVE not in json.dumps(result)
    assert owner["namespace"].entries == before + 1 == owner["namespace"].exits
    assert activity.validate_result(body, owner["selected"]) is body


@pytest.mark.parametrize("case", [
    "no_coo", "no_binding_digest", "wrong_principal", "disabled_coo",
    "changed_issuer", "changed_client", "changed_policy",
])
def test_missing_or_wrong_principal_refused_before_runtime(owner, case):
    service = owner["service"]
    principal = copy.deepcopy(owner["principal"])
    coo = owner["mutable"]
    if case == "no_coo": service._activity_membership = None
    elif case == "no_binding_digest": service.authorize.binding_digest = lambda x: None
    elif case == "disabled_coo": coo["missions"][0]["enabled"] = False
    elif case == "changed_issuer": principal["issuer_digest"] = "1" * 64
    elif case == "changed_client":
        principal["client_ref"] = "0" * 64 if principal["client_ref"] != "0" * 64 else "1" * 64
    elif case == "changed_policy": principal["policy_id"] = "another-policy"
    elif case == "wrong_principal": principal["subject_digest"] = "3" * 64
    before = owner["namespace"].entries
    result = _run(owner, principal=principal)
    assert result == wire.error("access_denied", 403)
    assert owner["namespace"].entries == before


def test_wrong_root_refuses_before_runtime(owner):
    before = owner["namespace"].entries
    selected = {**owner["selected"], "root_job_id": "JOB-987"}
    assert _run(owner, selection=selected) == wire.error("selection_not_found", 404)
    assert owner["namespace"].entries == before


def test_wrong_attempt_returns_only_closed_unavailable(owner):
    selected = {**owner["selected"], "attempt_id": "ATT-" + "9" * 32}
    result = _run(owner, selection=selected)
    assert result == activity.unavailable(selected, "SOURCE_UNAVAILABLE")
    assert SENSITIVE not in json.dumps(result)


@pytest.mark.parametrize("field,value", [
    ("work_ref", "WS:OTHER"),
    ("job_id", "JOB-987"),
    ("attempt_id", "ATT-" + "A" * 32),
    ("unknown", "private"),
])
def test_malformed_and_cross_workstream_frame_is_never_acquired(owner, field, value):
    selected = {**owner["selected"], field: value}
    before = owner["namespace"].entries
    result = _run(owner, selection=selected)
    if field == "work_ref":
        assert result == wire.error("access_denied", 403)
    elif field == "unknown" or field == "attempt_id":
        assert result == wire.error("invalid_input", 400)
    else:
        assert result == activity.unavailable(selected, "SOURCE_UNAVAILABLE")
    assert owner["namespace"].entries == before if field in ("work_ref", "unknown", "attempt_id") else True


@pytest.mark.parametrize("change", ["disable", "generation", "client", "permission", "replace_callback"])
def test_recheck_blocks_mid_read_coo_or_binding_rotation(owner, change):
    service = owner["service"]
    original = service._read_retained_activity
    def mutate_after_producer(value):
        result = original(value)
        if change == "disable":
            owner["mutable"]["missions"][0]["enabled"] = False
        elif change == "generation":
            owner["mutable"]["missions"][0]["outcome_ref"] = "outcome:rotated"
        elif change == "client":
            owner["mutable"]["binding"]["binding"]["client_ref"] = "5" * 64
        elif change == "permission":
            service.authorize.binding_digest = lambda x: "e" * 64
        else:
            service._activity_membership = lambda p, w: service._activity_membership(p, w)
        return result
    service._read_retained_activity = mutate_after_producer
    assert _run(owner) == wire.error("access_denied", 403)


@pytest.mark.parametrize("case", ["changed_root", "source_changed", "unbounded", "source_error"])
def test_original_reader_faults_hide_evidence(owner, monkeypatch, case):
    if case == "changed_root":
        original = er.BoundedRuntimeReadObservation.read_retained_operator_activity_bounded
        def change(obs, *args):
            source = original(obs, *args)
            return replace(source, root_metadata=replace(source.root_metadata, work_ref="WS:OTHER"))
        monkeypatch.setattr(er.BoundedRuntimeReadObservation,
                            "read_retained_operator_activity_bounded", change)
        reason = "SOURCE_UNAVAILABLE"
    elif case == "source_changed":
        original = er.Runtime.observe_bounded_read
        from contextlib import contextmanager
        @contextmanager
        def change(runtime):
            with original(runtime) as observation:
                yield observation
            if runtime is owner["reader"]:
                observation._receipt = replace(observation.receipt, state="CONFLICT")
        monkeypatch.setattr(er.Runtime, "observe_bounded_read", change)
        reason = "SOURCE_CHANGED"
    elif case == "unbounded":
        monkeypatch.setattr(er.BoundedRuntimeReadObservation,
                            "read_retained_operator_activity_bounded",
                            lambda *_: (_ for _ in ()).throw(er.RuntimeRoleResultOverBudget()))
        reason = "OVER_BUDGET"
    else:
        monkeypatch.setattr(er.BoundedRuntimeReadObservation,
                            "read_retained_operator_activity_bounded",
                            lambda *_: (_ for _ in ()).throw(ValueError(SENSITIVE)))
        reason = "SOURCE_UNAVAILABLE"
    result = _run(owner)
    assert result == activity.unavailable(owner["selected"], reason)
    assert SENSITIVE not in json.dumps(result)


def test_wire_contract_does_not_accept_private_or_provider_fields(owner):
    normal = _run(owner)["result"]
    corrupted = copy.deepcopy(normal)
    corrupted["activity"]["rows"][0]["prompt"] = SENSITIVE
    with pytest.raises(ValueError):
        activity.validate_result(corrupted, owner["selected"])
    assert SENSITIVE not in json.dumps(normal)
    wrong = copy.deepcopy(normal)
    wrong["source_observation"]["runtime"]["source_identity"] = SENSITIVE
    with pytest.raises(ValueError):
        activity.validate_result(wrong, owner["selected"])
    wrong = copy.deepcopy(normal)
    wrong["activity"]["source"]["live_worker_count"] = 0
    with pytest.raises(ValueError):
        activity.validate_result(wrong, owner["selected"])
