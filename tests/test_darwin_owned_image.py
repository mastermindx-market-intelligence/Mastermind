"""Exact original-child image semantics; deterministic drift falsifiers."""
import dataclasses
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
from contextlib import contextmanager
import pytest
from control_plane import darwin_process_image as d
from control_plane.codex_worker import ProcessIdentity
from control_plane.executive_process_identity import _ProcessInstanceObservation
from integrations.session_bridge.bound_launch_capture.runtime import lane_runtime as lane
from integrations.session_bridge.bound_launch_capture import fabric_owned_start as producer


@pytest.fixture
def image(tmp_path,monkeypatch):
    path=tmp_path/'image';path.write_bytes(b'inert executable bytes');path.chmod(0o555)
    observation=('11111111-2222-3333-4444-555555555555',_ProcessInstanceObservation(3,4),
        ProcessIdentity('100.000001',22,22,470,470,470,470,os.getpid()),path)
    state=SimpleNamespace(observation=observation,reads=0,change=None)
    def observe(pid):
        assert pid==22
        state.reads+=1
        if state.reads>1 and state.change:
            return state.change(observation)
        return observation
    monkeypatch.setattr(d.sys,'platform','darwin')
    monkeypatch.setattr(d,'_kernel_observation',observe)
    @contextmanager
    def inert_file(path):
        fd=os.open(path,os.O_RDONLY)
        try:yield fd,os.fstat(fd)
        finally:os.close(fd)
    # Custody check separately belongs to existing _native_open tests. Actual
    # FD hashing and process-bracket equality remain active here.
    monkeypatch.setattr(d,'_native_open',inert_file)
    return state


def test_actual_fd_hash_and_darwin_generation(image):
    row=d.inspect_owned_darwin_image(22)
    assert row['sha256']==hashlib.sha256(b'inert executable bytes').hexdigest()
    assert row['process_start_identity']=='darwin:100.000001'
    assert row['parent_pid']==os.getpid() and row['exec_instance']['pidversion']==4
    assert producer._qualified_generation(row)=='darwin:100.000001'


@pytest.mark.parametrize('change',[
    lambda v:(v[0],dataclasses.replace(v[1],unique_id=99),v[2],v[3]),
    lambda v:(v[0],dataclasses.replace(v[1],pidversion=99),v[2],v[3]),
    lambda v:(v[0],v[1],dataclasses.replace(v[2],effective_uid=99),v[3]),
    lambda v:(v[0],v[1],dataclasses.replace(v[2],parent_pid=99),v[3]),
    lambda v:(v[0],v[1],v[2],Path('/different/kernel/image')),
])
def test_generation_principal_parent_or_image_drift_refuses(image,change):
    image.change=change
    with pytest.raises(d.DarwinProcessImageError):d.inspect_owned_darwin_image(22)


def test_exec_instance_latched_on_original_owner(image,monkeypatch):
    row=d.inspect_owned_darwin_image(22)
    owner=SimpleNamespace(result=None,process=SimpleNamespace(pid=22,poll=lambda:None),label='original',
        _identity=dict(pid=22,pgid=22,session_id=22,boot_id=row['boot_id'],
            process_start_identity=row['process_start_identity'],effective_uid=470,effective_gid=470,
            real_uid=470,real_gid=470))
    monkeypatch.setattr(lane,'_require_owned_execution',lambda candidate: candidate is owner or pytest.fail('foreign'))
    monkeypatch.setattr(d,'inspect_owned_darwin_image',lambda pid:dict(row))
    first=lane.observe_owned_process_image(owner)
    assert first['process_start_identity'].startswith('darwin:')
    row['exec_instance']={**row['exec_instance'],'pidversion':99}
    with pytest.raises(lane.LaneRuntimeError,match='exec_instance_changed'):
        lane.observe_owned_process_image(owner)


