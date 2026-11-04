#!/usr/bin/env python3
"""Hermetic mock-localhost tests for the experiential53 inference transport.

SOURCE MOCK PROOF ONLY.  Every dial in this suite lands on an in-process
mock gateway bound to an ephemeral ``127.0.0.1`` port.  There is no provider
contact, no credential read, no host mutation outside a temp directory, and
no installed-service claim: this suite proves the transport's executable
behaviour, not a qualified installation and not a worker START.

Run directly:

    python3 ops/native_fabric/experiential53/test_experiential_transport.py
"""
from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import experiential_pin as pin  # noqa: E402
import experiential_transport as transport  # noqa: E402

REFUSED = transport.ExperientialTransportRefused
PIN_REFUSED = pin.ExperientialPinRefused

#: A valid-shaped host-managed proxy token (never a provider key).
PROXY_TOKEN = "L" * 32
PROVIDER_KEY = "xpl_" + "k" * 40
ROUTE_ID = "experiential-gw-20261103"
ROUTE_GENERATION = "a" * 64
RUN_ID = "explabs-transport-20261103-01"
PACKET_ROOT = "packets/2026-11-03/explabs-01"
PROMPT = "Return exactly the word ok."

#: Both source constants patched: this is the TEST qualification harness.
#: The shipped generation keeps both False and refuses before any dial.
QUALIFIED = (
    mock.patch.object(pin, "TRANSPORT_INSTALLED", True),
    mock.patch.object(transport, "ROUTE_QUALIFIED", True),
)


def completion_frame(content: str = "ok", model: str = transport.MODEL,
                     usage: "dict | None" = None) -> bytes:
    frame = {
        "id": "chatcmpl-mock-1",
        "object": "chat.completion",
        "model": model,
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant", "content": content}}],
    }
    if usage is not None:
        frame["usage"] = usage
    return json.dumps(frame).encode()


class MockGateway(ThreadingHTTPServer):
    """Scripted OpenAI-compatible mock on an ephemeral loopback port."""

    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, script) -> None:  # noqa: ANN001
        self.script = script          # (method, path, headers, body) -> (status, ctype, payload)
        self.requests = []            # observed (method, path, dict-headers, body)
        self._lock = threading.Lock()
        super().__init__(("127.0.0.1", 0), _MockHandler)

    def observe(self, entry) -> None:  # noqa: ANN001
        with self._lock:
            self.requests.append(entry)

    def handle_error(self, request, client_address) -> None:  # noqa: ANN001
        # Abandoned client sockets (timeout test) are expected mock noise,
        # never test evidence: silence them like the incumbent endpoint does.
        pass

    @property
    def port(self) -> int:
        return self.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1/chat/completions"


