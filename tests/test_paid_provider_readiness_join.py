"""Actual A/B current-state reader → C descriptor, with Root custody simulated.

No installed definition, root grant, controller/host or real readiness is read.
The one external constructor seam is explicit; actual fixed state parser,
freshness/account checks, source hashes and backend projection are unchanged.
"""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest
from control_plane import paid_fabric_backend as backend
from control_plane import paid_fabric_wire as wire
from control_plane.paid_model_execution_contract import digest,paid_host_reference
from ops.native_fabric.quota_continuity.candidate import paid_host_readiness as readiness
from ops.native_fabric.quota_continuity.candidate import paid_provider_entry as entry
from tests.test_paid_provider_entry import bound_material
from tests.test_paid_host_readiness import OwnerMetadataFixture

ROOT=Path(__file__).parents[1]
NATIVE=ROOT/'ops/native_fabric/quota_continuity/candidate'


@pytest.fixture
def joined(tmp_path,monkeypatch):
    p,_,_,_,old=bound_material(tmp_path)
    source=p['paid_source_config'];q=source['qualification'];c=q['initializer_commitment']
    q.update(registry_key='ubuntu0',transport_alias='mmx-ubuntu0',
             boot_id='12345678-1234-1234-1234-123456789abc')
    c.update(host_ref='ubuntu0',transport_alias='mmx-ubuntu0')
    q['initializer_commitment_sha256']=digest(c)
    source['host_ref']=paid_host_reference('ubuntu0','mmx-ubuntu0')
    hashes={n:hashlib.sha256((NATIVE/n).read_bytes()).hexdigest() for n in entry.SOURCE_NAMES}
    q['qualifier_sources_sha256'].update({n:hashes[n] for n in entry.INITIALIZER_NAMES})
    physical=deepcopy(source);physical.pop('capacity_capability_id')
    physical.update(schema_version='mastermind.paid_fabric_host_binding/v1',
                    worker_source_config_digest=digest(source))
    p.update(paid_physical_binding=physical,physical_binding_sha256=digest(physical))
    p['paid_route']['host_ref']=source['host_ref']
    validator=(ROOT/'ops/native_fabric/quota_continuity/source/glm_keys.py').read_bytes()
    b=dict(old['readiness_binding']);b.update(host=q['registry_key'],transport_alias=q['transport_alias'],
        boot_id=q['boot_id'],source_config_sha256=digest(source),
        initializer_commitment_sha256=q['initializer_commitment_sha256'],
        validator_sha256=hashlib.sha256(validator).hexdigest(),
        readiness_source_sha256=hashlib.sha256((NATIVE/'paid_host_readiness.py').read_bytes()).hexdigest())
    checks=[]
    ctx=readiness.InstalledReadinessContext(readiness._SEAL,binding=b,commitment=c,
        sources={n:(NATIVE/n).read_bytes() for n in entry.SOURCE_NAMES},
        root=ROOT,checks=[lambda:checks.append('qualified-source-seam')])
    @contextmanager
    def installed():ctx.check();yield ctx;ctx.check()
    monkeypatch.setattr(readiness,'open_installed_context',installed)
    monkeypatch.setitem(sys.modules,'paid_host_readiness',readiness)
    owner_path=tmp_path/'owner';directory=owner_path/'state/hosts';directory.mkdir(parents=True,mode=0o700)
    monkeypatch.setattr(readiness,'_OWNER',owner_path)
    import os
    monkeypatch.setattr(readiness,'os',OwnerMetadataFixture(os))
    monkeypatch.setattr(readiness.time,'time',lambda:1000)
    config=old['config_identity']
    envelope=dict(schema=readiness.SCHEMA,config_scope=readiness.SCOPE,
        host='ubuntu0',transport_alias='mmx-ubuntu0',mode='glm',context=b,
        validator_sha256=b['validator_sha256'],observed_at=1000,status='known',
        accounts={p['paid_account']:True},config_identity=config)
    document=dict(host='ubuntu0',ts=1000,reachable=True,boot_id=q['boot_id'],
                  glm_local_account_readiness=envelope)
    path=directory/'ubuntu0.json';path.write_bytes(readiness.canonical(document));path.chmod(0o600)
    startup=SimpleNamespace(native_ext=NATIVE,release_root=ROOT,
        sources={str((NATIVE/n).relative_to(ROOT)):h for n,h in hashes.items()})
    owner=object.__new__(backend.CanonicalPaidBackend);owner._startup=startup
    owner._require_source_context=lambda payload:None if payload==p else entry.refuse()
    # Root sealed-file custody is the one disclosed external fixture premise.
    # The real exact path/vector/hash comparisons in the backend still execute.
    monkeypatch.setattr(backend,'_root_source',lambda selected:
        selected.read_bytes() if selected.parent==NATIVE and selected.name in hashes else entry.refuse())
    return owner,p,path,document,config,checks


def test_backend_consumes_actual_qualified_state_and_stable_config_identity(joined):
    owner,p,path,doc,config,checks=joined
    first=owner._provider_entry_descriptor(p)
    assert first['config_identity']==config and first['run_id']==p['binding']['attempt_id']
    assert first['readiness_binding_sha256']==digest(first['readiness_binding']) and checks
    # A later same-config observation does not rewrite an in-flight descriptor.
    doc['glm_local_account_readiness']['observed_at']=999.5
    path.write_bytes(readiness.canonical(doc))
    assert owner._provider_entry_descriptor(p)==first
    first['config_identity'][1]+=1
    assert owner._provider_entry_descriptor(p)['config_identity']==config


@pytest.mark.parametrize('mutation',['legacy','stale','unknown','false','foreign-account',
    'foreign-context','wrong-boot','config-owner','config-mode','initializer-source'])
def test_current_unknown_or_mixed_observation_has_no_canonical_fallback(joined,mutation):
    owner,p,path,doc,_,_=joined;value=doc['glm_local_account_readiness']
    if mutation=='legacy':value['schema']='mastermind.glm_local_account_readiness.v1'
    elif mutation=='stale':value['observed_at']=1
    elif mutation=='unknown':value.update(status='unknown',accounts={},config_identity=None)
    elif mutation=='false':value['accounts'][p['paid_account']]=False
    elif mutation=='foreign-account':value['accounts']={'other':True}
    elif mutation=='foreign-context':value['context']['source_config_sha256']='0'*64
    elif mutation=='wrong-boot':doc['boot_id']='foreign'
    elif mutation=='config-owner':value['config_identity'][3]+=1
    elif mutation=='config-mode':value['config_identity'][2]=0o100644
    else:p['paid_source_config']['qualification']['initializer_commitment']['host_ref']='foreign'
    path.write_bytes(readiness.canonical(doc))
    with pytest.raises(ValueError):owner._provider_entry_descriptor(p)
