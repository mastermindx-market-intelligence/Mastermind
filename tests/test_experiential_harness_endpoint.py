"""A real OpenAI SDK consumer of the attempt-owned Experiential gateway seam.

Every provider interaction here is a local mock gateway on 127.0.0.1.  No
vendor request, no provider key, no live credential and no billable call is
involved.  The gateway owns the upstream key in production; this suite only
proves the consumer seam: attempt binding, one logical send, and fail-stop
effect semantics.
"""
from __future__ import annotations

import http.client
import json
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import pytest

from control_plane.attempt_inference_endpoint import InferenceEffectUnknown
from control_plane.experiential_harness_endpoint import (
    ExperientialGatewayRoute,
    ExperientialHarnessBinding,
    ExperientialHarnessContractError,
    ExperientialHarnessEndpoint,
    GatewayOutcome,
    GatewayStreamReceipt,
    forward_to_gateway,
    gateway_route_generation,
)
from control_plane.opencode_go_pooled_transport import ProviderRequest

MODEL = "deepseek-v4.1-flash"
NEAR_MISS_MODEL = "deepseek-v4.1-flash-1017"
CAPABILITY = "attemptcapability" + "c" * 24
PROXY_TOKEN = "local-scoped-proxy-token-" + "p" * 24
ROUTE_ID = "experiential-labs-chat"

CHUNK_TEXT = (
    b'data: {"id":"chatcmpl-fixture","object":"chat.completion.chunk","created":1,'
    b'"model":"deepseek-v4.1-flash","choices":[{"index":0,"delta":{"role":"assistant",'
    b'"content":"ok"},"finish_reason":null}]}\n\n'
)
CHUNK_TOOL_CALL = (
    b'data: {"id":"chatcmpl-fixture","object":"chat.completion.chunk","created":1,'
    b'"model":"deepseek-v4.1-flash","choices":[{"index":0,"delta":{"tool_calls":[{"index":0,'
    b'"id":"call_fixture","type":"function","function":{"name":"lookup",'
    b'"arguments":"{\\"q\\":\\"x\\"}"}}]},"finish_reason":null}]}\n\n'
)
CHUNK_DONE = b"data: [DONE]\n\n"
DEFAULT_FRAMES = CHUNK_TEXT + CHUNK_TOOL_CALL + CHUNK_DONE


class MockGateway:
    """A real local HTTP gateway stand-in with no vendor behind it."""

    def __init__(self, *, status=200, frames=DEFAULT_FRAMES, drop_response=False,
                 content_type="text/event-stream", gate=None, hang_seconds=0.0):
        self.status = status
        self.frames = frames
        self.drop_response = drop_response
        self.content_type = content_type
        self.gate = gate
        self.hang_seconds = hang_seconds
        self.requests: list[dict] = []
        self.entered = threading.Event()
        self._server = None
        self._thread = None

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> "MockGateway":
        gateway = self

        class Handler(_BaseHandler):
            def do_POST(self):  # noqa: N802
                gateway._handle(self)

        class Server(ThreadingHTTPServer):
            daemon_threads = True

            def handle_error(self, request, client_address) -> None:  # noqa: ANN001
                pass

        self._server = Server(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=3)

    @property
    def base_url(self) -> str:
        return "http://127.0.0.1:%d/v1" % self._server.server_address[1]

    # -- behaviour ---------------------------------------------------------
    def _handle(self, handler) -> None:
        length = int(handler.headers.get("Content-Length") or 0)
        body = handler.rfile.read(length)
        self.requests.append({
            "path": handler.path,
            "headers": {k.lower(): v for k, v in handler.headers.items()},
            "body": body,
        })
        self.entered.set()
        if self.gate is not None:
            self.gate.wait(5)
        if self.hang_seconds:
            # The gateway took the request and then went quiet: the client's
            # outcome is ambiguous and it must never replay.
            threading.Event().wait(self.hang_seconds)
        if self.drop_response:
            # The gateway accepted the request and then vanished: the client's
            # outcome is ambiguous.
            handler.close_connection = True
            try:
                handler.connection.close()
            except OSError:
                pass
            return
        if self.status != 200:
            payload = b'{"error":{"message":"fixture refusal"}}'
            handler.send_response(self.status)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(payload)))
            handler.end_headers()
            handler.wfile.write(payload)
            return
        handler.send_response(200)
        handler.send_header("Content-Type", self.content_type)
        handler.send_header("Content-Length", str(len(self.frames)))
        handler.end_headers()
        handler.wfile.write(self.frames)