class _MockHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "MockGateway"
    sys_version = ""

    def log_message(self, *args) -> None:  # noqa: ANN002
        pass

    def _respond(self, status: int, ctype: str, payload: bytes,
                 extra_headers: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(payload)
        self.close_connection = True

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b""
        entry = ("POST", self.path, dict(self.headers.items()), body)
        self.server.observe(entry)
        try:
            status, ctype, payload, extra = self.server.script(*entry)
        except Exception:
            self._respond(500, "application/json", b'{"error": {"message": "mock script error"}}')
            return
        self._respond(status, ctype, payload, extra)

    def do_GET(self) -> None:  # noqa: N802
        self.server.observe(("GET", self.path, dict(self.headers.items()), b""))
        self._respond(404, "application/json", b'{"error": {"message": "route not supported"}}')


def mock_route(server: MockGateway, token: str = PROXY_TOKEN) -> transport.GatewayRoute:
    return transport.GatewayRoute(
        host="127.0.0.1", port=server.port, proxy_token=token,
        route_id=ROUTE_ID, route_generation=ROUTE_GENERATION)


def admit_kwargs() -> dict:
    """Every admission gate satisfied (account B, authenticated readback)."""
    return {
        "registry_entry": {"enabled": True},
        "entitlement": {"verified": True},
        "retention_acknowledged": True,
        "sensitive_data_opt_in": True,
        "proprietary_code": False,
        "code_exposure_opt_in": False,
        "account": "b",
        "quota_readback": "authenticated",
    }


def run_ok(server: MockGateway, *, script=None, prompt: str = PROMPT, **overrides):
    """One transport call against the mock (happy path unless scripted).

    The server's own script is honoured when no explicit ``script`` is given,
    so error-status cases can preload a failing response.
    """
    if script is not None:
        server.script = script
    kwargs = dict(
        run_id=RUN_ID, packet_root=PACKET_ROOT, task_class="fix_build",
        pool="experiential", model="glm-5.3-uncensored",
        route=mock_route(server), prompt=prompt, system="",
        limits=transport.TransportLimits(connect_timeout_s=2.0, read_timeout_s=2.0),
        **admit_kwargs())
    kwargs.update(overrides)
    with QUALIFIED[0], QUALIFIED[1]:
        return transport.run_opt_in_inference(**kwargs)


class ShippedFailClosedTests(unittest.TestCase):
    """The shipped generation refuses before any dial.  Zero requests."""

    def setUp(self):
        self.server = MockGateway(
            lambda *a: (200, "application/json", completion_frame(), {}))
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def _dial_args(self) -> dict:
        return dict(
            run_id=RUN_ID, packet_root=PACKET_ROOT, task_class="fix_build",
            pool="experiential", model="glm-5.3-uncensored",
            route=mock_route(self.server), prompt=PROMPT, **admit_kwargs())

    def test_unqualified_route_refuses_before_dial(self):
        with self.assertRaisesRegex(REFUSED, "EXPERIENTIAL_GATEWAY_ROUTE_UNQUALIFIED"):
            with mock.patch.object(pin, "TRANSPORT_INSTALLED", True):
                transport.run_opt_in_inference(**self._dial_args())
        self.assertEqual(self.server.requests, [])

    def test_uninstalled_pin_transport_refuses_before_dial(self):
        with self.assertRaisesRegex(PIN_REFUSED, "EXPERIENTIAL_TRANSPORT_NOT_INSTALLED"):
            with mock.patch.object(transport, "ROUTE_QUALIFIED", True):
                transport.run_opt_in_inference(**self._dial_args())
        self.assertEqual(self.server.requests, [])

    def test_default_call_never_dials_even_with_both_gates_off(self):
        # Contract order: the pin admission gate (last in the pin law) fires
        # before the transport route gate; either way, zero requests dial.
        with self.assertRaisesRegex(PIN_REFUSED, "EXPERIENTIAL_TRANSPORT_NOT_INSTALLED"):
            transport.run_opt_in_inference(**self._dial_args())
        self.assertEqual(self.server.requests, [])

    def test_route_subcommand_reports_unqualified(self):
        import argparse
        self.assertEqual(transport._cli_route(argparse.Namespace()), 78)


class HappyPathTests(unittest.TestCase):
    """Exact wire contract of the ONE admitted POST."""

    def setUp(self):
        self.server = MockGateway(
            lambda *a: (200, "application/json", completion_frame(), {}))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_exact_frame_one_post_and_outcome(self):
        outcome = run_ok(self.server)
        self.assertEqual(len(self.server.requests), 1, "exactly one POST, no retry")
        method, path, headers, body = self.server.requests[0]
        self.assertEqual((method, path), ("POST", "/v1/chat/completions"))
        frame = json.loads(body)
        self.assertEqual(frame["model"], "glm-5.3-uncensored")
        self.assertIs(frame["stream"], False)
        self.assertEqual(frame["messages"], [{"role": "user", "content": PROMPT}])
        # billing01 corrective child: the frame now also carries the fixed
        # conservative worst-case output bound; everything else is unchanged.
        self.assertEqual(set(frame),
                         {"model", "messages", "stream", "max_tokens", "gateway"})
        self.assertEqual(frame["max_tokens"], transport.MAX_OUTPUT_TOKENS)
        self.assertEqual(outcome.max_output_tokens, transport.MAX_OUTPUT_TOKENS)
        # Experiential's default waterfall can perform multiple generation
        # dispatches inside one HTTP request. Pin both budgets to one and
        # disable internal provider-rung fallback, not just SDK retries.
        self.assertEqual(frame["gateway"], {
            "retry": {
                "max_attempts_per_route": 1,
                "max_total_attempts": 1,
                "backoff": {"type": "none"},
            },
            "routing": {"allow_fallbacks": False},
        })
        self.assertEqual(headers.get("Authorization"), f"Bearer {PROXY_TOKEN}")
        self.assertEqual(headers.get("Idempotency-Key"), RUN_ID)
        self.assertTrue(headers.get("Content-Type", "").startswith("application/json"))
        # packet identity is preserved verbatim on the outcome
        self.assertEqual(outcome.run_id, RUN_ID)
        self.assertEqual(outcome.packet_root, PACKET_ROOT)
        self.assertEqual((outcome.pool, outcome.model, outcome.task_class),
                         ("experiential", "glm-5.3-uncensored", "fix_build"))
        self.assertEqual(outcome.http_status, 200)
        self.assertEqual(outcome.content, "ok")
        self.assertEqual(outcome.model_echo, "glm-5.3-uncensored")
        self.assertGreater(outcome.bytes_received, 0)
        self.assertEqual(outcome.route_id, ROUTE_ID)
        self.assertEqual(outcome.route_generation, ROUTE_GENERATION)
        # the summary is metadata-only: no completion text.  billing01:
        # matched as a quoted JSON VALUE — the summary's typed key names
        # (e.g. the literal string "max_output_tokens") are metadata, not
        # completion content, and must not trip a blunt substring check.
        self.assertNotIn(json.dumps(outcome.content), json.dumps(outcome.summary()))
        self.assertIn("content_chars", json.dumps(outcome.summary()))

    def test_system_prompt_frames_system_role_first(self):
        outcome = run_ok(self.server, system="Be terse.")
        frame = json.loads(self.server.requests[0][3])
        self.assertEqual(
            frame["messages"],
            [{"role": "system", "content": "Be terse."},
             {"role": "user", "content": PROMPT}])
        self.assertEqual(outcome.content, "ok")

    def test_no_get_ever_issued(self):
        run_ok(self.server)
        self.assertTrue(all(r[0] == "POST" for r in self.server.requests))


class StatusFailClosedTests(unittest.TestCase):
    """Every non-200 status is a typed refusal; never a retry, never silent."""

    def _status_case(self, status: int, reason: str, *, ctype="application/json",
                     payload=b'{"error": {"message": "mock"}}', extra=None):
        observed = []

        def script(method, path, headers, body):
            observed.append(status)
            return status, ctype, payload, extra

        server = MockGateway(script)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with self.assertRaises(REFUSED) as caught:
                run_ok(server)
            self.assertEqual(caught.exception.reason, reason, f"status {status}")
            self.assertEqual(len(server.requests), 1, f"status {status}: one POST only")
            self.assertEqual(observed, [status], f"status {status}: no second attempt")
        finally:
            server.shutdown()
            server.server_close()

    def test_401_auth_refused(self):
        self._status_case(401, "GATEWAY_AUTH_REFUSED")

    def test_403_auth_refused(self):
        self._status_case(403, "GATEWAY_AUTH_REFUSED")

    def test_413_body_refused(self):
        self._status_case(413, "GATEWAY_REQUEST_TOO_LARGE")

    def test_429_rate_limited_never_retried_despite_retry_after(self):
        self._status_case(429, "GATEWAY_RATE_LIMITED",
                          extra={"Retry-After": "1"})

    def test_400_request_refused(self):
        self._status_case(400, "GATEWAY_REQUEST_REFUSED")

    def test_404_route_refused(self):
        self._status_case(404, "GATEWAY_REQUEST_REFUSED")

    def test_503_local_queue_full_refused(self):
        self._status_case(503, "GATEWAY_LOCAL_QUEUE_FULL")

    def test_504_queue_wait_refused(self):
        self._status_case(504, "GATEWAY_QUEUE_WAIT_EXPIRED")

    def test_500_upstream_refused(self):
        self._status_case(500, "GATEWAY_UPSTREAM_ERROR")

    def test_502_upstream_refused(self):
        self._status_case(502, "GATEWAY_UPSTREAM_ERROR")

    def test_204_is_never_silent_success(self):
        self._status_case(204, "GATEWAY_STATUS_REFUSED", payload=b"")


class RedirectRefusalTests(unittest.TestCase):
    def test_302_is_refused_and_never_followed(self):
        server = MockGateway(
            lambda *a: (302, "text/plain", b"moved", {"Location": "/v1/elsewhere"}))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with self.assertRaisesRegex(REFUSED, "GATEWAY_REDIRECT_REFUSED"):
                run_ok(server)
            paths = [r[1] for r in server.requests]
            self.assertEqual(paths, ["/v1/chat/completions"],
                             "the Location target must never be dialled")
        finally:
            server.shutdown()
            server.server_close()

    def test_307_is_refused_and_never_followed(self):
        server = MockGateway(
            lambda *a: (307, "text/plain", b"temp", {"Location": "/v1/chat/completions"}))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with self.assertRaisesRegex(REFUSED, "GATEWAY_REDIRECT_REFUSED"):
                run_ok(server)
            self.assertEqual(len(server.requests), 1, "no re-issued POST")
        finally:
            server.shutdown()
            server.server_close()


class ResponseLawTests(unittest.TestCase):
    def _case(self, payload: bytes, ctype: str, reason: str, detail: str = ""):
        server = MockGateway(lambda *a: (200, ctype, payload, {}))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with self.assertRaises(REFUSED) as caught:
                run_ok(server)
            self.assertEqual(caught.exception.reason, reason)
            if detail:
                self.assertIn(detail, caught.exception.detail)
            self.assertEqual(len(server.requests), 1)
        finally:
            server.shutdown()
            server.server_close()

    def test_malformed_json_refused(self):
        self._case(b"{not json", "application/json", "GATEWAY_RESPONSE_MALFORMED")

    def test_non_object_json_refused(self):
        self._case(b"[1,2]", "application/json", "GATEWAY_RESPONSE_MALFORMED")

    def test_empty_choices_refused(self):
        self._case(json.dumps({"choices": []}).encode(),
                   "application/json", "GATEWAY_RESPONSE_MALFORMED")

    def test_missing_message_refused(self):
        frame = {"choices": [{"index": 0}]}
        self._case(json.dumps(frame).encode(),
                   "application/json", "GATEWAY_RESPONSE_MALFORMED")

    def test_empty_content_refused(self):
        self._case(completion_frame(content="   "),
                   "application/json", "GATEWAY_RESPONSE_EMPTY")

    def test_substituted_model_refused(self):
        self._case(completion_frame(model="glm-5.3"),
                   "application/json", "GATEWAY_RESPONSE_MODEL_MISMATCH")

    def test_non_json_content_type_refused(self):
        self._case(completion_frame(), "text/plain", "GATEWAY_RESPONSE_MALFORMED")

    def test_oversized_response_refused(self):
        self._case(b"x" * (transport.MAX_RESPONSE_BYTES + 1),
                   "application/json", "GATEWAY_RESPONSE_TOO_LARGE")


class BoundedDialTests(unittest.TestCase):
    def test_timeout_is_typed_and_single(self):
        def script(method, path, headers, body):
            import time
            time.sleep(2.0)
            return 200, "application/json", completion_frame(), {}

        server = MockGateway(script)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            tiny = transport.TransportLimits(connect_timeout_s=0.2, read_timeout_s=0.3)
            with self.assertRaisesRegex(REFUSED, "GATEWAY_TIMEOUT"):
                run_ok(server, limits=tiny)
            self.assertEqual(len(server.requests), 1)
        finally:
            server.shutdown()
            server.server_close()

    def test_unreachable_port_is_typed(self):
        dead = socket.socket()
        dead.bind(("127.0.0.1", 0))
        dead_port = dead.getsockname()[1]
        dead.close()  # closed: nothing listens
        route = transport.GatewayRoute(
            host="127.0.0.1", port=dead_port, proxy_token=PROXY_TOKEN,
            route_id=ROUTE_ID, route_generation=ROUTE_GENERATION)
        tiny = transport.TransportLimits(connect_timeout_s=0.5, read_timeout_s=0.5)
        with QUALIFIED[0], QUALIFIED[1]:
            with self.assertRaisesRegex(REFUSED, "GATEWAY_UNREACHABLE"):
                transport.run_opt_in_inference(
                    run_id=RUN_ID, packet_root=PACKET_ROOT, task_class="fix_build",
                    pool="experiential", model="glm-5.3-uncensored",
                    route=route, prompt=PROMPT, limits=tiny, **admit_kwargs())

    def test_limits_cannot_be_loosened_past_caps(self):
        with self.assertRaisesRegex(REFUSED, "TRANSPORT_LIMITS_INVALID"):
            transport.TransportLimits(connect_timeout_s=0.1,
                                      read_timeout_s=transport.MAX_READ_TIMEOUT_S + 1)
        with self.assertRaisesRegex(REFUSED, "TRANSPORT_LIMITS_INVALID"):
            transport.TransportLimits(connect_timeout_s=0, read_timeout_s=1)


class NoAmbientProxyTests(unittest.TestCase):
    """A poisoned proxy environment must not leak the POST off loopback."""

    def test_poisoned_env_still_reaches_loopback_mock(self):
        server = MockGateway(lambda *a: (200, "application/json", completion_frame(), {}))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        poisoned = {
            "http_proxy": "http://127.0.0.1:1", "https_proxy": "http://127.0.0.1:1",
            "all_proxy": "http://127.0.0.1:1", "HTTP_PROXY": "http://127.0.0.1:1",
            "HTTPS_PROXY": "http://127.0.0.1:1", "ALL_PROXY": "http://127.0.0.1:1",
            "no_proxy": "",
        }
        try:
            with mock.patch.dict(os.environ, poisoned):
                outcome = run_ok(server)
            self.assertEqual(outcome.http_status, 200)
            self.assertEqual(len(server.requests), 1)
            # ...and the request that arrived is the real one, not a replay
            self.assertEqual(json.loads(server.requests[0][3])["model"],
                             "glm-5.3-uncensored")
        finally:
            server.shutdown()
            server.server_close()


class SecretFreeSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.server = MockGateway(lambda *a: (200, "application/json", completion_frame(), {}))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_token_never_appears_on_outcome_or_summary(self):
        outcome = run_ok(self.server)
        surfaces = (repr(outcome), str(outcome), json.dumps(outcome.summary()),
                    json.dumps(vars(outcome)))
        for surface in surfaces:
            self.assertNotIn(PROXY_TOKEN, surface)
        # the route binding hides it too
        route = mock_route(self.server)
        self.assertNotIn(PROXY_TOKEN, repr(route))

    def test_refusal_details_never_carry_token_or_prompt(self):
        server = MockGateway(lambda *a: (401, "application/json",
                                         b'{"error": {"message": "unauthorized"}}', {}))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with self.assertRaises(REFUSED) as caught:
                run_ok(server, prompt=PROMPT)
            surfaces = (str(caught.exception), caught.exception.reason,
                        caught.exception.detail)
            for surface in surfaces:
                self.assertNotIn(PROXY_TOKEN, surface)
                self.assertNotIn(PROMPT, surface)
        finally:
            server.shutdown()
            server.server_close()

    def test_provider_key_is_refused_as_route_token(self):
        with self.assertRaisesRegex(REFUSED, "PROVIDER_KEY_REFUSED"):
            run_ok(self.server, route=mock_route(self.server, token=PROVIDER_KEY))
        self.assertEqual(self.server.requests, [])


class RouteLawTests(unittest.TestCase):
    def _route(self, **overrides) -> transport.GatewayRoute:
        fields = dict(host="127.0.0.1", port=8311, proxy_token=PROXY_TOKEN,
                      route_id=ROUTE_ID, route_generation=ROUTE_GENERATION)
        fields.update(overrides)
        return transport.GatewayRoute(**fields)

    def _refusal(self, route, reason: str) -> None:
        with self.assertRaises(REFUSED) as caught:
            transport._validate_route(route)
        self.assertEqual(caught.exception.reason, reason)

    def test_exact_loopback_route_valid(self):
        self.assertEqual(transport._validate_route(self._route()), self._route())

    def test_non_pinned_hosts_refused(self):
        for host in ("localhost", "127.0.0.2", "0.0.0.0", "::1",
                     "gateway.internal", "example.com"):
            self._refusal(self._route(host=host), "GATEWAY_ROUTE_NOT_LOOPBACK")

    def test_schemes_refused(self):
        for scheme in ("ftp", "unix", "file", ""):
            self._refusal(self._route(scheme=scheme), "GATEWAY_ROUTE_SCHEME_REFUSED")

    def test_ports_refused(self):
        for port in (0, -1, 65536, "8311", True, 1.5):
            self._refusal(self._route(port=port), "GATEWAY_ROUTE_PORT_INVALID")

    def test_base_path_refused(self):
        for path in ("/v1/", "/v2", "/v1/chat", "", "/V1"):
            self._refusal(self._route(base_path=path),
                          "GATEWAY_ROUTE_BASE_PATH_REFUSED")

    def test_route_identity_refused(self):
        self._refusal(self._route(route_id="bad id!"), "GATEWAY_ROUTE_ID_INVALID")
        self._refusal(self._route(route_generation="A" * 64),
                      "GATEWAY_ROUTE_GENERATION_INVALID")
        self._refusal(self._route(route_generation="z" * 64),
                      "GATEWAY_ROUTE_GENERATION_INVALID")

    def test_token_shape_refused(self):
        # non-string tokens (never a valid type)
        for token in (None, 123, b"bytes", 1.5):
            self._refusal(self._route(proxy_token=token), "GATEWAY_TOKEN_REQUIRED")
        # malformed strings
        for token in ("short", "", "x" * 300,
                      "has space inside 24chars token!!",
                      "line\nbreak-token-24+chars!!"):
            self._refusal(self._route(proxy_token=token), "GATEWAY_TOKEN_INVALID")

    def test_route_object_type_refused(self):
        self._refusal(("127.0.0.1", 8311), "GATEWAY_ROUTE_INVALID")

    def test_attempt_seam_named_not_shimmed(self):
        # PR #1920 is unmerged in this generation: the explicit probe refuses.
        if transport.attempt_seam_available():
            self.skipTest("seam merged on this base; refusal law not applicable")
        with self.assertRaisesRegex(REFUSED, "EXPERIENTIAL_ATTEMPT_SEAM_UNAVAILABLE"):
            transport.require_attempt_seam()


class PacketIdentityTests(unittest.TestCase):
    def test_invalid_run_id_refused(self):
        server = MockGateway(lambda *a: (200, "application/json", completion_frame(), {}))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            for bad in ("", "bad id!", None, "x" * 200):
                with self.assertRaisesRegex((REFUSED, PIN_REFUSED), "RUN_ID_INVALID"):
                    run_ok(server, run_id=bad)
            self.assertEqual(server.requests, [])
        finally:
            server.shutdown()
            server.server_close()

    def test_invalid_packet_root_refused(self):
        server = MockGateway(lambda *a: (200, "application/json", completion_frame(), {}))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            for bad in ("", None, "no spaces allowed here", "x" * 300, "../escape"):
                with self.assertRaisesRegex(REFUSED, "PACKET_ROOT_INVALID"):
                    run_ok(server, packet_root=bad)
            self.assertEqual(server.requests, [])
        finally:
            server.shutdown()
            server.server_close()


class PromptBoundTests(unittest.TestCase):
    def test_prompt_laws(self):
        server = MockGateway(lambda *a: (200, "application/json", completion_frame(), {}))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            for kwargs in ({"prompt": ""}, {"prompt": "   "}, {"prompt": None},
                           {"prompt": 7},
                           {"prompt": "x" * (transport.MAX_PROMPT_CHARS + 1)},
                           {"system": "y" * (transport.MAX_SYSTEM_CHARS + 1)},
                           {"system": 7}):
                with self.assertRaises(REFUSED):
                    run_ok(server, **kwargs)
            self.assertEqual(server.requests, [])
        finally:
            server.shutdown()
            server.server_close()

    def test_encoded_body_cap_refused(self):
        server = MockGateway(lambda *a: (200, "application/json", completion_frame(), {}))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            # NUL json-escapes to six bytes even with ensure_ascii=False and is
            # not stripped whitespace, so a max-char prompt still exceeds the
            # 1 MiB encoded cap: the frame is refused before any dial.
            huge = "\x00" * transport.MAX_PROMPT_CHARS
            with self.assertRaisesRegex(REFUSED, "REQUEST_BODY_TOO_LARGE"):
                run_ok(server, prompt=huge)
            self.assertEqual(server.requests, [])
        finally:
            server.shutdown()
            server.server_close()


class AdmissionLawThroughTransportTests(unittest.TestCase):
    """The pin law runs unchanged inside the transport, in contract order."""

    def setUp(self):
        self.server = MockGateway(lambda *a: (200, "application/json", completion_frame(), {}))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def _dial(self, **admit_overrides):
        kwargs = admit_kwargs()
        kwargs.update(admit_overrides)
        return run_ok(self.server, **kwargs)

    def test_wrong_pool_carrier_refused_before_dial(self):
        with self.assertRaisesRegex(PIN_REFUSED, "GLM_POOL_CARRIER_REFUSED"):
            self._dial(pool="glm")
        self.assertEqual(self.server.requests, [])

    def test_canonical_glm_slug_refused(self):
        with self.assertRaisesRegex(PIN_REFUSED, "EXPERIENTIAL_MODEL_DISTINCT"):
            self._dial(model="glm-5.3")
        with self.assertRaisesRegex(PIN_REFUSED, "EXPERIENTIAL_MODEL_SLUG_MISMATCH"):
            self._dial(model="glm-5.3-uncensored-v2")
        self.assertEqual(self.server.requests, [])

    def test_auto_pin_refused(self):
        with self.assertRaisesRegex(PIN_REFUSED, "MANUAL_POOL_REQUIRED"):
            self._dial(pool="auto", model="auto")
        self.assertEqual(self.server.requests, [])

    def test_forbidden_task_class_refused(self):
        with self.assertRaisesRegex(PIN_REFUSED, "EXPERIENTIAL_TASK_CLASS_FORBIDDEN"):
            self._dial(task_class="review")
        self.assertEqual(self.server.requests, [])

    def test_provider_disabled_refused(self):
        with self.assertRaisesRegex(PIN_REFUSED, "PROVIDER_DISABLED"):
            self._dial(registry_entry={"enabled": False})
        self.assertEqual(self.server.requests, [])

    def test_entitlement_unverified_refused(self):
        with self.assertRaisesRegex(PIN_REFUSED, "ENTITLEMENT_UNVERIFIED"):
            self._dial(entitlement=None)
        self.assertEqual(self.server.requests, [])

    def test_retention_ack_required_per_request(self):
        with self.assertRaisesRegex(PIN_REFUSED, "RETENTION_UNVERIFIED"):
            self._dial(retention_acknowledged=False)
        self.assertEqual(self.server.requests, [])

    def test_sensitive_data_opt_in_required_per_request(self):
        with self.assertRaisesRegex(PIN_REFUSED, "SENSITIVE_DATA_DISCLOSURE_REQUIRED"):
            self._dial(sensitive_data_opt_in=False)
        self.assertEqual(self.server.requests, [])

    def test_proprietary_code_requires_independent_opt_in(self):
        with self.assertRaisesRegex(PIN_REFUSED, "PROPRIETARY_CODE_EXPOSURE_REFUSED"):
            self._dial(proprietary_code=True, code_exposure_opt_in=False)
        self.assertEqual(self.server.requests, [])
        # with the independent opt-in it dials exactly once
        outcome = self._dial(proprietary_code=True, code_exposure_opt_in=True)
        self.assertEqual(outcome.http_status, 200)
        self.assertEqual(len(self.server.requests), 1)

    def test_account_a_stays_held(self):
        with self.assertRaisesRegex(PIN_REFUSED, "ACCOUNT_A_HELD_HTTP403"):
            self._dial(account="a")
        self.assertEqual(self.server.requests, [])

    def test_unknown_account_refused(self):
        with self.assertRaisesRegex(PIN_REFUSED, "ACCOUNT_UNKNOWN"):
            self._dial(account="c")
        self.assertEqual(self.server.requests, [])

    def test_account_b_without_authenticated_readback_refused(self):
        for readback in (None, "assumed", "unverified", ""):
            with self.assertRaisesRegex(PIN_REFUSED, "QUOTA_READBACK_UNAUTHENTICATED"):
                self._dial(quota_readback=readback)
        self.assertEqual(self.server.requests, [])

    def test_no_fallback_after_refusal(self):
        verdict = pin.fallback_refused("experiential", "glm-5.3-uncensored",
                                       "experiential", "glm-5.3-uncensored")
        self.assertEqual(verdict["reason"], "FAILED_PIN_NOT_RETRIED")
        self.assertIsNone(verdict["fallback"])
        self.assertIsNone(verdict["escalate_to"])


class CliTests(unittest.TestCase):
    @staticmethod
    def _run_cli(*argv: str) -> tuple:
        import subprocess
        script = HERE / "experiential_transport.py"
        return subprocess.run(
            [sys.executable, str(script), *argv],
            capture_output=True, text=True, timeout=120,
            cwd=str(tempfile.gettempdir()))

    def test_status_reports_fail_closed(self):
        done = self._run_cli("status")
        self.assertIn("ROUTE_QUALIFIED=False", done.stdout)
        self.assertIn("PIN_TRANSPORT_INSTALLED=False", done.stdout)
        self.assertIn("FAIL_CLOSED_SHIPPED", done.stdout)
        self.assertEqual(done.returncode, 78)
        self.assertNotIn(PROXY_TOKEN, done.stdout + done.stderr)

    def test_route_refuses_without_dialing(self):
        done = self._run_cli("route")
        self.assertIn("EXPERIENTIAL_GATEWAY_ROUTE_UNQUALIFIED", done.stderr)
        self.assertEqual(done.returncode, 78)

    def test_mockproof_runs_hermetic_proof(self):
        done = self._run_cli("mockproof")
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])
        self.assertIn("MOCKPROOF", done.stdout)


