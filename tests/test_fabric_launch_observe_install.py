from __future__ import annotations

import json
from pathlib import Path
import subprocess
import types
import urllib.error

import pytest

from ops.fabric_launch import observe as observer
from ops.fabric_launch import install


@pytest.fixture
def no_real_commands(monkeypatch):
    calls=[]
    def command(argv,**kwargs):
        calls.append((argv,kwargs))
        return types.SimpleNamespace(returncode=0,stdout=b'fixture-read',stderr=b'')
    monkeypatch.setattr(observer.subprocess,'run',command)
    monkeypatch.setattr(observer.shutil,'which',lambda name:'/fixture/'+name)
    return calls


def test_doctor_never_claims_unprobed_writes_or_dispatch(tmp_path,no_real_commands):
    result=observer.observe('fixture.mission',tmp_path,repository='owner/repo')
    rows={r['tool']:r for r in result['items']}
    assert rows['workspace.read']['state']=='CALLABLE'
    assert rows['python.run']['state']=='CALLABLE'
    assert rows['github.read']['state']=='CALLABLE'
    for name in ('workspace.write','git.branch-write','github.pr-write','paper.edit','company.reply','executive.child-submit','tests.run'):
        assert rows[name]['state']=='UNKNOWN'
    assert len(no_real_commands)==4
    for argv,kwargs in no_real_commands:
        assert 'shell' not in kwargs
        assert kwargs['timeout']==10
        assert not any(x in argv for x in ('login','install','auth','push','commit','reset'))


def test_doctor_does_not_export_process_output(tmp_path,no_real_commands):
    result=observer.observe('fixture.mission',tmp_path)
    assert 'fixture-read' not in json.dumps(result)


def test_invalid_repository_is_not_executed(tmp_path,no_real_commands):
    with pytest.raises(ValueError,match='REPOSITORY_INVALID'):
        observer.observe('fixture.mission',tmp_path,repository='owner/repo; cat secret')
    assert not any(a[0]=='gh' for a,_ in no_real_commands)


def test_endpoint_not_selected_by_request_text(tmp_path,no_real_commands):
    with pytest.raises(ValueError,match='SERVICE_NOT_REGISTERED'):
        observer.observe('fixture.mission',tmp_path,services=['https://untrusted.invalid'])


def test_discovery_alone_does_not_prove_callability(tmp_path,no_real_commands,monkeypatch):
    class Probe:
        def __init__(self,name):pass
        def observe(self):return {},[{'name':'search_openai_docs'}]
        def call(self,*args):return {'isError':True}
    monkeypatch.setattr(observer,'ReadOnlyMcpProbe',Probe)
    rows={r['tool']:r for r in observer.observe('fixture.mission',tmp_path,services=['openai-docs'])['items']}
    assert rows['docs.search']['state']=='UNKNOWN'


@pytest.mark.parametrize('status,state',[(401,'AUTH_REQUIRED'),(403,'DENIED'),(503,'UNKNOWN')])
def test_remote_auth_and_denials_are_not_retried(tmp_path,no_real_commands,monkeypatch,status,state):
    calls=[]
    class Probe:
        def __init__(self,name):calls.append(name)
        def observe(self):raise urllib.error.HTTPError('https://fixture.invalid',status,'fixture',{},None)
    monkeypatch.setattr(observer,'ReadOnlyMcpProbe',Probe)
    rows={r['tool']:r for r in observer.observe('fixture.mission',tmp_path,services=['openai-docs'])['items']}
    assert rows['docs.search']['state']==state and calls==['openai-docs']


def test_pool_wrapper_edit_preserves_existing_dispatch_body():
    original=b'#!/bin/bash\nCMD="$1";shift\ncase "$CMD" in\n  run) ORIGINAL_RUN ;;\n  status) ORIGINAL_STATUS ;;\nesac\n'
    new=install.wrapper_content(original,Path('/source release/commit'))
    assert new.count(install.BEGIN.encode())==1
    assert b'ORIGINAL_RUN' in new and b'ORIGINAL_STATUS' in new
    assert install.wrapper_content(new,Path('/source release/commit'))==new
    newer=install.wrapper_content(new,Path('/other release/commit'))
    assert newer.count(install.BEGIN.encode())==1 and b'/other release/commit' in newer
    assert b'/source release/commit' not in newer


def test_wrapper_unknown_shape_refuses_without_effect():
    with pytest.raises(ValueError,match='WRAPPER_SHAPE'):
        install.wrapper_content(b'#!/bin/sh\nunknown dispatch',Path('/release'))


def test_wrapper_cas_preserves_colliding_edit(tmp_path):
    wrapper=tmp_path/'pool';original=b'#!/bin/bash\ncase "$CMD" in\n*) exit 2;;\nesac\n';wrapper.write_bytes(original)
    wrapper.write_bytes(original+b'# another writer\n')
    with pytest.raises(ValueError,match='PREIMAGE_CHANGED'):
        install.activate(wrapper,Path('/release'),install.sha(original))
    assert wrapper.read_bytes().endswith(b'# another writer\n')
    assert not list(tmp_path.glob('*.pre-worker*'))


def test_wrapper_activation_is_backed_up_and_idempotent(tmp_path):
    wrapper=tmp_path/'pool';original=b'#!/bin/bash\ncase "$CMD" in\n*) exit 2;;\nesac\n';wrapper.write_bytes(original);wrapper.chmod(0o755)
    result=install.activate(wrapper,Path('/release'),install.sha(original))
    assert result['state']=='PROMPT_HOOK_INSTALLED'
    assert Path(result['backup']).read_bytes()==original
    actual=wrapper.read_bytes()
    result2=install.activate(wrapper,Path('/release'),install.sha(actual))
    assert result2['state']=='ALREADY_CURRENT'
    assert wrapper.read_bytes()==actual


def test_wrapper_symlink_cannot_be_activated(tmp_path):
    target=tmp_path/'target';target.write_text('untouched')
    wrapper=tmp_path/'pool';wrapper.symlink_to(target)
    with pytest.raises(ValueError,match='WRAPPER_NOT_REGULAR'):
        install.activate(wrapper,Path('/release'),install.sha(b'untouched'))
    assert target.read_text()=='untouched'
