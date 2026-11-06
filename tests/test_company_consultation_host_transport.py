from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from common.company_consultation_host_contract import (
    HOST_REQUEST_SCHEMA, MAX_REQUEST_BYTES, HostFrameError,
    decode_request, encode_request, encode_json_frame,
)
from integrations import company_consultation_host_transport as transport
from integrations.mastermind_company_mcp.consultation import _result


@pytest.mark.parametrize("tool", [
    "company.peers", "company.consult", "company.reply", "company.consultation",
])
def test_closed_request_roundtrip(tool):
    args = {"text": "héllo\nworld"}
    frame = encode_request(tool, args)
    assert frame.count(b"\n") == 1
    assert decode_request(frame) == (tool, args)


@pytest.mark.parametrize("frame", [
    b'{}\n', b'[]\n', b'{}', b'{}\n{}\n', b'\xff\n',
    b'{"x":1,"x":2}\n', b'{"x":{"n":1,"n":2}}\n',
    b'{"x":NaN}\n', b'{"x":Infinity}\n',
])
def test_malformed_wire_refuses(frame):
    with pytest.raises(HostFrameError):
        decode_request(frame)


@pytest.mark.parametrize("field", ["job_id", "attempt_id", "binding_id", "token"])
def test_caller_identity_is_never_a_top_level_request_field(field):
    frame = (json.dumps({
        "schema": HOST_REQUEST_SCHEMA, "tool": "company.peers", "arguments": {},
        field: "caller-selected",
    }) + "\n").encode()
    with pytest.raises(HostFrameError):
        decode_request(frame)


@pytest.mark.parametrize("arguments", [
    {1: "coerced-key"}, {"n": float("nan")}, {"n": float("inf")},
    {"n": object()}, {"values": [None] * 4096},
])
def test_encoder_rejects_non_json_or_over_budget_values(arguments):
    with pytest.raises(HostFrameError):
        encode_request("company.peers", arguments)


def test_exact_utf8_byte_boundary():
    empty = encode_request("company.peers", {"x": ""})
    fill = MAX_REQUEST_BYTES - len(empty)
    frame = encode_request("company.peers", {"x": "a" * fill})
    assert len(frame) == MAX_REQUEST_BYTES
    assert decode_request(frame)[1]["x"] == "a" * fill
    with pytest.raises(HostFrameError):
        encode_request("company.peers", {"x": "a" * (fill + 1)})
    with pytest.raises(HostFrameError):
        decode_request(frame[:-1] + b" \n")


def test_nested_json_budget_refuses():
    nested = {}
    for _ in range(34):
        nested = {"x": nested}
    with pytest.raises(HostFrameError):
        encode_request("company.peers", nested)
    frame = ('{"schema":"' + HOST_REQUEST_SCHEMA +
             '","tool":"company.peers","arguments":' +
             json.dumps(nested) + '}\n').encode()
    with pytest.raises(HostFrameError):
        decode_request(frame)


def arguments(tool):
    if tool == "company.consult":
        return {"to": "peer-" + "1" * 32, "question": "Question?",
                "evidence_refs": [], "artifact_revisions": []}
    return {}


async def exchange(tmp_path, tool, response, *, wrong_uid=False):
    path = str(tmp_path / "h.sock")
    received = []
    done = asyncio.Event()

    async def handle(reader, writer):
        try:
            received.append(await reader.readline())
            if response is not None and received[-1]:
                writer.write(response)
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
            done.set()

    server = await asyncio.start_unix_server(handle, path)
    try:
        gateway = transport.UnixCompanyConsultationGateway(
            socket_path=path, server_uid=os.getuid() + (1 if wrong_uid else 0),
            timeout_seconds=2,
        )
        result = await gateway.call(tool, arguments(tool))
        await asyncio.wait_for(done.wait(), 2)
        return result, received
    finally:
        server.close()
        await server.wait_closed()


