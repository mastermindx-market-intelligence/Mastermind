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
* A provider error frame latches the stream as an unresolved effect.  A later
  terminal marker never revives it, so an error that arrives before the
  completion frame is never reported as a completion, and the attempt fails
  stop instead of allowing a second upstream POST.
* The gateway socket is dialled at a pinned numeric loopback address.  The
  name is resolved once and the numeric answer is used for the send, so a
  rebinding resolver cannot move a bearer-bearing request off loopback.
* The gateway base path is the pinned allowlisted path.  An ambiguous prefix,
  a dot segment or an encoded separator is refused before transport.
* An ambiguous effect keeps the status and the byte count it observed, and an
  outcome the owner could not record fails closed rather than continuing.

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

from control_plane.experiential_plan_policy import plan_policy_digest, route_policy_generation

MAX_STREAM_BYTES = 64 * 1024 * 1024
MAX_ERROR_BYTES = 256 * 1024
MAX_EVENT_BYTES = 1024 * 1024
MAX_IDEMPOTENCY_KEY = 128
MAX_TOKEN_LENGTH = 256

GATEWAY_CHAT_PATH = "chat/completions"
GATEWAY_RESPONSES_PATH = "responses"
#: Protocol -> concrete gateway route.  The gateway admits exactly these two
#: streaming routes; the attempt endpoint's protocol names are reused verbatim
#: so one binding drives both ends.
GATEWAY_PATHS = {
    "openai-chat": GATEWAY_CHAT_PATH,
    "responses": GATEWAY_RESPONSES_PATH,
}
#: The one gateway base path this consumer admits.  The dialled path is this
#: base path plus the route path, so a base path outside the list is refused
#: before transport: an ambiguous prefix would let a normalising proxy move
#: the request somewhere the owner never attested.
GATEWAY_BASE_PATHS = ("/v1",)

_LOOPBACK_NAMES = frozenset({"localhost"})
#: A valid HTTP status is 1xx-5xx.  The hundreds digit bounds it without
#: naming a status literal in this source.
_VALID_STATUS_HUNDREDS = (1, 2, 3, 4, 5)
#: Provider frame types that carry a refusal rather than a completion.
_PROVIDER_ERROR_TYPES = frozenset({
    "error",
    "response.failed",
    "response.incomplete",
    "response.cancelled",
})


class ExperientialHarnessContractError(RuntimeError):
    """The local consumer/gateway composition contract is invalid or not admitted."""


class ExperientialHarnessUnavailable(RuntimeError):
    """The gateway could not be reached; nothing was sent and nothing took effect."""


