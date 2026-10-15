"""Finite publisher is inert until root owner, release and Capacity attest."""
from pathlib import Path
from types import SimpleNamespace
import os
import pytest

from tests.test_finite_service_host import qualified_host
from ops.executive_os import finite_definition_publication as pub


def test_existing_canonical_renderer_is_the_only_accepted_five_file_shape(qualified_host):
    _host, _prior, artifacts, _calls = qualified_host
    hashes = pub.verify_candidate(artifacts)
    assert set(hashes) == pub.FILES
    for name, digest in hashes.items():
        assert digest == pub.sha256(artifacts[name])
    assert 'capacity_capability_id' in artifacts['worker.json'].decode()


@pytest.mark.parametrize('mutation', [
    lambda a: {k:v for k,v in a.items() if k!='owner_entry.py'},
    lambda a: dict(a, **{'evil_extra':b"x"}),
    lambda a: dict(a, **{'worker.json':a['worker.json']+b'\x00'}),
    lambda a: dict(a, **{'worker.json':b''}),
    lambda a: dict(a, **{'worker.json':b'x'*32769}),
    lambda a: dict(a, **{'com.mastermind.executive.fabric.minimax-finite-01.plist':b'not plist'}),
])
def test_source_and_bundle_tamper_refused_before_any_write(qualified_host, mutation):
    _,_,files,_=qualified_host
    with pytest.raises(pub.FinitePublicationRefused):
        pub.verify_candidate(mutation(files))


def test_missing_capacity_id_fails_closed(qualified_host):
    _,_,files,_=qualified_host
    import json
    worker = json.loads(files['worker.json'])
    del worker['capacity_capability_id']
    from ops.executive_os.attended_worker_definition import _json
    damaged=dict(files, **{'worker.json':_json(worker)})
    with pytest.raises(pub.FinitePublicationRefused):
        pub.verify_candidate(damaged)


def test_single_exclusive_publication_preserves_bytes_and_refuses_replay(qualified_host, tmp_path):
    _,_,files,_=qualified_host
    home=tmp_path/'control-config'
    home.mkdir()
    destination=home/'fabric-minimax-finite-01'
    stamp=pub._write_exclusive(destination,files,uid=os.getuid(),gid=os.getgid())
    assert stamp==pub.verify_candidate(files)
    assert set(p.name for p in destination.iterdir())==pub.FILES
    assert (destination.stat().st_mode&0o777)==0o755
    assert all((destination/name).read_bytes()==raw for name,raw in files.items())
    assert all(((destination/name).stat().st_mode & 0o777) == 0o444 for name in files)
    with pytest.raises(pub.FinitePublicationRefused,match='already exists'):
        pub._write_exclusive(destination,files,uid=os.getuid(),gid=os.getgid())
    assert set(p.name for p in destination.iterdir())==pub.FILES


def test_partial_error_preserves_original_directory_without_replay(monkeypatch,qualified_host,tmp_path):
    _,_,files,_=qualified_host
    destination=tmp_path/'fabric-minimax-finite-01'
    original=pub.os.fchown
    count=[0]
    def deny_second(fd,uid,gid):
        count[0]+=1
        if count[0]==2: raise OSError('test-only simulated incomplete write')
        return original(fd,uid,gid)
    monkeypatch.setattr(pub.os,'fchown',deny_second)
    with pytest.raises(pub.FinitePublicationEffectUnknown):
        pub._write_exclusive(destination,files,uid=os.getuid(),gid=os.getgid())
    assert destination.is_dir()
    assert (destination.stat().st_mode&0o777)==0o700
    with pytest.raises(pub.FinitePublicationRefused):
        pub._write_exclusive(destination,files,uid=os.getuid(),gid=os.getgid())


def test_capacity_owner_refusal_blocks_root_publication_before_effect(monkeypatch,qualified_host,tmp_path):
    _,_,files,_=qualified_host
    calls=[]
    monkeypatch.setattr(pub.os, "geteuid", lambda: 0)
    def refuse(host,cap):
        calls.append((host,cap))
        return False
    with pytest.raises(pub.FinitePublicationRefused,match='Capacity owner refused'):
        pub.publish_disarmed_definition('a'*40,'a'*64,files,verified_capacity_binding=refuse, trusted_render_again=lambda *a: files)
    assert calls==[('fixture-host','fixture-capacity')]
    assert not (tmp_path/'fabric-minimax-finite-01').exists()


def test_no_owner_capacity_callback_blocks_before_root_preflight(monkeypatch,qualified_host):
    monkeypatch.setattr(pub.os, "geteuid", lambda: 0)
    _,_,files,_=qualified_host
    with pytest.raises(pub.FinitePublicationRefused,match='Capacity owner and renderer are required'):
        pub.publish_disarmed_definition('a'*40,'a'*64,files,verified_capacity_binding=None, trusted_render_again=lambda *a: files)

def test_non_root_cannot_invoke_capacity_owner_or_write(monkeypatch,qualified_host):
    _,_,files,_=qualified_host
    monkeypatch.setattr(pub.os, "geteuid", lambda: 501)
    invoked=[]
    with pytest.raises(pub.FinitePublicationRefused,match="exact root"):
        pub.publish_disarmed_definition('a'*40,'a'*64,files,
            verified_capacity_binding=lambda *args: invoked.append(args) or True,
            trusted_render_again=lambda *args: files)
    assert invoked==[]

