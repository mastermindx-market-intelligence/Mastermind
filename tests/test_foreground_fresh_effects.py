"""Closure between admission, executor scheduling, and transport write boundaries."""
import asyncio
from types import SimpleNamespace
import pytest
from control_plane import foreground_operation as scope
from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor
from control_plane.executive_worker_broker import WorkerBrokerClient
from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
from control_plane.remote_worker_transport import TransportEffect, TransportError
from tests.test_foreground_operation import frame, admit
from tests.test_foreground_operator_completion import service_at
from tests.test_foreground_only_execution import foreground_only
from tests.test_remote_worker_broker_client import _binding, _Paths, _Writer, _Reader, IDENTITY


def test_queued_physical_cycle_closes_before_thread_entry(tmp_path,monkeypatch):
    async def run():
        s=service_at(tmp_path);foreground_only(s,monkeypatch)
        f=frame('physical-cycle-delay')
        async with scope._session_bridge_foreground_dispatch(s.runtime,f,lambda:None) as op:
            async with s._foreground_cycle_scope(op):
                root=(await admit(s.runtime,tmp_path,op,f))['job_id']
                monkeypatch.setattr(s,'_require_coo_worker_composed',lambda:None)
                monkeypatch.setattr(s,'_is_bound_coo_root',lambda _:True)
                monkeypatch.setattr(s,'_require_initial_coo_workspace',lambda _:None)
                async def nothing(*args):return None
                monkeypatch.setattr(s,'_prepare_maintenance_root_workspace',nothing)
                monkeypatch.setattr(s,'_reconcile_unowned_cycle_attempts',nothing)
                monkeypatch.setattr(s,'_native_cycle_once',nothing)
                async def delayed(function,*args,**kwargs):
                    op._mark_source_closed()
                    return await asyncio.to_thread(function,*args,**kwargs)
                monkeypatch.setattr(s,'_run_physical',delayed)
                with pytest.raises(scope.ForegroundOperationClosed):await s._run_coo_cycle(root)
                assert len(s.runtime.jobs.list_jobs())==1
                assert s.runtime.attempts.list_attempts()==[]
    asyncio.run(run())


def test_cycle_closes_during_reads_before_planner_mutation(tmp_path,monkeypatch):
    async def run():
        s=service_at(tmp_path);f=frame('cycle-read-delay')
        async with scope._session_bridge_foreground_dispatch(s.runtime,f,lambda:None) as op:
            root=(await admit(s.runtime,tmp_path,op,f))['job_id']
            original=s.runtime.jobs.list_jobs
            def close_during_read(*a,**kw):
                result=original(*a,**kw);op._mark_source_closed();return result
            monkeypatch.setattr(s.runtime.jobs,'list_jobs',close_during_read)
            with pytest.raises(scope.ForegroundOperationClosed):
                CooCycle(s.runtime,before_admission=op.require_root).run_once(root)
            assert len(original())==1 and s.runtime.attempts.list_attempts()==[]
    asyncio.run(run())


def test_claim_is_retained_when_operator_thread_starts_after_close(tmp_path,monkeypatch):
    async def run():
        s=service_at(tmp_path);f=frame('operator-thread-delay')
        async with scope._session_bridge_foreground_dispatch(s.runtime,f,lambda:None) as op:
            root=(await admit(s.runtime,tmp_path,op,f))['job_id']
            planner=s.runtime.jobs.create_cycle_planner(root,command_id=f'coo-cycle:{root}:create-planner:0')
            supervisor=ExecutiveOperatorSupervisor(s.runtime,
                adapter_factory=lambda *a:pytest.fail('closed thread reached adapter'),prompt_source=SimpleNamespace())
            original=asyncio.to_thread
            async def delayed(function,*a,**kw):
                assert len(s.runtime.attempts.list_attempts())==1
                op._mark_source_closed()
                return await original(function,*a,**kw)
            monkeypatch.setattr(asyncio,'to_thread',delayed)
            with pytest.raises(scope.ForegroundOperationClosed):
                await supervisor.start_cycle_job(planner.job_id,command_id=f'coo-cycle:{root}:dispatch:{planner.job_id}:attempt:1')
            attempts=s.runtime.attempts.list_attempts()
            assert len(attempts)==1 and attempts[0].status.value=='CLAIMED'
            with s.runtime.store.read() as c:
                assert c.execute('SELECT count(*) FROM harness_session_epochs').fetchone()[0]==0
    asyncio.run(run())


@pytest.mark.parametrize('transport',['unix','tls'])
@pytest.mark.parametrize('operation',['ohf-start','ohf-resume','ohf-begin-turn'])
def test_connection_delay_closure_writes_no_fresh_effect_bytes(tmp_path,monkeypatch,transport,operation):
    async def run():
        s=service_at(tmp_path);f=frame('connection-delay')
        async with scope._session_bridge_foreground_dispatch(s.runtime,f,lambda:None) as op:
            root=(await admit(s.runtime,tmp_path,op,f))['job_id']
            writer=_Writer()
            async def delayed(*a,**kw):
                op._mark_source_closed()
                return _Reader(b''),writer
            if transport=='unix':
                client=WorkerBrokerClient(tmp_path/'unused.sock')
                monkeypatch.setattr(asyncio,'open_unix_connection',delayed)
            else:
                paths=_Paths(tmp_path/'ca',tmp_path/'cert',tmp_path/'key')
                for path in (paths.ca,paths.cert,paths.key):path.write_bytes(b'inert fixture')
                client=RemoteWorkerBrokerClient(_binding(paths),IDENTITY,allowed_operations={operation})
                monkeypatch.setattr(client,'_open_connection',delayed)
            with pytest.raises(TransportError) as error:
                await client.request(operation,{},before_write=lambda *_:op.require_root(root))
            assert error.value.code=='foreground_start_refused'
            assert error.value.classification is TransportEffect.NO_EFFECT
            assert not writer.written and writer.closed
    asyncio.run(run())


