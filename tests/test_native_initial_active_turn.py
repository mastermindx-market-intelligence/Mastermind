"""Original dispatch exposes initial TX5 only after ACK; inert provider effects."""
import asyncio
import threading

import pytest

from control_plane.fresh_conversation import ConversationRefusal
from control_plane.operator_harness_contract import OperationId, OperationKind, OperationReceiptKind, operation_receipt_command_id
from control_plane.executive_runtime import StateConflict
from tests.test_fresh_conversation import case, preview, create, cleanup


async def _wait(event, task, failures):
    # Observe the owning coroutine as well as the inert phase. Admission can
    # fail before the adapter callback; report that cause instead of masking it
    # with a thread-pool wait timeout. The deadline is only a test harness bound.
    async with asyncio.timeout(30):
        while not event.is_set():
            if task.done():
                try:
                    await task
                except Exception as exc:
                    pytest.fail("initial dispatch ended before inert phase: "
                                + repr(failures) + " " + repr(exc))
                pytest.fail("initial dispatch completed without inert phase")
            await asyncio.sleep(0.01)


def test_original_dispatch_exposes_acknowledged_initial_turn_and_interrupts_during_collection(tmp_path, monkeypatch):
    async def run():
        service, runtime, owner, principal, request, adapters = case(tmp_path)
        prepared = await preview(owner, principal, request)
        acknowledged, allow_ack, collecting, allow_collect = [threading.Event() for _ in range(4)]
        interrupts, failures = [], []
        original_run = service.operator_supervisor._run_claimed
        def traced(*args, **kwargs):
            try:
                return original_run(*args, **kwargs)
            except Exception as exc:
                chain = []
                current = exc
                while current is not None:
                    chain.append((type(current).__name__, str(current)))
                    current = current.__cause__
                failures.append(chain)
                raise
        monkeypatch.setattr(service.operator_supervisor, "_run_claimed", traced)
        factory = service.operator_supervisor.adapter_factory
        def wrapped(loader):
            adapter = factory(loader)
            begin, collect = adapter.begin_turn, adapter.read_events
            def begin_turn(**kwargs):
                observed = begin(**kwargs)
                acknowledged.set()
                assert allow_ack.wait(10)
                return observed
            def read_events(*args, **kwargs):
                collecting.set()
                assert allow_collect.wait(10)
                return collect(*args, **kwargs)
            def interrupt(turn, *, operation_id):
                interrupts.append((turn, operation_id))
                allow_collect.set()
            adapter.begin_turn, adapter.read_events, adapter.interrupt_turn = begin_turn, read_events, interrupt
            return adapter
        monkeypatch.setattr(service.operator_supervisor, "adapter_factory", wrapped)
        task = asyncio.create_task(create(owner, principal, request, prepared))
        try:
            await _wait(acknowledged, task, failures)
            dispatch = service._native_operator_dispatch
            assert dispatch is not None and dispatch.active_turn is None
            assert dispatch.retained is None and not dispatch.started.done()
            with runtime.store.read() as connection:
                assert connection.execute(
                    "SELECT COUNT(*) FROM events WHERE event_type=? AND payload_json LIKE ?",
                    (OperationReceiptKind.APPLIED.value,
                     '%"operation_kind":"' + OperationKind.BEGIN_TURN.value + '"%')).fetchone()[0] == 0
            allow_ack.set()
            await _wait(collecting, task, failures)
            active = dispatch.active_turn
            assert active is not None and active.owner is service.operator_supervisor
            assert dispatch.retained is None and not dispatch.started.done()
            assert service._dispatch_lock.locked() and service._workspace_lock.locked()
            facts = service.operator_supervisor._require_active_native_turn(active)
            assert facts.attempt_id == active.turn.attempt_id
            receipt = runtime.events.get_event_by_command_id(
                operation_receipt_command_id(active.operation_id, OperationReceiptKind.APPLIED))
            assert receipt is not None
            # The public authenticated Stop route is separate work. This proves
            # its existing exact Runtime/orchestrator seam needs neither lock.
            operation = OperationId("ohf-op:fixture-initial-exact-stop")
            orchestrator = service.operator_supervisor._orchestrator(active.lease, active.adapter)
            await asyncio.to_thread(orchestrator.interrupt_turn, active.session, active.turn,
                                    operation_id=operation)
            try:
                result = await task
            except ConversationRefusal:
                pytest.fail("initial continuation failed: " + repr(failures))
            assert result["state"] == "CREATED"
            assert interrupts == [(active.turn, operation)]
            assert active.withdrawn and dispatch.active_turn is None and dispatch.retained is not None
            assert dispatch.retained.session == active.session
            with pytest.raises(StateConflict):
                service.operator_supervisor._require_active_native_turn(active)
            assert runtime.events.get_event_by_command_id(
                operation_receipt_command_id(operation, OperationReceiptKind.APPLIED)) is not None
        finally:
            allow_ack.set(); allow_collect.set()
            if not task.done():
                await asyncio.gather(task, return_exceptions=True)
            await cleanup(service)
    asyncio.run(run())


