from __future__ import annotations

import json
import socket
import threading
from pathlib import Path

import pytest

from control_plane.executive_privileged_action import REQUEST_SCHEMA, STATUS_REQUEST_SCHEMA
from control_plane.executive_privileged_broker import BrokerTrustError, WIRE_RESPONSE_SCHEMA


def _effect_request(*, action: str = "executive.services.start", request_id: str = "req-001") -> dict:
    return {"schema": REQUEST_SCHEMA, "request_id": request_id, "action": action, "args": {}}


def _status_request(*, request_id: str = "req-001") -> dict:
    return {"schema": STATUS_REQUEST_SCHEMA, "request_id": request_id}


def _receipt(**overrides: object) -> dict:
    value = {
        "schema": "mastermind.executive_privileged_action_receipt.v1",
        "request_id": "req-001",
        "request_sha256": "0" * 64,
        "action": "executive.services.start",
        "effect_class": "SERVICE_CONTROL",
        "started_at": "2026-09-14T00:00:00Z",
        "finished_at": "2026-09-14T00:00:01Z",
        "exit_code": 0,
        "outcome": "SUCCEEDED",
        "release_sha": "a" * 40,
        "broker_version": "1",
        "stdout_bytes": 0,
        "stdout_sha256": "0" * 64,
        "stdout_excerpt": "",
        "stderr_bytes": 0,
        "stderr_sha256": "0" * 64,
        "stderr_excerpt": "",
    }
    value.update(overrides)
    return value


def _serve_once(socket_path: Path, respond) -> threading.Event:
    ready = threading.Event()

    def server() -> None:
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(socket_path))
        listener.listen(1)
        ready.set()
        connection, _ = listener.accept()
        with connection:
            data = b""
            while not data.endswith(b"\n"):
                data += connection.recv(4096)
            respond(connection, data)
        listener.close()

    thread = threading.Thread(target=server, daemon=True)
    thread.start()
    assert ready.wait(2)
    return thread


def test_default_socket_path_and_client_timeout() -> None:
    from control_plane import executive_privileged_client as client

    assert client.DEFAULT_SOCKET == Path("/var/run/mastermind-executive/privileged.sock")
    assert client.DEFAULT_CLIENT_TIMEOUT_SECONDS == 660


def test_send_effect_uses_one_newline_delimited_json_frame(short_socket_root: Path) -> None:
    from control_plane import executive_privileged_client as client

    socket_path = short_socket_root / "effect.sock"
    observed = {}

    def respond(connection, data):
        observed["raw"] = data
        connection.sendall(b'{"ok":true,"replayed":false,"receipt":{}}\n')

    thread = _serve_once(socket_path, respond)
    request = _effect_request(request_id="req-wire-001")
    response = client.send_effect(request, socket_path=socket_path)
    thread.join(2)
    assert response["ok"] is True
    frame = observed["raw"]
    assert frame.count(b"\n") == 1
    assert json.loads(frame) == request


def test_send_status_uses_one_newline_delimited_json_frame(short_socket_root: Path) -> None:
    from control_plane import executive_privileged_client as client

    socket_path = short_socket_root / "status.sock"
    observed = {}

    def respond(connection, data):
        observed["raw"] = data
        connection.sendall(
            b'{"ok":true,"query":true,"status":"NOT_FOUND","request_id":"req-status-001",'
            b'"installed_release_sha":"' + b"a" * 40 + b'"}\n'
        )

    thread = _serve_once(socket_path, respond)
    request = _status_request(request_id="req-status-001")
    response = client.send_status(request, socket_path=socket_path)
    thread.join(2)
    assert response["ok"] is True
    assert response["status"] == "NOT_FOUND"
    frame = observed["raw"]
    assert frame.count(b"\n") == 1
    assert json.loads(frame) == request


def test_send_effect_raises_on_transport_loss_without_retry(short_socket_root: Path) -> None:
    from control_plane import executive_privileged_client as client

    socket_path = short_socket_root / "drop.sock"
    observed = []

    def drop_response(connection, data):
        # Consume the request before closing: exercise response loss, not a
        # scheduler-dependent BrokenPipeError while the client is still sending.
        observed.append(json.loads(data))

    thread = _serve_once(socket_path, drop_response)
    with pytest.raises(RuntimeError, match="closed before a response"):
        client.send_effect(_effect_request(), socket_path=socket_path, timeout_seconds=2)
    thread.join(2)
    assert not thread.is_alive()
    assert observed == [_effect_request()]


def test_send_effect_rejects_response_exceeding_byte_bound(short_socket_root: Path) -> None:
    from control_plane import executive_privileged_client as client

    socket_path = short_socket_root / "big.sock"

    def respond(connection, data):
        oversized = b'{"ok":true,"pad":"' + b"x" * (200 * 1024) + b'"}\n'
        connection.sendall(oversized)

    thread = _serve_once(socket_path, respond)
    with pytest.raises(RuntimeError, match="exceeded the client bound"):
        client.send_effect(_effect_request(), socket_path=socket_path, timeout_seconds=2)
    thread.join(2)


def test_send_effect_rejects_multiple_frames(short_socket_root: Path) -> None:
    from control_plane import executive_privileged_client as client

    socket_path = short_socket_root / "multi.sock"

    def respond(connection, data):
        connection.sendall(b'{"ok":true}\n{"ok":true}\n')

    thread = _serve_once(socket_path, respond)
    with pytest.raises(RuntimeError, match="multiple frames"):
        client.send_effect(_effect_request(), socket_path=socket_path, timeout_seconds=2)
    thread.join(2)


