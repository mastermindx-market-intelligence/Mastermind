"""N0 source conformance. Node contract doubles are NOT a mounted DSH runtime."""
from __future__ import annotations
import dataclasses
import hashlib
import importlib
import json
import shutil
import subprocess
from pathlib import Path
import pytest
from control_plane.operator_harness_contract import (
    AuthRealmFact, CapabilityIdentity, CapabilityManifest, LaunchDecision,
)
from tests.test_ohf_p1a_operator_harness_contract import _requested, _observed

ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = '0d1f50007f9bca3f52b06e1c3074fa14d5fb0720'
def digest(c): return 'sha256:' + c*64
def canonical(v): return json.dumps(v, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
def hash_value(v): return 'sha256:' + hashlib.sha256(canonical(v)).hexdigest()
def load(): return importlib.import_module('experiments.harness_convergence.dsh_native.ohf_consumer')
def document():
    return dict(format='dsh-native-observation/n0', upstream_commit=UPSTREAM,
        binding=dict(attempt_id='attempt-fixture',worker_id='worker-fixture',process_generation_id='generation-fixture',native_session_id='native-fixture-1'),
        recipe_digest=digest('a'),presentation='native',extension_policy='N0_CLOSED_FIXTURE_NO_EXTERNAL_CAPABILITIES',
        model=dict(provider='fixture',model='fixture-model',reasoning_effort=None,max_tokens=64),
        tools=[dict(name=n,description=f'In-memory {n}',parameters={'type':'object','additionalProperties':False},implementation_digest=digest('c')) for n in ['fixture_read','fixture_note']],
        composition=[dict(entry_id='core',module='@deepseek-ai/dsh-tools',module_digest=digest('b'))])
def context(m):
    d=document()
    tool_ids=tuple((r['name'],hash_value({k:r[k] for k in ['name','description','parameters']}),r['implementation_digest']) for r in d['tools'])
    binding=m.NativeBinding(**d['binding'],recipe_digest=d['recipe_digest'],tools=tool_ids,
        modules=tuple((r['entry_id'],r['module'],r['module_digest']) for r in d['composition']))
    req=_requested(worker_id='worker-fixture',provider='fixture',requested_model='fixture-model',expected_config_digest=None,
        capabilities=CapabilityManifest(required=tuple(CapabilityIdentity(name=n,kind='tool',harness_binary_digest='digest-v1',tool_schema_digest=s) for n,s,_ in tool_ids)))
    host=_observed(auth=AuthRealmFact(worker_id='worker-fixture',provider='fixture'),capabilities=(),effective_skills=())
    return binding,req,host

def test_positive_calls_existing_comparator_without_starting_work():
    m=load();b,r,h=context(m);result=m.compareNativeObservation(canonical(document()),binding=b,requested=r,host_observation=h)
    assert result.launch.decision is LaunchDecision.ALLOW
    assert result.comparator_allows is True and result.first_work_started is False
    assert result.evidence_scope=='N0_SOURCE_CONFORMANCE'

@pytest.mark.parametrize('field',['tools','composition','binding','recipe_digest','model','presentation','extension_policy','upstream_commit'])
def test_missing_load_bearing_field_refuses(field):
    m=load();b,r,h=context(m);d=document();del d[field]
    with pytest.raises(m.NativeObservationError):m.compareNativeObservation(canonical(d),binding=b,requested=r,host_observation=h)

@pytest.mark.parametrize('change',[
    lambda d:d.update(allow=True),lambda d:d.update(tools=[]),lambda d:d.update(tools=None),
    lambda d:d['tools'].reverse(),lambda d:d['tools'].append(d['tools'][0]),
    lambda d:d['tools'][0].update(implementation_digest=digest('d')),
    lambda d:d['tools'][0].update(description='changed'),
    lambda d:d['binding'].update(native_session_id='other'),
    lambda d:d['binding'].update(process_generation_id='other'),
    lambda d:d['binding'].update(worker_id='other'),
    lambda d:d.update(recipe_digest=digest('e')),
    lambda d:d['composition'][0].update(module_digest=digest('f')),
    lambda d:d['model'].update(complete=True),lambda d:d['model'].update(max_tokens=True),
    lambda d:d.update(presentation='ptc'),lambda d:d.update(extension_policy='UNKNOWN'),
])
def test_altered_unknown_or_ambiguous_evidence_refuses(change):
    m=load();b,r,h=context(m);d=document();change(d)
    with pytest.raises(m.NativeObservationError):m.compareNativeObservation(canonical(d),binding=b,requested=r,host_observation=h)

@pytest.mark.parametrize('raw',[b'{', b'\xff', b'{"format":"x","format":"y"}', b'{"number":NaN}', b' '*65537])
def test_wire_failures_are_bounded_and_do_not_echo(raw):
    m=load();b,r,h=context(m)
    with pytest.raises(m.NativeObservationError) as e:m.compareNativeObservation(raw,binding=b,requested=r,host_observation=h)
    assert str(e.value)==e.value.code and len(str(e.value))<80

def test_existing_comparator_owns_model_mismatch():
    m=load();b,r,h=context(m);d=document();d['model']['model']='wrong-model'
    result=m.compareNativeObservation(canonical(d),binding=b,requested=r,host_observation=h)
    assert result.launch.decision is LaunchDecision.REFUSE_SERVED_MODEL_MISMATCH
    assert not result.comparator_allows

def test_host_unknown_sandbox_is_not_filled_from_request():
    m=load();b,r,h=context(m);h=dataclasses.replace(h,sandbox_state=None)
    result=m.compareNativeObservation(canonical(document()),binding=b,requested=r,host_observation=h)
    assert result.launch.decision is LaunchDecision.REFUSE_UNATTESTABLE

def test_host_unknown_required_metadata_is_not_turned_into_verified_inventory():
    m=load();b,r,h=context(m);h=dataclasses.replace(h,unknown_fields=('effective_mcp',))
    with pytest.raises(m.NativeObservationError):m.compareNativeObservation(canonical(document()),binding=b,requested=r,host_observation=h)

def test_host_identity_is_checked_against_separate_binding():
    m=load();b,r,h=context(m);h=dataclasses.replace(h,auth=AuthRealmFact(worker_id='other',provider='fixture'))
    with pytest.raises(m.NativeObservationError):m.compareNativeObservation(canonical(document()),binding=b,requested=r,host_observation=h)

def test_size_depth_and_credential_shapes_refuse():
    m=load();b,r,h=context(m)
    for value in ['x'*70000, {'access_token':'sensitive-fixture-marker'}]:
        d=document();d['tools'][0]['parameters']=value
        with pytest.raises(m.NativeObservationError) as e:m.compareNativeObservation(canonical(d),binding=b,requested=r,host_observation=h)
        assert 'sensitive-fixture-marker' not in str(e.value)
    nested={}
    for _ in range(40):nested={'x':nested}
    with pytest.raises(m.NativeObservationError):m.compareNativeObservation(canonical(nested),binding=b,requested=r,host_observation=h)

def test_actual_typescript_producer_bytes_feed_existing_python_comparator():
    m=load();node=shutil.which('node')
    if node is None:pytest.skip('Node unavailable: cross-language proof NOT executed')
    version=subprocess.run([node,'--version'],capture_output=True,text=True,check=True,timeout=10).stdout.strip()
    major=int(version.removeprefix('v').split('.')[0])
    if major<24:pytest.skip('Cross-language source test requires Node >=24; native DSH remains separately held')
    p=subprocess.run([node,str(ROOT/'tests/harness_convergence/dsh_native_observation.spec.ts'),'--emit'],capture_output=True,cwd=ROOT,timeout=20)
    assert p.returncode==0,p.stderr.decode(errors='replace')
    b,r,h=context(m);result=m.compareNativeObservation(p.stdout,binding=b,requested=r,host_observation=h)
    assert result.launch.decision is LaunchDecision.ALLOW
    assert result.first_work_started is False
    assert result.evidence_scope=='N0_SOURCE_CONFORMANCE'


def test_native_census_cannot_hide_extra_host_capability():
    from control_plane.operator_harness_contract import ObservedCapabilityIdentity
    m=load();b,r,h=context(m)
    h=dataclasses.replace(h,capabilities=(ObservedCapabilityIdentity(kind='tool',name='ambient_write'),))
    with pytest.raises(m.NativeObservationError,match='HOST_EXTENSION_CONFLICT'):
        m.compareNativeObservation(canonical(document()),binding=b,requested=r,host_observation=h)

@pytest.mark.parametrize('field',['effective_skills','effective_mcp','effective_plugins_or_apps'])
def test_native_census_cannot_clear_existing_host_inventory(field):
    m=load();b,r,h=context(m);h=dataclasses.replace(h,**{field:('ambient-fixture',)})
    with pytest.raises(m.NativeObservationError,match='HOST_EXTENSION_CONFLICT'):
        m.compareNativeObservation(canonical(document()),binding=b,requested=r,host_observation=h)

def test_optional_unknown_does_not_become_a_global_veto():
    m=load();b,r,h=context(m);h=dataclasses.replace(h,unknown_fields=('provider_account_id','optional_display_label'))
    result=m.compareNativeObservation(canonical(document()),binding=b,requested=r,host_observation=h)
    assert result.launch.decision is LaunchDecision.ALLOW

def test_owner_binding_cannot_retain_mutable_aliases():
    m=load();b,r,h=context(m)
    with pytest.raises(m.NativeObservationError):dataclasses.replace(b,tools=list(b.tools))


def test_typescript_negative_suite_is_in_the_repository_gate():
    node=shutil.which('node')
    if node is None:pytest.skip('Node unavailable: TypeScript negative suite NOT executed')
    version=subprocess.run([node,'--version'],capture_output=True,text=True,check=True,timeout=10).stdout.strip()
    if int(version.removeprefix('v').split('.')[0])<24:
        pytest.skip('TypeScript source conformance suite requires Node >=24')
    p=subprocess.run([node,'--test','--test-reporter=tap',str(ROOT/'tests/harness_convergence/dsh_native_observation.spec.ts')],capture_output=True,text=True,cwd=ROOT,timeout=30)
    assert p.returncode==0,p.stdout[-5000:]+p.stderr[-2000:]
    assert '# fail 0' in p.stdout and '# skipped 0' in p.stdout


def native_config_digest(d):
    return hash_value({k:d[k] for k in ['upstream_commit','recipe_digest','presentation','extension_policy','model','tools','composition']})

def test_effective_config_is_derived_from_native_bytes_not_echoed_host_config():
    m=load();b,r,h=context(m)
    r=dataclasses.replace(r,expected_config_digest=native_config_digest(document()))
    h=dataclasses.replace(h,effective_config_digest='host-config-is-not-native-config')
    result=m.compareNativeObservation(canonical(document()),binding=b,requested=r,host_observation=h)
    assert result.launch.decision is LaunchDecision.ALLOW
    assert result.launch.observed.effective_config_digest==native_config_digest(document())

def test_native_token_setting_drift_cannot_hide_behind_matching_host_config():
    m=load();b,r,h=context(m)
    frozen=native_config_digest(document());r=dataclasses.replace(r,expected_config_digest=frozen)
    h=dataclasses.replace(h,effective_config_digest=frozen)
    d=document();d['model']['max_tokens']=65
    result=m.compareNativeObservation(canonical(d),binding=b,requested=r,host_observation=h)
    assert result.launch.decision is LaunchDecision.REFUSE_CONFIG_DRIFT
    assert not result.comparator_allows
