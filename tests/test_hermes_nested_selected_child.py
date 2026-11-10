"""Actual nested capture/publication/selected dispatch under the original root.

Only physical provider execution and privileged fixture ownership are inert.
Runtime admission, canonical hierarchy/plan proof, Workspace/CooHost capture,
fixed installed target, claim, terminal return and command replay are real.
"""
from __future__ import annotations

import asyncio
import copy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from control_plane import executive_runtime as er
from control_plane.coo_principal_host import (
    selected_child_material, selected_child_material_digest, validate_selected_child_target,
)
from control_plane.executive_coo_policy import CooCyclePolicy, CooCyclePolicyError
from control_plane.executive_terminal_return import TerminalReturnError, reduce_terminal_return
from integrations.hermes_delegate.executive import (
    ExecutiveChildQualification, ExecutiveSelectedChild, ExecutiveSelectedChildComposition,
    ExecutiveSelectedChildTarget, clear_selected_child_composition, install_selected_child_composition,
)
from tests.test_executive_coo_hierarchy_service import _complete, _plan_body
from tests.test_hermes_selected_child_dispatch import (
    _call, _claim_events, _selected_child_service, _selection, _settle, short_socket_root,
)
from tests.test_hermes_selected_child_target import (
    WORK_REF, _capture, _host, _installed_consumers, _installed_document,
    _publication, _runtime_snapshot, _unsealed_installation, admitted, unsealed,
)


def _admit(service, coordinator, *, delegation=None, step_count=1):
    runtime = service.runtime
    planner = runtime.jobs.create_cycle_planner(
        coordinator.job_id, command_id=f"coo-cycle:{coordinator.job_id}:create-planner:0")
    dispatch = runtime.attempts.dispatch_cycle_job(
        planner.job_id, worker_id=service.config.worker_id,
        command_id=f"coo-cycle:{coordinator.job_id}:dispatch:{planner.job_id}:attempt:1")
    body = _plan_body(dispatch, coordinator, delegation=delegation)
    for ordinal in range(1, step_count):
        body["steps"].append({**copy.deepcopy(body["steps"][0]),
                              "ordinal": ordinal, "step_id": f"STEP-{ordinal}",
                              "objective": f"Complete bounded outcome {ordinal}"})
    _complete(runtime, dispatch, body)
    return runtime.jobs.admit_cycle_plan(coordinator.job_id,
        command_id=f"coo-cycle:{coordinator.job_id}:admit-plan:{dispatch.attempt.attempt_id}")


def _nested(service, root, tmp_path, *, coordinator_depth=1):
    coordinator = root
    for level in range(coordinator_depth):
        coordinator = _admit(service, coordinator,
            delegation={"descendant_limit": 14 - 2 * level, "max_depth": 3})[0]
    leaf = _admit(service, coordinator)[0]
    return SimpleNamespace(runtime=service.runtime, root=root, coordinator=coordinator,
                           leaf=leaf, work=lambda _index: leaf, control_room_root=tmp_path)


def _capture_host(host, principal, context, state, *, children=None):
    return host.capture_selected_child_target(principal=principal, context=context,
        work_ref=WORK_REF, root_job_id=state.root.job_id,
        child_job_ids=children or [state.leaf.job_id])


