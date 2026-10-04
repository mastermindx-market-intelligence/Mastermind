"""The service reconciles terminal lost returns without replaying worker leases."""
import asyncio

import pytest

from control_plane.ceo_intent import submit_intent
from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_runtime import JobPayload, Runtime, StateConflict
from control_plane.executive_service import ExecutiveControlService
from tests.test_executive_os_phase1fc import _register, _v2_intent
from tests.test_executive_service import _config


def _failed_planner(tmp_path, *, terminal=True, marker=True):
    runtime = Runtime.at(tmp_path / "runtime")
    _register(runtime)
    intent = _v2_intent(execution_contract={
        "requested_authorities": ["READ"], "attempt_limit": 1,
    })
    root_id = submit_intent(runtime, intent)["job_id"]
    planner = runtime.jobs.create_cycle_planner(
        root_id, command_id=f"coo-cycle:{root_id}:create-planner:0",
    )
    command = f"coo-cycle:{root_id}:dispatch:{planner.job_id}:attempt:1"
    claimed = runtime.attempts.dispatch_cycle_job(
        planner.job_id, command_id=command, lease_owner="old-service-owner",
    )
    assert claimed is not None and claimed.claimed_now
    if terminal:
        runtime.attempts.fail_attempt(
            claimed.attempt.attempt_id,
            fence_generation=claimed.attempt.fence_generation,
            lease_token=claimed.lease_token,
            payload=JobPayload(summary="Broker refused before provider launch"),
        )
    if marker:
        runtime.jobs.record_cycle_dispatch_effect_unknown(
            root_id, selected_job_id=planner.job_id, dispatch_command_id=command,
        )
    return runtime, root_id, planner.job_id, command, claimed.attempt.attempt_id


def _facts(runtime):
    with runtime.store.read() as connection:
        return {
            table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table}")]
            for table in ("jobs", "attempts", "worker_quota_classes",
                          "harness_session_epochs", "process_generations")
        }


def test_restarted_service_reconciles_terminal_then_blocks_without_provider(tmp_path):
    _runtime, root_id, job_id, command, attempt_id = _failed_planner(tmp_path)
    read_only = Runtime.at(tmp_path / "runtime", create=False)
    observed = read_only.attempts.terminal_cycle_dispatch_outcome(job_id, command_id=command)
    assert observed.outcome == "TERMINAL" and observed.lease_token is None
    reopened = Runtime.at(tmp_path / "runtime")
    before = _facts(reopened)
    service = ExecutiveControlService(_config(tmp_path / "host"))
    service.runtime = reopened
    binding_reads = []

    def bound(job):
        binding_reads.append(job.job_id)
        return reopened.jobs.get_job(root_id)

    def forbidden(*args, **kwargs):
        raise AssertionError("terminal observation must not select or launch a worker")

    service._require_bound_coo_job = bound
    service._require_supervisor = forbidden
    service._require_operator_supervisor = forbidden
    service._require_coo_workspace = forbidden
    assert service.instance_id != "old-service-owner"
    cycle = CooCycle(reopened, dispatcher=lambda job, cmd: asyncio.run(
        service._dispatch_cycle_job_exact(job, cmd)
    ))
    first = cycle.run_once(root_id)
    assert first.action == "DISPATCHED"
    assert first.selected_job_id == job_id
    assert first.command_id == command
    assert binding_reads == [job_id]
    assert reopened.jobs.pending_cycle_dispatch_effect_unknown(root_id) is None
    resolution = reopened.store.get_event_by_command_id(command + ":reconciled")
    assert resolution is not None
    assert resolution.event_type == "COO_DISPATCH_RECONCILED"
    assert resolution.attempt_id == attempt_id
    second = cycle.run_once(root_id)
    assert second.action == "BLOCKED"
    assert second.command_id == f"coo-cycle:{root_id}:block:plan_terminal_adverse:{job_id}"
    assert _facts(reopened) == before
    assert len(reopened.attempts.list_attempts(job_id)) == 1
    assert service._dispatch_tasks == {}
    # The cycle replays its block, without revisiting the terminal reader.
    assert cycle.run_once(root_id) == second
    assert binding_reads == [job_id]


@pytest.mark.parametrize("fault", ["missing-marker", "active", "wrong-command", "foreign-job", "resolved"])
def test_terminal_reader_refuses_unbound_or_resolved_history_without_writes(tmp_path, fault):
    runtime, root_id, job_id, command, _attempt_id = _failed_planner(
        tmp_path, terminal=fault != "active", marker=fault != "missing-marker",
    )
    if fault == "resolved":
        receipt = runtime.attempts.terminal_cycle_dispatch_outcome(job_id, command_id=command)
        runtime.jobs.reconcile_cycle_dispatch_effect(
            root_id, selected_job_id=job_id, dispatch_command_id=command, receipt=receipt,
        )
    before = _facts(runtime)
    events_before = runtime.events.list_events()
    with pytest.raises(StateConflict):
        runtime.attempts.terminal_cycle_dispatch_outcome(
            root_id if fault == "foreign-job" else job_id,
            command_id=command + "-wrong" if fault == "wrong-command" else command,
        )
    assert _facts(runtime) == before
    assert runtime.events.list_events() == events_before


def test_resolved_terminal_reader_requires_exact_reconciliation_and_stays_read_only(tmp_path):
    runtime, root_id, job_id, command, attempt_id = _failed_planner(tmp_path)
    with pytest.raises(StateConflict):
        runtime.attempts.reconciled_terminal_cycle_dispatch_outcome(job_id, command_id=command)
    receipt = runtime.attempts.terminal_cycle_dispatch_outcome(job_id, command_id=command)
    runtime.jobs.reconcile_cycle_dispatch_effect(root_id, selected_job_id=job_id,
                                                dispatch_command_id=command, receipt=receipt)
    before, events = _facts(runtime), runtime.events.list_events()
    observed = runtime.attempts.reconciled_terminal_cycle_dispatch_outcome(job_id, command_id=command)
    assert observed.attempt.attempt_id == attempt_id
    assert observed.outcome == "TERMINAL" and observed.lease_token is None
    assert observed.claimed_now is False
    assert _facts(runtime) == before and runtime.events.list_events() == events
    with pytest.raises(StateConflict):
        runtime.attempts.terminal_cycle_dispatch_outcome(job_id, command_id=command)


@pytest.mark.parametrize("malformed", [False, True])
def test_selector_validates_terminal_block_before_current_policy_binding(tmp_path, malformed):
    runtime, root_id, job_id, command, _attempt_id = _failed_planner(tmp_path)
    receipt = runtime.attempts.terminal_cycle_dispatch_outcome(job_id, command_id=command)
    runtime.jobs.reconcile_cycle_dispatch_effect(root_id, selected_job_id=job_id,
                                                dispatch_command_id=command, receipt=receipt)
    def forbidden(*args):
        raise AssertionError("blocked root cannot reach current dispatch binding or provider")
    assert CooCycle(runtime, dispatcher=forbidden).run_once(root_id).action == "BLOCKED"
    if malformed:
        with runtime.store.transaction() as conn:
            # Test the reader against deliberately corrupted historical bytes.
            conn.execute("DROP TRIGGER events_are_immutable_update")
            conn.execute("UPDATE events SET actor='foreign' WHERE event_type='COO_CYCLE_BLOCKED' AND job_id=?", (root_id,))
    service = ExecutiveControlService(_config(tmp_path / "host"))
    service.runtime = runtime
    service._is_bound_coo_root = forbidden
    if malformed:
        with pytest.raises(StateConflict):
            service._next_bound_coo_root()
    else:
        assert service._next_bound_coo_root() is None
