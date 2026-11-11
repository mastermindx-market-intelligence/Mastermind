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
import socket
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
#: A provider refusal inside the stream: the JSON error object form.
CHUNK_ERROR = (
    b'data: {"error":{"message":"provider refusal","type":"server_error"}}\n\n'
)
#: The provider refusal in its SSE event form.
CHUNK_ERROR_EVENT = (
    b'event: error\ndata: {"message":"provider refusal"}\n\n'
)
#: A bare SSE error event is a refusal even without a data: field.
CHUNK_ERROR_EVENT_BARE = b"event: error\n\n"
#: The provider refusal in its error object form.
CHUNK_ERROR_OBJECT = (
    b'data: {"object":"error","message":"provider refusal"}\n\n'
)
#: A responses stream that carries a tool call and then completes.
RESPONSES_TOOL_CALL = (
    b'data: {"type":"response.output_item.added","sequence_number":1,'
    b'"item":{"id":"fc_fixture","type":"function_call","call_id":"call_fixture",'
    b'"name":"lookup","arguments":"{\\"q\\":\\"x\\"}"}}\n\n'
)
RESPONSES_COMPLETED = (
    b'data: {"type":"response.completed","sequence_number":2,'
    b'"response":{"id":"resp_fixture","status":"completed"}}\n\n'
)
#: A responses stream that fails before its completion frame.
RESPONSES_FAILED = (
    b'data: {"type":"response.failed","sequence_number":1,'
    b'"response":{"id":"resp_fixture","status":"failed"}}\n\n'
)


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

    @property
    def port(self) -> int:
        return self._server.server_address[1]

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


class _ScriptedResolver:
    """A resolver that answers one name with a scripted sequence of addresses.

    Every answer is a list of literal addresses.  The requested port is
    carried through, exactly as a real resolver does, so the consumer that
    pins an answer dials the port it asked for.
    """

    def __init__(self, answers):
        self._answers = list(answers)
        self._calls = 0
        self._real = socket.getaddrinfo

    @property
    def calls(self) -> int:
        return self._calls

    def __call__(self, host, port, *args, **kwargs):
        if host != "localhost":
            return self._real(host, port, *args, **kwargs)
        self._calls += 1
        script = self._answers[min(self._calls - 1, len(self._answers) - 1)]
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                (address, port),
            )
            for address in script
        ]


def localhost_route(gateway: MockGateway, *, path="chat/completions") -> ExperientialGatewayRoute:
    """A route that names the gateway, so it has to be resolved and pinned."""
    base_url = "http://localhost:%d/v1" % gateway.port
    return ExperientialGatewayRoute(
        route_id=ROUTE_ID,
        route_generation=gateway_route_generation(base_url, path),
        base_url=base_url,
        path=path,
    )


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
    kwargs.setdefault("on_outcome", outcomes.append)
    endpoint = ExperientialHarnessEndpoint(binding, **kwargs)
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


# --------------------------------------------------------------------------
# 7. A provider error frame is never a completion.
#
# The independent review of the previous head reproduced a chat stream that
# carried a provider error and then ``[DONE]``: the consumer marked the
# request completed and a second child request produced a second upstream
# POST.  A provider error latches for good, so the terminal marker can never
# revive it and the attempt fails stop instead.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "error_frame",
    [CHUNK_ERROR, CHUNK_ERROR_EVENT, CHUNK_ERROR_EVENT_BARE, CHUNK_ERROR_OBJECT],
)
def test_a_chat_provider_error_frame_is_never_a_completion_and_blocks_a_second_send(error_frame):
    frames = error_frame + CHUNK_DONE
    gateway = MockGateway(frames=frames).start()
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
        assert outcomes[0].http_status == 200
        assert outcomes[0].bytes_forwarded == len(frames)
    finally:
        gateway.stop()


def test_a_chat_provider_error_frame_alone_is_never_a_completion():
    gateway = MockGateway(frames=CHUNK_ERROR).start()
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


def test_a_real_openai_sdk_client_surfaces_the_provider_error_and_never_sends_twice():
    openai = pytest.importorskip(
        "openai", reason="OpenAI SDK unavailable in this test environment"
    )
    gateway = MockGateway(frames=CHUNK_ERROR + CHUNK_DONE).start()
    try:
        endpoint, outcomes, failures = build(binding_for(gateway))
        with endpoint:
            client = sdk_client(endpoint)
            with pytest.raises(openai.APIError) as caught:
                list(client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "user", "content": "Say ok"}],
                    stream=True,
                ))
            assert "provider refusal" in str(caught.value)
            assert raw_post(endpoint)[0] == 409
        assert len(gateway.requests) == 1
        assert endpoint.stopped_forwarding
        assert failures == ["effect_unknown"]
        assert outcomes[0].kind == "effect_unknown"
        assert PROXY_TOKEN not in repr(outcomes[0])
    finally:
        gateway.stop()