def test_launcher_is_not_the_executed_image(image):
    row=d.inspect_owned_darwin_image(22)
    pin=SimpleNamespace(**{k:row[k] for k in ('device','inode','size','sha256','uid','gid','mtime_ns','mode')},
        version='inert',real_path='/different/launcher')
    pin.inode+=1
    with pytest.raises(producer.OwnedStartRefused,match='pinned_binary_mismatch'):
        producer._match_pinned_binary(row,pin)


def test_fake_platform_label_refuses():
    with pytest.raises(producer.OwnedStartRefused):
        producer._qualified_generation({'start_identity':'100.000001','process_start_identity':'linux:100.000001'})


@pytest.mark.parametrize('when',['unchanged','before','after'])
def test_actual_retainer_detects_same_path_exec_and_preserves_once_fence(tmp_path,monkeypatch,when):
    from test_fabric_owned_start_retention import active, encode
    # Existing inert launch fixture is used for one harmless child; its owner
    # and real retainer execute from the newly packaged production module.
    monkeypatch.setattr(lane,'_observe_owned_launch_identity',lambda pid:dict(
        pid=pid,pgid=pid,session_id=pid,boot_id='fixture-boot',process_start_identity='darwin:100.000001',
        effective_uid=os.geteuid(),effective_gid=os.getegid(),real_uid=os.getuid(),real_gid=os.getgid()))
    monkeypatch.setattr(lane,'_session_pids',lambda pgid:())
    monkeypatch.setattr(lane,'_verified_group_members',lambda pgid:((pgid,),True))
    owner,release,holds,record=active(lane,tmp_path)
    snapshot={'exec_instance':{'unique_id':3,'pidversion':4}}
    owner._observed_image_snapshot=snapshot
    observations=[]
    def observe(candidate):
        assert candidate is owner
        observations.append(True)
        if when=='before' or (when=='after' and len(observations)>1):
            raise lane.LaneRuntimeError('owned_image_exec_instance_changed')
        return snapshot
    monkeypatch.setattr(lane,'observe_owned_process_image',observe)
    try:
        if when=='unchanged':
            digest=lane.retain_owned_start_bytes(owner,encode(record))
            assert digest==hashlib.sha256(encode(record)).hexdigest()
            assert holds==[] and len(observations)==2
        else:
            with pytest.raises(lane.LaneRuntimeError,match='exec_instance_changed'):
                lane.retain_owned_start_bytes(owner,encode(record))
            assert owner._start_record_sha256 is None
            assert holds==['owned_start_publication_unconfirmed']
        assert owner._start_publication_attempted
        assert owner._original_start_receipt_path.exists() is (when!='before')
        with pytest.raises(lane.LaneRuntimeError,match='already_attempted'):
            lane.retain_owned_start_bytes(owner,encode(record))
    finally:
        release.touch()
        lane.finish_owned_process(owner)


def test_foreign_handle_cannot_enter_packaged_observer():
    with pytest.raises(lane.LaneRuntimeError):lane.observe_owned_process_image(SimpleNamespace())


def test_packaged_linux_observer_keeps_linux_identity(monkeypatch):
    from control_plane import linux_process_identity
    monkeypatch.setattr(lane.sys,'platform','linux')
    identity=dict(pid=22,pgid=22,session_id=22,boot_id='linux-boot',process_start_identity='linux:789',
        effective_uid=470,effective_gid=470,real_uid=470,real_gid=470)
    row={k:v for k,v in identity.items() if k not in ('pid','process_start_identity')}
    row.update(start_identity='789',parent_pid=os.getpid())
    owner=SimpleNamespace(result=None,process=SimpleNamespace(pid=22,poll=lambda:None),label='original',_identity=identity)
    monkeypatch.setattr(lane,'_require_owned_execution',lambda candidate: candidate is owner or pytest.fail('foreign'))
    monkeypatch.setattr(linux_process_identity,'inspect_linux_process_image',lambda pid:dict(row))
    observed=lane.observe_owned_process_image(owner)
    assert producer._qualified_generation(observed)=='linux:789'
    assert lane.observe_owned_process_image(owner)==observed
