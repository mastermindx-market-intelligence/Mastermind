"""Actual sealed Macro reader, eighth grant and incumbent Runtime owner join."""
import copy
import subprocess
import pytest
from common import workspace_instruction_admission_contract as wire
from control_plane.workspace_instruction_admission import read_instruction_admission_control,instruction_admission_request
from control_plane.workspace_instruction_permission_binding import InstructionAdmissionPermissions
from control_plane.workspace_project_permission_binding import ProjectPermissionSourceUnavailable
from integrations.mastermind_workspace_app.project_admission_permissions import instruction_admission_permissions
from tests.test_workspace_project_admission import setup as project_setup,count
from tests.test_installed_project_instructions_context import bound

WORK='WS:ONE';REF='INS:DAILY-ONE';COMMAND='mmos-instruction-pause-'+'1'*40


def setup(tmp_path,monkeypatch,field='supplied'):
    runtime,service,bindings,project,_=project_setup(tmp_path)
    slot=bindings['profiles']['member-0']
    slot['instruction_admission_suspend']={'work_ref':WORK,'instruction_ref':REF,'permission_digest':'f'*64}
    source=tmp_path/'source';source.mkdir();collector,seen=bound(source,monkeypatch,field)
    reader=collector.project_instructions_reader(macro_root=seen['macro']);service._project_instructions_reader=reader
    # Reuse the actual cache owner fixture retained by its provider closure.
    from tests.test_workspace_read_service import cache_fixture
    owners,clock,cache=cache_fixture(tmp_path/'instruction-cache');service.cache=cache
    doc=owners[0].state_cache['doc'];doc['sources']={'macro_sha':seen['sha']}
    from scripts import chairman_control_room as ccr
    def publish():
        with owners[0].state_lock:ccr._publish_source_validity(owners[0],doc,tuple(clock),tuple(clock))
    publish()
    permissions=instruction_admission_permissions(policy=service._project_admission_permissions._owner._policy,load_bindings=lambda:bindings)
    service._instruction_admission_permissions=permissions
    body=reader.read(work_ref=WORK)
    frame={'schema':wire.ACTION_FRAME_SCHEMA,'operation':wire.PAUSE,'selection':{'work_ref':WORK,'instruction_ref':REF,'command_id':COMMAND},
        'principal':project['principal'],'admission_expires_at':1000,'expected_revision':body['instructions'][0]['revision'] if body['instructions'] else 'a'*64,'expected_source':body['source']}
    def call(mode='pause',value=None,host_ready=lambda:True):
        selected=copy.deepcopy(frame if value is None else value)
        if mode=='current':
            selected.update(schema=wire.CONTROL_FRAME_SCHEMA,operation=wire.OPERATIONS['current']);selected['selection'].pop('command_id');selected.pop('expected_revision');selected.pop('expected_source')
        elif mode=='status':
            selected.update(schema=wire.STATUS_FRAME_SCHEMA,operation=wire.OPERATIONS['status']);selected.pop('expected_revision');selected.pop('expected_source')
        options=dict(permissions=service._instruction_admission_permissions,host_ready=host_ready,now=lambda:500)
        return read_instruction_admission_control(service,selected,**options) if mode=='current' else instruction_admission_request(service,selected,status=mode=='status',**options)
    return runtime,service,bindings,frame,call,seen,doc,publish


def test_real_current_pause_and_original_status_are_distinct_facts(tmp_path,monkeypatch):
    runtime,_,_,frame,call,_,_,_=setup(tmp_path,monkeypatch);before=count(runtime)
    current=call('current')['result'];assert current['state']=='NOT_SUSPENDED' and current['permission']=={'pause':True}
    assert len(current['owner_context']['principal_scope'])==64 and count(runtime)==before
    first=call()['result'];assert first['disposition']=='COMMITTED' and first['receipt']['instruction_ref']==REF
    assert call()['result']==first and count(runtime)==before+1
    assert call('current')['result']['current_receipt']==first['receipt']
    assert call('status')['result']['receipt']==first['receipt']
    absent=copy.deepcopy(frame);absent['selection']['command_id']='mmos-instruction-pause-'+'2'*40
    assert call('status',absent)['result']['state']=='NOT_OBSERVED' and count(runtime)==before+1


