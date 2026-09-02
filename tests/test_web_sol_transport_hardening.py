from __future__ import annotations

from dataclasses import is_dataclass
import io
import os
from pathlib import Path
import shutil
import socket
import struct
import tempfile
import threading
import time

import pytest

from integrations.chairman_surfaces import web_sol_client as client
from integrations.chairman_surfaces import web_sol_native_host as native
from integrations.chairman_surfaces import web_sol_protocol as wsp


INSTANCE_ID = "a" * 64
BOOT_NONCE = "boot-nonce-0000000000000001"


def valid_request(action: str = "INSPECT") -> dict:
    return {
        "schema": wsp.ACTION_SCHEMA,
        "binding_id": "11111111-1111-4111-8111-111111111111",
        "conversation_fingerprint": "b" * 64,
        "binding_fingerprint": "c" * 64,
        "action": action,
        "operation_key": "web-sol-t1-transport-hardening-20260901-sol-001",
        "issued_at": "2026-09-01T02:00:00Z",
        "expires_at": "2026-09-01T02:00:30Z",
        "nonce": "nonce-0000000000000001",
    }


def observation() -> dict:
    return {
        "schema": wsp.PROBE_SCHEMA,
        "target_present": True,
        "exact_conversation_loaded": True,
        "page_responsive": True,
        "document_ready_state": "complete",
        "visibility": "visible",
        "composer_available": True,
        "generation_state": "idle",
        "auth_required": False,
        "provider_error_present": False,
    }


def valid_receipt(request: dict) -> dict:
    return {
        "schema": wsp.RECEIPT_SCHEMA,
        "binding_id": request["binding_id"],
        "conversation_fingerprint": request["conversation_fingerprint"],
        "binding_fingerprint": request["binding_fingerprint"],
        "action": request["action"],
        "operation_key": request["operation_key"],
        "nonce": request["nonce"],
        "status": "INSPECTED",
        "observed_at": "2026-09-01T02:00:01Z",
        "observation": observation(),
    }


class Clock:
    def __init__(self, now: float = 0.0):
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class AdvancingReader:
    def __init__(self, chunks: list[bytes], clock: Clock, advances: list[float]):
        self._chunks = iter(chunks)
        self._advances = iter(advances)
        self._clock = clock

    def read(self, _size: int) -> bytes:
        self._clock.advance(next(self._advances, 0.0))
        return next(self._chunks, b"")


class AdvancingWriter:
    def __init__(self, clock: Clock, *, per_write: float, max_chunk: int = 1):
        self.clock = clock
        self.per_write = per_write
        self.max_chunk = max_chunk
        self.writes = 0

    def write(self, payload: bytes) -> int:
        self.writes += 1
        self.clock.advance(self.per_write)
        return min(len(payload), self.max_chunk)

    def flush(self) -> None:
        return None


def test_deadline_is_frozen_monotonic_and_clamps_at_zero():
    assert hasattr(native, "Deadline")
    deadline = native.Deadline(ends_at=10.0)
    assert is_dataclass(deadline)
    assert deadline.remaining(lambda: 7.5) == pytest.approx(2.5)
    assert deadline.remaining(lambda: 11.0) == 0.0
    with pytest.raises(Exception):
        deadline.ends_at = 12.0


def test_partial_header_and_payload_consume_one_deadline():
    payload = b'{"ok":true}'
    framed = struct.pack("@I", len(payload)) + payload

    header_clock = Clock()
    header_reader = AdvancingReader(
        [framed[:2], framed[2:4]],
        header_clock,
        [0.6, 0.6],
    )
    with pytest.raises(native.NativeHostError, match="frame_read_timeout"):
        native.read_frame(
            header_reader,
            deadline=native.Deadline(ends_at=1.0),
            monotonic=header_clock,
        )

    payload_clock = Clock()
    payload_reader = AdvancingReader(
        [framed[:4], framed[4:8], framed[8:]],
        payload_clock,
        [0.1, 0.5, 0.5],
    )
    with pytest.raises(native.NativeHostError, match="frame_read_timeout"):
        native.read_frame(
            payload_reader,
            deadline=native.Deadline(ends_at=1.0),
            monotonic=payload_clock,
        )


