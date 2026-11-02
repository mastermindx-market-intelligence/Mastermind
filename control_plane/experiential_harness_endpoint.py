"""Attempt-owned OpenAI-compatible consumer for the Experiential Labs gateway.

The Experiential Labs localhost gateway (PR #1849) is an outbound OpenAI
compatible transport.  Its own SDK helper is gateway-side wiring, not a Fabric
consumer: nothing in it owns an Attempt, a route binding or a fail-stop
effect.  This module is the missing consumer seam.  A real OpenAI Python SDK
client can point at the attempt-owned loopback endpoint produced here and
complete a chat stream through the gateway.

Nothing new is granted or scheduled by this module:

* The attempt-owned loopback boundary, its refusal semantics and its fail-stop
  latch stay in :mod:`control_plane.attempt_inference_endpoint`.  This module
  composes that boundary; it never edits, replaces or softens it.
* The gateway keeps owning the upstream ``xpl_`` provider key, its key
  rotation, its rolling admission and its provider refusal policy.  This module
  reads no provider key at all.  It holds only the *local scoped proxy token*
  that the gateway itself demands, and only for the lifetime of one forward.
* The child process sees only its private attempt capability.  The proxy token
  never reaches the child, never reaches a receipt and never reaches a log.
* There is no queue, no scheduler, no model choice and no price or admission
  decision here.  The model slug is the owner's already-selected slug; this
  module refuses any other slug rather than silently substituting one.
* One accepted child request produces exactly one upstream POST.  There is no
  client retry, no HTTP retry, no key rotation and no fallback route.

The route is *pinned*: only a loopback gateway base URL is admitted, and the
route generation is the attested identity of that exact pinned target (see
:func:`gateway_route_generation`).  The identity in the returned receipt is
re-checked against the binding by the existing endpoint, so a drifted or
misremembered route cannot present itself as the approved one.
"""
from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import math
import socket
import threading
import time
from dataclasses import dataclass, field, replace
from typing import Callable, Optional
from urllib.parse import urlsplit

from control_plane.attempt_inference_endpoint import (
    AttemptInferenceBinding,
    AttemptInferenceEndpoint,
    InferenceEffectUnknown,
    InferenceEndpointContractError,
    InferenceForwardReceipt,
    InferenceForwardRefused,
)
from control_plane.opencode_go_pooled_transport import ProviderRequest, _freeze_request

MAX_STREAM_BYTES = 64 * 1024 * 1024
MAX_ERROR_BYTES = 256 * 1024
MAX_EVENT_BYTES = 1024 * 1024
MAX_IDEMPOTENCY_KEY = 128
MAX_TOKEN_LENGTH = 512

GATEWAY_CHAT_PATH = "chat/completions"
GATEWAY_RESPONSES_PATH = "responses"
#: Protocol -> concrete gateway route.  The gateway admits exactly these two
#: streaming routes; the attempt endpoint's protocol names are reused verbatim
#: so one binding drives both ends.
GATEWAY_PATHS = {
    "openai-chat": GATEWAY_CHAT_PATH,
    "responses": GATEWAY_RESPONSES_PATH,
}

_LOOPBACK_NAMES = frozenset({"localhost"})


class ExperientialHarnessContractError(RuntimeError):
    """The local consumer/gateway composition contract is invalid or not admitted."""


class ExperientialHarnessUnavailable(RuntimeError):
    """The gateway could not be reached; nothing was sent and nothing took effect."""


class ExperientialHarnessEffectUnknown(RuntimeError):
    """The gateway may have taken effect; an automatic replay is not safe."""


@dataclass(frozen=True)
class GatewayOutcome:
    """One secret-free terminal outcome of an attempt-owned gateway forward."""

    kind: str
    http_status: Optional[int]
    route_id: str
    route_generation: str
    model_id: str
    bytes_forwarded: int


