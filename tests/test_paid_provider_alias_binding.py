"""Actual dca assembly DATA interoperability, never host/qualification proof."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest
from ops.native_fabric.quota_continuity.candidate import paid_provider_entry as entry
from ops.native_fabric.quota_continuity.candidate import paid_initializer as owner
from tests.test_paid_provider_entry import inputs

FIXTURE=Path(__file__).with_name('fixtures')/'h1_dca50013_commitment.json'


def wrapper_request(tmp_path):
    raw=FIXTURE.read_bytes()
    assert hashlib.sha256(raw).hexdigest()=='dd78c9d37ae78e5609d904a5d34420e3716829c6f5674868046fe11e0930cbc5'
    data=json.loads(raw)
    assert data['source_sha256']=='726544463fa6c4058512a558f70e5d0c585f9742594d20363f873b0b2d0fb8e7'
    assert data['output']['status']=='DATA_CANDIDATE_NOT_APPROVAL_NOT_QUALIFICATION'
    c=data['output']['commitment']
    assert entry.digest(c)==data['output']['commitment_sha256']
    req,*_=inputs(tmp_path)
    req.update(initializer_commitment=c,initializer_commitment_sha256=entry.digest(c),
        host_ref=c['host_ref'],transport_alias=c['transport_alias'],
        python_path=c['launch_python']['path'],capture_root=c['lane_root']+'/ext/lanes',
        config_identity=[1,20,0o100600,c['account']['uid'],c['account']['gid'],1,30,5,6])
    return req


def test_actual_dca_assembled_alias_keeps_observed_selector_and_fixed_image(tmp_path):
    req=wrapper_request(tmp_path);c=req['initializer_commitment']
    assert c['bootstrap_python']['path']=='/usr/bin/python3.12'
    assert c['launch_python']['path']=='/usr/bin/python3'
    assert c['bootstrap_python']!=c['launch_python']  # actual 7ae failure witness
    checked=entry.validate_request(req)
    assert checked==req and checked['python_path']=='/usr/bin/python3'
    assert entry.same_entry_image(c)


@pytest.mark.parametrize('mutation',['image','real-path','selector'])
def test_actual_wrapper_image_or_observed_selector_mismatch_refuses(tmp_path,mutation):
    req=wrapper_request(tmp_path);c=req['initializer_commitment']
    if mutation=='image':c['launch_python']['sha256']='0'*64
    elif mutation=='real-path':c['launch_python']['real_path']='/other/python3.12'
    else:req['python_path']='/other/python3'
    req['initializer_commitment_sha256']=entry.digest(c)
    with pytest.raises(entry.ProviderEntryRefused):entry.validate_request(req)


@pytest.mark.parametrize('mutation',[None,'prefix','selector','kernel-image'])
def test_actual_current_runtime_predicate_has_no_expected_selector_rewrite(tmp_path,monkeypatch,mutation):
    req=wrapper_request(tmp_path)
    observed=dict(python_path='/usr/bin/python3',kernel_executable='/usr/bin/python3.12',
        startup=dict(prefix='/usr',exec_prefix='/usr',base_prefix='/usr',base_exec_prefix='/usr'))
    if mutation=='prefix':observed['startup']['prefix']='/home/user/venv'
    elif mutation=='selector':observed['python_path']='/home/user/venv/bin/python3'
    elif mutation=='kernel-image':observed['kernel_executable']='/other/python3.12'
    monkeypatch.setattr(owner,'_current_entry_runtime',lambda:deepcopy(observed))
    before=deepcopy(req)
    if mutation is None:owner._require_current_entry_runtime(req)
    else:
        with pytest.raises(owner.InitializerCommitmentRefused):owner._require_current_entry_runtime(req)
    assert req==before
