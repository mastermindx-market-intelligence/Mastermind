"""Kernel identity fixtures only: no host census, environ read or live API probe."""
import ctypes
import os
from pathlib import Path
import pytest
import lane_runtime as lr


def linux_fixture(monkeypatch, *, pid=4321, ticks="987654", state="S", status=None, boot="12345678-1234-5678-1234-567812345678"):
    observe = lr._observe_owned_launch_identity
    fields = [state, "40", str(pid), str(pid)] + ["0"] * 15 + [ticks]
    raw = f"{pid} (fixture ) with spaces) " + " ".join(fields)
    texts = {"/proc/sys/kernel/random/boot_id": boot,
             f"/proc/{pid}/stat": raw,
             f"/proc/{pid}/status": status or "Name:\tfixture\nUid:\t501 502 502 502\nGid:\t20 21 21 21\n"}
    accessed = []
    def read(path):
        accessed.append(path)
        return texts[path]
    monkeypatch.setattr(lr.sys, "platform", "linux")
    monkeypatch.setattr(lr, "_launch_kernel_text", read)
    monkeypatch.setattr(lr.os, "getpgid", lambda n: n)
    monkeypatch.setattr(lr.os, "getsid", lambda n: n)
    return observe, accessed


def test_linux_identity_reads_only_fixed_owned_public_metadata(monkeypatch):
    observe, accessed = linux_fixture(monkeypatch)
    actual = observe(4321)
    assert actual == dict(pid=4321, pgid=4321, session_id=4321,
        boot_id="12345678-1234-5678-1234-567812345678",
        process_start_identity="linux:987654", effective_uid=502,
        effective_gid=21, real_uid=501, real_gid=20)
    assert accessed == ["/proc/sys/kernel/random/boot_id", "/proc/4321/stat", "/proc/4321/status"]


@pytest.mark.parametrize("overrides", [
    {"ticks": "-1"}, {"ticks": "invalid"}, {"state": "Z"}, {"state": "X"},
    {"boot": "invalid boot"},
    {"status": "Uid: 501 502 502 502\nUid: 501 502 502 502\nGid: 20 21 21 21"},
    {"status": "Uid: 501 502 502\nGid: 20 21 21 21"},
    {"status": "Uid: 501 -1 502 502\nGid: 20 21 21 21"},
])
def test_linux_malformed_or_dead_identity_refuses(monkeypatch, overrides):
    observe, _ = linux_fixture(monkeypatch, **overrides)
    with pytest.raises(lr.LaneRuntimeError, match="launch_identity_unavailable"):
        observe(4321)


def darwin_fixture(monkeypatch, *, start_sec=1791710000, start_usec=123456, reported_pid=4321, returned_size=None):
    observe = lr._observe_owned_launch_identity
    class Reader:
        def __call__(self, pid, flavor, arg, pointer, size):
            assert (pid, flavor, arg, size) == (4321, 3, 0, ctypes.sizeof(lr._LaunchProcBSDInfo))
            info = ctypes.cast(pointer, ctypes.POINTER(lr._LaunchProcBSDInfo)).contents
            info.pid = reported_pid
            info.pgid = pid
            info.uid, info.gid, info.ruid, info.rgid = 502, 21, 501, 20
            info.start_sec, info.start_usec = start_sec, start_usec
            return size if returned_size is None else returned_size
    class Library:
        proc_pidinfo = Reader()
    monkeypatch.setattr(lr.sys, "platform", "darwin")
    monkeypatch.setattr(lr.ctypes, "CDLL", lambda path, **kw: Library())
    def sysctl(command, *, timeout):
        assert command == ["/usr/sbin/sysctl", "-n", "kern.bootsessionuuid"]
        assert timeout == 2
        return ["12345678-1234-5678-1234-567812345678"]
    monkeypatch.setattr(lr, "_run_ps_lines", sysctl)
    monkeypatch.setattr(lr.os, "getpgid", lambda n: n)
    monkeypatch.setattr(lr.os, "getsid", lambda n: n)
    return observe


def test_darwin_identity_uses_exact_libproc_public_structure(monkeypatch):
    actual = darwin_fixture(monkeypatch)(4321)
    assert ctypes.sizeof(lr._LaunchProcBSDInfo) == 136
    assert actual["process_start_identity"] == "darwin:1791710000.123456"
    assert (actual["effective_uid"], actual["effective_gid"], actual["real_uid"], actual["real_gid"]) == (502, 21, 501, 20)


@pytest.mark.parametrize("overrides", [
    {"start_sec": 0}, {"start_usec": 1000000},
    {"reported_pid": 99}, {"returned_size": 0},
])
def test_darwin_invalid_generation_or_partial_read_refuses(monkeypatch, overrides):
    observe = darwin_fixture(monkeypatch, **overrides)
    with pytest.raises(lr.LaneRuntimeError, match="launch_identity_unavailable"):
        observe(4321)


def test_moved_receipt_parent_never_releases_target(tmp_path, monkeypatch):
    parent = tmp_path / "private"
    parent.mkdir(mode=0o700)
    launch = parent / "launch.json"
    moved = tmp_path / "moved"
    link = lr.os.link
    def swap(*args, **kwargs):
        link(*args, **kwargs)
        parent.rename(moved)
        parent.mkdir(mode=0o700)
    monkeypatch.setattr(lr.os, "link", swap)
    with pytest.raises(lr.LaneRuntimeError, match="launch_receipt_directory_moved"):
        lr._write_immutable_launch_receipt(launch, {"schema": "fixture"})
    assert not launch.exists()
    assert (moved / "launch.json").exists(), "retain already published evidence for reconciliation"


def test_publication_flushes_readonly_mode_before_link(tmp_path, monkeypatch):
    calls = []
    fsync, fchmod, link = lr.os.fsync, lr.os.fchmod, lr.os.link
    def sync(fd):
        calls.append("fsync")
        fsync(fd)
    def mode(fd, value):
        calls.append("fchmod")
        fchmod(fd, value)
    def publish(*args, **kwargs):
        assert "fchmod" in calls
        assert "fsync" in calls[calls.index("fchmod") + 1:]
        calls.append("link")
        link(*args, **kwargs)
    monkeypatch.setattr(lr.os, "fsync", sync)
    monkeypatch.setattr(lr.os, "fchmod", mode)
    monkeypatch.setattr(lr.os, "link", publish)
    lr._write_immutable_launch_receipt(tmp_path / "launch.json", {"schema": "fixture"})
