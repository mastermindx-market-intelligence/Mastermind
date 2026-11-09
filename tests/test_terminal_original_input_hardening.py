"""Inert real-file regressions for durable input preparation and post-read custody."""
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from control_plane import terminal_original_input_artifacts as toi
from tests.test_terminal_original_input_artifacts import (
    CANARY, CMD, ISSUER, FINGERPRINT, PAYLOAD, artifact_path, make_helper, prepare, read,
)


def test_directory_sync_failure_never_returns_prepared_reference(tmp_path, monkeypatch):
    h = make_helper(tmp_path)
    actual = os.fsync
    def fail_directory(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("synthetic-private-fsync-canary")
        return actual(fd)
    monkeypatch.setattr(toi.os, "fsync", fail_directory)
    with pytest.raises(toi.TerminalInputError) as error:
        prepare(h)
    assert str(error.value) == toi.TERMINAL_INPUT_UNAVAILABLE


def test_zero_byte_write_stops_immediately_and_retains_partial_identity(tmp_path, monkeypatch):
    h = make_helper(tmp_path)
    calls = []
    def no_progress(fd, payload):
        calls.append(fd)
        if len(calls) == 1:
            return 0
        raise OSError("bounded test guard: old implementation repeated zero write")
    with monkeypatch.context() as patch:
        patch.setattr(toi.os, "write", no_progress)
        with pytest.raises(toi.TerminalInputError):
            prepare(h)
    assert len(calls) == 1
    path = artifact_path(tmp_path)
    inode = path.stat().st_ino
    assert path.read_bytes() == b""
    with pytest.raises(toi.TerminalInputError):
        prepare(h)
    assert path.stat().st_ino == inode
    assert len(list((tmp_path / toi.PRIVATE_SUBDIR).glob("*/input.bin"))) == 1


def test_original_complete_file_reconciles_durably_after_key_sync_failure(tmp_path, monkeypatch):
    h = make_helper(tmp_path)
    path = artifact_path(tmp_path)
    actual_sync = os.fsync
    def fail_key_sync(fd):
        info = os.fstat(fd)
        if path.parent.exists() and stat.S_ISDIR(info.st_mode) and info.st_ino == path.parent.stat().st_ino:
            raise OSError("synthetic key sync failure")
        return actual_sync(fd)
    with monkeypatch.context() as patch:
        patch.setattr(toi.os, "fsync", fail_key_sync)
        with pytest.raises(toi.TerminalInputError):
            prepare(h)
    inode, data = path.stat().st_ino, path.read_bytes()
    synced = []
    def record_sync(fd):
        synced.append(os.fstat(fd).st_ino)
        return actual_sync(fd)
    def no_replay(*_):
        raise AssertionError("reconciliation must not replay any write")
    with monkeypatch.context() as patch:
        patch.setattr(toi.os, "fsync", record_sync)
        patch.setattr(toi.os, "write", no_replay)
        ref = prepare(h)
    assert inode in synced
    assert path.parent.stat().st_ino in synced
    assert path.stat().st_ino == inode and path.read_bytes() == data
    assert read(h, ref.artifact_sha256) == PAYLOAD


@pytest.mark.parametrize("flag", ["_O_DIRECTORY", "_O_NOFOLLOW", "_O_NONBLOCK"])
def test_missing_atomic_open_primitive_is_unavailable(tmp_path, monkeypatch, flag):
    monkeypatch.setattr(toi, flag, 0)
    with pytest.raises(toi.TerminalInputError) as error:
        make_helper(tmp_path)
    assert str(error.value) == toi.TERMINAL_INPUT_UNAVAILABLE


@pytest.mark.parametrize("operation", ["prepare", "read"])
def test_fifo_at_original_input_refuses_without_blocking_or_replacement(tmp_path, operation):
    """A two-second child boundary prevents an old blocking open hanging pytest."""
    h = make_helper(tmp_path)
    prepare(h)
    path = artifact_path(tmp_path)
    path.unlink()  # Replace only this test's inert setup artifact with the adversarial FIFO.
    os.mkfifo(path, 0o600)
    inode = path.stat().st_ino
    program = """
import sys
from pathlib import Path
from control_plane.terminal_original_input_artifacts import TerminalOriginalInputArtifacts, TerminalInputError
h = TerminalOriginalInputArtifacts(Path(sys.argv[1]))
arguments = dict(command_id='cmd-001', issuer_scope_sha256='a'*64, fingerprint_sha256='b'*64)
try:
    if sys.argv[2] == 'prepare':
        h.prepare(**arguments, payload=b'inert source input')
    else:
        h.read(**arguments, expected_artifact_sha256='c'*64)
except TerminalInputError as error:
    assert str(error) == 'TERMINAL_INPUT_UNAVAILABLE'
else:
    raise AssertionError('FIFO was accepted')
"""
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-B", "-c", program, str(tmp_path), operation],
                            cwd=root, env={"PATH": os.defpath, "PYTHONPATH": str(root)},
                            capture_output=True, timeout=2)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert path.stat().st_ino == inode
    assert stat.S_ISFIFO(path.stat().st_mode)


