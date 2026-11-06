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


def test_private_stage_write_error_never_creates_partial_canonical(monkeypatch,qualified_host,tmp_path):
    _,_,files,_=qualified_host
    destination=tmp_path/'fabric-minimax-finite-01'
    original=pub.os.fchown
    count=[0]
    def deny_second(fd,uid,gid):
        count[0]+=1
        assert not destination.exists()
        if count[0]==2: raise OSError('test-only simulated incomplete write')
        return original(fd,uid,gid)
    monkeypatch.setattr(pub.os,'fchown',deny_second)
    with pytest.raises(pub.FinitePublicationRefused,match='without canonical'):
        pub._write_exclusive(destination,files,uid=os.getuid(),gid=os.getgid())
    assert not destination.exists()
    assert not list(tmp_path.glob('.fabric-minimax-finite-01.*.stage'))
    monkeypatch.setattr(pub.os,'fchown',original)
    assert pub._write_exclusive(destination,files,uid=os.getuid(),gid=os.getgid())==pub.verify_candidate(files)
    assert set(path.name for path in destination.iterdir())==pub.FILES


def test_capacity_owner_refusal_blocks_root_publication_before_effect(monkeypatch,qualified_host,tmp_path):
    _,prior,files,_=qualified_host
    home=tmp_path/'control-config';home.mkdir()
    monkeypatch.setattr(pub.owner,'CONFIG_ROOT',home)
    # These fake-host unit fixtures do not impersonate the root-owned
    # production CONFIG_ROOT. The separate guard tests exercise real trust.
    monkeypatch.setattr(pub,'_trusted_control_root',lambda fd: os.fstat(fd))
    monkeypatch.setattr(pub,'DESTINATION',home/'fabric-minimax-finite-01')
    monkeypatch.setattr(pub.os,'geteuid',lambda:0)
    class Owner:
        def require_exact_install(self,sha):return sha
        def require_transaction_absent(self):return None
        def _config_root_safe(self):return None
        def require_services_already_stopped(self):return None
        def require_service_uids_quiescent(self):return None
        def load_unarmed_configs(self,sha):return prior
        def require_runtime_quiescent(self,prior):return None
    monkeypatch.setattr(pub.owner,'ProductionCeoSubmitHost',Owner)
    calls=[]
    def refuse(join):
        calls.append(join.to_dict())
        return False
    with pytest.raises(pub.FinitePublicationRefused,match='Capacity/config binding differs'):
        pub.publish_disarmed_definition('a'*40,prior.control_sha256,files,
            verified_capacity_binding=refuse)
    assert len(calls)==1 and calls[0]['host_ref']=='host-'+'a'*64
    assert calls[0]['capacity_capability_id']=='fixture-capacity'
    assert len(calls[0]['worker_source_config_digest'])==64
    assert not pub.DESTINATION.exists()


def test_no_owner_capacity_callback_blocks_before_root_preflight(monkeypatch,qualified_host):
    monkeypatch.setattr(pub.os, "geteuid", lambda: 0)
    _,_,files,_=qualified_host
    with pytest.raises(pub.FinitePublicationRefused,match='Capacity owner is required'):
        pub.publish_disarmed_definition('a'*40,'a'*64,files,verified_capacity_binding=None)

def test_non_root_cannot_invoke_capacity_owner_or_write(monkeypatch,qualified_host):
    _,_,files,_=qualified_host
    monkeypatch.setattr(pub.os, "geteuid", lambda: 501)
    invoked=[]
    with pytest.raises(pub.FinitePublicationRefused,match="exact root"):
        pub.publish_disarmed_definition('a'*40,'a'*64,files,
            verified_capacity_binding=lambda *args: invoked.append(args) or True,
            )
    assert invoked==[]