def test_stalled_short_writer_consumes_the_same_deadline():
    clock = Clock()
    writer = AdvancingWriter(clock, per_write=0.4, max_chunk=1)
    with pytest.raises(native.NativeHostError, match="frame_write_timeout"):
        native.write_frame(
            writer,
            {"ok": True},
            deadline=native.Deadline(ends_at=1.0),
            monotonic=clock,
        )
    assert writer.writes == 3


def test_client_uses_one_deadline_across_handshake_action_and_receipt(
    monkeypatch,
    tmp_path,
):
    request = valid_request()
    seen = []

    class FakeConnection:
        def settimeout(self, _value):
            return None

        def connect(self, _path):
            return None

        def makefile(self, _mode, buffering=0):
            return io.BytesIO()

        def close(self):
            return None

    monkeypatch.setattr(client, "_private_socket", lambda _path: None)
    monkeypatch.setattr(client.socket, "socket", lambda *_args, **_kwargs: FakeConnection())

    def handshake(_reader, _writer, *, expected_instance_id, deadline, monotonic):
        assert expected_instance_id == INSTANCE_ID
        seen.append(deadline)
        assert callable(monotonic)
        return {}

    def write_frame(_writer, document, *, deadline, monotonic):
        assert document == request
        seen.append(deadline)
        assert callable(monotonic)

    def read_frame(_reader, *, deadline, monotonic):
        seen.append(deadline)
        assert callable(monotonic)
        return valid_receipt(request)

    monkeypatch.setattr(client, "_complete_transport_handshake", handshake)
    monkeypatch.setattr(native, "write_frame", write_frame)
    monkeypatch.setattr(native, "read_frame", read_frame)

    result = client._exchange_web_sol_socket(
        request,
        path=tmp_path / "fixture.sock",
        expected_instance_id=INSTANCE_ID,
        monotonic=lambda: 10.0,
    )
    assert result == valid_receipt(request)
    assert len(seen) == 3
    assert len({id(item) for item in seen}) == 1
    assert seen[0].ends_at == pytest.approx(10.0 + client.SOCKET_TIMEOUT_SECONDS)


def test_complete_foreground_frame_timeout_is_effect_unknown(
    monkeypatch,
    tmp_path,
):
    request = valid_request(action="FOREGROUND")
    clock = Clock()

    class CompleteThenLateWriter:
        def __init__(self):
            self.payloads: list[bytes] = []

        def write(self, payload: bytes) -> int:
            material = bytes(payload)
            self.payloads.append(material)
            clock.advance(client.SOCKET_TIMEOUT_SECONDS + 0.1)
            return len(material)

        def flush(self) -> None:
            return None

        def close(self) -> None:
            return None

    reader = io.BytesIO()
    writer = CompleteThenLateWriter()

    class FakeConnection:
        def settimeout(self, _value):
            return None

        def connect(self, _path):
            return None

        def makefile(self, mode, buffering=0):
            assert buffering == 0
            return reader if mode == "rb" else writer

        def close(self):
            return None

    monkeypatch.setattr(client, "_private_socket", lambda _path: None)
    monkeypatch.setattr(client.socket, "socket", lambda *_args, **_kwargs: FakeConnection())
    monkeypatch.setattr(
        client,
        "_complete_transport_handshake",
        lambda *_args, **_kwargs: {},
    )

    with pytest.raises(client.WebSolExtensionError) as caught:
        client._exchange_web_sol_socket(
            request,
            path=tmp_path / "fixture.sock",
            expected_instance_id=INSTANCE_ID,
            monotonic=clock,
        )

    assert caught.value.code == "foreground_effect_unknown"
    assert isinstance(caught.value.__cause__, native.NativeHostError)
    assert caught.value.__cause__.code == "frame_write_timeout"
    assert b"".join(writer.payloads) == native.encode_frame(request)


