"""Original local lease mechanics only; no ACK authority or host qualification."""
import dataclasses
import fcntl
import os

import pytest
from test_fabric_owned_process_phases import lr


def lease(lr, tmp_path, *, opted_in=True):
    return lr.LaneLease.acquire(tmp_path / 'active', key='original-run', label='original-run',
        load1=0, cpu_count=4, max_active=4, env={}, reconcile_unreleased=opted_in)


def test_original_release_is_durable_once_and_receipt_is_immutable(lr, tmp_path):
    owner = lease(lr, tmp_path)
    path = owner.path
    before = path.stat()
    value = owner.release_after_assignment_ack()
    assert value.schema == 'mastermind.lane.owned_release/v1'
    assert value.key == path.name and value.marker_inode == before.st_ino
    assert value.marker_device == before.st_dev
    assert value.marker_absent is True and value.parent_synced is True
    assert not path.exists() and owner.fd is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        value.marker_absent = False
    with pytest.raises(lr.LaneRuntimeError): owner.release_after_assignment_ack()


@pytest.mark.parametrize('state', ['held', 'released', 'legacy', 'marker_swap', 'parent_swap', 'hardlink', 'bytes'])
def test_release_refuses_unqualified_original_before_unlink(lr, tmp_path, monkeypatch, state):
    owner = lease(lr, tmp_path, opted_in=state != 'legacy')
    if state == 'held': owner.hold_for_reconciliation('inert_unknown')
    elif state == 'released': owner.release()
    elif state == 'marker_swap':
        owner.path.rename(owner.path.with_name('original-retained'))
        owner.path.write_bytes(b'foreign marker')
    elif state == 'parent_swap':
        owner.path.parent.rename(tmp_path / 'original-directory')
        owner.path.parent.mkdir()
        owner.path.write_bytes(b'foreign parent marker')
    elif state == 'hardlink': os.link(owner.path, tmp_path / 'alias')
    elif state == 'bytes': owner.path.write_bytes(b'changed original bytes')
    before = owner.path.read_bytes() if owner.path.exists() else None
    calls = []
    monkeypatch.setattr(lr.os, 'unlink', lambda *args, **kwargs: calls.append((args, kwargs)))
    with pytest.raises(lr.LaneRuntimeError): owner.release_after_assignment_ack()
    assert calls == []
    assert (owner.path.read_bytes() if owner.path.exists() else None) == before


@pytest.mark.parametrize('failure', ['unlink', 'fsync', 'readback'])
def test_uncertain_release_holds_original_exclusion_and_never_retries(lr, tmp_path, monkeypatch, failure):
    owner = lease(lr, tmp_path)
    old_unlink, old_fsync, old_stat = lr.os.unlink, lr.os.fsync, lr.os.stat
    effects = []
    def unlink(*args, **kwargs):
        effects.append('unlink')
        if failure == 'unlink': raise OSError('inert unlink failure')
        return old_unlink(*args, **kwargs)
    def fsync(fd):
        if failure == 'fsync' and os.fstat(fd).st_ino == owner.path.parent.stat().st_ino:
            raise OSError('inert directory fsync failure')
        return old_fsync(fd)
    def stat(name, *args, **kwargs):
        if failure == 'readback' and name == owner.path.name and 'dir_fd' in kwargs:
            # Raise only once the actual original marker has been unlinked.
            if not owner.path.exists(): raise PermissionError('inert absence unknown')
        return old_stat(name, *args, **kwargs)
    monkeypatch.setattr(lr.os, 'unlink', unlink)
    monkeypatch.setattr(lr.os, 'fsync', fsync)
    monkeypatch.setattr(lr.os, 'stat', stat)
    with pytest.raises(lr.LaneRuntimeError): owner.release_after_assignment_ack()
    assert owner._preserve is True and not owner._released
    assert owner.fd is not None
    assert effects == ['unlink']
    with pytest.raises(lr.LaneRuntimeError): owner.release_after_assignment_ack()
    assert effects == ['unlink']
    other = os.open(owner.path.parent / '.admission.lock', os.O_RDWR)
    try:
        with pytest.raises(BlockingIOError): fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally: os.close(other)
    # Only fixture teardown closes retained descriptors; no reconciliation effect.
    os.close(owner._assignment_release_lock_fd)
    owner._assignment_release_lock_fd = None
    if owner._assignment_release_parent_fd is not None:
        os.close(owner._assignment_release_parent_fd)
        owner._assignment_release_parent_fd = None


def test_legacy_release_remains_none_and_does_not_mint_receipt(lr, tmp_path):
    owner = lease(lr, tmp_path, opted_in=False)
    assert owner.release() is None
    assert not owner.path.exists()


def test_wrong_original_thread_refuses_without_unlink(lr, tmp_path, monkeypatch):
    owner = lease(lr, tmp_path)
    monkeypatch.setattr(lr.threading, 'get_ident', lambda: owner._assignment_owner_thread + 1)
    with pytest.raises(lr.LaneRuntimeError): owner.release_after_assignment_ack()
    assert owner.path.exists() and owner._preserve


def test_parent_replacement_after_unlink_is_not_release_proof(lr, tmp_path, monkeypatch):
    owner = lease(lr, tmp_path)
    original = lr.os.fsync
    before = owner.path.parent.stat()
    moved = tmp_path / 'retained-parent'
    def fsync(fd):
        original(fd)
        if os.fstat(fd).st_ino == before.st_ino:
            owner.path.parent.rename(moved)
            owner.path.parent.mkdir()
    monkeypatch.setattr(lr.os, 'fsync', fsync)
    with pytest.raises(lr.LaneRuntimeError): owner.release_after_assignment_ack()
    assert owner._preserve and owner._assignment_release_receipt is None
    assert not (moved / owner.path.name).exists()
    assert not owner.path.exists()  # no replacement marker/history is fabricated
    os.close(owner._assignment_release_lock_fd)
    os.close(owner._assignment_release_parent_fd)
    owner._assignment_release_lock_fd = owner._assignment_release_parent_fd = None


def test_release_unknown_hold_does_not_relock_or_rewrite_original_custody(lr, tmp_path, monkeypatch):
    owner = lease(lr, tmp_path)
    old_fsync = lr.os.fsync
    parent_inode = owner.path.parent.stat().st_ino
    def fsync(fd):
        if os.fstat(fd).st_ino == parent_inode:
            raise OSError('inert interrupted parent durability')
        return old_fsync(fd)
    monkeypatch.setattr(lr.os, 'fsync', fsync)
    with pytest.raises(lr.LaneRuntimeError): owner.release_after_assignment_ack()
    assert not owner.path.exists()
    original_failure = owner._assignment_release_failure
    def no_second_lock_or_marker(*args, **kwargs):
        pytest.fail('reconciliation hold would reacquire its already-held admission lock')
    monkeypatch.setattr(lr.os, 'open', no_second_lock_or_marker)
    owner.hold_for_reconciliation('actual_backend_release_failed')
    assert owner._assignment_release_failure == original_failure
    assert owner._preserve and not owner.path.exists()
    os.close(owner._assignment_release_lock_fd)
    os.close(owner._assignment_release_parent_fd)
    owner._assignment_release_lock_fd = owner._assignment_release_parent_fd = None
