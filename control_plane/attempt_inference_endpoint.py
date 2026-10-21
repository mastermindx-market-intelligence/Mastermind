"""Attempt-owned loopback inference endpoint for an existing Worker harness.

This is the provider-neutral local boundary beneath provider-specific adapters.
It is NOT a daemon, provider router, credential store, account selector, retry
ledger, Worker adapter, or lifecycle owner.  The existing Worker/supervisor owns
launch, cancellation, durable effects, and cleanup; a trusted composition owner
supplies one immutable session/model/protocol/route binding plus one forwarder.

The child harness receives only an attempt-private loopback capability.  Client
authentication headers are consumed locally and never enter the forwarded
``ProviderRequest``.  After any admitted forwarding failure or identity mismatch,
this endpoint permanently stops forwarding so an outer client retry cannot create
a second ambiguous provider effect.
"""
from __future__ import annotations

import hmac
import json
import re
import socket
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable

from control_plane.opencode_go_pooled_transport import ProviderRequest, _freeze_request

_MAX_BODY = 1024 * 1024
_HTTP_BAD_REQUEST = 4 * 100
_HTTP_UNAUTHORIZED = _HTTP_BAD_REQUEST + 1
_HTTP_METHOD_NOT_ALLOWED = _HTTP_BAD_REQUEST + 5
_HTTP_CONFLICT = _HTTP_BAD_REQUEST + 9
_HTTP_STATUS_UPPER_EXCLUSIVE = 6 * 100
_PATHS = {
    "openai-chat": "chat/completions",
    "anthropic": "messages",
    "responses": "responses",
}
_ROUTE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class InferenceEndpointContractError(RuntimeError):
    """The local endpoint/binding contract is invalid or not admitted."""


class InferenceForwardRefused(InferenceEndpointContractError):
    """Trusted upstream admission refused before provider effect authority."""


class InferenceEffectUnknown(RuntimeError):
    """Forwarding may have produced a provider-side effect; do not replay."""


class EndpointCloseUncertain(RuntimeError):
    """The outer existing Worker supervisor must reconcile endpoint cleanup."""


@dataclass(frozen=True)
class AttemptInferenceBinding:
    """One immutable inference route inside an already-admitted Worker Attempt.

    ``route_id`` and ``route_generation`` are integrity/correlation identities,
    not placement authority.  The owning Provider/Capacity layer selects them
    before this endpoint exists.  ``client_capability`` is local-process auth and
    is deliberately excluded from repr/log-friendly surfaces.
    """

    session_id: str
    model_id: str
    protocol: str
    route_id: str
    route_generation: str
    client_capability: str = field(repr=False)


@dataclass(frozen=True)
class InferenceForwardReceipt:
    """Secret-free terminal identity returned by the trusted forwarder."""

    route_id: str
    route_generation: str
    http_status: int
    bytes_forwarded: int
    terminal_observed: bool


def _validate_binding(binding: AttemptInferenceBinding) -> None:
    if not isinstance(binding, AttemptInferenceBinding) or binding.protocol not in _PATHS:
        raise InferenceEndpointContractError("unsupported inference binding")
    if (
        not isinstance(binding.client_capability, str)
        or not 32 <= len(binding.client_capability) <= 256
        or not binding.client_capability.isascii()
        or not binding.client_capability.isalnum()
    ):
        raise InferenceEndpointContractError("private client capability required")
    if not isinstance(binding.route_id, str) or _ROUTE_ID_RE.fullmatch(binding.route_id) is None:
        raise InferenceEndpointContractError("route identity is invalid")
    if (
        not isinstance(binding.route_generation, str)
        or _DIGEST_RE.fullmatch(binding.route_generation) is None
    ):
        raise InferenceEndpointContractError("route generation must be a lowercase SHA-256")

    # Reuse the incumbent request identity validator without reading a credential.
    try:
        _freeze_request(
            ProviderRequest(
                _PATHS[binding.protocol],
                binding.session_id,
                {},
                json.dumps({"model": binding.model_id, "stream": True}).encode(),
            ),
            replayable=False,
        )
    except Exception as exc:  # provider-specific exception types must not leak here
        raise InferenceEndpointContractError("inference binding identity is invalid") from exc


