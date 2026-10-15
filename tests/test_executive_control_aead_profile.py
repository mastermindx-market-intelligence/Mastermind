"""Source-only sealed-profile contracts; host custody fixtures are explicitly simulated."""
from pathlib import Path
import copy
import hashlib
import io
import json
import os
import subprocess
import sys
import zipfile
from types import SimpleNamespace

import pytest
from ops.executive_os import control_aead_contract as c, control_aead_profile as p

ROOT=Path(__file__).parents[1]
LOCK=(ROOT/p.LOCK_RELATIVE).read_bytes()

def test_minimal_lock_exact_versions_and_rejects_unreviewed_inputs():
    result=c.parse_lock(LOCK)
    assert {k:v['version'] for k,v in result.items()}==c.VERSIONS
    for changed in (LOCK+b'httpx==1.0\n --hash=sha256:'+b'a'*64,LOCK.replace(b'50.0.1',b'50.0.2'),LOCK+b'--index-url https://example.test\n',LOCK+LOCK,b'cryptography==50.0.1\n'):
        with pytest.raises(c.AeadContractError):c.parse_lock(changed)

@pytest.mark.parametrize('path',['../x','/x','cffi/../os.py','cffi//x.py','cffi/./x.py','cffi\\x.py','os.py','sitecustomize.py','cffi/x.pth','pycparser/__pycache__/x.pyc','cryptography/usercustomize.py','cffi/x\n.py','../cryptography/a.py'])
def test_no_paths_or_startup_hooks_escape_profile(path):assert not c.allowed_profile_path(path)

def test_canonical_manifest_rejects_duplicates_unknown_fields_and_bool():
    files=[{'path':'cryptography/a.py','bytes':3,'mode':0o444,'sha256':'a'*64}]
    data=c.manifest_bytes('b'*64,files)
    assert c.parse_manifest(data,'b'*64)['files']==files
    for changed in (data.replace(b'"bytes":3',b'"bytes":true'),data.replace(b'"bytes":3',b'"bytes":3,"bytes":3'),data.replace(b'"schema":',b'"extra":1,"schema":'),data.replace(b'"files":',b'"files" :'),data[:-1]):
        with pytest.raises(c.AeadContractError):c.parse_manifest(changed,'b'*64)
    with pytest.raises(c.AeadContractError):c.parse_manifest(data,'c'*64)
    with pytest.raises(c.AeadContractError):c.manifest_bytes('b'*64,files+files)


def fake_bundle():
    # Small public wheel fixtures test structure. Actual approved wheel proof is
    # separately run under the intended PSF interpreter and retained as evidence.
    lock=[];wheels={}
    for name,version in c.VERSIONS.items():
        tag='cp312-cp312-macosx_11_0_arm64' if name=='cffi' else 'cp311-abi3-macosx_10_9_universal2' if name=='cryptography' else 'py3-none-any'
        wheel=io.BytesIO()
        with zipfile.ZipFile(wheel,'w') as z:
            z.writestr(f'{name}-{version}.dist-info/METADATA',f'Name: {name}\nVersion: {version}\n')
            z.writestr(f'{name}/__init__.py','')
        payload=wheel.getvalue();wheels[f'{name}-{version}-{tag}.whl']=payload
        lock.append(f'{name}=={version} \\\n --hash=sha256:{p.digest(payload)}\n')
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:
        for name,data in wheels.items():z.writestr(name,data)
    return b.getvalue(),''.join(lock).encode()

def test_bundle_authority_is_original_locked_wheels_not_caller_manifest():
    bundle,lock=fake_bundle();wheels,packages,manifest=p.bundle_files(bundle,lock)
    assert len(wheels)==3 and len(packages)==6
    assert c.parse_manifest(manifest,p.digest(lock))['lock_sha256']==p.digest(lock)
    changed=io.BytesIO()
    with zipfile.ZipFile(changed,'w') as z:
        for name,data in wheels.items():z.writestr(name,data+b'changed' if name.startswith('cffi') else data)
    with pytest.raises(p.AeadProfileError):p.bundle_files(changed.getvalue(),lock)
    with pytest.raises(p.AeadProfileError):p.bundle_files(bundle,LOCK)
    with pytest.raises(c.AeadContractError):p.bundle_files(bundle,lock.replace(b'2.1.1',b'2.1.2'))


