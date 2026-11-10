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
* **Worst-case output is bounded.**  Every admitted frame carries a fixed
  conservative ``max_tokens`` (module constant ``MAX_OUTPUT_TOKENS``).  A
  caller may TIGHTEN it per request; nothing can loosen it — the constant is
  the ceiling, never a runtime flag and never a route field.  This also caps
  the billed exposure of a request that fails mid-generation (vendor law: a
  failed or disconnected request may still incur charge).
* **Provider reconciliation handle.**  The provider/gateway ``X-Request-Id``
  RESPONSE header is captured, strictly shape-validated and surfaced on the
  outcome as an opaque, bounded, non-secret reconciliation handle that is
  distinct from the locally sent ``Idempotency-Key``.  A missing or malformed
  handle is typed, never synthesized and never logged raw.  It is the key
  the EXISTING billing owner uses against the settled Cost API
  (``GET /api/v1/generation?id=<x-request-id>``) / usage export — this
  module never dials it.
* **Cost is never invented.**  Per the Experiential Cost API law, a request
  carrying an ``Idempotency-Key`` is NOT annotated with ``usage.cost``, so
  the per-request cost is UNKNOWN at transport time.  A response without a
  usable inline ``usage.cost`` observation is therefore explicitly
  ``COST_RECONCILIATION_PENDING`` — never zero USD, never a fabricated
  figure, never a provider query, never a ledger write.  A type-safe inline
  observation is surfaced as ``COST_RECONCILIATION_OBSERVED_INLINE`` and is
  explicitly NOT settled billing.  ``usage.is_byok`` true fails the request
  closed for this platform-funded-only pool (``COST_BYOK_REFUSED``): the
  completion is discarded, no retry, no fallback.
* **Exact model echo.**  A present echoed ``model`` must equal the pinned
  request slug BYTE-FOR-BYTE (case-sensitive); uppercase, mixed-case and
  near-alias variants are substituted-model refusals.
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
import math
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

# Direct source CLI and flat native releases use the same policy source.
from pathlib import Path as _PolicyPath
import sys as _policy_sys
_policy_source_root = _PolicyPath(__file__).resolve().parents[3]
if (_policy_source_root / "control_plane" / "experiential_plan_policy.py").is_file():
    _policy_sys.path.insert(0, str(_policy_source_root))

try:
    from control_plane.experiential_plan_policy import (
        PLAN_MODELS, FREE_NATIVE_MODELS, plan_model_endpoint, PlanRequestRefused, admit_plan_account,
        plan_policy_digest, route_policy_generation, select_plan_model,
    )
except ModuleNotFoundError as exc:
    if exc.name not in {"control_plane", "control_plane.experiential_plan_policy"}:
        raise
    from experiential_plan_policy import (
        PLAN_MODELS, FREE_NATIVE_MODELS, plan_model_endpoint, PlanRequestRefused, admit_plan_account,
        plan_policy_digest, route_policy_generation, select_plan_model,
    )

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

#: Worst-case completion size bound sent on EVERY admitted request.  This
#: transport serves bounded manual fix_build-class packet work, not free-form
#: generation: 512 output tokens is ample headroom for those task classes
#: while capping the worst-case billed exposure per request — including a
#: request that fails or disconnects mid-generation (vendor law: that may
#: still incur charge and is never retried or refunded here).  A caller may
#: tighten the cap per request via ``max_output_tokens=``; NOTHING can
#: loosen it: the constant is the ceiling, never an argument default that
#: admits a larger value and never a route field.
MAX_OUTPUT_TOKENS = 512

#: The provider reconciliation handle (response header ``X-Request-Id``) is
#: an opaque, bounded, non-secret string.  Strict shape law: printable ASCII
#: (no whitespace, no control characters — log-safe by construction), at
#: most 128 characters.  Anything else is unusable and is NEVER surfaced,
#: logged raw or substituted by the local ``Idempotency-Key``.
MAX_PROVIDER_REQUEST_ID_CHARS = 128
_PROVIDER_REQUEST_ID_RE = re.compile(r"^[\x21-\x7e]{1,128}$")