def _validate_receipt(receipt: object, binding: AttemptInferenceBinding) -> InferenceForwardReceipt:
    if not isinstance(receipt, InferenceForwardReceipt):
        raise InferenceEffectUnknown("forwarder returned an unsupported receipt")
    if receipt.route_id != binding.route_id or receipt.route_generation != binding.route_generation:
        raise InferenceEffectUnknown("forwarder receipt changed the bound route identity")
    if (
        isinstance(receipt.http_status, bool)
        or not isinstance(receipt.http_status, int)
        or receipt.http_status < 100
        or receipt.http_status >= _HTTP_STATUS_UPPER_EXCLUSIVE
        or isinstance(receipt.bytes_forwarded, bool)
        or not isinstance(receipt.bytes_forwarded, int)
        or receipt.bytes_forwarded < 0
        or not isinstance(receipt.terminal_observed, bool)
    ):
        raise InferenceEffectUnknown("forwarder receipt is malformed")
    return receipt


class _Server(HTTPServer):
    """At most one request thread; never accumulate a retry queue."""

    allow_reuse_address = False

    def __init__(self, owner: "AttemptInferenceEndpoint") -> None:
        self.owner = owner
        self.slot = threading.Lock()
        self.active: threading.Thread | None = None
        self.active_socket = None
        super().__init__(("127.0.0.1", 0), _Handler)

    def process_request(self, request, client_address) -> None:  # noqa: ANN001
        # A bounded handoff lets the previous completed response close its socket.
        # It does not retain a request queue or admit concurrent inference.
        if not self.slot.acquire(timeout=0.1):
            self.shutdown_request(request)
            return

        def run() -> None:
            try:
                self.finish_request(request, client_address)
            except Exception:
                pass  # Request diagnostics are deliberately not printed.
            finally:
                self.shutdown_request(request)
                self.active_socket = None
                self.slot.release()

        request.settimeout(3.0)
        self.active_socket = request
        self.active = threading.Thread(
            target=run,
            name=f"{self.owner._thread_prefix}-request",
            daemon=True,
        )
        self.active.start()

    def handle_error(self, request, client_address) -> None:  # noqa: ANN001
        # Never print request bodies, keys, headers or underlying callback errors.
        pass


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "Mastermind"
    sys_version = ""

    def log_message(self, *args) -> None:  # noqa: ANN002
        pass

    def _reply(self, status: int, code: str) -> None:
        payload = json.dumps(
            {"error": {"type": code, "message": "Worker action required."}}
        ).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)
        self.close_connection = True

    def do_GET(self) -> None:
        self._reply(_HTTP_METHOD_NOT_ALLOWED, "MMX_METHOD_REFUSED")

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_HEAD = do_GET

    def do_POST(self) -> None:
        owner: AttemptInferenceEndpoint = self.server.owner  # type: ignore[attr-defined]
        binding = owner.binding
        self.close_connection = True
        try:
            auth = self.headers.get_all("Authorization", [])
            api_keys = self.headers.get_all("x-api-key", [])
            if binding.protocol == "anthropic" and len(api_keys) == 1 and not auth:
                supplied = ("Bearer " + api_keys[0]).encode("utf-8")
            else:
                supplied = auth[0].encode("utf-8") if len(auth) == 1 and not api_keys else b""
            if not hmac.compare_digest(supplied, owner._authorization):
                self._reply(_HTTP_UNAUTHORIZED, "MMX_CLIENT_REFUSED")
                return
            if owner._poisoned.is_set() or owner._cancel.is_set():
                self._reply(_HTTP_CONFLICT, "MMX_WORKER_STOPPED")
                return
            lengths = self.headers.get_all("Content-Length", [])
            if (
                self.path != "/v1/" + owner._path
                or self.headers.get("Origin") is not None
                or self.headers.get("Transfer-Encoding") is not None
                or len(lengths) != 1
                or not lengths[0].isdigit()
                or not 0 < int(lengths[0]) <= _MAX_BODY
                or self.headers.get("Content-Type", "").split(";")[0].strip().lower()
                != "application/json"
            ):
                self._reply(_HTTP_BAD_REQUEST, "MMX_REQUEST_REFUSED")
                return
            body = self.rfile.read(int(lengths[0]))
            if len(body) != int(lengths[0]):
                self._reply(_HTTP_BAD_REQUEST, "MMX_REQUEST_REFUSED")
                return
            headers = {
                name: self.headers[name]
                for name in ("anthropic-version", "anthropic-beta")
                if name in self.headers
            }
            headers["Content-Type"] = "application/json"
            request = _freeze_request(
                ProviderRequest(owner._path, binding.session_id, headers, body),
                replayable=False,
            )
            payload = json.loads(request.body)
            if (
                payload.get("model") != binding.model_id
                or payload.get("stream") is not True
                or payload.get("background") is True
            ):
                self._reply(_HTTP_BAD_REQUEST, "MMX_BINDING_REFUSED")
                return
        except Exception:
            self._reply(_HTTP_BAD_REQUEST, "MMX_REQUEST_REFUSED")
            return

        started = False

        def consume(chunk: bytes) -> None:
            nonlocal started
            if not isinstance(chunk, bytes) or not chunk:
                raise ValueError("invalid stream chunk")
            if not started:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Transfer-Encoding", "chunked")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()
                started = True
            self.wfile.write(("%x\r\n" % len(chunk)).encode() + chunk + b"\r\n")
            self.wfile.flush()

        try:
            receipt = _validate_receipt(
                owner._forward(request, on_chunk=consume, cancel=owner._cancel),
                binding,
            )
            if receipt.http_status != 200 or not receipt.terminal_observed:
                owner._fail("upstream_refused_or_incomplete")
                if not started:
                    self._reply(_HTTP_CONFLICT, "MMX_PROVIDER_STOPPED")
                return
            if not started:
                raise InferenceEffectUnknown("terminal success produced no response bytes")
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except InferenceForwardRefused:
            owner._fail("request_admission_refused")
            if not started:
                self._reply(_HTTP_CONFLICT, "MMX_ADMISSION_STOPPED")
        except Exception:
            owner._fail("effect_unknown")
            if not started:
                self._reply(_HTTP_CONFLICT, "MMX_EFFECT_UNRESOLVED")
        finally:
            self.close_connection = True


