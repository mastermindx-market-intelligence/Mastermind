"""Actual Macro -> Control -> Bridge -> native producer; inert OS boundaries.

Positive provider cases below are explicitly synthetic validator vectors, not
evidence that the current native reader observes provider authentication.
"""
import asyncio
import copy
import dataclasses
from datetime import UTC, datetime
import hashlib
import importlib.util
import os
from pathlib import Path
import time
from types import MappingProxyType
import pytest
from control_plane import native_capacity_acquisition as acquisition
from control_plane import native_capacity_v2 as v2
from control_plane.executive_fabric_composition import FabricBindingSource
from tests.test_control_native_capacity_reader import reader, native, bound, enrolled

# The default suite uses frozen test-only Macro bytes, never an installed producer.
# Explicit cross-repository qualification points at the actual Macro checkout.
_MACRO_ROOT=os.environ.get('MASTERMIND_TEST_MACRO_SOURCE')
MACRO=(Path(_MACRO_ROOT)/'engine'/'provider_capacity_v2.py' if _MACRO_ROOT else
       Path(__file__).parent/'fixtures'/'native_capacity_v2'/'macro_producer.py')
_PRODUCER_SHA256='946537a8abf54715d5ba98d21ada007bb535f1c12a45ccb69915eb5db19ed9ab'
assert hashlib.sha256(MACRO.read_bytes()).hexdigest()==_PRODUCER_SHA256, 'Macro test input changed'

@pytest.fixture
def composed(reader, monkeypatch):
    data=MACRO.read_bytes()
    # Existing fixture's actual source export is the release authority.
    from ops.executive_os.capacity_source_contract import acquire_control_native_registration
    registration=acquire_control_native_registration(reader.probe,reader.physical)
    reader.raw['native_capacity_v2']={'macro_release':registration['source_release_commit'],
        'producer_sha256':hashlib.sha256(data).hexdigest()}
    bindings=FabricBindingSource(Path('/fixture/bindings'), 'a'*64,(reader.physical,),(),MappingProxyType({}),MappingProxyType({}))
    monkeypatch.setattr(FabricBindingSource,'__call__',lambda self,h,w:reader.physical)
    owner=acquisition.NativeCapacitySource.from_startup(reader.probe,bindings)
    # The actual Macro bytes run. Only sealed-file custody is a fixture here;
    # separate tests below exercise the real pinned file reader.
    monkeypatch.setattr(acquisition.NativeCapacitySource,'_read_producer',lambda self:data)
    return owner,reader