@pytest.mark.parametrize("coordinator_depth", [1, 2])
def test_nested_capture_publication_qualifies_claims_and_replays_original_command(
    tmp_path, short_socket_root, unsealed, coordinator_depth,
):
    async def exercise():
        async with _selected_child_service(tmp_path, short_socket_root,
                name=f"nested-selection-{coordinator_depth}") as (service, supervisor, root, returned, gate):
            state = _nested(service, root, tmp_path, coordinator_depth=coordinator_depth)
            before = _runtime_snapshot(state.runtime)
            with state.runtime.observe_bounded_read() as observation:
                captured = observation.read_selected_child_target_bounded(
                    root.job_id, child_job_ids=(state.leaf.job_id,))
            assert captured.plan.root_job_id == captured.plan.root_metadata.root_job_id == root.job_id
            assert captured.plan.admission["coordinator_job_id"] == state.coordinator.job_id
            host, principal, context, _coo = _host(state)
            publication = _publication(_capture_host(host, principal, context, state))
            assert _runtime_snapshot(state.runtime) == before
            assert publication["root_job_id"] == root.job_id
            assert publication["children"][0]["parent_job_id"] == state.coordinator.job_id
            assert publication["source"]["plan_digest"] == state.leaf.plan_digest
            document = _installed_document(publication)
            source, config = _unsealed_installation(document, unsealed)
            installed, settings = _installed_consumers(document, source, config)
            target = installed.selected_child_target()
            assert type(target) is ExecutiveSelectedChildTarget
            assert target.material_digest() == settings.selected_child_target.material_digest() == publication["material_digest"]
            child = target.children[0]
            assert child.command_id == (
                f"coo-cycle:{state.coordinator.job_id}:dispatch:{state.leaf.job_id}:attempt:1")
            observed = ExecutiveChildQualification(state.runtime, child.selection).qualify()
            assert observed["state"] == "QUALIFIED", observed
            assert observed["root_job_id"] == root.job_id
            assert observed["parent_job_id"] == state.coordinator.job_id
            authority, _config, _document, facts = service._selected_child_fixture
            composition = ExecutiveSelectedChildComposition(service=service, runtime=state.runtime,
                children=target.children, loop=asyncio.get_running_loop(), authority=authority,
                context=facts["context"], capability_profile_digest=facts["capability_profile_digest"],
                receiving_request_guard=target.require_current)
            install_selected_child_composition(composition)
            try:
                first = await _call({"action": "selected_child_submit", "command": child.command_id})
                assert first["state"] == "ACTIVE", first
                attempt = first["attempt_id"]
                replay = await _call({"action": "selected_child_submit", "command": child.command_id})
                assert replay["attempt_id"] == attempt and replay["state"] == "ACTIVE", replay
                assert len(_claim_events(state.runtime, state.leaf.job_id)) == 1
                gate.set()
                await _settle(service)
                status = await _call({"action": "selected_child_status", "command": child.command_id})
                assert status["state"] == "COMPLETED" and status["attempt_id"] == attempt, status
                replay = await _call({"action": "selected_child_submit", "command": child.command_id})
                assert replay["state"] == "COMPLETED" and replay["attempt_id"] == attempt, replay
                assert _claim_events(state.runtime, state.leaf.job_id)[0]["command_id"] == child.command_id
                assert state.runtime.jobs.get_job(state.leaf.job_id).attempt_count == 1
                assert [item.attempt_id for item in returned] == [attempt]
                assert all(job.root_job_id == root.job_id for job in state.runtime.jobs.list_jobs())
            finally:
                clear_selected_child_composition()
    asyncio.run(exercise())



def _runtime_driver(tmp_path, *, material=False):
    from control_plane.ceo_intent import submit_intent
    from tests.test_executive_os_phase1fc import _register, _v2_intent
    runtime = er.Runtime.at(tmp_path / "runtime")
    _register(runtime)
    root = runtime.jobs.get_job(submit_intent(runtime,
        _v2_intent(business_impact="material" if material else "routine"))["job_id"])
    # Data for the shared fixture's admission helper; this is not a service,
    # principal, provider or permission substitute.
    driver = SimpleNamespace(runtime=runtime, config=SimpleNamespace(worker_id="worker-1"))
    return driver, root


def _runtime_state(tmp_path, *, coordinator_depth=1, material=False):
    driver, root = _runtime_driver(tmp_path, material=material)
    return _nested(driver, root, tmp_path, coordinator_depth=coordinator_depth)