@pytest.mark.parametrize("target", ["file", "key", "root", "key_mode"])
def test_read_refuses_changed_path_binding_after_file_open(tmp_path, monkeypatch, target):
    root = tmp_path / "runs"
    root.mkdir(mode=0o700)
    h = make_helper(root)
    ref = prepare(h, payload=CANARY)
    path = artifact_path(root)
    inode = path.stat().st_ino
    actual_read = os.read
    changed = []
    def substitute(fd, size):
        value = actual_read(fd, size)
        if not changed and os.fstat(fd).st_ino == inode:
            changed.append(True)
            if target == "file":
                path.rename(path.with_name("retained-original.bin"))
                path.write_bytes(b"replacement")
                path.chmod(0o600)
            elif target == "key":
                key = path.parent
                key.rename(key.with_name(key.name + "-retained"))
                key.mkdir(mode=0o700)
            elif target == "root":
                root.rename(tmp_path / "retained-root")
                root.mkdir(mode=0o700)
            else:
                path.parent.chmod(0o755)
        return value
    monkeypatch.setattr(toi.os, "read", substitute)
    with pytest.raises(toi.TerminalInputError) as error:
        read(h, ref.artifact_sha256)
    assert changed
    assert str(error.value) == toi.TERMINAL_INPUT_UNAVAILABLE
    assert CANARY.decode() not in str(error.value)


def test_read_native_error_does_not_expose_error_payload(tmp_path, monkeypatch):
    h = make_helper(tmp_path)
    ref = prepare(h)
    def fail_read(*_):
        raise OSError("synthetic-private-native-error-canary")
    monkeypatch.setattr(toi.os, "read", fail_read)
    with pytest.raises(toi.TerminalInputError) as error:
        read(h, ref.artifact_sha256)
    assert str(error.value) == toi.TERMINAL_INPUT_UNAVAILABLE


def test_noncanonical_existing_header_is_not_reaccepted_with_new_digest(tmp_path):
    h = make_helper(tmp_path)
    prepare(h)
    path = artifact_path(tmp_path)
    header, body = path.read_bytes().split(b"\n", 1)
    path.write_bytes(header.replace(b'":"', b'": "') + b"\n" + body)
    altered = path.read_bytes()
    inode = path.stat().st_ino
    with pytest.raises(toi.TerminalInputError):
        prepare(h)
    assert path.read_bytes() == altered
    assert path.stat().st_ino == inode


def test_root_descriptor_is_closed_when_postopen_identity_refuses(tmp_path, monkeypatch):
    h = make_helper(tmp_path)
    ref = prepare(h)
    actual_stat = os.fstat
    affected = []
    def drift(fd):
        value = actual_stat(fd)
        if not affected and stat.S_ISDIR(value.st_mode):
            affected.append(fd)
            fields = list(value)
            fields[1] += 1
            return os.stat_result(fields)
        return value
    with monkeypatch.context() as patch:
        patch.setattr(toi.os, "fstat", drift)
        with pytest.raises(toi.TerminalInputError):
            read(h, ref.artifact_sha256)
    assert affected
    with pytest.raises(OSError):
        actual_stat(affected[0])
