"""Executive/native boundaries: no model calls or credential material in fixtures."""
import copy
import json
import os
import pwd
import subprocess
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane.claude_operator_adapter import ClaudeOperatorAdapter, ClaudeReadbackPolicyObserver, ClaudeOperatorError, _digest
from control_plane.executive_agent_capabilities import claude_security_config_digest
from control_plane.claude_operator_helper_protocol import native_plan_contract
from control_plane.operator_harness_contract import (CapabilityIdentity, CapabilityManifest,
    RequestedExecutionProfile, NativeHelperPolicy, SessionEpochRef, ProcessGenerationRef,
    ProcessIdentityObservation, OperationId, TurnRef, EventCursor, compare_launch, LaunchDecision,
    ProcessLiveness, ProviderWriterState)

POLICY = {'tools':['Read','Glob','Grep'],'permission_mode':'dontAsk','setting_sources':[],
          'strict_mcp_config':True,'mcp_servers':{},'skills':[],
          'sandbox':{'enabled':True,'failIfUnavailable':True,'autoAllowBashIfSandboxed':False,
              'allowUnsandboxedCommands':False,'excludedCommands':[],
              'network':{'allowedDomains':[],'deniedDomains':['*'],'allowAllUnixSockets':False,'allowLocalBinding':False}}}

class FakeClient:
    def __init__(self):
        self.pid=700001
        self.running=False
        self.calls=[]
        self.turn=None
        self.sid=None
        self.lost_begin=False
        self.bad_result=False
        self.terminal=True
    def start(self): self.running=True
    def alive(self): return self.running
    def private_group_alive(self): return self.running
    def request(self, method, fields, **kwargs):
        self.calls.append((method,copy.deepcopy(fields)))
        if method=='initialize':
            c=fields['config'];self.sid=c['session_id']
            return {'sdk_version':'0.2.160','cli_version':'2.1.275','session_id':self.sid,
                    'registration_zero_turn':True,'native_subscription_verified':True,
                    'applied_launch_provenance':{'setting_sources':[],'strict_mcp_config':True,'skills':[]},
                    'settings_readback_provenance':'native-get_settings/0.2.160/2.1.275',
                    'result_contract':native_plan_contract(),
                    'initialization':{'model':c['model'],'cwd':c['cwd'],'tools':['Read','Glob','Grep','StructuredOutput'],
                        'skills':[],'plugins':[],'mcp_servers':[],'permissionMode':'dontAsk'},
                    'mcp_status':{'servers':[]},'server_info':{'account':{'apiProvider':'firstParty','subscriptionType':'Claude Max'}},
                    'effective_policy':{'sandbox':copy.deepcopy(POLICY['sandbox'])}}
        if method=='begin_turn':
            self.turn=fields['turn_id']
            if self.lost_begin:raise TimeoutError('response lost')
            return {'acknowledged':False}
        if method=='collect':return {'terminal':self.terminal,'success':True,'acknowledged':True,
                                    'drain_closed':True,'event_sequence':1}
        if method=='read_events':return {'events':[{'kind':'result','sequence':1,'turn_id':self.turn,'is_error':False}]}
        if method=='reconcile':return {'session_reachable':True,'session_id':self.sid}
        return {'acknowledged':True}
    def request_raw_turn_page(self, **kwargs):
        result={'terminal':self.terminal,'success':not self.bad_result,'session_id':self.sid,'turn_id':self.turn,
                'result_source':'native-structured-output','result_contract':native_plan_contract(),
                'native_result_id':'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','summary':'{"answer":"verified"}'}
        return SimpleNamespace(consume=lambda:result)
    def graceful_close(self, **kwargs):
        self.running=False
        return SimpleNamespace(private_group_empty=True,leader_exit_confirmed_graceful=True,controller_returncode=0)
    def terminate(self, **kwargs):self.running=False