def test_root_owner_publishes_only_after_same_locked_config_and_render(monkeypatch, qualified_host, tmp_path):
    _, prior, files, _ = qualified_host
    from ops.executive_os import finite_definition_publication as pub
    home=tmp_path/'control-config'
    home.mkdir()
    monkeypatch.setattr(pub.owner,'CONFIG_ROOT',home)
    # These fake-host unit fixtures do not impersonate the root-owned
    # production CONFIG_ROOT. The separate guard tests exercise real trust.
    monkeypatch.setattr(pub,'_trusted_control_root',lambda fd: os.fstat(fd))
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
    monkeypatch.setattr(pub,'_write_exclusive',lambda path, payload, uid,gid,parent_fd=None:
        actions.append('publish') or pub.verify_candidate(payload))
    def capacity(join):
        actions.append('capacity-checked')
        assert join.host_ref=='host-'+'a'*64 and join.capacity_capability_id=='fixture-capacity'
        assert len(join.worker_source_config_digest)==64
        return True
    def renderer(prior_value, release_sha, join):
        actions.append('render-rechecked')
        assert release_sha=='a'*40 and join.host_ref=='host-'+'a'*64
        assert prior_value is prior
        return files.copy()
    monkeypatch.setattr(pub, 'render_owner_definition', renderer)
    x=pub.publish_disarmed_definition('a'*40,'e'*64,files,
        verified_capacity_binding=capacity)
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
    # These fake-host unit fixtures do not impersonate the root-owned
    # production CONFIG_ROOT. The separate guard tests exercise real trust.
    monkeypatch.setattr(pub,'_trusted_control_root',lambda fd: os.fstat(fd))
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
    monkeypatch.setattr(pub,'render_owner_definition',
        lambda *a:dict(files, **{'owner_entry.py':b'separate entry bytes'}))
    with pytest.raises(pub.FinitePublicationRefused,match='source-rendered'):
        pub.publish_disarmed_definition('a'*40,prior.control_sha256,files,
            verified_capacity_binding=lambda *a:True)
    assert not pub.DESTINATION.exists()

def test_native_acl_drift_prevents_canonical_publication(monkeypatch,qualified_host,tmp_path):
    _,_,files,_=qualified_host
    from control_plane import fs_security
    directory=tmp_path/'fabric-minimax-finite-01'
    monkeypatch.setattr(fs_security, 'has_macos_acl', lambda *a,**kw: True)
    with pytest.raises(pub.FinitePublicationRefused,match='without canonical'):
        pub._write_exclusive(directory,files,uid=os.getuid(),gid=os.getgid())
    assert not directory.exists()
    assert not list(tmp_path.glob('.fabric-minimax-finite-01.*.stage'))


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
    assert len(spans)==30
    spellings=[body.splitlines()[line-1][start:end] for line,start,end,_ in spans]
    assert spellings.count('"_mastermind_minimax"')==4
    assert spellings.count('0o440')==1
    assert spellings.count('0o444')==2
    assert spellings.count('0o700')==7
    assert spellings.count('0o755')==4
    assert spellings.count('450')==1
    assert spellings.count('470')==10
    assert spellings.count('0o555')==1
    assert reviewed_literal_spans('ops/executive_os/finite_definition_publication.py',
        body+'\n# changed source')==()
    assert reviewed_literal_spans('ops/executive_os/foreign.py',body)==()

def test_capacity_identity_requires_canonical_host_reference(qualified_host):
    import json
    from ops.executive_os.attended_worker_definition import _json
    _,_,files,_=qualified_host
    original=json.loads(files['bindings.json'])
    for bad in ('m2studio','fixture-host','local-unbound','host-'+'b'*63):
        body=dict(original,bindings=[dict(original['bindings'][0], host_ref=bad)])
        with pytest.raises(pub.FinitePublicationRefused):
            pub.verify_candidate(dict(files, **{'bindings.json':_json(body)}))

def test_installed_source_entry_never_skips_original_stopped_service_gate(
        monkeypatch, qualified_host):
    from control_plane.executive_capacity_join import CapacityJoin, PROVIDER_CAPACITY_SCHEMA
    from control_plane.executive_fabric_composition import _bindings
    host, prior, files, _ = qualified_host
    physical, = _bindings(files["bindings.json"])
    join = CapacityJoin(physical.host_ref, 'fixture-capacity',
        PROVIDER_CAPACITY_SCHEMA, physical.worker_source_config_digest)
    calls=[]
    monkeypatch.setattr(pub.os, 'geteuid', lambda:0)
    class FakeOwner:
        def require_exact_install(self,sha):
            calls.append('release');return sha
        def require_transaction_absent(self):calls.append('marker')
        def require_services_already_stopped(self):
            calls.append('service-running');raise ValueError('Control still running')
        def require_service_uids_quiescent(self):raise AssertionError('not reached')
    monkeypatch.setattr(pub.owner, 'ProductionCeoSubmitHost', FakeOwner)
    monkeypatch.setattr(pub,'render_owner_definition',
        lambda *args: pytest.fail('render must not run during live service'))
    monkeypatch.setattr(pub,'publish_disarmed_definition',
        lambda *args,**kwargs: pytest.fail('publication never bypasses stopped service'))
    with pytest.raises(pub.FinitePublicationRefused,match='root/Capacity source preflight'):
        pub.publish_from_installed_sources('a'*40, 'e'*64, join,
            verified_capacity_binding=lambda j: True)
    assert calls==['release','marker','service-running']