class OutputTokenBoundTests(unittest.TestCase):
    """The fixed conservative max_tokens law: emitted on every frame,
    tighten-only, refused before any dial when violated."""

    def setUp(self):
        self.server = MockGateway(
            lambda *a: (200, "application/json", completion_frame(), {}))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_default_cap_is_the_module_constant(self):
        self.assertEqual(transport.MAX_OUTPUT_TOKENS, 512)
        outcome = run_ok(self.server)
        frame = json.loads(self.server.requests[0][3])
        self.assertEqual(frame["max_tokens"], 512)
        self.assertEqual(outcome.max_output_tokens, 512)
        # The gateway retry policy rides the SAME frame, unchanged: one
        # vendor dispatch total, no internal provider-rung fallback.
        self.assertEqual(frame["gateway"], {
            "retry": {
                "max_attempts_per_route": 1,
                "max_total_attempts": 1,
                "backoff": {"type": "none"},
            },
            "routing": {"allow_fallbacks": False},
        })

    def test_cap_can_be_tightened_per_request(self):
        outcome = run_ok(self.server, max_output_tokens=64)
        frame = json.loads(self.server.requests[0][3])
        self.assertEqual(frame["max_tokens"], 64)
        self.assertEqual(outcome.max_output_tokens, 64)

    def test_cap_cannot_be_loosened_and_never_dials(self):
        for bad in (transport.MAX_OUTPUT_TOKENS + 1, 4096, 0, -5,
                    True, 1.5, "512"):
            with self.assertRaisesRegex(REFUSED, "MAX_OUTPUT_TOKENS_INVALID"):
                run_ok(self.server, max_output_tokens=bad)
        self.assertEqual(self.server.requests, [])