def test_real_composition_preserves_unknowns_and_no_provider_effect(composed):
    owner,reader=composed
    result=asyncio.run(owner.acquire())
    row=result['slots'][0]
    assert row['provider_enabled'] is None
    assert row['realm_auth']['state']==row['provider_health']['state']=='unknown'
    assert row['quota_horizons']==[] and row['cooling']['active'] is None
    assert len(reader.requests)==1 and reader.native.backend._attempted is False
    join={'schema':v2.JOIN_SCHEMA,'provider_capacity_schema':v2.SCHEMA,
          **{k:row[k] for k in ('host_ref','capacity_capability_id','capability_generation','worker_source_config_digest')}}
    with pytest.raises(v2.NativeCapacityRefusal,match='ENABLEMENT_UNQUALIFIED'):
        v2.known_admissible(result,join,now_ms=time.time_ns()//1_000_000)

def test_public_producer_has_no_facts_or_unbound_source(composed):
    owner,reader=composed
    spec=importlib.util.spec_from_file_location('macro_v2_subject',MACRO)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    with pytest.raises(TypeError): module.build_snapshot(observations={})
    with pytest.raises(acquisition.NativeCapacityAcquisitionError,match='SOURCE_UNBOUND'):
        asyncio.run(module.build_snapshot())
    assert reader.requests==[]

@pytest.mark.parametrize('fault',['nonce','host_ref','boot_ref','source_receipt_digest','realm_generation','stale','source-change'])
def test_actual_owner_drift_never_normalizes_or_retries(composed,fault):
    owner,reader=composed;reader.fault=fault
    with pytest.raises(Exception):asyncio.run(owner.acquire())
    assert len(reader.requests)==1 and reader.native.backend._attempted is False

def good_snapshot(now):
    stamp=datetime.fromtimestamp(now/1000,UTC).isoformat(timespec='milliseconds').replace('+00:00','Z')
    reset=datetime.fromtimestamp((now+60000)/1000,UTC).isoformat(timespec='milliseconds').replace('+00:00','Z')
    row={'host_ref':'host-'+'a'*64,'boot_ref':'boot-'+'b'*64,'capacity_capability_id':'ncap_test',
        'capability_generation':3,'realm_generation':2,'enrollment_receipt_digest':'e'*64,
        'provider':'minimax','provider_enabled':True,'worker_source_config_digest':'c'*64,'observed_at':stamp,
        'realm_auth':{'state':'authenticated','method':'subscription_api_key','source_quality':'native_provider'},
        'provider_health':{'state':'healthy','error_class':None,'scope':'capability_generation','observed_at':stamp},
        'cooling':{'active':False,'kind':None,'reset_at':None,'evidence':'native_provider','scope':'capability_generation','observed_at':stamp},
        'quota_horizons':[{'name':'subscription','remaining':1,'limit':10,'reset_at':reset,'scope':'capability_generation','observed_at':stamp}],
        'last_provider_outcome':{'class':'success','scope':'capability_generation','observed_at':stamp}}
    value={'schema':v2.SCHEMA,'generated_at_ms':now,'source':{
        'source_release_commit':'a'*40,'previous_release_commit':'b'*40,'material_source_digest':'d'*64,
        'source_receipt_digest':'f'*64,'registration_receipt_digest':'0'*64},'producer_sha256':'1'*64,'slots':[row]}
    value['snapshot_hash']=v2.digest(value)
    join={'schema':v2.JOIN_SCHEMA,'provider_capacity_schema':v2.SCHEMA,
        **{k:row[k] for k in ('host_ref','capacity_capability_id','capability_generation','worker_source_config_digest')}}
    return value,join

@pytest.mark.parametrize('fault',['schema','extra','hash','bool-generation','unbound','unknown-enabled',
    'unknown-auth','unknown-health','unknown-cooling','quota-empty','quota-zero','stale','host-local','duplicate'])
def test_strict_consumer_and_known_only_policy(fault):
    now=time.time_ns()//1_000_000;value,join=good_snapshot(now);row=value['slots'][0]
    assert v2.known_admissible(value,join,now_ms=now)['provider']=='minimax'
    if fault=='schema':value['schema']='mastermind.provider_capacity.v1'
    if fault=='extra':row['available']=True
    if fault=='bool-generation':row['capability_generation']=True
    if fault=='unbound':row['host_ref']='local-unbound'
    if fault=='unknown-enabled':row['provider_enabled']=None
    if fault=='unknown-auth':row['realm_auth']['state']='unknown'
    if fault=='unknown-health':row['provider_health']['state']='unknown'
    if fault=='unknown-cooling':row['cooling']['active']=None
    if fault=='quota-empty':row['quota_horizons']=[]
    if fault=='quota-zero':row['quota_horizons'][0]['remaining']=0
    if fault=='stale':now+=60000
    if fault=='host-local':row['provider_health']['scope']='host_local'
    if fault=='duplicate':value['slots'].append(copy.deepcopy(row))
    value['snapshot_hash']=v2.digest({k:v for k,v in value.items() if k!='snapshot_hash'})
    if fault=='hash':value['snapshot_hash']='f'*64
    with pytest.raises(v2.NativeCapacityRefusal):v2.known_admissible(value,join,now_ms=now)


def test_default_absent_and_public_source_constructor_refuse(composed):
    owner,reader=composed
    del reader.raw['native_capacity_v2']
    assert acquisition.NativeCapacitySource.from_startup(owner.probe,owner.bindings) is None
    with pytest.raises(acquisition.NativeCapacityAcquisitionError):
        acquisition.NativeCapacitySource(None,owner.probe,owner.bindings,owner.release,owner.digest)
    assert reader.requests==[]


@pytest.mark.parametrize('fault',['bytes','oversize','custody','renamed'])
def test_exact_fixed_macro_file_reader_refuses_changed_bytes_or_owner(composed,monkeypatch,tmp_path,fault):
    import contextlib
    from control_plane import codex_provider_realm as realm
    from ops.executive_os.capacity_source_contract import SYSTEM_ROOT
    owner,_=composed
    data=MACRO.read_bytes()
    local=tmp_path/'producer.py'
    local.write_bytes(b'x'*65537 if fault=='oversize' else data+b'\n' if fault=='bytes' else data)
    @contextlib.contextmanager
    def held(path):
        assert path==SYSTEM_ROOT/'capacity-sources'/'macro'/owner.release/acquisition.PRODUCER_RELATIVE
        if fault=='custody':raise realm.ProviderRealmError('NATIVE_REALM_IDENTITY_UNAVAILABLE')
        with local.open('rb') as stream:
            yield stream.fileno(),os.fstat(stream.fileno())
            if fault=='renamed':raise realm.ProviderRealmError('NATIVE_REALM_IDENTITY_UNAVAILABLE')
    monkeypatch.setattr(realm,'_native_open',held)
    # Restore the actual file reader; only its established custody primitive is
    # fixture-owned. Failures must propagate, not normalize a caller path.
    original=Path(acquisition.__file__).read_text()
    ns={'__name__':'inert_reader_test'};exec(compile(original,acquisition.__file__,'exec'),ns)
    with pytest.raises((realm.ProviderRealmError,acquisition.NativeCapacityAcquisitionError,ns['NativeCapacityAcquisitionError'])):
        ns['NativeCapacitySource']._read_producer(owner)


@pytest.mark.parametrize('fault',['inactive-reset','inactive-kind','failed-outcome'])
def test_contradictory_positive_facts_refuse(fault):
    now=time.time_ns()//1_000_000;value,join=good_snapshot(now);row=value['slots'][0]
    if fault=='inactive-reset':row['cooling']['reset_at']=row['quota_horizons'][0]['reset_at']
    if fault=='inactive-kind':row['cooling']['kind']='provider'
    if fault=='failed-outcome':row['last_provider_outcome']['class']='auth_failure'
    value['snapshot_hash']=v2.digest({k:v for k,v in value.items() if k!='snapshot_hash'})
    with pytest.raises(v2.NativeCapacityRefusal):v2.known_admissible(value,join,now_ms=now)
