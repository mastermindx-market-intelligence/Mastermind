"""Closed native-operation boundaries with explicit native owner doubles.

These do not execute Hermes, a provider, a Linux service, or an Office path.
The wire test uses a real AF_UNIX stream; native authority effects are doubles.
"""
import asyncio
from contextlib import contextmanager
import json
from pathlib import Path
import socket
import sys
import threading
from types import ModuleType, SimpleNamespace

import pytest

from integrations.hermes_runtime import native_session_control as control
from integrations.hermes_runtime.errors import RuntimeRefusal


def module(monkeypatch, name, **members):
    value = ModuleType(name)
    value.__dict__.update(members)
    monkeypatch.setitem(sys.modules, name, value)
    return value


@pytest.fixture
def native(monkeypatch, tmp_path):
    home = tmp_path.resolve()
    target = dict(profile_id=str(home), session_id="owned-session", principal_id="uid:994",
                  instance_id="owner-1", authority_epoch=7, revision=3, execution_generation=2)
    receipt = dict(admission_id="native-admission", ref=dict(profile_id=str(home), session_id="owned-session"),
                   sequence=1, status="queued", outcome=None, authority_epoch=7, execution_generation=None)
    calls, scopes = [], []
    state = SimpleNamespace(changed=False, lose=False, closed=False, transport=None)

    @contextmanager
    def scope(value):
        scopes.append(value)
        try:
            yield
        finally:
            scopes.pop()

    class Transport:
        def __init__(self, stream_getter, lock):
            self.stream_getter, self.lock = stream_getter, lock

        def write(self, obj):
            with self.lock:
                try:
                    self.stream_getter().write(json.dumps(obj))
                    return True
                except BrokenPipeError:
                    return False

        def close(self):
            pass

    class Connection:
        def __init__(self, authority, transport, identity, *, operator):
            assert not operator and identity["user_id"] == target["principal_id"]
            assert identity["profile_scope"] == "profile" and len(scopes) == 2
            assert transport is state.transport
            self.transport = transport

        async def dispatch(self, request):
            calls.append(request)
            assert self.transport.write({"event": "native-ownership-test"})
            if request["method"] == "session.resume":
                value = {k: target[k] for k in ("session_id", "authority_epoch", "revision", "execution_generation")}
                value["stored_session_id"] = target["session_id"]
                if state.changed:
                    value["revision"] += 1
                return {"result": value}
            if state.lose:
                raise TimeoutError("admission response lost")
            return {"result": receipt}

        async def close(self):
            state.closed = True

    def bind(value):
        state.transport = value
        return "original-token"

    def reset(token):
        assert token == "original-token"
        state.reset = True

    grant = dict(subject=target["principal_id"], scope="profile", instance_id=target["instance_id"],
                 profile_id=str(home), capabilities=["session:read", "session:submit"])
    runner = SimpleNamespace(session_authority=object(),
                             session_ticket_store=SimpleNamespace(redeem=lambda *a, **k: grant))
    module(monkeypatch, "gateway.session_controls", AuthorityConnection=Connection)
    module(monkeypatch, "gateway.run_api", _embedded_chat_enabled=lambda: True)
    module(monkeypatch, "gateway.session_authorities", owner_scope=scope)
    module(monkeypatch, "gateway.run_idle_exit", attached_client=scope)
    module(monkeypatch, "tui_gateway.transport", StdioTransport=Transport,
           bind_transport=bind, reset_transport=reset)
    monkeypatch.setattr(control, "_target", lambda *a: dict(target))
    params = dict(target=dict(target), submission_id="operation-1", text="Explain this mission.", ticket="private-ticket")
    return SimpleNamespace(home=home, target=target, receipt=receipt, params=params,
                           runner=runner, calls=calls, state=state, scopes=scopes)


def test_one_native_admission_preserves_receipt_and_cleans_viewer(native):
    result = asyncio.run(control._submit(native.runner, native.home, native.params, "uid:994"))
    assert result == dict(schema=control.SCHEMA, status="ADMITTED", admission=native.receipt)
    assert [call["method"] for call in native.calls] == ["session.resume", "prompt.submit"]
    assert native.calls[-1]["params"] == dict(session_id="owned-session", submission_id="operation-1",
                                             text="Explain this mission.", finite=True)
    assert native.state.closed and native.state.reset and not native.scopes
    assert native.state.transport.write({"late": "native event"}) is False


def test_changed_resume_never_submits(native):
    native.state.changed = True
    result = asyncio.run(control._submit(native.runner, native.home, native.params, "uid:994"))
    assert result["status"] == "NOT_SUBMITTED"
    assert [call["method"] for call in native.calls] == ["session.resume"]
    assert native.state.closed


def test_lost_admission_response_is_unknown_and_never_replayed(native):
    native.state.lose = True
    result = asyncio.run(control._submit(native.runner, native.home, native.params, "uid:994"))
    assert result["status"] == "EFFECT_UNKNOWN"
    assert sum(call["method"] == "prompt.submit" for call in native.calls) == 1
    assert native.state.closed and native.state.reset


def test_receipt_stream_has_a_byte_budget_and_no_retained_transcript():
    stream = control._ReceiptStream()
    stream.write("x" * control.MAX_WIRE_BYTES)
    with pytest.raises(BrokenPipeError):
        stream.write("é")
    assert stream.closed and stream.bytes == control.MAX_WIRE_BYTES
    assert set(vars(stream)) == {"bytes", "closed"}


def test_read_original_missing_is_unknown_and_wrong_principal_refuses(monkeypatch, tmp_path):
    db = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(control, "_db", lambda home: db)
    state = SimpleNamespace(row=None)
    module(monkeypatch, "hermes_state_runtime", find_session_admission=lambda *a, **k: state.row,
           get_session_admission=lambda *a, **k: state.row)
    module(monkeypatch, "gateway.session_results", admission_result=lambda *a: None)
    params = dict(operation="read_original", profile_id=str(tmp_path), session_id="s", submission_id="op",
                  input_sha256=control.input_digest("question"), admission_id=None)
    assert control._read_original(tmp_path, params, "uid:994")["status"] == "EFFECT_UNKNOWN"
    state.row = dict(principal_id="uid:993", target_session_id="s", request_id="op")
    with pytest.raises(RuntimeRefusal, match="NATIVE_SECRETARY_ORIGINAL_MISMATCH"):
        control._read_original(tmp_path, params, "uid:994")


def test_private_wire_uses_one_existing_socket_request(monkeypatch, tmp_path):
    left, right = socket.socketpair()
    requests = []
    def serve():
        with right:
            raw = bytearray()
            while b"\n" not in raw:
                raw.extend(right.recv(65536))
            requests.append(json.loads(raw))
            right.sendall(json.dumps(dict(protocol=1, id=1, ok=True,
                result=dict(schema=control.SCHEMA, status="EFFECT_UNKNOWN"))).encode() + b"\n")
    worker = threading.Thread(target=serve)
    worker.start()
    module(monkeypatch, "hermes_cli.gateway_runtime_discovery", connect_private=lambda *a: left)
    result = control.NativeSecretaryClient(tmp_path).read_original(
        session_id="s", submission_id="op", input_sha256=control.input_digest("question"))
    worker.join(timeout=2)
    assert not worker.is_alive() and result["status"] == "EFFECT_UNKNOWN"
    assert len(requests) == 1 and requests[0]["verb"] == control.VERB
    assert requests[0]["params"]["operation"] == "read_original"
