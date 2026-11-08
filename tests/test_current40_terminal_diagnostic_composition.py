"""Pure source-only current40 successor; never import or inspect live owners."""
from __future__ import annotations
import hashlib
import inspect
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from ops.native_fabric.provider_plans import compose
from ops.native_fabric.quota_continuity.rollout import native_generation
from test_current116_maintenance_guard_composition import current_source

PROFILE = 'current116-terminal-diagnostics'
DIRECTORY = 'terminal_diagnostics/current40'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture(scope='module')
def source40(current_source, tmp_path_factory):
    output = tmp_path_factory.mktemp('source40-reference')/'code'
    result = compose.compose(current_source, output, profile_name='current116-maintenance-guard')
    profile = json.loads((compose.HERE/DIRECTORY/'profile.json').read_text())
    files = json.loads((output/'FILES.json').read_text())
    assert files == profile['base_files'] and len(files)==116
    for name, wanted in files.items():
        assert sha((output/name).read_bytes())==wanted
    # A public-code comparison descriptor, not an installed selection receipt.
    (output/'RELEASE.json').write_text(json.dumps({
        'digest':profile['base_selection']['generation'],'files':files,
        'source_only_reference':True}))
    assert result['publication_performed'] is result['selection_performed'] is False
    return output


@pytest.fixture
def base(source40, tmp_path):
    output=tmp_path/'base';shutil.copytree(source40,output);return output


def test_actual_source40_to116_successor_changes_only_reviewed_worker(base,tmp_path):
    target=tmp_path/'output';result=compose.compose(base,target,profile_name=PROFILE)
    profile=json.loads((compose.HERE/DIRECTORY/'profile.json').read_text())
    component=json.loads((compose.HERE/'terminal_diagnostics/component.json').read_text())
    before,after=profile['base_files'],profile['files']
    assert len(before)==len(after)==116
    assert {k for k in before if before[k]!=after[k]}=={component['member']}
    assert before[component['member']]==component['before'] and after[component['member']]==component['after']
    assert profile['patches']=={component['member']:{'before':component['before'],'after':component['after'],
        'patch':'terminal_diagnostics/'+component['patch'],'patch_sha256':component['patch_sha256']}}
    assert profile['source_map']=={}
    for name,wanted in after.items():
        assert sha((target/name).read_bytes())==wanted
        if name!=component['member']:
            assert (target/name).read_bytes()==(base/name).read_bytes()
    # Incumbent publisher's pure closure validator accepts the exact same ingress.
    assert native_generation.manifest_files(after)==after
    assert native_generation._entrypoints_for(before)==native_generation._entrypoints_for(after)
    compile((target/component['member']).read_bytes(),'source-only-new-worker','exec')
    assert result['base_generation']==profile['base_selection']['generation']
    assert result['files']==116
    assert result['publication_performed'] is result['selection_performed'] is False
    for absent in ('CURRENT.json','RELEASE.json','ext/state','ext/active','ext/broker','ext/pools.yaml'):
        assert not (target/absent).exists() and not (target/absent).is_symlink()


def test_original_runtime_link_and_unknown_fixture_are_not_consumed_or_changed(base,tmp_path,monkeypatch):
    private=tmp_path/'inert-original-owner';private.mkdir()
    sentinel=private/'fixture-unknown.json';sentinel.write_bytes(b'{"state":"EFFECT_UNKNOWN","fixture":true}')
    (base/'ext/state').symlink_to(private,target_is_directory=True)
    old=sentinel.read_bytes();seen=[];real=compose.digest
    def code_only(path):
        assert not str(path).startswith(str(private))
        assert not str(path).startswith(str(base/'ext/state'))
        seen.append(str(path));return real(path)
    monkeypatch.setattr(compose,'digest',code_only)
    target=tmp_path/'isolated-output';compose.compose(base,target,profile_name=PROFILE)
    assert sentinel.read_bytes()==old and (base/'ext/state').is_symlink()
    assert not (target/'ext/state').exists() and not (target/'ext/state').is_symlink()
    assert not list(target.rglob('*.local-terminal-diagnostic.json'))
    assert not list(target.rglob('*.request.json'))
    assert seen