class ExperientialHarnessEffectUnknown(RuntimeError):
    """The gateway may have taken effect; an automatic replay is not safe.

    ``http_status`` and ``bytes_forwarded`` carry what the forward already
    observed.  Both are secret free, and they let the owner record the truth
    about an ambiguous forward instead of a placeholder.
    """

    def __init__(
        self,
        message: str,
        *,
        http_status: Optional[int] = None,
        bytes_forwarded: int = 0,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.bytes_forwarded = bytes_forwarded


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
    plan_policy: str = "legacy"

    def __post_init__(self) -> None:
        if not isinstance(self.route_id, str) or not self.route_id.strip():
            raise ExperientialHarnessContractError("gateway route identity is required")
        if self.path not in set(GATEWAY_PATHS.values()):
            raise ExperientialHarnessContractError("unsupported gateway route path")
        _normalize_base_url(self.base_url)
        if gateway_route_generation(self.base_url, self.path, self.plan_policy) != self.route_generation:
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


def gateway_route_generation(base_url: str, path: str, plan_policy: str = "legacy") -> str:
    """The attested identity of one pinned gateway target.

    The owner computes this once for the approved loopback gateway and injects
    it with the route.  The forwarder recomputes it from the target it is about
    to dial, so a route that drifted after attestation is refused instead of
    being forwarded under the approved identity.
    """
    try:
        return route_policy_generation(base_url, path, plan_policy)
    except ValueError as exc:
        raise ExperientialHarnessContractError("invalid gateway plan policy") from exc


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
    _require_pinned_base_path(parts.path)
    if not _is_loopback_host(parts.hostname or ""):
        raise ExperientialHarnessContractError("gateway base URL must be a loopback address")
    return base_url.rstrip("/")


def _require_pinned_base_path(path: str) -> None:
    """Refuse an ambiguous gateway base path before anything is dialled.

    The dialled path is the pinned base path plus the route path, so a base
    path that a normalising proxy could rewrite is refused rather than
    dialled: a dot segment, a repeated separator, an encoded separator or an
    encoded dot, and any prefix outside the allowlist.
    """
    normalized = path.rstrip("/")
    if normalized not in GATEWAY_BASE_PATHS:
        raise ExperientialHarnessContractError(
            "gateway base path is not the pinned allowlisted path"
        )
    segments = normalized.split("/")
    if segments and segments[0] == "":
        # The leading empty segment is the path root, not an empty segment.
        segments = segments[1:]
    for segment in segments:
        if segment in ("", ".", ".."):
            raise ExperientialHarnessContractError("gateway base path is ambiguous")
        if "%" in segment or "\\" in segment:
            raise ExperientialHarnessContractError("gateway base path is ambiguous")


def _observed_status(value) -> Optional[int]:  # noqa: ANN001
    """Keep an observed status only when it is a real status integer."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _observed_bytes(value) -> int:  # noqa: ANN001
    """Keep an observed byte count only when it is a real count."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


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


@dataclass(frozen=True)
class _PinnedEndpoint:
    """One numeric loopback address the gateway socket is allowed to use."""

    family: int
    address: str
    port: int


def _pin_loopback_endpoints(host: str, port: int) -> tuple[_PinnedEndpoint, ...]:
    """Resolve the gateway host exactly once into numeric loopback endpoints.

    A numeric loopback literal is pinned without any name resolution at all.
    A name is resolved once, here, and every answer must be a loopback
    address; the pinned numbers are then dialled directly.  The name is never
    resolved again, so a rebinding resolver cannot move a bearer-bearing
    request off loopback between the check and the send.
    """
    candidate = host.strip("[]").lower()
    try:
        literal = ipaddress.ip_address(candidate)
    except ValueError:
        literal = None
    if literal is not None:
        if not literal.is_loopback:
            raise ExperientialHarnessContractError(
                "gateway address is not a loopback address"
            )
        family = socket.AF_INET6 if literal.version == 6 else socket.AF_INET
        return (_PinnedEndpoint(family, str(literal), port),)
    try:
        infos = socket.getaddrinfo(candidate, port, type=socket.SOCK_STREAM)
    except OSError:
        raise ExperientialHarnessUnavailable("gateway address could not be resolved") from None
    pinned: list[_PinnedEndpoint] = []
    for family, _socktype, _proto, _canonname, sockaddr in infos:
        try:
            resolved = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            raise ExperientialHarnessContractError(
                "gateway resolution did not yield a numeric address"
            ) from None
        if not resolved.is_loopback:
            # The name resolved off loopback.  Refuse before any byte carries
            # the local scoped proxy token.
            raise ExperientialHarnessContractError(
                "gateway resolution drifted off loopback"
            )
        pinned.append(_PinnedEndpoint(family, sockaddr[0], int(sockaddr[1])))
    if not pinned:
        raise ExperientialHarnessUnavailable("gateway address could not be resolved")
    return tuple(pinned)


def _dial_pinned(endpoints, timeout, source_address):  # noqa: ANN001
    """Open one socket to a pinned numeric loopback endpoint.

    No name is resolved here: the socket is handed the numeric address that
    was pinned and verified, so the dialled peer cannot differ from the
    checked one.
    """
    if source_address is not None:
        # A source address is never used here and could reintroduce a name
        # resolution; refuse rather than resolve one.
        raise OSError("a pinned gateway dial does not accept a source address")
    last_error = None
    for endpoint in endpoints:
        sock = socket.socket(endpoint.family, socket.SOCK_STREAM)
        try:
            if timeout is not None and timeout is not getattr(
                socket, "_GLOBAL_DEFAULT_TIMEOUT", None
            ):
                sock.settimeout(timeout)
            sock.connect((endpoint.address, endpoint.port))
            return sock
        except OSError as exc:
            last_error = exc
            try:
                sock.close()
            except OSError:
                pass
    if last_error is None:
        raise OSError("the pinned gateway address could not be dialled")
    raise last_error


def _install_pinned_dial(connection, endpoints) -> None:  # noqa: ANN001
    """Bind the connection to the pinned numeric endpoints."""

    def dial(address, timeout=None, source_address=None):  # noqa: ANN001, ARG001
        return _dial_pinned(endpoints, timeout, source_address)

    connection._create_connection = dial


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


def _is_provider_error_payload(payload: dict) -> bool:
    """True when one provider frame reports a refusal rather than progress.

    A provider error may arrive as a JSON error object, as an error object
    type, or as an error stream object.  Each of them is the provider saying
    the request did not complete normally.
    """
    if payload.get("error") is not None:
        return True
    if payload.get("type") in _PROVIDER_ERROR_TYPES:
        return True
    if payload.get("object") == "error":
        return True
    return False


class _StreamTerminal:
    """Bounded SSE framing observer.  It never rewrites or drops provider frames.

    Frames are observed only to learn when the provider stream reached its
    terminal event, or that it reported an error.  The bytes handed to the
    child are the provider's bytes.

    A provider error frame latches :attr:`failed` for good.  A later
    ``[DONE]`` never revives a latched stream, so an error that arrives
    before the terminal marker cannot be reported as a completion.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self.buffer = bytearray()
        self.data: list[bytes] = []
        self.event = b""
        self.event_bytes = 0
        self.terminal = False
        self.failed = False
        self.failure_reason = ""

    def _latch_failure(self, reason: str) -> None:
        if self.failed:
            return
        self.failed = True
        self.failure_reason = reason
        self.terminal = False

    def _dispatch(self) -> None:
        if not self.data:
            # A bare SSE error event still reports a failed provider request.
            # Discarding it would let a later [DONE] falsely complete the stream.
            if self.event == b"error":
                self._latch_failure("provider error event")
            self.event, self.event_bytes = b"", 0
            return
        data = b"\n".join(self.data)
        self.data = []
        event, self.event = self.event, b""
        self.event_bytes = 0
        if self.terminal or self.failed:
            # A settled outcome is final: a later frame never revives it.
            return
        if event == b"error":
            self._latch_failure("provider error event")
            return
        if self.path == GATEWAY_CHAT_PATH and data.strip() == b"[DONE]":
            self.terminal = True
            return
        try:
            payload = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return
        if not isinstance(payload, dict):
            return
        if _is_provider_error_payload(payload):
            self._latch_failure("provider error frame")
            return
        if (
            self.path == GATEWAY_RESPONSES_PATH
            and payload.get("type") == "response.completed"
        ):
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


def _effective_port(parts) -> int:  # noqa: ANN001
    """The port this scheme dials, taken from the transport's own default."""
    if parts.port is not None:
        return parts.port
    if parts.scheme == "https":
        return http.client.HTTPSConnection.default_port
    return http.client.HTTPConnection.default_port


def _open_connection(parts, timeout: float, port: int):  # noqa: ANN001
    """Open the gateway connection against pinned numeric loopback endpoints."""
    # A missing port keeps the scheme's own default rather than a literal here.
    endpoints = _pin_loopback_endpoints(parts.hostname or "", port)
    if parts.scheme == "https":
        connection = http.client.HTTPSConnection(parts.hostname, parts.port, timeout=timeout)
    else:
        connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=timeout)
    _install_pinned_dial(connection, endpoints)
    return connection


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
    if gateway_route_generation(route.base_url, route.path, route.plan_policy) != route.route_generation:
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
    observed_status: Optional[int] = None

    def refresh_timeout() -> None:
        if cancel is not None and cancel.is_set():
            raise ExperientialHarnessEffectUnknown(
                "attempt cancelled after submission",
                http_status=observed_status,
                bytes_forwarded=forwarded,
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ExperientialHarnessEffectUnknown(
                "gateway request exceeded its deadline",
                http_status=observed_status,
                bytes_forwarded=forwarded,
            )
        window = max(0.001, min(idle, remaining))
        connection.timeout = window
        sock = getattr(connection, "sock", None)
        if sock is not None:
            sock.settimeout(window)

    try:
        connection = _open_connection(parts, min(idle, total), _effective_port(parts))
        headers = {
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        if route.plan_policy != "legacy":
            headers["X-Fabric-Plan-Policy"] = plan_policy_digest(route.plan_policy)
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
            raise ExperientialHarnessEffectUnknown(
                "gateway request write failed",
                http_status=observed_status,
                bytes_forwarded=forwarded,
            ) from None
        refresh_timeout()
        response = connection.getresponse()
        status = response.status
        if (
            isinstance(status, bool)
            or not isinstance(status, int)
            or status // 100 not in _VALID_STATUS_HUNDREDS
        ):
            raise ExperientialHarnessEffectUnknown("gateway returned an invalid status")
        observed_status = status
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
            raise ExperientialHarnessEffectUnknown(
                "gateway did not return an event stream",
                http_status=observed_status,
                bytes_forwarded=forwarded,
            )
        observer = _StreamTerminal(route.path)
        while True:
            refresh_timeout()
            chunk = response.read1(16384)
            if not isinstance(chunk, bytes):
                raise ExperientialHarnessEffectUnknown(
                    "gateway returned invalid stream bytes",
                    http_status=observed_status,
                    bytes_forwarded=forwarded,
                )
            if not chunk:
                observer.finish()
                if observer.failed:
                    raise ExperientialHarnessEffectUnknown(
                        "gateway reported a provider error",
                        http_status=observed_status,
                        bytes_forwarded=forwarded,
                    )
                if not observer.terminal:
                    raise ExperientialHarnessEffectUnknown(
                        "gateway stream ended before its terminal frame",
                        http_status=observed_status,
                        bytes_forwarded=forwarded,
                    )
                break
            forwarded += len(chunk)
            if forwarded > MAX_STREAM_BYTES:
                raise ExperientialHarnessEffectUnknown(
                    "gateway stream exceeded its size bound",
                    http_status=observed_status,
                    bytes_forwarded=forwarded,
                )
            observer.feed(chunk)
            on_chunk(chunk)
            if observer.failed:
                # The provider reported an error.  This is never a completion,
                # and the endpoint fails stop so no second POST can follow.
                raise ExperientialHarnessEffectUnknown(
                    "gateway reported a provider error",
                    http_status=observed_status,
                    bytes_forwarded=forwarded,
                )
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
            raise ExperientialHarnessEffectUnknown(
                "gateway forwarding failed",
                http_status=observed_status,
                bytes_forwarded=forwarded,
            ) from None
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
            failure = None
            receipt = None
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
                receipt = InferenceForwardReceipt(
                    route_id=result.route_id,
                    route_generation=result.route_generation,
                    http_status=result.http_status,
                    bytes_forwarded=result.bytes_forwarded,
                    terminal_observed=result.terminal_observed,
                )
            except ExperientialHarnessContractError:
                outcome = replace(outcome, kind="refused")
                failure = InferenceForwardRefused(
                    "Experiential consumer contract refused the request"
                )
            except ExperientialHarnessUnavailable:
                outcome = replace(outcome, kind="unavailable")
                failure = InferenceForwardRefused("Experiential gateway is unavailable")
            except ExperientialHarnessEffectUnknown as exc:
                # Keep what the forward actually observed: an ambiguous effect
                # with a known status and a known byte count is still a fact.
                outcome = replace(
                    outcome,
                    kind="effect_unknown",
                    http_status=_observed_status(exc.http_status),
                    bytes_forwarded=_observed_bytes(exc.bytes_forwarded),
                )
                failure = InferenceEffectUnknown(
                    "Experiential gateway effect is unresolved"
                )
            except Exception:
                outcome = replace(outcome, kind="effect_unknown")
                failure = InferenceEffectUnknown("Experiential gateway forwarding failed")
            # The owner attestation callback is part of the terminal contract.
            # A callback that fails means the outcome was never attested, so
            # the attempt fails closed here instead of continuing as if the
            # forward had been recorded.
            if self._on_outcome is not None:
                try:
                    self._on_outcome(outcome)
                except Exception:
                    if failure is None:
                        failure = InferenceEffectUnknown(
                            "Experiential gateway outcome attestation failed"
                        )
            if failure is not None:
                raise failure from None
            return receipt

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
