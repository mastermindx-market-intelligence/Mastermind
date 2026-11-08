"""Original nominal message custody; the native creator read is an explicit unit seam.

No provider, native process, signed-in host or enabled native policy is claimed.
The existing real fresh admission/source/argument/root owner runs unchanged.
"""
import asyncio
import copy
import json

import pytest

from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor
from control_plane.executive_runtime import StateConflict
from control_plane.foreground_operation import current_foreground_operation, ForegroundOperationRefusal
from control_plane.fresh_conversation import ConversationRefusal
from control_plane.fresh_conversation_admission import (
    require_native_initial_message, require_initial_native_claim,
)
from control_plane.native_conversation_result import DSH_NATIVE_RESULT_CONTRACT
from control_plane.executive_agent_capabilities import DSH_NATIVE_CONVERSATION_PROFILE_ID
from tests.test_fresh_conversation import case, preview, create, cleanup
from tests.test_fresh_conversation_admission import interrupted


@pytest.mark.parametrize("change", [
    None, "legacy_creator", "copied_source", "missing_source", "wrong_owner",
    "message", "response", "operation_key", "closed",
])
def test_native_initial_input_rejoins_original_request_without_planner_instruction(tmp_path, monkeypatch, change):
    async def run():
        service, runtime, owner, principal, request, adapters = case(tmp_path)
        prepared = await preview(owner, principal, request)
        original = service._run_coo_cycle
        inspected = []
        async def inspect(root_id):
            outcome = await original(root_id)
            if outcome.action == "PLANNER_CREATED":
                child = runtime.jobs.get_job(outcome.selected_job_id)
                operation = current_foreground_operation()
                source = operation._fresh_conversation_creation_source[0]
                assert operation._root == root_id
                # check() is intentionally pre-commit and cannot be reused here.
                with pytest.raises(ValueError):
                    source.check()
                with monkeypatch.context() as m:
                    if change != "legacy_creator":
                        m.setattr(runtime.jobs, "assert_native_conversation_execution", lambda job_id: dict(
                            root_job_id=root_id, job_id=child.job_id,
                            result_contract=DSH_NATIVE_RESULT_CONTRACT))
                    selected_supervisor = service.operator_supervisor
                    if change == "copied_source":
                        m.setattr(operation, "_fresh_conversation_creation_source",
                                  (copy.copy(source), operation._fresh_conversation_creation_source[1]))
                    elif change == "missing_source":
                        m.setattr(operation, "_fresh_conversation_creation_source", None)
                    elif change == "wrong_owner":
                        selected_supervisor = ExecutiveOperatorSupervisor(runtime,
                            adapter_factory=lambda _: None, prompt_source=service.operator_supervisor.prompt_source)
                    elif change in {"message", "response"}:
                        root = runtime.jobs.get_job(root_id)
                        value = json.loads(root.objective)
                        value[change] += " changed"
                        with runtime.store.transaction() as connection:
                            connection.execute("UPDATE jobs SET objective=? WHERE job_id=?",
                                               (json.dumps(value, ensure_ascii=False, separators=(",", ":")), root_id))
                    elif change == "operation_key":
                        m.setattr(operation, "_operation_key", "foreign-operation")
                    elif change == "closed":
                        operation._mark_source_closed()
                    if change is None:
                        text = require_native_initial_message(runtime, child, operation,
                                                              supervisor=selected_supervisor)
                        assert text == request["message"]
                        assert text.startswith("  ") and text.endswith("  ") and "新对话" in text
                        assert "sealed result summary" not in text
                    else:
                        with pytest.raises((ValueError, StateConflict, ForegroundOperationRefusal)):
                            require_native_initial_message(runtime, child, operation,
                                                           supervisor=selected_supervisor)
                inspected.append(True)
                raise OSError("fixture stops after original source inspection; no claim/provider")
            return outcome
        monkeypatch.setattr(service, "_run_coo_cycle", inspect)
        try:
            with pytest.raises(ConversationRefusal):
                await create(owner, principal, request, prepared)
            assert inspected == [True]
            assert not runtime.attempts.list_attempts() and not adapters
        finally:
            await cleanup(service)
    asyncio.run(run())


def test_native_fresh_claim_keeps_original_live_request_fence(tmp_path, monkeypatch):
    async def run():
        service, runtime, root = await interrupted(tmp_path, monkeypatch, before_child=False)
        with pytest.raises((StateConflict, ValueError)):
            require_initial_native_claim(runtime.store, root_job_id=root.job_id,
                role="plan", profile=DSH_NATIVE_CONVERSATION_PROFILE_ID)
        assert not runtime.attempts.list_attempts()
    asyncio.run(run())


@pytest.mark.parametrize("resumed", [False, True])
def test_native_results_reuse_original_current_writer_owner(tmp_path, monkeypatch, resumed):
    from test_dsh_native_runtime_result import _started_native, _turn
    from test_dsh_native_runtime_resume import _release, _resume
    f = _started_native(tmp_path, monkeypatch)
    turn, observation = _turn(f)
    f.runtime.operator_harness.seal_native_conversation_result(turn=turn, observation=observation, **f.lease)
    if resumed:
        _release(f)
        f = _resume(f)
        turn, observation = _turn(f, 2)
        f.runtime.operator_harness.seal_native_conversation_result(turn=turn, observation=observation, **f.lease)
    facts = f.runtime.current_harness_binding_source(f.epoch.attempt_id)
    assert facts.job_id == f.job.job_id and facts.worker_id == f.epoch.worker_id
    assert facts.session_epoch_id == f.epoch.session_epoch_id
    assert facts.process_generation_id == f.generation.process_generation_id
    assert facts.provider_session_id == f.session_id and facts.provider == "acp"
    with f.runtime.store.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM events WHERE event_type='ORCHESTRATION_ROLE_RESULT_SEALED'").fetchone()[0] == 0