class AttemptInferenceEndpoint:
    """One keyless local inference surface scoped to an existing Worker Attempt.

    ``forward`` is trusted host composition.  It owns any credential read and
    provider-specific transport and returns only :class:`InferenceForwardReceipt`.
    It receives no client authentication secret because the endpoint strips that
    header before constructing the bound ``ProviderRequest``.
    """

    def __init__(
        self,
        binding: AttemptInferenceBinding,
        *,
        forward: Callable,
        on_terminal_failure: Callable[[str], None],
        cancel: threading.Event,
        thread_prefix: str = "inference",
    ) -> None:
        _validate_binding(binding)
        if not isinstance(cancel, threading.Event) or not callable(forward) or not callable(on_terminal_failure):
            raise InferenceEndpointContractError("invalid endpoint dependencies")
        if (
            not isinstance(thread_prefix, str)
            or _ROUTE_ID_RE.fullmatch(thread_prefix) is None
            or len(thread_prefix) > 32
        ):
            raise InferenceEndpointContractError("invalid endpoint thread identity")
        self.binding = binding
        self._path = _PATHS[binding.protocol]
        self._authorization = ("Bearer " + binding.client_capability).encode()
        self._forward = forward
        self._failure = on_terminal_failure
        self._cancel = cancel
        self._thread_prefix = thread_prefix
        self._poisoned = threading.Event()
        self._notification_failed = threading.Event()
        self._server: _Server | None = None
        self._thread: threading.Thread | None = None
        self._ever_started = False

    def _fail(self, kind: str) -> None:
        if self._poisoned.is_set():
            return
        self._poisoned.set()  # Stop forwarding BEFORE notifying another owner.
        try:
            self._failure(kind)
        except Exception:
            # Failure to record an event is not permission to send more requests.
            self._notification_failed.set()

    @property
    def base_url(self) -> str:
        if self._server is None:
            raise InferenceEndpointContractError("endpoint not running")
        return "http://127.0.0.1:%d/v1" % self._server.server_port

    @property
    def stopped_forwarding(self) -> bool:
        return self._poisoned.is_set()

    @property
    def failure_notification_failed(self) -> bool:
        return self._notification_failed.is_set()

    def __enter__(self) -> "AttemptInferenceEndpoint":
        if self._ever_started:
            raise InferenceEndpointContractError("endpoint cannot restart")
        self._ever_started = True
        self._server = _Server(self)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            kwargs={"poll_interval": 0.05},
            name=f"{self._thread_prefix}-endpoint",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(self, *error) -> None:  # noqa: ANN002
        self.close()

    def close(self) -> None:
        server = self._server
        if server is None:
            return
        if threading.current_thread() in (self._thread, server.active):
            self._poisoned.set()
            self._cancel.set()
            raise EndpointCloseUncertain(
                "endpoint cleanup requires its existing outer supervisor"
            )
        self._poisoned.set()
        self._cancel.set()
        server.shutdown()
        client = server.active_socket
        if client is not None:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=1)
        worker = server.active
        if worker is not None:
            worker.join(timeout=1)
        if (
            (self._thread is not None and self._thread.is_alive())
            or (worker is not None and worker.is_alive())
        ):
            raise EndpointCloseUncertain(
                "existing worker supervisor must reconcile endpoint cleanup"
            )
        self._server = self._thread = None