def test_source_state_conflict_does_not_become_a_durable_cycle_block(tmp_path):
    from control_plane.executive_runtime import StateConflict
    async def run():
        s=service_at(tmp_path);f=frame('missing-source-owner')
        async with scope._session_bridge_foreground_dispatch(s.runtime,f,lambda:None) as op:
            root=(await admit(s.runtime,tmp_path,op,f))['job_id']
            before=s.runtime.events.list_events(job_id=root)
            def missing_owner(_):raise StateConflict('original owner gone')
            with pytest.raises(StateConflict,match='original owner gone'):
                CooCycle(s.runtime,before_admission=missing_owner).run_once(root)
            assert s.runtime.events.list_events(job_id=root)==before
            assert len(s.runtime.jobs.list_jobs())==1
    asyncio.run(run())


def test_close_during_canonical_prewrite_read_prevents_transmission(tmp_path,monkeypatch):
    import threading
    async def run():
        s=service_at(tmp_path);f=frame('canonical-read-delay')
        async with scope._session_bridge_foreground_dispatch(s.runtime,f,lambda:None) as op:
            root=(await admit(s.runtime,tmp_path,op,f))['job_id']
            entered,release=threading.Event(),threading.Event()
            original=s.runtime.store.find_event_by_command_id
            def delayed_read(*args,**kwargs):
                value=original(*args,**kwargs);entered.set()
                assert release.wait(3)
                return value
            monkeypatch.setattr(s.runtime.store,'find_event_by_command_id',delayed_read)
            writer=_Writer()
            async def connected(*a,**kw):return _Reader(b''),writer
            monkeypatch.setattr(asyncio,'open_unix_connection',connected)
            client=WorkerBrokerClient(tmp_path/'unused.sock')
            task=asyncio.create_task(asyncio.to_thread(client.request_sync,'ohf-start',{},
                before_write=lambda *_:op.require_root(root)))
            try:
                assert await asyncio.to_thread(entered.wait,3)
                op._mark_source_closed()
            finally:release.set()
            with pytest.raises(TransportError) as error:await task
            assert error.value.classification is TransportEffect.NO_EFFECT
            assert not writer.written and writer.closed
    asyncio.run(run())


def test_bound_proxy_carries_guard_for_start_resume_turn_but_allows_cleanup():
    from control_plane.remote_codex_operator_adapter import RemoteCodexOperatorAdapter
    from control_plane.operator_harness_contract import OperationId, SessionEpochRef, ProcessGenerationRef, TurnRef
    class BoundaryReached(Exception):pass
    class Client:
        calls=[]
        def request_sync(self,operation,payload,**kwargs):
            guard=kwargs.get('before_write')
            if operation in {'ohf-start','ohf-resume','ohf-begin-turn'}:
                assert callable(guard);guard(operation,payload)
            else:assert guard is None
            self.calls.append(operation)
            raise BoundaryReached()
    client=Client();adapter=RemoteCodexOperatorAdapter(client,turn_input_loader=lambda _:'bounded')
    live=True
    def require_live():
        if not live:raise scope.ForegroundOperationClosed()
    adapter.bind_fresh_effect_guard(require_live,attempt_id='attempt')
    epoch=SessionEpochRef('epoch','attempt','worker',1)
    generation=ProcessGenerationRef('generation','epoch',1,'worker')
    with pytest.raises(BoundaryReached):
        adapter.start_session(operation_id=OperationId('ohf-op:start'),requested=None,epoch=epoch,generation=generation)
    # The original proxy START reached its mocked boundary; closure blocks the turn.
    live=False
    with pytest.raises(scope.ForegroundOperationClosed):
        adapter.begin_turn(operation_id=OperationId('ohf-op:turn'),turn=TurnRef('turn','epoch','generation','attempt'),generation=generation,launch=None)
    with pytest.raises(scope.ForegroundOperationClosed):
        adapter.resume_session(operation_id=OperationId('ohf-op:resume'),requested=None,epoch=epoch,generation=generation,provider_session=None)
    with pytest.raises(BoundaryReached):
        adapter.graceful_stop(generation,operation_id=OperationId('ohf-op:stop'))
    assert client.calls==['ohf-start','ohf-stop']
    # A frozen callback cannot be reused for changed generation/turn bytes.
    live=True
    payload={'epoch':{'attempt_id':'attempt','session_epoch_id':'epoch'},
             'generation':{'session_epoch_id':'epoch','process_generation_id':'generation'}}
    guard=adapter._fresh_write_options('ohf-start',payload)['before_write']
    with pytest.raises(Exception,match='bytes changed'):
        guard('ohf-start',{**payload,'generation':{**payload['generation'],'process_generation_id':'different'}})
