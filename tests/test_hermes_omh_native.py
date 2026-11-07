"""Native bridge uses only the current Hermes registry and a fixed local CLI."""
from contextlib import nullcontext
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace,ModuleType

import pytest

ROOT=Path(__file__).resolve().parents[1]


def load(tmp_path):
    source=ROOT/'integrations/hermes_omh/plugin/__init__.py'
    assert source.is_file(),'Native OMH plugin not implemented'
    dest=tmp_path/'plugin';dest.mkdir(exist_ok=True)
    shutil.copyfile(source,dest/'__init__.py')
    spec=importlib.util.spec_from_file_location('omh_native_test_'+tmp_path.name,dest/'__init__.py')
    mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
    descriptor=dict(schema=mod.RUNTIME_SCHEMA,release_commit='a'*40,source_root=str(ROOT),
                    python_executable=sys.executable,profile_home=str(tmp_path/'profile'),
                    omh_home=str(tmp_path/'omh'),
                    source_files={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in mod.SOURCE_FILES})
    (dest/'_runtime.json').write_text(json.dumps(descriptor));(dest/'_runtime.json').chmod(0o600)
    return mod,descriptor,dest


def framework(monkeypatch,profile):
    entries={}; disposed=[]; calls=[]
    registry=SimpleNamespace(get_entry=lambda name,scope=None:entries.get((scope,name)),
                             snapshot_registration=lambda name,scope=None:entries.get((scope,name)))
    registry_mod=ModuleType('tools.registry');registry_mod.registry=registry
    lifecycle=ModuleType('registration_lifecycle');lifecycle.replacement_coordinator=SimpleNamespace(transaction=nullcontext)
    constants=ModuleType('hermes_constants');constants.get_hermes_home=lambda:Path(profile)
    monkeypatch.setitem(sys.modules,'tools.registry',registry_mod)
    monkeypatch.setitem(sys.modules,'registration_lifecycle',lifecycle)
    monkeypatch.setitem(sys.modules,'hermes_constants',constants)
    def register(**kw):
        calls.append(kw);entry=SimpleNamespace(**kw);key=(profile,kw['name']);entries[key]=entry
        def dispose():
            disposed.append(key)
            if entries.get(key) is entry:entries.pop(key)
        return SimpleNamespace(dispose=dispose)
    commands={}
    def register_command(name,handler,**kw):
        entry=dict(handler=handler,**kw);commands[name]=entry
        def dispose():
            if commands.get(name) is entry:commands.pop(name)
        return SimpleNamespace(dispose=dispose)
    ctx=SimpleNamespace(_manager=SimpleNamespace(scope_key=profile,_plugin_commands=commands),profile_name='custom',register_tool=register,register_command=register_command)
    return ctx,entries,calls,disposed,constants


def test_native_dispatch_uses_fixed_argv_no_credentials_and_truthful_result(tmp_path,monkeypatch):
    m,d,where=load(tmp_path);ctx,entries,calls,disposed,_=framework(monkeypatch,d['profile_home'])
    observed=[]
    def run(argv,**kw):
        observed.append((argv,kw))
        return SimpleNamespace(returncode=0,stdout=b'{"schema":"mastermind.hermes_omh.bridge/v1","state":"LOCAL_BRIDGE_READY","admitted":false,"dispatched":false}',stderr=b'')
    monkeypatch.setattr(m.subprocess,'run',run)
    monkeypatch.setenv('ZAI_API_KEY','SECRET_SENTINEL')
    registration=m.register(ctx)
    assert len(calls)==1 and calls[0]['name']=='mmx_omh'
    out=json.loads(calls[0]['handler']({'action':'status'},session_id='native-session'))
    assert out['state']=='LOCAL_BRIDGE_READY' and out['admitted'] is False
    argv,kw=observed[0]
    assert argv[0]==sys.executable and '-I' in argv and '-B' in argv
    assert not kw.get('shell') and kw['timeout']==20
    assert 'ZAI_API_KEY' not in kw['env'] and 'SECRET_SENTINEL' not in str(kw)
    assert json.loads(kw['input'])=={'action':'status'}
    assert registration is not None


