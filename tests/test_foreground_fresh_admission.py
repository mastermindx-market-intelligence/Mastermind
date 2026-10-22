"""Fresh source callback on the real canonical sink; no provider or START."""
import asyncio
import concurrent.futures
import copy
import threading

import pytest

from control_plane import ceo_intent as sink
from control_plane import executive_ceo_ingress as ingress
from control_plane.executive_runtime import JobStatus, Runtime
from tests import test_ceo_intent as old
from tests import test_executive_ceo_ingress_admission_hook as hooks
from tests import test_executive_os_phase1fc as phase1fc


def submit(runtime, tmp_path, observer=None, **changes):
    return sink.submit_intent(runtime, old._v2_intent(tmp_path, **changes),
        workspace_root=old._workspace_root(tmp_path),
        fresh_admission_observer=observer)


def test_callback_observes_committed_source_before_return_without_dispatch(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    seen = []
    def observer(root_id, command_id):
        root = runtime.jobs.get_job(root_id)
        event = runtime.store.find_event_by_command_id(command_id)
        assert root.parent_job_id is None and root.root_job_id == root_id
        assert root.status is JobStatus.QUEUED and root.attempt_count == 0
        assert event["job_id"] == root_id
        assert runtime.attempts.list_attempts() == []
        seen.append((root_id, command_id))
    receipt = submit(runtime, tmp_path, observer)
    assert seen == [(receipt["job_id"], sink.command_id_for(receipt["intent_id"]))]
    assert receipt["dispatched"] is False and receipt["duplicate"] is False
    assert "fresh_admission" not in receipt


def test_replay_never_calls_fresh_source_or_changes_root(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    first = submit(runtime, tmp_path)
    def forbidden(*_):
        raise AssertionError("replay cannot create attendance")
    replay = submit(runtime, tmp_path, forbidden)
    assert replay["duplicate"] is True and replay["job_id"] == first["job_id"]
    assert replay["dispatched"] is False and len(runtime.jobs.list_jobs()) == 1


def test_conflicting_replay_never_calls_observer(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    submit(runtime, tmp_path)
    seen = []
    with pytest.raises(sink.CeoIntentError):
        submit(runtime, tmp_path, lambda *v: seen.append(v), objective="Different work")
    assert seen == [] and len(runtime.jobs.list_jobs()) == 1


@pytest.mark.parametrize("observer", [False, {}, "caller JSON"])
def test_noncallable_source_refuses_before_root(tmp_path, observer):
    runtime = Runtime.at(tmp_path / "runtime")
    with pytest.raises(sink.CeoIntentError):
        submit(runtime, tmp_path, observer)
    assert runtime.jobs.list_jobs() == []


def test_async_source_refuses_before_root(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    async def observer(*_):
        pass
    with pytest.raises(sink.CeoIntentError):
        submit(runtime, tmp_path, observer)
    assert runtime.jobs.list_jobs() == []


@pytest.mark.parametrize("failure", ["raise", "bool", "coroutine"])
def test_post_commit_source_failure_preserves_original_root_without_replay(tmp_path, failure):
    runtime = Runtime.at(tmp_path / "runtime")
    seen = []
    async def returned():
        pass
    def observer(*v):
        seen.append(v)
        if failure == "raise":
            raise ValueError("PRIVATE CALLBACK CONTENT")
        return True if failure == "bool" else returned()
    with pytest.raises(sink._FreshAdmissionObserverFailed) as error:
        submit(runtime, tmp_path, observer)
    assert "PRIVATE CALLBACK CONTENT" not in str(error.value)
    roots = runtime.jobs.list_jobs()
    assert len(roots) == 1 and roots[0].status is JobStatus.QUEUED
    assert len(seen) == 1 and runtime.attempts.list_attempts() == []
    replay = submit(runtime, tmp_path, lambda *_: pytest.fail("no repeat observation"))
    assert replay["duplicate"] is True and replay["job_id"] == roots[0].job_id


def test_concurrent_same_operation_observes_only_actual_new_root(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    old._gate_pre_reads(runtime, parties=4)
    seen, lock = [], threading.Lock()
    def observer(*v):
        with lock:
            seen.append(v)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(pool.map(lambda _: submit(runtime, tmp_path, observer), range(4)))
    assert len({r["job_id"] for r in receipts}) == 1
    assert sum(not r["duplicate"] for r in receipts) == 1
    assert len(seen) == 1 and len(runtime.jobs.list_jobs()) == 1


def strict_call(runtime, tmp_path, observer, *, guard=None, frame=None):
    phase1fc._register_placement_union(runtime)
    return ingress.handle_frame(frame or hooks._strict_v2_frame(), runtime=runtime,
        grounding_provider=hooks.pr_a._FakeGrounding(),
        workspace_root=str(tmp_path / "workspaces"), service_state="READY",
        ceo_ingress_armed=True, strict_v2_admission=True,
        execution_binding_provider=phase1fc._v3_execution_binding,
        dialogue_source_provider=lambda *_: hooks._dialogue_source(),
        admission_guard=guard, fresh_admission_observer=observer)


def test_real_strict_ingress_retains_fresh_observation_after_guard_and_reobservations(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    seen = []
    def guard(_):
        seen.append("guard")
    def observer(root_id, command_id):
        assert runtime.store.find_event_by_command_id(command_id)["job_id"] == root_id
        seen.append("fresh")
    result = asyncio.run(strict_call(runtime, tmp_path, observer, guard=guard))
    assert seen == ["guard", "fresh"] and result["dispatched"] is False
    assert len(runtime.jobs.list_jobs()) == 1


def test_private_post_commit_error_survives_ingress_classification(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    def observer(*_):
        raise ValueError("PRIVATE CALLBACK CONTENT")
    with pytest.raises(sink._FreshAdmissionObserverFailed):
        asyncio.run(strict_call(runtime, tmp_path, observer))
    assert len(runtime.jobs.list_jobs()) == 1 and runtime.attempts.list_attempts() == []


def test_actual_admission_refusal_has_no_fresh_observation_or_root(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    seen = []
    def guard(_):
        raise ValueError("closed host")
    with pytest.raises(ingress.CeoIngressError):
        asyncio.run(strict_call(runtime, tmp_path, lambda *v: seen.append(v), guard=guard))
    assert seen == [] and runtime.jobs.list_jobs() == []


def test_caller_frame_cannot_supply_source_callback(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    frame = copy.deepcopy(hooks._strict_v2_frame())
    frame["fresh_admission_observer"] = "forged"
    seen = []
    with pytest.raises(ingress.CeoIngressError):
        asyncio.run(strict_call(runtime, tmp_path, lambda *v: seen.append(v), frame=frame))
    assert seen == [] and runtime.jobs.list_jobs() == []
