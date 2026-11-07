"""Observe the real HTTPX request boundary; no publisher or submit is mocked in."""
import asyncio
import json

import httpx
import pytest

from integrations.mastermind_executive_app import os_commission_client as module

KEY = "mmos-launch-" + "a" * 40
SCOPE = "b" * 64
ARGS = {"operation_key": KEY, "objective": "Read the current contract."}
OK = {"schema": module.SCHEMA, "status": "prepared", "operation_key": KEY,
      "principal_scope": SCOPE, "head_sha": "c" * 40, "content_sha256": "d" * 64}
BEARER = "header.payload.signature"


def install_transport(monkeypatch, handler):
    real = httpx.AsyncClient
    construction = []
    calls = []

    async def observed(request):
        calls.append(request)
        return await handler(request)

    def client(**kwargs):
        construction.append(kwargs)
        return real(**kwargs, transport=httpx.MockTransport(observed))

    monkeypatch.setattr(httpx, "AsyncClient", client)
    return calls, construction


def run(client=None):
    return asyncio.run((client or module.StudioCommissionClient(port=45999)).prepare(
        arguments=ARGS, bearer=BEARER, principal_scope=SCOPE,
    ))


def test_exact_one_fixed_request_no_proxy_redirect_retry(monkeypatch):
    async def handler(request):
        assert str(request.url) == "http://127.0.0.1:45999/os-internal/commission/prepare"
        assert request.method == "POST"
        assert request.headers["authorization"] == f"Bearer {BEARER}"
        assert json.loads(request.content) == {"arguments": ARGS}
        return httpx.Response(200, json=OK)
    calls, construction = install_transport(monkeypatch, handler)
    result = run()
    assert result.status == "prepared"
    assert result.head_sha == OK["head_sha"]
    assert len(calls) == 1
    assert construction == [{"trust_env": False, "follow_redirects": False, "timeout": 90.0}]


@pytest.mark.parametrize("reply", [
    {**OK, "principal_scope": "e" * 64},
    {**OK, "operation_key": "mmos-launch-" + "e" * 40},
    {**OK, "head_sha": "../foreign"},
    {**OK, "content_sha256": "0"},
    {**OK, "extra": "foreign"},
    {**OK, "status": "accepted"},
    {"schema": module.SCHEMA, "status": "refused", "operation_key": KEY, "code": "arbitrary"},
])
def test_unqualified_receipt_never_proves_publication(monkeypatch, reply):
    async def handler(_):
        return httpx.Response(200, json=reply)
    calls, _ = install_transport(monkeypatch, handler)
    assert run().status == "effect_unknown"
    assert len(calls) == 1


@pytest.mark.parametrize("raw", [
    b"not json", b"[]", b"{}",
    json.dumps(OK).replace('"status": "prepared"', '"status":"prepared","status":"prepared"').encode(),
    b"x" * (module.MAX_RESPONSE_BYTES + 1),
])
def test_malformed_duplicate_and_oversize_reply_retains_uncertainty(monkeypatch, raw):
    async def handler(_):
        return httpx.Response(200, content=raw)
    calls, _ = install_transport(monkeypatch, handler)
    assert run().status == "effect_unknown"
    assert len(calls) == 1


@pytest.mark.parametrize("code", [301, 302, 307, 308, 401, 403, 404, 500])
def test_http_failure_and_redirect_are_not_replayed(monkeypatch, code):
    async def handler(_):
        return httpx.Response(code, headers={"location": "https://example.invalid/"}, json=OK)
    calls, _ = install_transport(monkeypatch, handler)
    assert run().status == "effect_unknown"
    assert len(calls) == 1


@pytest.mark.parametrize("status,code", [
    ("refused", "publication_refused"), ("conflict", "publication_conflict"),
    ("effect_unknown", "publication_unknown"),
])
def test_closed_refusal_survives_without_claiming_a_job(monkeypatch, status, code):
    async def handler(_):
        return httpx.Response(200, json={"schema": module.SCHEMA, "status": status,
                                        "operation_key": KEY, "code": code})
    install_transport(monkeypatch, handler)
    result = run()
    assert (result.status, result.code, result.head_sha) == (status, code, None)


def test_response_loss_after_owner_effect_never_replays(monkeypatch):
    async def handler(request):
        raise httpx.ReadError("response lost", request=request)
    calls, _ = install_transport(monkeypatch, handler)
    result = run()
    assert result.status == "effect_unknown" and result.operation_key == KEY
    assert len(calls) == 1


def test_total_deadline_covers_entire_exchange(monkeypatch):
    async def handler(_):
        await asyncio.sleep(2)
        return httpx.Response(200, json=OK)
    calls, _ = install_transport(monkeypatch, handler)
    assert run(module.StudioCommissionClient(port=45999, timeout_seconds=1)).status == "effect_unknown"
    assert len(calls) == 1


@pytest.mark.parametrize("port", [True, 0, 443, 8443, 45017, 65536, "45999"])
def test_destination_is_only_host_selected_unreserved_loopback_port(port):
    with pytest.raises(ValueError):
        module.StudioCommissionClient(port=port)


@pytest.mark.parametrize("bearer", ["", "x y", "x\r\ny", "a.b.c\x00", "a.b.c" + "x" * 16384])
def test_bad_bearer_is_rejected_before_io(bearer):
    with pytest.raises(ValueError):
        asyncio.run(module.StudioCommissionClient(port=45999).prepare(
            arguments=ARGS, bearer=bearer, principal_scope=SCOPE,
        ))
