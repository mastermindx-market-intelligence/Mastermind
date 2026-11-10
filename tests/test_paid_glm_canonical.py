"""Closed codec/issuer unit checks; no kernel/provider/installed proof claimed."""
import ast
import copy
import hashlib
import importlib.util
from pathlib import Path
import sys
import pytest

from control_plane.fabric_control_start import ControlStartAuthority

ROOT=Path(__file__).parents[1]/'ops/native_fabric/paid_canonical_glm'
KEY=b'k'*32
NOW=1000000


@pytest.fixture
def modules(monkeypatch):
    def load(name,path):
        spec=importlib.util.spec_from_file_location(name,path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
    cap=load('paid_fixture_codec',ROOT/'candidate/glm_lease_capability.py')
    monkeypatch.setitem(sys.modules,'glm_lease_capability',cap)
    gateway=load('paid_fixture_gateway',ROOT/'candidate/glm_lease_gateway.py')
    return cap,gateway


def lease(model='glm-5.3-flash',pool='glm'):
    return dict(id='lease-1',orchestrator_id='JOB-root',pool=pool,account='account-1',
                model=model,host='ubuntu3',pid=100,granted_at=NOW-10,ttl=600,
                last_heartbeat=NOW,state='held',renewable=1)


def scope(model='glm-5.3-flash'):
    return dict(root='JOB-root',job_id='JOB-child',attempt_id='ATT-1',parent_job_id='JOB-root',
                effective_grant_digest='a'*64,commission_sha256='b'*64,
                physical_binding_sha256='c'*64,model=model,host='ubuntu3',fence=1,pin_version=2,
                payload_sha256='d'*64,request_body_sha256='e'*64,result_schema_sha256='f'*64,
                now=NOW,ttl=60)


# Exact, SHA-pinned predecessor for finite long-horizon six-comparator amendment.
# This is stronger than merely accepting arbitrary changes in the legacy prefix.
PRE_LONG_CODEC_SHA='eb473e0ebe5c2cdf67fd8f1a2f689a5d2218a6a33e7ce7c9a32ff50fc868062f'
PRE_LONG_GATEWAY_SHA='f70e233fae56590e51b0431d2f1b8f833ffb072c404b9ba9285eb335b65d0710'
POST_LONG_CODEC_SHA='3e4e2ad4dbdfd2ead14ef764adb0e134d6d73e907ef0edebe1d692d1b155a48c'
POST_LONG_GATEWAY_SHA='3ab7ae015d8093f81ab41d8ae73dd849572c8718530750d70ffe551aa719e258'


def test_codec_v1_source_prefix_unchanged_except_exact_finite_ttl_ceiling():
    old=(ROOT/'source/glm_lease_capability.py').read_bytes()
    new=(ROOT/'candidate/glm_lease_capability.py').read_bytes()
    assert hashlib.sha256(new).hexdigest()=='ccfe3c6f4f08778d6d179d60da67f393f000b66e4997a2502a7ad180c6a571a6'
    new=new[:17698]
    assert new.count(b'15000')==4 and b'7500' not in new
    assert hashlib.sha256(new).hexdigest()==POST_LONG_CODEC_SHA
    # Restore four exact predecessor TTL literals and check the entire original.
    baseline=new.replace(b'15000',b'7500')
    assert hashlib.sha256(baseline).hexdigest()==PRE_LONG_CODEC_SHA
    assert baseline.startswith(old)
    # The original signed-token source itself is never edited or reinterpreted.
    assert old.count(b'7500')==2


def test_v1_gateway_methods_unchanged_except_exact_finite_ttl_ceiling():
    old=(ROOT/'source/glm_lease_gateway.py').read_bytes()
    new=(ROOT/'candidate/glm_lease_gateway.py').read_bytes()
    assert hashlib.sha256(new).hexdigest()=='2b2e47c2e9f01ba72a33603e17465c96c084e79a32c331a8d52d0f4039bfbef7'
    new=new[:14300]
    assert new.count(b'15000')==2 and b'7500' not in new
    assert hashlib.sha256(new).hexdigest()==POST_LONG_GATEWAY_SHA
    baseline=new.replace(b'15000',b'7500')
    assert hashlib.sha256(baseline).hexdigest()==PRE_LONG_GATEWAY_SHA
    def methods(source):
        tree=ast.parse(source)
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='GlmLeaseGateway')
        return {n.name:ast.dump(n,include_attributes=False) for n in cls.body if isinstance(n,ast.FunctionDef)}
    original=methods(old);normalized=methods(baseline)
    for name in original:assert normalized[name]==original[name]


