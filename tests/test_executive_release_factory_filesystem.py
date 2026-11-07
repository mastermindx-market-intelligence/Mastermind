"""Real disposable filesystem races with explicitly synthetic root/ACL facts."""
import os
from pathlib import Path
import stat
import time
from types import SimpleNamespace

import pytest

from control_plane import executive_release_factory as f


@pytest.fixture
def filesystem(tmp_path, monkeypatch):
    if f.sys.platform != "darwin":
        pytest.skip("Darwin descriptor observer")
    real_stat, real_fstat = os.stat, os.fstat
    external_volume = Path('/Volumes/Mastermind')
    external_ino = real_stat(external_volume).st_ino if external_volume.exists() else None
    # Only identity ownership and absence of ACLs are synthetic. Actual opens,
    # directory descriptors, symlinks, FIFO types and replace races are real.
    def root_info(info):
        values = {name: getattr(info, name) for name in dir(info) if name.startswith('st_')}
        values.update(st_uid=0, st_gid=0)
        # Qualify only the user's external-volume ancestor in this disposable
        # fixture; never chmod the shared volume or weaken the real observer.
        if info.st_ino == external_ino and stat.S_ISDIR(info.st_mode):
            values['st_mode'] = info.st_mode & ~0o022
        return SimpleNamespace(**values)
    def stat_info(*args, **kwargs):
        return root_info(real_stat(*args, **kwargs))
    def fstat_info(*args, **kwargs):
        return root_info(real_fstat(*args, **kwargs))
    # supports_dir_fd lists original native builtins; build a Reader before the
    # test-only metadata wrapper so production feature detection stays real.
    reader = f._Reader()
    monkeypatch.setattr(f.os, "stat", stat_info)
    monkeypatch.setattr(f.os, "fstat", fstat_info)
    monkeypatch.setattr(f, "has_macos_acl", lambda *args, **kwargs: False)
    leaf = tmp_path / "leaf"
    leaf.write_bytes(b"unchanged bytes")
    leaf.chmod(0o400)
    return reader, leaf