def test_validate_effect_response_correlates_id_digest_action_release() -> None:
    from control_plane import executive_privileged_client as client
    from control_plane.executive_privileged_action import canonical_request_bytes, validate_request
    import hashlib

    request = _effect_request(request_id="req-corr-001")
    digest = hashlib.sha256(canonical_request_bytes(validate_request(request))).hexdigest()
    receipt = _receipt(request_id="req-corr-001", request_sha256=digest, action="executive.services.start")
    response = {"schema": WIRE_RESPONSE_SCHEMA, "ok": True, "replayed": False, "receipt": receipt}

    validated = client.validate_effect_response(response, request, expected_release_sha="a" * 40)
    assert validated["receipt"]["outcome"] == "SUCCEEDED"


def test_validate_effect_response_rejects_uncorrelated_receipt() -> None:
    from control_plane import executive_privileged_client as client

    request = _effect_request(request_id="req-bound-001")
    receipt = _receipt(request_id="req-other-001")
    response = {"schema": WIRE_RESPONSE_SCHEMA, "ok": True, "replayed": False, "receipt": receipt}

    with pytest.raises(BrokerTrustError):
        client.validate_effect_response(response, request)


def test_validate_effect_response_accepts_effect_unknown_refusal() -> None:
    from control_plane import executive_privileged_client as client

    request = _effect_request()
    response = {
        "schema": WIRE_RESPONSE_SCHEMA,
        "ok": False,
        "error": "EFFECT_UNKNOWN",
        "detail": "transport ambiguous",
    }
    validated = client.validate_effect_response(response, request)
    assert validated["error"] == "EFFECT_UNKNOWN"


def test_validate_effect_response_rejects_malformed_refusal() -> None:
    from control_plane import executive_privileged_client as client

    request = _effect_request()
    response = {"schema": WIRE_RESPONSE_SCHEMA, "ok": False, "error": "EFFECT_UNKNOWN"}
    with pytest.raises(RuntimeError):
        client.validate_effect_response(response, request)


def test_validate_status_response_terminal() -> None:
    from control_plane import executive_privileged_client as client

    response = {
        "schema": WIRE_RESPONSE_SCHEMA,
        "ok": True,
        "query": True,
        "status": "TERMINAL",
        "request_id": "req-001",
        "installed_release_sha": "a" * 40,
        "receipt": _receipt(),
    }
    validated = client.validate_status_response(response, expected_request_id="req-001")
    assert validated["status"] == "TERMINAL"


@pytest.mark.parametrize("status", ["EFFECT_UNKNOWN", "NOT_FOUND"])
def test_validate_status_response_non_terminal_statuses(status: str) -> None:
    from control_plane import executive_privileged_client as client

    response = {
        "schema": WIRE_RESPONSE_SCHEMA,
        "ok": True,
        "query": True,
        "status": status,
        "request_id": "req-001",
        "installed_release_sha": "a" * 40,
    }
    if status == "EFFECT_UNKNOWN":
        response["marker_release_sha"] = "b" * 40
    validated = client.validate_status_response(response, expected_request_id="req-001")
    assert validated["status"] == status


@pytest.mark.parametrize(
    "response",
    [
        {"ok": True, "query": True, "status": "NOT_FOUND", "request_id": "req-001", "installed_release_sha": "a" * 40},
        {
            "schema": WIRE_RESPONSE_SCHEMA,
            "ok": True,
            "query": True,
            "status": "NOT_FOUND",
            "request_id": "other-001",
            "installed_release_sha": "a" * 40,
        },
        {
            "schema": WIRE_RESPONSE_SCHEMA,
            "ok": True,
            "query": True,
            "status": "MADE_UP",
            "request_id": "req-001",
            "installed_release_sha": "a" * 40,
        },
        {
            "schema": WIRE_RESPONSE_SCHEMA,
            "ok": True,
            "query": True,
            "status": "TERMINAL",
            "request_id": "req-001",
            "installed_release_sha": "a" * 40,
            "receipt": {"request_id": "other-001", "outcome": "SUCCEEDED", "exit_code": 0},
        },
    ],
)
def test_validate_status_response_rejects_malformed_or_ambiguous(response: dict) -> None:
    from control_plane import executive_privileged_client as client

    with pytest.raises(RuntimeError):
        client.validate_status_response(response, expected_request_id="req-001")


def test_send_effect_has_no_caller_selectable_socket_positional() -> None:
    from control_plane import executive_privileged_client as client

    with pytest.raises(TypeError):
        client.send_effect(_effect_request(), "/tmp/should-not-be-positional")


@pytest.mark.parametrize("operation", ["send_effect", "send_status"])
@pytest.mark.parametrize("failed_stage", ["send", "receive"])
def test_transport_failure_never_reconnects_or_resends(monkeypatch, operation, failed_stage):
    from control_plane import executive_privileged_client as client

    calls = []
    failure = BrokenPipeError("send lost") if failed_stage == "send" else ConnectionResetError("response lost")

    class FailedConnection:
        def settimeout(self, value):
            calls.append("timeout")
        def connect(self, path):
            calls.append("connect")
        def sendall(self, payload):
            calls.append("send")
            if failed_stage == "send":
                raise failure
        def recv(self, size):
            calls.append("receive")
            raise failure
        def close(self):
            calls.append("close")

    def make_connection(*args):
        calls.append("socket")
        return FailedConnection()

    monkeypatch.setattr(client.socket, "socket", make_connection)
    request = _effect_request() if operation == "send_effect" else _status_request()
    with pytest.raises(type(failure)) as caught:
        getattr(client, operation)(request)
    assert caught.value is failure
    expected = ["socket", "timeout", "connect", "send"]
    if failed_stage == "receive":
        expected.append("receive")
    assert calls == expected + ["close"]
