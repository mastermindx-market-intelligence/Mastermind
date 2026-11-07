"""Actual isolated Runtime transactions/source owner, not installed grant proof."""
from concurrent.futures import ThreadPoolExecutor
import dataclasses
import json
import subprocess
import threading
import pytest
from common.executive_workspace_contract import canonical
from control_plane import executive_runtime as owner
from control_plane.executive_runtime import Runtime,StateConflict
from control_plane.instruction_work_source import _issue_instruction_work_source
from tests.test_installed_project_instructions_context import bound
from tests.test_workstream_admission_runtime import mutable_rows,event_count

WORK='WS:ONE';REF='INS:DAILY-ONE'

def setup(tmp_path,monkeypatch):
    area=tmp_path/'source';area.mkdir();collector,seen=bound(area,monkeypatch)
    reader=collector.project_instructions_reader(macro_root=seen['macro'])
    def capture():
        body=reader.read(work_ref=WORK);row=body['instructions'][0]
        return _issue_instruction_work_source(reader=reader,work_ref=WORK,instruction_ref=row['instruction_ref'],revision=row['revision'],source=body['source'],principal_guard=lambda:None)
    return Runtime.at(tmp_path/'runtime'),capture(),capture,seen


def create(runtime,binding,command='instruction-root',parent=None):
    return runtime.jobs.create_job('Instruction-driven bounded test work',provenance={'workstream':WORK},parent_job_id=parent,command_id=command,
        _instruction_source=binding,_principal_commit_guard=lambda:None)


def pause(runtime,binding,command='instruction-pause',guard=lambda:None):
    return runtime.jobs.pause_instruction_admission(binding,command_id=command,actor='test-operator',_commit_guard=guard)


def test_exact_pause_status_duplicate_and_distinct_audit_receipts(tmp_path,monkeypatch):
    runtime,binding,_,_=setup(tmp_path,monkeypatch)
    assert runtime.jobs.read_instruction_admission_suspension(WORK,REF) is None
    receipt=pause(runtime,binding);assert receipt['state']=='PAUSED' and receipt['instruction_ref']==REF
    before=event_count(runtime);assert pause(runtime,binding)==receipt and event_count(runtime)==before
    observed=runtime.jobs.read_instruction_admission_pause_command(WORK,REF,command_id='instruction-pause',actor='test-operator');assert observed==receipt
    assert runtime.jobs.read_instruction_admission_pause_command(WORK,REF,command_id='not-observed',actor='test-operator') is None
    second=pause(runtime,binding,'second-audit');assert second['event_id']!=receipt['event_id'] and event_count(runtime)==before+1
    with pytest.raises(StateConflict):runtime.jobs.read_instruction_admission_pause_command(WORK,REF,command_id='instruction-pause',actor='foreign')


def test_pause_stops_only_bound_new_roots_and_descendants(tmp_path,monkeypatch):
    runtime,binding,_,_=setup(tmp_path,monkeypatch);root=create(runtime,binding);pause(runtime,binding)
    before=mutable_rows(runtime)
    with pytest.raises(StateConflict,match='INSTRUCTION_ADMISSION_SUSPENDED'):create(runtime,binding,'new-root')
    with pytest.raises(StateConflict,match='INSTRUCTION_ADMISSION_SUSPENDED'):runtime.jobs.create_job('child',parent_job_id=root.job_id,command_id='new-child',provenance={'workstream':'WS:OTHER'})
    with runtime.store.transaction() as connection:
        row=connection.execute('SELECT * FROM jobs WHERE job_id=?',(root.job_id,)).fetchone()
        with pytest.raises(StateConflict,match='INSTRUCTION_ADMISSION_SUSPENDED'):
            owner._insert_cycle_child(connection,runtime.store,root_row=row,role='work',objective='new child',requested_authorities=['READ'],allowed_write_paths=[],validation_commands=[],cost_class='small',attempt_limit=1,review_required=False,command_id='cycle-child',plan_attempt_id='ATT-test',plan_digest='a'*64,plan_step_id='STEP-1',repair_round=0)
    assert mutable_rows(runtime)==before
    runtime.jobs.create_job('Explicit project work',provenance={'workstream':WORK},command_id='explicit')
    runtime.jobs.create_job('Legacy unbound work',command_id='legacy')
    with runtime.store.read() as connection:
        payload=json.loads(connection.execute("SELECT payload_json FROM events WHERE command_id='instruction-root'").fetchone()[0])
        assert payload['provenance']['instruction_source']==binding.material() and 'text' not in payload['provenance']['instruction_source']