def test_installed_source_entry_joins_original_capacity_and_same_publisher(
        monkeypatch, qualified_host):
    from control_plane.executive_capacity_join import CapacityJoin, PROVIDER_CAPACITY_SCHEMA
    from control_plane.executive_fabric_composition import _bindings
    _, prior, files, _ = qualified_host
    physical, = _bindings(files["bindings.json"])
    join = CapacityJoin(physical.host_ref, 'fixture-capacity',
        PROVIDER_CAPACITY_SCHEMA, physical.worker_source_config_digest)
    calls=[]
    monkeypatch.setattr(pub.os, 'geteuid', lambda:0)
    class FakeOwner:
        def require_exact_install(self,sha):calls.append('release');return sha
        def require_transaction_absent(self):calls.append('marker')
        def require_services_already_stopped(self):calls.append('stopped')
        def require_service_uids_quiescent(self):calls.append('uids')
        def load_unarmed_configs(self,sha):calls.append('configs');return prior
        def require_runtime_quiescent(self,x):calls.append('runtime')
    monkeypatch.setattr(pub.owner,'ProductionCeoSubmitHost',FakeOwner)
    def validate(j):
        calls.append('capacity')
        return j==join
    def render(p,sha,j):
        calls.append('renderer')
        assert (p,sha,j)==(prior,'a'*40,join)
        return files.copy()
    def publish(sha,control_sha,artifacts,*,verified_capacity_binding):
        calls.append('original-publisher')
        assert (sha,control_sha)==('a'*40,prior.control_sha256)
        assert artifacts==files and verified_capacity_binding is validate
        return {'effect':'INERT_TEST'}
    monkeypatch.setattr(pub,'render_owner_definition',render)
    monkeypatch.setattr(pub,'publish_disarmed_definition',publish)
    assert pub.publish_from_installed_sources('a'*40,prior.control_sha256,join,
        verified_capacity_binding=validate)=={'effect':'INERT_TEST'}
    assert calls==['release','marker','stopped','uids','configs','runtime',
        'capacity','renderer','original-publisher']

def test_post_write_control_drift_is_uncertain_effect_never_success(
        monkeypatch, qualified_host, tmp_path):
    from types import SimpleNamespace
    from control_plane.executive_capacity_join import CapacityJoin, PROVIDER_CAPACITY_SCHEMA
    from control_plane.executive_fabric_composition import _bindings
    _, prior, files, _ = qualified_host
    physical, = _bindings(files["bindings.json"])
    home=tmp_path/'control-config';home.mkdir()
    monkeypatch.setattr(pub.owner,'CONFIG_ROOT',home)
    # These fake-host unit fixtures do not impersonate the root-owned
    # production CONFIG_ROOT. The separate guard tests exercise real trust.
    monkeypatch.setattr(pub,'_trusted_control_root',lambda fd: os.fstat(fd))
    monkeypatch.setattr(pub,'DESTINATION',home/'fabric-minimax-finite-01')
    monkeypatch.setattr(pub.os,'geteuid',lambda:0)
    reads=[0];writes=[]
    class Host:
        def require_exact_install(self,sha):return sha
        def require_transaction_absent(self):return None
        def _config_root_safe(self):return None
        def require_services_already_stopped(self):return None
        def require_service_uids_quiescent(self):return None
        def load_unarmed_configs(self,sha):
            reads[0]+=1
            if reads[0]>1:
                return SimpleNamespace(**dict(vars(prior), worker_sha256='f'*64))
            return prior
        def require_runtime_quiescent(self,prior):return None
    monkeypatch.setattr(pub.owner,'ProductionCeoSubmitHost',Host)
    monkeypatch.setattr(pub,'render_owner_definition',lambda *a:files.copy())
    monkeypatch.setattr(pub,'_write_exclusive',
        lambda *args,**kwargs:writes.append(True) or pub.verify_candidate(files))
    with pytest.raises(pub.FinitePublicationEffectUnknown,match='original config'):
        pub.publish_disarmed_definition('a'*40,prior.control_sha256,files,
            verified_capacity_binding=lambda join:True)
    assert writes==[True] and reads==[2]

