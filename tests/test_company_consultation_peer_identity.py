"""Lineage qualification only; no provider, service grant, or dispatch."""
from __future__ import annotations

from dataclasses import replace
import os
import socket
import subprocess
import sys

import pytest

from control_plane import company_consultation_peer_identity as lineage
from control_plane import executive_peer_identity as peer
from control_plane.codex_worker import ProcessIdentity, ProcessInspector
from control_plane.executive_process_identity import _ProcessInstanceObservation


@pytest.fixture
def family(monkeypatch):
    left, right = socket.socketpair()
    observation = peer._KernelObservation(
        b"K" * 32, 451, 200, 20, peer._descriptor_identity(left)
    )
    monkeypatch.setattr(peer, "_observe_socket", lambda _: observation)
    child = ProcessIdentity("child-start", 100, 100, 451, 451, 451, 451, 100)
    parent = ProcessIdentity("parent-start", 100, 100, 451, 451, 451, 451, 50)
    processes = {200: child, 100: parent}
    instances = {
        200: _ProcessInstanceObservation(2000, 20, 1000, 10),
        100: _ProcessInstanceObservation(1000, 10, 500, 5),
    }
    class Inspector:
        def inspect(self, pid):
            return processes[pid]
        def boot_session_id(self):
            return "boot"
    monkeypatch.setattr(lineage, "_observe_process_instance", instances.__getitem__)
    try:
        yield peer.capture_peer_identity(left), Inspector(), processes, instances, observation
    finally:
        left.close()
        right.close()


def check(family, **changes):
    captured, inspector, *_ = family
    fields = dict(writer_pid=100, writer_pgid=100,
                  writer_start_identity="parent-start", writer_boot_id="boot")
    fields.update(changes)
    return lineage.require_current_writer_parent(captured, inspector=inspector, **fields)


def test_direct_child_matches_current_writer(family):
    captured, inspector, *_ = family
    assert lineage.immediate_parent_pid(captured, inspector=inspector) == 100
    assert check(family) is None


@pytest.mark.parametrize("field,value", [
    ("writer_pid", True), ("writer_pid", 0), ("writer_pgid", None),
    ("writer_start_identity", ""), ("writer_boot_id", ""),
])
def test_incomplete_writer_facts_refuse(family, field, value):
    with pytest.raises(peer.PeerIdentityError, match="CONSULT_WRITER_IDENTITY_REQUIRED"):
        check(family, **{field: value})


@pytest.mark.parametrize("field,value", [
    ("parent_pid", None), ("parent_pid", 0), ("parent_pid", True),
    ("effective_uid", 501), ("real_uid", 0),
])
def test_child_process_must_have_exact_principal_and_parent(family, field, value):
    family[2][200] = replace(family[2][200], **{field: value})
    with pytest.raises(peer.PeerIdentityError, match="CONSULT_CHILD_IDENTITY_UNAVAILABLE"):
        check(family)


@pytest.mark.parametrize("field,value", [
    ("parent_unique_id", None), ("parent_unique_id", 0), ("pidversion", 21),
    ("parent_pidversion", None), ("parent_pidversion", 0),
])
def test_child_native_instance_must_match_socket(family, field, value):
    family[3][200] = replace(family[3][200], **{field: value})
    with pytest.raises(peer.PeerIdentityError, match="CONSULT_CHILD_IDENTITY_UNAVAILABLE"):
        check(family)


@pytest.mark.parametrize("field,value", [
    ("writer_start_identity", "reused-pid"), ("writer_boot_id", "old-boot"),
    ("writer_pgid", 101),
])
def test_stale_runtime_process_facts_refuse(family, field, value):
    with pytest.raises(peer.PeerIdentityError, match="CONSULT_PARENT_WRITER_MISMATCH"):
        check(family, **{field: value})


@pytest.mark.parametrize("pid,field,value", [
    (200, "parent_pid", 101), (100, "effective_uid", 501), (100, "real_uid", 0),
])
def test_wrong_immediate_parent_or_writer_principal_refuses(family, pid, field, value):
    family[2][pid] = replace(family[2][pid], **{field: value})
    with pytest.raises(peer.PeerIdentityError, match="CONSULT_PARENT_WRITER_MISMATCH"):
        check(family)


def test_equal_pid_cannot_substitute_for_parent_unique_id(family):
    family[3][100] = replace(family[3][100], unique_id=9999)
    with pytest.raises(peer.PeerIdentityError, match="CONSULT_PARENT_WRITER_MISMATCH"):
        check(family)