def test_later_authored_revision_does_not_resume_stable_instruction(tmp_path,monkeypatch):
    runtime,binding,capture,seen=setup(tmp_path,monkeypatch);pause(runtime,binding)
    record=seen['record'];record.write_text(record.read_text().replace('Review the project carefully.','A later authored revision.'))
    subprocess.run(['git','-C',str(seen['macro']),'add','.'],check=True,capture_output=True);subprocess.run(['git','-C',str(seen['macro']),'commit','-qm','later authored content'],check=True,capture_output=True)
    later=capture();assert later.material()['revision']!=binding.material()['revision']
    with pytest.raises(StateConflict,match='INSTRUCTION_ADMISSION_SUSPENDED'):create(runtime,later,'later-root')
    assert runtime.jobs.read_instruction_admission_suspension(WORK,REF)['state']=='PAUSED'
    assert runtime.jobs.read_instruction_admission_pause_command(WORK,REF,command_id='instruction-pause',actor='test-operator')['revision']==binding.material()['revision']


@pytest.mark.parametrize('child',[False,True])
def test_queued_fresh_claim_stops_but_existing_lease_can_start(tmp_path,monkeypatch,child):
    runtime,binding,_,_=setup(tmp_path,monkeypatch)
    runtime.workers.register_worker('worker-01',provider='codex',account_label='test',worker_type='test')
    runtime.workers.register_worker('worker-02',provider='codex',account_label='test2',worker_type='test')
    root=create(runtime,binding);lease=runtime.attempts.claim_job(root.job_id);assert lease is not None
    queued=runtime.jobs.create_job('queued child',parent_job_id=root.job_id,command_id='queued-child') if child else create(runtime,binding,'queued-root')
    before=mutable_rows(runtime);pause(runtime,binding);assert mutable_rows(runtime)==before
    assert runtime.attempts.claim_job(queued.job_id,worker_id='worker-02') is None and mutable_rows(runtime)==before
    runtime.attempts.record_process(lease.attempt.attempt_id,fence_generation=lease.attempt.fence_generation,lease_token=lease.lease_token,provider_session_id='fixture-existing')
    runtime.attempts.mark_running(lease.attempt.attempt_id,fence_generation=lease.attempt.fence_generation,lease_token=lease.lease_token)
    assert runtime.attempts.get_attempt(lease.attempt.attempt_id).status.value=='RUNNING'


def test_public_provenance_foreign_scope_and_private_carrier_cannot_invent_binding(tmp_path,monkeypatch):
    runtime,binding,_,_=setup(tmp_path,monkeypatch)
    source=binding.material()
    for provenance in [{'workstream':WORK,'instruction_source':source},{'workstream':WORK,'instruction_source_digest':'a'*64}]:
        with pytest.raises(StateConflict,match='INSTRUCTION_ADMISSION_SOURCE_REQUIRED'):runtime.jobs.create_job('forged',provenance=provenance)
    with pytest.raises(StateConflict):runtime.jobs.create_job('foreign',provenance={'workstream':'WS:FOREIGN'},_instruction_source=binding,_principal_commit_guard=lambda:None)
    with pytest.raises(StateConflict):runtime.jobs.create_job('missing guard',provenance={'workstream':WORK},_instruction_source=binding)
    captured=[];original=runtime.jobs._create_job_in_transaction
    class Capture(Exception):pass
    def capture(connection,*,spec,**kwargs):captured.append(spec);raise Capture()
    monkeypatch.setattr(runtime.jobs,'_create_job_in_transaction',capture)
    with pytest.raises(Capture):runtime.jobs.create_job('capture template',provenance={'workstream':WORK})
    spec=dataclasses.replace(captured[0],event_provenance={'workstream':WORK,'instruction_source':source,'instruction_source_digest':'a'*64})
    with runtime.store.transaction() as connection:
        with pytest.raises(StateConflict):original(connection,spec=spec)
        with pytest.raises(StateConflict):original(connection,spec=spec,_c2_capability=object())
    assert runtime.jobs.list_jobs()==[]