def test_rename_ack_lost_preserves_original_canonical_and_unknown_effect(
        monkeypatch, qualified_host,tmp_path):
    _,_,files,_=qualified_host
    destination=tmp_path/'fabric-minimax-finite-01'
    from ops.executive_os import capacity_host_artifacts as owner_rename
    def issued_then_lost(src_fd,source,dst_fd,target):
        os.rename(source,target,src_dir_fd=src_fd,dst_dir_fd=dst_fd)
        raise OSError('simulated native ack lost after rename')
    monkeypatch.setattr(owner_rename,'_rename_exclusive',issued_then_lost)
    with pytest.raises(pub.FinitePublicationEffectUnknown):
        pub._write_exclusive(destination,files,uid=os.getuid(),gid=os.getgid())
    assert destination.exists()
    assert set(p.name for p in destination.iterdir())==pub.FILES
    assert all((destination/name).read_bytes()==data for name,data in files.items())
    assert not list(tmp_path.glob('.fabric-minimax-finite-01.*.stage'))
    with pytest.raises(pub.FinitePublicationRefused,match='already exists'):
        pub._write_exclusive(destination,files,uid=os.getuid(),gid=os.getgid())


def test_failed_native_no_replace_before_effect_discards_own_private_stage(
        monkeypatch,qualified_host,tmp_path):
    _,_,files,_=qualified_host
    destination=tmp_path/'fabric-minimax-finite-01'
    from ops.executive_os import capacity_host_artifacts as owner_rename
    monkeypatch.setattr(owner_rename,'_rename_exclusive',
        lambda *args:(_ for _ in ()).throw(OSError('atomic no-replace refused')))
    with pytest.raises(pub.FinitePublicationRefused,match='without canonical'):
        pub._write_exclusive(destination,files,uid=os.getuid(),gid=os.getgid())
    assert not destination.exists() and not list(tmp_path.glob('.fabric-minimax-finite-01.*.stage'))


def test_private_snapshot_remains_exact_after_mutating_original_mapping(
        monkeypatch,qualified_host,tmp_path):
    _,_,files,_=qualified_host
    destination=tmp_path/'fabric-minimax-finite-01'
    frozen=dict(files)
    original_write=pub.os.write
    changed=[False]
    def mutate_after_first_write(fd,data):
        if not changed[0]:
            files['owner_entry.py']=b'NOT_THE_REVIEWED_ENTRY'
            changed[0]=True
        return original_write(fd,data)
    monkeypatch.setattr(pub.os,'write',mutate_after_first_write)
    digests=pub._write_exclusive(destination,files,uid=os.getuid(),gid=os.getgid())
    assert changed[0]
    assert digests==pub.verify_candidate(frozen)
    assert all((destination/name).read_bytes()==raw for name,raw in frozen.items())

def test_lock_busy_is_definite_refusal_before_any_directory_effect(
        monkeypatch,qualified_host,tmp_path):
    _, prior, files, _ = qualified_host
    home=tmp_path/'control-config';home.mkdir()
    monkeypatch.setattr(pub.owner,'CONFIG_ROOT',home)
    # These fake-host unit fixtures do not impersonate the root-owned
    # production CONFIG_ROOT. The separate guard tests exercise real trust.
    monkeypatch.setattr(pub,'_trusted_control_root',lambda fd: os.fstat(fd))
    monkeypatch.setattr(pub,'DESTINATION',home/'fabric-minimax-finite-01')
    monkeypatch.setattr(pub.os,'geteuid',lambda:0)
    class Owner:
        def require_exact_install(self,sha):return sha
        def require_transaction_absent(self):return None
        def _config_root_safe(self):return None
    monkeypatch.setattr(pub.owner,'ProductionCeoSubmitHost',Owner)
    monkeypatch.setattr(pub.fcntl,'flock',
        lambda *a: (_ for _ in ()).throw(BlockingIOError('other owner writing')))
    called=[]
    with pytest.raises(pub.FinitePublicationRefused,match='mutex occupied'):
        pub.publish_disarmed_definition('a'*40,prior.control_sha256,files,
            verified_capacity_binding=lambda join:called.append(join))
    assert called==[] and not pub.DESTINATION.exists()


