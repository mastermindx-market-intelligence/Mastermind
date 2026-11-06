"""Real schema joins over inert rendered source. No installed service or secret."""
import dataclasses
import hashlib
import json
import os
import plistlib
from pathlib import Path

import pytest

from ops.executive_os import attended_worker_definition as render
from control_plane.executive_fabric_composition import _bindings
from control_plane.executive_fabric_bridge_broker import BridgeConfig
from control_plane.fabric_attended_canary import probe_config
from control_plane.worker_execution_contract import BinaryAttestation
from scripts import executive_os_phase1c_worker as worker


@pytest.fixture
def inputs(tmp_path):
    binary = BinaryAttestation(path='/fixture/claude', real_path='/fixture/claude', version='2.1.0',
        sha256='d'*64, team_identifier=None, size=11, device=1, inode=2, mode=0o555,
        uid=0, gid=0, mtime_ns=1)
    receipt = render._json({'schema_version': 'mastermind.attended_claude_binary/v1',
                           'binary': dataclasses.asdict(binary)})
    return dict(primary_config={'worker_id':'codex-01','worker_user':'_mastermind_worker',
        'worker_uid':451,'worker_gid':451,'provider_home':str(tmp_path/'runtime/workers/codex-01/provider-home'),
        'control_uid':450}, worker_id='finite-minimax', worker_user='finite_worker', worker_group='finite_group',
        worker_uid=os.getuid(), worker_gid=os.getgid(), control_gid=450, runtime_root=str(tmp_path/'runtime'),
        definition_dir=str(tmp_path/'config/finite'), socket_path=str(tmp_path/'sockets/finite.sock'),
        binary=binary, binary_receipt_path=str(tmp_path/'config/claude-receipt.json'),
        binary_receipt_sha256=hashlib.sha256(receipt).hexdigest(), realm_generation=1,
        release_root=str(tmp_path/'releases'/('a'*40)), release_commit='a'*40, release_tree='b'*40,
        release_manifest_sha256='c'*64, python_binary='/usr/bin/python3',
        host_ref='fixture-host', model_class=render.get_binding(render.canary.BINDING).model_classes[0], execution_profile_digest='e'*64,
        routing_root_id='original-root', routing_parent_run_id='original-parent', max_turns=2)


def test_rendered_definition_reaches_actual_policy_and_probe_readers(inputs, tmp_path):
    artifacts=render.build_finite_worker_artifacts(**inputs)
    path=tmp_path/'reader.json';path.write_bytes(artifacts['worker.json']);path.chmod(0o600)
    value=worker._load_config(path,require_root_owner=False)
    for field in ('workspace_root','run_root','provider_home'):
        Path(value[field]).mkdir(parents=True,mode=0o700)
    policy=dataclasses.replace(worker._broker_policy(value),require_assignment_seal=True)
    assert policy.require_assignment_seal and not policy.allowed_supplementary_gids
    assert policy.worker_id == inputs['worker_id']
    physical,=_bindings(artifacts['bindings.json'])
    assert physical.worker_source_config_digest==hashlib.sha256(artifacts['worker.json']).hexdigest()
    assert physical.binary_sha256 == inputs['binary'].sha256
    bridge=BridgeConfig.from_document(json.loads(artifacts['bridge.json']))
    assert bridge.bridge_uid==physical.worker_uid==policy.worker_uid
    assert bridge.socket_path==Path(physical.socket_path)
    cfg=probe_config(value,release_sha=inputs['release_commit'],probe_sha256='a'*64,control_gid=450)
    assert cfg.expected_worker_uid==policy.worker_uid


def test_launchd_definition_is_separate_disarmed_and_uses_exact_fixed_entry(inputs):
    before=json.dumps(inputs['primary_config'],sort_keys=True)
    artifacts=render.build_finite_worker_artifacts(**inputs)
    plist=plistlib.loads(next(v for k,v in artifacts.items() if k.endswith('.plist')))
    socket=plist['Sockets']['AttendedFabric']
    assert socket['SockPathOwner']==0 and socket['SockPathGroup']==450 and socket['SockPathMode']==0o660
    assert plist['UserName']==inputs['worker_user'] and plist['GroupName']==inputs['worker_group']
    assert plist['InitGroups'] is False and plist['Disabled'] is True and plist['KeepAlive'] is False
    assert plist['ProgramArguments']==['/usr/bin/python3','-I','-S','-B',inputs['definition_dir']+'/owner_entry.py']
    assert json.dumps(inputs['primary_config'],sort_keys=True)==before
    namespace={'__name__':'inert_render_test'}
    exec(compile(artifacts['owner_entry.py'],'rendered','exec'),namespace)
    assert namespace['RELEASE']==inputs['release_root']
    assert namespace['MANIFEST']==inputs['release_manifest_sha256']
    assert namespace['ARGUMENTS']['bindings_sha256']==hashlib.sha256(artifacts['bindings.json']).hexdigest()
    assert namespace['ARGUMENTS']['routing_root_id']=='original-root'
    assert 'credential_loader' not in namespace['ARGUMENTS']