class ProviderRequestIdTests(unittest.TestCase):
    """The provider ``X-Request-Id`` response handle: captured, validated,
    surfaced as opaque bounded metadata — distinct from the Idempotency-Key,
    and usable by the billing owner without any second dial."""

    HANDLE = "req-01HV2Zexample9f8e7d6c5b4a"

    def _server_with(self, status: int, extra: "dict | None" = None,
                     payload: "bytes | None" = None):
        server = MockGateway(
            lambda *a: (status, "application/json",
                        payload if payload is not None else completion_frame(),
                        extra or {}))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server

    def _run(self, server, **overrides):
        try:
            return run_ok(server, **overrides)
        finally:
            server.shutdown()
            server.server_close()

    def test_positive_handle_is_surfaced_as_opaque_metadata(self):
        server = self._server_with(200, {"X-Request-Id": self.HANDLE})
        outcome = self._run(server)
        self.assertEqual(outcome.provider_request_id, self.HANDLE)
        self.assertEqual(outcome.provider_request_id_status,
                         transport.PROVIDER_REQUEST_ID_PRESENT)
        # distinct from the locally sent Idempotency-Key
        self.assertNotEqual(outcome.provider_request_id, outcome.idempotency_key)
        # reflected in outcome/metadata only — and the ONLY dial is the
        # single chat/completions POST (no Cost API call, no GET, ever)
        self.assertIn(self.HANDLE, json.dumps(outcome.summary()))
        self.assertEqual(len(server.requests), 1)
        self.assertEqual(server.requests[0][0], "POST")
        self.assertEqual(server.requests[0][1], "/v1/chat/completions")

    def test_header_name_lookup_is_case_insensitive(self):
        server = self._server_with(200, {"x-request-id": self.HANDLE})
        outcome = self._run(server)
        self.assertEqual(outcome.provider_request_id, self.HANDLE)

    def test_missing_handle_is_typed_never_synthesized(self):
        server = self._server_with(200)
        outcome = self._run(server)
        self.assertIsNone(outcome.provider_request_id)
        self.assertEqual(outcome.provider_request_id_status,
                         transport.PROVIDER_REQUEST_ID_MISSING)
        self.assertIn('"provider_request_id": null',
                      json.dumps(outcome.summary()))

    def test_malformed_handle_is_discarded_raw_value_never_surfaced(self):
        for bad in ("bad handle with spaces", "tab\there", "x" * 300, "",
                    "  "):
            server = self._server_with(200, {"X-Request-Id": bad})
            try:
                outcome = run_ok(server)
            finally:
                server.shutdown()
                server.server_close()
            self.assertIsNone(outcome.provider_request_id, bad)
            self.assertEqual(outcome.provider_request_id_status,
                             transport.PROVIDER_REQUEST_ID_MALFORMED, bad)
            # the malformed RAW value must never reach any surface (only
            # values with visible content can leak; "" trivially cannot)
            if bad.strip():
                surfaces = (json.dumps(outcome.summary()), str(outcome),
                            repr(outcome))
                for surface in surfaces:
                    self.assertNotIn(bad, surface, bad)

    def test_handle_on_failed_post_reaches_the_typed_refusal(self):
        # vendor law: a failed/disconnected request may still incur charge,
        # so the validated handle rides the typed refusal for reconciliation
        server = self._server_with(401, {"X-Request-Id": self.HANDLE},
                                   b'{"error": {"message": "unauthorized"}}')
        try:
            with self.assertRaises(REFUSED) as caught:
                run_ok(server)
            self.assertEqual(caught.exception.reason, "GATEWAY_AUTH_REFUSED")
            self.assertIn(f"provider_request_id={self.HANDLE}",
                          caught.exception.detail)
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(len(server.requests), 1)

    def test_no_handle_on_failed_post_is_omitted_not_fabricated(self):
        server = self._server_with(429, {"Retry-After": "1"},
                                   b'{"error": {"message": "slow down"}}')
        try:
            with self.assertRaises(REFUSED) as caught:
                run_ok(server)
            self.assertNotIn("provider_request_id", caught.exception.detail)
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(len(server.requests), 1, "one POST, never retried")