@pytest.fixture
def configured(tmp_path):
    root=tmp_path.resolve();home=root/'home';home.mkdir(mode=0o700);(home/'.claude').mkdir(mode=0o700);(home/'tmp').mkdir(mode=0o700)
    workspace=root/'workspace';workspace.mkdir();binary=root/'claude';binary.write_bytes(b'qualified fixture executable')
    client=FakeClient()
    a=ClaudeOperatorAdapter(binary_path=binary,provider_home=home,workspace_root=workspace,
        worker_id='worker',expected_harness_version='2.1.275',expected_config_digest=claude_security_config_digest({'sandbox':POLICY['sandbox']},launch_provenance={k:POLICY[k] for k in ('setting_sources','strict_mcp_config','skills')}),
        network_policy='disabled',turn_input_loader=lambda t:'Actual project task for '+t.turn_id,
        policy_observer=ClaudeReadbackPolicyObserver(POLICY),client_factory=lambda *args:client,
        process_identity_observer=lambda pid:ProcessIdentityObservation(pid,pid,'start','boot'),
        base_sha_resolver=lambda path:'a'*40)
    profile=RequestedExecutionProfile('worker','claude','claude-opus-5','claude-agent-sdk',a.binary_digest,'2.1.275',
        a.configured_workspace,'read-only','never','disabled',
        CapabilityManifest(required=tuple(CapabilityIdentity(t,a.binary_digest,kind='tool') for t in [*POLICY['tools'],'StructuredOutput'])),
        NativeHelperPolicy.DISABLED,'authority-hash',expected_config_digest=claude_security_config_digest({'sandbox':POLICY['sandbox']},launch_provenance={k:POLICY[k] for k in ('setting_sources','strict_mcp_config','skills')}))
    epoch=SessionEpochRef('epoch','attempt','worker',1);gen=ProcessGenerationRef('generation','epoch',1,'worker')
    return a,client,profile,epoch,gen

def start(value):
    a,c,p,e,g=value
    observed=a.start_session(operation_id=OperationId('ohf-op:start'),requested=p,epoch=e,generation=g)
    return observed,compare_launch(p,a.observed_attestation(g))

def test_actual_observations_allow_ordinary_project_payload_and_terminal_consumption(configured):
    a,c,p,e,g=configured;session,launch=start(configured)
    assert session.provider_session_id==c.sid and launch.decision is LaunchDecision.ALLOW
    t=TurnRef('turn','epoch','generation','attempt')
    assert a.begin_turn(operation_id=OperationId('ohf-op:turn'),turn=t,generation=g,launch=launch).acknowledged
    assert [f['payload'] for m,f in c.calls if m=='begin_turn']==['Actual project task for turn']
    events,cursor=a.read_events(EventCursor('attempt','epoch','generation',turn_id='turn'))
    assert events[0].kind=='turn/completed' and cursor.local_sequence==1
    candidate=a.collect_candidate_result(t);raw=a.observe_raw_role_result(t)
    assert candidate.artifact_digest==raw.provider_turn_artifact_digest
    assert raw.canonical_result_json=='{"answer":"verified"}'
    assert candidate.complete_job_permitted is False
    stopped=a.graceful_stop(g,operation_id=OperationId('ohf-op:stop'))
    assert stopped.process_liveness is ProcessLiveness.PROVEN_DEAD
    assert stopped.provider_writer_state is ProviderWriterState.RELEASED

def test_fabricated_allow_cannot_override_observed_model(configured):
    a,c,p,e,g=configured;_,launch=start(configured)
    forged=replace(launch,observed=replace(launch.observed,served_model='invented'))
    with pytest.raises(ClaudeOperatorError,match='actual launch'):
        a.begin_turn(operation_id=OperationId('ohf-op:turn'),turn=TurnRef('turn','epoch','generation','attempt'),generation=g,launch=forged)
    assert not any(m=='begin_turn' for m,_ in c.calls)