@pytest.mark.parametrize("coordinator_depth", [1, 2])
def test_runtime_nested_capture_installed_target_claim_completion_and_replay(tmp_path, unsealed, coordinator_depth):
    from tests.test_executive_coo_hierarchy_cycle import finish_result
    state = _runtime_state(tmp_path, coordinator_depth=coordinator_depth)
    before = _runtime_snapshot(state.runtime)
    with state.runtime.observe_bounded_read() as observation:
        captured = observation.read_selected_child_target_bounded(
            state.root.job_id, child_job_ids=(state.leaf.job_id,))
    assert captured.plan.root_job_id == captured.plan.root_metadata.root_job_id == state.root.job_id
    assert captured.plan.admission["coordinator_job_id"] == state.coordinator.job_id
    publication = _publication(_capture(state))
    assert _runtime_snapshot(state.runtime) == before
    document = _installed_document(publication)
    source, config = _unsealed_installation(document, unsealed)
    installed, settings = _installed_consumers(document, source, config)
    target = installed.selected_child_target()
    assert type(target) is ExecutiveSelectedChildTarget
    assert target.material_digest() == settings.selected_child_target.material_digest() == publication["material_digest"]
    target.require_current()
    child = target.children[0]
    assert child.command_id == f"coo-cycle:{state.coordinator.job_id}:dispatch:{state.leaf.job_id}:attempt:1"
    qualified = ExecutiveChildQualification(state.runtime, child.selection).qualify()
    assert qualified["state"] == "QUALIFIED", qualified
    assert qualified["root_job_id"] == state.root.job_id
    assert qualified["parent_job_id"] == state.coordinator.job_id
    dispatch = state.runtime.attempts.dispatch_cycle_job(state.leaf.job_id,
        command_id=child.command_id, worker_id="worker-1", expected_selection=child.expected_selection())
    assert dispatch is not None
    replay = state.runtime.attempts.dispatch_cycle_job(state.leaf.job_id,
        command_id=child.command_id, worker_id="worker-1", expected_selection=child.expected_selection())
    assert replay.attempt.attempt_id == dispatch.attempt.attempt_id
    finish_result(state.runtime, dispatch)
    completion = state.runtime.validated_role_completion(state.leaf.job_id,
        expected_attempt_id=dispatch.attempt.attempt_id)
    assert completion.job.root_job_id == state.root.job_id
    assert completion.job.parent_job_id == state.coordinator.job_id
    assert completion.coordinator_job == state.runtime.jobs.get_job(state.coordinator.job_id)
    candidate = reduce_terminal_return(material=completion)
    assert candidate.job_id == state.leaf.job_id
    assert candidate.root_job_id == state.root.job_id
    assert candidate.attempt_id == dispatch.attempt.attempt_id
    assert candidate.operation_key == f"exec-{state.leaf.job_id.lower()}"
    assert candidate.session_ref == f"asd-session-exec-{state.leaf.job_id.lower()}"
    assert candidate.runtime_status == "COMPLETED"
    assert candidate.result_envelope_digest == completion.result_digest
    replay = state.runtime.attempts.dispatch_cycle_job(state.leaf.job_id,
        command_id=child.command_id, worker_id="worker-1", expected_selection=child.expected_selection())
    assert replay.attempt.attempt_id == dispatch.attempt.attempt_id
    assert len(_claim_events(state.runtime, state.leaf.job_id)) == 1
    assert state.runtime.jobs.get_job(state.leaf.job_id).attempt_count == 1
    assert all(job.root_job_id == state.root.job_id for job in state.runtime.jobs.list_jobs())


def test_nested_capture_rejects_two_actual_coordinators(tmp_path):
    driver, root = _runtime_driver(tmp_path)
    coordinators = _admit(driver, root,
        delegation={"descendant_limit": 6, "max_depth": 3}, step_count=2)
    leaves = [_admit(driver, parent)[0] for parent in coordinators]
    state = SimpleNamespace(runtime=driver.runtime, root=root, leaf=leaves[0],
                            work=lambda _index: leaves[0], control_room_root=tmp_path)
    before = _runtime_snapshot(state.runtime)
    host, principal, context, _ = _host(state)
    with pytest.raises(er.StateConflict, match="coordinator"):
        _capture_host(host, principal, context, state, children=[leaf.job_id for leaf in leaves])
    assert _runtime_snapshot(state.runtime) == before
    children = tuple(ExecutiveSelectedChild(_selection(leaf), 1) for leaf in leaves)
    with pytest.raises(ValueError, match="coordinator plan"):
        ExecutiveSelectedChildTarget(WORK_REF, children, lambda: None)


@pytest.mark.parametrize("alteration", ["root", "parent", "plan_attempt", "plan_digest", "current_attempt"])
def test_nested_qualification_refuses_foreign_or_stale_coordinates(tmp_path, alteration):
    state = _runtime_state(tmp_path)
    selection = _selection(state.leaf)
    changed = {
        "root": {"root_job_id": state.coordinator.job_id},
        "parent": {"parent_job_id": state.root.job_id},
        "plan_attempt": {"plan_attempt_id": "ATT-" + "e" * 32},
        "plan_digest": {"plan_digest": "e" * 64},
        "current_attempt": {"expected_current_attempt_id": "ATT-" + "e" * 32},
    }[alteration]
    before = _runtime_snapshot(state.runtime)
    result = ExecutiveChildQualification(state.runtime, replace(selection, **changed)).qualify()
    assert result["state"] == "REFUSED", result
    assert _runtime_snapshot(state.runtime) == before


