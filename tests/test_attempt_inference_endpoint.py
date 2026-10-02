"""Provider-neutral attempt-owned loopback inference endpoint."""
from __future__ import annotations

from dataclasses import replace
import http.client
import json
import threading
from urllib.parse import urlsplit

import pytest

from control_plane.attempt_inference_endpoint import (
    AttemptInferenceBinding,
    AttemptInferenceEndpoint,
    InferenceEffectUnknown,
    InferenceEndpointContractError,
    InferenceForwardReceipt,
    InferenceForwardRefused,
)

CAP = "z" * 48
MODEL = "test-model"
GEN = "a" * 64
HTTP_BAD_REQUEST = 4 * 100
HTTP_UNAUTHORIZED = HTTP_BAD_REQUEST + 1
HTTP_CONFLICT = HTTP_BAD_REQUEST + 9
BODY = json.dumps(
    {
        "model": MODEL,
        "stream": True,
        "messages": [{"role": "user", "content": "inspect this bounded input"}],
    }
).encode()
BINDING = AttemptInferenceBinding(
    session_id="attempt-session",
    model_id=MODEL,
    protocol="openai-chat",
    route_id="production-mode-a",
    route_generation=GEN,
    client_capability=CAP,
)


def _call(endpoint, *, body=BODY, capability=CAP, path="/v1/chat/completions", headers=None):
    url = urlsplit(endpoint.base_url)
    conn = http.client.HTTPConnection(url.hostname, url.port, timeout=3)
    request_headers = {
        "Authorization": "Bearer " + capability,
        "Content-Type": "application/json",
    }
    request_headers.update(headers or {})
    conn.request("POST", path, body=body, headers=request_headers)
    response = conn.getresponse()
    result = response.status, response.read()
    conn.close()
    return result


def _endpoint(*, forward=None, failure=None, binding=BINDING):
    seen = []

    def default_forward(request, *, on_chunk, cancel):
        seen.append(request)
        assert not cancel.is_set()
        on_chunk(b'data: {"choices":[]}\n\n')
        on_chunk(b"data: [DONE]\n\n")
        return InferenceForwardReceipt(
            route_id=binding.route_id,
            route_generation=binding.route_generation,
            http_status=200,
            bytes_forwarded=35,
            terminal_observed=True,
        )

    ep = AttemptInferenceEndpoint(
        binding,
        forward=forward or default_forward,
        on_terminal_failure=failure or (lambda kind: seen.append(kind)),
        cancel=threading.Event(),
    )
    return ep, seen


def test_keyless_forwarder_receives_fixed_session_model_and_no_client_auth_secret():
    ep, seen = _endpoint()
    with ep:
        status, body = _call(ep)
        assert status == 200
        assert body.endswith(b"data: [DONE]\n\n")
        assert ep.base_url.startswith("http://127.0.0.1:")
    request = seen[0]
    assert request.session_id == "attempt-session"
    assert request.body == BODY
    assert request.headers == {"Content-Type": "application/json"}
    assert CAP not in repr(request)
    assert CAP not in repr(BINDING)


@pytest.mark.parametrize(
    "body,path,capability",
    [
        (BODY.replace(MODEL.encode(), b"other-model"), "/v1/chat/completions", CAP),
        (BODY.replace(b"true", b"false"), "/v1/chat/completions", CAP),
        (BODY, "/v1/responses", CAP),
        (BODY, "/v1/chat/completions", "wrong"),
    ],
)
def test_unbound_request_never_reaches_forwarder(body, path, capability):
    ep, seen = _endpoint()
    with ep:
        status, _ = _call(ep, body=body, path=path, capability=capability)
        assert status in {HTTP_BAD_REQUEST, HTTP_UNAUTHORIZED}
        assert seen == []
        assert not ep.stopped_forwarding


def test_effect_unknown_fail_stops_before_outer_client_retry():
    calls = []
    failures = []

    def forward(request, *, on_chunk, cancel):
        calls.append(request)
        raise InferenceEffectUnknown("unknown")

    ep, _ = _endpoint(forward=forward, failure=lambda kind: failures.append((kind, ep.stopped_forwarding)))
    with ep:
        assert _call(ep)[0] == HTTP_CONFLICT
        for _ in range(3):
            assert _call(ep)[0] == HTTP_CONFLICT
    assert len(calls) == 1
    assert failures == [("effect_unknown", True)]