def test_lost_dispatch_response_is_not_retried(configured):
    a,c,p,e,g=configured;_,launch=start(configured);c.lost_begin=True;t=TurnRef('turn','epoch','generation','attempt')
    with pytest.raises(ClaudeOperatorError) as err:
        a.begin_turn(operation_id=OperationId('ohf-op:turn'),turn=t,generation=g,launch=launch)
    assert err.value.effect_unknown
    with pytest.raises(ClaudeOperatorError):
        a.begin_turn(operation_id=OperationId('ohf-op:turn'),turn=t,generation=g,launch=launch)
    assert sum(m=='begin_turn' for m,_ in c.calls)==1
    assert a.reconcile(g).process_liveness is ProcessLiveness.ALIVE

def test_cancel_does_not_invent_provider_release(configured):
    a,c,p,e,g=configured;start(configured)
    state=a.cancel(g,reason='controlled interruption',operation_id=OperationId('ohf-op:cancel'))
    assert state.process_liveness is ProcessLiveness.PROVEN_DEAD
    assert state.provider_writer_state is ProviderWriterState.UNKNOWN

@pytest.mark.parametrize('mutation',[lambda p:p['sandbox'].__setitem__('enabled',False),
    lambda p:p.__setitem__('tools',['Read','Bash']),lambda p:p.__setitem__('mcp_servers',{'other':{}}),
    lambda p:p.__setitem__('setting_sources',['user'])])
def test_unqualified_policy_refused(mutation):
    p=copy.deepcopy(POLICY);mutation(p)
    with pytest.raises(ValueError):ClaudeReadbackPolicyObserver(p)

def test_private_native_result_failure_cannot_be_accepted(configured):
    a,c,p,e,g=configured;_,launch=start(configured);t=TurnRef('turn','epoch','generation','attempt')
    a.begin_turn(operation_id=OperationId('ohf-op:turn'),turn=t,generation=g,launch=launch);c.bad_result=True
    with pytest.raises(ClaudeOperatorError,match='terminal result'):
        a.collect_candidate_result(t)

def test_changed_policy_readback_refuses(configured):
    a,c,p,e,g=configured
    handshake=c.request('initialize',{'config':{'session_id':'native-session','model':p.requested_model,'cwd':str(a.workspace_root)}})
    handshake['effective_policy']['sandbox']['allowUnsandboxedCommands']=True
    with pytest.raises(ClaudeOperatorError,match='policy differs'):
        a.policy_observer.observe(handshake)


def test_absent_private_tmp_refuses_before_any_process_start(configured):
    a,c,p,e,g=configured;(a.provider_home/'tmp').rmdir()
    with pytest.raises((OSError,ClaudeOperatorError)):start(configured)
    assert not c.running and not c.calls


def test_shared_policy_encoder_matches_actual_handshake_provenance(configured):
    a,c,p,e,g=configured;_,launch=start(configured)
    assert launch.observed.effective_config_digest==p.expected_config_digest
    assert launch.decision is LaunchDecision.ALLOW


def test_terminal_event_arriving_after_page_is_consumed(configured):
    a,c,p,e,g=configured;_,launch=start(configured);t=TurnRef('turn','epoch','generation','attempt')
    a.begin_turn(operation_id=OperationId('ohf-op:turn'),turn=t,generation=g,launch=launch)
    request=c.request;pages=[]
    def raced(method, fields, **kwargs):
        if method=='read_events':
            pages.append(fields['after_sequence'])
            if len(pages)==1:return {'events':[],'has_more':False}
        return request(method,fields,**kwargs)
    c.request=raced
    events,cursor=a.read_events(EventCursor('attempt','epoch','generation',turn_id='turn'))
    assert len(pages)==2 and cursor.local_sequence==1
    assert [x.kind for x in events]==['turn/completed']