#: Cost reconciliation status vocabulary (typed, metadata-only).  This
#: transport NEVER invents a cost figure: a missing/unusable inline
#: observation stays PENDING for the EXISTING billing owner to reconcile via
#: the provider request id and the settled usage export; a type-safe
#: observation is surfaced inline-only and is explicitly NOT settled
#: billing.  ``cost_settled`` is False by law on this surface.
COST_RECONCILIATION_PENDING = "COST_RECONCILIATION_PENDING"
COST_RECONCILIATION_OBSERVED_INLINE = "COST_RECONCILIATION_OBSERVED_INLINE"
PROVIDER_REQUEST_ID_PRESENT = "PROVIDER_REQUEST_ID_PRESENT"
PROVIDER_REQUEST_ID_MISSING = "PROVIDER_REQUEST_ID_MISSING"
PROVIDER_REQUEST_ID_MALFORMED = "PROVIDER_REQUEST_ID_MALFORMED"

#: A type-safe inline cost observation must be a finite, non-negative number
#: within this typed sanity bound; anything else is untrusted and recorded
#: as unusable (PENDING), never as a dollar figure.
MAX_INLINE_COST_USD = 100.0

_RUN_ID_RE = pin.RUN_ID_RE
_PACKET_ROOT_RE = re.compile(r"^(?:/[A-Za-z0-9][A-Za-z0-9_./:-]{0,1022}|[A-Za-z0-9][A-Za-z0-9_./:-]{0,254})$")
_PROXY_TOKEN_RE = re.compile(r"^[\x21-\x7e]{24,256}$")
_ROUTE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
#: Provider key shape (Experiential Labs ``xpl_`` keys).  The gateway owns
#: these; a transport route carries the host-managed proxy token instead.
_PROVIDER_KEY_PREFIX = "xpl_"


class ExperientialTransportRefused(RuntimeError):
    """Typed, fail-closed transport refusal (stable upper-snake ``reason``).

    ``detail`` is metadata-only by construction: status codes, header names,
    limit names, and — since billing01 — the SHAPE-VALIDATED provider
    reconciliation handle (bounded printable ASCII, log-safe by
    construction).  Prompt, response body, the proxy token and any
    malformed/unvalidated header value can never enter it, so a refusal is
    safe to log.
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
    plan_policy: str = "legacy"
    endpoint: str = GATEWAY_CHAT_PATH


@dataclass(frozen=True)
class InferenceOutcome:
    """Secret-free terminal outcome of the ONE admitted inference request.

    Carries the packet identity verbatim and the completion text.  No token,
    no route credentials, no request bodies beyond the returned content.

    Cost/reconciliation fields (typed, never invented):

    * ``provider_request_id`` — the validated opaque provider
      ``X-Request-Id`` response handle (or ``None`` when missing/malformed;
      the raw malformed value never surfaces).  Distinct from the locally
      sent ``Idempotency-Key``.
    * ``cost_status`` — ``COST_RECONCILIATION_PENDING`` while the per-request
      cost is UNKNOWN (the default for idempotent-annotated requests, which
      the provider deliberately does not annotate with ``usage.cost``), or
      ``COST_RECONCILIATION_OBSERVED_INLINE`` for a type-safe inline
      observation that is explicitly NOT settled.
    * ``cost_usd_observed`` — only ever a type-safe inline observation;
      ``None`` otherwise.  Zero is never synthesized.
    * ``cost_settled`` — False by law on this surface; settlement belongs to
      the existing billing owner via the settled usage export.
    * ``max_output_tokens`` — the worst-case output bound actually sent.
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
    provider_request_id: Optional[str] = None
    provider_request_id_status: str = PROVIDER_REQUEST_ID_MISSING
    cost_status: str = COST_RECONCILIATION_PENDING
    cost_usd_observed: Optional[float] = None
    cost_settled: bool = False
    cost_detail: str = "not_observed"
    max_output_tokens: Optional[int] = MAX_OUTPUT_TOKENS
    request_endpoint: str = GATEWAY_CHAT_PATH
    plan_lane: Optional[str] = None

    def summary(self) -> Dict[str, Any]:
        """Metadata-only view (no completion text, no credentials)."""
        return {
            "source": self.source,
            "plan_lane": self.plan_lane,
            "request_endpoint": self.request_endpoint,
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
            "provider_request_id": self.provider_request_id,
            "provider_request_id_status": self.provider_request_id_status,
            "cost_status": self.cost_status,
            "cost_usd_observed": self.cost_usd_observed,
            "cost_settled": self.cost_settled,
            "cost_detail": self.cost_detail,
            "max_output_tokens": self.max_output_tokens,
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
    allowed_paths = {GATEWAY_CHAT_PATH}
    if route.plan_policy in {"free_only", "free_and_uncensored"}:
        allowed_paths.update(FREE_NATIVE_MODELS.values())
    if route.endpoint not in allowed_paths:
        raise ExperientialTransportRefused("GATEWAY_ROUTE_ENDPOINT_REFUSED")
    split = urlsplit(_gateway_url(route))
    if split.hostname != GATEWAY_HOST or split.path != f"{GATEWAY_BASE_PATH}/{route.endpoint}":
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
            f"{route.base_path}/{route.endpoint}")


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