@dataclass(frozen=True)
class ExperientialGatewayRoute:
    """One pinned Experiential Labs gateway target and its attested identity.

    ``route_generation`` must be the value of
    :func:`gateway_route_generation` for this exact ``base_url``/``path`` pair.
    That makes the identity describe the target that is actually dialled, so a
    changed port, path or host stops being the approved route.
    """

    route_id: str
    route_generation: str
    base_url: str
    path: str

    def __post_init__(self) -> None:
        if not isinstance(self.route_id, str) or not self.route_id.strip():
            raise ExperientialHarnessContractError("gateway route identity is required")
        if self.path not in set(GATEWAY_PATHS.values()):
            raise ExperientialHarnessContractError("unsupported gateway route path")
        _normalize_base_url(self.base_url)
        if gateway_route_generation(self.base_url, self.path) != self.route_generation:
            raise ExperientialHarnessContractError(
                "route generation does not attest this pinned gateway target"
            )


@dataclass(frozen=True)
class ExperientialHarnessBinding:
    """One immutable inference binding inside an already-admitted Attempt.

    ``model_id`` is the model slug the owner already selected.  It is never
    rewritten here, and a child that asks for any other slug is refused before
    the gateway is contacted.
    """

    session_id: str
    model_id: str
    protocol: str
    route: ExperientialGatewayRoute
    client_capability: str = field(repr=False)


@dataclass(frozen=True)
class GatewayStreamReceipt:
    """Secret-free terminal identity returned by the gateway forwarder."""

    route_id: str
    route_generation: str
    http_status: int
    bytes_forwarded: int
    terminal_observed: bool


def gateway_route_generation(base_url: str, path: str) -> str:
    """The attested identity of one pinned gateway target.

    The owner computes this once for the approved loopback gateway and injects
    it with the route.  The forwarder recomputes it from the target it is about
    to dial, so a route that drifted after attestation is refused instead of
    being forwarded under the approved identity.
    """
    normalized = str(base_url).rstrip("/")
    return hashlib.sha256(f"{normalized}\n{path}".encode("utf-8")).hexdigest()


def _normalize_base_url(base_url: str) -> str:
    """Admit only a loopback gateway base URL; never a public bind."""
    if not isinstance(base_url, str) or not base_url.strip():
        raise ExperientialHarnessContractError("gateway base URL is required")
    parts = urlsplit(base_url)
    if parts.scheme not in ("http", "https"):
        raise ExperientialHarnessContractError("gateway base URL must be http or https")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ExperientialHarnessContractError(
            "gateway base URL must not carry credentials, a query or a fragment"
        )
    if not _is_loopback_host(parts.hostname or ""):
        raise ExperientialHarnessContractError("gateway base URL must be a loopback address")
    return base_url.rstrip("/")


def _is_loopback_host(host: str) -> bool:
    candidate = host.strip("[]").lower()
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        pass
    if candidate not in _LOOPBACK_NAMES:
        return False
    try:
        infos = socket.getaddrinfo(candidate, None)
    except OSError:
        return False
    addresses = {info[4][0] for info in infos}
    if not addresses:
        return False
    try:
        return all(ipaddress.ip_address(address).is_loopback for address in addresses)
    except ValueError:
        return False