def test_the_child_receives_the_provider_error_bytes_and_no_credential():
    gateway = MockGateway(frames=CHUNK_ERROR + CHUNK_DONE).start()
    try:
        endpoint, _, _ = build(binding_for(gateway))
        with endpoint:
            with pytest.raises(http.client.IncompleteRead) as caught:
                raw_post(endpoint)
        received = caught.value.partial
        assert b"provider refusal" in received
        assert PROXY_TOKEN.encode() not in received
        assert CAPABILITY.encode() not in received
    finally:
        gateway.stop()


# --------------------------------------------------------------------------
# 8. The gateway socket is pinned to a numeric loopback address.
#
# The previous head admitted a named loopback host and let the HTTP client
# resolve it again at request time.  A rebinding resolver could therefore
# answer the check with a loopback address and the send with another one.
# The name is now resolved once and the numeric answer is dialled directly.
# --------------------------------------------------------------------------


def test_a_rebinding_resolver_is_refused_before_the_proxy_token_is_sent(monkeypatch):
    gateway = MockGateway().start()
    resolver = _ScriptedResolver([["127.0.0.1"], ["203.0.113.10"]])
    monkeypatch.setattr(socket, "getaddrinfo", resolver)
    try:
        binding = replace(binding_for(gateway), route=localhost_route(gateway))
        endpoint, outcomes, failures = build(binding)
        with endpoint:
            assert raw_post(endpoint)[0] == 409
            assert raw_post(endpoint)[0] == 409
        assert gateway.requests == []
        assert endpoint.stopped_forwarding
        assert failures == ["request_admission_refused"]
        assert outcomes[0].kind == "refused"
        assert resolver.calls == 2
    finally:
        gateway.stop()


def test_the_gateway_socket_is_pinned_to_a_numeric_loopback_address(monkeypatch):
    gateway = MockGateway().start()
    resolver = _ScriptedResolver([["127.0.0.1"], ["127.0.0.1"], ["203.0.113.10"]])
    monkeypatch.setattr(socket, "getaddrinfo", resolver)
    try:
        binding = replace(binding_for(gateway), route=localhost_route(gateway))
        endpoint, outcomes, failures = build(binding)
        with endpoint:
            status, body = raw_post(endpoint)
        assert status == 200
        assert body == DEFAULT_FRAMES
        assert len(gateway.requests) == 1
        # The name was resolved once for the binding and once for the forward.
        # The dial then used the pinned number, so no later resolution could
        # move the bearer-bearing request off loopback.
        assert resolver.calls == 2
        assert outcomes[0].kind == "completed"
        assert failures == []
    finally:
        gateway.stop()


def test_a_numeric_loopback_gateway_is_never_resolved_at_all(monkeypatch):
    gateway = MockGateway().start()
    resolver = _ScriptedResolver([["203.0.113.10"]])
    monkeypatch.setattr(socket, "getaddrinfo", resolver)
    try:
        endpoint, outcomes, _ = build(binding_for(gateway))
        with endpoint:
            status, _ = raw_post(endpoint)
        assert status == 200
        assert len(gateway.requests) == 1
        assert resolver.calls == 0
    finally:
        gateway.stop()


# --------------------------------------------------------------------------
# 9. An ambiguous effect keeps what was actually observed.
# --------------------------------------------------------------------------


def test_an_ambiguous_stream_keeps_the_observed_status_and_forwarded_bytes():
    gateway = MockGateway(frames=CHUNK_TEXT).start()
    try:
        endpoint, outcomes, failures = build(binding_for(gateway))
        with endpoint:
            with pytest.raises(http.client.IncompleteRead):
                raw_post(endpoint)
        assert outcomes[0].kind == "effect_unknown"
        assert outcomes[0].http_status == 200
        assert outcomes[0].bytes_forwarded == len(CHUNK_TEXT)
        assert CAPABILITY not in repr(outcomes[0])
        assert PROXY_TOKEN not in repr(outcomes[0])
        assert failures == ["effect_unknown"]
    finally:
        gateway.stop()


def test_an_ambiguous_effect_without_a_status_records_no_status():
    gateway = MockGateway().start()
    gateway.stop()
    endpoint, outcomes, failures = build(binding_for(gateway))
    with endpoint:
        assert raw_post(endpoint)[0] == 409
    assert outcomes[0].kind == "unavailable"
    assert outcomes[0].http_status is None
    assert outcomes[0].bytes_forwarded == 0


# --------------------------------------------------------------------------
# 10. The gateway base path is the pinned one and nothing else.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("base_url", [
    "http://127.0.0.1:8311/v1/../../admin",
    "http://127.0.0.1:8311/v1/./admin",
    "http://127.0.0.1:8311//v1",
    "http://127.0.0.1:8311/v1%2f..%2fadmin",
    "http://127.0.0.1:8311/v1%2e%2e/admin",
    "http://127.0.0.1:8311/admin/v1",
    "http://127.0.0.1:8311/v1beta",
    "http://127.0.0.1:8311/",
])
def test_an_ambiguous_gateway_base_path_is_refused_before_the_gateway(base_url):
    with pytest.raises(ExperientialHarnessContractError):
        ExperientialGatewayRoute(
            route_id=ROUTE_ID,
            route_generation=gateway_route_generation(base_url, "chat/completions"),
            base_url=base_url,
            path="chat/completions",
        )


