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

INGRESS_SERVER_VERSION = {
    CeoIngressReadGateway: "1.0.0",
    WebCeoCeoIngressReadGateway: "1.1.0",
    WebCeoV2CeoIngressReadGateway: "1.2.0",
    WebCeoV3CeoIngressReadGateway: "1.2.0",
}
OUTPUT_SERVER_VERSION = {
    **INGRESS_SERVER_VERSION,
    WebCeoV3CeoIngressReadGateway: "1.4.0",
}


def canonical_result(
    profile=CeoIngressReadGateway,
    *,
    ok=True,
    code="not_found",
    message="No matching runtime record",
):
    return {
        "schema": RESULT_SCHEMA,
        "tool": "executive_state",
        "ok": ok,
        "server_version": INGRESS_SERVER_VERSION[profile],
        "mode": "readonly",
        "generated_at": "2026-10-04T03:00:00+00:00",
        "grounding": {
            "boot_packet_schema": "mastermind.ceo_boot_packet.v1",
            "macro": {"root": "/macro", "sha": "b" * 40},
            "mastermind": {"branch": "HEAD", "root": "/mastermind", "sha": "a" * 40},
            "runtime": "readonly:installed-executive-runtime",
            "runtime_db": {"path": "/runtime/executive.sqlite3", "present": True},
        },
        "data": {
            "mastermind": {"branch": "HEAD", "root": "/mastermind", "sha": "a" * 40},
            "macro": {"root": "/macro", "sha": "b" * 40},
            "boot_packet_schema": "mastermind.ceo_boot_packet.v1",
            "inbox_schema": "mastermind.executive_inbox.v2",
            "strategic_state": {"schema": "mastermind.strategic_state.v1"},
            "next_recommended_act": "Review current attention.",
            "runtime_db": {"path": "/runtime/executive.sqlite3", "present": True},
            "runtime_counts": {"jobs": {"total": 2}},
            "attention_counts": {"total": 0, "chairman": 0, "ceo": 0, "coo": 0},
            "handoffs": [],
        } if ok else None,
        "degraded": [],
        "bounded": [],
        "error": None if ok else {"code": code, "message": message},
    }


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
@pytest.mark.parametrize(("mutate", "case"), [
    (lambda value: value.__setitem__("schema", "wrong-schema"), "wrong-schema"),
    (lambda value: value.__setitem__("tool", "executive_job"), "wrong-tool"),
    (lambda value: value.__setitem__("ok", 1), "non-bool-ok"),
    (lambda value: value.__setitem__("ok", None), "null-ok"),
    (lambda value: value.__setitem__("private_detail", SECRET), "extra-private-field"),
    (lambda value: value.__setitem__("mode", "write"), "wrong-mode"),
    (lambda value: value.__setitem__("server_version", "9.9.9"), "wrong-version"),
    (lambda value: value.__setitem__("generated_at", 1), "bad-generated-at"),
    (lambda value: value.__setitem__("generated_at", "not-a-time"), "malformed-generated-at"),
    (lambda value: value["grounding"].__setitem__("private_detail", SECRET), "private-grounding-field"),
    (lambda value: value["data"].__setitem__("execution_ready", True), "forged-readiness-field"),
    (lambda value: value.__setitem__("data", None), "null-success-data"),
    (
        lambda value: value.__setitem__(
            "bounded",
            [{"bounded": True, "original_bytes": 10, "returned_bytes": 5,
              "field": "x", "private_detail": SECRET}],
        ),
        "private-bounding-field",
    ),
    (lambda value: value.__setitem__("grounding", []), "bad-grounding"),
    (lambda value: value.__setitem__("degraded", [1]), "bad-degraded"),
    (lambda value: value.__setitem__("bounded", ["not-a-receipt"]), "bad-bounded"),
    (
        lambda value: value.__setitem__(
            "error", {"code": "not_found", "message": SECRET}
        ),
        "success-with-error",
    ),
])
def test_untrusted_success_envelope_is_not_a_success_or_permission_refusal(
    profile, mutate, case
):
    result = canonical_result(profile)
    mutate(result)
    observed = asyncio.run(socket_read(profile, {"ok": True, "result": result}))
    assert_diagnostic(observed, "backend_unavailable", "invalid response")


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize(("mutate", "case"), [
    (
        lambda value: value.__setitem__(
            "data", {"runtime_counts": {"jobs": 99}, "private_detail": SECRET}
        ),
        "failure-with-data",
    ),
    (
        lambda value: value["error"].__setitem__("private_detail", SECRET),
        "failure-extra-error-field",
    ),
    (
        lambda value: value["error"].__setitem__("code", "future-error-code"),
        "unknown-error-code",
    ),
    (
        lambda value: value["error"].__setitem__("message", {"private": SECRET}),
        "non-string-error-message",
    ),
    (lambda value: value.__setitem__("error", None), "missing-error-shape"),
])
def test_malformed_inner_error_envelope_is_refused_without_leak(
    profile, mutate, case
):
    result = canonical_result(
        profile, ok=False, code="authority_refused", message=SECRET
    )
    mutate(result)
    observed = asyncio.run(socket_read(profile, {"ok": True, "result": result}))
    assert_diagnostic(observed, "backend_unavailable", "invalid response")


@pytest.mark.parametrize("profile", PROFILES)
def test_valid_canonical_read_success_is_preserved(profile):
    wire = canonical_result(profile)
    expected = copy.deepcopy(wire)
    expected["server_version"] = OUTPUT_SERVER_VERSION[profile]
    observed = asyncio.run(
        socket_read(profile, {"ok": True, "result": copy.deepcopy(wire)})
    )
    assert observed == expected


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize(
    ("upstream_code", "code", "category"),
    [
        ("authority_refused", "backend_refused", "permission was refused"),
        ("not_found", "backend_refused", "request was refused"),
        ("invalid_input", "backend_refused", "request was refused"),
        ("backend_unavailable", "backend_unavailable", "unavailable in the installed backend"),
        ("grounding_unavailable", "backend_unavailable", "unavailable in the installed backend"),
        ("timeout", "backend_unavailable", "unavailable in the installed backend"),
        ("internal_error", "backend_unavailable", "unavailable in the installed backend"),
    ],
)
def test_canonical_inner_error_is_classified_and_redacted(
    profile, upstream_code, code, category
):
    wire = canonical_result(
        profile, ok=False, code=upstream_code, message=SECRET
    )
    observed = asyncio.run(
        socket_read(profile, {"ok": True, "result": copy.deepcopy(wire)})
    )
    assert_diagnostic(observed, code, category)


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