def test_real_codec_roundtrip_native_lease_columns(modules):
    cap,_=modules;l=lease();token=cap.mint_canonical(KEY,l,**scope())
    result=cap.authorize_canonical(token,KEY,lambda _:l,model=l['model'],run_id='ATT-1',host='ubuntu3',now=NOW+1)
    assert result['fence']==1 and result['parent_job_id']=='JOB-root'


@pytest.mark.parametrize('model,pool',[('glm-5.3-flash','glm'),('glm-5.3','glm-frontier')])
def test_pool_scope_matches_actual_existing_broker_route(modules,model,pool):
    cap,_=modules;l=lease(model,pool)
    token=cap.mint_canonical(KEY,l,**scope(model))
    cap.authorize_canonical(token,KEY,lambda _:l,model=model,run_id='ATT-1',host='ubuntu3',now=NOW+1)


@pytest.mark.parametrize('field,value',[('host','ubuntu0'),('model','wrong'),('pool','bailian'),
                                       ('pool','glm-frontier'),('pid',101),('account','other'),
                                       ('orchestrator_id','other'),('state','released')])
def test_current_lease_disagreement_refuses_before_use(modules,field,value):
    cap,_=modules;l=lease();token=cap.mint_canonical(KEY,l,**scope());l[field]=value
    with pytest.raises(cap.CapabilityError):
        cap.authorize_canonical(token,KEY,lambda _:l,model='glm-5.3-flash',run_id='ATT-1',host='ubuntu3',now=NOW+1)


def test_root_parent_is_actual_null_not_invented_root_parent(modules):
    cap,_=modules;s=scope();s.update(job_id='JOB-root',parent_job_id=None)
    token=cap.mint_canonical(KEY,lease(),**s)
    result=cap.authorize_canonical(token,KEY,lambda _:lease(),model='glm-5.3-flash',run_id='ATT-1',host='ubuntu3',now=NOW+1)
    assert result['parent_job_id'] is None
    s['job_id']='JOB-child'
    with pytest.raises(cap.CapabilityError):cap.mint_canonical(KEY,lease(),**s)


@pytest.mark.parametrize('fence',[None,True,'1',0,-1])
def test_runtime_fence_is_genuine_integer_shape(modules,fence):
    cap,_=modules;s=scope();s['fence']=fence
    with pytest.raises(cap.CapabilityError):cap.mint_canonical(KEY,lease(),**s)


def test_v1_token_never_upgrades_to_canonical(modules):
    cap,_=modules;l=lease()
    token=cap.mint(KEY,l,root='JOB-root',model=l['model'],run_id='ATT-1',host='ubuntu3',now=NOW,ttl=60)
    with pytest.raises(cap.CapabilityError):
        cap.authorize_canonical(token,KEY,lambda _:l,model=l['model'],run_id='ATT-1',host='ubuntu3',now=NOW+1)


def test_field_constructed_actual_authority_refuses_before_any_db_read(modules):
    _,gw=modules
    owner=object.__new__(gw.GlmLeaseGateway)
    calls=[];owner._connection=lambda:calls.append('forbidden')
    authority=ControlStartAuthority(payload_sha256='a'*64,pin_identity_sha256='b'*64,
        attempt_id='ATT-1',fence_generation=1,pin_version=2,expires_at=NOW+60)
    with pytest.raises(gw.CanonicalCapabilityError):
        owner._issue_canonical({},authority=authority,lease_id='lease-1',ttl=60,request_body={})
    assert calls==[]



