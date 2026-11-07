"""Explicit Meta family over the incumbent one-shot transport; inert fixtures."""
from __future__ import annotations
import copy
from unittest.mock import AsyncMock
import pytest
from control_plane import remote_worker_transport as wire
from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
from tests.test_remote_hermes_secretary_transport import (
    binding, anyio_backend, _Writer, _Reader, _answering_pair, _canonical,
    _observe, _submit, _read_original, HOST_REF, ROOT_ID, BINDING, IMPLEMENTATION, SESSION,
)

pytestmark = pytest.mark.anyio
NATIVE = "mastermind.hermes_meta_native_control/v1"


def meta_client(binding):
    return RemoteWorkerBrokerClient.for_meta_conversation(
        binding, host_ref=HOST_REF, root_id=ROOT_ID, session_id=SESSION,
        expected_host_binding_sha256=BINDING, expected_implementation_sha=IMPLEMENTATION)


@pytest.mark.parametrize("operation", [_observe(), _submit(), _read_original()])
def test_meta_family_round_trip_and_schema_digest_separation(operation):
    meta = wire.build_meta_request(HOST_REF, ROOT_ID, BINDING, IMPLEMENTATION, operation)
    secretary = wire.build_secretary_request(HOST_REF, ROOT_ID, BINDING, IMPLEMENTATION, operation)
    assert meta["request_sha256"] != secretary["request_sha256"]
    assert wire.decode_meta_request(_canonical(meta)) == meta
    with pytest.raises(wire.TransportValidationError):
        wire.decode_secretary_request(_canonical(meta))
    with pytest.raises(wire.TransportValidationError):
        wire.decode_meta_request(_canonical(secretary))
    result = {"schema": NATIVE, "status": "EFFECT_UNKNOWN"}
    response = wire.build_meta_response(meta, outcome="ok", result=result)
    assert wire.decode_meta_response(_canonical(response), meta)["result"] == result
    with pytest.raises(wire.TransportValidationError):
        wire.build_meta_response(meta, outcome="ok", result=dict(
            result, schema="mastermind.hermes_secretary_native_control/v1"))
    changed = copy.deepcopy(meta)
    changed["schema"] = secretary["schema"]
    with pytest.raises(wire.TransportValidationError):
        wire.decode_secretary_request(_canonical(changed))


@pytest.mark.parametrize("family", ["meta", "secretary"])
async def test_wrong_bound_client_family_never_connects(binding, monkeypatch, family):
    factory = getattr(RemoteWorkerBrokerClient, "for_" + family + "_conversation")
    client = factory(binding, host_ref=HOST_REF, root_id=ROOT_ID, session_id=SESSION,
                     expected_host_binding_sha256=BINDING, expected_implementation_sha=IMPLEMENTATION)
    connect = AsyncMock(side_effect=AssertionError("foreign family connected"))
    monkeypatch.setattr(client, "_open_connection", connect)
    other = "secretary" if family == "meta" else "meta"
    with pytest.raises(wire.TransportError) as caught:
        await getattr(client, "request_" + other)(_submit(), before_write=lambda *_: None)
    assert caught.value.classification is wire.TransportEffect.NO_EFFECT
    connect.assert_not_called()


async def test_meta_seals_before_connect_and_writes_once_after_commit(binding, monkeypatch):
    client = meta_client(binding)
    events = []
    writer = _Writer(events=events)
    result = {"schema": NATIVE, "status": "ADMITTED", "admission": {"admission_id": "admission-1"}}
    observed = []
    def respond(request):
        observed.append(request["request"])
        return wire.build_meta_response(request, outcome="ok", result=result)
    reader = _answering_pair(writer, respond, decode_request=wire.decode_meta_request)
    request = _submit()
    expected = copy.deepcopy(request)
    async def connect():
        events.append("connect")
        request["text"] = "changed after sealing"
        return reader, writer
    monkeypatch.setattr(client, "_open_connection", connect)
    def commit(operation, payload):
        events.append("commit")
        assert operation == "submit" and payload == expected
    assert await client.request_meta(request, before_write=commit) == result
    assert observed == [expected] and events == ["connect", "commit", "write"]
    assert writer.closed and writer.aborted


@pytest.mark.parametrize("stage", ["missing-guard", "guard", "lost-response", "foreign-response"])
async def test_meta_preserves_prewrite_and_ambiguous_postwrite_boundaries(binding, monkeypatch, stage):
    client = meta_client(binding)
    writer = _Writer()
    if stage == "foreign-response":
        def respond(request):
            response = wire.build_meta_response(request, outcome="ok",
                result={"schema": NATIVE, "status": "ADMITTED"})
            response["result"]["schema"] = "mastermind.hermes_secretary_native_control/v1"
            return response
        reader = _answering_pair(writer, respond, decode_request=wire.decode_meta_request)
    else:
        reader = _Reader()
    connect = AsyncMock(return_value=(reader, writer))
    monkeypatch.setattr(client, "_open_connection", connect)
    def guard(*_):
        if stage == "guard":
            raise RuntimeError("original commit refused")
    with pytest.raises(wire.TransportError) as caught:
        await client.request_meta(_submit(), before_write=None if stage == "missing-guard" else guard)
    written = stage in {"lost-response", "foreign-response"}
    assert caught.value.classification is (wire.TransportEffect.EFFECT_UNKNOWN if written
                                           else wire.TransportEffect.NO_EFFECT)
    assert bool(writer.written) is written
    if stage == "missing-guard":
        connect.assert_not_called()
    else:
        connect.assert_awaited_once()