@pytest.mark.parametrize('kind',['missing-session','wrong-profile','source-drift','descriptor-drift','extra-field','stale-registration'])
def test_native_refuses_before_process(tmp_path,monkeypatch,kind):
    m,d,where=load(tmp_path);ctx,entries,calls,disposed,constants=framework(monkeypatch,d['profile_home'])
    m.register(ctx);h=calls[0]['handler'];session='native-session';args={'action':'status'}
    if kind=='missing-session':session=''
    if kind=='wrong-profile':constants.get_hermes_home=lambda:tmp_path/'foreign'
    if kind=='source-drift':monkeypatch.setattr(m,'verify_sources',lambda binding:False)
    if kind=='descriptor-drift':(where/'_runtime.json').write_text('{}')
    if kind=='extra-field':args['root_id']='ATTACKER'
    if kind=='stale-registration':entries[(d['profile_home'],'mmx_omh')]=SimpleNamespace(handler=lambda *a:None)
    monkeypatch.setattr(m.subprocess,'run',lambda *a,**k:pytest.fail('Refused request spawned process'))
    out=json.loads(h(args,session_id=session))
    assert out['state']=='REFUSED' and out['dispatched'] is False


def test_registry_collision_is_not_overridden(tmp_path,monkeypatch):
    m,d,_=load(tmp_path);ctx,entries,calls,disposed,_=framework(monkeypatch,d['profile_home'])
    previous=object();entries[(d['profile_home'],'mmx_omh')]=previous
    with pytest.raises(m.NativeBridgeError):m.register(ctx)
    assert not calls and entries[(d['profile_home'],'mmx_omh')] is previous


@pytest.mark.parametrize('kind',['timeout','bad-json','bad-status','stderr','oversized','false-admission'])
def test_process_failures_are_value_free_and_never_retried(tmp_path,monkeypatch,kind):
    m,d,_=load(tmp_path);ctx,entries,calls,disposed,_=framework(monkeypatch,d['profile_home'])
    count=[]
    def run(*a,**k):
        count.append(1)
        if kind=='timeout':raise subprocess.TimeoutExpired(a[0],20,output=b'SECRET_SENTINEL')
        raw=b'{"state":"LOCAL_BRIDGE_READY","admitted":false,"dispatched":false}'
        if kind=='bad-json':raw=b'SECRET_SENTINEL'
        if kind=='bad-status':raw=b'{"state":"EXECUTING","admitted":false,"dispatched":false}'
        if kind=='oversized':raw=b'x'*131074
        if kind=='false-admission':raw=b'{"state":"LOCAL_BRIDGE_READY","admitted":true,"dispatched":false}'
        return SimpleNamespace(returncode=0,stdout=raw,stderr=b'SECRET_SENTINEL' if kind=='stderr' else b'')
    monkeypatch.setattr(m.subprocess,'run',run);m.register(ctx)
    out=calls[0]['handler']({'action':'status'},session_id='native-session')
    assert json.loads(out)['state']=='REFUSED' and len(count)==1 and 'SECRET_SENTINEL' not in out


def test_readback_failure_disposes_only_native_handle(tmp_path,monkeypatch):
    m,d,_=load(tmp_path);ctx,entries,calls,disposed,_=framework(monkeypatch,d['profile_home'])
    real=ctx.register_tool
    def register(**kw):
        handle=real(**kw);entries[(d['profile_home'],'mmx_omh')].toolset='wrong';return handle
    ctx.register_tool=register
    with pytest.raises(m.NativeBridgeError):m.register(ctx)
    assert len(disposed)==1 and not entries


