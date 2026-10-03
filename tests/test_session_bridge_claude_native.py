"""Claude Code native cross-session target and transport tests."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import socket
import stat
import tempfile

import pytest

from integrations.session_bridge.claude_native import (
    ClaudeNativeAttentionClient,
    ClaudeNativeTarget,
    ClaudeNativeTargetProjector,
    ClaudeProcessObservation,
)
from integrations.session_bridge.native_wire import AttentionReference
from integrations.session_bridge.schemas import BridgeError

SESSION = "f71c3451-edd7-4e88-93d8-1fe483eac293"
OTHER = "11111111-2222-4333-8444-555555555555"
REF = AttentionReference(
    operation_key="claude-native-op-001",
    message_key="asd-executive-request-001",
)


class Facts:
    def __init__(self, values):
        self.values = dict(values)
        self.calls = []

    def __call__(self, pid: int):
        self.calls.append(pid)
        return self.values.get(pid)


def process(pid: int, executable: Path, session_id: str = SESSION, *, started="Fri Oct  2 00:26:22 2026"):
    return ClaudeProcessObservation(
        pid=pid,
        uid=os.geteuid(),
        process_start=started,
        executable=str(executable.resolve()),
        argv=(str(executable.resolve()), "--output-format", "stream-json", f"--resume={session_id}"),
    )


class SocketFixture:
    def __init__(self, root: Path, pid: int):
        self.root = root
        self.pid = pid
        self.path = root / f"{pid}.sock"
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(str(self.path))
        os.chmod(self.path, 0o600)
        self.server.listen(1)

    def close(self):
        self.server.close()
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


@pytest.fixture
def native(tmp_path: Path):
    root = tmp_path / "cc-socks"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    binroot = tmp_path / "allowed"
    binroot.mkdir()
    executable = binroot / "claude"
    executable.write_text("#!/bin/sh\n")
    executable.chmod(0o700)
    session_root = tmp_path / "sessions"
    session_root.mkdir(mode=0o700)
    sock = SocketFixture(root, 49451)
    facts = Facts({49451: process(49451, executable)})
    projector = ClaudeNativeTargetProjector(
        socket_root=root,
        session_root=session_root,
        allowed_executable_roots=(binroot,),
        process_observer=facts,
        uid=os.geteuid(),
    )
    try:
        yield root, binroot, executable, sock, facts, projector
    finally:
        sock.close()


def test_projector_returns_generation_bound_exact_uuid_target(native):
    _root, _binroot, executable, sock, facts, projector = native
    targets = projector.list_targets()
    assert len(targets) == 1
    target = targets[0]
    assert target.session_id == SESSION
    assert target.pid == 49451
    assert target.executable == str(executable.resolve())
    assert target.socket_path == str(sock.path)
    assert target.target_ref.startswith("claude:")
    assert target.socket_inode == sock.path.stat().st_ino
    assert projector.resolve(target.target_ref) == target
    assert facts.calls == [49451, 49451]


@pytest.mark.parametrize("argv", [
    ("claude", "--output-format", "stream-json"),
    ("claude", "--resume", "not-a-uuid"),
    ("claude", f"--resume={SESSION}", f"--resume={OTHER}"),
])
def test_projector_omits_socket_without_one_exact_resume_uuid(native, argv):
    _root, _binroot, executable, _sock, facts, projector = native
    facts.values[49451] = ClaudeProcessObservation(
        pid=49451, uid=os.geteuid(), process_start="Fri Oct  2 00:26:22 2026",
        executable=str(executable.resolve()), argv=(str(executable.resolve()), *argv[1:]),
    )
    assert projector.list_targets() == []


def test_projector_rejects_stale_socket_pid(native):
    _root, _binroot, _executable, _sock, facts, projector = native
    facts.values.clear()
    assert projector.list_targets() == []


def test_projector_rejects_executable_outside_host_allowlist(native, tmp_path):
    _root, _binroot, _executable, _sock, facts, projector = native
    other = tmp_path / "other-claude"
    other.write_text("x")
    other.chmod(0o700)
    facts.values[49451] = process(49451, other)
    assert projector.list_targets() == []


def test_projector_rejects_socket_root_permissions(native):
    root, _binroot, _executable, _sock, _facts, projector = native
    os.chmod(root, 0o755)
    with pytest.raises(BridgeError) as error:
        projector.list_targets()
    assert error.value.code == "native_unavailable"


def test_projector_rejects_socket_owner_or_mode(native):
    _root, _binroot, _executable, sock, _facts, projector = native
    os.chmod(sock.path, 0o666)
    assert projector.list_targets() == []


def test_target_ref_changes_with_process_generation(native):
    _root, _binroot, executable, _sock, facts, projector = native
    first = projector.list_targets()[0]
    facts.values[49451] = process(49451, executable, started="Fri Oct  2 00:26:23 2026")
    second = projector.list_targets()[0]
    assert first.session_id == second.session_id
    assert first.target_ref != second.target_ref


def test_resolve_refuses_target_when_binding_rotated(native):
    _root, _binroot, executable, _sock, facts, projector = native
    first = projector.list_targets()[0]
    facts.values[49451] = process(49451, executable, started="Fri Oct  2 00:26:23 2026")
    with pytest.raises(BridgeError) as error:
        projector.resolve(first.target_ref)
    assert error.value.code == "native_target_stale"


def test_native_client_writes_one_documented_user_frame(native):
    _root, _binroot, _executable, sock, _facts, projector = native
    target = projector.list_targets()[0]
    client = ClaudeNativeAttentionClient(projector, target=target, timeout_seconds=1.0)

    async def exercise():
        task = asyncio.create_task(client.deliver(REF))
        conn, _ = await asyncio.to_thread(sock.server.accept)
        try:
            raw = await asyncio.to_thread(conn.recv, 8192)
        finally:
            conn.close()
        return await task, raw

    result, raw = asyncio.run(exercise())
    assert raw.endswith(b"\n")
    frame = json.loads(raw)
    assert frame["type"] == "user"
    assert frame["message"]["role"] == "user"
    text = frame["message"]["content"]
    assert "asd-executive-request-001" in text
    assert "claude-native-op-001" in text
    assert "grants no permissions" in text.lower()
    assert set(frame) == {"type", "message"}
    assert set(frame["message"]) == {"role", "content"}
    assert result == {
        "state": "TRANSPORT_WRITTEN",
        "target_ref": target.target_ref,
        "session_id": SESSION,
        "target_consumed": False,
        "parent_consumed": False,
    }


def test_native_client_never_sends_auth_secret(native):
    _root, _binroot, _executable, sock, _facts, projector = native
    target = projector.list_targets()[0]
    client = ClaudeNativeAttentionClient(projector, target=target, timeout_seconds=1.0)

    async def exercise():
        task = asyncio.create_task(client.deliver(REF))
        conn, _ = await asyncio.to_thread(sock.server.accept)
        try:
            raw = await asyncio.to_thread(conn.recv, 8192)
        finally:
            conn.close()
        return await task, raw

    _result, raw = asyncio.run(exercise())
    assert b'"type":"auth"' not in raw
    assert b"CLAUDE_CODE_MESSAGING_TOKEN" not in raw


def test_client_revalidates_full_target_before_connect(native):
    _root, _binroot, executable, sock, facts, projector = native
    target = projector.list_targets()[0]
    facts.values[49451] = process(49451, executable, started="Fri Oct  2 00:26:23 2026")
    client = ClaudeNativeAttentionClient(projector, target=target, timeout_seconds=0.2)
    with pytest.raises(BridgeError) as error:
        asyncio.run(client.deliver(REF))
    assert error.value.code == "native_target_stale"
    sock.server.settimeout(0.05)
    with pytest.raises(TimeoutError):
        sock.server.accept()


def test_connect_failure_is_definitive_pre_effect(native):
    _root, _binroot, _executable, sock, _facts, projector = native
    target = projector.list_targets()[0]
    sock.close()
    client = ClaudeNativeAttentionClient(projector, target=target, timeout_seconds=0.2)
    with pytest.raises(BridgeError) as error:
        asyncio.run(client.deliver(REF))
    assert error.value.code in {"native_target_stale", "native_unavailable"}


class PartialSendSocket:
    def __init__(self):
        self.connected = False
        self.closed = False

    def settimeout(self, _value):
        return None

    def connect(self, _path):
        self.connected = True

    def sendall(self, _payload):
        raise BrokenPipeError("lost after possible partial write")

    def close(self):
        self.closed = True


def test_send_failure_after_connect_is_effect_unknown(native):
    _root, _binroot, _executable, _sock, _facts, projector = native
    target = projector.list_targets()[0]
    fake = PartialSendSocket()
    client = ClaudeNativeAttentionClient(
        projector, target=target, timeout_seconds=0.2,
        socket_factory=lambda: fake,
    )
    with pytest.raises(BridgeError) as error:
        asyncio.run(client.deliver(REF))
    assert error.value.code == "native_effect_unknown"
    assert fake.connected is True and fake.closed is True
    assert "partial" not in str(error.value)


def test_client_has_no_retry_or_fallback_state(native):
    _root, _binroot, _executable, _sock, _facts, projector = native
    target = projector.list_targets()[0]
    client = ClaudeNativeAttentionClient(projector, target=target, timeout_seconds=0.2)
    assert not hasattr(client, "retry")
    assert not hasattr(client, "fallback")
    assert not hasattr(client, "operation_store")


def test_projector_uses_provider_session_metadata_when_resume_is_not_in_process_argv(
    native, tmp_path
):
    root, binroot, executable, sock, facts, _projector = native
    sessions = tmp_path / "provider-sessions"
    sessions.mkdir(mode=0o700)
    metadata = {
        "pid": 49451,
        "sessionId": SESSION,
        "messagingSocketPath": str(sock.path),
        "status": "idle",
        "version": "2.1.284",
    }
    (sessions / "49451.json").write_text(json.dumps(metadata))
    os.chmod(sessions, 0o700)
    os.chmod(sessions / "49451.json", 0o600)

    facts.values[49451] = ClaudeProcessObservation(
        pid=49451,
        uid=os.geteuid(),
        process_start="Fri Oct  2 00:26:22 2026",
        executable=str(executable.resolve()),
        argv=(str(executable.resolve()), "--output-format", "stream-json"),
    )
    projector = ClaudeNativeTargetProjector(
        socket_root=root,
        session_root=sessions,
        allowed_executable_roots=(binroot,),
        process_observer=facts,
        uid=os.geteuid(),
    )

    targets = projector.list_targets()
    assert len(targets) == 1
    assert targets[0].session_id == SESSION
    assert targets[0].socket_path == str(sock.path)


def test_projector_requires_explicit_host_socket_root(native):
    _root, binroot, _executable, _sock, facts, _projector = native
    with pytest.raises(TypeError):
        ClaudeNativeTargetProjector(
            allowed_executable_roots=(binroot,),
            process_observer=facts,
            uid=os.geteuid(),
        )


def test_projector_requires_explicit_provider_session_root(native):
    root, binroot, _executable, _sock, facts, _projector = native
    with pytest.raises(TypeError):
        ClaudeNativeTargetProjector(
            socket_root=root,
            allowed_executable_roots=(binroot,),
            process_observer=facts,
            uid=os.geteuid(),
        )
