"""Real path mutations; Control ownership and Git observations explicitly inert."""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import pytest
from integrations.session_bridge.bound_launch_capture import fabric_attended_backend as backend
from control_plane import broker_assignment_seal, codex_worker

@pytest.mark.parametrize('damage', ['none','home_inode','home_mode','home_symlink','tmp_inode','workspace_inode','head','dirty','binary'])
def test_pre_spawn_rechecks_current_original_resources(tmp_path, monkeypatch, damage):
    paths={name:tmp_path/name for name in ('workspace','run','home','tmp')}
    for path in paths.values(): path.mkdir(mode=0o700)
    identities={name:codex_worker._path_identity(path) for name,path in paths.items()}
    policy=SimpleNamespace(require_assignment_seal=True)
    evidence={'finite_home_tmp':{'home_path':str(paths['home']),'tmp_path':str(paths['tmp']),
        'evidence_sha256':hashlib.sha256(backend._bytes({k:identities[k] for k in ('home','tmp')})).hexdigest()}}
    inputs=SimpleNamespace(preparation={'policy':policy},workspace_identity=identities['workspace'],
        provider_home_identity=identities['home'],binary_pin=object())
    spec={'workspace_path':str(paths['workspace']),'run_dir':str(paths['run']),
        'expected_base_sha':'a'*40,'isolation_manifest':{}}
    # Test the fresh-reader integration; actual Control UID/isolation rules have
    # their own canonical tests and are not granted by this fixture.
    monkeypatch.setattr(broker_assignment_seal,'observe_roots',lambda values,*a:
        {k:codex_worker._path_identity(Path(v)) for k,v in values.items()})
    def git(*a,**k):
        assert k['require_clean'] is True
        if damage=='dirty': raise ValueError('dirty workspace')
        return SimpleNamespace(head=('b' if damage=='head' else 'a')*40)
    monkeypatch.setattr(codex_worker,'_git_snapshot',git)
    def binary(pin):
        assert pin is inputs.binary_pin
        if damage=='binary': raise ValueError('changed binary')
    monkeypatch.setattr(codex_worker,'_assert_binary_unchanged',binary)
    if damage.endswith('_inode'):
        key=damage[:-6]; paths[key].rename(tmp_path/(key+'-retained')); paths[key].mkdir(mode=0o700)
    elif damage=='home_mode': paths['home'].chmod(0o750)
    elif damage=='home_symlink':
        paths['home'].rename(tmp_path/'retained'); paths['home'].symlink_to(tmp_path/'retained')
    if damage=='none': backend._require_current_assignment(inputs,spec,evidence)
    else:
        with pytest.raises((ValueError,OSError)): backend._require_current_assignment(inputs,spec,evidence)
