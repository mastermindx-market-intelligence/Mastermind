from __future__ import annotations

import hashlib
import json
import socket
import threading
from pathlib import Path

import pytest

from control_plane.executive_privileged_action import (
    REQUEST_SCHEMA,
    STATUS_REQUEST_SCHEMA,
    canonical_request_bytes,
    validate_request,
)
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


def _correlated_receipt(**overrides: object) -> dict:
    request = _effect_request()
    digest = hashlib.sha256(canonical_request_bytes(validate_request(request))).hexdigest()
    receipt = _receipt(request_sha256=digest)
    receipt.update(overrides)
    return receipt


def test_client_validates_bounded_excerpts_and_rejects_nonlegacy_oversize() -> None:
    from control_plane import executive_privileged_client as client

    marker = "...[truncated]"
    valid_receipt = _correlated_receipt(stdout_excerpt="s" * 286 + marker)
    valid_response = {
        "schema": WIRE_RESPONSE_SCHEMA,
        "ok": True,
        "replayed": False,
        "receipt": valid_receipt,
    }
    validated = client.validate_effect_response(valid_response, _effect_request())
    assert validated["receipt"]["stdout_excerpt"] == "s" * 286 + marker

    invalid_receipts = [
        _correlated_receipt(stdout_excerpt="s" * 301),
        _correlated_receipt(stdout_excerpt="s" * 313 + marker),
        _correlated_receipt(stdout_excerpt="s" * 314 + marker),
        _correlated_receipt(stdout_excerpt="s" * 300 + "...[truncatex]"),
        _correlated_receipt(stdout_excerpt="s" * 315 + marker),
    ]
    for receipt in invalid_receipts:
        response = {**valid_response, "receipt": receipt}
        with pytest.raises(BrokerTrustError, match="stdout_excerpt is invalid"):
            client.validate_effect_response(response, _effect_request())


def test_client_status_accepts_exact_legacy_314_receipt_across_release() -> None:
    from control_plane import executive_privileged_client as client

    marker = "...[truncated]"
    receipt = _correlated_receipt(
        release_sha="f" * 40,
        stdout_excerpt="o" * 300 + marker,
        stderr_excerpt="e" * 300 + marker,
    )
    response = {
        "schema": WIRE_RESPONSE_SCHEMA,
        "ok": True,
        "query": True,
        "status": "TERMINAL",
        "request_id": "req-001",
        "installed_release_sha": "a" * 40,
        "receipt": receipt,
    }

    validated = client.validate_status_response(response, expected_request_id="req-001")

    assert validated["receipt"]["release_sha"] == "f" * 40
    assert validated["receipt"]["stdout_excerpt"] == "o" * 300 + marker
    assert validated["receipt"]["stderr_excerpt"] == "e" * 300 + marker


# Aggregate deadline regression probes use deterministic clocks and sockets.
from types import SimpleNamespace
import json
import pytest
from control_plane import executive_privileged_client as client

@pytest.fixture
def rig(monkeypatch):
    now = [1_000_000_000]
    events = []
    steps = {}
    chunks = [b'{"ok":true}\n']
    errors = {}
    class Connection:
        timeout = 15
        def gettimeout(self):
            return self.timeout
        def step(self, name):
            events.append(name)
            now[0] += steps.get(name, 0)
            if name in errors:
                raise errors[name]
        def settimeout(self, value):
            if value < 0:
                raise ValueError("Timeout value out of range")
            self.timeout = value
            events.append(('timeout', value))
        def connect(self, path):
            assert path == str(client.DEFAULT_SOCKET)
            self.step('connect')
        def getpeereid(self):
            self.step('peer')
            return (0, 0)
        def sendall(self, raw):
            assert raw == b'{"operation":"fixture"}\n'
            self.step('send')
        def recv(self, size):
            assert 0 < size <= 4096
            self.step('recv')
            return chunks.pop(0)
        def close(self):
            self.step('close')
    connection = Connection()
    def make_socket(*args):
        events.append('socket')
        return connection
    monkeypatch.setattr(client.socket, 'socket', make_socket)
    monkeypatch.setattr(client, 'time', SimpleNamespace(monotonic_ns=lambda: now[0]), raising=False)
    def send(**kw):
        return client._send_one_frame({'operation':'fixture'}, socket_path=client.DEFAULT_SOCKET,
                                      timeout_seconds=15, require_root_peer=True, **kw)
    return SimpleNamespace(now=now, events=events, steps=steps, chunks=chunks,
                           errors=errors, send=send, connection=connection,
                           end=now[0]+15_000_000_000)

@pytest.mark.parametrize('bad', [True,False,0,-1,1.0,'2',[],type('IntSubclass',(int,),{})(3)])
def test_invalid_endpoint_before_socket(rig,bad):
    with pytest.raises((TypeError,ValueError)):
        rig.send(deadline_monotonic_ns=bad)
    assert rig.events == []

@pytest.mark.parametrize('delta', [0,-1])
def test_expired_endpoint_before_socket(rig,delta):
    with pytest.raises(TimeoutError):
        rig.send(deadline_monotonic_ns=rig.now[0]+delta)
    assert rig.events == []