class CostReconciliationTests(unittest.TestCase):
    """Cost is never invented: missing/unusable inline observations stay
    COST_RECONCILIATION_PENDING (never zero USD), a type-safe observation is
    explicitly inline-only, and no provider/billing endpoint is ever dialed."""

    def _run_with_usage(self, usage, *, expect_refusal: "str | None" = None):
        server = MockGateway(
            lambda *a: (200, "application/json", completion_frame(usage=usage), {}))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            if expect_refusal is not None:
                with self.assertRaises(REFUSED) as caught:
                    run_ok(server)
                return None, caught.exception, server
            outcome = run_ok(server)
            return outcome, None, server
        finally:
            server.shutdown()
            server.server_close()

    def _assert_one_post_no_provider_dial(self, server):
        self.assertEqual(len(server.requests), 1)
        self.assertTrue(all(r[0] == "POST" for r in server.requests))
        self.assertEqual({r[1] for r in server.requests},
                         {"/v1/chat/completions"})

    def test_idempotent_response_without_usage_is_pending_not_zero(self):
        outcome, refusal, server = self._run_with_usage(None)
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome.cost_status, "COST_RECONCILIATION_PENDING")
        self.assertIsNone(outcome.cost_usd_observed)
        self.assertIs(outcome.cost_settled, False)
        self.assertEqual(outcome.cost_detail, "usage_frame_missing")
        summary = json.dumps(outcome.summary())
        self.assertIn('"cost_status": "COST_RECONCILIATION_PENDING"', summary)
        self.assertIn('"cost_usd_observed": null', summary)
        self.assertIn('"cost_settled": false', summary)
        self.assertNotIn('"cost_usd_observed": 0', summary)
        self._assert_one_post_no_provider_dial(server)

    def test_usage_without_cost_is_pending(self):
        outcome, _, server = self._run_with_usage({"prompt_tokens": 5})
        self.assertEqual(outcome.cost_status, "COST_RECONCILIATION_PENDING")
        self.assertIsNone(outcome.cost_usd_observed)
        self.assertEqual(outcome.cost_detail, "usage_cost_missing")
        self._assert_one_post_no_provider_dial(server)

    def test_type_safe_cost_is_inline_observation_not_settled(self):
        outcome, _, server = self._run_with_usage({"cost": 0.0042,
                                                   "is_byok": False})
        self.assertEqual(outcome.cost_status,
                         "COST_RECONCILIATION_OBSERVED_INLINE")
        self.assertAlmostEqual(outcome.cost_usd_observed, 0.0042)
        self.assertIs(outcome.cost_settled, False)
        self.assertEqual(outcome.cost_detail, "inline_observation_not_settled")
        summary = json.dumps(outcome.summary())
        self.assertIn("COST_RECONCILIATION_OBSERVED_INLINE", summary)
        self.assertIn('"cost_settled": false', summary)
        self._assert_one_post_no_provider_dial(server)

    def test_untrusted_cost_is_never_surfaced_as_a_dollar_figure(self):
        for usage, detail in (
                ({"cost": "0.01"}, "usage_cost_unusable_type"),
                ({"cost": True}, "usage_cost_unusable_type"),
                ({"cost": [1, 2]}, "usage_cost_unusable_type"),
                ({"cost": -1}, "usage_cost_unusable_value"),
                ({"cost": 1e400}, "usage_cost_unusable_value"),
                ({"cost": 101.0}, "usage_cost_unusable_value"),
        ):
            outcome, _, server = self._run_with_usage(usage)
            self.assertEqual(outcome.cost_status,
                             "COST_RECONCILIATION_PENDING", usage)
            # the unusable value is never surfaced as a dollar figure
            self.assertIsNone(outcome.cost_usd_observed, usage)
            self.assertIn('"cost_usd_observed": null',
                          json.dumps(outcome.summary()))
            self.assertEqual(outcome.cost_detail, detail, usage)
            server.shutdown()
            server.server_close()

    def test_unusable_usage_frame_is_pending(self):
        outcome, _, server = self._run_with_usage("3 cents")
        self.assertEqual(outcome.cost_status, "COST_RECONCILIATION_PENDING")
        self.assertIsNone(outcome.cost_usd_observed)
        self.assertEqual(outcome.cost_detail, "usage_frame_unusable")
        self._assert_one_post_no_provider_dial(server)

    def test_non_boolean_is_byok_poisons_the_observation_not_the_content(self):
        outcome, _, server = self._run_with_usage({"cost": 0.01,
                                                   "is_byok": "true"})
        self.assertEqual(outcome.cost_status, "COST_RECONCILIATION_PENDING")
        self.assertIsNone(outcome.cost_usd_observed)
        self.assertEqual(outcome.cost_detail, "usage_is_byok_unusable")
        self.assertEqual(outcome.content, "ok")
        self._assert_one_post_no_provider_dial(server)


