"""Public-code prospective source composition; no installed/current/runtime read."""
from __future__ import annotations
import ast
import hashlib
import inspect
import json
from pathlib import Path
import subprocess
import sys

import pytest
from ops.native_fabric.provider_plans import compose
from test_current40_terminal_diagnostic_composition import source40
from test_current116_maintenance_guard_composition import current_source

GENERATION='5b5713e6870b688b1cc2f9978df9d7539159b25b291f5019853a293f905a5b3a'
WORKER='ext/native_plan_worker.py'
NEW_WORKER='2df8947c446e143d46bbf979e30dd11965080922839e2e37c3d8c0289ef2af7b'
CASES=[('terminal116-protected-memory','memory118',118),
       ('terminal116-protected-memory-support-status','memory118_support_status',119)]
ROOT=Path(__file__).resolve().parents[1]


def sha(raw):return hashlib.sha256(raw).hexdigest()


@pytest.fixture(scope='module')
def terminal_source(source40,tmp_path_factory):
    target=tmp_path_factory.mktemp('public-terminal-predecessor')/'code'
    result=compose.compose(source40,target,profile_name='current116-terminal-diagnostics')
    files=json.loads((target/'FILES.json').read_text())
    expected=json.loads((compose.HERE/'terminal_diagnostics/current40/profile.json').read_text())
    assert files==expected['files'] and len(files)==116 and files[WORKER]==NEW_WORKER
    assert result['publication_performed'] is result['selection_performed'] is False
    for relative,wanted in files.items():assert sha((target/relative).read_bytes())==wanted
    # Explicit inert descriptor ONLY; Root's proposed generation is not a receipt.
    (target/'RELEASE.json').write_text(json.dumps({'digest':GENERATION,'files':files,
        'fixture_premise':'UNSELECTED public source comparison, not current/admission'}))
    return target


@pytest.mark.parametrize('profile,folder,count',CASES)
def test_old_profiles_refuse_terminal_successor(terminal_source,tmp_path,profile,folder,count):
    output=tmp_path/'refused'
    old='current116-protected-memory'+('-support-status' if count==119 else '')
    with pytest.raises(ValueError,match='selected native base changed'):
        compose.compose(terminal_source,output,profile_name=old)
    assert not output.exists()


@pytest.mark.parametrize('profile,folder,count',CASES)
def test_successor_preserves_terminal_worker_and_every_other_accepted_target(terminal_source,tmp_path,profile,folder,count):
    output=tmp_path/'joined';result=compose.compose(terminal_source,output,profile_name=profile)
    old=json.loads((compose.HERE/folder/'profile.json').read_text())
    new=json.loads((compose.HERE/folder/'after_terminal_diagnostics/profile.json').read_text())
    base=json.loads((terminal_source/'FILES.json').read_text())
    assert new['base_files']==base and new['base_selection']['generation']==GENERATION
    assert new['patches']==old['patches'] and new['source_map']==old['source_map']
    assert set(new['files'])==set(old['files']) and len(new['files'])==count
    assert {k for k in old['files'] if old['files'][k]!=new['files'][k]}=={WORKER}
    assert new['files'][WORKER]==base[WORKER]==NEW_WORKER
    assert new['expected_predecessor']['actual_publication_observed'] is False
    assert new['expected_predecessor']['actual_selection_observed'] is False
    for relative,wanted in new['files'].items():
        assert sha((output/relative).read_bytes())==wanted
        if relative in base and old['files'][relative]==old['base_files'][relative]:
            assert (output/relative).read_bytes()==(terminal_source/relative).read_bytes()
    assert not (output/'RELEASE.json').exists() and not (output/'CURRENT.json').exists()
    assert not (output/'ext/broker').exists() and not (output/'ext/state').exists()
    assert result['files']==count and result['publication_performed'] is result['selection_performed'] is False


@pytest.mark.parametrize('profile,folder,count',CASES)
@pytest.mark.parametrize('defect',['old40','old40_relabelled','worker_drift','foreign_member'])
def test_stale_foreign_or_relabelled_parent_refuses_before_output(terminal_source,source40,tmp_path,profile,folder,count,defect):
    import shutil
    parent=tmp_path/'base';shutil.copytree(source40 if defect.startswith('old40') else terminal_source,parent)
    record=parent/'RELEASE.json';d=json.loads(record.read_text())
    if defect=='old40_relabelled':d['digest']=GENERATION
    elif defect=='worker_drift':(parent/WORKER).write_bytes((parent/WORKER).read_bytes()+b'\n# drift\n')
    elif defect=='foreign_member':d['files']['ext/foreign.py']='0'*64
    record.write_text(json.dumps(d));output=tmp_path/'not-created'
    with pytest.raises(ValueError):compose.compose(parent,output,profile_name=profile)
    assert not output.exists()


def test_composer_extension_recovers_exact_accepted_S5_source_and_default():
    raw=Path(compose.__file__).read_text()
    repair_branch='    elif profile_name == "terminal119-fleet-launch-repair":\n        profile_root = HERE / "fleet_launch_repair"\n'
    repair_choice=', "terminal119-fleet-launch-repair"'
    assert raw.count(repair_branch)==raw.count(repair_choice)==1
    raw=raw.replace(repair_branch,'').replace(repair_choice,'')
    for profile,folder,count in CASES:
        branch=f'    elif profile_name == "{profile}":\n        profile_root = HERE / "{folder}" / "after_terminal_diagnostics"\n'
        choice=f', "{profile}"'
        assert raw.count(branch)==raw.count(choice)==1
        raw=raw.replace(branch,'').replace(choice,'')
    assert sha(raw.encode())=='27cfb2c9e51d24927dbd1d8a64acacbf59ca8c0575a99ae193705bfbf2cb26ce'
    assert inspect.signature(compose.compose).parameters['profile_name'].default=='provider-plans'
    result=subprocess.run([sys.executable,str(Path(compose.__file__)),'--help'],capture_output=True,text=True)
    assert result.returncode==0
    for name in ['provider-plans','current116-maintenance-guard','current116-remote-placement',
            'current116-protected-memory','current116-protected-memory-support-status',
            'current116-terminal-diagnostics',*(x[0] for x in CASES)]:assert name in result.stdout


@pytest.mark.parametrize('profile,folder,count',CASES)
def test_real_fixed_CLI_emits_only_exact_source(terminal_source,tmp_path,profile,folder,count):
    output=tmp_path/'cli-source'
    result=subprocess.run([sys.executable,str(Path(compose.__file__)),'--base',str(terminal_source),
        '--output',str(output),'--profile',profile],check=True,capture_output=True,text=True)
    reply=json.loads(result.stdout);expected=json.loads((compose.HERE/folder/'after_terminal_diagnostics/profile.json').read_text())
    assert reply['files']==count and reply['publication_performed'] is reply['selection_performed'] is False
    assert json.loads((output/'FILES.json').read_text())==expected['files']
    assert sha((output/WORKER).read_bytes())==NEW_WORKER