def test_guard_revocation_rolls_back_pause_and_unknown_event_stays_closed(tmp_path,monkeypatch):
    runtime,binding,_,_=setup(tmp_path,monkeypatch);original=runtime.store.append_event
    def failed(connection,**kwargs):
        original(connection,**kwargs)
        if kwargs['event_type']=='WORKSTREAM_INSTRUCTION_ADMISSION_SUSPENDED':raise StateConflict('current instruction grant revoked')
    monkeypatch.setattr(runtime.store,'append_event',failed)
    with pytest.raises(StateConflict):pause(runtime,binding)
    assert event_count(runtime)==0 and runtime.jobs.read_instruction_admission_suspension(WORK,REF) is None
    monkeypatch.setattr(runtime.store,'append_event',original)
    with runtime.store.transaction() as connection:runtime.store.append_event(connection,aggregate_type='workstream_instruction',aggregate_id=WORK+'/'+REF,event_type='UNKNOWN_STATE',command_id='unknown-instruction')
    with pytest.raises(StateConflict,match='INSTRUCTION_SUSPENSION_SOURCE_INVALID'):pause(runtime,binding)
    with pytest.raises(StateConflict,match='INSTRUCTION_SUSPENSION_SOURCE_INVALID'):create(runtime,binding)
    assert event_count(runtime)==1


def test_pause_orders_before_fresh_claim_under_same_writer_lock(tmp_path,monkeypatch):
    runtime,binding,_,_=setup(tmp_path,monkeypatch);runtime.workers.register_worker('worker-01',provider='codex',account_label='test',worker_type='test');root=create(runtime,binding)
    entered=threading.Event();release=threading.Event();claim_started=threading.Event();append=runtime.store.append_event
    def held(connection,**kwargs):
        append(connection,**kwargs)
        if kwargs['event_type']=='WORKSTREAM_INSTRUCTION_ADMISSION_SUSPENDED':entered.set();assert release.wait(10)
    monkeypatch.setattr(runtime.store,'append_event',held)
    def claim():claim_started.set();return runtime.attempts.claim_job(root.job_id)
    with ThreadPoolExecutor(2) as pool:
        paused=pool.submit(pause,runtime,binding);assert entered.wait(10)
        claimed=pool.submit(claim);assert claim_started.wait(10);assert not claimed.done();release.set()
        assert paused.result(15)['state']=='PAUSED' and claimed.result(15) is None


def test_stale_source_cannot_pause_and_current_guard_is_rechecked_inside_commit(tmp_path,monkeypatch):
    runtime,binding,capture,seen=setup(tmp_path,monkeypatch)
    record=seen['record'];record.write_text(record.read_text().replace('Review the project carefully.','Changed current source.'))
    subprocess.run(['git','-C',str(seen['macro']),'add','.'],check=True,capture_output=True);subprocess.run(['git','-C',str(seen['macro']),'commit','-qm','current revision'],check=True,capture_output=True)
    with pytest.raises(ValueError):pause(runtime,binding)
    assert event_count(runtime)==0
    current=capture();allowed=[True];original=runtime.store.append_event
    def guard():
        if not allowed[0]:raise StateConflict('current scoped permission revoked')
    def revoke(connection,**kwargs):
        original(connection,**kwargs)
        if kwargs['event_type']=='WORKSTREAM_INSTRUCTION_ADMISSION_SUSPENDED':allowed[0]=False
    monkeypatch.setattr(runtime.store,'append_event',revoke)
    with pytest.raises(StateConflict,match='scoped permission revoked'):pause(runtime,current,guard=guard)
    assert event_count(runtime)==0 and runtime.jobs.read_instruction_admission_suspension(WORK,REF) is None