def _build_request_frame(prompt: str, system: Any, max_tokens: int, model: str = MODEL) -> bytes:
    """The exact admitted request frame.  The model is the pin's law; the
    frame is non-streaming by law; ``max_tokens`` is the validated
    tighten-only worst-case output bound; no other caller-supplied field can
    enter it."""
    messages: list = []
    if isinstance(system, str) and system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    # Vendor-owned retries and waterfall fallbacks occur *inside* one HTTP POST.
    # Disabling HTTP SDK retries alone would still permit up to eight generation
    # dispatches. Pin one attempt and forbid internal provider-rung fallback.
    # These are documented Experiential gateway controls, not provider fields.
    frame = {
        "model": model,
        "messages": messages,
        "stream": False,
        # Fixed conservative worst-case output bound.  A request that fails
        # or disconnects mid-generation may still incur charge (vendor law),
        # so the cap also bounds failed-call exposure; there is no refund or
        # retry path here to lean on.
        "max_tokens": max_tokens,
        "gateway": {
            "retry": {
                "max_attempts_per_route": 1,
                "max_total_attempts": 1,
                "backoff": {"type": "none"},
            },
            "routing": {"allow_fallbacks": False},
        },
    }
    body = json.dumps(frame, ensure_ascii=False).encode("utf-8")
    if len(body) > MAX_REQUEST_BYTES:
        raise ExperientialTransportRefused(
            "REQUEST_BODY_TOO_LARGE",
            f"encoded frame {len(body)} bytes > {MAX_REQUEST_BYTES}")
    return body


def _native_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate native field")
        value[key] = item
    return value


def _native_constant(_value):
    raise ValueError("nonfinite native value")


def validate_native_packet(prompt: str, model: str) -> dict:
    """A typed decision packet is data; its answers never execute an action."""
    try:
        payload = json.loads(prompt, object_pairs_hook=_native_object,
                             parse_constant=_native_constant)
    except (ValueError, TypeError, RecursionError) as exc:
        raise ExperientialTransportRefused("PLAN_NATIVE_PACKET_INVALID") from exc
    endpoint = FREE_NATIVE_MODELS.get(model)
    state_key = "state" if endpoint == "systemone" else "input"
    if (endpoint is None or type(payload) is not dict
            or set(payload) != {state_key, "questions"}
            or not isinstance(payload[state_key], (str, dict, list))
            or not payload[state_key]
            or (endpoint == "decisions" and type(payload[state_key]) is dict)):
        raise ExperientialTransportRefused("PLAN_NATIVE_PACKET_INVALID")
    questions = payload["questions"]
    if endpoint == "systemone":
        if type(questions) is not dict or not 1 <= len(questions) <= 32:
            raise ExperientialTransportRefused("PLAN_NATIVE_QUESTIONS_INVALID")
        if any(type(name) is not str or not _ROUTE_ID_RE.fullmatch(name) for name in questions):
            raise ExperientialTransportRefused("PLAN_NATIVE_QUESTIONS_INVALID")
        rows = list(questions.values())
    else:
        if type(questions) is not list or not 1 <= len(questions) <= 32:
            raise ExperientialTransportRefused("PLAN_NATIVE_QUESTIONS_INVALID")
        rows = questions
    names = set()
    for question in rows:
        if type(question) is not dict:
            raise ExperientialTransportRefused("PLAN_NATIVE_QUESTIONS_INVALID")
        kind = question.get("type")
        kinds = {"noul", "choice", "score"} if endpoint == "systemone" else {"predicate", "choice", "score"}
        instructions = question.get("instructions")
        allowed = {"type", "instructions", "criteria"} if endpoint == "systemone" else {"type", "instructions", "name", "choices", "levels"}
        if (type(kind) is not str or kind not in kinds or set(question) - allowed
                or type(instructions) is not str or not instructions.strip()
                or len(instructions) > 65536):
            raise ExperientialTransportRefused("PLAN_NATIVE_QUESTIONS_INVALID")
        name = question.get("name")
        if name is not None:
            if type(name) is not str or not _ROUTE_ID_RE.fullmatch(name) or name in names:
                raise ExperientialTransportRefused("PLAN_NATIVE_QUESTIONS_INVALID")
            names.add(name)
        if kind in {"noul", "predicate"}:
            if set(question).intersection({"criteria", "choices", "levels"}):
                raise ExperientialTransportRefused("PLAN_NATIVE_QUESTIONS_INVALID")
            continue
        if endpoint == "systemone":
            options = question.get("criteria")
            if kind == "choice":
                valid = (type(options) is dict and 2 <= len(options) <= 64
                         and all(type(k) is str and k and type(v) is str and v for k, v in options.items()))
            else:
                valid = type(options) is list and 2 <= len(options) <= 10 and all(type(v) is str and v for v in options)
        else:
            options = question.get("choices" if kind == "choice" else "levels")
            label = "value" if kind == "choice" else "label"
            limit = 64 if kind == "choice" else 10
            valid = (type(options) is list and 2 <= len(options) <= limit
                     and all(type(v) is dict and set(v) == {label, "description"}
                             and type(v[label]) is str and v[label]
                             and type(v["description"]) is str and v["description"] for v in options))
            if valid:
                valid = len({v[label] for v in options}) == len(options)
            if ("levels" if kind == "choice" else "choices") in question:
                valid = False
        if not valid:
            raise ExperientialTransportRefused("PLAN_NATIVE_QUESTIONS_INVALID")
    return payload