def simulated_custody(tmp_path,monkeypatch):
    actual_uid=os.geteuid()
    # Metadata simulation only; no real service admission or installed custody.
    monkeypatch.setattr(p,'SYSTEM_ROOT',tmp_path/'system')
    p.SYSTEM_ROOT.mkdir()
    monkeypatch.setattr(p,'sealed_directory',lambda path,**kwargs:None)
    real_data=p.secure_data
    monkeypatch.setattr(p,'secure_data',lambda path,uid=0,**kwargs:real_data(path,uid=actual_uid,**kwargs))
    monkeypatch.setattr(p.os,'geteuid',lambda:0)
    release=tmp_path/('a'*40);(release/'requirements').mkdir(parents=True)
    bundle,lock=fake_bundle();(release/p.LOCK_RELATIVE).write_bytes(lock)
    artifact=tmp_path/'bundle.zip';artifact.write_bytes(bundle);artifact.chmod(0o600)
    return release,artifact,actual_uid


def test_real_profile_materialization_verifies_restart_and_refuses_tampering(tmp_path,monkeypatch):
    release,artifact,uid=simulated_custody(tmp_path,monkeypatch)
    observation=p.materialize_bundle(artifact,release,operator_uid=uid)
    assert p.materialize_bundle(artifact,release,operator_uid=uid)==observation
    root=Path(observation['root']);target=root/'packages/cffi/__init__.py'
    target.chmod(0o644);target.write_text('tampered');target.chmod(0o444)
    with pytest.raises(p.AeadProfileError):p.verify_profile(release)
    with pytest.raises(p.AeadProfileError):p.materialize_bundle(artifact,release,operator_uid=uid)


def test_existing_profile_occupant_never_replaced_or_cleaned(tmp_path,monkeypatch):
    release,artifact,uid=simulated_custody(tmp_path,monkeypatch)
    lock=(release/p.LOCK_RELATIVE).read_bytes();root=p.profile_root(lock);root.mkdir(parents=True)
    marker=root/'incumbent';marker.write_text('preserve')
    with pytest.raises(Exception):p.materialize_bundle(artifact,release,operator_uid=uid)
    assert marker.read_text()=='preserve'


def test_disabled_profile_performs_no_dependency_io(monkeypatch):
    monkeypatch.setattr(p,'verify_profile',lambda *a:pytest.fail('disabled dependency IO'))
    assert p.activate_if_enrolled({},'/missing') is None
    assert p.observe_if_enrolled({'reply_events':{'armed':False}},'/missing') is None


def test_existing_control_projection_joins_optional_profile_and_preserves_disabled_read_path(monkeypatch):
    import control_plane.executive_installed_peer as peer
    raw={'proof_base_sha':'a'*40,'control_uid':450,'python_runtime_provenance_digest':'b'*64}
    monkeypatch.setattr(peer,'_read_trusted_bytes',lambda *a,**k:(json.dumps(raw).encode(),None))
    monkeypatch.setattr(peer,'_observe_ancestors',lambda *a:())
    monkeypatch.setattr(peer,'_object_identity',lambda *a:())
    monkeypatch.setattr(peer,'_deadline_fence',lambda *a:None)
    monkeypatch.setattr(p,'verify_profile',lambda *a:pytest.fail('disabled profile IO'))
    assert peer._verify_control_projection(None).control_aead is None
    raw['reply_events']={'armed':True}
    monkeypatch.setattr(peer,'_observe_control_aead',lambda *a:peer._AeadObservation((('manifest_sha256','a'*64),),()))
    before=peer._verify_control_projection(None)
    assert before.control_aead.details==(('manifest_sha256','a'*64),)
    monkeypatch.setattr(peer,'_observe_control_aead',lambda *a:peer._AeadObservation((('manifest_sha256','c'*64),),()))
    assert peer._verify_control_projection(None)!=before
    def failed(*a):raise p.AeadProfileError('fixture tamper')
    monkeypatch.setattr(peer,'_observe_control_aead',failed)
    with pytest.raises(Exception,match='SERVICE_CONTROL_AEAD_CLOSURE_REFUSED'):peer._verify_control_projection(None)