def test_simultaneous_duplicate_pause_has_one_original_receipt_and_reconcile_is_readonly(tmp_path,monkeypatch):
    runtime,binding,_,_=setup(tmp_path,monkeypatch);ready=threading.Barrier(2)
    def invoke():ready.wait(10);return pause(runtime,binding)
    with ThreadPoolExecutor(2) as pool:
        first=pool.submit(invoke);second=pool.submit(invoke);assert first.result(40)==second.result(40)
    assert event_count(runtime)==1
    receipt=runtime.jobs.read_instruction_admission_suspension(WORK,REF)
    def no_writer():raise AssertionError('original receipt reconciliation opened a writer')
    monkeypatch.setattr(runtime.store,'transaction',no_writer)
    assert pause(runtime,binding)==receipt
    with pytest.raises(StateConflict):runtime.jobs.pause_instruction_admission(binding,command_id='instruction-pause',actor='foreign-actor',_commit_guard=lambda:None)


def test_actual_unknown_harness_receipt_and_existing_writer_are_untouched(tmp_path,monkeypatch):
    import test_ohf_p1b_runtime as harness
    from control_plane.operator_harness_contract import OperationId,OperationReceiptKind,operation_receipt_command_id
    _,binding,_,_=setup(tmp_path,monkeypatch)
    def lease_at(path):
        runtime=Runtime.at(path);runtime.workers.register_worker('worker-01',provider='codex',account_label='test',worker_type='test')
        root=create(runtime,binding);lease=runtime.attempts.claim_job(root.job_id);assert lease is not None
        return runtime,lease
    monkeypatch.setattr(harness,'_lease',lease_at)
    runtime,lease,epoch,generation=harness._started(tmp_path/'unknown-runtime')
    operation=OperationId('ohf-op:instruction-unknown')
    runtime.operator_harness.reserve_checkpoint_operation(generation=generation,operation_id=operation,fence_generation=lease.attempt.fence_generation,lease_token=lease.lease_token)
    assert runtime.operator_harness.record_effect_unknown(attempt_id=lease.attempt.attempt_id,operation_id=operation,fence_generation=lease.attempt.fence_generation,lease_token=lease.lease_token,phase='checkpoint',detail='inert fixture unknown')
    command=operation_receipt_command_id(operation,OperationReceiptKind.EFFECT_UNKNOWN);receipt=runtime.store.get_event_by_command_id(command);before=mutable_rows(runtime)
    with runtime.store.read() as connection:
        epochs=[tuple(row) for row in connection.execute('SELECT * FROM harness_session_epochs ORDER BY 1')]
        generations=[tuple(row) for row in connection.execute('SELECT * FROM process_generations ORDER BY 1')]
    pause(runtime,binding)
    assert runtime.store.get_event_by_command_id(command)==receipt and mutable_rows(runtime)==before
    with runtime.store.read() as connection:
        assert [tuple(row) for row in connection.execute('SELECT * FROM harness_session_epochs ORDER BY 1')]==epochs
        assert [tuple(row) for row in connection.execute('SELECT * FROM process_generations ORDER BY 1')]==generations


def test_historical_unbound_provenance_is_not_backfilled_into_instruction_work(tmp_path,monkeypatch):
    runtime,binding,_,_=setup(tmp_path,monkeypatch)
    runtime.workers.register_worker('worker-01',provider='codex',account_label='test',worker_type='test')
    append=runtime.store.append_event
    def historical(connection,**kwargs):
        if kwargs['event_type']=='JOB_CREATED' and kwargs['command_id']=='legacy-before-instruction-schema':
            kwargs['payload']={**kwargs['payload'],'provenance':{'instruction_source':{'old_label':'metadata'}}}
        return append(connection,**kwargs)
    monkeypatch.setattr(runtime.store,'append_event',historical)
    legacy=runtime.jobs.create_job('Historical unbound work',command_id='legacy-before-instruction-schema')
    pause(runtime,binding)
    assert runtime.attempts.claim_job(legacy.job_id) is not None