class _BaseHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:  # noqa: ANN002
        pass


def route_for(gateway: MockGateway, *, path="chat/completions") -> ExperientialGatewayRoute:
    return ExperientialGatewayRoute(
        route_id=ROUTE_ID,
        route_generation=gateway_route_generation(gateway.base_url, path),
        base_url=gateway.base_url,
        path=path,
    )


def binding_for(gateway: MockGateway, *, model=MODEL, protocol="openai-chat",
                capability=CAPABILITY, session="attempt-session-1") -> ExperientialHarnessBinding:
    return ExperientialHarnessBinding(
        session_id=session,
        model_id=model,
        protocol=protocol,
        route=route_for(gateway),
        client_capability=capability,
    )


def build(binding: ExperientialHarnessBinding, **kwargs):
    outcomes: list[GatewayOutcome] = []
    failures: list[str] = []
    kwargs.setdefault("token_loader", lambda: PROXY_TOKEN)
    kwargs.setdefault("on_terminal_failure", failures.append)
    kwargs.setdefault("cancel", threading.Event())
    endpoint = ExperientialHarnessEndpoint(
        binding,
        on_outcome=outcomes.append,
        **kwargs,
    )
    return endpoint, outcomes, failures


def sdk_client(endpoint: ExperientialHarnessEndpoint):
    openai = pytest.importorskip(
        "openai", reason="OpenAI SDK unavailable in this test environment"
    )
    return openai.OpenAI(**endpoint.client_options())


def raw_post(endpoint: ExperientialHarnessEndpoint, *, capability=CAPABILITY, body=None,
             path="/v1/chat/completions"):
    parts = urlsplit(endpoint.base_url)
    connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=5)
    payload = body if body is not None else json.dumps(
        {"model": MODEL, "stream": True, "messages": [{"role": "user", "content": "hi"}]}
    ).encode()
    connection.request(
        "POST",
        path,
        body=payload,
        headers={"Authorization": "Bearer " + capability, "Content-Type": "application/json"},
    )
    response = connection.getresponse()
    result = (response.status, response.read())
    connection.close()
    return result


# --------------------------------------------------------------------------
# 1. A real OpenAI SDK client completes a stream through the attempt endpoint.
# --------------------------------------------------------------------------


def test_real_openai_sdk_client_completes_a_chat_stream_through_the_attempt_endpoint():
    gateway = MockGateway().start()
    try:
        endpoint, outcomes, failures = build(binding_for(gateway))
        with endpoint:
            client = sdk_client(endpoint)
            stream = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": "Say ok"}],
                stream=True,
            )
            chunks = list(stream)

        assert len(chunks) == 2
        assert chunks[0].choices[0].delta.content == "ok"
        tool_calls = chunks[1].choices[0].delta.tool_calls
        assert tool_calls and tool_calls[0].function.name == "lookup"
        assert json.loads(tool_calls[0].function.arguments) == {"q": "x"}
        assert gateway.requests and len(gateway.requests) == 1
        assert failures == []
        assert outcomes[0].kind == "completed"
        assert outcomes[0].http_status == 200
        assert outcomes[0].bytes_forwarded == len(DEFAULT_FRAMES)
        assert outcomes[0].model_id == MODEL
        assert outcomes[0].route_id == ROUTE_ID
    finally:
        gateway.stop()


def test_the_gateway_sees_only_the_local_proxy_token_and_never_the_attempt_capability():
    gateway = MockGateway().start()
    try:
        endpoint, _, _ = build(binding_for(gateway))
        with endpoint:
            client = sdk_client(endpoint)
            list(client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": "Say ok"}],
                stream=True,
            ))
        headers = gateway.requests[0]["headers"]
        assert headers["authorization"] == "Bearer " + PROXY_TOKEN
        assert CAPABILITY not in json.dumps(headers)
        assert CAPABILITY not in gateway.requests[0]["body"].decode()
        assert gateway.requests[0]["path"] == "/v1/chat/completions"
        body = json.loads(gateway.requests[0]["body"])
        assert body["model"] == MODEL and body["stream"] is True
    finally:
        gateway.stop()


def test_client_options_disable_automatic_retry_and_never_carry_the_proxy_token():
    gateway = MockGateway().start()
    try:
        endpoint, _, _ = build(binding_for(gateway))
        with endpoint:
            options = endpoint.client_options()
        assert options["max_retries"] == 0
        assert options["api_key"] == CAPABILITY
        assert options["base_url"].startswith("http://127.0.0.1:")
        assert PROXY_TOKEN not in json.dumps(options)
    finally:
        gateway.stop()


