"""Read diagnostics must identify the observed boundary without implying execution."""
import asyncio
import copy
import json
from pathlib import Path
import tempfile

import pytest

from integrations.executive_mcp.schemas import RESULT_SCHEMA
from integrations.mastermind_executive_app.gateway import (
    CeoIngressClient,
    CeoIngressReadGateway,
    CeoIngressResponse,
    TRANSPORT_NOT_SENT,
    TRANSPORT_SENT_OK,
    TRANSPORT_SENT_UNKNOWN,
    WebCeoCeoIngressReadGateway,
    WebCeoV2CeoIngressReadGateway,
)
from integrations.mosyle_mdm.executive import WebCeoV3CeoIngressReadGateway


SECRET = "/Users/private-owner/credentials/example-secret-value"


class UnusedMdm:
    async def list_macos_devices(self):
        raise AssertionError("Executive reads must not fall back to MDM")


def reader(profile, path, client):
    if profile is WebCeoV3CeoIngressReadGateway:
        return profile(path, client, mdm_reader=UnusedMdm())
    return profile(path, client)


PROFILES = (
    CeoIngressReadGateway,
    WebCeoCeoIngressReadGateway,
    WebCeoV2CeoIngressReadGateway,
    WebCeoV3CeoIngressReadGateway,
)


def canonical_result(*, ok=True):
    result = {
        "schema": RESULT_SCHEMA,
        "tool": "executive_state",
        "ok": ok,
        "server_version": "1.4.0",
        "mode": "readonly",
        "generated_at": "2026-10-04T03:00:00+00:00",
        "grounding": {"mastermind_sha": "a" * 40},
        "data": {"runtime_counts": {"jobs": 2}} if ok else None,
        "degraded": [],
        "bounded": [],
    }
    if not ok:
        result["error"] = {"code": "not_found", "message": "No matching runtime record"}
    return result


async def socket_read(profile, wire):
    frames = []
    completed = asyncio.Event()

    async def backend(stream, writer):
        try:
            frames.append(json.loads(await stream.readline()))
            if wire is not None:
                payload = wire if isinstance(wire, bytes) else json.dumps(wire).encode() + b"\n"
                writer.write(payload)
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
            completed.set()

    # Short AF_UNIX paths are required on macOS; never contact the installed socket.
    with tempfile.TemporaryDirectory(prefix="erd-", dir="/tmp") as directory:
        path = str(Path(directory) / "reader.sock")
        server = await asyncio.start_unix_server(backend, path=path)
        async with server:
            gateway = reader(profile, path, CeoIngressClient(connect_timeout=1, read_timeout=1))
            result = await gateway.call("executive_state", {})
            await asyncio.wait_for(completed.wait(), 1)
            await gateway.aclose()
        assert len(frames) == 1
        assert frames[0]["tool"] == "executive_state"
        assert frames[0]["arguments"] == {}
        return result


def assert_diagnostic(result, code, category):
    assert result["schema"] == RESULT_SCHEMA
    assert result["tool"] == "executive_state"
    assert result["ok"] is False
    assert result["mode"] == "readonly"
    assert result["data"] is None
    assert result["grounding"] == {}
    assert set(result["error"]) == {"code", "message"}
    assert result["error"]["code"] == code
    message = result["error"]["message"]
    assert category in message
    assert "read operation" in message
    assert "submission and execution readiness were not observed" in message
    assert SECRET not in json.dumps(result)
    assert "effect_unknown" not in json.dumps(result)
    assert "retry" not in message.lower()


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize(
    ("wire", "code", "category"),
    [
        (None, "backend_unavailable", "after the read request was attempted"),
        (b"not-json\\n", "backend_unavailable", "after the read request was attempted"),
        ({"ok": 1}, "backend_unavailable", "after the read request was attempted"),
        ({"ok": False, "error": {"code": "peer_denied", "message": SECRET}},
         "backend_unavailable", "unavailable in the installed backend"),
        ({"ok": False, "error": {"code": "peer_credentials_unavailable", "message": SECRET}},
         "backend_unavailable", "unavailable in the installed backend"),
        ({"ok": False, "error": {"code": "unsupported_ingress_schema", "message": SECRET}},
         "backend_unavailable", "unavailable in the installed backend"),
        ({"ok": False, "error": {"code": "internal_error", "message": SECRET}},
         "backend_unavailable", "unavailable in the installed backend"),
        ({"ok": False, "error": {"code": "authority_refused", "message": SECRET}},
         "backend_refused", "permission was refused"),
        ({"ok": False, "error": {"code": "ingress_unavailable", "message": SECRET}},
         "backend_unavailable", "unavailable in the installed backend"),
        ({"ok": False, "error": {"code": "backend_unavailable", "message": SECRET}},
         "backend_unavailable", "unavailable in the installed backend"),
        ({"ok": False, "error": {"code": "invalid_input", "message": SECRET}},
         "backend_refused", "request was refused"),
        ({"ok": False, "error": {"code": "unrecognized-" + SECRET, "message": SECRET}},
         "backend_unavailable", "invalid response"),
    ],
)
def test_real_read_transport_distinguishes_failure_without_replay(profile, wire, code, category):
    assert_diagnostic(asyncio.run(socket_read(profile, wire)), code, category)