def test_slow_drip_does_not_replenish_budget(rig):
    rig.chunks[:] = [b'{',b'"ok"',b':',b'true',b'}\n']
    rig.steps['recv'] = 4_000_000_000
    with pytest.raises(TimeoutError):rig.send(deadline_monotonic_ns=rig.end)
    assert rig.events.count('socket') == rig.events.count('connect') == rig.events.count('send') == 1
    assert rig.events.count('recv') == 4
    assert rig.events.count('close') == 1
    waits=[x[1] for x in rig.events if isinstance(x,tuple)]
    assert waits == sorted(waits,reverse=True)
    assert waits[-1] <= 3


def test_cumulative_phases_refuse_late_response(rig):
    rig.steps.update(connect=3_000_000_000,peer=4_000_000_000,send=4_000_000_000,recv=5_000_000_000)
    with pytest.raises(TimeoutError):rig.send(deadline_monotonic_ns=rig.end)
    assert rig.events.count('socket') == rig.events.count('connect') == rig.events.count('send') == 1
    assert rig.events.count('close') == 1


def test_peer_observation_expiry_prevents_send(rig):
    rig.steps['peer']=15_000_000_000
    with pytest.raises(TimeoutError):rig.send(deadline_monotonic_ns=rig.end)
    assert 'send' not in rig.events
    assert rig.events.count('close') == 1


@pytest.mark.parametrize('stage',['close','parse'])
def test_success_crossing_final_boundary_is_rejected(rig,monkeypatch,stage):
    if stage=='close':rig.steps['close']=15_000_000_000
    else:
        def late_parse(raw):
            value=json.loads(raw)
            rig.now[0]=rig.end
            return value
        monkeypatch.setattr(client,'json',SimpleNamespace(loads=late_parse,dumps=json.dumps))
    with pytest.raises(TimeoutError):rig.send(deadline_monotonic_ns=rig.end)
    assert rig.events.count('send') == rig.events.count('close') == 1


@pytest.mark.parametrize('stage',['connect','peer','send','recv'])
def test_primary_error_identity_survives_close_failure_and_expiry(rig,stage):
    error=RuntimeError('primary '+stage)
    rig.errors[stage]=error
    rig.errors['close']=OSError('secondary close failure')
    rig.steps['close']=15_000_000_000
    with pytest.raises(RuntimeError) as caught:rig.send(deadline_monotonic_ns=rig.end)
    assert caught.value is error
    assert rig.events.count('close') == 1
    assert rig.events.count('socket') == 1


def test_direct_response_expiry_before_receive(rig):
    with pytest.raises(TimeoutError):
        client._read_response(rig.connection,deadline_monotonic_ns=rig.now[0])
    assert 'recv' not in rig.events


def test_success_and_legacy_without_clock(rig,monkeypatch):
    assert rig.send(deadline_monotonic_ns=rig.end)=={'ok':True}
    assert rig.events.count('send')==rig.events.count('close')==1
    for options in ({},{'deadline_monotonic_ns':None}):
        rig.events.clear();rig.chunks[:]=[b'{"ok":true}\n']
        def no_clock():raise AssertionError('legacy clock read')
        monkeypatch.setattr(client,'time',SimpleNamespace(monotonic_ns=no_clock))
        assert rig.send(**options)=={'ok':True}
        assert rig.events==['socket',('timeout',15),'connect','peer','send','recv','close']


def test_successful_close_failure_is_not_retried(rig):
    error = OSError("close failed")
    rig.errors["close"] = error
    with pytest.raises(OSError) as caught:
        rig.send(deadline_monotonic_ns=rig.end)
    assert caught.value is error
    assert rig.events.count("close") == 1


@pytest.mark.parametrize("local_limit", [0, 0.25, 2])
def test_aggregate_deadline_never_enlarges_existing_socket_timeout(rig, local_limit):
    result = client._send_one_frame(
        {"operation": "fixture"}, socket_path=client.DEFAULT_SOCKET,
        timeout_seconds=local_limit, require_root_peer=True,
        deadline_monotonic_ns=rig.end)
    assert result == {"ok": True}
    waits = [event[1] for event in rig.events if isinstance(event, tuple)]
    assert waits and all(wait == local_limit for wait in waits)
    assert rig.events.count("send") == 1


def test_invalid_local_socket_limit_refuses_before_connect(rig):
    with pytest.raises(ValueError):
        client._send_one_frame(
            {"operation": "fixture"}, socket_path=client.DEFAULT_SOCKET,
            timeout_seconds=-1, deadline_monotonic_ns=rig.end)
    assert "connect" not in rig.events and "send" not in rig.events
    assert rig.events.count("close") == 1


def test_large_positive_endpoint_is_clamped_before_float_conversion(rig):
    assert rig.send(deadline_monotonic_ns=10 ** 1000) == {"ok": True}
    waits = [event[1] for event in rig.events if isinstance(event, tuple)]
    assert waits and all(wait == 15 for wait in waits)


def test_serialization_consumes_aggregate_budget_before_socket(rig, monkeypatch):
    def late_encode(*args, **kwargs):
        result = json.dumps(*args, **kwargs)
        rig.now[0] = rig.end
        return result
    monkeypatch.setattr(client, "json", SimpleNamespace(dumps=late_encode, loads=json.loads))
    with pytest.raises(TimeoutError):
        rig.send(deadline_monotonic_ns=rig.end)
    assert rig.events == []


def test_deadline_validated_before_serialization(rig, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("invalid endpoint reached serialization")
    monkeypatch.setattr(client, "json", SimpleNamespace(dumps=unexpected))
    with pytest.raises(TypeError):
        rig.send(deadline_monotonic_ns=True)
    assert rig.events == []