def test_uncertain_drain_cannot_supply_candidate_even_if_success_claimed(configured):
    a,c,p,e,g=configured;_,launch=start(configured);t=TurnRef('turn','epoch','generation','attempt')
    a.begin_turn(operation_id=OperationId('ohf-op:turn'),turn=t,generation=g,launch=launch)
    original=c.request_raw_turn_page
    def uncertain(**kwargs):
        value=original(**kwargs).consume();value['failure']='response_effect_unknown'
        return SimpleNamespace(consume=lambda:value)
    c.request_raw_turn_page=uncertain
    with pytest.raises(ClaudeOperatorError,match='terminal result'):a.collect_candidate_result(t)


def test_actual_owned_process_credentials_are_observed(configured):
    a,c,p,e,g=configured;start(configured)
    child=subprocess.Popen(['/bin/sleep','5'],start_new_session=True)
    try:
        from control_plane.codex_operator_adapter import _default_process_identity
        state=a._state(g);state.process=_default_process_identity(child.pid)
        a.process_identity_observer=_default_process_identity
        result=a.observe_process_credentials(g)
        assert result.os_principal_uid==os.geteuid()
        assert result.os_principal_name==pwd.getpwuid(os.geteuid()).pw_name
        assert result.process_identity['pid']==child.pid
    finally:
        child.terminate();child.wait(timeout=5)


def test_changed_process_identity_refuses_credential_admission(configured,monkeypatch):
    a,c,p,e,g=configured;start(configured)
    a.process_identity_observer=lambda pid:ProcessIdentityObservation(pid,pid,'other-start','boot')
    monkeypatch.setattr(subprocess,'run',lambda *args,**kwargs:pytest.fail('must not inspect recycled PID'))
    with pytest.raises(ClaudeOperatorError,match='credentials') as error:a.observe_process_credentials(g)
    assert error.value.effect_unknown


def test_process_identity_changed_during_credential_probe_refuses(configured,monkeypatch):
    a,c,p,e,g=configured;start(configured);state=a._state(g)
    identities=iter([state.process,replace(state.process,process_start_identity='changed')])
    a.process_identity_observer=lambda pid:next(identities)
    monkeypatch.setattr(subprocess,'run',lambda *args,**kwargs:SimpleNamespace(stdout=str(os.geteuid())))
    with pytest.raises(ClaudeOperatorError,match='credentials'):a.observe_process_credentials(g)


def test_native_home_observation_is_fresh_and_metadata_only(configured):
    a,c,p,e,g=configured;start(configured)
    original=a.observe_provider_home_identity(g).provider_home_identity
    assert original['inode']==a.provider_home.stat().st_ino
    retired=a.provider_home.with_name('retired-home');a.provider_home.rename(retired)
    a.provider_home.mkdir(mode=0o700)
    fresh=a.observe_provider_home_identity(g).provider_home_identity
    assert fresh['inode']!=original['inode']
    # Broker compares this fresh observation to its enrolled immutable identity.
    a.provider_home.chmod(0o755)
    with pytest.raises(ClaudeOperatorError,match='provider home'):a.observe_provider_home_identity(g)
    a.provider_home.rmdir();a.provider_home.symlink_to(retired,target_is_directory=True)
    with pytest.raises(ClaudeOperatorError,match='provider home'):a.observe_provider_home_identity(g)


@pytest.mark.parametrize('field,value',[('result_source','native-result-text'),('result_contract',None)])
def test_text_fallback_or_unknown_schema_cannot_supply_candidate(configured,field,value):
    a,c,p,e,g=configured;_,launch=start(configured);t=TurnRef('turn','epoch','generation','attempt')
    a.begin_turn(operation_id=OperationId('ohf-op:turn'),turn=t,generation=g,launch=launch)
    original=c.request_raw_turn_page
    def wrong(**kwargs):
        result=original(**kwargs).consume();result[field]=value
        return SimpleNamespace(consume=lambda:result)
    c.request_raw_turn_page=wrong
    with pytest.raises(ClaudeOperatorError,match='terminal result'):a.collect_candidate_result(t)
