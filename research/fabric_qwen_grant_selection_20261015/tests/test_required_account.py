"""Synthetic-only picker and launcher tests: no live account/provider access."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

SOURCE = Path(os.environ.get('QWEN_GRANT_SOURCE', Path(__file__).resolve().parents[1] / 'candidate'))
EXT = Path(__file__).resolve().parent / 'support'

@pytest.fixture
def picker(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('grant_fixture', SOURCE / 'bailian_keys.py')
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    monkeypatch.setattr(m, 'SLOTS_ROOT', str(tmp_path/'slots'))
    monkeypatch.setattr(m, 'LOCK_PATH', str(tmp_path/'slots/.lock'))
    monkeypatch.setattr(m, 'key_names', lambda: ['Kris', 'Ryan'])
    monkeypatch.setattr(m, 'current_per_key_cap', lambda: 3)
    monkeypatch.setattr(m, 'cooldown_info', lambda name: None)
    monkeypatch.setattr(m, 'prune_stale', lambda name: 0)
    monkeypatch.delenv('BAILIAN_PICK_SKIP', raising=False)
    monkeypatch.delenv('BAILIAN_PREFER', raising=False)
    monkeypatch.delenv('POOL_ACCOUNT', raising=False)
    return m

def test_required_account_wins_over_load_and_inherited_preference(picker, tmp_path, monkeypatch):
    monkeypatch.setenv('BAILIAN_PREFER', 'Ryan')
    monkeypatch.setenv('POOL_ACCOUNT', 'Ryan')
    touched=[]
    monkeypatch.setattr(picker, 'prune_stale', lambda name: touched.append(name) or 2)
    assert picker.pick(pid=123, prefer='Ryan', require='Kris') == 'Kris'
    assert touched == ['Kris']
    assert (tmp_path/'slots/Kris/123').is_file()
    assert not (tmp_path/'slots/Ryan').exists()

@pytest.mark.parametrize('reason', ['not_configured','excluded','cooldown','at_capacity'])
def test_unavailable_required_account_never_touches_alternative(picker,tmp_path,monkeypatch,capsys,reason):
    if reason == 'not_configured': monkeypatch.setattr(picker,'key_names',lambda:['Ryan'])
    if reason == 'excluded': monkeypatch.setenv('BAILIAN_PICK_SKIP','Kris')
    if reason == 'cooldown': monkeypatch.setattr(picker,'cooldown_info',lambda name:(9999999999,'access_denied'))
    touched=[]
    monkeypatch.setattr(picker,'prune_stale',lambda name:touched.append(name) or 3)
    with pytest.raises(SystemExit) as caught: picker.pick(pid=123,require='Kris')
    assert caught.value.code == 3
    assert f'account=Kris reason={reason}' in capsys.readouterr().err
    assert 'Ryan' not in touched
    assert not (tmp_path/'slots/Ryan').exists()
    assert not (tmp_path/'slots/Kris/123').exists()

def test_required_account_keeps_existing_429_soft_cap(picker,monkeypatch):
    monkeypatch.setattr(picker,'cooldown_info',lambda name:(9999999999,'http_429'))
    monkeypatch.setattr(picker,'_effective_cap_for_key',lambda name:2)
    monkeypatch.setattr(picker,'prune_stale',lambda name:1)
    assert picker.pick(pid=123,require='Kris') == 'Kris'

def test_unleased_preference_retains_rotation(picker,monkeypatch):
    monkeypatch.setattr(picker,'prune_stale',lambda name:3 if name=='Kris' else 0)
    assert picker.pick(pid=123,prefer='Kris') == 'Ryan'

@pytest.mark.parametrize('bad', ['', 'Kris Ryan', '../Kris', 'Kris;false', '\nKris'])
def test_invalid_required_name_refuses_before_account_read(picker,monkeypatch,bad):
    monkeypatch.setattr(picker,'key_names',lambda:pytest.fail('account read before validation'))
    with pytest.raises(SystemExit) as caught: picker.pick(require=bad)
    assert caught.value.code==2

def test_cli_passes_required_name(picker,monkeypatch,capsys):
    captured={}
    def fake(**kw): captured.update(kw); return 'Kris'
    monkeypatch.setattr(picker,'pick',fake)
    assert picker.cmd_pick(['--require','Kris'])==0
    assert captured=={'prefer':None,'require':'Kris'}
    assert capsys.readouterr().out=='Kris\n'

@pytest.mark.parametrize('args', [['--require'],['--require','Kris','--require','Ryan'],['--require','Kris','--prefer','Ryan'],['--require','Kris','Ryan']])
def test_ambiguous_cli_never_selects(picker,monkeypatch,args):
    monkeypatch.setattr(picker,'pick',lambda **kw:pytest.fail('ambiguous request selected'))
    with pytest.raises(SystemExit) as caught: picker.cmd_pick(args)
    assert caught.value.code==2

@pytest.fixture
def launcher(monkeypatch):
    spec=importlib.util.spec_from_file_location('outer_fixture',EXT/'outer_fixture.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    m.EXT = EXT
    # Preserve installed public dependency, select candidate source only.
    original=m.shutil.copy2
    def copy(src,dst,*args,**kw):
        if Path(src).name=='qwen_exec.sh': src=SOURCE/'qwen_exec.sh'
        return original(src,dst,*args,**kw)
    monkeypatch.setattr(m.shutil,'copy2',copy)
    return m

def test_outer_launcher_requests_exact_account_once(launcher,tmp_path):
    r,events=launcher.run_fixture(tmp_path,account='Kris',selected='Kris')
    assert r.returncode==0,r.stderr
    assert [e for e in events if e[0]=='pick']==[['pick','--require','Kris']]
    assert ['env','Kris'] in events

def test_outer_mismatch_guard_survives_misbehaving_picker(launcher,tmp_path):
    r,events=launcher.run_fixture(tmp_path,account='Kris',selected='Ryan')
    assert r.returncode==75
    assert not any(e[0] in ['env','codex'] for e in events)
    assert 'OUTER_LEASE_ACCOUNT_MISMATCH' in r.stderr

def test_unleased_launcher_keeps_soft_preference(launcher,tmp_path):
    r,events=launcher.run_fixture(tmp_path,account='Kris',selected='Ryan',leased='0')
    assert r.returncode==0,r.stderr
    assert ['pick','--prefer','Kris'] in events
    assert ['env','Ryan'] in events

@pytest.mark.parametrize('condition', ['available','not_configured','excluded','cooldown','at_capacity'])
def test_real_picker_join_in_actual_launcher(launcher,tmp_path,monkeypatch,condition):
    pick_code = '''if cmd=='pick':
 import importlib.util
 spec=importlib.util.spec_from_file_location('real_picker',PICKER_SOURCE)
 m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 m.SLOTS_ROOT=str(log.parent/'real-slots');m.LOCK_PATH=str(log.parent/'real-slots/.lock')
 condition=os.environ['SELECTED_ACCOUNT']
 m.key_names=lambda:['Ryan'] if condition=='not_configured' else ['Kris','Ryan']
 m.current_per_key_cap=lambda:3
 m.cooldown_info=lambda name:(9999999999,'access_denied') if name=='Kris' and condition=='cooldown' else None
 m.prune_stale=lambda name:3 if name=='Kris' and condition=='at_capacity' else 0
 os.environ['BAILIAN_PICK_SKIP']='Kris' if condition=='excluded' else ''
 m.cmd_pick(sys.argv[2:])
'''.replace('PICKER_SOURCE', repr(str(SOURCE/'bailian_keys.py'))).rstrip()
    monkeypatch.setattr(launcher,'KEY_STUB',launcher.KEY_STUB.replace("if cmd=='pick':print(os.environ['SELECTED_ACCOUNT'])",pick_code))
    r,events=launcher.run_fixture(tmp_path,account='Kris',selected=condition)
    assert len([e for e in events if e[0]=='pick'])==1
    assert not (tmp_path/'real-slots/Ryan').exists()
    if condition=='available':
        assert r.returncode==0,r.stderr
        assert ['env','Kris'] in events
        assert any(e[:2]==['codex','Kris'] for e in events)
    else:
        assert r.returncode==75,r.stderr
        assert f'REQUIRED_ACCOUNT_UNAVAILABLE account=Kris reason={condition}' in r.stderr
        assert not any(e[0] in ['env','codex','release'] for e in events)