def test_key_guard_observes_acl_on_open_descriptor_and_parent(tmp_path,monkeypatch):
    from integrations.session_bridge.reply_event_host_composition import _provisioned_cipher
    from ops.executive_os import executive_mcp_entry as entry
    from control_plane import fs_security
    key=tmp_path/'synthetic-key';key.write_bytes(b'k'*32);key.chmod(0o600)
    monkeypatch.setattr(entry,'require_sealed_path',lambda *a,**k:None)
    seen=[]
    def acl(path,*,expected_identity,descriptor=None):
        seen.append((Path(path),descriptor))
        return Path(path)==key
    monkeypatch.setattr(fs_security,'has_macos_acl',acl)
    with pytest.raises(ValueError,match='key ACL'):_provisioned_cipher(key,'fixture',control_uid=os.geteuid())
    assert seen[-1][0]==key and type(seen[-1][1]) is int
    monkeypatch.setattr(fs_security,'has_macos_acl',lambda path,**kwargs:Path(path)==tmp_path)
    with pytest.raises(ValueError,match='parent ACL'):_provisioned_cipher(key,'fixture',control_uid=os.geteuid())


def test_installer_and_wrapper_keep_baseline_flags_and_existing_owner_order():
    script=(ROOT/'ops/executive_os/install.sh').read_text()
    assert script.index('control AEAD bundle preflight refused')<script.index('# Cross the mutation boundary')
    assert script.index('control_aead_profile.py" materialize')>script.index('installed release contains a filesystem ACL')
    assert '"$PYTHON_BINARY" -I -S -B' in script and '--control-aead-bundle' in script
    wrapper=(ROOT/'scripts/executive_os_phase1c_control_wrapper.py').read_text()
    assert 'activate_if_enrolled(load_control_config(args.config),release)' in wrapper.replace(' ', '')
    assert 'network-runtimes' not in wrapper


def test_active_loader_refuses_cached_foreign_dependency_before_path_selection(tmp_path,monkeypatch):
    source=tmp_path/'foreign-crypto.py';source.write_text('')
    package=tmp_path/'qualified';package.mkdir()
    monkeypatch.setattr(p,'verify_profile',lambda *a:{'packages':str(package)})
    monkeypatch.setattr(p.os,'geteuid',lambda:450)
    monkeypatch.setitem(sys.modules,'cryptography',SimpleNamespace(__file__=str(source)))
    before=list(sys.path)
    with pytest.raises(p.AeadProfileError):p.activate_if_enrolled({'proof_base_sha':'a'*40,'control_uid':450,'reply_events':{'armed':True}},'/'+('a'*40))
    assert sys.path==before


def test_secure_descriptor_refuses_mode_hardlink_symlink_and_acl(tmp_path,monkeypatch):
    file=tmp_path/'public-fixture';file.write_bytes(b'public-source');file.chmod(0o600)
    assert p.secure_data(file,uid=os.geteuid(),mode=0o600)==b'public-source'
    file.chmod(0o640)
    with pytest.raises(p.AeadProfileError):p.secure_data(file,uid=os.geteuid(),mode=0o600)
    file.chmod(0o600);alias=tmp_path/'alias';os.link(file,alias)
    with pytest.raises(p.AeadProfileError):p.secure_data(file,uid=os.geteuid(),mode=0o600)
    alias.unlink();alias.symlink_to(file)
    with pytest.raises(p.AeadProfileError):p.secure_data(alias,uid=os.geteuid(),mode=0o600)
    seen=[]
    def acl(path,*,expected_identity,descriptor):
        seen.append(descriptor);return True
    monkeypatch.setattr(p,'has_macos_acl',acl)
    with pytest.raises(p.AeadProfileError):p.secure_data(file,uid=os.geteuid(),mode=0o600)
    assert len(seen)==1 and type(seen[0]) is int