def test_the_pinned_gateway_base_path_is_admitted():
    base_url = "http://127.0.0.1:8311/v1"
    route = ExperientialGatewayRoute(
        route_id=ROUTE_ID,
        route_generation=gateway_route_generation(base_url, "chat/completions"),
        base_url=base_url,
        path="chat/completions",
    )
    assert route.base_url == base_url


# --------------------------------------------------------------------------
# 11. An outcome the owner could not record fails closed.
# --------------------------------------------------------------------------


def test_a_failing_outcome_callback_fails_closed_and_blocks_a_second_send():
    gateway = MockGateway().start()
    try:
        def refuse(outcome):
            raise RuntimeError("the owner could not record the outcome")

        endpoint, outcomes, failures = build(binding_for(gateway), on_outcome=refuse)
        with endpoint:
            with pytest.raises(http.client.IncompleteRead):
                raw_post(endpoint)
            assert raw_post(endpoint)[0] == 409
        assert len(gateway.requests) == 1
        assert endpoint.stopped_forwarding
        assert failures == ["effect_unknown"]
        assert outcomes == []
    finally:
        gateway.stop()


def test_a_failing_outcome_callback_after_a_refusal_still_fails_closed():
    gateway = MockGateway(status=429, frames=b"{}").start()
    try:
        def refuse(outcome):
            raise RuntimeError("the owner could not record the outcome")

        endpoint, outcomes, failures = build(binding_for(gateway), on_outcome=refuse)
        with endpoint:
            assert raw_post(endpoint)[0] == 409
            assert raw_post(endpoint)[0] == 409
        assert len(gateway.requests) == 1
        assert endpoint.stopped_forwarding
        # The owner never learned the outcome, so the attempt is unresolved
        # rather than refused: the consumer cannot claim there was no effect.
        assert failures == ["effect_unknown"]
        assert outcomes == []
    finally:
        gateway.stop()


# --------------------------------------------------------------------------
# 12. The responses protocol keeps its tool call and completion frames.
# --------------------------------------------------------------------------


def responses_binding_for(gateway: MockGateway) -> ExperientialHarnessBinding:
    return ExperientialHarnessBinding(
        session_id="attempt-session-1",
        model_id=MODEL,
        protocol="responses",
        route=route_for(gateway, path="responses"),
        client_capability=CAPABILITY,
    )


def test_the_responses_protocol_completes_a_tool_call_stream():
    frames = RESPONSES_TOOL_CALL + RESPONSES_COMPLETED
    gateway = MockGateway(frames=frames).start()
    try:
        endpoint, outcomes, failures = build(responses_binding_for(gateway))
        with endpoint:
            status, body = raw_post(endpoint, path="/v1/responses")
        assert status == 200
        assert body == frames
        assert gateway.requests[0]["path"] == "/v1/responses"
        assert outcomes[0].kind == "completed"
        assert outcomes[0].http_status == 200
        assert outcomes[0].bytes_forwarded == len(frames)
        assert failures == []
    finally:
        gateway.stop()


def test_a_responses_provider_error_frame_is_never_a_completion():
    frames = RESPONSES_FAILED + RESPONSES_COMPLETED
    gateway = MockGateway(frames=frames).start()
    try:
        endpoint, outcomes, failures = build(responses_binding_for(gateway))
        with endpoint:
            with pytest.raises(http.client.IncompleteRead):
                raw_post(endpoint, path="/v1/responses")
            assert raw_post(endpoint, path="/v1/responses")[0] == 409
        assert len(gateway.requests) == 1
        assert endpoint.stopped_forwarding
        assert failures == ["effect_unknown"]
        assert outcomes[0].kind == "effect_unknown"
        assert outcomes[0].http_status == 200
        assert outcomes[0].bytes_forwarded == len(frames)
    finally:
        gateway.stop()


def test_plan_policy_is_bound_to_generation_and_sent_by_owner():
    from control_plane.experiential_plan_policy import plan_policy_digest
    gateway = MockGateway().start()
    try:
        mode = "free_only"
        generation = gateway_route_generation(gateway.base_url, "chat/completions", mode)
        route = ExperientialGatewayRoute(
            ROUTE_ID, generation, gateway.base_url, "chat/completions", mode)
        with pytest.raises(ExperientialHarnessContractError, match="generation"):
            replace(route, plan_policy="free_and_uncensored")
        receipt = forward_to_gateway(
            ProviderRequest("chat/completions", "policy-session",
                            {"Content-Type": "application/json"},
                            b'{"model":"deepseek-v4.1-flash:free","stream":true,"messages":[]}'),
            route=route, token_loader=lambda: PROXY_TOKEN, on_chunk=lambda chunk: None)
        assert receipt.route_generation == generation
        assert len(gateway.requests) == 1
        assert gateway.requests[0]["headers"]["x-fabric-plan-policy"] == plan_policy_digest(mode)
        assert json.loads(gateway.requests[0]["body"])["model"].endswith(":free")
    finally:
        gateway.stop()
