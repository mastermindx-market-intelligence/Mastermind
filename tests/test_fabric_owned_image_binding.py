"""Original Popen binding with inert kernel observations, never live /proc reads."""
import os
import sys

import pytest

from control_plane import linux_process_identity as lpi
from test_fabric_owned_process_phases import lr, begin


def active(lr, tmp_path, monkeypatch):
    def identity(pid):
        return dict(pid=pid, pgid=pid, session_id=pid, boot_id='fixture-boot',
                    process_start_identity='linux:123', effective_uid=os.geteuid(),
                    effective_gid=os.getegid(), real_uid=os.getuid(), real_gid=os.getgid())
    monkeypatch.setattr(lr, '_observe_owned_launch_identity', identity)
    owner, release = begin(lr, tmp_path)
    observation = dict(start_identity='123', pgid=owner.process.pid,
        session_id=owner.process.pid, boot_id='fixture-boot',
        effective_uid=os.geteuid(), effective_gid=os.getegid(),
        real_uid=os.getuid(), real_gid=os.getgid(), parent_pid=os.getpid(),
        sha256='a' * 64, size=42, device=1, inode=2, mode=0o100755,
        uid=50111, gid=50112, mtime_ns=3, ctime_ns=4)
    calls = []
    def inspect(pid):
        calls.append(pid)
        return dict(observation)
    monkeypatch.setattr(lpi, 'inspect_linux_process_image', inspect)
    monkeypatch.setattr(lr.sys, 'platform', 'linux')
    return owner, release, observation, calls


def test_actual_owner_pid_and_kernel_image_preserve_separate_file_principal(lr, tmp_path, monkeypatch):
    owner, release, observation, calls = active(lr, tmp_path, monkeypatch)
    actual = lr.observe_owned_process_image(owner)
    assert calls == [owner.process.pid]
    assert actual == dict(observation, pid=owner.process.pid, label='original-run')
    assert actual['uid'] != actual['effective_uid']
    assert owner.result is None and owner.process.poll() is None
    release.touch()
    assert lr.finish_owned_process(owner).cleanup_proven


@pytest.mark.parametrize('field', ['start_identity', 'pgid', 'session_id', 'boot_id',
                                    'effective_uid', 'effective_gid', 'real_uid', 'real_gid'])
def test_changed_generation_or_principal_cannot_rebind_owner(lr, tmp_path, monkeypatch, field):
    owner, release, observation, calls = active(lr, tmp_path, monkeypatch)
    value = observation[field]
    observation[field] = value + 1 if isinstance(value, int) else value + '-changed'
    with pytest.raises(lr.LaneRuntimeError, match='generation_changed'):
        lr.observe_owned_process_image(owner)
    assert lr._EXECUTION_OWNER is owner and owner.result is None
    release.touch()
    lr.finish_owned_process(owner)


def test_kernel_refusal_retains_original_owner_for_existing_settlement(lr, tmp_path, monkeypatch):
    owner, release, _, _ = active(lr, tmp_path, monkeypatch)
    def refused(pid): raise lpi.LinuxProcessIdentityError('fixture denied')
    monkeypatch.setattr(lpi, 'inspect_linux_process_image', refused)
    with pytest.raises(lr.LaneRuntimeError, match='observation_unqualified'):
        lr.observe_owned_process_image(owner)
    assert lr._EXECUTION_OWNER is owner
    release.touch()
    lr.finish_owned_process(owner)


def test_process_exit_during_observation_refuses_stale_image(lr, tmp_path, monkeypatch):
    owner, release, observation, _ = active(lr, tmp_path, monkeypatch)
    def exits(pid):
        release.touch()
        owner.process.wait(timeout=3)
        return dict(observation)
    monkeypatch.setattr(lpi, 'inspect_linux_process_image', exits)
    with pytest.raises(lr.LaneRuntimeError, match='generation_changed'):
        lr.observe_owned_process_image(owner)
    lr.finish_owned_process(owner)


def test_settled_owner_is_not_reinspected(lr, tmp_path, monkeypatch):
    owner, release, _, calls = active(lr, tmp_path, monkeypatch)
    release.touch()
    lr.finish_owned_process(owner)
    with pytest.raises(lr.LaneRuntimeError, match='not_live'):
        lr.observe_owned_process_image(owner)
    assert calls == []


def test_foreign_handle_and_unqualified_platform_do_not_inspect(lr, tmp_path, monkeypatch):
    owner, release, _, calls = active(lr, tmp_path, monkeypatch)
    with pytest.raises(lr.LaneRuntimeError, match='owner_thread_required'):
        lr.observe_owned_process_image(object())
    monkeypatch.setattr(lr.sys, 'platform', 'darwin')
    with pytest.raises(lr.LaneRuntimeError, match='platform_unqualified'):
        lr.observe_owned_process_image(owner)
    assert calls == []
    release.touch()
    lr.finish_owned_process(owner)