def test_installed_release_refusal_never_invokes_capacity(monkeypatch,qualified_host,tmp_path):
    _, prior, files, _ = qualified_host
    monkeypatch.setattr(pub.os,'geteuid',lambda:0)
    class Owner:
        def require_exact_install(self,sha):
            raise ValueError('stale release')
        def require_transaction_absent(self):
            raise AssertionError('not reached')
    monkeypatch.setattr(pub.owner,'ProductionCeoSubmitHost',Owner)
    called=[]
    with pytest.raises(pub.FinitePublicationRefused,match='original Control/Capacity qualification'):
        pub.publish_disarmed_definition('a'*40,prior.control_sha256,files,
            verified_capacity_binding=lambda join:called.append(join) or True)
    assert called==[]

def test_original_private_stage_refuses_new_generation_without_cleanup(
        qualified_host,tmp_path):
    _,_,files,_=qualified_host
    name='.fabric-minimax-finite-01.original.1234.stage'
    orphan=tmp_path/name;orphan.mkdir(mode=0o700)
    destination=tmp_path/'fabric-minimax-finite-01'
    with pytest.raises(pub.FinitePublicationRefused,match='prior finite private stage'):
        pub._write_exclusive(destination,files,uid=os.getuid(),gid=os.getgid())
    assert orphan.exists() and not destination.exists()
    assert [p.name for p in tmp_path.glob('.fabric-minimax-finite-01.*.stage')]==[name]


def test_late_canonical_collision_is_preserved_and_never_replaced(
        monkeypatch,qualified_host,tmp_path):
    _,_,files,_=qualified_host
    destination=tmp_path/'fabric-minimax-finite-01'
    from ops.executive_os import capacity_host_artifacts as owner_rename
    def late_foreign_name(src_fd,source,dst_fd,target):
        os.mkdir(target,0o700,dir_fd=dst_fd)
        raise FileExistsError('test foreign canonical appeared')
    monkeypatch.setattr(owner_rename,'_rename_exclusive',late_foreign_name)
    with pytest.raises(pub.FinitePublicationRefused,match='without canonical'):
        pub._write_exclusive(destination,files,uid=os.getuid(),gid=os.getgid())
    assert destination.exists() and list(destination.iterdir())==[]
    assert not list(tmp_path.glob('.fabric-minimax-finite-01.*.stage'))

def test_invalid_capacity_token_pre_effect_refused(qualified_host):
    import json
    from ops.executive_os.attended_worker_definition import _json
    _,_,files,_=qualified_host
    worker=json.loads(files['worker.json'])
    worker['capacity_capability_id']='not a valid token!'
    candidate=dict(files, **{'worker.json':_json(worker)})
    binding=json.loads(files['bindings.json'])
    binding['bindings'][0]['worker_source_config_digest']=pub.sha256(candidate['worker.json'])
    candidate['bindings.json']=_json(binding)
    with pytest.raises(pub.FinitePublicationRefused,match='finite definition validation'):
        pub.verify_candidate(candidate)


def test_untrusted_control_directory_refuses_after_opening_exact_fd(
        monkeypatch,tmp_path):
    import stat
    path=tmp_path/'unsafe-config'
    path.mkdir(mode=0o777)
    path.chmod(0o777)
    monkeypatch.setattr(pub.owner,'CONFIG_ROOT',path)
    fd=os.open(path,os.O_RDONLY | os.O_DIRECTORY | getattr(os,'O_NOFOLLOW',0))
    try:
        with pytest.raises(pub.FinitePublicationRefused,match='config root is untrusted'):
            pub._trusted_control_root(fd)
    finally:
        os.close(fd)


def test_original_locked_parent_fd_cannot_be_retargeted(
        qualified_host,tmp_path):
    _,_,files,_=qualified_host
    home=tmp_path/'config';home.mkdir()
    destination=home/'fabric-minimax-finite-01'
    fd=os.open(home,os.O_RDONLY | os.O_DIRECTORY)
    old_path=tmp_path/'config-original'
    try:
        home.rename(old_path)
        home.mkdir()
        with pytest.raises(pub.FinitePublicationRefused,match='locked parent directory moved'):
            pub._write_exclusive(destination,files,uid=os.getuid(),gid=os.getgid(),
                                  parent_fd=fd)
        assert list(home.iterdir())==[]
        assert list(old_path.iterdir())==[]
    finally:
        os.close(fd)


