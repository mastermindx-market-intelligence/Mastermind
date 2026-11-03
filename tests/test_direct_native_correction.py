"""H7: actual Runtime admission, fenced correction and parent acknowledgment.
Physical process/UID observations remain the existing joined fixture seams.
"""
import asyncio
import pytest
from control_plane import direct_native_execution as dn, executive_runtime as er
from tests.test_direct_native_supervisor_runtime_join import joined, _execution, _complete


def test_running_correction_is_fenced_and_not_terminal_or_consumed(joined):
    runtime,job,access,_,adapter,supervisor=joined
    async def run():
        active=await supervisor.start_direct_native_job(job.job_id,access=_execution(access))
        attempt=runtime.attempts.list_attempts(job.job_id)[0]
        selected=dict(work_ref=access.work_ref,job_id=job.job_id,attempt_id=attempt.attempt_id,
                      fence_generation=attempt.fence_generation,operation_key='correct-original')
        request=runtime.request_direct_native_correction(selected,access=access)
        assert request['status']=='CANCEL_REQUESTED'
        assert runtime.jobs.get_job(job.job_id).status.value=='CANCEL_REQUESTED'
        assert runtime.attempts.get_attempt(attempt.attempt_id).status.value=='CANCEL_REQUESTED'
        assert runtime.request_direct_native_correction(selected,access=access)==request
        return selected
    asyncio.run(run())


@pytest.mark.parametrize('fault',['foreign-parent','stale-fence','changed-generation'])
def test_correction_refuses_foreign_or_stale_without_writing(joined,fault):
    runtime,job,access,generation,adapter,supervisor=joined
    async def run():
        await supervisor.start_direct_native_job(job.job_id,access=_execution(access))
        attempt=runtime.attempts.list_attempts(job.job_id)[0]
        selected=dict(work_ref=access.work_ref,job_id=job.job_id,attempt_id=attempt.attempt_id,
                      fence_generation=attempt.fence_generation,operation_key='correct-original')
        rejected=access
        if fault=='foreign-parent':rejected=dn._issue_access('a'*64,access.work_ref,generation[0],lambda:generation[0])
        if fault=='stale-fence':selected['fence_generation']+=1
        if fault=='changed-generation':generation[0]='f'*64
        with pytest.raises((er.StateConflict,ValueError)):
            runtime.request_direct_native_correction(selected,access=rejected)
        assert runtime.jobs.get_job(job.job_id).status.value in {'RUNNING','CHECKPOINTED'}
    asyncio.run(run())


def test_completed_attempt_wins_correction_without_new_cancel(joined):
    runtime,job,access,_,adapter,supervisor=joined
    completed=_complete(joined)
    selected=dict(work_ref=access.work_ref,job_id=job.job_id,attempt_id=completed.attempt.attempt_id,
                  fence_generation=completed.attempt.fence_generation,operation_key='late-correction')
    result=runtime.request_direct_native_correction(selected,access=access)
    assert result['status']=='COMPLETED'
    with runtime.store.read() as connection:
        assert connection.execute("SELECT count(*) FROM events WHERE event_type='JOB_CANCEL_REQUESTED'").fetchone()[0]==0


def test_running_correction_settles_actual_attempt_and_parent_consumes_typed_cancelled(joined):
    from tests.test_fabric_result_projection import _bound_reader, _release
    runtime,job,access,generation,adapter,supervisor=joined
    async def run():
        active=await supervisor.start_direct_native_job(job.job_id,access=_execution(access))
        attempt=active.lease.attempt
        selected=dict(work_ref=access.work_ref,job_id=job.job_id,attempt_id=attempt.attempt_id)
        request=dict(selected,fence_generation=attempt.fence_generation,operation_key='correct-original')
        assert runtime.request_direct_native_correction(request,access=access)['status']=='CANCEL_REQUESTED'
        keeper,namespace,binding,reader=_bound_reader(runtime)
        try:
            assert reader.read_direct_native_result_bounded(selected,access=access)['availability']=='UNAVAILABLE'
            settled=await supervisor.finish_job(active)
            assert settled.job.status.value=='CANCELLED'
            terminal=reader.read_direct_native_result_bounded(selected,access=access)
            assert terminal['availability']=='AVAILABLE',terminal
            assert terminal['result']['terminal_status']=='CANCELLED'
            assert terminal['consumption']['state']=='UNCONSUMED'
            command=dict(selected,result_digest=terminal['result']['result_digest'],operation_key='ack-cancelled-original')
            consumed=runtime.consume_direct_native_result(command,access=access)
            assert consumed['state']=='CONSUMED'
            assert runtime.consume_direct_native_result(command,access=access)==consumed
            assert reader.read_direct_native_result_bounded(selected,access=access)['consumption']==consumed
            assert adapter.start_count==1
        finally:_release(keeper,binding)
    asyncio.run(run())