def test_guarded_client_isolates_malformed_peer_and_refuses_concurrent_peer(
    monkeypatch,
):
    assert hasattr(native, "_serve_guarded_client")
    action_gate = threading.Lock()
    calls = []

    def malformed(*_args, **_kwargs):
        calls.append("malformed")
        raise native.NativeHostError("frame_invalid_json")

    monkeypatch.setattr(native, "_serve_client", malformed)
    server_one, peer_one = socket.socketpair()
    try:
        outcome = native._serve_guarded_client(
            server_one,
            object(),
            object(),
            timeout_seconds=1.0,
            expected_instance_id=INSTANCE_ID,
            boot_nonce=BOOT_NONCE,
            action_gate=action_gate,
        )
        assert outcome == "client_refused"
        assert calls == ["malformed"]
        assert action_gate.acquire(blocking=False)
        action_gate.release()
    finally:
        peer_one.close()

    action_gate.acquire()
    server_two, peer_two = socket.socketpair()
    try:
        outcome = native._serve_guarded_client(
            server_two,
            object(),
            object(),
            timeout_seconds=1.0,
            expected_instance_id=INSTANCE_ID,
            boot_nonce=BOOT_NONCE,
            action_gate=action_gate,
        )
        assert outcome == "adapter_busy"
        peer_two.settimeout(0.5)
        assert peer_two.recv(1) == b""
        assert calls == ["malformed"]
    finally:
        action_gate.release()
        peer_two.close()


def test_close_unlinks_only_the_exact_socket_inode_this_server_created(tmp_path):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    os.chmod(private, 0o700)
    destination = private / "web_sol.sock"
    displaced = private / "web_sol.original.sock"

    original = native.open_private_server(destination, owner_uid=os.getuid())
    destination.rename(displaced)
    replacement = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    replacement.bind(os.fspath(destination))
    os.chmod(destination, 0o600)
    replacement.listen(1)
    replacement_identity = destination.lstat()

    try:
        native.close_private_server(original, destination, owner_uid=os.getuid())
        current = destination.lstat()
        assert (current.st_dev, current.st_ino) == (
            replacement_identity.st_dev,
            replacement_identity.st_ino,
        )
        assert displaced.exists()
    finally:
        replacement.close()
        destination.unlink(missing_ok=True)
        displaced.unlink(missing_ok=True)


def test_private_server_refuses_overlong_unix_socket_path_before_bind(tmp_path):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    os.chmod(private, 0o700)
    destination = private / ("x" * 180)
    with pytest.raises(native.NativeHostError, match="socket_path_too_long"):
        native.open_private_server(destination, owner_uid=os.getuid())
    assert not destination.exists()


@pytest.fixture
def short_socket_root():
    # Keep the test-owned AF_UNIX root below Darwin's fixed 104-byte limit;
    # pytest's nested tmp_path can exceed the production path budget.
    value = Path(tempfile.mkdtemp(prefix="mmx-wsx-t1-", dir="/tmp"))
    os.chmod(value, 0o700)
    try:
        yield value
    finally:
        shutil.rmtree(value, ignore_errors=True)


def _run_host_with_partial_unsolicited_frame(
    monkeypatch,
    short_socket_root: Path,
    material: bytes,
) -> tuple[bool, list[BaseException], float]:
    private = short_socket_root
    destination = native.wsi.socket_path(INSTANCE_ID, root=private)
    read_fd, write_fd = os.pipe()
    chrome_in = os.fdopen(read_fd, "rb", buffering=0)
    errors: list[BaseException] = []
    monkeypatch.setattr(
        native,
        "complete_server_handshake",
        lambda *_args, **_kwargs: {},
    )
    os.write(write_fd, material)

    def run() -> None:
        try:
            native.run_native_host(
                chrome_in,
                io.BytesIO(),
                caller_origin=native.ALLOWED_EXTENSION_ORIGIN,
                expected_instance_id=INSTANCE_ID,
                socket_root=private,
                owner_uid=os.getuid(),
                action_timeout_seconds=0.1,
                boot_nonce_factory=lambda: BOOT_NONCE,
            )
        except BaseException as exc:
            errors.append(exc)

    worker = threading.Thread(target=run, daemon=True)
    started = time.monotonic()
    worker.start()
    worker.join(0.75)
    exceeded_deadline = worker.is_alive()
    try:
        os.close(write_fd)
    except OSError:
        pass
    worker.join(2.0)
    elapsed = time.monotonic() - started
    try:
        assert not worker.is_alive()
    finally:
        chrome_in.close()
        if destination.exists():
            os.unlink(destination)
        native._SERVER_SOCKET_IDENTITIES.clear()
    return exceeded_deadline, errors, elapsed


