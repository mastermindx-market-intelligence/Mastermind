"""New-purpose glue checks with explicit qualification-engine/platform seams.

Actual held Linux image/ACL/FD execution remains the existing initializer test
pack and future host qualification. These tests never manufacture that proof.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import urllib.request

import pytest
from ops.native_fabric.quota_continuity.candidate import paid_initializer as owner
from ops.native_fabric.quota_continuity.candidate import paid_provider_entry as entry
from tests.test_paid_provider_entry import inputs

ROOT=Path(__file__).parents[1]/'ops/native_fabric/quota_continuity/candidate'


def fixture(tmp_path,monkeypatch):
    request,body,_,capture,pre=inputs(tmp_path)
    sources={name:(ROOT/name).read_bytes() for name in entry.SOURCE_NAMES}
    hashes={name:hashlib.sha256(raw).hexdigest() for name,raw in sources.items()}
    capsule_path=Path(request['capture_root']).parent.parent/'tmp/ATT-1.glm-cap.json'
    capsule=json.loads(capsule_path.read_bytes());capsule['provider_entry']['sources_sha256']=hashes
    raw=entry.canonical(capsule);capsule_path.write_bytes(raw)
    request=entry.request_from_capsule(capsule,capsule_raw=raw,timeout_seconds=55,entry_nonce='a'*64)
    monkeypatch.setattr(owner,'_INITIALIZER_SOURCE_HASHES',{n:hashes[n] for n in entry.INITIALIZER_NAMES})
    # Explicit isolated/no-site and kernel-boot fixture premises. No real Linux
    # startup, host observation or qualification receipt is claimed.
    monkeypatch.setattr(owner,'require_no_site_policy',lambda:None)
    monkeypatch.setattr(owner,'_read_boot_id',lambda:request['boot_id'])
    monkeypatch.setattr(owner,'_current_entry_runtime',lambda:dict(
        python_path='/usr/bin/python3',kernel_executable='/usr/bin/python3',
        startup=dict(prefix='/usr',exec_prefix='/usr',base_prefix='/usr',base_exec_prefix='/usr')))
    bundle={n:sources[n] for n in entry.BUNDLE_NAMES}
    return request,bundle,pre


def test_new_entry_uses_captured_environment_and_restores_after_return(tmp_path,monkeypatch):
    request,bundle,pre=fixture(tmp_path,monkeypatch)
    before=dict(os.environ);checks=[];posts=[]
    initialized={'HOME':request['initializer_commitment']['account']['home'],
        'PATH':'/usr/bin:/bin','GLM_CONFIG':'/inert/observed.json',
        'GLM_SHIM_TOKEN':'0123456789abcdef0123456789abcdef'}
    def qualified_engine(req,probe,*,_entry):
        assert req==request and probe is None
        module=sys.modules['_fixed_canonical_paid_entry.linux_process_identity']
        monkeypatch.setattr(module,'inspect_linux_process_image',
                            lambda pid:dict(start_identity='fixture',boot_id=request['boot_id']))
        child=sys.modules['_fixed_canonical_paid_entry.paid_provider_entry']
        monkeypatch.setattr(child,'_runtime_observation',lambda:dict(
            python_path='/usr/bin/python3',python_version='3.12.3',
            startup=dict(prefix='/usr',exec_prefix='/usr',base_prefix='/usr',base_exec_prefix='/usr')))
        return _entry.execute(initialized,pre,lambda:(_entry.check(),checks.append(1)),None)
    monkeypatch.setattr(owner,'_run_owner',qualified_engine)
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,n):
            return entry.canonical(dict(status='completed',error=None,incomplete_details=None,
                output=[dict(type='message',role='assistant',status='completed',
                    content=[dict(type='output_text',text='{"summary":"fixed"}')])]))
    def open_(request,timeout):
        assert dict(os.environ)==initialized
        assert 0<timeout<=55
        posts.append(1);return Response()
    monkeypatch.setattr(urllib.request,'build_opener',lambda *a:SimpleNamespace(open=open_))
    assert owner.run_canonical_entry(request,source_bundle=bundle)==b'{"summary":"fixed"}'
    assert posts==[1] and checks and dict(os.environ)==before
    assert '_fixed_canonical_paid_entry' not in sys.modules


@pytest.mark.parametrize('fault',['source','extra','initializer','expired','boot','mixed-image','old-purpose'])
def test_new_purpose_refuses_before_qualification_private_effects(tmp_path,monkeypatch,fault):
    request,bundle,_=fixture(tmp_path,monkeypatch);calls=[]
    monkeypatch.setattr(owner,'_run_owner',lambda *a,**k:calls.append('FORBIDDEN_PRIVATE_INIT'))
    if fault=='source':bundle['paid_provider_entry.py']+=b'\nraise RuntimeError("UNTRUSTED")\n'
    elif fault=='extra':bundle['caller.py']=b'print("FORBIDDEN")'
    elif fault=='initializer':request['sources_sha256']['paid_initializer.py']='0'*64
    elif fault=='expired':request['deadline_monotonic_ns']=1
    elif fault=='boot':request['boot_id']='foreign-boot';monkeypatch.setattr(owner,'_read_boot_id',lambda:'original-boot')
    elif fault=='mixed-image':request['initializer_commitment']['launch_python']['path']='/other/python3'
    else:request['purpose']='canonical-paid-qualification.v1'
    with pytest.raises(ValueError):owner.run_canonical_entry(request,source_bundle=bundle)
    assert calls==[]


def test_environment_drift_after_dispatch_refuses_and_restores_without_replay(tmp_path,monkeypatch):
    request,bundle,pre=fixture(tmp_path,monkeypatch);before=dict(os.environ);posts=[]
    initialized={'HOME':request['initializer_commitment']['account']['home'],'PATH':'/usr/bin:/bin'}
    def qualified_engine(req,probe,*,_entry):
        module=sys.modules['_fixed_canonical_paid_entry.linux_process_identity']
        monkeypatch.setattr(module,'inspect_linux_process_image',
                            lambda pid:dict(start_identity='fixture',boot_id=request['boot_id']))
        child=sys.modules['_fixed_canonical_paid_entry.paid_provider_entry']
        monkeypatch.setattr(child,'_runtime_observation',lambda:dict(
            python_path='/usr/bin/python3',python_version='3.12.3',
            startup=dict(prefix='/usr',exec_prefix='/usr',base_prefix='/usr',base_exec_prefix='/usr')))
        return _entry.execute(initialized,pre,_entry.check,None)
    monkeypatch.setattr(owner,'_run_owner',qualified_engine)
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,n):
            os.environ['GLM_CONFIG']='/foreign/after-dispatch'
            return entry.canonical(dict(status='completed',error=None,incomplete_details=None,
                output=[dict(type='message',role='assistant',status='completed',
                    content=[dict(type='output_text',text='{"summary":"unaccepted"}')])]))
    def open_(request,timeout):posts.append(1);return Response()
    monkeypatch.setattr(urllib.request,'build_opener',lambda *a:SimpleNamespace(open=open_))
    with pytest.raises(owner.InitializerCommitmentRefused):owner.run_canonical_entry(request,source_bundle=bundle)
    assert posts==[1] and dict(os.environ)==before


def test_old_qualification_wrapper_keeps_exact_default_call(monkeypatch):
    seen=[];request={'original':'DATA'}
    monkeypatch.setattr(owner,'_run_owner',lambda *a,**k:(seen.append((a,k)) or b'original'))
    assert owner.run_bootstrap(request,'fixed probe')==b'original'
    assert seen==[((request,'fixed probe'),{})]