def test_nested_publication_refuses_root_command_and_mixed_parent_even_with_rehashed_material(tmp_path):
    state = _runtime_state(tmp_path)
    publication = _publication(_capture(state))
    for alteration in ("root-command", "self-parent", "mixed-parent", "mixed-plan"):
        changed = copy.deepcopy(publication)
        child = changed["children"][0]
        if alteration == "root-command":
            child["command_id"] = f"coo-cycle:{state.root.job_id}:dispatch:{child['job_id']}:attempt:1"
        elif alteration == "self-parent":
            child["parent_job_id"] = child["job_id"]
            child["command_id"] = f"coo-cycle:{child['job_id']}:dispatch:{child['job_id']}:attempt:1"
        else:
            sibling = {**child, "job_id": "JOB-999999"}
            if alteration == "mixed-parent": sibling["parent_job_id"] = state.root.job_id
            else: sibling["plan_digest"] = "f" * 64
            sibling["command_id"] = f"coo-cycle:{sibling['parent_job_id']}:dispatch:{sibling['job_id']}:attempt:1"
            changed["children"].append(sibling)
        changed["material_digest"] = selected_child_material_digest(
            selected_child_material(WORK_REF, changed["children"]))
        with pytest.raises(ValueError):
            validate_selected_child_target(changed)


def test_nested_selected_claim_rejects_root_scoped_command_before_any_attempt(tmp_path):
    state = _runtime_state(tmp_path)
    child = ExecutiveSelectedChild(_selection(state.leaf), 1)
    expected = replace(child.expected_selection(),
        command_id=f"coo-cycle:{state.root.job_id}:dispatch:{state.leaf.job_id}:attempt:1")
    with pytest.raises(er.StateConflict):
        state.runtime.attempts.dispatch_cycle_job(state.leaf.job_id,
            worker_id="worker-1", command_id=expected.command_id, expected_selection=expected)
    assert _claim_events(state.runtime, state.leaf.job_id) == []


@pytest.mark.parametrize("change", ["source", "permission", "policy"])
def test_nested_capture_refuses_changes_inside_the_same_observation(tmp_path, monkeypatch, change):
    state = _runtime_state(tmp_path)
    host, principal, context, coo = _host(state)
    before = _runtime_snapshot(state.runtime)
    original_load = CooCyclePolicy.load
    def mutate():
        if change == "source":
            host.workspace.cache.snapshot().owner.state_published_seq += 1
        elif change == "permission":
            coo["missions"][0]["enabled"] = False
        else:
            def changed_load(cls, path=None, *, version=1):
                value = original_load(path, version=version)
                return replace(value, source_sha256="f" * 64) if version == 2 else value
            monkeypatch.setattr(CooCyclePolicy, "load", classmethod(changed_load))
    read_selected = er.BoundedRuntimeReadObservation.read_selected_child_target_bounded
    def at_selected_read(observation, *args, **kwargs):
        # The preliminary CooHost mission read stays unchanged. The mutation
        # occurs inside this capture's already-entered policy/source bracket.
        mutate()
        return read_selected(observation, *args, **kwargs)
    monkeypatch.setattr(er.BoundedRuntimeReadObservation,
                        "read_selected_child_target_bounded", at_selected_read)
    with pytest.raises(ValueError):
        _capture_host(host, principal, context, state)
    assert _runtime_snapshot(state.runtime) == before


def test_nested_capture_preserves_required_v1_ancestor_transport_policy(tmp_path, monkeypatch):
    state = _runtime_state(tmp_path)
    original = CooCyclePolicy.load
    def load(cls, path=None, *, version=1):
        if version == 1: raise CooCyclePolicyError("fixture required ancestor policy unavailable")
        return original(path, version=version)
    monkeypatch.setattr(CooCyclePolicy, "load", classmethod(load))
    # The original planner's canonical terminal transport evidence uses v1,
    # even when its admitted reservation is v2. It remains required authority.
    before = _runtime_snapshot(state.runtime)
    with pytest.raises(CooCyclePolicyError, match="required ancestor policy"):
        _capture(state)
    assert _runtime_snapshot(state.runtime) == before