def test_the_gateway_forwarder_returns_a_sealed_receipt_for_the_attested_route():
    gateway = MockGateway().start()
    try:
        route = route_for(gateway)
        chunks: list[bytes] = []
        receipt = forward_to_gateway(
            ProviderRequest(
                "chat/completions",
                "attempt-session-1",
                {"Content-Type": "application/json"},
                json.dumps({"model": MODEL, "stream": True, "messages": []}).encode(),
            ),
            route=route,
            token_loader=lambda: PROXY_TOKEN,
            on_chunk=chunks.append,
        )
        assert isinstance(receipt, GatewayStreamReceipt)
        assert receipt.route_id == ROUTE_ID
        assert receipt.route_generation == gateway_route_generation(gateway.base_url, "chat/completions")
        assert receipt.http_status == 200
        assert receipt.terminal_observed is True
        assert receipt.bytes_forwarded == len(DEFAULT_FRAMES)
        assert b"".join(chunks) == DEFAULT_FRAMES
    finally:
        gateway.stop()


# --------------------------------------------------------------------------
# 2. An unauthorized child fails before the gateway and leaks no secret.
# --------------------------------------------------------------------------


def test_unauthorized_child_fails_before_the_gateway_and_leaks_no_secret():
    gateway = MockGateway().start()
    try:
        endpoint, outcomes, _ = build(binding_for(gateway))
        with endpoint:
            status, body = raw_post(endpoint, capability="wrong-capability-value-" + "w" * 24)
            assert status == 401
            assert CAPABILITY.encode() not in body
            assert PROXY_TOKEN.encode() not in body
            assert not endpoint.stopped_forwarding
        assert gateway.requests == []
        assert outcomes == []
    finally:
        gateway.stop()


def test_a_child_that_reuses_the_proxy_token_is_still_refused():
    gateway = MockGateway().start()
    try:
        endpoint, _, _ = build(binding_for(gateway))
        with endpoint:
            status, body = raw_post(endpoint, capability=PROXY_TOKEN)
            assert status == 401
            assert PROXY_TOKEN.encode() not in body
        assert gateway.requests == []
    finally:
        gateway.stop()


# --------------------------------------------------------------------------
# 3. Binding mismatches are refused before any provider call.
# --------------------------------------------------------------------------


def test_a_different_model_slug_is_refused_without_a_provider_call():
    gateway = MockGateway().start()
    try:
        endpoint, _, _ = build(binding_for(gateway, model=MODEL))
        with endpoint:
            body = json.dumps({
                "model": NEAR_MISS_MODEL,
                "stream": True,
                "messages": [{"role": "user", "content": "hi"}],
            }).encode()
            status, response = raw_post(endpoint, body=body)
            assert status == 400
            assert b"MMX_BINDING_REFUSED" in response
        assert gateway.requests == []
    finally:
        gateway.stop()


def test_a_non_streaming_child_request_is_refused_without_a_provider_call():
    gateway = MockGateway().start()
    try:
        endpoint, _, _ = build(binding_for(gateway))
        with endpoint:
            body = json.dumps({"model": MODEL, "messages": []}).encode()
            assert raw_post(endpoint, body=body)[0] == 400
        assert gateway.requests == []
    finally:
        gateway.stop()


def test_a_forged_receipt_route_identity_is_refused_and_latches():
    gateway = MockGateway().start()
    try:
        def forged(request, **kwargs):
            return GatewayStreamReceipt(
                route_id=ROUTE_ID,
                route_generation="f" * 64,
                http_status=200,
                bytes_forwarded=0,
                terminal_observed=True,
            )

        endpoint, outcomes, failures = build(binding_for(gateway), forward=forged)
        with endpoint:
            assert raw_post(endpoint)[0] == 409
            assert endpoint.stopped_forwarding
            assert raw_post(endpoint)[0] == 409
        assert gateway.requests == []
        assert failures == ["effect_unknown"]
        assert outcomes and outcomes[0].kind == "effect_unknown"
    finally:
        gateway.stop()


def test_a_non_loopback_gateway_target_is_refused_before_listening():
    with pytest.raises(ExperientialHarnessContractError):
        ExperientialGatewayRoute(
            route_id=ROUTE_ID,
            route_generation=gateway_route_generation("http://10.0.0.5:8311/v1", "chat/completions"),
            base_url="http://10.0.0.5:8311/v1",
            path="chat/completions",
        )