@pytest.mark.parametrize('mutation',['generation','foreign-manifest','extra-member','worker-drift','broker-drift','symlink-worker'])
def test_wrong_stale_or_mixed_parent_refuses_before_output(base,tmp_path,mutation):
    p=base/'RELEASE.json';row=json.loads(p.read_text())
    if mutation=='generation':row['digest']='0'*64
    elif mutation=='foreign-manifest':row['files'].pop('ext/pick.py')
    elif mutation=='extra-member':row['files']['ext/foreign.py']='0'*64
    else:
        member=base/('ext/lease_broker.py' if mutation=='broker-drift' else 'ext/native_plan_worker.py')
        if mutation=='symlink-worker':
            real=tmp_path/'owned-copy.py';member.rename(real);member.symlink_to(real)
        else:member.write_bytes(member.read_bytes()+b'\n# changed\n')
    p.write_text(json.dumps(row));target=tmp_path/'refused-output'
    with pytest.raises(ValueError):compose.compose(base,target,profile_name=PROFILE)
    assert not target.exists()


def test_changed_reviewed_patch_refuses_before_output(base,tmp_path,monkeypatch):
    source=tmp_path/'component-source'
    shutil.copytree(compose.HERE/'terminal_diagnostics',source/'terminal_diagnostics')
    patch=source/'terminal_diagnostics/native_plan_worker.py.forward.patch'
    patch.write_bytes(patch.read_bytes()+b'\n')
    monkeypatch.setattr(compose,'HERE',source);target=tmp_path/'refused-output'
    with pytest.raises(ValueError,match='source patch changed'):
        compose.compose(base,target,profile_name=PROFILE)
    assert not target.exists()


@pytest.mark.parametrize('name',['terminal_diagnostics','../terminal_diagnostics','/tmp/profile.json'])
def test_only_closed_named_profile_is_accepted(base,tmp_path,name):
    output=tmp_path/'not-created'
    with pytest.raises(ValueError,match='unknown native source profile'):
        compose.compose(base,output,profile_name=name)
    assert not output.exists()


def test_occupied_destination_and_existing_default_preserved(base,tmp_path):
    target=tmp_path/'occupied';target.mkdir();marker=target/'existing';marker.write_text('unchanged')
    with pytest.raises(ValueError,match='output must be new'):
        compose.compose(base,target,profile_name=PROFILE)
    assert marker.read_text()=='unchanged'
    assert inspect.signature(compose.compose).parameters['profile_name'].default=='provider-plans'


def test_cli_emits_only_source_and_preserves_existing_builder_contract(base,tmp_path):
    output=tmp_path/'cli-output'
    result=subprocess.run([sys.executable,str(Path(compose.__file__)),
        '--profile',PROFILE,'--base',str(base),'--output',str(output)],
        capture_output=True,text=True,check=True)
    row=json.loads(result.stdout)
    assert row['state']=='SOURCE_COMPOSED' and row['files']==116
    assert row['publication_performed'] is row['selection_performed'] is False
    expected=json.loads((compose.HERE/DIRECTORY/'profile.json').read_text())['files']
    assert json.loads((output/'FILES.json').read_text())==expected
    assert not (output/'CURRENT.json').exists()


def test_entire_composer_inverse_is_exact_protected_preimage():
    raw=Path(compose.__file__).read_text()
    successor_branch='    elif profile_name == "terminal116-protected-memory":\n        profile_root = HERE / "memory118" / "after_terminal_diagnostics"\n'
    successor_choice=', "terminal116-protected-memory"'
    assert raw.count(successor_branch)==raw.count(successor_choice)==1
    raw=raw.replace(successor_branch,'').replace(successor_choice,'')
    successor_branch='    elif profile_name == "terminal116-protected-memory-support-status":\n        profile_root = HERE / "memory118_support_status" / "after_terminal_diagnostics"\n'
    successor_choice=', "terminal116-protected-memory-support-status"'
    assert raw.count(successor_branch)==raw.count(successor_choice)==1
    raw=raw.replace(successor_branch,'').replace(successor_choice,'')
    branch='    elif profile_name == "current116-terminal-diagnostics":\n        profile_root = HERE / "terminal_diagnostics" / "current40"\n'
    choice=', "current116-terminal-diagnostics"'
    assert raw.count(branch)==raw.count(choice)==1
    prior=raw.replace(branch,'').replace(choice,'')
    provenance=json.loads((compose.HERE/DIRECTORY/'provenance.json').read_text())
    assert sha(prior.encode())=='4f735a61726c2c7a1f0c1e31c1ce65f7bcac1540a791914f0abb6fc99c3c3ef2'