@pytest.mark.parametrize('change',['missing','project','instruction','reuse','read','expired','host','revision','source','field'])
def test_foreign_missing_stale_or_unqualified_requests_never_mutate(tmp_path,monkeypatch,change):
    runtime,_,bindings,frame,call,_,_,_=setup(tmp_path,monkeypatch);slot=bindings['profiles']['member-0'];before=count(runtime)
    if change=='missing':slot['instruction_admission_suspend']=None
    elif change=='project':slot['instruction_admission_suspend']['work_ref']='WS:OTHER'
    elif change=='instruction':slot['instruction_admission_suspend']['instruction_ref']='INS:OTHER'
    elif change=='reuse':slot['instruction_admission_suspend']['permission_digest']=slot['binding']['permission_digest']
    elif change=='read':slot['binding']=None
    elif change=='expired':frame['admission_expires_at']=499
    elif change=='revision':frame['expected_revision']='e'*64
    elif change=='source':frame['expected_source']['commit']='e'*40
    elif change=='field':frame['actor']='forged'
    result=call(value=frame,host_ready=lambda:change!='host')
    assert result.get('ok') is False if change=='field' else result['result']['disposition']=='NOT_DISPATCHED'
    assert count(runtime)==before


@pytest.mark.parametrize('field',['empty','absent'])
def test_missing_instruction_content_is_not_empty_execution_or_permission(tmp_path,monkeypatch,field):
    runtime,_,_,_,call,_,_,_=setup(tmp_path,monkeypatch,field);before=count(runtime)
    current=call('current')['result'];assert current['reason_codes']==['INSTRUCTION_NOT_SUPPLIED']
    assert len(current['owner_context']['principal_scope'])==64
    assert all(current[key] is None for key in ['state','source','instruction_revision','permission','current_receipt'])
    assert call()['result']['disposition']=='NOT_DISPATCHED'
    assert call('status')['result']['state']=='NOT_OBSERVED' and count(runtime)==before


@pytest.mark.parametrize('loss',['inside_commit','after_commit','transport'])
def test_late_permission_or_transport_loss_retains_unknown_original(tmp_path,monkeypatch,loss):
    runtime,_,bindings,_,call,_,_,_=setup(tmp_path,monkeypatch);slot=bindings['profiles']['member-0'];grant=copy.deepcopy(slot['instruction_admission_suspend']);before=count(runtime)
    if loss=='inside_commit':
        original=runtime.store.append_event
        def append(connection,**kwargs):
            original(connection,**kwargs)
            if kwargs['event_type']=='WORKSTREAM_INSTRUCTION_ADMISSION_SUSPENDED':slot['instruction_admission_suspend']=None
        monkeypatch.setattr(runtime.store,'append_event',append)
    else:
        original=runtime.jobs.pause_instruction_admission
        def pause(*args,**kwargs):
            receipt=original(*args,**kwargs)
            if loss=='transport':raise RuntimeError('private owner transport detail')
            slot['instruction_admission_suspend']=None;return receipt
        monkeypatch.setattr(runtime.jobs,'pause_instruction_admission',pause)
    result=call()['result'];assert result['disposition']=='EFFECT_UNKNOWN' and result['receipt'] is None and 'private' not in str(result)
    assert count(runtime)==before+(loss!='inside_commit')
    slot['instruction_admission_suspend']=grant
    status=call('status')['result'];assert status['state']==('NOT_OBSERVED' if loss=='inside_commit' else 'OBSERVED')