class ByokFailClosedTests(unittest.TestCase):
    """usage.is_byok=true fails closed for the platform-funded-only pool."""

    def test_byok_refused_no_retry_completion_discarded(self):
        server = MockGateway(
            lambda *a: (200, "application/json",
                        completion_frame(usage={"cost": 0.01,
                                                "is_byok": True}), {}))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with self.assertRaisesRegex(REFUSED, "COST_BYOK_REFUSED") as caught:
                run_ok(server)
            self.assertIn("platform-funded", caught.exception.detail)
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(len(server.requests), 1, "one POST, no retry")

    def test_explicit_false_byok_is_the_normal_inline_path(self):
        server = MockGateway(
            lambda *a: (200, "application/json",
                        completion_frame(usage={"cost": 0.01,
                                                "is_byok": False}), {}))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            outcome = run_ok(server)
            self.assertEqual(outcome.cost_status,
                             "COST_RECONCILIATION_OBSERVED_INLINE")
        finally:
            server.shutdown()
            server.server_close()


class ExactModelEchoTests(unittest.TestCase):
    """The echoed model must equal the pinned slug byte-for-byte."""

    def _case(self, echoed_model: str):
        server = MockGateway(
            lambda *a: (200, "application/json",
                        completion_frame(model=echoed_model), {}))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with self.assertRaises(REFUSED) as caught:
                run_ok(server)
            self.assertEqual(caught.exception.reason,
                             "GATEWAY_RESPONSE_MODEL_MISMATCH")
            self.assertEqual(len(server.requests), 1)
        finally:
            server.shutdown()
            server.server_close()

    def test_uppercase_variant_refused(self):
        self._case("GLM-5.3-UNCENSORED")

    def test_mixed_case_variant_refused(self):
        self._case("Glm-5.3-Uncensored")

    def test_casefold_is_no_longer_accepted(self):
        # the exact slug casefolds to itself, so the incumbent case-insensitive
        # law could not tell these apart; the exact law does
        self.assertNotEqual("GLM-5.3-uncensored".casefold(), "GLM-5.3-uncensored")
        self._case("GLM-5.3-uncensored")

    def test_whitespace_padded_variants_refused(self):
        self._case("glm-5.3-uncensored ")
        self._case(" glm-5.3-uncensored")

    def test_near_alias_refused(self):
        self._case("glm-5.3-uncensored-v2")
        self._case("glm-5.3")