def test_close_failure_after_native_publish_does_not_erase_result(
        monkeypatch,qualified_host,tmp_path):
    import stat
    _,_,files,_=qualified_host
    destination=tmp_path/'fabric-minimax-finite-01'
    close_original=pub.os.close
    changed=[False]
    def fail_after_actual_close(fd):
        if not changed[0] and destination.exists():
            try:
                opened=os.fstat(fd)
                canonical=destination.stat()
                same=(stat.S_ISDIR(opened.st_mode) and
                      (opened.st_dev,opened.st_ino)==(canonical.st_dev,canonical.st_ino))
            except OSError:
                same=False
            if same:
                changed[0]=True
                close_original(fd)
                raise OSError('lost close acknowledgement after committed rename')
        return close_original(fd)
    monkeypatch.setattr(pub.os,'close',fail_after_actual_close)
    digests=pub._write_exclusive(destination,files,uid=os.getuid(),gid=os.getgid())
    assert changed==[True]
    assert destination.is_dir() and digests==pub.verify_candidate(files)


def test_stage_open_fd_exhaustion_has_no_canonical_effect(
        monkeypatch,qualified_host,tmp_path):
    import errno
    _,_,files,_=qualified_host
    destination=tmp_path/'fabric-minimax-finite-01'
    actual_open=pub.os.open
    triggered=[False]
    def simulated_fd_limit(path, flags, mode=0o777, *, dir_fd=None):
        if dir_fd is not None and str(path).endswith('.stage') and not triggered[0]:
            triggered[0]=True
            raise OSError(errno.EMFILE,'simulated file descriptor exhaustion')
        return actual_open(path,flags,mode,dir_fd=dir_fd)
    monkeypatch.setattr(pub.os,'open',simulated_fd_limit)
    with pytest.raises(pub.FinitePublicationRefused,match='empty private stage removed'):
        pub._write_exclusive(destination,files,uid=os.getuid(),gid=os.getgid())
    assert triggered==[True] and not destination.exists()
    assert not list(tmp_path.glob('.fabric-minimax-finite-01.*.stage'))


def test_root_publisher_close_error_preserves_applied_receipt(
        monkeypatch,qualified_host,tmp_path):
    _,prior,files,_=qualified_host
    home=tmp_path/'control-config';home.mkdir()
    monkeypatch.setattr(pub.owner,'CONFIG_ROOT',home)
    monkeypatch.setattr(pub,'DESTINATION',home/'fabric-minimax-finite-01')
    monkeypatch.setattr(pub.os,'geteuid',lambda:0)
    monkeypatch.setattr(pub,'_trusted_control_root',lambda fd:os.fstat(fd))
    class FakeHost:
        def require_exact_install(self,sha):pass
        def require_transaction_absent(self):pass
        def _config_root_safe(self):pass
        def require_services_already_stopped(self):pass
        def require_service_uids_quiescent(self):pass
        def load_unarmed_configs(self,sha):return prior
        def require_runtime_quiescent(self,p):pass
    monkeypatch.setattr(pub.owner,'ProductionCeoSubmitHost',FakeHost)
    monkeypatch.setattr(pub,'render_owner_definition',lambda *a:files.copy())
    monkeypatch.setattr(pub,'_write_exclusive',
        lambda path, data, *,uid,gid,parent_fd:pub.verify_candidate(data))
    actual_close=pub.os.close
    injected=[False]
    def bad_close(fd):
        try:
            info=os.fstat(fd); check=home.stat()
            is_lock=(info.st_dev,info.st_ino)==(check.st_dev,check.st_ino)
        except OSError:
            is_lock=False
        actual_close(fd)
        if is_lock and not injected[0]:
            injected[0]=True
            raise OSError('original lock released, acknowledgement lost')
    monkeypatch.setattr(pub.os,'close',bad_close)
    result=pub.publish_disarmed_definition('a'*40,prior.control_sha256,files,
            verified_capacity_binding=lambda *a:True)
    assert injected==[True] and result['effect']=='APPLIED'
