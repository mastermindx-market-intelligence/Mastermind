#!/usr/bin/env python3
"""experiential_transport.py — the opt-in native gateway inference transport.

Scope of this file (child: experiential53-native-transport, stacked on the
manual-pin scaffolding):

* The ACTUAL executable inference transport for the MANUAL-only
  ``experiential`` pool: one bounded, opt-in, non-streaming OpenAI-compatible
  ``chat/completions`` POST to the existing shared Experiential Labs gateway
  (PR #1849 contract), consumed exactly like the Attempt-owned consumer
  (PR #1920) consumes it.
* It is DISABLED at source until qualification: the immutable module constant
  ``ROUTE_QUALIFIED`` is ``False`` in this generation, so every run refuses
  ``EXPERIENTIAL_GATEWAY_ROUTE_UNQUALIFIED`` before any dial, exactly like the
  pin law refuses ``EXPERIENTIAL_TRANSPORT_NOT_INSTALLED``.  The constant is
  never a function argument — no caller can assert its way past an
  unqualified route.  Flipping it in source is a transport-owner attestation
  that the gateway route is installed on THIS host (the qualified generation
  is a separate, later change).
* No second control plane: no credential store, no key storage, no queue, no
  ledger, no billing, no quota arithmetic, no retry bookkeeping.  Admission
  is the pin law (:func:`experiential_pin.admit_execution`) re-run here in
  full; the gateway keeps owning RPM/backpressure; the upstream ``xpl_``
  provider key stays inside the gateway process and is NEVER seen, accepted,
  transmitted or stored by this module.

Transport laws (each one typed, fail-closed, and mock-tested):

* **Loopback only.**  The route host must be the pinned NUMERIC ``127.0.0.1``;
  a name that resolves anywhere else cannot move a bearer-bearing request off
  loopback (same law as the Attempt-owned consumer).  Scheme is ``http``
  (gateway bind) or ``https`` (owner-qualified encrypted loopback) — nothing
  else.  Base path is exactly ``/v1``; the dialled path is exactly
  ``/v1/chat/completions``.  Dot segments, encoded separators and ambiguous
  prefixes are refused before transport.
* **Proxy-leak proof.**  The opener is built with ``ProxyHandler({})``: no
  ambient ``http_proxy``/``https_proxy``/``all_proxy``/``trust_env`` value is
  consulted, so a poisoned environment cannot route the request anywhere.
* **No redirects.**  Any 3xx is a typed refusal (``GATEWAY_REDIRECT_REFUSED``).
  The redirect handler never follows, so a Location header can never move the
  bearer token or the prompt off the attested route.
* **One POST.**  Exactly one request is issued.  There is no retry, no
  key rotation, no fallback route, no second dial — including on 429 with a
  ``Retry-After`` header (the header is recorded as observed, never obeyed).
* **Bounded.**  Prompt/system text and the encoded request body are bounded
  before dial; the response is read with a hard byte cap; connect and read
  timeouts are bounded.  A truncated or oversized response is a refusal, not
  a partial success.
* **Fail-closed statuses.**  Anything other than HTTP 200 is a typed refusal:
  3xx redirect, 401/403 auth, 413 body, 429 rate limit, 503/504 local queue,
  any other 4xx/5xx, and — deliberately — 204 (the gateway's own
  disconnected-caller response is NOT silently accepted as empty success).
  A 200 with a malformed frame, empty ``choices``, empty content, a
  non-JSON content-type, or a substituted ``model`` field is also refused.
* **Secret-free surface.**  The gateway proxy token (host-managed, org-scoped;
  supplied per-forward by trusted host composition, never read from the
  environment or a file by this module) is carried only inside the route
  binding, excluded from ``repr``, never placed in a refusal detail, a
  result, a summary, or a log.  A provider ``xpl_`` key is refused outright
  (``PROVIDER_KEY_REFUSED``) if it is ever offered in place of the proxy
  token.
* **Retention/exposure acks are per-request.**  The retention acknowledgement,
  the sensitive-data disclosure opt-in and the independent proprietary-code
  opt-in are re-validated by the pin admission on EVERY call — nothing is
  cached, sticky or implied by a previous run.
* **Packet identity is preserved.**  ``run_id`` and ``packet_root`` are
  validated, carried through unchanged, and returned on the outcome;
  ``run_id`` is also the gateway ``Idempotency-Key`` for the one logical
  request (the #1849 worker-client law).
* **Unmerged dependency is named, not bypassed.**  Composition with the
  Attempt-owned consumer seam (``control_plane.experiential_harness_endpoint``,
  PR #1920, unmerged) is available only as an explicit probe:
  :func:`require_attempt_seam` refuses ``EXPERIENTIAL_ATTEMPT_SEAM_UNAVAILABLE``
  while that PR is unmerged rather than silently reimplementing or shimming it.

Mock proof vs live proof: every behaviour above is proven by the hermetic
suite against an in-process mock gateway on an ephemeral loopback port with
zero provider contact (``test_experiential_transport.py`` / CLI ``mockproof``).
That is SOURCE MOCK PROOF.  It is not a live provider call, not an installed
service, and not a worker START: until both source constants below are flipped
by their owners on a qualified host, the shipped transport cannot emit a
single upstream byte.
"""
from __future__ import annotations