@pytest.fixture
def fixture_peer(monkeypatch):
    # Portable transport mechanics; the separate Darwin test uses real audit.
    monkeypatch.setattr(transport, "capture_peer_identity",
                        lambda _: SimpleNamespace(euid=os.getuid()))
    monkeypatch.setattr(transport, "_current_capture", lambda _: None)


def test_unix_call_has_only_closed_semantic_frame(tmp_path, fixture_peer):
    result = _result("company.peers", {"peers": []})
    actual, received = asyncio.run(exchange(
        tmp_path, "company.peers", encode_json_frame(result, limit=65536),
    ))
    assert actual == result
    assert len(received) == 1
    assert decode_request(received[0]) == ("company.peers", {})


@pytest.mark.parametrize("response", [None, b"not-json\n", b"{}\n", b"{}\n{}\n",
                                     b"x" * 65537 + b"\n"])
def test_lost_or_invalid_modifying_response_is_unknown_without_retry(
    tmp_path, fixture_peer, response,
):
    result, received = asyncio.run(exchange(tmp_path, "company.consult", response))
    assert result["error"]["code"] == "EFFECT_UNKNOWN"
    assert len(received) == 1


def test_wrong_server_uid_refuses_before_request_body(tmp_path, fixture_peer):
    result, received = asyncio.run(exchange(tmp_path, "company.consult", None, wrong_uid=True))
    assert result["error"]["code"] == "ACCESS_REFUSED"
    assert received == [b""]


def test_wrong_tool_receipt_after_send_is_unknown(tmp_path, fixture_peer):
    wrong = _result("company.reply", {"ok": True})
    result, received = asyncio.run(exchange(
        tmp_path, "company.consult", encode_json_frame(wrong, limit=65536),
    ))
    assert result["error"]["code"] == "EFFECT_UNKNOWN"
    assert len(received) == 1


def test_missing_socket_is_unavailable_before_send(tmp_path):
    client = transport.UnixCompanyConsultationGateway(
        socket_path=str(tmp_path / "absent.sock"), server_uid=os.getuid(),
    )
    result = asyncio.run(client.call("company.consult", arguments("company.consult")))
    assert result["error"]["code"] == "UNAVAILABLE"


@pytest.mark.skipif(sys.platform != "darwin", reason="native Darwin server audit token")
def test_real_unix_server_peer_capture(tmp_path):
    expected = _result("company.peers", {"peers": []})
    result, received = asyncio.run(exchange(
        tmp_path, "company.peers", encode_json_frame(expected, limit=65536),
    ))
    assert result == expected
    assert len(received) == 1


@pytest.mark.parametrize("tool", [None, [], "x" * 70000, "private-unknown-tool"])
def test_unknown_tool_is_bounded_and_never_connects(tmp_path, tool):
    client = transport.UnixCompanyConsultationGateway(
        socket_path=str(tmp_path / "absent.sock"), server_uid=os.getuid(),
    )
    result = asyncio.run(client.call(tool, {}))
    assert result["tool"] == "unknown"
    assert result["error"]["code"] == "INVALID_REQUEST"


def test_cancellation_after_modifying_send_remains_unknown(tmp_path, fixture_peer):
    async def scenario():
        path = str(tmp_path / "cancel.sock")
        sent = asyncio.Event()
        closed = asyncio.Event()
        calls = []
        async def handle(reader, writer):
            calls.append(await reader.readline())
            sent.set()
            await reader.read()
            writer.close()
            await writer.wait_closed()
            closed.set()
        server = await asyncio.start_unix_server(handle, path)
        try:
            client = transport.UnixCompanyConsultationGateway(
                socket_path=path, server_uid=os.getuid(), timeout_seconds=2,
            )
            task = asyncio.create_task(client.call("company.consult", arguments("company.consult")))
            await asyncio.wait_for(sent.wait(), 2)
            task.cancel()
            result = await task
            await asyncio.wait_for(closed.wait(), 2)
            assert result["error"]["code"] == "EFFECT_UNKNOWN"
            assert len(calls) == 1
        finally:
            server.close()
            await server.wait_closed()
    asyncio.run(scenario())
