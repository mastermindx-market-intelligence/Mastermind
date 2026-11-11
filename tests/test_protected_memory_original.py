"""Genuine disposable Runtime terminal/receipts, no recipient auth or body read.

Reuses explicit installed/kernel/LINUX/process premises from the joined source
fixture. This proves read-only original integrity, not completed disclosure or
a newly authenticated caller, service/user recipient, grant, live study or E0.
"""
import asyncio
import json
import pwd
import os
import pytest
from tests.test_protected_memory_execution import joined
from tests.test_protected_memory_profile import configured
from tests.test_protected_memory_peer import installed
from tests.test_protected_memory_economic import economy
from control_plane import protected_memory_execution as execution
from control_plane import protected_memory_original as original
from control_plane.executive_supervisor import ExecutiveSupervisor
from control_plane.executive_runtime import StateConflict


@pytest.fixture
def completed(joined):
    runtime,job,lease,_,_,_,_,_,_=joined
    class Unused:
        inspector=execution.ProcessInspector()
        def __getattr__(self,name):raise AssertionError('ordinary adapter not used')
    asyncio.run(ExecutiveSupervisor(runtime,Unused(),worker_user=pwd.getpwuid(os.getuid()).pw_name).run_protected_memory_case(lease))
    return runtime,job,lease


def test_terminal_original_reference_is_readonly_without_active_lease_or_private_bytes(completed,monkeypatch):
    runtime,job,lease=completed
    before=runtime.events.list_events()
    from control_plane import paid_fabric_backend
    monkeypatch.setattr(paid_fabric_backend,'_private_read',lambda *_a:(_ for _ in ()).throw(AssertionError('no private read')))
    ref=original.completed_original_reference(runtime,lease.attempt.attempt_id)
    observed=original.current_reference(ref)
    assert observed['job_id']==job.job_id and observed['root_job_id']==job.root_job_id
    assert observed['original_recipient']['recipient_kind']=='native_broker_service' and observed['disclosure_authorized'] is False
    assert observed['retry_authorized'] is False and 'answer' not in json.dumps(observed)
    assert runtime.events.list_events()==before and runtime.attempts.get_attempt(lease.attempt.attempt_id).status.value=='COMPLETED'
    assert not hasattr(ref,'prepare') and not hasattr(ref,'start') and not hasattr(ref,'result')


@pytest.mark.parametrize('damage',['preinput','result','parent','phase','flags','missing-original'])
def test_existing_immutable_runtime_refuses_original_rebinding_before_reference_changes(completed,damage):
    runtime,job,lease=completed
    ref=original.completed_original_reference(runtime,lease.attempt.attempt_id)
    before=original.current_reference(ref)
    # Retain the actual earlier boundary; do not disable immutable-event or
    # terminal-state guards to manufacture a corrupt Runtime in this fixture.
    with pytest.raises(StateConflict):
        with runtime.store.transaction() as con:
            if damage=='parent':con.execute('UPDATE jobs SET parent_job_id=? WHERE job_id=?',(job.job_id,job.job_id))
            elif damage=='phase':con.execute("UPDATE attempts SET status='RUNNING' WHERE attempt_id=?",(lease.attempt.attempt_id,))
            elif damage=='missing-original':con.execute("DELETE FROM events WHERE event_type='MEMORY_ECONOMIC_ADMISSION_ATTEMPT'")
            else:
                kind='MEMORY_ECONOMIC_ADMISSION_ATTEMPT' if damage=='preinput' else 'MEMORY_ORIGINAL_RESULT_RETAINED'
                row=con.execute('SELECT event_id,payload_json FROM events WHERE event_type=?',(kind,)).fetchone()
                value=json.loads(row['payload_json'])
                if damage=='preinput':value['pre_input']['native_source_locator']['root_id']='foreign-original'
                elif damage=='result':value['result_sha256']='e'*64
                else:value['verification']['authenticated']=0
                con.execute('UPDATE events SET payload_json=? WHERE event_id=?',(json.dumps(value),row['event_id']))
    assert original.current_reference(ref)==before
    assert original.current_reference(original.completed_original_reference(runtime,lease.attempt.attempt_id))==before


def test_additional_mixed_original_result_receipt_is_rejected_without_rewriting_original(completed):
    runtime,job,lease=completed
    ref=original.completed_original_reference(runtime,lease.attempt.attempt_id)
    with runtime.store.transaction() as con:
        row=con.execute("SELECT payload_json FROM events WHERE event_type='MEMORY_ORIGINAL_RESULT_RETAINED'").fetchone()
        payload=json.loads(row['payload_json']);payload['result_sha256']='e'*64
        runtime.store.append_event(con,aggregate_type='attempt',aggregate_id=lease.attempt.attempt_id,
            event_type='MEMORY_ORIGINAL_RESULT_RETAINED',job_id=job.job_id,attempt_id=lease.attempt.attempt_id,
            worker_id=lease.attempt.worker_id,quota_class=lease.attempt.quota_class,actor='supervisor',
            command_id='inert-conflicting-result-observation',payload=payload)
    with pytest.raises(original.OriginalReferenceRefused):original.current_reference(ref)


@pytest.mark.parametrize('shape',['dict','clone','subclass'])
def test_no_dto_or_clone_is_original_reference_permission(completed,shape):
    runtime,_,lease=completed
    ref=original.completed_original_reference(runtime,lease.attempt.attempt_id)
    if shape=='dict':ref=original.current_reference(ref)
    elif shape=='clone':ref=object.__new__(original.OriginalMemoryReference)
    else:
        class Foreign(original.OriginalMemoryReference):pass
        ref=object.__new__(Foreign)
    with pytest.raises(original.OriginalReferenceRefused):original.current_reference(ref)