def _build_native_frame(prompt: str, system: Any, model: str) -> bytes:
    if system:
        raise ExperientialTransportRefused("PLAN_NATIVE_SYSTEM_PROMPT_REFUSED")
    frame = validate_native_packet(prompt, model)
    frame["model"] = model
    frame["gateway"] = {"routing": {"allow_fallbacks": False},
        "retry": {"max_attempts_per_route": 1, "max_total_attempts": 1,
                  "backoff": {"type": "none"}}}
    raw = json.dumps(frame, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(raw) > MAX_REQUEST_BYTES:
        raise ExperientialTransportRefused("REQUEST_BODY_TOO_LARGE")
    return raw


def _parse_native_completion(raw, content_type, model, packet, canonical_model=None):
    """Return typed native answers in their original question order/identity."""
    if not content_type.lower().startswith("application/json"):
        raise ExperientialTransportRefused("GATEWAY_RESPONSE_MALFORMED")
    try:
        frame = json.loads(raw, object_pairs_hook=_native_object, parse_constant=_native_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ExperientialTransportRefused("GATEWAY_RESPONSE_MALFORMED") from exc
    if type(frame) is not dict or "error" in frame:
        raise ExperientialTransportRefused("GATEWAY_RESPONSE_MALFORMED")
    echo = frame.get("model")
    allowed_echoes = {model, model.removesuffix(":free")}
    # The Decisions alias exposes the documented underlying OpenAI Luna model.
    if model == "gpt-6-luna-decisions:free":
        allowed_echoes.add("gpt-6-luna")
    if echo is not None and (type(echo) is not str or echo not in allowed_echoes):
        # TypeSafe documents a concrete Jev semantic version for jev-latest.
        # The exact free request alias/endpoint stays pinned; a reported release
        # is retained as model_echo, never used to select or send another model.
        if not (model == "jev-latest:free" and type(echo) is str
                and re.fullmatch(r"jev-\d+\.\d+\.\d+", echo)
                and (canonical_model is None or canonical_model in allowed_echoes | {echo})):
            raise ExperientialTransportRefused("GATEWAY_RESPONSE_MODEL_MISMATCH")
    questions, answers = packet["questions"], frame.get("answers")
    if FREE_NATIVE_MODELS[model] == "systemone":
        if type(answers) is not dict or set(answers) != set(questions):
            raise ExperientialTransportRefused("GATEWAY_RESPONSE_MALFORMED")
        pairs = [(questions[name], answers[name]) for name in questions]
    else:
        if type(answers) is not list or len(answers) != len(questions):
            raise ExperientialTransportRefused("GATEWAY_RESPONSE_MALFORMED")
        pairs = list(zip(questions, answers))
    for question, answer in pairs:
        if type(answer) is not dict:
            raise ExperientialTransportRefused("GATEWAY_RESPONSE_MALFORMED")
        if answer.get("type") == "refusal":
            raise ExperientialTransportRefused("GATEWAY_RESPONSE_REFUSAL")
        kind = question["type"]
        if answer.get("type") != kind or answer.get("name") != question.get("name"):
            raise ExperientialTransportRefused("GATEWAY_RESPONSE_MALFORMED")
        if kind in {"predicate", "noul", "score"}:
            key = "probability" if kind == "predicate" else kind
            value = answer.get(key)
            top = len(question.get("criteria", question.get("levels", []))) - 1 if kind == "score" else 1
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= top:
                raise ExperientialTransportRefused("GATEWAY_RESPONSE_MALFORMED")
        else:
            values = question.get("criteria")
            if values is None:
                values = [item["value"] for item in question["choices"]]
            if type(answer.get("choice")) is not str or answer["choice"] not in values:
                raise ExperientialTransportRefused("GATEWAY_RESPONSE_MALFORMED")
    return json.dumps(frame, ensure_ascii=False, allow_nan=False), echo, frame.get("usage")


def _classify_http_error(status: int, content_type: str,
                         provider_request_id: str = "") -> ExperientialTransportRefused:
    """One typed refusal per status class.  No status is silently accepted.

    ``provider_request_id`` (when the failed response carried a VALIDATED
    ``X-Request-Id``) is appended to the typed detail: the vendor documents
    that a failed or disconnected request may still incur charge, so the
    existing billing owner must be able to reconcile even refused POSTs via
    the provider handle.  The handle is shape-validated printable ASCII, so
    the detail stays metadata-only and log-safe.
    """
    if 300 <= status < 400:
        refusal = ExperientialTransportRefused(
            "GATEWAY_REDIRECT_REFUSED", f"status {status}")
    elif status in (401, 403):
        refusal = ExperientialTransportRefused(
            "GATEWAY_AUTH_REFUSED", f"status {status}")
    elif status == 413:
        refusal = ExperientialTransportRefused("GATEWAY_REQUEST_TOO_LARGE", "status 413")
    elif status == 429:
        refusal = ExperientialTransportRefused(
            "GATEWAY_RATE_LIMITED", "status 429; Retry-After is never obeyed (one POST)")
    elif 400 <= status < 500:
        refusal = ExperientialTransportRefused("GATEWAY_REQUEST_REFUSED", f"status {status}")
    elif status == 503:
        refusal = ExperientialTransportRefused(
            "GATEWAY_LOCAL_QUEUE_FULL", "status 503")
    elif status == 504:
        refusal = ExperientialTransportRefused(
            "GATEWAY_QUEUE_WAIT_EXPIRED", "status 504")
    elif status >= 500:
        refusal = ExperientialTransportRefused("GATEWAY_UPSTREAM_ERROR", f"status {status}")
    elif status != 200:
        # e.g. the gateway's 204 disconnected-caller response: not a success,
        # and never silently accepted as an empty completion.
        refusal = ExperientialTransportRefused("GATEWAY_STATUS_REFUSED", f"status {status}")
    else:
        refusal = ExperientialTransportRefused(
            "GATEWAY_RESPONSE_MALFORMED", "expected Content-Type application/json")
    if provider_request_id:
        refusal.detail = (f"{refusal.detail}; provider_request_id="
                          f"{provider_request_id}")
    return refusal


def _parse_completion(raw: bytes, content_type: str, expected_model: str = MODEL) -> Tuple[str, Optional[str], Any]:
    """The exact JSON response law: 200 + JSON + non-empty choices + content.

    The echoed ``model`` must match the pinned request slug BYTE-FOR-BYTE —
    case-sensitive (``GLM-5.3-UNCENSORED`` and other variants are substituted
    models, never accepted foldings).  A response carrying NO ``model`` field
    keeps the incumbent metadata tolerance and is refused downstream by the
    choices/content law instead.  The raw ``usage`` object, if any, is
    returned unvalidated; typed cost observation is :func:`_observe_cost`'s
    law.
    """
    if not content_type.lower().startswith("application/json"):
        raise ExperientialTransportRefused(
            "GATEWAY_RESPONSE_MALFORMED", "expected Content-Type application/json")
    try:
        frame = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ExperientialTransportRefused(
            "GATEWAY_RESPONSE_MALFORMED", "body is not UTF-8 JSON")
    if not isinstance(frame, dict):
        raise ExperientialTransportRefused("GATEWAY_RESPONSE_MALFORMED", "frame is not an object")
    model_echo = frame.get("model")
    if model_echo is not None:
        allowed_echoes = {expected_model}
        if expected_model in PLAN_MODELS and expected_model.endswith(":free"):
            allowed_echoes.add(expected_model[:-5])
        if not isinstance(model_echo, str) or model_echo not in allowed_echoes:
            raise ExperientialTransportRefused(
                "GATEWAY_RESPONSE_MODEL_MISMATCH",
                f"expected pinned model {expected_model!r}")
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
    return (content,
            model_echo if isinstance(model_echo, str) else None,
            frame.get("usage"))


def _validate_output_tokens(value: Any) -> int:
    """Tighten-only worst-case output law.  ``None`` selects the constant.

    The module constant ``MAX_OUTPUT_TOKENS`` is the ceiling; a caller may
    lower the cap for one request, and ANY other value (too large, non-int,
    bool, zero, negative) is refused BEFORE any dial.  There is no parameter,
    flag or route field that raises the cap.
    """
    if value is None:
        return MAX_OUTPUT_TOKENS
    if isinstance(value, bool) or not isinstance(value, int) \
            or not 1 <= value <= MAX_OUTPUT_TOKENS:
        raise ExperientialTransportRefused(
            "MAX_OUTPUT_TOKENS_INVALID",
            f"expected an int in [1, {MAX_OUTPUT_TOKENS}]; "
            "the worst-case output cap is never loosened")
    return int(value)


def _validate_provider_request_id(value: Any) -> Optional[str]:
    """The provider ``X-Request-Id`` RESPONSE header, as an opaque handle.

    Returns the handle only when it passes the strict bounded printable-ASCII
    shape (1-128 chars, no whitespace/control — log-safe by construction);
    anything else returns ``None`` and the raw value is discarded: never
    surfaced, never logged, never replaced by the locally sent
    ``Idempotency-Key``.  The handle is NOT a secret and NOT a credential —
    it is the reconciliation key the EXISTING billing owner uses against the
    settled Cost API (``GET /api/v1/generation?id=<x-request-id>``) / usage
    export.  This module never dials that API.
    """
    if not isinstance(value, str):
        return None
    handle = value.strip()
    if not handle \
            or len(handle) > MAX_PROVIDER_REQUEST_ID_CHARS \
            or _PROVIDER_REQUEST_ID_RE.fullmatch(handle) is None:
        return None
    return handle


def _provider_handle_status(raw: Any, handle: Optional[str]) -> str:
    """Typed observation status for the provider reconciliation handle."""
    if handle is not None:
        return PROVIDER_REQUEST_ID_PRESENT
    if raw is None:
        return PROVIDER_REQUEST_ID_MISSING
    return PROVIDER_REQUEST_ID_MALFORMED


def _observe_cost(usage: Any) -> Tuple[str, Optional[float], bool, str]:
    """Typed, fail-safe cost observation from the response ``usage`` object.

    Returns ``(cost_status, cost_usd_observed, cost_settled, cost_detail)``:

    * NO usable inline observation -> ``COST_RECONCILIATION_PENDING`` /
      ``None`` / ``False``.  Requests sent with an ``Idempotency-Key`` are
      deliberately NOT annotated with ``usage.cost`` by the vendor, so this
      is the EXPECTED posture: the per-request cost is UNKNOWN here and the
      existing billing owner reconciles later via the provider request id /
      settled usage export.  Zero USD is NEVER synthesized.
    * a type-safe observation (finite, non-negative, within the typed sanity
      bound) -> ``COST_RECONCILIATION_OBSERVED_INLINE`` / the value /
      ``False`` — explicitly an INLINE OBSERVATION, not settled billing;
      never accumulated, never written anywhere by this module.
    * present-but-untrusted values (wrong type, negative, non-finite, beyond
      the bound) -> PENDING with a typed detail; the raw value never surfaces.
    * ``usage.is_byok`` true -> typed ``COST_BYOK_REFUSED``: this
      platform-funded-only pool never consumes caller-brought provider
      credentials.  Fail closed; the completion is discarded; no retry, no
      fallback, no refund path (settlement/reconciliation stays with the
      existing billing owner).
    """
    cost_settled = False  # this surface NEVER asserts settled billing
    if not isinstance(usage, dict):
        if usage is None:
            return (COST_RECONCILIATION_PENDING, None, cost_settled,
                    "usage_frame_missing")
        return (COST_RECONCILIATION_PENDING, None, cost_settled,
                "usage_frame_unusable")
    is_byok = usage.get("is_byok")
    if is_byok is True:
        raise ExperientialTransportRefused(
            "COST_BYOK_REFUSED",
            "usage.is_byok=true: this pool is platform-funded only and never "
            "runs on caller-brought provider credentials; no retry, no "
            "fallback")
    if is_byok is not None and is_byok is not False:
        # A non-boolean is_byok cannot be interpreted: no inline observation
        # may be claimed from an untrusted usage block (the cost law stays
        # PENDING).  Typed detail only; the raw value never surfaces.
        return (COST_RECONCILIATION_PENDING, None, cost_settled,
                "usage_is_byok_unusable")
    raw_cost = usage.get("cost")
    if raw_cost is None:
        return (COST_RECONCILIATION_PENDING, None, cost_settled,
                "usage_cost_missing")
    if isinstance(raw_cost, bool) or not isinstance(raw_cost, (int, float)):
        return (COST_RECONCILIATION_PENDING, None, cost_settled,
                "usage_cost_unusable_type")
    cost = float(raw_cost)
    if not math.isfinite(cost) or cost < 0 or cost > MAX_INLINE_COST_USD:
        return (COST_RECONCILIATION_PENDING, None, cost_settled,
                "usage_cost_unusable_value")
    return (COST_RECONCILIATION_OBSERVED_INLINE, cost, cost_settled,
            "inline_observation_not_settled")


def require_plan_route_qualified(route: GatewayRoute, model: str) -> None:
    """A plan route is host-enrolled and bound to the enforced gateway policy.

    Legacy qualification constants retain their original meaning. A new plan
    must use a distinct scoped account, fresh metadata and a policy-bound route.
    """
    _validate_route(route)
    if model not in PLAN_MODELS or route.plan_policy not in {"free_only", "free_and_uncensored"}:
        raise ExperientialTransportRefused("PLAN_GATEWAY_POLICY_REQUIRED")
    base = f"{route.scheme}://{route.host}:{route.port}{route.base_path}"
    if route.endpoint != plan_model_endpoint(model):
        raise ExperientialTransportRefused("PLAN_GATEWAY_MODEL_PROTOCOL_MISMATCH")
    if route.route_generation != route_policy_generation(base, route.endpoint, route.plan_policy):
        raise ExperientialTransportRefused("PLAN_GATEWAY_GENERATION_MISMATCH")


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
    max_output_tokens: Optional[int] = None,
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
    5. bounded request framing — fixed conservative ``max_tokens`` worst-case
       output bound (tighten-only; the module constant is the ceiling),
    6. exactly one fail-closed POST,
    7. exact JSON response law -> provider ``X-Request-Id`` reconciliation
       handle + typed cost posture -> secret-free outcome.

    No step is optional and no step is cached: the acks, the account law and
    the readback are re-evaluated per request.

    The outcome NEVER asserts a settled cost: a response without a usable
    inline ``usage.cost`` is ``COST_RECONCILIATION_PENDING`` (the expected
    posture for idempotency-annotated requests), and the provider
    ``X-Request-Id`` handle — not this module — is what the existing billing
    owner reconciles against the settled usage export.  A ``usage.is_byok``
    true response fails closed (``COST_BYOK_REFUSED``) with the completion
    discarded and no retry.
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
    if admitted["model"] in PLAN_MODELS:
        require_plan_route_qualified(route, admitted["model"])
        if route.plan_policy != admitted["plan_policy"]:
            raise ExperientialTransportRefused("PLAN_GATEWAY_POLICY_MISMATCH")
    else:
        require_route_qualified()
        _validate_route(route)
    _validate_prompt(prompt, system, bounded)
    native_packet = None
    if admitted["model"] in FREE_NATIVE_MODELS:
        if max_output_tokens is not None:
            raise ExperientialTransportRefused("PLAN_NATIVE_OUTPUT_TOKEN_OPTION_REFUSED")
        native_packet = validate_native_packet(prompt, admitted["model"])
        output_cap = None  # Native decision models are input-billed, not chat generation.
        body = _build_native_frame(prompt, system, admitted["model"])
    else:
        output_cap = _validate_output_tokens(max_output_tokens)
        body = _build_request_frame(prompt, system, output_cap, admitted["model"])

    headers = {
        "Authorization": f"Bearer {route.proxy_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        # One logical request; the gateway's idempotency law (#1849).
        **({"Idempotency-Key": rid} if native_packet is None else {}),
        # Content-Length is deliberately NOT set here: urllib computes it, and
        # a duplicate Content-Length is refused by the attempt boundary law.
    }
    if admitted["model"] in PLAN_MODELS:
        headers["X-Fabric-Plan-Policy"] = admitted["policy_digest"]
    request = urllib.request.Request(_gateway_url(route), data=body,
                                     headers=headers, method="POST")
    opener = _build_opener()
    try:
        response = opener.open(request, timeout=bounded.socket_timeout)
    except ExperientialTransportRefused:
        raise
    except urllib.error.HTTPError as exc:
        content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
        # A failed POST may still incur charge (vendor law): surface the
        # provider's reconciliation handle on the typed refusal when it is
        # present and shape-valid, so the billing owner can reconcile it
        # later.  A malformed/absent handle is simply omitted here and typed
        # on the success path only.
        failed_handle = _validate_provider_request_id(
            exc.headers.get("X-Request-Id") if exc.headers else None)
        try:
            exc.read(MAX_ERROR_BODY_BYTES)  # drained, never surfaced or logged
        except Exception:
            pass
        finally:
            exc.close()
        raise _classify_http_error(exc.code, content_type,
                                   provider_request_id=failed_handle or "")
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
        non200_handle = _validate_provider_request_id(
            response.headers.get("X-Request-Id") if response.headers else None)
        try:
            response.read(MAX_ERROR_BODY_BYTES)
        except Exception:
            pass
        finally:
            response.close()
        raise _classify_http_error(status, content_type,
                                   provider_request_id=non200_handle or "")
    provider_handle_raw = (response.headers.get("X-Request-Id")
                           if response.headers else None)
    provider_handle = _validate_provider_request_id(provider_handle_raw)
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
    try:
        if native_packet is None:
            content, model_echo, usage = _parse_completion(raw, content_type, admitted["model"])
        else:
            content, model_echo, usage = _parse_native_completion(
                raw, content_type, admitted["model"], native_packet,
                response.headers.get("X-Gateway-Canonical-Model"))
        # Inline observation is never settled billing and cannot authorize BYOK.
        cost_status, cost_usd, cost_settled, cost_detail = _observe_cost(usage)
    except ExperientialTransportRefused as exc:
        # A completed HTTP exchange can still have an invalid result. Keep its
        # nonsecret handle so the original request can be reconciled, not resent.
        detail = exc.detail
        if provider_handle:
            detail += ("; " if detail else "") + "provider_request_id=" + provider_handle
        raise ExperientialTransportRefused(exc.reason, detail) from exc
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
        idempotency_key=rid if native_packet is None else "",
        http_status=200,
        bytes_received=len(raw),
        content=content,
        model_echo=model_echo,
        provider_request_id=provider_handle,
        provider_request_id_status=_provider_handle_status(
            provider_handle_raw, provider_handle),
        cost_status=cost_status,
        cost_usd_observed=cost_usd,
        cost_settled=cost_settled,
        cost_detail=cost_detail,
        max_output_tokens=output_cap,
        request_endpoint=route.endpoint,
        plan_lane=admitted.get("plan_lane"),
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
    print(f"MAX_OUTPUT_TOKENS={MAX_OUTPUT_TOKENS}")
    print(f"COST_LAW={COST_RECONCILIATION_PENDING}_OR_"
          f"{COST_RECONCILIATION_OBSERVED_INLINE}_NEVER_SYNTHESIZED")
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