def test_corrupt_owner_qualified_root_marker_never_becomes_legacy_or_claimable(tmp_path,monkeypatch):
    runtime,binding,_,_=setup(tmp_path,monkeypatch)
    append=runtime.store.append_event
    def corrupt(connection,**kwargs):
        if kwargs['event_type']=='JOB_CREATED':
            payload=json.loads(canonical(kwargs['payload']));payload['instruction_admission']['source_digest']='f'*64
            kwargs['payload']=payload
        return append(connection,**kwargs)
    monkeypatch.setattr(runtime.store,'append_event',corrupt)
    root=create(runtime,binding)
    runtime.workers.register_worker('worker-01',provider='codex',account_label='test',worker_type='test')
    with pytest.raises(StateConflict,match='INSTRUCTION_ADMISSION_ROOT_SOURCE_INVALID'):runtime.attempts.claim_job(root.job_id)


def test_actual_v2_root_factory_accepts_only_private_source_and_current_host_guard(tmp_path,monkeypatch):
    from control_plane import ceo_intent
    from tests.test_executive_os_phase1fc import _v2_intent
    runtime,binding,_,_=setup(tmp_path,monkeypatch);seen=[]
    intent=ceo_intent.validate_intent(_v2_intent(workstream=WORK,grounding={'mastermind_sha':'a'*40,'macro_sha':binding.material()['source']['commit']}))
    def admit():seen.append(True)
    kwargs=dict(fingerprint=ceo_intent.intent_fingerprint(intent),command_id=ceo_intent.command_id_for(intent['intent_id']),workspace_root=None,_instruction_source=binding)
    with pytest.raises(StateConflict):runtime.jobs.create_v2_orchestration_root(intent,**kwargs)
    root=runtime.jobs.create_v2_orchestration_root(intent,**kwargs,_instruction_admission_guard=admit)
    assert root.orchestration_role=='aggregation' and len(seen)==2
    pause(runtime,binding)
    other={**intent,'intent_id':'CEO-INSTRUCTION-ROOT-2'}
    with pytest.raises(StateConflict,match='INSTRUCTION_ADMISSION_SUSPENDED'):
        runtime.jobs.create_v2_orchestration_root(other,fingerprint=ceo_intent.intent_fingerprint(other),command_id=ceo_intent.command_id_for(other['intent_id']),workspace_root=None,_instruction_source=binding,_instruction_admission_guard=admit)
    with pytest.raises(ceo_intent.CeoIntentError):ceo_intent.validate_intent({**other,'instruction_source':binding.material()})


def test_actual_principal_root_factory_keeps_instruction_source_separate_from_execution_guard(tmp_path,monkeypatch):
    from control_plane.coo_principal_envelope import PrincipalAdmissionContext,derive_principal_orchestration_envelope
    runtime,binding,_,_=setup(tmp_path,monkeypatch);seen=[]
    bundle=derive_principal_orchestration_envelope({'operation_key':'instruction-root','objective':'Continue a bounded instruction task.','department':'executive-infrastructure','priority':1,'workstream':WORK,'business_impact':'routine'},context=PrincipalAdmissionContext(work_ref=WORK,principal_binding_digest='1'*64,mission_authority_ref='authority:instruction-test',authority_generation_digest='2'*64),grounding={'mastermind_sha':'a'*40,'macro_sha':binding.material()['source']['commit'],'boot_packet_schema':'mastermind.ceo_boot_packet.v1'})
    root=runtime.jobs.create_principal_orchestration_root(bundle,principal_admission_guard=lambda value:seen.append(value),_instruction_source=binding)
    assert root.orchestration_role=='aggregation' and len(seen)==3
    with runtime.store.read() as connection:
        payload=json.loads(connection.execute("SELECT payload_json FROM events WHERE event_type='JOB_CREATED' AND job_id=?",(root.job_id,)).fetchone()[0])
        assert payload['instruction_admission']['source']==binding.material()