def test_a_route_generation_that_does_not_attest_the_pinned_target_is_refused():
    with pytest.raises(ExperientialHarnessContractError):
        ExperientialGatewayRoute(
            route_id=ROUTE_ID,
            route_generation="0" * 64,
            base_url="http://127.0.0.1:8311/v1",
            path="chat/completions",
        )


def test_a_route_whose_path_disagrees_with_the_protocol_is_refused():
    gateway = MockGateway().start()
    try:
        binding = replace(binding_for(gateway), protocol="responses")
        with pytest.raises(ExperientialHarnessContractError):
            build(binding)
    finally:
        gateway.stop()


# --------------------------------------------------------------------------
# 4. Refusals, cancellation and ambiguous effects fail stop without a retry.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", [402, 403, 429, 504])
def test_an_upstream_refusal_latches_without_a_second_send(status):
    gateway = MockGateway(status=status, frames=b"{}").start()
    try:
        endpoint, outcomes, failures = build(binding_for(gateway))
        with endpoint:
            assert raw_post(endpoint)[0] == 409
            for _ in range(3):
                assert raw_post(endpoint)[0] == 409
        assert len(gateway.requests) == 1
        assert endpoint.stopped_forwarding
        assert failures == ["upstream_refused_or_incomplete"]
        assert outcomes[0].kind == "refused"
        assert outcomes[0].http_status == status
    finally:
        gateway.stop()


def test_an_ambiguous_upstream_effect_fails_stop_without_a_retry():
    gateway = MockGateway(drop_response=True).start()
    try:
        endpoint, outcomes, failures = build(binding_for(gateway))
        with endpoint:
            assert raw_post(endpoint)[0] == 409
            assert raw_post(endpoint)[0] == 409
        assert len(gateway.requests) == 1
        assert endpoint.stopped_forwarding
        assert failures == ["effect_unknown"]
        assert outcomes[0].kind == "effect_unknown"
    finally:
        gateway.stop()


def test_a_stream_that_ends_without_a_terminal_frame_is_an_ambiguous_effect():
    gateway = MockGateway(frames=CHUNK_TEXT).start()
    try:
        endpoint, outcomes, failures = build(binding_for(gateway))
        with endpoint:
            with pytest.raises(http.client.IncompleteRead):
                raw_post(endpoint)
            assert raw_post(endpoint)[0] == 409
        assert len(gateway.requests) == 1
        assert endpoint.stopped_forwarding
        assert failures == ["effect_unknown"]
        assert outcomes[0].kind == "effect_unknown"
    finally:
        gateway.stop()


def test_a_cancelled_attempt_never_reaches_the_gateway():
    gateway = MockGateway().start()
    try:
        cancel = threading.Event()
        cancel.set()
        endpoint, outcomes, _ = build(binding_for(gateway), cancel=cancel)
        with endpoint:
            assert raw_post(endpoint)[0] == 409
        assert gateway.requests == []
        assert outcomes == []
    finally:
        gateway.stop()


def test_a_gateway_that_is_not_listening_is_refused_without_a_provider_effect():
    gateway = MockGateway().start()
    gateway.stop()
    endpoint, outcomes, failures = build(binding_for(gateway))
    with endpoint:
        assert raw_post(endpoint)[0] == 409
        assert raw_post(endpoint)[0] == 409
    assert endpoint.stopped_forwarding
    assert failures == ["request_admission_refused"]
    assert outcomes[0].kind == "unavailable"
    assert outcomes[0].http_status is None


def test_a_missing_local_proxy_token_is_refused_before_the_gateway():
    gateway = MockGateway().start()
    try:
        def refuse():
            raise RuntimeError("no token configured")

        endpoint, outcomes, _ = build(binding_for(gateway), token_loader=refuse)
        with endpoint:
            assert raw_post(endpoint)[0] == 409
        assert gateway.requests == []
        assert outcomes[0].kind == "refused"
    finally:
        gateway.stop()


# --------------------------------------------------------------------------
# 5. Concurrency stays with the existing attempt endpoint.
# --------------------------------------------------------------------------


def test_a_concurrent_child_request_never_creates_a_second_upstream_send():
    gate = threading.Event()
    gateway = MockGateway(gate=gate).start()
    try:
        endpoint, _, _ = build(binding_for(gateway))
        results: list[int] = []
        with endpoint:
            first = threading.Thread(
                target=lambda: results.append(raw_post(endpoint)[0]), daemon=True
            )
            first.start()
            assert gateway.entered.wait(5)
            with pytest.raises(Exception):
                raw_post(endpoint)
            gate.set()
            first.join(5)
            assert not first.is_alive()
        assert results == [200]
        assert len(gateway.requests) == 1
    finally:
        gateway.stop()