def test_authored_revision_does_not_resume_and_original_receipt_recovers_after_removal(tmp_path,monkeypatch):
    runtime,_,_,frame,call,seen,doc,publish=setup(tmp_path,monkeypatch);first=call()['result']['receipt'];before=count(runtime)
    path=seen['record'];path.write_text(path.read_text().replace('Review the project carefully.','Later authored content.'))
    subprocess.run(['git','-C',str(seen['macro']),'add','.'],check=True,capture_output=True);subprocess.run(['git','-C',str(seen['macro']),'commit','-qm','later instruction'],check=True,capture_output=True)
    doc['sources']['macro_sha']=subprocess.check_output(['git','-C',str(seen['macro']),'rev-parse','HEAD'],text=True).strip();publish()
    current=call('current')['result'];assert current['state']=='PAUSED' and current['instruction_revision']!=first['revision'] and current['current_receipt']==first
    assert call()['result']['receipt']==first # same immutable original request
    changed=copy.deepcopy(frame);changed['expected_revision']=current['instruction_revision'];changed['expected_source']=current['source']
    assert call(value=changed)['result']['disposition']=='EFFECT_UNKNOWN' and count(runtime)==before
    path.write_text(path.read_text().replace("standing_instructions:\n  - instruction_ref: INS:DAILY-ONE\n    text: 'Later authored content.'\n",'standing_instructions: []\n'))
    subprocess.run(['git','-C',str(seen['macro']),'add','.'],check=True,capture_output=True);subprocess.run(['git','-C',str(seen['macro']),'commit','-qm','remove content'],check=True,capture_output=True)
    doc['sources']['macro_sha']=subprocess.check_output(['git','-C',str(seen['macro']),'rev-parse','HEAD'],text=True).strip();publish()
    unavailable=call('current')['result'];assert unavailable['availability']=='UNAVAILABLE'
    assert unavailable['owner_context']==current['owner_context'] and unavailable['permission'] is None
    assert call('status')['result']['receipt']==first and count(runtime)==before


@pytest.mark.parametrize('change',['seal','loader','method','factory','context','callback'])
def test_nominal_permission_source_rejects_forgery_rebinding_and_detachment(tmp_path,monkeypatch,change):
    _,service,_,_,call,_,_,_=setup(tmp_path,monkeypatch);source=service._instruction_admission_permissions;owner=source._owner
    if change=='seal':
        with pytest.raises(ProjectPermissionSourceUnavailable):InstructionAdmissionPermissions(object(),owner,source._context,source._callback,source._qualified_owner)
        return
    if change=='loader':object.__setattr__(owner,'_load_bindings',lambda:{})
    elif change=='method':monkeypatch.setattr(type(owner),'_instruction_authorizer',lambda **kwargs:lambda p:True)
    elif change=='factory':object.__setattr__(owner,'_factory',lambda **kwargs:(lambda p:True,lambda p:True))
    elif change=='context':object.__setattr__(source,'_context',())
    else:object.__setattr__(source,'_callback',object())
    assert call()['result']['disposition']=='NOT_DISPATCHED'


def test_instance_reader_override_cannot_replace_the_nominal_canonical_owner(tmp_path,monkeypatch):
    _,service,_,_,call,_,_,_=setup(tmp_path,monkeypatch)
    def forged(**kwargs):raise AssertionError('instance callback must not be used')
    service._project_instructions_reader.read=forged
    assert call('current')['result']['state']=='NOT_SUSPENDED'


def test_cache_publication_change_in_commit_rolls_back_and_withholds_original(tmp_path,monkeypatch):
    from dataclasses import replace
    runtime,service,_,_,call,_,_,_=setup(tmp_path,monkeypatch);before=count(runtime);changed=[False]
    snapshot=service.cache.snapshot;append=runtime.store.append_event
    def read():
        value=snapshot();return replace(value,publication=value.publication+1) if changed[0] else value
    def drift(connection,**kwargs):
        append(connection,**kwargs)
        if kwargs['event_type']=='WORKSTREAM_INSTRUCTION_ADMISSION_SUSPENDED':changed[0]=True
    monkeypatch.setattr(service.cache,'snapshot',read);monkeypatch.setattr(runtime.store,'append_event',drift)
    assert call()['result']['disposition']=='EFFECT_UNKNOWN' and count(runtime)==before