def test_legacy_capture_uses_v1_when_unrelated_v2_is_unavailable(admitted, monkeypatch):
    original = CooCyclePolicy.load
    def load(cls, path=None, *, version=1):
        if version == 2: raise CooCyclePolicyError("fixture unrelated v2 unavailable")
        return original(path, version=version)
    monkeypatch.setattr(CooCyclePolicy, "load", classmethod(load))
    captured = _capture(admitted)
    child = captured["children"][0]
    assert child["parent_job_id"] == child["root_job_id"] == admitted.root.job_id
    assert child["command_id"] == f"coo-cycle:{admitted.root.job_id}:dispatch:{child['job_id']}:attempt:1"


def test_nested_capture_refuses_superseded_work_and_qualifies_its_actual_repair(tmp_path):
    from tests.test_executive_coo_hierarchy_cycle import finish_result
    from tests.test_executive_os_phase1fc import _register, _review_body
    state = _runtime_state(tmp_path, material=True)
    runtime, parent, leaf = state.runtime, state.coordinator, state.leaf
    work = runtime.attempts.dispatch_cycle_job(leaf.job_id, worker_id="worker-1",
        command_id=f"coo-cycle:{parent.job_id}:dispatch:{leaf.job_id}:attempt:1")
    finish_result(runtime, work)
    complete = runtime.validated_role_completion(leaf.job_id, expected_attempt_id=work.attempt.attempt_id)
    _register(runtime, "worker-2")
    review = runtime.jobs.create_cycle_review(parent.job_id, leaf.job_id,
        command_id=f"coo-cycle:{parent.job_id}:create-review:{leaf.job_id}:1")
    reviewed = runtime.attempts.dispatch_cycle_job(review.job_id, worker_id="worker-2",
        command_id=f"coo-cycle:{parent.job_id}:dispatch:{review.job_id}:attempt:1")
    seal, _terminal = _complete(runtime, reviewed, _review_body(
        root_id=state.root.job_id, plan_attempt_id=leaf.plan_attempt_id, plan_digest=leaf.plan_digest,
        plan_step_id=leaf.plan_step_id, target_job_id=leaf.job_id,
        target_attempt_id=work.attempt.attempt_id, target_result_digest=complete.role_result_digest,
        repair_round=0, verdict="reject"))
    repair = runtime.jobs.create_cycle_repair(parent.job_id, leaf.job_id, review.job_id,
        command_id=f"coo-cycle:{parent.job_id}:create-repair:{leaf.job_id}:{review.job_id}:{seal['role_result_digest']}:1")
    with pytest.raises(er.StateConflict, match="superseded"):
        _capture(state)
    refused = ExecutiveChildQualification(runtime, _selection(runtime.jobs.get_job(leaf.job_id))).qualify()
    assert refused["reason"] == "EXECUTIVE_CHILD_SUPERSEDED", refused
    captured = _capture(state, child_job_ids=[repair.job_id])
    assert captured["children"][0]["parent_job_id"] == parent.job_id
    assert captured["children"][0]["root_job_id"] == state.root.job_id
    assert captured["children"][0]["repair_round"] == 1
    qualified = ExecutiveChildQualification(runtime, _selection(repair)).qualify()
    assert qualified["state"] == "QUALIFIED", qualified
    # The superseded revision remains its own sealed completion. Reporting
    # that fact does not make it the current accepted revision or replay work.
    historical = reduce_terminal_return(material=runtime.validated_role_completion(
        leaf.job_id, expected_attempt_id=work.attempt.attempt_id))
    assert historical.job_id == leaf.job_id
    assert historical.attempt_id == work.attempt.attempt_id
    rejected = reduce_terminal_return(material=runtime.validated_role_completion(
        review.job_id, expected_attempt_id=reviewed.attempt.attempt_id))
    assert rejected.root_job_id == state.root.job_id
    assert rejected.review_verdict == "reject"