class MalformedMetadataSecretFreeTests(unittest.TestCase):
    """Rejected provider metadata must not enter any public refusal surface."""

    PROMPT_MARKER = "PROMPT_SENTINEL_2042_PRIVATE"
    TOKEN_MARKER = "xpl_2042_fixture_private_token"

    def _assert_secret_free(self, refusal):
        surfaces = (refusal.reason, refusal.detail, str(refusal), repr(refusal))
        for surface in surfaces:
            for marker in (self.PROMPT_MARKER, self.TOKEN_MARKER,
                           PROXY_TOKEN, PROVIDER_KEY):
                self.assertNotIn(marker, surface)
        self.assertLessEqual(len(refusal.detail), 128)

    def _case(self, payload, content_type, reason):
        server = MockGateway(lambda *a: (200, content_type, payload, {}))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with self.assertRaises(REFUSED) as caught:
                run_ok(server, prompt=self.PROMPT_MARKER)
            self.assertEqual(caught.exception.reason, reason)
            self.assertEqual([request[0] for request in server.requests], ["POST"])
            self.assertEqual(server.requests[0][1], "/v1/chat/completions")
            self._assert_secret_free(caught.exception)
        finally:
            server.shutdown()
            server.server_close()

    def test_wrong_string_model_does_not_reflect_prompt_or_token(self):
        model = f"wrong/{self.PROMPT_MARKER}/{self.TOKEN_MARKER}/{PROXY_TOKEN}"
        self._case(completion_frame(model=model), "application/json",
                   "GATEWAY_RESPONSE_MODEL_MISMATCH")

    def test_wrong_object_model_does_not_reflect_nested_private_values(self):
        model = {"unexpected": {"prompt": self.PROMPT_MARKER,
                                "token": self.TOKEN_MARKER,
                                "proxy": PROXY_TOKEN, "provider": PROVIDER_KEY}}
        self._case(completion_frame(model=model), "application/json",
                   "GATEWAY_RESPONSE_MODEL_MISMATCH")

    def test_wrong_array_model_does_not_reflect_nested_private_values(self):
        model = [self.PROMPT_MARKER, {"secret": self.TOKEN_MARKER}, PROXY_TOKEN]
        self._case(completion_frame(model=model), "application/json",
                   "GATEWAY_RESPONSE_MODEL_MISMATCH")

    def test_non_json_header_does_not_reflect_private_parameters(self):
        content_type = (
            f"text/plain; prompt={self.PROMPT_MARKER}; token={self.TOKEN_MARKER}; "
            f"proxy={PROXY_TOKEN}"
        )
        self._case(completion_frame(), content_type, "GATEWAY_RESPONSE_MALFORMED")

    def test_classification_helper_does_not_reflect_unvalidated_content_type(self):
        refusal = transport._classify_http_error(
            200, f"text/plain; prompt={self.PROMPT_MARKER}; token={self.TOKEN_MARKER}")
        self.assertEqual(refusal.reason, "GATEWAY_RESPONSE_MALFORMED")
        self._assert_secret_free(refusal)