import argparse
import http.client
import json
import re
import socket
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from importlib.util import find_spec
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlsplit

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import experiential_pin as pin  # noqa: E402  (same-directory sibling law)

#: Exact pool/slug are THE PIN'S law, re-exported read-only.  The transport
#: never carries a second copy of the slug and never substitutes a model.
POOL = pin.POOL
MODEL = pin.MODEL

#: The pinned gateway route shape (PR #1849 / PR #1920 contract).
GATEWAY_HOST = "127.0.0.1"
GATEWAY_CHAT_PATH = "chat/completions"
GATEWAY_BASE_PATH = "/v1"
ALLOWED_SCHEMES = ("http", "https")

#: Immutable source attestation: NO qualified gateway route is installed on a
#: host in this generation.  Every run refuses before any dial.  Never an
#: argument; flipping it is a transport-owner source change, not a flag.
ROUTE_QUALIFIED = False

#: Attempt-owned consumer seam (PR #1920) — unmerged in this generation.
ATTEMPT_SEAM_MODULE = "control_plane.experiential_harness_endpoint"

#: Bounded transport limits.  The 1 MiB request cap matches the merged
#: attempt boundary's own body cap; the 8 MiB response cap matches the
#: gateway's own body limit.  These are performance bounds, not admission
#: law, so a caller may tighten (never loosen) them via ``TransportLimits``.
MAX_REQUEST_BYTES = 1024 * 1024
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_ERROR_BODY_BYTES = 64 * 1024
MAX_PROMPT_CHARS = 200_000
MAX_SYSTEM_CHARS = 50_000
MAX_CONNECT_TIMEOUT_S = 30.0
MAX_READ_TIMEOUT_S = 900.0

_RUN_ID_RE = pin.RUN_ID_RE
_PACKET_ROOT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./:-]{0,255}$")
_PROXY_TOKEN_RE = re.compile(r"^[\x21-\x7e]{24,256}$")
_ROUTE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
#: Provider key shape (Experiential Labs ``xpl_`` keys).  The gateway owns
#: these; a transport route carries the host-managed proxy token instead.
_PROVIDER_KEY_PREFIX = "xpl_"