def test_initial_collection_failure_keeps_one_original_cleanup_owner(tmp_path, monkeypatch):
    async def run():
        service, runtime, owner, principal, request, adapters = case(tmp_path)
        prepared = await preview(owner, principal, request)
        supervisor = service.operator_supervisor
        factory, original_cleanup = supervisor.adapter_factory, supervisor._cleanup_failed_session
        cleanups, service_aborts, dispatches = [], [], []
        def wrapped(loader):
            adapter = factory(loader)
            def fail(*args, **kwargs):
                dispatch = service._native_operator_dispatch
                assert dispatch.active_turn is not None and dispatch.retained is None
                dispatches.append(dispatch)
                raise OSError("inert collection failed after acknowledged initial work")
            adapter.read_events = fail
            return adapter
        def counted_cleanup(**kwargs):
            dispatch = service._native_operator_dispatch
            assert dispatch is not None and dispatch.active_turn is None and dispatch.retained is None
            cleanups.append(kwargs["handle"])
            return original_cleanup(**kwargs)
        async def premature_abort(*args, **kwargs):
            service_aborts.append(True)
            raise AssertionError("service cannot own initial cleanup before retained return")
        monkeypatch.setattr(supervisor, "adapter_factory", wrapped)
        monkeypatch.setattr(supervisor, "_cleanup_failed_session", counted_cleanup)
        monkeypatch.setattr(supervisor, "abort_retained_native_job", premature_abort)
        try:
            with pytest.raises(ConversationRefusal):
                await create(owner, principal, request, prepared)
            # Existing owned coroutine settles cleanup before delivering failure.
            assert len(cleanups) == len(dispatches) == 1
            assert service_aborts == []
            assert dispatches[0].active_turn is None and dispatches[0].retained is None
            assert len(adapters) == 1 and adapters[0].stop_calls == 1
        finally:
            await cleanup(service)
    asyncio.run(run())


def test_late_active_publication_is_refused_after_synchronous_withdrawal(tmp_path, monkeypatch):
    from concurrent.futures import Future
    from types import SimpleNamespace
    from control_plane import executive_service as module
    from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor, ActiveNativeOperatorTurn
    from control_plane.executive_runtime import AttemptLease
    from test_dsh_native_runtime_result import _started_native, _turn, _orchestrator
    host = tmp_path/"host"
    host.mkdir()
    service, *_ = case(host)
    f = _started_native(tmp_path/"native", monkeypatch)
    turn, observation = _turn(f, candidate=False)
    _driver, _port, adapter, session = _orchestrator(f)
    supervisor = ExecutiveOperatorSupervisor(f.runtime, claimed_adapter_factory=lambda *a, **k: None,
                                              prompt_source=SimpleNamespace())
    service.runtime, service.operator_supervisor = f.runtime, supervisor
    active = ActiveNativeOperatorTurn(supervisor, f.job,
        AttemptLease(f.dispatch.attempt, f.dispatch.lease_token), session, adapter, turn,
        OperationId(observation.native_claim.operation_id))
    dispatch = module._NativeOperatorDispatch(f.job.job_id,
        f"coo-cycle:{f.root.job_id}:dispatch:{f.job.job_id}:attempt:1", Future(), Future())
    service._native_operator_dispatch = dispatch
    queued = []
    loop = SimpleNamespace(call_soon_threadsafe=lambda callback: queued.append(callback))
    with monkeypatch.context() as selected:
        selected.setattr(asyncio, "get_running_loop", lambda: loop)
        observer = service._native_initial_turn_observer(dispatch, supervisor)
    monkeypatch.setattr(module, "_NATIVE_ACTIVE_OBSERVATION_WAIT_SECONDS", 0.0)
    timeouts = []
    def invoke(present):
        try:
            observer(active, present)
        except TimeoutError:
            timeouts.append(present)
    thread = threading.Thread(target=invoke, args=(True,))
    thread.start(); thread.join(timeout=2)
    assert not thread.is_alive() and timeouts == [True] and len(queued) == 1
    # The original supervisor's finally must invalidate immediately even when
    # both event-loop acknowledgements have timed out. No callback is retried.
    active.withdraw()
    with pytest.raises(StateConflict, match="withdrawn"):
        supervisor._require_active_native_turn(active)
    thread = threading.Thread(target=invoke, args=(False,))
    thread.start(); thread.join(timeout=2)
    assert not thread.is_alive() and timeouts == [True, False] and len(queued) == 2
    for callback in queued:
        callback()
        assert dispatch.active_turn is None
    with pytest.raises(StateConflict, match="withdrawn"):
        supervisor._require_active_native_turn(active)
    assert dispatch.retained is None