def test_four_hour_legacy_signed_lease_roundtrip_and_scope_guards(modules):
    cap,_=modules
    l=lease();l['ttl']=16000
    token=cap.mint(KEY,l,root='JOB-root',model=l['model'],
                   run_id='ATT-1',host='ubuntu3',now=NOW,ttl=15000)
    value=cap.authorize(token,KEY,lambda _:l,model=l['model'],
                        run_id='ATT-1',host='ubuntu3',now=NOW+1)
    assert value['expires_at']-value['issued_at']==15000
    assert value['root']=='JOB-root' and value['lease_id']=='lease-1'
    # A signed token cannot grant authority beyond the current matching lease.
    for action in ('other_host','other_model','released_lease','stale_heartbeat','expired_token'):
        with pytest.raises(cap.CapabilityError):
            changed=copy.deepcopy(l)
            model=l['model'];host='ubuntu3';clock=NOW+1
            if action=='other_host':host='ubuntu1'
            elif action=='other_model':model='other-model'
            elif action=='released_lease':changed['state']='released'
            elif action=='stale_heartbeat':changed['last_heartbeat']=NOW-16001
            elif action=='expired_token':clock=NOW+15000
            cap.authorize(token,KEY,lambda _:changed,model=model,
                          run_id='ATT-1',host=host,now=clock)
    for invalid in (15001,0,-1,True,1.5):
        with pytest.raises(cap.CapabilityError):
            cap.mint(KEY,l,root='JOB-root',model=l['model'],
                     run_id='ATT-1',host='ubuntu3',now=NOW,ttl=invalid)
    # Original <=7500 signed generation tokens stay readable.
    old=cap.mint(KEY,l,root='JOB-root',model=l['model'],
                 run_id='ATT-1',host='ubuntu3',now=NOW,ttl=7500)
    assert cap.authorize(old,KEY,lambda _:l,model=l['model'],
                         run_id='ATT-1',host='ubuntu3',now=NOW+1)['v']==1


def test_four_hour_canonical_v2_signed_lease_is_independent(modules):
    cap,_=modules
    l=lease();l['ttl']=16000
    s=scope();s['ttl']=15000
    token=cap.mint_canonical(KEY,l,**s)
    value=cap.authorize_canonical(token,KEY,lambda _:l,model=l['model'],
                                  run_id='ATT-1',host='ubuntu3',now=NOW+1)
    assert value['expires_at']-value['issued_at']==15000
    assert value['fence']==1 and value['commission_sha256']=='b'*64
    with pytest.raises(cap.CapabilityError):
        cap.authorize(token,KEY,lambda _:l,model=l['model'],
                      run_id='ATT-1',host='ubuntu3',now=NOW+1)
    with pytest.raises(cap.CapabilityError):
        cap.authorize_canonical(token,KEY,lambda _:l,model=l['model'],
                                run_id='ATT-1',host='ubuntu0',now=NOW+1)
    with pytest.raises(cap.CapabilityError):
        cap.mint_canonical(KEY,l,**{**s,'ttl':15001})


def test_four_hour_http_gateway_mints_only_matching_broker_lease(modules):
    cap,gateway=modules
    l=lease();l['ttl']=16000
    class ReadOnlyConnection:
        def close(self):pass
    owner=object.__new__(gateway.GlmLeaseGateway)
    owner._models=frozenset({l['model']})
    owner._accounts=frozenset({l['account']})
    owner._clock=lambda:NOW
    owner._signing_key=KEY
    owner._connection=lambda:ReadOnlyConnection()
    owner._lease_lookup=lambda connection,lease_id:l if lease_id==l['id'] else None
    request=dict(lease_id=l['id'],root='JOB-root',model=l['model'],
                 run_id='ATT-1',host='ubuntu3',ttl=15000)
    issued=owner.issue(request)
    assert issued['expires_at']==NOW+15000
    assert cap.authorize(issued['token'],KEY,lambda _:l,model=l['model'],
                         run_id='ATT-1',host='ubuntu3',now=NOW+1)['v']==1
    with pytest.raises(gateway.LeaseGatewayError):
        owner.issue({**request,'ttl':15001})
    with pytest.raises(gateway.LeaseGatewayError):
        owner.issue({**request,'ttl':True})
    with pytest.raises(gateway.LeaseGatewayError):
        owner.issue({**request,'model':'unqualified'})
    # Real broker expiry/state remains authoritative; no extension by token.
    with pytest.raises(cap.CapabilityError):
        cap.authorize(issued['token'],KEY,lambda _:{**l,'state':'released'},
                      model=l['model'],run_id='ATT-1',host='ubuntu3',now=NOW+1)