def test_held_descriptor_read_and_flags(filesystem, monkeypatch):
    reader, leaf = filesystem
    real_open, real_close = os.open, os.close
    opened, closed, leaf_flags = [], [], []
    def opening(path, flags, *args, **kwargs):
        descriptor = real_open(path, flags, *args, **kwargs)
        opened.append(descriptor)
        if path == leaf.name:
            leaf_flags.append(flags)
        return descriptor
    def closing(descriptor):
        closed.append(descriptor)
        return real_close(descriptor)
    monkeypatch.setattr(f.os, "open", opening)
    monkeypatch.setattr(f.os, "close", closing)
    observed = reader.observe(leaf, maximum=100, mode=0o400)
    assert observed.raw == b"unchanged bytes"
    assert observed.sha256 == f._hash(observed.raw)
    assert leaf_flags[0] & (os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC) == (
        os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
    assert sorted(opened) == sorted(closed)


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo", "directory", "writable"])
def test_hostile_leaf_types_refuse(filesystem, kind):
    reader, leaf = filesystem
    if kind == "symlink":
        other = leaf.with_name("other")
        leaf.rename(other)
        leaf.symlink_to(other)
    elif kind == "hardlink":
        os.link(leaf, leaf.with_name("other"))
    elif kind == "fifo":
        leaf.unlink()
        os.mkfifo(leaf, 0o400)
    elif kind == "directory":
        leaf.unlink()
        leaf.mkdir(mode=0o500)
    else:
        leaf.chmod(0o422)
    started = time.monotonic()
    with pytest.raises(f.ReleaseConsumerError):
        reader.observe(leaf, maximum=100, mode=0o400)
    assert time.monotonic() - started < 1


def test_prechecked_leaf_raced_to_fifo_never_blocks_and_closes(filesystem, monkeypatch):
    reader, leaf = filesystem
    real_open, real_close = os.open, os.close
    opened, closed = [], []
    def opening(path, flags, *args, **kwargs):
        if path == leaf.name:
            leaf.unlink()
            os.mkfifo(leaf, 0o400)
            assert flags & os.O_NONBLOCK
        descriptor = real_open(path, flags, *args, **kwargs)
        opened.append(descriptor)
        return descriptor
    def closing(descriptor):
        closed.append(descriptor)
        return real_close(descriptor)
    monkeypatch.setattr(f.os, "open", opening)
    monkeypatch.setattr(f.os, "close", closing)
    started = time.monotonic()
    with pytest.raises(f.ReleaseConsumerError):
        reader.observe(leaf, maximum=100, mode=0o400)
    assert time.monotonic() - started < 1
    assert sorted(opened) == sorted(closed)


def test_same_length_replacement_during_read_refuses(filesystem, monkeypatch):
    reader, leaf = filesystem
    real_read = os.read
    changed = []
    def reading(descriptor, count):
        data = real_read(descriptor, count)
        if data and not changed:
            changed.append(True)
            replacement = leaf.with_name("replacement")
            replacement.write_bytes(b"different bytes")
            replacement.chmod(0o400)
            replacement.replace(leaf)
        return data
    monkeypatch.setattr(f.os, "read", reading)
    with pytest.raises(f.ReleaseConsumerError):
        reader.observe(leaf, maximum=100, mode=0o400)
    assert changed


def test_acl_refusal_observes_held_descriptor(filesystem, monkeypatch):
    reader, leaf = filesystem
    seen = []
    def acl(path, *, expected_identity, descriptor):
        seen.append(descriptor)
        assert os.fstat(descriptor).st_ino == expected_identity.st_ino
        return stat.S_ISREG(expected_identity.st_mode)
    monkeypatch.setattr(f, "has_macos_acl", acl)
    with pytest.raises(f.ReleaseConsumerError):
        reader.observe(leaf, maximum=100, mode=0o400)
    assert seen


def test_exhausted_budget_and_oversized_leaf_refuse(filesystem):
    reader, leaf = filesystem
    with pytest.raises(f.ReleaseConsumerError):
        reader.observe(leaf, maximum=2, mode=0o400)
    reader.deadline_monotonic_ns = 0
    with pytest.raises(f.ReleaseConsumerError):
        reader.observe(leaf, maximum=100, mode=0o400)


def test_missing_required_native_flag_refuses(monkeypatch):
    monkeypatch.setattr(f.os, "O_NONBLOCK", 0)
    with pytest.raises(f.ReleaseConsumerError):
        f._Reader()


@pytest.mark.parametrize("payload,valid", [
    (b"ABCDEF12-1111-4111-8111-111111111111\n", True),
    (b"0" * 4097, False), (b"", False),
    (b"00000000-0000-0000-0000-000000000000\n", False),
])
def test_boot_observation_has_fixed_command_bounded_pipe_and_cleanup(monkeypatch, payload, valid):
    read_fd, write_fd = os.pipe()
    os.write(write_fd, payload)
    os.close(write_fd)
    class Process:
        stdout = os.fdopen(read_fd, "rb")
        def wait(self, timeout):
            assert 0 < timeout <= 2
            return 0
        def poll(self):
            return 0
        def kill(self):
            pytest.fail("completed synthetic sysctl must not be killed")
    process = Process()
    def spawn(argv, **kwargs):
        assert argv == ["/usr/sbin/sysctl", "-n", "kern.bootsessionuuid"]
        assert kwargs["cwd"] == "/" and "shell" not in kwargs
        assert set(kwargs["env"]) == {"PATH", "LANG", "LC_ALL"}
        return process
    monkeypatch.setattr(f.subprocess, "Popen", spawn)
    if valid:
        assert f._boot_id() == "abcdef12-1111-4111-8111-111111111111"
    else:
        with pytest.raises(f.ReleaseConsumerError):
            f._boot_id()
    assert process.stdout.closed