# --------------------------------------------------------------------------
# 6. The endpoint itself is a one-shot attempt surface.
# --------------------------------------------------------------------------


def test_the_endpoint_cannot_restart_and_the_capability_stays_out_of_the_repr():
    gateway = MockGateway().start()
    try:
        binding = binding_for(gateway)
        assert CAPABILITY not in repr(binding)
        endpoint, _, _ = build(binding)
        with endpoint:
            pass
        endpoint.close()
        with pytest.raises(ExperientialHarnessContractError):
            endpoint.__enter__()
    finally:
        gateway.stop()


def test_an_invalid_attempt_capability_is_refused_before_listening():
    gateway = MockGateway().start()
    try:
        with pytest.raises(ExperientialHarnessContractError):
            build(binding_for(gateway, capability="short"))
    finally:
        gateway.stop()


def test_the_model_slug_is_never_substituted_by_the_consumer():
    gateway = MockGateway().start()
    try:
        endpoint, outcomes, _ = build(binding_for(gateway, model=MODEL))
        with endpoint:
            client = sdk_client(endpoint)
            list(client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": "Say ok"}],
                stream=True,
            ))
        assert json.loads(gateway.requests[0]["body"])["model"] == MODEL
        assert outcomes[0].model_id == MODEL
        assert endpoint.model_id == MODEL
    finally:
        gateway.stop()


def test_a_timeout_after_a_possible_send_fails_stop_without_a_retry():
    gateway = MockGateway(hang_seconds=3.0).start()
    try:
        endpoint, outcomes, failures = build(
            binding_for(gateway), idle_timeout_seconds=0.5, total_timeout_seconds=5.0
        )
        with endpoint:
            assert raw_post(endpoint)[0] == 409
            assert raw_post(endpoint)[0] == 409
        assert len(gateway.requests) == 1
        assert endpoint.stopped_forwarding
        assert failures == ["effect_unknown"]
        assert outcomes[0].kind == "effect_unknown"
    finally:
        gateway.stop()


def test_the_child_receives_the_provider_frames_unmodified():
    gateway = MockGateway().start()
    try:
        endpoint, _, _ = build(binding_for(gateway))
        with endpoint:
            status, body = raw_post(endpoint)
        assert status == 200
        assert body == DEFAULT_FRAMES
    finally:
        gateway.stop()


def test_an_owner_supplied_idempotency_key_reaches_the_gateway_as_a_header():
    gateway = MockGateway().start()
    try:
        endpoint, _, _ = build(
            binding_for(gateway), idempotency_key_loader=lambda: "attempt-request-1"
        )
        with endpoint:
            client = sdk_client(endpoint)
            list(client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": "Say ok"}],
                stream=True,
            ))
        assert gateway.requests[0]["headers"]["idempotency-key"] == "attempt-request-1"
    finally:
        gateway.stop()


def test_an_unusable_idempotency_key_is_refused_before_the_gateway():
    gateway = MockGateway().start()
    try:
        endpoint, outcomes, _ = build(
            binding_for(gateway), idempotency_key_loader=lambda: "bad key"
        )
        with endpoint:
            assert raw_post(endpoint)[0] == 409
        assert gateway.requests == []
        assert outcomes[0].kind == "refused"
    finally:
        gateway.stop()


def test_a_non_event_stream_success_is_an_ambiguous_effect():
    gateway = MockGateway(content_type="application/json", frames=b'{"ok":true}').start()
    try:
        endpoint, outcomes, failures = build(binding_for(gateway))
        with endpoint:
            assert raw_post(endpoint)[0] == 409
            assert raw_post(endpoint)[0] == 409
        assert len(gateway.requests) == 1
        assert endpoint.stopped_forwarding
        assert failures == ["effect_unknown"]
        assert outcomes[0].kind == "effect_unknown"
    finally:
        gateway.stop()


def test_the_typed_effect_unknown_contract_of_the_existing_endpoint_is_preserved():
    gateway = MockGateway().start()
    try:
        def unresolved(request, **kwargs):
            raise InferenceEffectUnknown("upstream effect is unresolved")

        endpoint, outcomes, failures = build(binding_for(gateway), forward=unresolved)
        with endpoint:
            assert raw_post(endpoint)[0] == 409
            assert raw_post(endpoint)[0] == 409
        assert gateway.requests == []
        assert endpoint.stopped_forwarding
        assert failures == ["effect_unknown"]
        assert outcomes[0].kind == "effect_unknown"
    finally:
        gateway.stop()