@pytest.mark.parametrize("profile", PROFILES)
def test_missing_socket_does_not_claim_reader_or_execution_ready(profile):
    with tempfile.TemporaryDirectory(prefix="erd-", dir="/tmp") as directory:
        gateway = reader(profile, str(Path(directory) / "absent.sock"), CeoIngressClient())
        result = asyncio.run(gateway.call("executive_state", {}))
    assert_diagnostic(result, "backend_unavailable", "request was not sent")


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize(("field", "value"), [
    ("schema", "wrong-schema"),
    ("tool", "executive_job"),
    ("ok", 1),
    ("ok", None),
])
def test_untrusted_success_envelope_is_not_a_success_or_permission_refusal(profile, field, value):
    result = canonical_result()
    result[field] = value
    result["private_detail"] = SECRET
    observed = asyncio.run(socket_read(profile, {"ok": True, "result": result}))
    assert_diagnostic(observed, "backend_unavailable", "invalid response")


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("ok", [True, False])
def test_valid_canonical_read_result_is_preserved(profile, ok):
    expected = canonical_result(ok=ok)
    observed = asyncio.run(socket_read(profile, {"ok": True, "result": copy.deepcopy(expected)}))
    assert observed == expected


class ClassifiedClient:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    async def send_frame(self, path, frame):
        self.calls += 1
        return self.response


@pytest.mark.parametrize("response", [
    CeoIngressResponse(transport="future-" + SECRET, detail=SECRET),
    CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=False, error={"code": [SECRET]}),
    CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=False, error=None),
    CeoIngressResponse(transport=TRANSPORT_NOT_SENT, ok=True, result=canonical_result(), detail=SECRET),
    CeoIngressResponse(transport=TRANSPORT_SENT_UNKNOWN, ok=False,
                       error={"code": "peer_denied"}, detail=SECRET),
])
def test_incoherent_classified_response_cannot_fabricate_permission_or_send_facts(response):
    client = ClassifiedClient(response)
    result = asyncio.run(CeoIngressReadGateway("/unused", client).call("executive_state", {}))
    assert client.calls == 1
    assert_diagnostic(result, "backend_unavailable", "invalid response")


def test_local_write_refusal_sends_no_read_frame():
    client = ClassifiedClient(CeoIngressResponse(transport=TRANSPORT_NOT_SENT))
    result = asyncio.run(CeoIngressReadGateway("/unused", client).call("submit_ceo_intent", {}))
    assert result["error"]["code"] == "authority_refused"
    assert client.calls == 0


@pytest.mark.parametrize("failure_point", ["write", "drain"])
def test_failed_socket_write_does_not_claim_request_delivery(failure_point, monkeypatch):
    connections = []

    class FailingWriter:
        def write(self, _data):
            if failure_point == "write":
                raise OSError("write failed " + SECRET)

        async def drain(self):
            raise OSError("drain failed " + SECRET)

        def close(self):
            pass

        async def wait_closed(self):
            pass

    async def connect(path, **_kwargs):
        connections.append(path)
        return object(), FailingWriter()

    monkeypatch.setattr(asyncio, "open_unix_connection", connect)
    gateway = CeoIngressReadGateway("/unused", CeoIngressClient())
    result = asyncio.run(gateway.call("executive_state", {}))
    assert connections == ["/unused"]
    assert_diagnostic(result, "backend_unavailable", "after the read request was attempted")
    assert "read request was sent" not in result["error"]["message"]