def test_wrong_install_profile_refuses_registration(tmp_path,monkeypatch):
    m,d,_=load(tmp_path);ctx,entries,calls,disposed,_=framework(monkeypatch,str(tmp_path/'wrong'))
    with pytest.raises(m.NativeBridgeError):m.register(ctx)
    assert not calls


def test_native_rechecks_registration_after_local_return(tmp_path,monkeypatch):
    m,d,_=load(tmp_path);ctx,entries,calls,disposed,_=framework(monkeypatch,d['profile_home'])
    def run(*a,**k):
        entries.clear()
        return SimpleNamespace(returncode=0,stdout=b'{"state":"LOCAL_BRIDGE_READY","admitted":false,"dispatched":false}',stderr=b'')
    monkeypatch.setattr(m.subprocess,'run',run);m.register(ctx)
    out=json.loads(calls[0]['handler']({'action':'status'},session_id='native-session'))
    assert out['state']=='REFUSED' and out['reason']=='NATIVE_REGISTRATION_STALE'


def test_native_registration_exception_preserves_uncertainty(tmp_path,monkeypatch):
    m,d,_=load(tmp_path);ctx,entries,calls,disposed,_=framework(monkeypatch,d['profile_home'])
    original=ctx.register_tool
    def write_then_raise(**kwargs):
        original(**kwargs);raise RuntimeError('PRIVATE_SENTINEL')
    ctx.register_tool=write_then_raise
    with pytest.raises(m.NativeBridgeError) as exc:m.register(ctx)
    assert str(exc.value)=='NATIVE_REGISTRATION_EFFECT_UNKNOWN'
    assert len(calls)==1 and not disposed


def test_native_live_command_uses_original_tool_handler(tmp_path,monkeypatch):
    m,d,_=load(tmp_path);ctx,entries,calls,disposed,_=framework(monkeypatch,d['profile_home'])
    requests=[]
    def run(*a,**k):
        request=json.loads(k['input']);requests.append(request)
        state='LOCAL_BRIDGE_READY' if request['action']=='status' else 'RECOMMENDED_NOT_ADMITTED'
        return SimpleNamespace(returncode=0,stdout=json.dumps(dict(state=state,admitted=False,dispatched=False)).encode(),stderr=b'')
    monkeypatch.setattr(m.subprocess,'run',run);m.register(ctx)
    command=ctx._manager._plugin_commands.get('mmx-omh')
    assert command is not None,'Live slash command not registered'
    out=json.loads(command['handler']('quick Investigate the failing test',session_id='native-session'))
    assert out['state']=='RECOMMENDED_NOT_ADMITTED'
    assert requests==[dict(action='recommend',category='quick',message='Investigate the failing test')]
    assert json.loads(command['handler']('status',session_id='native-session'))['state']=='LOCAL_BRIDGE_READY'


def test_native_command_collision_preserves_original_and_registers_nothing(tmp_path,monkeypatch):
    m,d,_=load(tmp_path);ctx,entries,calls,disposed,_=framework(monkeypatch,d['profile_home'])
    previous=dict(handler=lambda *_:None);ctx._manager._plugin_commands['mmx-omh']=previous
    with pytest.raises(m.NativeBridgeError):m.register(ctx)
    assert not calls and ctx._manager._plugin_commands['mmx-omh'] is previous


def test_native_command_refuses_missing_context_and_stale_command(tmp_path,monkeypatch):
    m,d,_=load(tmp_path);ctx,entries,calls,disposed,_=framework(monkeypatch,d['profile_home'])
    monkeypatch.setattr(m.subprocess,'run',lambda *a,**k:pytest.fail('Invalid command spawned process'))
    m.register(ctx);command=ctx._manager._plugin_commands['mmx-omh']['handler']
    assert json.loads(command('status'))['state']=='REFUSED'
    ctx._manager._plugin_commands.clear()
    assert json.loads(command('status',session_id='native-session'))['state']=='REFUSED'