def test_run_native_host_reports_exact_owned_socket_cleanup_failure(
    monkeypatch,
    short_socket_root,
):
    private = short_socket_root
    destination = native.wsi.socket_path(INSTANCE_ID, root=private)
    read_fd, write_fd = os.pipe()
    os.close(write_fd)
    chrome_in = os.fdopen(read_fd, "rb", buffering=0)
    original_unlink = Path.unlink

    def refuse_exact_owned_socket(path: Path, *args, **kwargs):
        if path == destination:
            raise PermissionError("blocked by test")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(
        native,
        "complete_server_handshake",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(Path, "unlink", refuse_exact_owned_socket)
    try:
        with pytest.raises(native.NativeHostError, match="socket_cleanup_failed"):
            native.run_native_host(
                chrome_in,
                io.BytesIO(),
                caller_origin=native.ALLOWED_EXTENSION_ORIGIN,
                expected_instance_id=INSTANCE_ID,
                socket_root=private,
                owner_uid=os.getuid(),
                action_timeout_seconds=0.1,
                boot_nonce_factory=lambda: BOOT_NONCE,
            )
        assert destination.exists()
    finally:
        chrome_in.close()
        if destination.exists():
            os.unlink(destination)
        native._SERVER_SOCKET_IDENTITIES.clear()


def test_failed_open_reports_exact_owned_socket_cleanup_failure(
    monkeypatch,
    short_socket_root,
):
    private = short_socket_root
    destination = private / "open-cleanup.sock"
    original_unlink = Path.unlink
    original_chmod = os.chmod

    def refuse_exact_owned_socket(path: Path, *args, **kwargs):
        if path == destination:
            raise PermissionError("blocked by test")
        return original_unlink(path, *args, **kwargs)

    def fail_post_bind_chmod(path, _mode):
        if Path(path) == destination:
            raise PermissionError("post-bind failure")
        return original_chmod(path, _mode)

    monkeypatch.setattr(Path, "unlink", refuse_exact_owned_socket)
    monkeypatch.setattr(native.os, "chmod", fail_post_bind_chmod)
    try:
        with pytest.raises(native.NativeHostError, match="socket_cleanup_failed"):
            native.open_private_server(destination, owner_uid=os.getuid())
        assert destination.exists()
    finally:
        if destination.exists():
            os.unlink(destination)
        native._SERVER_SOCKET_IDENTITIES.clear()


def test_unsolicited_partial_header_is_bounded_by_action_timeout(
    monkeypatch,
    short_socket_root,
):
    exceeded, errors, elapsed = _run_host_with_partial_unsolicited_frame(
        monkeypatch,
        short_socket_root,
        b"\x08\x00",
    )
    assert not exceeded, f"host exceeded frame deadline ({elapsed:.3f}s)"
    assert len(errors) == 1
    assert isinstance(errors[0], native.ChromeChannelError)
    assert errors[0].code == "frame_read_timeout"


def test_unsolicited_partial_payload_is_bounded_by_action_timeout(
    monkeypatch,
    short_socket_root,
):
    exceeded, errors, elapsed = _run_host_with_partial_unsolicited_frame(
        monkeypatch,
        short_socket_root,
        struct.pack("@I", 8) + b'{"x"',
    )
    assert not exceeded, f"host exceeded frame deadline ({elapsed:.3f}s)"
    assert len(errors) == 1
    assert isinstance(errors[0], native.ChromeChannelError)
    assert errors[0].code == "frame_read_timeout"


def test_clean_chrome_eof_remains_normal_and_removes_exact_socket(
    monkeypatch,
    short_socket_root,
):
    private = short_socket_root
    destination = native.wsi.socket_path(INSTANCE_ID, root=private)
    read_fd, write_fd = os.pipe()
    os.close(write_fd)
    chrome_in = os.fdopen(read_fd, "rb", buffering=0)
    monkeypatch.setattr(
        native,
        "complete_server_handshake",
        lambda *_args, **_kwargs: {},
    )
    try:
        result = native.run_native_host(
            chrome_in,
            io.BytesIO(),
            caller_origin=native.ALLOWED_EXTENSION_ORIGIN,
            expected_instance_id=INSTANCE_ID,
            socket_root=private,
            owner_uid=os.getuid(),
            action_timeout_seconds=0.1,
            boot_nonce_factory=lambda: BOOT_NONCE,
        )
        assert result is None
        assert not destination.exists()
    finally:
        chrome_in.close()
        if destination.exists():
            os.unlink(destination)
        native._SERVER_SOCKET_IDENTITIES.clear()
