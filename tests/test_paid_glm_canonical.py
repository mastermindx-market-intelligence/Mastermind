"""Closed codec/issuer unit checks; no kernel/provider/installed proof claimed."""
import ast
import copy
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


def test_codec_v1_source_prefix_unchanged():
    assert (ROOT/'candidate/glm_lease_capability.py').read_bytes().startswith(
        (ROOT/'source/glm_lease_capability.py').read_bytes())


def test_v1_gateway_methods_unchanged():
    def methods(path):
        source=path.read_text();tree=ast.parse(source)
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='GlmLeaseGateway')
        return {n.name:ast.dump(n,include_attributes=False) for n in cls.body if isinstance(n,ast.FunctionDef)}
    old=methods(ROOT/'source/glm_lease_gateway.py');new=methods(ROOT/'candidate/glm_lease_gateway.py')
    for name in old:assert new[name]==old[name]


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