def run_mockproof() -> bool:
    """The CLI-embedded hermetic proof.  Loopback mock only; no provider.

    Returns True when the full happy path plus the one-POST/redirect/no-proxy
    laws pass in-process.  SOURCE MOCK PROOF ONLY — not a live provider call,
    not an installed service, not a worker START.
    """
    checks: list[tuple[str, bool]] = []

    server = MockGateway(lambda *a: (200, "application/json", completion_frame(), {}))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        outcome = run_ok(server)
        checks.append(("happy_path_one_post",
                       outcome.content == "ok" and len(server.requests) == 1))
        checks.append(("packet_identity",
                       outcome.run_id == RUN_ID and outcome.packet_root == PACKET_ROOT))
        # billing01 laws: cost pending (never zero), bounded output, BYOK
        # fail-closed, provider reconciliation handle surfaced
        checks.append(("cost_pending_not_zero",
                       outcome.cost_status == transport.COST_RECONCILIATION_PENDING
                       and outcome.cost_usd_observed is None
                       and outcome.cost_settled is False))
        checks.append(("bounded_output",
                       json.loads(server.requests[0][3])["max_tokens"]
                       == transport.MAX_OUTPUT_TOKENS
                       and outcome.max_output_tokens == transport.MAX_OUTPUT_TOKENS))

        server.script = (lambda *a: (429, "application/json",
                                     b'{"error": {"message": "slow down"}}',
                                     {"Retry-After": "1"}))
        try:
            run_ok(server)
            checks.append(("429_refused", False))
        except REFUSED as exc:
            checks.append(("429_refused_once",
                           exc.reason == "GATEWAY_RATE_LIMITED"
                           and len(server.requests) == 2))

        server.script = (lambda *a: (302, "text/plain", b"moved",
                                     {"Location": "/v1/elsewhere"}))
        try:
            run_ok(server)
            checks.append(("redirect_refused", False))
        except REFUSED as exc:
            checks.append(("redirect_never_followed",
                           exc.reason == "GATEWAY_REDIRECT_REFUSED"
                           and all(r[1] == "/v1/chat/completions"
                                   for r in server.requests)))

        server.script = (lambda *a: (200, "application/json",
                                     completion_frame(usage={"cost": 0.01,
                                                             "is_byok": True}),
                                     {}))
        try:
            run_ok(server)
            checks.append(("byok_refused", False))
        except REFUSED as exc:
            checks.append(("byok_fail_closed",
                           exc.reason == "COST_BYOK_REFUSED"
                           and len(server.requests) == 4))

        server.script = (lambda *a: (200, "application/json", completion_frame(),
                                     {"X-Request-Id": "req-mockproof-1"}))
        try:
            surfaced = run_ok(server)
            checks.append(("provider_request_id_surfaced",
                           surfaced.provider_request_id == "req-mockproof-1"
                           and surfaced.provider_request_id_status
                           == transport.PROVIDER_REQUEST_ID_PRESENT
                           and surfaced.cost_status
                           == transport.COST_RECONCILIATION_PENDING
                           and len(server.requests) == 5))
        except Exception:
            checks.append(("provider_request_id_surfaced", False))
    except Exception:
        checks.append(("unexpected_error", False))
    finally:
        server.shutdown()
        server.server_close()

    ok = all(passed for _, passed in checks)
    for name, passed in checks:
        print(f"  mock[{name}]={'PASS' if passed else 'FAIL'}")
    return ok


def main() -> int:
    unittest.main(module=sys.modules[__name__], argv=[sys.argv[0]], exit=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
