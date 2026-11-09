"""Source-only registry→original-owner→fixed reader proof; no host dispatch."""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

import pytest
from test_support_policy_status import patched_source, runtime, source_stage


def observation_only_grok(r):
    entry=r.registry['ubuntu0']
    entry['support_policy_observation_root']=entry.pop('physical_lane_root')
    path=r.state/(r.run+'.request-launch.json')
    value=json.loads(path.read_text())
    value['route'].update(POOL='grok',MODE='grok',MODEL='grok-4.7')
    path.write_text(json.dumps(value))
    return r.status.original_request(r.run,r.original_root,r.parent)


def test_observation_only_grok_actual_producer_adapter_once(runtime,monkeypatch,capsys):
    r=runtime
    request,frame,alias=observation_only_grok(r)
    assert request['binding']['path']==str(r.root)
    assert frame['configured_host']==hashlib.sha256(
        json.dumps(r.registry['ubuntu0'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
    assert 'physical_lane_root' not in r.registry['ubuntu0']
    assert alias=='qualified-fixture'
    calls=[]
    def read(alias,request,**kwargs):
        calls.append(alias)
        return json.dumps(r.status.observe(request)).encode()
    monkeypatch.setattr(r.delivery,'transport',read)
    args=['support-policy-status',r.run,'--root',r.original_root,'--parent',r.parent]
    assert r.task.main(args)==0
    out=json.loads(capsys.readouterr().out)
    assert out['state']=='OBSERVED' and out['comparison']=='IDENTICAL'
    assert r.task.main(args)==78
    assert json.loads(capsys.readouterr().out)['state']=='PRIOR_OR_UNKNOWN_READ'
    assert calls==['qualified-fixture']
    assert all(out[k] is False for k in ('maintenance_authorized','admission_authorized',
        'historical_release_ack','execution_replayed'))


def test_pure_observation_resolver_does_not_modify_registry(runtime):
    r=runtime
    entry={'ssh_alias':'qualified-fixture','support_policy_observation_root':str(r.root)}
    before=copy.deepcopy(entry)
    value=r.status.configured_support_policy_observation_root('ubuntu0',entry)
    assert value==r.delivery.configured_remote_lane_root('ubuntu0',
        {'ssh_alias':entry['ssh_alias'],'physical_lane_root':str(r.root)})
    assert entry==before


@pytest.mark.parametrize('change', ['conflict','malformed_global','malformed_observation',
    'null_observation','relative_observation','unsafe_observation','unknown_host','bad_alias','absent'])
def test_actual_constructor_refuses_bad_binding_before_intent(runtime,monkeypatch,change):
    r=runtime;entry=r.registry['ubuntu0']
    entry['support_policy_observation_root']=str(r.root)
    if change=='conflict':entry['physical_lane_root']=str(r.root/'foreign')
    if change=='malformed_global':entry['physical_lane_root']='~/lanes'
    if change=='malformed_observation':entry['support_policy_observation_root']=str(r.root)+'/'
    if change=='null_observation':entry['support_policy_observation_root']=None
    if change=='relative_observation':entry['support_policy_observation_root']='lanes'
    if change=='unsafe_observation':entry['support_policy_observation_root']=str(r.root)+'/../lanes'
    if change=='unknown_host':r.registry.clear()
    if change=='bad_alias':entry['ssh_alias']='unsafe alias'
    if change=='absent':entry.pop('physical_lane_root');entry.pop('support_policy_observation_root')
    # Neither caller environment nor a HOME spelling is an enrollment source.
    monkeypatch.setenv('SUPPORT_POLICY_OBSERVATION_ROOT',str(r.root))
    monkeypatch.setenv('REMOTE_PHYSICAL_ROOT',str(r.root))
    calls=[]
    monkeypatch.setattr(r.delivery,'transport',lambda *a,**k:calls.append('forbidden'))
    with pytest.raises(ValueError):
        r.status.inspect_original(r.run,r.original_root,r.parent,qualified_sources=r.status.source_hashes())
    assert calls==[]
    assert not (r.state/(r.run+'.support-policy-status.intent.json')).exists()


@pytest.mark.parametrize('phase',['before_transport','after_read'])
@pytest.mark.parametrize('change',['root','alias','other_host_entry_fact','withdrawal'])
def test_observation_host_entry_currentness_retains_intent_and_withholds_report(runtime,monkeypatch,phase,change):
    r=runtime;observation_only_grok(r);calls=[]
    def withdraw():
        entry=r.registry['ubuntu0']
        if change=='root':entry['support_policy_observation_root']=str(r.root/'foreign')
        if change=='alias':entry['ssh_alias']='other-alias'
        if change=='other_host_entry_fact':entry['load_gate']=3
        if change=='withdrawal':entry.pop('support_policy_observation_root')
    import provider_outcome
    original_write=provider_outcome.write_new
    def write(path,value):
        result=original_write(path,value)
        if phase=='before_transport' and str(path).endswith('.intent.json'):withdraw()
        return result
    monkeypatch.setattr(provider_outcome,'write_new',write)
    def transport(alias,request,**kwargs):
        calls.append(alias);value=r.status.observe(request)
        assert value['state']=='OBSERVED'
        if phase=='after_read':withdraw()
        return json.dumps(value).encode()
    monkeypatch.setattr(r.delivery,'transport',transport)
    out=r.status.inspect_original(r.run,r.original_root,r.parent,qualified_sources=r.status.source_hashes())
    assert out['state']=='PRIOR_OR_UNKNOWN_READ' and 'counts' not in out
    assert len(calls)==(phase=='after_read')
    assert (r.state/(r.run+'.support-policy-status.intent.json')).exists()
    assert not (r.state/(r.run+'.support-policy-status.result.json')).exists()
    # A subsequent attempt cannot turn retained uncertainty into another call.
    if change=='withdrawal':r.registry['ubuntu0']['support_policy_observation_root']=str(r.root)
    repeated=r.status.inspect_original(r.run,r.original_root,r.parent,qualified_sources=r.status.source_hashes())
    assert repeated['state']=='PRIOR_OR_UNKNOWN_READ'
    assert len(calls)==(phase=='after_read')


@pytest.mark.parametrize('mode,operator,global_root,expected',[
    ('grok',False,False,0),('grok',True,False,0),('grok',False,True,78),
    ('grok',True,True,78),('glm',False,True,0),('glm',True,True,78)])
def test_actual_registry_loader_preserves_dispatch_contract(runtime,mode,operator,global_root,expected):
    r=runtime
    # Full exact production load_host_registry, including real custody reads and
    # strict registry/binding parsing, ends at a local inert boundary. No entrypoint,
    # remote command, provider, broker or fake global parser is substituted.
    text=(r.ext/'remote_sub.sh').read_text()
    assert hashlib.sha256(text.encode()).hexdigest()=='8a8491882608f73db58b596b02bd37955eebcd4670bcb8bb2d2ac6a0fa659f63'
    function='load_host_registry() {\n'+text.split('load_host_registry() {\n',1)[1].split('\n}\n',1)[0]+'\n}\n'
    entry={'ssh_alias':'qualified-fixture','cores':4,'max_active':2,'load_gate':4,
        'roles':['lanes'],'allowed_modes':['grok','glm'],
        'support_policy_observation_root':str(r.root)}
    if global_root:entry['physical_lane_root']=str(r.root)
    registry=r.ext/'hosts.json';registry.write_text(json.dumps({'ubuntu0':entry}));registry.chmod(0o600)
    values={'HOSTS_SOURCE':str(registry),'HOST_ARG':'ubuntu0','HERE':str(r.ext),
        'REMOTE_SUB_PYTHON':sys.executable,'MODE':mode,'RUN_ID_ARG':'inert-scope',
        'PLAIN_PACKET_RETAINED':'inert-packet','POOL_ORCHESTRATOR_ID':'fixture-root',
        'POOL_PARENT_RUN_ID':'fixture-parent','REMOTE_CWD':'~','OPERATOR_CHILD_BUDGET':'0',
        'NEW_MACRO_COMMIT':'','CPU_SCOPE_QUOTA':'','RC':'0',
        'FABRIC_OPERATOR_CHILD_ID':'fixture-child' if operator else '',
        'FABRIC_OPERATOR_POST_SUPPORT_CONTINUATION':'','FABRIC_OPERATOR_PRELEASE_CONTINUATION':''}
    script='set -u\n'+'\n'.join(k+'='+shlex.quote(v) for k,v in values.items())+'\n'
    script+='log() { printf "%s\\n" "$*"; }\n'
    script+='commission_run() { [ "$1" = host-registry ] || exit 99; shift; "$@"; }\n'+function
    script+='load_host_registry || exit "$RC"\nprintf "%s\\n" INERT_BOUNDARY\n'
    env={k:v for k,v in os.environ.items() if not k.startswith(('POOL_','FABRIC_OPERATOR_'))}
    result=subprocess.run(['bash','-c',script],capture_output=True,text=True,env=env,timeout=15)
    assert result.returncode==expected,(result.stdout,result.stderr)
    assert ('INERT_BOUNDARY' in result.stdout)==(expected==0)
    if expected==78:assert 'REMOTE_LANE_ROOT_SCOPE_REFUSED before_lease=1 before_remote=1' in result.stdout


def test_observation_binding_reaches_actual_isolated_reader(runtime):
    from test_support_policy_status import test_generated_isolated_reader_executes_with_real_existing_parser
    r=runtime;r.request,_,_=observation_only_grok(r)
    test_generated_isolated_reader_executes_with_real_existing_parser(r)


def test_equal_dual_binding_preserves_actual_original_request(runtime):
    r=runtime;before=r.status.original_request(r.run,r.original_root,r.parent)[0]
    r.registry['ubuntu0']['support_policy_observation_root']=str(r.root)
    entry=copy.deepcopy(r.registry['ubuntu0'])
    after,frame,alias=r.status.original_request(r.run,r.original_root,r.parent)
    assert after['binding']==before['binding'] and alias=='qualified-fixture'
    assert after['original_metadata_sha256']!=before['original_metadata_sha256']
    assert r.registry['ubuntu0']==entry