def _bounded_seconds(value: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExperientialHarnessContractError("invalid gateway timeout")
    if not math.isfinite(value) or not 0 < value <= maximum:
        raise ExperientialHarnessContractError("invalid gateway timeout")
    return float(value)


def _load_token(token_loader: Callable[[], str]) -> str:
    """Read the local scoped proxy token.  It is never logged or returned."""
    try:
        token = token_loader()
    except Exception:
        raise ExperientialHarnessContractError("local scoped gateway token is unavailable") from None
    if (
        not isinstance(token, str)
        or not 24 <= len(token) <= MAX_TOKEN_LENGTH
        or not token.isascii()
        or any(ord(char) < 33 or ord(char) > 126 for char in token)
    ):
        raise ExperientialHarnessContractError("local scoped gateway token is unusable")
    return token


class _StreamTerminal:
    """Bounded SSE framing observer.  It never rewrites or drops provider frames.

    Frames are observed only to learn when the provider stream reached its
    terminal event.  The bytes handed to the child are the provider's bytes.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self.buffer = bytearray()
        self.data: list[bytes] = []
        self.event = b""
        self.event_bytes = 0
        self.terminal = False

    def _dispatch(self) -> None:
        if not self.data:
            self.event, self.event_bytes = b"", 0
            return
        data = b"\n".join(self.data)
        self.data = []
        event, self.event = self.event, b""
        self.event_bytes = 0
        if self.terminal:
            return
        if self.path == GATEWAY_CHAT_PATH:
            if data.strip() == b"[DONE]":
                self.terminal = True
            return
        try:
            payload = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return
        if not isinstance(payload, dict):
            return
        if payload.get("error") is not None or payload.get("type") in {
            "error",
            "response.failed",
            "response.incomplete",
            "response.cancelled",
        }:
            raise ValueError("provider error frame")
        if payload.get("type") == "response.completed":
            response = payload.get("response")
            if isinstance(response, dict) and response.get("status") == "completed":
                self.terminal = True

    def _line(self, line: bytes) -> None:
        self.event_bytes += len(line) + 1
        if self.event_bytes > MAX_EVENT_BYTES:
            raise ValueError("event size exceeded")
        if not line:
            self._dispatch()
        elif line.startswith(b"data:"):
            value = line[5:]
            self.data.append(value[1:] if value.startswith(b" ") else value)
        elif line.startswith(b"event:"):
            self.event = line[6:].lstrip(b" ")

    def finish(self) -> None:
        if self.buffer.endswith(b"\r"):
            self._line(bytes(self.buffer[:-1]))
            self.buffer.clear()

    def feed(self, chunk: bytes) -> None:
        self.buffer.extend(chunk)
        while True:
            positions = [p for p in (self.buffer.find(b"\n"), self.buffer.find(b"\r")) if p >= 0]
            if not positions:
                break
            pos = min(positions)
            if self.buffer[pos] == 13 and pos + 1 == len(self.buffer):
                break
            step = 2 if self.buffer[pos : pos + 2] == b"\r\n" else 1
            line = bytes(self.buffer[:pos])
            del self.buffer[:pos + step]
            self._line(line)
        if len(self.buffer) + self.event_bytes > MAX_EVENT_BYTES:
            raise ValueError("event size exceeded")


def _open_connection(parts, timeout: float):  # noqa: ANN001
    if parts.scheme == "https":
        return http.client.HTTPSConnection(parts.hostname, parts.port or 443, timeout=timeout)
    return http.client.HTTPConnection(parts.hostname, parts.port or 80, timeout=timeout)


def _drain_error_body(response) -> None:  # noqa: ANN001
    """Read a bounded refusal body and discard it.  It is never logged or sent."""
    remaining = MAX_ERROR_BYTES + 1
    while remaining > 0:
        try:
            chunk = response.read1(min(16384, remaining))
        except Exception:
            return
        if not chunk:
            return
        remaining -= len(chunk)


def forward_to_gateway(
    request: ProviderRequest,
    *,
    route: ExperientialGatewayRoute,
    token_loader: Callable[[], str],
    on_chunk: Callable[[bytes], None],
    cancel: Optional[threading.Event] = None,
    idempotency_key: Optional[str] = None,
    idle_timeout_seconds: float = 60.0,
    total_timeout_seconds: float = 900.0,
) -> GatewayStreamReceipt:
    """Forward one approved streaming request to the pinned gateway.

    The caller owns the gateway's local scoped proxy token; this function
    reads it only for this one request and never returns, logs or forwards it.
    There is exactly one POST.  A definite upstream refusal is reported as a
    non-200 receipt, and anything that may have taken effect is raised as
    :class:`ExperientialHarnessEffectUnknown`.
    """
    frozen = _freeze_request(request, replayable=False)
    try:
        payload = json.loads(frozen.body)
    except (ValueError, UnicodeDecodeError):
        raise ExperientialHarnessContractError("request body must be valid JSON") from None
    if not isinstance(payload, dict) or payload.get("stream") is not True:
        raise ExperientialHarnessContractError("foreground streaming request required")
    if payload.get("background") is True:
        raise ExperientialHarnessContractError("background requests are not admitted")
    if not callable(token_loader) or not callable(on_chunk):
        raise ExperientialHarnessContractError("forwarder dependencies must be callable")
    if cancel is not None and not isinstance(cancel, threading.Event):
        raise ExperientialHarnessContractError("invalid cancellation signal")
    idle = _bounded_seconds(idle_timeout_seconds, 300.0)
    total = _bounded_seconds(total_timeout_seconds, 1800.0)
    if idempotency_key is not None and (
        not isinstance(idempotency_key, str)
        or not idempotency_key
        or len(idempotency_key) > MAX_IDEMPOTENCY_KEY
        or not idempotency_key.isascii()
        or any(ord(char) < 33 or ord(char) > 126 for char in idempotency_key)
    ):
        raise ExperientialHarnessContractError("invalid idempotency key")
    # Re-attest the pinned target: the identity in the receipt must describe
    # the target this call actually dials.
    if gateway_route_generation(route.base_url, route.path) != route.route_generation:
        raise ExperientialHarnessContractError(
            "pinned gateway target does not match its attested route generation"
        )
    token = _load_token(token_loader)
    if cancel is not None and cancel.is_set():
        raise ExperientialHarnessContractError("attempt cancelled before submission")

    parts = urlsplit(route.base_url)
    url_path = parts.path.rstrip("/") + "/" + route.path
    deadline = time.monotonic() + total
    connection = None
    response = None
    submitted = False
    forwarded = 0

    def refresh_timeout() -> None:
        if cancel is not None and cancel.is_set():
            raise ExperientialHarnessEffectUnknown("attempt cancelled after submission")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ExperientialHarnessEffectUnknown("gateway request exceeded its deadline")
        window = max(0.001, min(idle, remaining))
        connection.timeout = window
        sock = getattr(connection, "sock", None)
        if sock is not None:
            sock.settimeout(window)

    try:
        connection = _open_connection(parts, min(idle, total))
        headers = {
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            connection.request("POST", url_path, body=frozen.body, headers=headers)
            submitted = True
        except Exception:
            # A failed connect never wrote a request byte; anything else may
            # have reached the gateway.
            if getattr(connection, "sock", None) is None:
                raise ExperientialHarnessUnavailable("gateway connection was refused") from None
            raise ExperientialHarnessEffectUnknown("gateway request write failed") from None
        refresh_timeout()
        response = connection.getresponse()
        status = response.status
        if isinstance(status, bool) or not isinstance(status, int) or not 100 <= status <= 599:
            raise ExperientialHarnessEffectUnknown("gateway returned an invalid status")
        if status != 200:
            _drain_error_body(response)
            return GatewayStreamReceipt(
                route_id=route.route_id,
                route_generation=route.route_generation,
                http_status=status,
                bytes_forwarded=0,
                terminal_observed=False,
            )
        content_type = (response.getheader("Content-Type") or "").split(";")[0].strip().lower()
        if content_type != "text/event-stream":
            raise ExperientialHarnessEffectUnknown("gateway did not return an event stream")
        observer = _StreamTerminal(route.path)
        while True:
            refresh_timeout()
            chunk = response.read1(16384)
            if not isinstance(chunk, bytes):
                raise ExperientialHarnessEffectUnknown("gateway returned invalid stream bytes")
            if not chunk:
                observer.finish()
                if not observer.terminal:
                    raise ExperientialHarnessEffectUnknown("gateway stream ended before its terminal frame")
                break
            forwarded += len(chunk)
            if forwarded > MAX_STREAM_BYTES:
                raise ExperientialHarnessEffectUnknown("gateway stream exceeded its size bound")
            observer.feed(chunk)
            on_chunk(chunk)
            if observer.terminal:
                break
        return GatewayStreamReceipt(
            route_id=route.route_id,
            route_generation=route.route_generation,
            http_status=200,
            bytes_forwarded=forwarded,
            terminal_observed=True,
        )
    except (
        ExperientialHarnessContractError,
        ExperientialHarnessUnavailable,
        ExperientialHarnessEffectUnknown,
    ):
        raise
    except Exception:
        if submitted:
            raise ExperientialHarnessEffectUnknown("gateway forwarding failed") from None
        raise ExperientialHarnessUnavailable("gateway forwarding failed") from None
    finally:
        for item in (response, connection):
            if item is not None:
                try:
                    item.close()
                except Exception:
                    pass


class ExperientialHarnessEndpoint:
    """One attempt-owned OpenAI-compatible consumer for a pinned gateway route.

    The child receives only its private attempt capability.  The local scoped
    proxy token is read inside the forwarder and never crosses into the child,
    a receipt, an outcome or a log.  A refusal, a cancelled stream or an
    ambiguous upstream effect stops this endpoint permanently so an outer client
    retry cannot create a second ambiguous provider effect.
    """

    def __init__(
        self,
        binding: ExperientialHarnessBinding,
        *,
        token_loader: Callable[[], str],
        on_terminal_failure: Callable[[str], None],
        cancel: threading.Event,
        forward: Callable = forward_to_gateway,
        on_outcome: Optional[Callable[[GatewayOutcome], None]] = None,
        idempotency_key_loader: Optional[Callable[[], Optional[str]]] = None,
        timeout: float = 900.0,
        idle_timeout_seconds: float = 60.0,
        total_timeout_seconds: float = 900.0,
        thread_prefix: str = "experiential",
    ) -> None:
        if not isinstance(binding, ExperientialHarnessBinding):
            raise ExperientialHarnessContractError("unsupported harness binding")
        if not isinstance(binding.route, ExperientialGatewayRoute):
            raise ExperientialHarnessContractError("unsupported gateway route")
        if binding.protocol not in GATEWAY_PATHS:
            raise ExperientialHarnessContractError("unsupported gateway protocol")
        if GATEWAY_PATHS[binding.protocol] != binding.route.path:
            raise ExperientialHarnessContractError("gateway route does not match the bound protocol")
        if not isinstance(cancel, threading.Event) or not callable(token_loader):
            raise ExperientialHarnessContractError("invalid endpoint dependencies")
        if not callable(on_terminal_failure) or not callable(forward):
            raise ExperientialHarnessContractError("invalid endpoint dependencies")
        if on_outcome is not None and not callable(on_outcome):
            raise ExperientialHarnessContractError("invalid endpoint dependencies")
        if idempotency_key_loader is not None and not callable(idempotency_key_loader):
            raise ExperientialHarnessContractError("invalid endpoint dependencies")
        self._timeout = _bounded_seconds(timeout, 1800.0)
        self._idle_timeout = _bounded_seconds(idle_timeout_seconds, 300.0)
        self._total_timeout = _bounded_seconds(total_timeout_seconds, 1800.0)
        self._route = binding.route
        self._on_outcome = on_outcome
        self._idempotency_key_loader = idempotency_key_loader
        core_binding = AttemptInferenceBinding(
            session_id=binding.session_id,
            model_id=binding.model_id,
            protocol=binding.protocol,
            route_id=binding.route.route_id,
            route_generation=binding.route.route_generation,
            client_capability=binding.client_capability,
        )

        def forward_request(request, *, on_chunk, cancel):  # noqa: ANN001
            outcome = GatewayOutcome(
                kind="effect_unknown",
                http_status=None,
                route_id=self._route.route_id,
                route_generation=self._route.route_generation,
                model_id=core_binding.model_id,
                bytes_forwarded=0,
            )
            try:
                payload = json.loads(request.body)
                if not isinstance(payload, dict) or payload.get("model") != core_binding.model_id:
                    raise ExperientialHarnessContractError("model slug is not the bound slug")
                key = None
                if self._idempotency_key_loader is not None:
                    try:
                        key = self._idempotency_key_loader()
                    except Exception:
                        raise ExperientialHarnessContractError(
                            "idempotency key is unavailable"
                        ) from None
                result = forward(
                    request,
                    route=self._route,
                    token_loader=token_loader,
                    on_chunk=on_chunk,
                    cancel=cancel,
                    idempotency_key=key,
                    idle_timeout_seconds=self._idle_timeout,
                    total_timeout_seconds=self._total_timeout,
                )
                if not isinstance(result, GatewayStreamReceipt):
                    raise ExperientialHarnessEffectUnknown("gateway returned an unsupported receipt")
                if (
                    result.route_id != self._route.route_id
                    or result.route_generation != self._route.route_generation
                ):
                    # The receipt claims a different route than the one this
                    # attempt is bound to; its effect cannot be trusted.
                    raise ExperientialHarnessEffectUnknown(
                        "gateway receipt changed the bound route identity"
                    )
                outcome = GatewayOutcome(
                    kind="completed"
                    if result.terminal_observed and result.http_status == 200
                    else "refused",
                    http_status=result.http_status,
                    route_id=result.route_id,
                    route_generation=result.route_generation,
                    model_id=core_binding.model_id,
                    bytes_forwarded=result.bytes_forwarded,
                )
                return InferenceForwardReceipt(
                    route_id=result.route_id,
                    route_generation=result.route_generation,
                    http_status=result.http_status,
                    bytes_forwarded=result.bytes_forwarded,
                    terminal_observed=result.terminal_observed,
                )
            except ExperientialHarnessContractError:
                outcome = replace(outcome, kind="refused")
                raise InferenceForwardRefused(
                    "Experiential consumer contract refused the request"
                ) from None
            except ExperientialHarnessUnavailable:
                outcome = replace(outcome, kind="unavailable")
                raise InferenceForwardRefused("Experiential gateway is unavailable") from None
            except ExperientialHarnessEffectUnknown:
                outcome = replace(outcome, kind="effect_unknown")
                raise InferenceEffectUnknown(
                    "Experiential gateway effect is unresolved"
                ) from None
            except Exception:
                outcome = replace(outcome, kind="effect_unknown")
                raise InferenceEffectUnknown("Experiential gateway forwarding failed") from None
            finally:
                if self._on_outcome is not None:
                    try:
                        self._on_outcome(outcome)
                    except Exception:
                        pass

        try:
            self._core = AttemptInferenceEndpoint(
                core_binding,
                forward=forward_request,
                on_terminal_failure=on_terminal_failure,
                cancel=cancel,
                thread_prefix=thread_prefix,
            )
        except InferenceEndpointContractError as exc:
            raise ExperientialHarnessContractError(str(exc)) from None
        self.binding = binding

    @property
    def base_url(self) -> str:
        try:
            return self._core.base_url
        except InferenceEndpointContractError as exc:
            raise ExperientialHarnessContractError(str(exc)) from None

    @property
    def route(self) -> ExperientialGatewayRoute:
        return self._route

    @property
    def model_id(self) -> str:
        """The model slug the owner selected.  This module never chooses one."""
        return self.binding.model_id

    @property
    def stopped_forwarding(self) -> bool:
        return self._core.stopped_forwarding

    @property
    def failure_notification_failed(self) -> bool:
        return self._core.failure_notification_failed

    def client_options(self) -> dict:
        """Keyword arguments for one OpenAI Python SDK client.

        The returned mapping carries the attempt-private capability and nothing
        else: the local scoped proxy token and any provider key stay inside
        this module.  ``max_retries`` is zero so the SDK never replays a POST.
        """
        return {
            "base_url": self.base_url,
            "api_key": self.binding.client_capability,
            "max_retries": 0,
            "timeout": self._timeout,
        }

    def __enter__(self) -> "ExperientialHarnessEndpoint":
        try:
            self._core.__enter__()
        except InferenceEndpointContractError as exc:
            raise ExperientialHarnessContractError(str(exc)) from None
        return self

    def __exit__(self, *error) -> None:  # noqa: ANN002
        self.close()

    def close(self) -> None:
        self._core.close()