@pytest.mark.parametrize("coordinator_change", ["missing", "original-root", "sibling"])
def test_nested_terminal_return_refuses_missing_or_spliced_coordinator(tmp_path, coordinator_change):
    from tests.test_executive_coo_hierarchy_cycle import finish_result
    driver, root = _runtime_driver(tmp_path)
    parents = _admit(driver, root,
        delegation={"descendant_limit": 6, "max_depth": 3}, step_count=2)
    leaf = _admit(driver, parents[0])[0]
    dispatch = driver.runtime.attempts.dispatch_cycle_job(leaf.job_id, worker_id="worker-1",
        command_id=f"coo-cycle:{parents[0].job_id}:dispatch:{leaf.job_id}:attempt:1")
    finish_result(driver.runtime, dispatch)
    completion = driver.runtime.validated_role_completion(leaf.job_id,
        expected_attempt_id=dispatch.attempt.attempt_id)
    replacement = {"missing": None, "original-root": root, "sibling": parents[1]}[coordinator_change]
    with pytest.raises(TerminalReturnError) as refused:
        reduce_terminal_return(material=replace(completion, coordinator_job=replacement))
    assert refused.value.code == "IDENTITY_REFUSED"


def test_nested_completion_revalidates_actual_coordinator_inside_same_snapshot(tmp_path, monkeypatch):
    from tests.test_executive_coo_hierarchy_cycle import finish_result
    from contextlib import contextmanager
    state = _runtime_state(tmp_path, coordinator_depth=2)
    dispatch = state.runtime.attempts.dispatch_cycle_job(state.leaf.job_id, worker_id="worker-1",
        command_id=f"coo-cycle:{state.coordinator.job_id}:dispatch:{state.leaf.job_id}:attempt:1")
    finish_result(state.runtime, dispatch)
    before = _runtime_snapshot(state.runtime)
    reads, qualified = [], []
    original_read = state.runtime.store.read
    original_qualify = er._selected_child_coordinator_plan
    @contextmanager
    def read():
        with original_read() as connection:
            reads.append(connection)
            yield connection
    def qualify(connection, root, coordinator):
        qualified.append((connection, root["job_id"], coordinator["job_id"]))
        return original_qualify(connection, root, coordinator)
    with monkeypatch.context() as patch:
        patch.setattr(state.runtime.store, "read", read)
        patch.setattr(er, "_selected_child_coordinator_plan", qualify)
        material = state.runtime.validated_role_completion(state.leaf.job_id,
            expected_attempt_id=dispatch.attempt.attempt_id)
    assert len(reads) == 1
    assert qualified == [(reads[0], state.root.job_id, state.coordinator.job_id)]
    assert reduce_terminal_return(material=material).root_job_id == state.root.job_id
    assert _runtime_snapshot(state.runtime) == before


def test_nested_completion_refuses_unavailable_coordinator_policy(tmp_path, monkeypatch):
    from tests.test_executive_coo_hierarchy_cycle import finish_result
    state = _runtime_state(tmp_path, coordinator_depth=2)
    dispatch = state.runtime.attempts.dispatch_cycle_job(state.leaf.job_id, worker_id="worker-1",
        command_id=f"coo-cycle:{state.coordinator.job_id}:dispatch:{state.leaf.job_id}:attempt:1")
    finish_result(state.runtime, dispatch)
    original = CooCyclePolicy.load
    def load(cls, path=None, *, version=1):
        if version == 2:
            raise CooCyclePolicyError("fixture current hierarchy policy unavailable")
        return original(path, version=version)
    monkeypatch.setattr(CooCyclePolicy, "load", classmethod(load))
    before = _runtime_snapshot(state.runtime)
    with pytest.raises(CooCyclePolicyError):
        state.runtime.validated_role_completion(state.leaf.job_id,
            expected_attempt_id=dispatch.attempt.attempt_id)
    assert _runtime_snapshot(state.runtime) == before


def test_deepest_full_root_capture_stays_within_original_shared_budgets(tmp_path):
    driver, root = _runtime_driver(tmp_path)
    parent = root
    for depth in range(2):
        parent = _admit(driver, parent,
            delegation={"descendant_limit": 14 - 2 * depth, "max_depth": 3})[0]
    leaves = _admit(driver, parent, step_count=11)
    assert len(driver.runtime.jobs.list_jobs()) == 17
    state = SimpleNamespace(runtime=driver.runtime, root=root, leaf=leaves[0],
                            work=lambda _index: leaves[0], control_room_root=tmp_path)
    before = _runtime_snapshot(driver.runtime)
    captured = _capture(state, child_job_ids=[leaf.job_id for leaf in leaves])
    assert len(captured["children"]) == 11
    assert all(child["root_job_id"] == root.job_id and child["parent_job_id"] == parent.job_id
               for child in captured["children"])
    assert _runtime_snapshot(driver.runtime) == before