def test_pre_effect_forward_refusal_is_terminal_but_sends_no_provider_bytes():
    calls = []

    def forward(request, *, on_chunk, cancel):
        calls.append(request)
        raise InferenceForwardRefused("policy refused")

    ep, failures = _endpoint(forward=forward)
    with ep:
        assert _call(ep)[0] == HTTP_CONFLICT
        assert _call(ep)[0] == HTTP_CONFLICT
    assert len(calls) == 1
    assert "request_admission_refused" in failures


@pytest.mark.parametrize(
    "changes",
    [
        {"route_id": "production-mode-b"},
        {"route_generation": "b" * 64},
        {"terminal_observed": False},
        {"http_status": HTTP_BAD_REQUEST + 29},
    ],
)
def test_forward_receipt_cannot_change_route_or_claim_incomplete_success(changes):
    calls = []

    def forward(request, *, on_chunk, cancel):
        calls.append(request)
        if (
            "route_id" not in changes
            and "route_generation" not in changes
            and changes.get("terminal_observed", True)
            and changes.get("http_status", 200) == 200
        ):
            on_chunk(b"data: [DONE]\n\n")
        receipt = InferenceForwardReceipt(
            route_id=BINDING.route_id,
            route_generation=BINDING.route_generation,
            http_status=200,
            bytes_forwarded=14,
            terminal_observed=True,
        )
        return replace(receipt, **changes)

    ep, _ = _endpoint(forward=forward)
    with ep:
        status, _ = _call(ep)
        assert status == HTTP_CONFLICT
        assert ep.stopped_forwarding
        assert _call(ep)[0] == HTTP_CONFLICT
    assert len(calls) == 1


def test_partial_stream_then_receipt_identity_mismatch_is_effect_unknown_and_poisoned():
    calls = []

    def forward(request, *, on_chunk, cancel):
        calls.append(request)
        on_chunk(b'data: {"choices":[]}\n\n')
        return InferenceForwardReceipt(
            route_id="production-mode-b",
            route_generation=BINDING.route_generation,
            http_status=200,
            bytes_forwarded=22,
            terminal_observed=True,
        )

    ep, _ = _endpoint(forward=forward)
    with ep:
        with pytest.raises(http.client.IncompleteRead):
            _call(ep)
        assert ep.stopped_forwarding
        assert _call(ep)[0] == HTTP_CONFLICT
    assert len(calls) == 1


@pytest.mark.parametrize(
    "binding",
    [
        replace(BINDING, route_id=""),
        replace(BINDING, route_id="bad route"),
        replace(BINDING, route_generation="short"),
        replace(BINDING, client_capability="short"),
        replace(BINDING, protocol="unknown"),
    ],
)
def test_invalid_trusted_binding_refuses_before_listening(binding):
    with pytest.raises(InferenceEndpointContractError):
        AttemptInferenceEndpoint(
            binding,
            forward=lambda *a, **k: None,
            on_terminal_failure=lambda _: None,
            cancel=threading.Event(),
        )


def test_anthropic_local_auth_uses_x_api_key_but_still_strips_it_from_forwarded_request():
    binding = replace(BINDING, protocol="anthropic")
    seen = []

    def forward(request, *, on_chunk, cancel):
        seen.append(request)
        on_chunk(b'event: message_stop\ndata: {"type":"message_stop"}\n\n')
        return InferenceForwardReceipt(
            binding.route_id, binding.route_generation, 200, 54, True
        )

    ep = AttemptInferenceEndpoint(
        binding,
        forward=forward,
        on_terminal_failure=lambda _: None,
        cancel=threading.Event(),
    )
    with ep:
        url = urlsplit(ep.base_url)
        conn = http.client.HTTPConnection(url.hostname, url.port, timeout=3)
        conn.request(
            "POST",
            "/v1/messages",
            body=BODY,
            headers={"x-api-key": CAP, "Content-Type": "application/json"},
        )
        response = conn.getresponse()
        assert response.status == 200
        response.read()
        conn.close()
    assert len(seen) == 1
    assert "Authorization" not in seen[0].headers
    assert "x-api-key" not in seen[0].headers