@pytest.mark.parametrize('unsupported',[False,True])
def test_bound_adapter_cancel_called_once_unknown_or_unsupported_never_becomes_terminal(joined,unsupported):
    from tests.test_fabric_result_projection import _bound_reader,_release
    runtime,job,access,_,adapter,supervisor=joined
    async def run():
        active=await supervisor.start_direct_native_job(job.job_id,access=_execution(access))
        selected=dict(work_ref=access.work_ref,job_id=job.job_id,attempt_id=active.lease.attempt.attempt_id)
        runtime.request_direct_native_correction(dict(selected,fence_generation=active.lease.attempt.fence_generation,operation_key='correct-once'),access=access)
        release=asyncio.Event();called=asyncio.Event();original=adapter.collect_result;calls=[]
        async def collect(ref):await release.wait();return await original(ref)
        async def cancel(ref,reason):
            calls.append(ref);called.set()
            if unsupported:raise NotImplementedError('physical fixture lacks supported interrupt')
            raise OSError('physical fixture lost cancel response')
        adapter.collect_result=collect;adapter.cancel=cancel
        pending=asyncio.create_task(supervisor.finish_job(active))
        await asyncio.wait_for(called.wait(),2)
        await asyncio.sleep(supervisor.heartbeat_interval_seconds*3)
        assert calls==[active.process_ref]
        assert runtime.jobs.get_job(job.job_id).status.value=='CANCEL_REQUESTED'
        keeper,namespace,binding,reader=_bound_reader(runtime)
        try:assert reader.read_direct_native_result_bounded(selected,access=access)['availability']=='UNAVAILABLE'
        finally:_release(keeper,binding)
        with runtime.store.read() as connection:
            rows=connection.execute("SELECT payload_json FROM events WHERE event_type='DIRECT_NATIVE_CANCEL_CALL_UNAVAILABLE'").fetchall()
            import json
            assert len(rows)==1 and json.loads(rows[0][0])['reason']==('UNSUPPORTED' if unsupported else 'EFFECT_UNKNOWN')
        release.set()
        settled=await pending
        assert settled.job.status.value=='CANCELLED' # only AFTER the later genuine fixture exit/seal
        assert calls==[active.process_ref]
    asyncio.run(run())


def test_reentered_finish_uses_retained_original_cancel_intent_without_second_adapter_call(joined):
    runtime,job,access,_,adapter,supervisor=joined
    async def run():
        active=await supervisor.start_direct_native_job(job.job_id,access=_execution(access))
        attempt=active.lease.attempt
        selected=dict(work_ref=access.work_ref,job_id=job.job_id,attempt_id=attempt.attempt_id)
        runtime.request_direct_native_correction(dict(selected,fence_generation=attempt.fence_generation,operation_key='correct-original'),access=access)
        assert runtime.reserve_direct_native_cancel_call(attempt.attempt_id,fence_generation=attempt.fence_generation,lease_token=active.lease.lease_token)
        calls=[];actual_cancel=adapter.cancel
        async def counted_cancel(ref,reason):
            calls.append(ref)
            return await actual_cancel(ref,reason)
        adapter.cancel=counted_cancel
        await adapter.cancel(active.process_ref,'original fixture adapter call before interrupted observation')
        # Reopen the actual existing Event store, then enter a new collection
        # loop with the same exact lease/ProcessRef. No provider/start is replayed.
        supervisor.runtime=er.Runtime.at(runtime.store.root,create=False,existing_writable=True,
            clock=lambda:supervisor._joined_clock[0])
        entered=asyncio.Event();release=asyncio.Event();actual_collect=adapter.collect_result
        async def collect(ref):
            entered.set();await release.wait()
            return await actual_collect(ref)
        adapter.collect_result=collect
        pending=asyncio.create_task(supervisor.finish_job(active))
        await entered.wait()
        await asyncio.sleep(supervisor.heartbeat_interval_seconds*3)
        assert calls==[active.process_ref]
        assert supervisor.runtime.jobs.get_job(job.job_id).status.value=='CANCEL_REQUESTED'
        release.set()
        settled=await pending
        assert settled.job.status.value=='CANCELLED'
        assert calls==[active.process_ref] and adapter.start_count==1
        with supervisor.runtime.store.read() as connection:
            assert connection.execute("SELECT count(*) FROM events WHERE event_type='DIRECT_NATIVE_CANCEL_CALL_STARTED'").fetchone()[0]==1
    asyncio.run(run())