class ExperientialTransportRefused(RuntimeError):
    """Typed, fail-closed transport refusal (stable upper-snake ``reason``).

    ``detail`` is metadata-only by construction: status codes, header names,
    limit names.  Prompt, response body and the proxy token can never enter
    it, so a refusal is safe to log.
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason + (f": {detail}" if detail else ""))
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class TransportLimits:
    """Bounded connect/read timeouts.  Tightening is allowed; loosening is not.

    ``connect_timeout_s``/``read_timeout_s`` are validated against the module
    caps so a caller cannot configure an unbounded dial.
    """

    connect_timeout_s: float = 5.0
    read_timeout_s: float = 900.0

    def __post_init__(self) -> None:
        for name, value, cap in (
            ("connect_timeout_s", self.connect_timeout_s, MAX_CONNECT_TIMEOUT_S),
            ("read_timeout_s", self.read_timeout_s, MAX_READ_TIMEOUT_S),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ExperientialTransportRefused("TRANSPORT_LIMITS_INVALID", name)
            if not 0 < float(value) <= cap:
                raise ExperientialTransportRefused(
                    "TRANSPORT_LIMITS_INVALID", f"{name} out of (0, {cap}]")

    @property
    def socket_timeout(self) -> float:
        return float(min(self.connect_timeout_s, self.read_timeout_s))


DEFAULT_LIMITS = TransportLimits()


@dataclass(frozen=True)
class GatewayRoute:
    """One attested loopback gateway route (PR #1849 contract shape).

    ``proxy_token`` is the host-managed, org-scoped gateway token supplied by
    trusted host composition for the lifetime of one forward.  It is
    deliberately excluded from ``repr`` and from every result surface.  It is
    NOT a provider key and must never be one.
    """

    host: str
    port: int
    proxy_token: str = field(repr=False)
    route_id: str
    route_generation: str
    scheme: str = "http"
    base_path: str = GATEWAY_BASE_PATH


@dataclass(frozen=True)
class InferenceOutcome:
    """Secret-free terminal outcome of the ONE admitted inference request.

    Carries the packet identity verbatim and the completion text.  No token,
    no route credentials, no request bodies beyond the returned content.
    """

    run_id: str
    packet_root: str
    pool: str
    model: str
    task_class: str
    route_id: str
    route_generation: str
    request_url_host: str
    request_url_port: int
    idempotency_key: str
    http_status: int
    bytes_received: int
    content: str
    model_echo: Optional[str]
    source: str = "gateway"

    def summary(self) -> Dict[str, Any]:
        """Metadata-only view (no completion text, no credentials)."""
        return {
            "source": self.source,
            "run_id": self.run_id,
            "packet_root": self.packet_root,
            "pool": self.pool,
            "model": self.model,
            "task_class": self.task_class,
            "route_id": self.route_id,
            "route_generation": self.route_generation,
            "host": self.request_url_host,
            "port": self.request_url_port,
            "idempotency_key": self.idempotency_key,
            "http_status": self.http_status,
            "bytes_received": self.bytes_received,
            "content_chars": len(self.content),
            "model_echo": self.model_echo,
        }


def _validate_route(route: Any) -> GatewayRoute:
    """Structural route law.  Ordered: host, scheme, port, path, identity, token."""
    if not isinstance(route, GatewayRoute):
        raise ExperientialTransportRefused("GATEWAY_ROUTE_INVALID", "not a GatewayRoute")
    if route.host != GATEWAY_HOST:  # exact numeric loopback; no name resolution
        raise ExperientialTransportRefused(
            "GATEWAY_ROUTE_NOT_LOOPBACK",
            f"pinned host is {GATEWAY_HOST}, got {route.host!r}")
    if route.scheme not in ALLOWED_SCHEMES:
        raise ExperientialTransportRefused(
            "GATEWAY_ROUTE_SCHEME_REFUSED",
            f"allowed schemes: {', '.join(ALLOWED_SCHEMES)}")
    if isinstance(route.port, bool) or not isinstance(route.port, int) \
            or not 1 <= route.port <= 65535:
        raise ExperientialTransportRefused("GATEWAY_ROUTE_PORT_INVALID")
    if route.base_path != GATEWAY_BASE_PATH:
        raise ExperientialTransportRefused(
            "GATEWAY_ROUTE_BASE_PATH_REFUSED",
            f"pinned base path is {GATEWAY_BASE_PATH!r}, got {route.base_path!r}")
    if not isinstance(route.route_id, str) or _ROUTE_ID_RE.fullmatch(route.route_id) is None:
        raise ExperientialTransportRefused("GATEWAY_ROUTE_ID_INVALID")
    if not isinstance(route.route_generation, str) \
            or _DIGEST_RE.fullmatch(route.route_generation) is None:
        raise ExperientialTransportRefused(
            "GATEWAY_ROUTE_GENERATION_INVALID", "must be a lowercase SHA-256")
    _validate_proxy_token(route.proxy_token)
    # The dialled URL is rebuilt from validated parts; the caller-supplied
    # fields can never smuggle an ambiguous path (no dot segment, no encoded
    # separator can pass the exact-path equality above).
    split = urlsplit(_gateway_url(route))
    if split.hostname != GATEWAY_HOST or split.path != f"{GATEWAY_BASE_PATH}/{GATEWAY_CHAT_PATH}":
        raise ExperientialTransportRefused("GATEWAY_ROUTE_URL_MISMATCH")
    return route


def _validate_proxy_token(token: Any) -> str:
    """Host-managed proxy token law; a provider key is refused outright."""
    if not isinstance(token, str):
        raise ExperientialTransportRefused("GATEWAY_TOKEN_REQUIRED")
    if token.startswith(_PROVIDER_KEY_PREFIX):
        raise ExperientialTransportRefused(
            "PROVIDER_KEY_REFUSED",
            "an upstream provider key never rides this transport; the "
            "gateway holds provider keys, not the worker")
    if _PROXY_TOKEN_RE.fullmatch(token) is None:
        raise ExperientialTransportRefused(
            "GATEWAY_TOKEN_INVALID",
            "expected the 24-256 printable-ASCII host-managed proxy token")
    return token


def _gateway_url(route: GatewayRoute) -> str:
    return (f"{route.scheme}://{route.host}:{route.port}"
            f"{route.base_path}/{GATEWAY_CHAT_PATH}")


class _RedirectRefused(urllib.request.HTTPRedirectHandler):
    """Any 3xx is a typed refusal.  Never followed, never re-issued."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        try:
            fp.close()  # do not leak the 3xx body stream
        except Exception:
            pass
        raise ExperientialTransportRefused(
            "GATEWAY_REDIRECT_REFUSED",
            f"status {code}: redirects are never followed from the attested route")


def _build_opener() -> urllib.request.OpenerDirector:
    # ProxyHandler({}) = no proxies at all: no ambient trust_env leak.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _RedirectRefused())


def _validate_packet_identity(run_id: Any, packet_root: Any) -> Tuple[str, str]:
    rid = str(run_id or "").strip()
    if _RUN_ID_RE.fullmatch(rid) is None:
        raise ExperientialTransportRefused("RUN_ID_INVALID")
    root = packet_root
    if not isinstance(root, str) or _PACKET_ROOT_RE.fullmatch(root) is None:
        raise ExperientialTransportRefused("PACKET_ROOT_INVALID")
    return rid, root


def _validate_prompt(prompt: Any, system: Any, limits: TransportLimits) -> str:
    if not isinstance(prompt, str) or not prompt.strip():
        raise ExperientialTransportRefused("PROMPT_REQUIRED")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise ExperientialTransportRefused(
            "PROMPT_TOO_LARGE", f"max {MAX_PROMPT_CHARS} chars")
    if system is None:
        return prompt
    if not isinstance(system, str):
        raise ExperientialTransportRefused("SYSTEM_PROMPT_INVALID")
    if len(system) > MAX_SYSTEM_CHARS:
        raise ExperientialTransportRefused(
            "SYSTEM_PROMPT_TOO_LARGE", f"max {MAX_SYSTEM_CHARS} chars")
    return prompt


def _build_request_frame(prompt: str, system: Any) -> bytes:
    """The exact admitted request frame.  The model is the pin's law; the
    frame is non-streaming by law; no caller-supplied field can enter it."""
    messages: list = []
    if isinstance(system, str) and system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    frame = {"model": MODEL, "messages": messages, "stream": False}
    body = json.dumps(frame, ensure_ascii=False).encode("utf-8")
    if len(body) > MAX_REQUEST_BYTES:
        raise ExperientialTransportRefused(
            "REQUEST_BODY_TOO_LARGE",
            f"encoded frame {len(body)} bytes > {MAX_REQUEST_BYTES}")
    return body


def _classify_http_error(status: int, content_type: str) -> ExperientialTransportRefused:
    """One typed refusal per status class.  No status is silently accepted."""
    if 300 <= status < 400:
        return ExperientialTransportRefused(
            "GATEWAY_REDIRECT_REFUSED", f"status {status}")
    if status in (401, 403):
        return ExperientialTransportRefused(
            "GATEWAY_AUTH_REFUSED", f"status {status}")
    if status == 413:
        return ExperientialTransportRefused("GATEWAY_REQUEST_TOO_LARGE", "status 413")
    if status == 429:
        return ExperientialTransportRefused(
            "GATEWAY_RATE_LIMITED", "status 429; Retry-After is never obeyed (one POST)")
    if 400 <= status < 500:
        return ExperientialTransportRefused("GATEWAY_REQUEST_REFUSED", f"status {status}")
    if status == 503:
        return ExperientialTransportRefused(
            "GATEWAY_LOCAL_QUEUE_FULL", "status 503")
    if status == 504:
        return ExperientialTransportRefused(
            "GATEWAY_QUEUE_WAIT_EXPIRED", "status 504")
    if status >= 500:
        return ExperientialTransportRefused("GATEWAY_UPSTREAM_ERROR", f"status {status}")
    if status != 200:
        # e.g. the gateway's 204 disconnected-caller response: not a success,
        # and never silently accepted as an empty completion.
        return ExperientialTransportRefused("GATEWAY_STATUS_REFUSED", f"status {status}")
    return ExperientialTransportRefused(
        "GATEWAY_RESPONSE_MALFORMED", f"content-type {content_type!r}")


def _parse_completion(raw: bytes, content_type: str) -> Tuple[str, Optional[str]]:
    """The exact JSON response law: 200 + JSON + non-empty choices + content."""
    if not content_type.lower().startswith("application/json"):
        raise ExperientialTransportRefused(
            "GATEWAY_RESPONSE_MALFORMED", f"content-type {content_type!r}")
    try:
        frame = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ExperientialTransportRefused(
            "GATEWAY_RESPONSE_MALFORMED", "body is not UTF-8 JSON")
    if not isinstance(frame, dict):
        raise ExperientialTransportRefused("GATEWAY_RESPONSE_MALFORMED", "frame is not an object")
    model_echo = frame.get("model")
    if model_echo is not None:
        if not isinstance(model_echo, str) or model_echo.casefold() != MODEL:
            raise ExperientialTransportRefused(
                "GATEWAY_RESPONSE_MODEL_MISMATCH",
                f"expected {MODEL!r}, gateway returned {model_echo!r}")
    choices = frame.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ExperientialTransportRefused("GATEWAY_RESPONSE_MALFORMED", "no choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise ExperientialTransportRefused("GATEWAY_RESPONSE_MALFORMED", "choice is not an object")
    message = first.get("message")
    if not isinstance(message, dict):
        raise ExperientialTransportRefused("GATEWAY_RESPONSE_MALFORMED", "no message object")
    content = message.get("content")
    if not isinstance(content, str):
        raise ExperientialTransportRefused("GATEWAY_RESPONSE_MALFORMED", "content is not a string")
    if not content.strip():
        raise ExperientialTransportRefused(
            "GATEWAY_RESPONSE_EMPTY", "completion content is empty")
    return content, model_echo if isinstance(model_echo, str) else None


def require_route_qualified() -> None:
    """The transport-owned attestation gate.  Reads the module constant."""
    if ROUTE_QUALIFIED is not True:
        raise ExperientialTransportRefused(
            "EXPERIENTIAL_GATEWAY_ROUTE_UNQUALIFIED",
            "no attested loopback Experiential gateway route is installed on "
            "this host in this generation; flipping ROUTE_QUALIFIED is a "
            "transport-owner source attestation, never a runtime flag")


def attempt_seam_available() -> bool:
    """Read-only probe for the Attempt-owned consumer seam (PR #1920)."""
    try:
        return find_spec(ATTEMPT_SEAM_MODULE) is not None
    except (ImportError, ValueError):
        return False


def require_attempt_seam() -> None:
    """Explicit dependency law: name the unmerged seam, never shim it."""
    if not attempt_seam_available():
        raise ExperientialTransportRefused(
            "EXPERIENTIAL_ATTEMPT_SEAM_UNAVAILABLE",
            f"{ATTEMPT_SEAM_MODULE} (PR #1920) is not importable in this "
            "generation; composition is the wiring owner's route and is "
            "never shimmed here")


def run_opt_in_inference(
    *,
    run_id: Any,
    packet_root: str,
    task_class: str,
    pool: Any,
    model: Any,
    registry_entry: Optional[Dict[str, Any]],
    entitlement: Optional[Dict[str, Any]],
    retention_acknowledged: bool,
    sensitive_data_opt_in: bool,
    proprietary_code: bool,
    code_exposure_opt_in: bool,
    account: Any,
    quota_readback: Any,
    route: GatewayRoute,
    prompt: str,
    system: str = "",
    limits: Optional[TransportLimits] = None,
) -> InferenceOutcome:
    """The ONE admitted, opt-in inference request through the local gateway.

    Contract order (deterministic, each step typed):

    1. packet identity validation (run_id / packet_root),
    2. strict manual preview -> recheck of the exact pin,
    3. full pin admission law — provider enabled, entitlement, retention
       acknowledgement, sensitive-data opt-in, proprietary-code opt-in,
       account law (A held, B capped with authenticated readback), transport
       (``pin.TRANSPORT_INSTALLED``),
    4. transport-owned route attestation (``ROUTE_QUALIFIED``) and structural
       route validation,
    5. bounded request framing,
    6. exactly one fail-closed POST,
    7. exact JSON response law -> secret-free outcome.

    No step is optional and no step is cached: the acks, the account law and
    the readback are re-evaluated per request.
    """
    bounded = limits if limits is not None else DEFAULT_LIMITS
    if not isinstance(bounded, TransportLimits):
        raise ExperientialTransportRefused("TRANSPORT_LIMITS_INVALID")
    rid, root = _validate_packet_identity(run_id, packet_root)

    # Strict manual preview -> recheck (the incumbent selection law).
    selected = pin.preview(rid, task_class, pool=pool, model=model)
    rechecked = pin.preview(rid, selected["task_class"],
                            pool=selected["pool"], model=selected["model"])
    if (selected["pool"], selected["model"], selected["task_class"]) != \
            (rechecked["pool"], rechecked["model"], rechecked["task_class"]):
        raise ExperientialTransportRefused("SELECTION_RECHECK_MISMATCH")

    # Full admission law, unchanged, at its canonical contract order.
    admitted = pin.admit_execution(
        pool=pool, model=model, task_class=task_class,
        registry_entry=registry_entry, entitlement=entitlement,
        retention_acknowledged=retention_acknowledged,
        sensitive_data_opt_in=sensitive_data_opt_in,
        proprietary_code=proprietary_code,
        code_exposure_opt_in=code_exposure_opt_in,
        account=account, quota_readback=quota_readback)

    # Transport-owned attestation + structure, after the admission law.
    require_route_qualified()
    _validate_route(route)
    _validate_prompt(prompt, system, bounded)
    body = _build_request_frame(prompt, system)

    headers = {
        "Authorization": f"Bearer {route.proxy_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        # One logical request; the gateway's idempotency law (#1849).
        "Idempotency-Key": rid,
        # Content-Length is deliberately NOT set here: urllib computes it, and
        # a duplicate Content-Length is refused by the attempt boundary law.
    }
    request = urllib.request.Request(_gateway_url(route), data=body,
                                     headers=headers, method="POST")
    opener = _build_opener()
    try:
        response = opener.open(request, timeout=bounded.socket_timeout)
    except ExperientialTransportRefused:
        raise
    except urllib.error.HTTPError as exc:
        content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
        try:
            exc.read(MAX_ERROR_BODY_BYTES)  # drained, never surfaced or logged
        except Exception:
            pass
        finally:
            exc.close()
        raise _classify_http_error(exc.code, content_type)
    except (socket.timeout, TimeoutError, http.client.HTTPException) as exc:
        raise ExperientialTransportRefused(
            "GATEWAY_TIMEOUT", type(exc).__name__)
    except (urllib.error.URLError, OSError) as exc:
        raise ExperientialTransportRefused(
            "GATEWAY_UNREACHABLE", type(exc).__name__)

    # Any non-200 that urllib surfaces as a normal response (no HTTPError for
    # these) is still refused, not silently accepted.
    status = getattr(response, "status", None) or response.getcode()
    content_type = response.headers.get("Content-Type", "")
    if status != 200:
        try:
            response.read(MAX_ERROR_BODY_BYTES)
        except Exception:
            pass
        finally:
            response.close()
        raise _classify_http_error(status, content_type)
    try:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    except (socket.timeout, TimeoutError, http.client.HTTPException) as exc:
        raise ExperientialTransportRefused("GATEWAY_TIMEOUT", type(exc).__name__)
    finally:
        response.close()
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ExperientialTransportRefused(
            "GATEWAY_RESPONSE_TOO_LARGE",
            f"exceeds {MAX_RESPONSE_BYTES} bytes")
    content, model_echo = _parse_completion(raw, content_type)
    return InferenceOutcome(
        run_id=rid,
        packet_root=root,
        pool=admitted["pool"],
        model=admitted["model"],
        task_class=admitted["task_class"],
        route_id=route.route_id,
        route_generation=route.route_generation,
        request_url_host=route.host,
        request_url_port=route.port,
        idempotency_key=rid,
        http_status=200,
        bytes_received=len(raw),
        content=content,
        model_echo=model_echo,
    )


def _route_from_env_stub() -> GatewayRoute:
    """Refuse before building anything: no ambient credential source exists.

    The route (including the proxy token) is supplied by trusted host
    composition only.  This stub exists so the CLI has no environment or file
    credential path to accidentally rely on.
    """
    raise ExperientialTransportRefused(
        "GATEWAY_ROUTE_SUPPLIED_BY_COMPOSITION_ONLY",
        "no env/file credential path exists in this module")


def _cli_status(_args: argparse.Namespace) -> int:
    """Zero-network gate report.  Proves the fail-closed shipped posture."""
    print(f"POOL={POOL}")
    print(f"MODEL={MODEL}")
    print(f"ROUTE_QUALIFIED={ROUTE_QUALIFIED}")
    print(f"PIN_TRANSPORT_INSTALLED={pin.TRANSPORT_INSTALLED}")
    print(f"ATTEMPT_SEAM_AVAILABLE={str(attempt_seam_available()).lower()}")
    print(f"GATEWAY_HOST={GATEWAY_HOST}")
    print(f"GATEWAY_BASE_PATH={GATEWAY_BASE_PATH}")
    print("STATE=FAIL_CLOSED_SHIPPED generation routes every run to a typed refusal")
    return 78


def _cli_route(_args: argparse.Namespace) -> int:
    try:
        require_route_qualified()
        require_attempt_seam()
        _route_from_env_stub()
    except ExperientialTransportRefused as exc:
        print(f"NONE reason={exc.reason}", file=sys.stderr)
        return 78
    return 0  # unreachable in this generation


def _cli_mockproof(_args: argparse.Namespace) -> int:
    """Hermetic end-to-end proof on an ephemeral loopback mock gateway.

    MOCK PROOF ONLY: in-process mock, loopback-ephemeral, zero provider
    contact, zero host mutation outside one temp directory.  Proves the
    transport is executable and enforces its laws; it is NOT a live provider
    call, NOT an installed service and NOT a worker START.
    """
    try:
        from test_experiential_transport import run_mockproof
    except ImportError:
        try:
            from ops.native_fabric.experiential53.test_experiential_transport import run_mockproof
        except ImportError:
            print("NONE reason=MOCKPROOF_SUITE_UNAVAILABLE", file=sys.stderr)
            return 78
    passed = run_mockproof()
    print(f"MOCKPROOF passed={passed} (source mock proof only; no provider contact)")
    return 0 if passed else 78


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="experiential_transport.py",
        description="Opt-in native gateway inference transport for the "
                    "MANUAL-only Experiential pool. Fail-closed until owner "
                    "qualification; no env/file credential path.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_status = sub.add_parser(
        "status", help="zero-network gate report (exit 78 while fail-closed)")
    p_status.set_defaults(func=_cli_status)
    p_route = sub.add_parser(
        "route", help="prove the route/dependency refusal ladder without dialing")
    p_route.set_defaults(func=_cli_route)
    p_mock = sub.add_parser(
        "mockproof", help="hermetic loopback mock proof (no provider contact)")
    p_mock.set_defaults(func=_cli_mockproof)
    return parser


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