@pytest.mark.parametrize("pid,field,value", [
    (200, "parent_unique_id", 9999), (200, "pidversion", 21),
    (100, "unique_id", 9999), (100, "pidversion", 11),
])
def test_instance_rotation_during_check_refuses(monkeypatch, family, pid, field, value):
    counts = {}
    def observe(candidate):
        counts[candidate] = counts.get(candidate, 0) + 1
        original = family[3][candidate]
        return (replace(original, **{field: value})
                if candidate == pid and counts[candidate] == 2 else original)
    monkeypatch.setattr(lineage, "_observe_process_instance", observe)
    with pytest.raises(peer.PeerIdentityError):
        check(family)


def test_socket_change_during_check_refuses(monkeypatch, family):
    calls = 0
    def observe(_):
        nonlocal calls
        calls += 1
        return family[4] if calls < 3 else replace(family[4], pidversion=21)
    monkeypatch.setattr(peer, "_observe_socket", observe)
    with pytest.raises(peer.PeerIdentityError, match="PEER_IDENTITY_CHANGED"):
        check(family)


def test_constructed_capture_is_not_authority(family):
    forged = object.__new__(peer.PeerIdentity)
    with pytest.raises(peer.PeerIdentityError, match="PEER_CAPTURE_PROVENANCE_REQUIRED"):
        lineage.immediate_parent_pid(forged, inspector=family[1])


def test_observer_failure_is_closed_nonsecret(monkeypatch, family):
    def fail(_):
        raise OSError("private credential path")
    monkeypatch.setattr(lineage, "_observe_process_instance", fail)
    with pytest.raises(peer.PeerIdentityError) as caught:
        check(family)
    assert str(caught.value) == "CONSULT_PROCESS_OBSERVATION_UNAVAILABLE"
    assert caught.value.__suppress_context__


@pytest.mark.skipif(sys.platform != "darwin", reason="native Darwin lineage")
def test_real_connected_child_has_current_parent_identity(tmp_path):
    path = str(tmp_path / "p.sock")
    with socket.socket(socket.AF_UNIX) as listener:
        listener.bind(path)
        listener.listen(1)
        listener.settimeout(10)
        child = subprocess.Popen([
            sys.executable, "-I", "-S", "-B", "-c",
            "import socket,sys; s=socket.socket(socket.AF_UNIX); "
            "s.connect(sys.argv[1]); s.recv(1)", path,
        ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            connection, _ = listener.accept()
            with connection:
                captured = peer.capture_peer_identity(connection)
                inspector = ProcessInspector()
                writer = inspector.inspect(os.getpid())
                assert captured.pid == child.pid
                assert lineage.immediate_parent_pid(captured, inspector=inspector) == os.getpid()
                lineage.require_current_writer_parent(
                    captured, writer_pid=os.getpid(), writer_pgid=writer.pgid,
                    writer_start_identity=writer.start_identity,
                    writer_boot_id=inspector.boot_session_id(), inspector=inspector,
                )
                connection.sendall(b"1")
            assert child.wait(timeout=10) == 0
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=10)
            child.stderr.close()


def test_parent_exec_after_child_creation_refuses(family):
    family[3][100] = replace(family[3][100], pidversion=11)
    with pytest.raises(peer.PeerIdentityError, match="CONSULT_PARENT_WRITER_MISMATCH"):
        check(family)


@pytest.mark.parametrize("pid,field,value", [
    (200, "parent_pid", 101), (100, "start_identity", "new-start"),
])
def test_process_observation_rotation_refuses(monkeypatch, family, pid, field, value):
    calls = {}
    def inspect(candidate):
        calls[candidate] = calls.get(candidate, 0) + 1
        original = family[2][candidate]
        return (replace(original, **{field: value})
                if candidate == pid and calls[candidate] == 2 else original)
    monkeypatch.setattr(family[1], "inspect", inspect)
    with pytest.raises(peer.PeerIdentityError, match="CONSULT_PARENT_WRITER_CHANGED"):
        check(family)


def test_boot_rotation_during_check_refuses(monkeypatch, family):
    boots = iter(("boot", "new-boot"))
    monkeypatch.setattr(family[1], "boot_session_id", lambda: next(boots))
    with pytest.raises(peer.PeerIdentityError, match="CONSULT_PARENT_WRITER_CHANGED"):
        check(family)