def test_root_owner_publishes_only_after_same_locked_config_and_render(monkeypatch, qualified_host, tmp_path):
    _, prior, files, _ = qualified_host
    from ops.executive_os import finite_definition_publication as pub
    home=tmp_path/'control-config'
    home.mkdir()
    monkeypatch.setattr(pub.owner,'CONFIG_ROOT',home)
    monkeypatch.setattr(pub,'DESTINATION',home/'fabric-minimax-finite-01')
    monkeypatch.setattr(pub.os,'geteuid',lambda:0)
    prior.control_sha256='e'*64
    actions=[]
    class FakeHost:
        def require_exact_install(self,sha):actions.append('install');return sha
        def require_transaction_absent(self):actions.append('marker-absent')
        def _config_root_safe(self):actions.append('config-owned')
        def require_services_already_stopped(self):actions.append('stopped')
        def require_service_uids_quiescent(self):actions.append('uids-idle')
        def load_unarmed_configs(self,sha):actions.append('disarmed');return prior
        def require_runtime_quiescent(self,prior):actions.append('runtime-idle')
    monkeypatch.setattr(pub.owner,'ProductionCeoSubmitHost',FakeHost)
    monkeypatch.setattr(pub,'_write_exclusive',lambda path, payload, uid,gid:
        actions.append('publish') or pub.verify_candidate(payload))
    def capacity(host,cap):
        actions.append('capacity-checked')
        assert (host,cap)==('fixture-host','fixture-capacity')
        return True
    def renderer(host,cap):
        actions.append('render-rechecked')
        return files.copy()
    x=pub.publish_disarmed_definition('a'*40,'e'*64,files,
        verified_capacity_binding=capacity,trusted_render_again=renderer)
    assert x['state']=='STAGED_DISARMED_DEFINITION'
    assert x['admitted_worker'] is False and x['service_started'] is False
    assert actions.count('capacity-checked')==2
    assert actions.index('stopped')<actions.index('publish')
    assert actions.index('disarmed')<actions.index('publish')
    assert actions.index('render-rechecked')<actions.index('publish')


def test_runtime_source_drift_refuses_before_any_effect(monkeypatch,qualified_host,tmp_path):
    _,prior,files,_=qualified_host
    home=tmp_path/'control-config'
    home.mkdir()
    monkeypatch.setattr(pub.owner,'CONFIG_ROOT',home)
    monkeypatch.setattr(pub,'DESTINATION',home/'fabric-minimax-finite-01')
    monkeypatch.setattr(pub.os,'geteuid',lambda:0)
    calls=[]
    class FakeHost:
        def require_exact_install(self,sha):return sha
        def require_transaction_absent(self):pass
        def _config_root_safe(self):pass
        def require_services_already_stopped(self):pass
        def require_service_uids_quiescent(self):pass
        def load_unarmed_configs(self,sha):return prior
        def require_runtime_quiescent(self,prior):pass
    monkeypatch.setattr(pub.owner,'ProductionCeoSubmitHost',FakeHost)
    def forbidden(*args,**kwargs):
        raise AssertionError('untrusted bytes must never publish')
    monkeypatch.setattr(pub,'_write_exclusive',forbidden)
    with pytest.raises(pub.FinitePublicationRefused,match='source-rendered'):
        pub.publish_disarmed_definition('a'*40,prior.control_sha256,files,
            verified_capacity_binding=lambda *a:True,
            trusted_render_again=lambda *a:dict(files, **{'owner_entry.py':b'separate entry bytes'}))
    assert not pub.DESTINATION.exists()

def test_native_acl_drift_fails_closed_and_preserves_partial_state(monkeypatch,qualified_host,tmp_path):
    _,_,files,_=qualified_host
    from control_plane import fs_security
    directory=tmp_path/'fabric-minimax-finite-01'
    monkeypatch.setattr(fs_security, 'has_macos_acl', lambda *a,**kw: True)
    with pytest.raises(pub.FinitePublicationEffectUnknown):
        pub._write_exclusive(directory,files,uid=os.getuid(),gid=os.getgid())
    assert directory.exists() and (directory.stat().st_mode & 0o777)==0o700
    with pytest.raises(pub.FinitePublicationRefused):
        pub._write_exclusive(directory,files,uid=os.getuid(),gid=os.getgid())


def test_destination_symlink_is_never_adopted(monkeypatch,qualified_host,tmp_path):
    _,_,files,_=qualified_host
    outside=tmp_path/'outside';outside.mkdir()
    destination=tmp_path/'fabric-minimax-finite-01';destination.symlink_to(outside, target_is_directory=True)
    with pytest.raises(pub.FinitePublicationRefused,match='already exists'):
        pub._write_exclusive(destination,files,uid=os.getuid(),gid=os.getgid())
    assert list(outside.iterdir())==[]

def test_protected_mode_review_is_exact_source_only():
    from tests.executive_identity_review import reviewed_literal_spans
    source=Path(__file__).parents[1]/'ops/executive_os/finite_definition_publication.py'
    body=source.read_text()
    spans=reviewed_literal_spans('ops/executive_os/finite_definition_publication.py',body)
    assert len(spans)==3
    assert all(body.splitlines()[line-1][start:end]=='0o700' for line,start,end,_ in spans)
    assert reviewed_literal_spans('ops/executive_os/finite_definition_publication.py',
        body+'\n# changed source')==()
    assert reviewed_literal_spans('ops/executive_os/foreign.py',body)==()