@pytest.mark.parametrize('key,value', [
    ('worker_uid',451),('worker_uid',450),('worker_gid',451),('worker_gid',450),
    ('worker_id','codex-01'),('worker_user','_mastermind_worker'),
    ('worker_uid',True),('realm_generation',0),('max_turns',0),
    ('binary_receipt_sha256','0'*64),('routing_root_id','bad/root'),
    ('runtime_root','/safe/../other'),('definition_dir','relative'),
    ('model_class','unregistered-class'),
])
def test_invalid_or_primary_colliding_target_refuses(inputs,key,value):
    with pytest.raises(Exception):render.build_finite_worker_artifacts(**{**inputs,key:value})


def test_artifact_cannot_be_grafted_into_sealed_release(inputs):
    for field in ('runtime_root','definition_dir','binary_receipt_path','socket_path'):
        with pytest.raises(render.AttendedDefinitionError,match='sealed release'):
            render.build_finite_worker_artifacts(**{**inputs,field:inputs['release_root']+'/new'})
    with pytest.raises(render.AttendedDefinitionError,match='sealed release'):
        render.build_finite_worker_artifacts(**{**inputs,'runtime_root':str(Path(inputs['release_root']).parent)})


def test_binary_identity_change_invalidates_prepared_receipt(inputs):
    changed=dataclasses.replace(inputs['binary'],inode=inputs['binary'].inode+1)
    with pytest.raises(render.AttendedDefinitionError,match='exact observed'):
        render.build_finite_worker_artifacts(**{**inputs,'binary':changed})


def test_attester_never_serializes_claim_without_observing(monkeypatch):
    from control_plane import claude_subscription_worker as c, codex_provider_realm as r
    from contextlib import contextmanager
    calls=[]
    @contextmanager
    def protected(path):
        calls.append('protected');yield
    def refused(*a,**k):
        calls.append('attest');raise RuntimeError('explicit fake binary refusal')
    monkeypatch.setattr(r,'_native_open',protected)
    monkeypatch.setattr(c,'attest_claude_binary',refused)
    with pytest.raises(RuntimeError,match='fake binary'):
        render.attest_binary_document('/fixture/claude',allowed_versions=['2.1.0'])
    assert calls==['protected','attest']


@pytest.mark.parametrize('target',['control_plane/fs_security.py','ops/__init__.py',
    'ops/executive_os/release_manifest.py','control_plane/__init__.py'])
def test_generated_main_refuses_changed_bootstrap_code_before_execution(tmp_path, monkeypatch, target):
    """Root metadata is a fixture; actual pinned-byte check runs before import."""
    import stat
    from types import SimpleNamespace
    root=tmp_path/'release';root.mkdir()
    marker=tmp_path/'must-not-exist'
    source_root=Path(render.__file__).parents[2]
    paths=['control_plane/fs_security.py','ops/__init__.py',
        'ops/executive_os/release_manifest.py','control_plane/__init__.py']
    rows=[]
    for name in paths:
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
        data=(source_root/name).read_bytes() if (source_root/name).exists() else b''
        path.write_bytes(data)
        rows.append(dict(path=name,type='file',mode=0o644,sha256=hashlib.sha256(data).hexdigest()))
    for path in root.rglob('*'):
        if path.is_dir():rows.append(dict(path=path.relative_to(root).as_posix(),type='directory',mode=0o755))
    manifest={'commit_sha':'a'*40,'tree_sha':'b'*40,'entries':rows}
    data=render._json(manifest);(root/'.executive-release-manifest.json').write_bytes(data)
    code=render._entry(root,'a'*40,'b'*40,hashlib.sha256(data).hexdigest(),{})
    entry=tmp_path/'entry.py';entry.write_bytes(code)
    namespace={'__name__':'fixture_entry','__file__':str(entry)}
    exec(compile(code,str(entry),'exec'),namespace)
    # Simulate a changed module with a harmless execution marker. The pinned
    # manifest remains unchanged, so NO release code is eligible to import.
    (root/target).write_text('from pathlib import Path\nPath('+repr(str(marker))+').touch()\n')
    monkeypatch.setattr(namespace['sys'],'argv',[str(entry)])
    namespace['protected']=lambda *a,**k:None
    real_lstat=Path.lstat
    def root_stat(path):
        real=real_lstat(path)
        return SimpleNamespace(st_uid=0,st_gid=0,st_mode=(stat.S_IFDIR|0o755) if stat.S_ISDIR(real.st_mode) else (stat.S_IFREG|0o644),
            st_dev=real.st_dev,st_ino=real.st_ino)
    monkeypatch.setattr(Path,'lstat',root_stat)
    # ACLs are a separate host qualification. Fixture Linux makes the actual
    # existing ACL observer a no-op without replacing its pinned source bytes.
    monkeypatch.setattr(namespace['sys'],'platform','linux')
    with pytest.raises(RuntimeError,match='changed'):
        namespace['main']()
    assert not marker.exists()
