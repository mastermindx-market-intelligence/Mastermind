"""Closed Secretary wire family and one-shot Control-side client.

These tests prove protocol behavior only.  They do not enroll a host, open a
live provider turn, dispatch a native admission, or attest a deployed
Secretary role.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from control_plane import remote_worker_broker_client as client_module
from control_plane import remote_worker_transport as transport
from control_plane.remote_worker_transport import (
    MAX_SECRETARY_REQUEST_BYTES,
    MAX_SECRETARY_RESPONSE_BYTES,
    REMOTE_HERMES_SECRETARY_REQUEST_SCHEMA,
    REMOTE_HERMES_SECRETARY_RESPONSE_SCHEMA,
    TransportEffect,
    TransportError,
    TransportValidationError,
)

pytestmark = pytest.mark.anyio

HOST_REF = "host-" + "a" * 64
ROOT_ID = "meta-ceo-open-harness-convergence-20261024-sol-001"
BINDING = "b" * 64
IMPLEMENTATION = "c" * 40
SESSION = "session-0001"
OTHER_SESSION = "session-0002"
PEER = b"secretary-transport-fixture-peer"
NATIVE_RESULT_SCHEMA = "mastermind.hermes_secretary_native_control/v1"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _canonical(value) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def _target(session_id: str = SESSION) -> dict:
    return {
        "profile_id": "/tmp/secretary-profile",
        "session_id": session_id,
        "principal_id": "principal-0001",
        "instance_id": "instance-0001",
        "authority_epoch": 3,
        "revision": 7,
        "execution_generation": 2,
    }


def _observe(session_id: str = SESSION) -> dict:
    return {"operation": "observe", "session_id": session_id}


def _submit(session_id: str = SESSION) -> dict:
    return {
        "operation": "submit",
        "target": _target(session_id),
        "submission_id": "submission-0001",
        "text": "one bounded Secretary question",
    }


def _read_original(session_id: str = SESSION) -> dict:
    return {
        "operation": "read_original",
        "session_id": session_id,
        "submission_id": "submission-0001",
        "input_sha256": "d" * 64,
    }


def _native_result(status: str = "ADMITTED", **fields) -> dict:
    return {"schema": NATIVE_RESULT_SCHEMA, "status": status, **fields}


def _request(operation: dict | None = None) -> dict:
    return transport.build_secretary_request(
        HOST_REF, ROOT_ID, BINDING, IMPLEMENTATION, operation or _observe()
    )


class _SSLObject:
    def __init__(self, certificate: bytes = PEER) -> None:
        self.certificate = certificate

    def getpeercert(self, binary_form: bool = False):
        if binary_form:
            return self.certificate
        return {}


class _Reader:
    def __init__(self, data: bytes = b"") -> None:
        self.data = bytearray(data)

    async def readexactly(self, count: int) -> bytes:
        if count > len(self.data):
            partial = bytes(self.data)
            self.data = bytearray()
            raise asyncio.IncompleteReadError(partial, count)
        value = bytes(self.data[:count])
        self.data = self.data[count:]
        return value


class _Writer:
    def __init__(
        self,
        *,
        certificate: bytes = PEER,
        fail_write: bool = False,
        fail_drain: bool = False,
        drain_delay: float = 0.0,
        events: list[str] | None = None,
    ) -> None:
        self.ssl_object = _SSLObject(certificate)
        self.fail_write = fail_write
        self.fail_drain = fail_drain
        self.drain_delay = drain_delay
        self.events = events if events is not None else []
        self.written = bytearray()
        self.closed = False
        self.aborted = False

    def get_extra_info(self, name: str):
        return self.ssl_object if name == "ssl_object" else None

    def write(self, data: bytes) -> None:
        self.events.append("write")
        if self.fail_write:
            raise OSError("private write failure")
        self.written.extend(data)

    async def drain(self) -> None:
        if self.drain_delay:
            await asyncio.sleep(self.drain_delay)
        if self.fail_drain:
            raise OSError("private drain failure")

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None

    @property
    def transport(self):
        return self

    def abort(self) -> None:
        self.aborted = True


@pytest.fixture
def binding(tmp_path: Path) -> transport.BrokerTransportBinding:
    for name in ("ca.pem", "client.pem", "client.key"):
        (tmp_path / name).write_bytes(b"fixture")
    return transport.BrokerTransportBinding(
        endpoint=("127.0.0.1", 7443),
        ca_path=tmp_path / "ca.pem",
        client_cert_path=tmp_path / "client.pem",
        client_key_path=tmp_path / "client.key",
        expected_server_fingerprint=hashlib.sha256(PEER).hexdigest(),
        timeout_seconds=0.5,
    )


def _client(binding, session_id: str = SESSION):
    return client_module.RemoteWorkerBrokerClient.for_secretary_conversation(
        binding,
        host_ref=HOST_REF,
        root_id=ROOT_ID,
        session_id=session_id,
        expected_host_binding_sha256=BINDING,
        expected_implementation_sha=IMPLEMENTATION,
    )


def _answering_pair(writer: _Writer, reply_for, *, decode_request=transport.decode_secretary_request):
    """A fake peer that answers the one framed write with a built reply."""
    reader = _Reader()
    original_write = writer.write

    def write(data: bytes) -> None:
        original_write(data)
        request = decode_request(bytes(writer.written[4:]))
        reader.data.extend(transport.encode_frame(_canonical(reply_for(request))))

    writer.write = write
    return reader


# --- wire family ------------------------------------------------------------


def test_secretary_request_round_trip_is_closed_and_digest_bound():
    request = transport.build_secretary_request(
        HOST_REF, ROOT_ID, BINDING, IMPLEMENTATION, _submit()
    )
    assert set(request) == {
        "schema", "host_ref", "root_id", "host_binding_sha256",
        "implementation_sha", "request", "request_sha256",
    }
    assert request["schema"] == REMOTE_HERMES_SECRETARY_REQUEST_SCHEMA
    assert request["request_sha256"] == transport.request_sha256(request)
    raw = _canonical(request)
    assert len(raw) <= MAX_SECRETARY_REQUEST_BYTES
    assert transport.decode_secretary_request(raw) == request


def test_secretary_response_round_trip_preserves_the_native_result():
    request = _request(_submit())
    native = _native_result("ADMITTED", admission={"admission_id": "admission-0001"})
    response = transport.build_secretary_response(request, outcome="ok", result=native)
    assert set(response) == {
        "schema", "host_ref", "root_id", "host_binding_sha256",
        "implementation_sha", "request_sha256", "outcome", "result",
    }
    assert response["schema"] == REMOTE_HERMES_SECRETARY_RESPONSE_SCHEMA
    raw = _canonical(response)
    assert len(raw) <= MAX_SECRETARY_RESPONSE_BYTES
    decoded = transport.decode_secretary_response(raw, request)
    assert decoded["result"] == native


def test_secretary_refusal_result_is_exactly_one_bounded_code():
    request = _request()
    response = transport.build_secretary_response(
        request, outcome="refused", result={"code": "SOURCE_CHANGED"}
    )
    assert response["outcome"] == "refused"
    assert response["result"] == {"code": "SOURCE_CHANGED"}
    with pytest.raises(TransportValidationError):
        transport.build_secretary_response(
            request, outcome="refused",
            result={"code": "SOURCE_CHANGED", "admission_id": "admission-0001"},
        )
    with pytest.raises(TransportValidationError):
        transport.build_secretary_response(
            request, outcome="refused", result={"code": "source changed"}
        )


def test_secretary_ok_result_keeps_native_refusal_and_unknown_states():
    request = _request()
    for status in ("REFUSED", "EFFECT_UNKNOWN", "NOT_SUBMITTED", "UNAVAILABLE"):
        native = _native_result(status, reason="TARGET_CHANGED")
        response = transport.build_secretary_response(request, outcome="ok", result=native)
        assert response["result"]["status"] == status
        assert response["result"]["reason"] == "TARGET_CHANGED"
    with pytest.raises(TransportValidationError):
        transport.build_secretary_response(
            request, outcome="ok", result={"schema": "other/v1", "status": "ADMITTED"}
        )
    with pytest.raises(TransportValidationError):
        transport.build_secretary_response(
            request, outcome="ok",
            result={"schema": NATIVE_RESULT_SCHEMA, "status": "STARTED"},
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate-key",
        "non-finite",
        "extra-key",
        "missing-key",
        "wrong-digest",
        "short-digest",
        "bad-host-ref",
        "bad-root-id",
        "bad-binding-pin",
        "bad-implementation-pin",
        "uppercase-pin",
        "bad-schema",
        "bad-inner-operation",
        "extra-inner-key",
        "missing-inner-key",
        "bool-epoch",
        "bool-revision",
        "bool-generation",
        "extra-target-key",
        "missing-target-key",
        "empty-text",
        "oversize-text",
        "bad-input-digest",
        "bad-admission-id",
        "not-an-object",
    ],
)
def test_secretary_request_rejects_every_non_closed_shape(mutation: str):
    request = _request(_submit())
    raw = _canonical(request)
    if mutation == "duplicate-key":
        raw = raw.replace(b'"root_id"', b'"root_id":"x","root_id"', 1)
    elif mutation == "non-finite":
        raw = raw.replace(b'"request_sha256"', b'"request_sha256":NaN', 1)
    elif mutation == "extra-key":
        request["extra"] = 1
        raw = _canonical(request)
    elif mutation == "missing-key":
        del request["root_id"]
        raw = _canonical(request)
    elif mutation == "wrong-digest":
        request["request_sha256"] = "0" * 64
        raw = _canonical(request)
    elif mutation == "short-digest":
        request["request_sha256"] = "0" * 63
        raw = _canonical(request)
    elif mutation == "bad-host-ref":
        request["host_ref"] = "host-not-hex"
        raw = _canonical(request)
    elif mutation == "bad-root-id":
        request["root_id"] = "not a bounded id"
        raw = _canonical(request)
    elif mutation == "bad-binding-pin":
        request["host_binding_sha256"] = "b" * 63
        raw = _canonical(request)
    elif mutation == "bad-implementation-pin":
        request["implementation_sha"] = "c" * 41
        raw = _canonical(request)
    elif mutation == "uppercase-pin":
        request["host_binding_sha256"] = "B" * 64
        raw = _canonical(request)
    elif mutation == "bad-schema":
        request["schema"] = "mastermind.remote_hermes_secretary_request/v2"
        raw = _canonical(request)
    elif mutation == "bad-inner-operation":
        request["request"] = {"operation": "cancel", "session_id": SESSION}
        raw = _canonical(request)
    elif mutation == "extra-inner-key":
        request["request"] = dict(_submit(), priority="high")
        raw = _canonical(request)
    elif mutation == "missing-inner-key":
        request["request"] = {"operation": "observe"}
        raw = _canonical(request)
    elif mutation == "bool-epoch":
        target = _target()
        target["authority_epoch"] = True
        request["request"] = {
            "operation": "submit", "target": target,
            "submission_id": "submission-0001", "text": "bounded",
        }
        raw = _canonical(request)
    elif mutation == "bool-revision":
        target = _target()
        target["revision"] = True
        request["request"] = {
            "operation": "submit", "target": target,
            "submission_id": "submission-0001", "text": "bounded",
        }
        raw = _canonical(request)
    elif mutation == "bool-generation":
        target = _target()
        target["execution_generation"] = True
        request["request"] = {
            "operation": "submit", "target": target,
            "submission_id": "submission-0001", "text": "bounded",
        }
        raw = _canonical(request)
    elif mutation == "extra-target-key":
        target = _target()
        target["extra"] = "x"
        request["request"] = {
            "operation": "submit", "target": target,
            "submission_id": "submission-0001", "text": "bounded",
        }
        raw = _canonical(request)
    elif mutation == "missing-target-key":
        target = _target()
        del target["instance_id"]
        request["request"] = {
            "operation": "submit", "target": target,
            "submission_id": "submission-0001", "text": "bounded",
        }
        raw = _canonical(request)
    elif mutation == "empty-text":
        request["request"] = {
            "operation": "submit", "target": _target(),
            "submission_id": "submission-0001", "text": "   ",
        }
        raw = _canonical(request)
    elif mutation == "oversize-text":
        request["request"] = {
            "operation": "submit", "target": _target(),
            "submission_id": "submission-0001", "text": "x" * (16 * 1024 + 1),
        }
        raw = _canonical(request)
    elif mutation == "bad-input-digest":
        request["request"] = dict(_read_original(), input_sha256="z" * 64)
        raw = _canonical(request)
    elif mutation == "bad-admission-id":
        request["request"] = dict(_read_original(), admission_id="bad\x00id")
        raw = _canonical(request)
    elif mutation == "not-an-object":
        raw = b"[1, 2, 3]"
    with pytest.raises(TransportValidationError):
        transport.decode_secretary_request(raw)


def test_secretary_read_original_accepts_the_optional_admission_id():
    request = transport.build_secretary_request(
        HOST_REF, ROOT_ID, BINDING, IMPLEMENTATION,
        dict(_read_original(), admission_id="admission-0001"),
    )
    assert request["request"]["admission_id"] == "admission-0001"
    assert transport.decode_secretary_request(_canonical(request)) == request
    with pytest.raises(TransportValidationError):
        transport.build_secretary_request(
            HOST_REF, ROOT_ID, BINDING, IMPLEMENTATION,
            dict(_read_original(), admission_id=None),
        )


def test_secretary_request_and_response_size_ceilings_are_enforced():
    request = _request()
    assert len(_canonical(request)) <= MAX_SECRETARY_REQUEST_BYTES
    with pytest.raises(TransportValidationError):
        transport.decode_secretary_request(b"x" * (MAX_SECRETARY_REQUEST_BYTES + 1))
    with pytest.raises(TransportValidationError):
        transport.decode_secretary_response(
            b"x" * (MAX_SECRETARY_RESPONSE_BYTES + 1), request
        )


@pytest.mark.parametrize(
    "mutation",
    ["wrong-host-ref", "wrong-root-id", "wrong-binding-pin", "wrong-implementation-pin",
     "wrong-request-digest", "wrong-schema", "extra-key", "missing-key", "unknown-outcome",
     "refused-extra-result", "ok-missing-schema"],
)
def test_secretary_response_rejects_mismatched_or_extra_fields(mutation: str):
    request = _request()
    response = transport.build_secretary_response(
        request, outcome="ok", result=_native_result()
    )
    if mutation == "wrong-host-ref":
        response["host_ref"] = "host-" + "f" * 64
    elif mutation == "wrong-root-id":
        response["root_id"] = "other-root-0001"
    elif mutation == "wrong-binding-pin":
        response["host_binding_sha256"] = "f" * 64
    elif mutation == "wrong-implementation-pin":
        response["implementation_sha"] = "f" * 40
    elif mutation == "wrong-request-digest":
        response["request_sha256"] = "f" * 64
    elif mutation == "wrong-schema":
        response["schema"] = "mastermind.remote_hermes_secretary_response/v2"
    elif mutation == "extra-key":
        response["extra"] = 1
    elif mutation == "missing-key":
        del response["outcome"]
    elif mutation == "unknown-outcome":
        response["outcome"] = "error"
    elif mutation == "refused-extra-result":
        response["outcome"] = "refused"
        response["result"] = {"code": "SOURCE_CHANGED", "admission_id": "admission-0001"}
    elif mutation == "ok-missing-schema":
        response["result"] = {"status": "ADMITTED"}
    with pytest.raises(TransportValidationError):
        transport.decode_secretary_response(_canonical(response), request)


def test_secretary_response_rejects_duplicate_keys_and_non_finite_numbers():
    request = _request()
    response = transport.build_secretary_response(
        request, outcome="ok", result=_native_result()
    )
    raw = _canonical(response)
    duplicate = raw.replace(b'"outcome"', b'"outcome":"ok","outcome"', 1)
    with pytest.raises(TransportValidationError):
        transport.decode_secretary_response(duplicate, request)
    non_finite = raw.replace(b'"outcome"', b'"outcome":NaN', 1)
    with pytest.raises(TransportValidationError):
        transport.decode_secretary_response(non_finite, request)


def test_secretary_wire_rules_match_the_native_owner_exactly():
    from integrations.hermes_runtime import native_session_control as native

    assert transport._SECRETARY_NATIVE_RESULT_SCHEMA == native.SCHEMA
    for value in [
        "session-0001", "", "x" * 1024, "x" * 1025, "bad\x00id", "bad\x7fid",
        "line\nbreak", "tab\tvalue", "ünicode-id",
    ]:
        native_ok = True
        try:
            native._id(value)
        except Exception:
            native_ok = False
        wire_ok = True
        try:
            transport.validate_secretary_native_id(value)
        except TransportValidationError:
            wire_ok = False
        assert wire_ok is native_ok, value

    for target in [
        _target(),
        dict(_target(), authority_epoch=True),
        dict(_target(), revision=True),
        dict(_target(), execution_generation=True),
        dict(_target(), authority_epoch=0),
        dict(_target(), revision=-1),
        dict(_target(), execution_generation=-1),
        dict(_target(), extra="x"),
    ]:
        native_ok = True
        try:
            native.validate_target(target)
        except Exception:
            native_ok = False
        wire_ok = True
        try:
            transport.validate_secretary_native_target(target)
        except TransportValidationError:
            wire_ok = False
        assert wire_ok is native_ok, target

    for text in ["bounded", "", "   ", "x" * (16 * 1024), "x" * (16 * 1024 + 1), "ünicode"]:
        native_ok = True
        try:
            native.input_digest(text)
        except Exception:
            native_ok = False
        wire_ok = True
        try:
            transport.validate_secretary_native_text(text)
        except TransportValidationError:
            wire_ok = False
        assert wire_ok is native_ok, text[:16]


# --- control-side client ----------------------------------------------------


def test_secretary_construction_binds_one_session_and_refuses_worker_identity(binding):
    client = _client(binding)
    assert client.identity == {}
    assert client.allowed_operations == frozenset()
    assert client.bound_payload_identity == {}
    assert client._host_observation is None
    assert client._secretary_conversation == (
        HOST_REF, ROOT_ID, SESSION, BINDING, IMPLEMENTATION
    )
    with pytest.raises(TransportValidationError):
        client.bind_payload_identity(
            session_epoch_id="EPOCH-001", process_generation_id="GEN-001"
        )


def test_secretary_construction_refuses_unqualified_bindings(binding):
    with pytest.raises(TransportValidationError):
        client_module.RemoteWorkerBrokerClient.for_secretary_conversation(
            binding, host_ref="not-a-host", root_id=ROOT_ID, session_id=SESSION,
            expected_host_binding_sha256=BINDING, expected_implementation_sha=IMPLEMENTATION,
        )
    with pytest.raises(TransportValidationError):
        client_module.RemoteWorkerBrokerClient.for_secretary_conversation(
            binding, host_ref=HOST_REF, root_id="not a bounded id", session_id=SESSION,
            expected_host_binding_sha256=BINDING, expected_implementation_sha=IMPLEMENTATION,
        )
    with pytest.raises(TransportValidationError):
        client_module.RemoteWorkerBrokerClient.for_secretary_conversation(
            binding, host_ref=HOST_REF, root_id=ROOT_ID, session_id=SESSION,
            expected_host_binding_sha256="B" * 64, expected_implementation_sha=IMPLEMENTATION,
        )
    with pytest.raises(TransportValidationError):
        client_module.RemoteWorkerBrokerClient.for_secretary_conversation(
            binding, host_ref=HOST_REF, root_id=ROOT_ID, session_id=SESSION,
            expected_host_binding_sha256=BINDING, expected_implementation_sha="c" * 41,
        )
    with pytest.raises(TransportValidationError):
        client_module.RemoteWorkerBrokerClient.for_secretary_conversation(
            binding, host_ref=HOST_REF, root_id=ROOT_ID, session_id="",
            expected_host_binding_sha256=BINDING, expected_implementation_sha=IMPLEMENTATION,
        )


def test_existing_constructors_leave_the_secretary_selector_unbound(binding):
    worker = client_module.RemoteWorkerBrokerClient(
        binding,
        {
            "host_ref": HOST_REF, "job_id": "JOB-001", "attempt_id": "ATT-001",
            "worker_id": "WORKER-001", "operation_id": "OP-001",
        },
        allowed_operations={"status"},
    )
    assert worker._secretary_conversation is None
    observer = client_module.RemoteWorkerBrokerClient.for_host_observation(
        binding, host_ref=HOST_REF, expected_host_binding_sha256=BINDING,
        expected_implementation_sha=IMPLEMENTATION,
    )
    assert observer._secretary_conversation is None
    assert observer._host_observation == (HOST_REF, BINDING, IMPLEMENTATION)


@pytest.mark.parametrize(
    "request_value",
    [
        {"operation": "observe", "session_id": OTHER_SESSION},
        {"operation": "read_original", "session_id": OTHER_SESSION,
         "submission_id": "submission-0001", "input_sha256": "d" * 64},
        {"operation": "submit", "target": _target(OTHER_SESSION),
         "submission_id": "submission-0001", "text": "bounded"},
    ],
)
async def test_secretary_retargeting_is_refused_before_any_connection(
    binding, monkeypatch, request_value
):
    client = _client(binding)

    async def should_not_connect():
        raise AssertionError("network must not be reached")

    monkeypatch.setattr(client, "_open_connection", should_not_connect)
    with pytest.raises(TransportError) as raised:
        await client.request_secretary(request_value, before_write=lambda *_: None)
    assert raised.value.classification is TransportEffect.NO_EFFECT
    assert raised.value.code == "secretary_request_invalid"


async def test_secretary_submit_requires_an_explicit_before_write(binding, monkeypatch):
    client = _client(binding)

    async def should_not_connect():
        raise AssertionError("network must not be reached")

    monkeypatch.setattr(client, "_open_connection", should_not_connect)
    with pytest.raises(TransportError) as raised:
        await client.request_secretary(_submit())
    assert raised.value.code == "before_write_required"
    assert raised.value.classification is TransportEffect.NO_EFFECT


async def test_secretary_submit_writes_once_after_pin_and_callback(binding, monkeypatch):
    client = _client(binding)
    events: list[str] = []
    writer = _Writer(events=events)
    native = _native_result("ADMITTED", admission={"admission_id": "admission-0001"})
    reader = _answering_pair(writer, lambda request: transport.build_secretary_response(
        request, outcome="ok", result=native
    ))
    seen: list[tuple] = []

    async def exchange():
        events.append("connect")
        return reader, writer

    monkeypatch.setattr(client, "_open_connection", exchange)
    original_pin = client._server_pin_matches

    def traced_pin(target):
        events.append("pin")
        return original_pin(target)

    monkeypatch.setattr(client, "_server_pin_matches", traced_pin)

    def before_write(operation, payload):
        events.append("callback")
        seen.append((operation, payload))
        return None

    result = await client.request_secretary(_submit(), before_write=before_write)
    assert result == native
    assert events == ["connect", "pin", "callback", "write"]
    assert seen == [("submit", _submit())]
    assert writer.closed and writer.aborted


async def test_secretary_before_write_failure_is_no_effect_and_writes_nothing(
    binding, monkeypatch
):
    client = _client(binding)
    writer = _Writer()

    async def exchange():
        return _Reader(), writer

    monkeypatch.setattr(client, "_open_connection", exchange)

    def refuse(operation, payload):
        raise RuntimeError("commit-start refused")

    with pytest.raises(TransportError) as raised:
        await client.request_secretary(_submit(), before_write=refuse)
    assert raised.value.classification is TransportEffect.NO_EFFECT
    assert raised.value.code == "before_write_refused"
    assert bytes(writer.written) == b""


async def test_secretary_before_write_refusal_result_is_no_effect(binding, monkeypatch):
    client = _client(binding)
    writer = _Writer()

    async def exchange():
        return _Reader(), writer

    monkeypatch.setattr(client, "_open_connection", exchange)

    def refuse(operation, payload):
        return "REFUSED"

    with pytest.raises(TransportError) as raised:
        await client.request_secretary(_submit(), before_write=refuse)
    assert raised.value.classification is TransportEffect.NO_EFFECT
    assert bytes(writer.written) == b""


async def test_secretary_wrong_server_pin_is_no_effect_without_a_write(binding, monkeypatch):
    client = _client(binding)
    writer = _Writer(certificate=b"another-peer-certificate")

    async def exchange():
        return _Reader(), writer

    monkeypatch.setattr(client, "_open_connection", exchange)
    with pytest.raises(TransportError) as raised:
        await client.request_secretary(_submit(), before_write=lambda *_: None)
    assert raised.value.code == "server_identity_mismatch"
    assert raised.value.classification is TransportEffect.NO_EFFECT
    assert bytes(writer.written) == b""


async def test_secretary_connection_failure_is_no_effect_and_never_retries(binding, monkeypatch):
    client = _client(binding)
    attempts = 0

    async def unavailable():
        nonlocal attempts
        attempts += 1
        raise OSError("private endpoint /secret.sock")

    monkeypatch.setattr(client, "_open_connection", unavailable)
    with pytest.raises(TransportError) as raised:
        await client.request_secretary(_submit(), before_write=lambda *_: None)
    assert raised.value.code == "unavailable"
    assert raised.value.classification is TransportEffect.NO_EFFECT
    assert attempts == 1
    assert "private" not in str(raised.value)


@pytest.mark.parametrize("failure", ["write", "drain", "lost-response", "invalid-response"])
async def test_secretary_submit_ambiguity_after_write_is_effect_unknown(
    binding, monkeypatch, failure
):
    client = _client(binding)
    attempts = 0
    writer = _Writer(fail_write=failure == "write", fail_drain=failure == "drain")
    payload = b""
    if failure == "invalid-response":
        payload = transport.encode_frame(b"not-json")

    async def exchange():
        nonlocal attempts
        attempts += 1
        return _Reader(payload), writer

    monkeypatch.setattr(client, "_open_connection", exchange)
    with pytest.raises(TransportError) as raised:
        await client.request_secretary(_submit(), before_write=lambda *_: None)
    assert raised.value.classification is TransportEffect.EFFECT_UNKNOWN
    assert attempts == 1


async def test_secretary_observational_loss_stays_no_effect(binding, monkeypatch):
    client = _client(binding)
    attempts = 0

    async def exchange():
        nonlocal attempts
        attempts += 1
        return _Reader(), _Writer()

    monkeypatch.setattr(client, "_open_connection", exchange)
    with pytest.raises(TransportError) as raised:
        await client.request_secretary(_observe())
    assert raised.value.classification is TransportEffect.NO_EFFECT
    assert attempts == 1


async def test_secretary_oversized_response_frame_is_ambiguous_for_a_submit(
    binding, monkeypatch
):
    client = _client(binding)
    attempts = 0

    async def exchange():
        nonlocal attempts
        attempts += 1
        return _Reader((MAX_SECRETARY_RESPONSE_BYTES + 1).to_bytes(4, "big")), _Writer()

    monkeypatch.setattr(client, "_open_connection", exchange)
    with pytest.raises(TransportError) as raised:
        await client.request_secretary(_submit(), before_write=lambda *_: None)
    assert raised.value.code == "response_invalid"
    assert raised.value.classification is TransportEffect.EFFECT_UNKNOWN
    assert attempts == 1


async def test_secretary_server_refusal_is_no_effect(binding, monkeypatch):
    client = _client(binding)
    attempts = 0
    writer = _Writer()
    reader = _answering_pair(writer, lambda request: transport.build_secretary_response(
        request, outcome="refused", result={"code": "SOURCE_CHANGED"}
    ))

    async def exchange():
        nonlocal attempts
        attempts += 1
        return reader, writer

    monkeypatch.setattr(client, "_open_connection", exchange)
    with pytest.raises(TransportError) as raised:
        await client.request_secretary(_submit(), before_write=lambda *_: None)
    assert raised.value.code == "refused"
    assert raised.value.classification is TransportEffect.NO_EFFECT
    assert attempts == 1


async def test_secretary_cancellation_before_the_write_is_no_effect(binding, monkeypatch):
    client = _client(binding)
    writer = _Writer()

    async def open_delayed():
        await asyncio.sleep(0.05)
        return _Reader(), writer

    monkeypatch.setattr(client, "_open_connection", open_delayed)
    task = asyncio.create_task(
        client.request_secretary(_submit(), before_write=lambda *_: None)
    )
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(TransportError) as raised:
        await task
    assert raised.value.classification is TransportEffect.NO_EFFECT
    assert raised.value.code == "secretary_request_cancelled"
    assert bytes(writer.written) == b""


async def test_secretary_cancellation_after_the_write_is_effect_unknown(binding, monkeypatch):
    client = _client(binding)
    writer = _Writer()

    async def exchange():
        return _Reader(), writer

    monkeypatch.setattr(client, "_open_connection", exchange)

    async def drain_slowly():
        await asyncio.sleep(5)

    writer.drain = drain_slowly
    task = asyncio.create_task(
        client.request_secretary(_submit(), before_write=lambda *_: None)
    )
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(TransportError) as raised:
        await task
    assert raised.value.code == "secretary_request_cancelled"
    assert raised.value.classification is TransportEffect.EFFECT_UNKNOWN


async def test_secretary_total_deadline_bounds_the_whole_exchange(binding, monkeypatch):
    client = _client(binding)
    writer = _Writer(drain_delay=0.5)

    async def exchange():
        return _Reader(), writer

    monkeypatch.setattr(client, "_open_connection", exchange)
    with pytest.raises(TransportError) as raised:
        await client.request_secretary(_submit(), before_write=lambda *_: None)
    assert raised.value.classification is TransportEffect.EFFECT_UNKNOWN
    assert writer.closed and writer.aborted


async def test_secretary_selector_refuses_worker_and_observation_modes(binding, monkeypatch):
    client = _client(binding)

    async def should_not_connect():
        raise AssertionError("network must not be reached")

    monkeypatch.setattr(client, "_open_connection", should_not_connect)
    with pytest.raises(TransportError) as raised:
        await client.request("status", {})
    assert raised.value.code == "operation_not_allowed"
    with pytest.raises(TransportError) as raised:
        await client.read_hermes_roles()
    assert raised.value.code == "host_observation_not_bound"
    with pytest.raises(TransportValidationError):
        client.bind_payload_identity(
            session_epoch_id="EPOCH-001", process_generation_id="GEN-001"
        )


async def test_secretary_native_result_is_returned_without_upgrading_it(binding, monkeypatch):
    client = _client(binding)
    writer = _Writer()
    native = _native_result("EFFECT_UNKNOWN")
    reader = _answering_pair(writer, lambda request: transport.build_secretary_response(
        request, outcome="ok", result=native
    ))

    async def exchange():
        return reader, writer

    monkeypatch.setattr(client, "_open_connection", exchange)
    result = await client.request_secretary(_submit(), before_write=lambda *_: None)
    assert result == native
    assert result["status"] == "EFFECT_UNKNOWN"


async def test_secretary_seals_nested_request_before_connect(binding, monkeypatch):
    client = _client(binding)
    original = _submit()
    sealed = json.loads(_canonical(original))
    writer = _Writer()
    native = _native_result("ADMITTED", admission={"admission_id": "admission-0001"})
    reader = _answering_pair(writer, lambda request: transport.build_secretary_response(
        request, outcome="ok", result=native))
    seen = []

    async def exchange():
        original["target"]["session_id"] = "caller-mutated-after-seal"
        original["text"] = "changed outside the sealed operation"
        return reader, writer

    def commit(operation, request):
        seen.append((operation, request))

    monkeypatch.setattr(client, "_open_connection", exchange)
    assert await client.request_secretary(original, before_write=commit) == native
    transmitted = transport.decode_secretary_request(bytes(writer.written[4:]))
    assert seen == [("submit", sealed)]
    assert transmitted["request"] == sealed


async def test_secretary_callback_cannot_mutate_the_sealed_submission(binding, monkeypatch):
    client = _client(binding)
    writer = _Writer()
    async def exchange():
        return _Reader(), writer
    def mutate(operation, request):
        request["target"]["revision"] += 1
    monkeypatch.setattr(client, "_open_connection", exchange)
    with pytest.raises(TransportError) as failure:
        await client.request_secretary(_submit(), before_write=mutate)
    assert failure.value.classification is TransportEffect.NO_EFFECT
    assert failure.value.code == "before_write_refused"
    assert bytes(writer.written) == b""


async def test_secretary_deadline_after_commit_callback_prevents_write(binding, monkeypatch):
    import time
    client = _client(binding)
    writer = _Writer()
    async def exchange():
        return _Reader(), writer
    def slow_commit(operation, request):
        time.sleep(0.03)
    monkeypatch.setattr(client, "_open_connection", exchange)
    monkeypatch.setattr(client_module, "_SECRETARY_TOTAL_BUDGET_SECONDS", 0.02)
    with pytest.raises(TransportError) as failure:
        await client.request_secretary(_submit(), before_write=slow_commit)
    assert failure.value.classification is TransportEffect.NO_EFFECT
    assert bytes(writer.written) == b""
