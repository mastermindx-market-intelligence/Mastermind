"""The unified Capacity Fabric router: one Anthropic-wire edge over every pool.

T3 (or any Anthropic Messages client) talks to this loopback service. For each
request the router resolves the model (or a ``fabric/*`` alias), selects a
route at admission time from live pool knowledge, and forwards — Anthropic
wire passthrough where the pool speaks it, closed translation where the pool
speaks the OpenAI wire. It owns no new credential store: loopback gateways use
their own local tokens and vendor keys are read live from the Hermes
credential pool. A request is never replayed to a second route after a
possible upstream effect; exhausted pools surface as typed refusals.
"""
from __future__ import annotations

import asyncio
import bisect
import functools
import hashlib
import hmac
import ipaddress
import json
import logging
import math
import os
import re

import time
import uuid
from dataclasses import dataclass, field
from http import HTTPStatus
from pathlib import Path

import httpx
import anyio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.requests import ClientDisconnect

from ops.native_fabric.unified_router.routes import (
    DEFAULT_AUTH_STORE,
    Route,
    RouteState,
    RoutePermit,
    WIRE_ANTHROPIC,
    WIRE_OPENAI,
    WIRE_RESPONSES,
    config_file_route_key,
    credential_pool_key,
    env_file_value,
    retry_after_seconds,
    decide_route,
)
from ops.native_fabric.unified_router import codex_oauth
from ops.native_fabric.unified_router.streaming import SSEDecoder, events, read_bounded
from ops.native_fabric.unified_router.wire import (
    OpenAIStreamTranslator,
    ResponsesStreamTranslator,
    WireTranslationError,
    anthropic_to_openai,
    anthropic_to_responses,
    openai_to_anthropic,
    responses_to_anthropic,
)

ALLOWED = {("POST", "v1/messages"), ("POST", "v1/messages/count_tokens"),
           ("GET", "v1/models")}

_log = logging.getLogger(__name__)

# One shared bound for request cleanup and the existing service drain contract.
UPSTREAM_CLEANUP_TIMEOUT_S = 5.0

# Public exception reasons are a closed set of router-authored literals. Return
# the registered literal, never exception text merely matching a FABRIC_* shape.
_PUBLIC_REFUSAL_CODES = (
    "FABRIC_EXACT_MODEL_REQUIRED",
    "FABRIC_INVALID_REQUEST",
    "FABRIC_RESPONSE_INVALID",
    "FABRIC_RESPONSE_INVALID_JSON",
    "FABRIC_RESPONSE_TOO_LARGE",
    "FABRIC_STREAM_CONTENT_TYPE",
    "FABRIC_STREAM_EVENT_TOO_LARGE",
    "FABRIC_STREAM_INCOMPLETE",
    "FABRIC_STREAM_INVALID",
    "FABRIC_STREAM_INVALID_JSON",
    "FABRIC_STREAM_INVALID_UTF8",
    "FABRIC_STREAM_TRUNCATED",
    "FABRIC_TRANSLATE_BLOCK",
    "FABRIC_TRANSLATE_BODY",
    "FABRIC_TRANSLATE_CHUNK",
    "FABRIC_TRANSLATE_INVALID",
    "FABRIC_TRANSLATE_MESSAGE",
    "FABRIC_TRANSLATE_RESPONSE",
    "FABRIC_TRANSLATE_ROLE",
    "FABRIC_TRANSLATE_TOOL_ARGUMENTS",
    "FABRIC_TRANSLATE_TOOL_CALL",
    "FABRIC_TRANSLATE_TOOL_IDENTITY",
    "FABRIC_UPSTREAM_INCOMPLETE",
    "FABRIC_UPSTREAM_RESPONSE_ERROR",
    "FABRIC_UPSTREAM_STREAM_ERROR",
)
LATENCY_BUCKET_UPPER_MS = (10., 50., 100., 250., 500., 1000., 2500., 5000.,
                          10000., 30000., 60000., 180000., 600000., 1800000.)
LATENCY_METRICS = frozenset({"headers_ms", "first_content_ms", "completion_ms"})
SELECTION_REASONS = frozenset({"FABRIC_MODEL_UNKNOWN", "FABRIC_ROUTES_DRAINED",
                               "FABRIC_ALL_ROUTES_COOLING", "FABRIC_ROUTES_BUSY"})
PRESELECTION_REASONS = frozenset({
    "FABRIC_ROUTER_BUSY", "FABRIC_REQUEST_TOO_LARGE", "FABRIC_REQUEST_BODY_TIMEOUT",
    "FABRIC_INVALID_REQUEST", "FABRIC_EXACT_MODEL_REQUIRED", "FABRIC_COUNT_TOKENS_WIRE",
    "FABRIC_ADMISSION_DEADLINE", "FABRIC_REQUEST_DISCONNECTED", "FABRIC_REQUEST_CANCELLED"})
PREFLIGHT_REASONS = frozenset({
    "FABRIC_OAUTH_OWNER_UNAVAILABLE", "FABRIC_OAUTH_OWNER_REFRESH_REQUIRED",
    "FABRIC_OAUTH_OWNER_HELD", "FABRIC_OAUTH_QUOTA_UNKNOWN",
    "FABRIC_OAUTH_ACCOUNTS_EXHAUSTED"})
_TERMINAL_REASONS = (frozenset(_PUBLIC_REFUSAL_CODES) | PRESELECTION_REASONS
                     | PREFLIGHT_REASONS | frozenset({
    "FABRIC_ROUTE_CREDENTIAL", "FABRIC_ROUTE_UNAVAILABLE", "FABRIC_ROUTE_CONNECT",
    "FABRIC_ROUTE_LOCAL_POOL_TIMEOUT", "FABRIC_UPSTREAM_EFFECT_UNKNOWN",
    "FABRIC_OAUTH_ACCOUNT_LIMIT"}))
_USAGE_FIELDS = ("input_tokens", "output_tokens", "cache_read_input_tokens",
                 "cache_creation_input_tokens")


@dataclass
class _ReceiptIdentity:
    """Bounded correlation only; never retain/log provider-controlled ID text."""
    sha256: str | None = None
    state: str = "unavailable"

    def observe(self, value) -> None:
        if value is None or self.state in {"invalid", "conflicting"}:
            return
        if not isinstance(value, str) or not 0 < len(value) <= 256:
            self.sha256, self.state = None, "invalid"
            return
        try:
            encoded = value.encode("utf-8")
        except UnicodeEncodeError:
            self.sha256, self.state = None, "invalid"
            return
        if len(encoded) > 256:
            self.sha256, self.state = None, "invalid"
            return
        digest = hashlib.sha256(encoded).hexdigest()
        if self.sha256 is not None and self.sha256 != digest:
            self.sha256, self.state = None, "conflicting"
        else:
            self.sha256, self.state = digest, "observed"


def _reported_count(value) -> int | None:
    # Booleans, numeric strings, floats and unreasonable/negative counts are
    # not measurements. A reported zero is distinct from missing metadata.
    return value if type(value) is int and 0 <= value <= 2**63 - 1 else None


@functools.lru_cache(maxsize=1)
def _receipt_source_sha256() -> str | None:
    # Identifies this gateway source only, not the whole release/configuration.
    # The caller contains I/O/logging failures so observation cannot affect work.
    try:
        return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    except OSError:
        return None


def _public_reason(exc: Exception, fallback: str) -> str:
    """Select a fixed public reason without propagating exception contents."""
    detail = str(exc)
    for public_code in _PUBLIC_REFUSAL_CODES:
        if detail == public_code:
            return public_code
    _log.warning("unified router withheld exception detail: %s", type(exc).__name__)
    return fallback


async def _run_in_executor(fn, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(fn, *args, **kwargs))


@dataclass(frozen=True)
class Settings:
    proxy_token: str
    state_dir: Path
    routes: tuple[Route, ...] = ()
    aliases: tuple[tuple[str, tuple[str, ...]], ...] = ()
    auth_store: Path = DEFAULT_AUTH_STORE
    max_body_bytes: int = 8 * 1024 * 1024
    upstream_timeout_s: float = 900.0
    route_cooldown_s: float = 30.0
    max_in_flight: int = 32
    request_timeout_s: float = 1800.0
    request_body_timeout_s: float = 30.0
    max_response_bytes: int = 16 * 1024 * 1024
    max_sse_event_bytes: int = 1024 * 1024
    max_attempts: int = 8
    model_labels: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if len(self.proxy_token) < 24:
            raise ValueError("FABRIC_ROUTER_TOKEN must contain at least 24 characters")
        if not self.routes:
            raise ValueError("the unified router needs at least one route")
        ids = [r.route_id for r in self.routes]
        if len(set(ids)) != len(ids):
            raise ValueError("route ids must be unique")
        groups = {}
        for route in self.routes:
            if route.concurrency_group:
                previous = groups.setdefault(route.concurrency_group, route.group_max_in_flight)
                if previous != route.group_max_in_flight:
                    raise ValueError("shared concurrency group ceilings must agree")
        for value in (self.max_in_flight, self.max_body_bytes,
                      self.max_response_bytes, self.max_sse_event_bytes):
            if type(value) is not int or value <= 0:
                raise ValueError("router limits must be positive integers")
        if type(self.max_attempts) is not int or not 1 <= self.max_attempts <= 64:
            raise ValueError("max_attempts must be an integer from 1 through 64")
        known_models = {m.lower() for r in self.routes for m in r.models} | {
            a.strip().lower() for a, _ in self.aliases}
        normalized_labels = {}
        for slug, label in self.model_labels:
            if (not isinstance(slug, str) or slug.strip().lower() not in known_models
                    or slug.strip().lower() in normalized_labels
                    or not isinstance(label, str) or not 1 <= len(label) <= 128
                    or any(ord(c) < 32 for c in label)):
                raise ValueError("model labels must name unique configured models with bounded display text")
            normalized_labels[slug.strip().lower()] = label
        object.__setattr__(self, "model_labels", tuple(normalized_labels.items()))
        for value in (self.upstream_timeout_s, self.route_cooldown_s,
                      self.request_timeout_s, self.request_body_timeout_s):
            if not math.isfinite(value) or value <= 0:
                raise ValueError("router timeouts must be positive and finite")
        for alias, targets in self.aliases:
            if not alias or not targets or not all(isinstance(t, str) and t for t in targets):
                raise ValueError("every alias needs at least one model target")


def _routes_from_document(document: dict) -> tuple[Route, ...]:
    routes = []
    for entry in document.get("routes", []):
        base_url = entry.get("base_url", "")
        if entry.get("kind") == "config_file" and entry.get("base_url_pointer"):
            _, base_url = config_file_route_key(entry.get("config_path", ""),
                                                entry.get("key_pointer", ""),
                                                entry["base_url_pointer"])
        routes.append(Route(
            route_id=entry["route_id"], kind=entry["kind"], base_url=base_url,
            wire=entry.get("wire", WIRE_ANTHROPIC),
            models=tuple(entry.get("models", ())),
            weight=entry.get("weight", 1.0),
            priority=entry.get("priority", 100),
            model_priority=entry.get("model_priority", {}),
            model_weight=entry.get("model_weight", {}),
            model_params=entry.get("model_params", {}),
            pool=entry.get("pool", ""), api_key_label=entry.get("api_key_label", ""),
            env_key=entry.get("env_key", ""),
            gateway_token_env=entry.get("gateway_token_env", ""),
            config_path=entry.get("config_path", ""),
            key_pointer=entry.get("key_pointer", ""),
            base_url_pointer=entry.get("base_url_pointer", ""),
            token_url=entry.get("token_url", ""),
            client_id=entry.get("client_id", ""),
            originator=entry.get("originator", ""),
            upstream_model=tuple((slug, wire) for slug, wire
                                 in entry.get("upstream_model", {}).items()),
            auth_header=entry.get("auth_header", ""),
            session_header=entry.get("session_header", ""),
            max_in_flight=entry.get("max_in_flight", 0),
            concurrency_group=entry.get("concurrency_group", ""),
            group_max_in_flight=entry.get("group_max_in_flight", 0),
            notes=entry.get("notes", "")))
    return tuple(routes)


def settings_from_env() -> Settings:
    routes_path = Path(os.environ.get("FABRIC_ROUTES_JSON", "")).expanduser()
    document = json.loads(routes_path.read_text(encoding="utf-8"))
    aliases = tuple(
        (alias, tuple(targets))
        for alias, targets in document.get("aliases", {}).items())
    return Settings(
        proxy_token=os.environ.get("FABRIC_ROUTER_TOKEN", "").strip(),
        state_dir=Path(os.environ.get("FABRIC_GATEWAY_STATE_DIR", ".state")).expanduser(),
        routes=_routes_from_document(document),
        aliases=aliases,
        auth_store=Path(os.environ.get("FABRIC_AUTH_STORE", str(DEFAULT_AUTH_STORE))).expanduser(),
        max_body_bytes=int(os.environ.get("FABRIC_MAX_BODY_BYTES", str(8 * 1024 * 1024))),
        upstream_timeout_s=float(os.environ.get("FABRIC_UPSTREAM_TIMEOUT_S", "900")),
        route_cooldown_s=float(os.environ.get("FABRIC_ROUTE_COOLDOWN_S", "30")),
        max_in_flight=int(os.environ.get("FABRIC_MAX_IN_FLIGHT", "32")),
        request_timeout_s=float(os.environ.get("FABRIC_REQUEST_TIMEOUT_S", "1800")),
        request_body_timeout_s=float(os.environ.get("FABRIC_REQUEST_BODY_TIMEOUT_S", "30")),
        max_response_bytes=int(os.environ.get("FABRIC_MAX_RESPONSE_BYTES", str(16 * 1024 * 1024))),
        max_sse_event_bytes=int(os.environ.get("FABRIC_MAX_SSE_EVENT_BYTES", str(1024 * 1024))),
        max_attempts=int(os.environ.get("FABRIC_MAX_ATTEMPTS", "8")),
        model_labels=tuple(document.get("model_labels", {}).items()),
    )


@dataclass
class RouterState:
    route_ids: frozenset[str] = field(default_factory=frozenset)
    routes: RouteState = field(default_factory=RouteState)
    started_at: float = field(default_factory=time.time)
    served: int = 0
    refused: int = 0
    selected: int = 0
    failed: int = 0
    cancelled: int = 0
    in_flight: int = 0
    attempts: int = 0
    failovers: int = 0
    exhausted: int = 0
    upstream_send_calls: int = 0
    per_route: dict[str, dict[str, int]] = field(default_factory=dict)
    oauth_cursor: dict[str, int] = field(default_factory=dict)
    oauth_bench: dict[tuple[str, str], float] = field(default_factory=dict)
    latency: dict[str, dict[str, float]] = field(default_factory=dict)
    latency_histograms: dict[str, dict[str, list[int]]] = field(default_factory=dict)
    selection_evaluations: int = 0
    selection_outcomes: dict[str, int] = field(default_factory=dict)
    selection_not_run: dict[str, int] = field(default_factory=dict)
    last_selection: dict | None = None
    last_selection_at: float = 0.0

    def count(self, route_id: str, outcome: str) -> None:
        if route_id not in self.route_ids or outcome not in {
                "selected", "served", "refused", "failed", "cancelled", "cleanup_failed",
                "admission_refused", "attempt_failed"}:
            return
        bucket = self.per_route.setdefault(route_id, {"served": 0, "refused": 0})
        bucket[outcome] = bucket.get(outcome, 0) + 1

    def observe_latency(self, route_id: str, metric: str, value: float) -> None:
        if (route_id not in self.route_ids or metric not in LATENCY_METRICS
                or not math.isfinite(value) or value < 0):
            return
        bucket = self.latency.setdefault(route_id, {})
        old = bucket.get(metric)
        bucket[metric] = value if old is None else .2 * value + .8 * old
        counts = self.latency_histograms.setdefault(route_id, {}).setdefault(
            metric, [0] * (len(LATENCY_BUCKET_UPPER_MS)+1))
        counts[bisect.bisect_left(LATENCY_BUCKET_UPPER_MS, value)] += 1

    def preselection_refused(self, reason: str) -> None:
        key = reason if reason in PRESELECTION_REASONS else "UNCLASSIFIED"
        self.selection_not_run[key] = self.selection_not_run.get(key, 0)+1

    def record_selection(self, decision, *, candidate_index: int, candidate_total: int,
                         configured_alias: bool, owner_excluded: int) -> dict:
        key = ("SELECTED" if decision.route is not None else
               decision.reason if decision.reason in SELECTION_REASONS else "UNCLASSIFIED")
        self.selection_evaluations += 1
        self.selection_outcomes[key] = self.selection_outcomes.get(key, 0)+1
        self.last_selection_at = time.monotonic()
        self.last_selection = dict(
            decision.evidence, sequence=self.selection_evaluations,
            selector_reason=key if decision.route is None else None,
            candidate_index=candidate_index, candidate_total=candidate_total,
            candidate_scope="this_candidate_only", configured_alias=configured_alias,
            owner_preflight_excluded=owner_excluded, local_permit_acquired=False,
            preflight_refusal=None)
        return self.last_selection


def _model_candidates(body: dict, aliases) -> list[tuple[str, str]]:
    """Ordered (model, alias) targets: an alias cascade, else the exact slug."""
    model = body.get("model")
    if not isinstance(model, str) or not model:
        raise WireTranslationError("FABRIC_EXACT_MODEL_REQUIRED")
    for alias, targets in aliases:
        if alias == model:
            return [(target, alias) for target in targets]
    return [(model, "")]


def _route_base_url(route: Route) -> str:
    if route.kind == "config_file" and not route.base_url and route.base_url_pointer:
        _, base_url = config_file_route_key(route.config_path, route.key_pointer,
                                            route.base_url_pointer)
        return base_url
    return route.base_url


def _route_authorization(route: Route, cfg: Settings) -> str:
    if route.kind == "gateway":
        token = os.environ.get(route.gateway_token_env, "")
        if not token:
            raise ValueError(f"route {route.route_id} gateway token missing")
        return token
    if route.kind == "credential_pool":
        if route.env_key:
            return env_file_value(cfg.auth_store, route.env_key)
        return credential_pool_key(cfg.auth_store, route.pool, route.api_key_label)
    if route.kind == "config_file":
        key, _ = config_file_route_key(route.config_path, route.key_pointer,
                                       route.base_url_pointer)
        return key
    raise ValueError(f"route kind {route.kind} cannot be authorized")


def _affinity(payload: dict) -> str | None:
    metadata = payload.get("metadata")
    if isinstance(metadata, dict) and isinstance(metadata.get("user_id"), str):
        return metadata["user_id"]
    return None


def _upstream_auth_headers(route: Route, credential: str) -> dict[str, str]:
    """Credential headers: a named raw-key header, else Bearer authorization."""
    if route.auth_header:
        return {route.auth_header: credential}
    return {"authorization": f"Bearer {credential}"}


def _session_headers(route: Route, payload: dict) -> dict[str, str]:
    """A stable, header-safe session id for upstreams that route by session."""
    if not route.session_header:
        return {}
    raw = _affinity(payload) or "anonymous"
    cleaned = "".join(ch for ch in raw if 33 <= ord(ch) <= 126)[:64] or "anonymous"
    return {route.session_header: f"fabric-{cleaned}"}


@dataclass
class _RequestLifecycle:
    """One local permit and upstream response; completion/cleanup are idempotent."""
    state: RouterState
    cfg: Settings
    route: Route
    permit: RoutePermit
    model: str
    counting: bool = False
    started: float = field(default_factory=time.monotonic)
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    upstream_response: httpx.Response | None = None
    sent: bool = False
    settled: bool = False
    closed: bool = False
    first_content_ms: float | None = None
    headers_ms: float | None = None
    attempt_failed: bool = False
    response_identity: _ReceiptIdentity = field(default_factory=_ReceiptIdentity)
    upstream_identity: _ReceiptIdentity = field(default_factory=_ReceiptIdentity)
    reported_usage: dict[str, int] = field(default_factory=dict)
    usage_invalid_fields: set[str] = field(default_factory=set)
    input_token_estimate: int | None = None

    @property
    def deadline(self) -> float:
        return self.started + self.cfg.request_timeout_s

    def content_observed(self) -> None:
        if self.first_content_ms is None:
            self.first_content_ms = (time.monotonic() - self.started) * 1000

    @property
    def translated_message_id(self) -> str:
        # Fixed before the first event, including Responses IDs arriving late.
        return "msg_fabric_" + self.request_id

    def observe_usage(self, usage) -> None:
        if not isinstance(usage, dict):
            if usage is not None:
                self.usage_invalid_fields.update(_USAGE_FIELDS)
            return
        fields = {name: usage.get(name) for name in (
            _USAGE_FIELDS if self.route.wire == WIRE_ANTHROPIC else _USAGE_FIELDS[:2])}
        if self.route.wire == WIRE_OPENAI:
            fields = {"input_tokens": usage.get("prompt_tokens"),
                      "output_tokens": usage.get("completion_tokens")}
        if self.route.wire in {WIRE_OPENAI, WIRE_RESPONSES}:
            details = usage.get("prompt_tokens_details" if self.route.wire == WIRE_OPENAI
                                else "input_tokens_details")
            if isinstance(details, dict):
                fields["cache_read_input_tokens"] = details.get("cached_tokens")
            elif details is not None:
                self.usage_invalid_fields.add("cache_read_input_tokens")
        for name, value in fields.items():
            count = _reported_count(value)
            if count is not None:
                # These are cumulative reports, never deltas to be summed.
                self.reported_usage[name] = count
            elif value is not None:
                self.usage_invalid_fields.add(name)

    def observe_message(self, value, *, translated: bool = False) -> None:
        if not isinstance(value, dict):
            return
        self.upstream_identity.observe(value.get("id"))
        if not translated:
            self.response_identity.observe(value.get("id"))
        self.observe_usage(value.get("usage"))

    def emit_terminal_receipt(self, outcome: str, reason: str) -> None:
        # Exactly one attempt from settle(). No bodies, arbitrary metadata,
        # headers, credentials, account rows or exception text enter this sink.
        # In particular, a failed log handler cannot skip permit cleanup.
        try:
            public_reason = (reason if reason in _TERMINAL_REASONS
                             or re.fullmatch(r"http_[3-5][0-9]{2}", reason) else None)
            receipt = {
                "schema": "fabric_terminal_v1", "request_id": self.request_id,
                "settled_unix_ms": int(time.time() * 1000), "process_id": os.getpid(),
                "gateway_source_sha256": _receipt_source_sha256(),
                "operation": "count_tokens" if self.counting else "messages",
                "route_id": self.route.route_id, "model": self.model, "wire": self.route.wire,
                "outcome": outcome, "reason": public_reason,
                "upstream_send_started": self.sent,
                "response_id_sha256": self.response_identity.sha256,
                "response_id_state": self.response_identity.state,
                "upstream_response_id_sha256": self.upstream_identity.sha256,
                "upstream_response_id_state": self.upstream_identity.state,
                "usage": {name: self.reported_usage.get(name) for name in _USAGE_FIELDS},
                "usage_source": "upstream_reported" if self.reported_usage else "unavailable",
                "usage_state": ("unavailable" if not self.reported_usage else
                                "partial" if outcome != "served" or self.usage_invalid_fields else "reported"),
                "usage_invalid_fields": sorted(self.usage_invalid_fields),
                "input_token_estimate": self.input_token_estimate,
                "cost_usd": None, "cost_status": "unknown",
                "duration_ms": round((time.monotonic() - self.started) * 1000, 3),
            }
            _log.info("FABRIC_TERMINAL %s", json.dumps(
                receipt, separators=(",", ":"), sort_keys=True, allow_nan=False))
        except Exception:
            pass

    def mark_attempt_failed(self) -> None:
        if not self.attempt_failed:
            self.attempt_failed = True
            self.state.count(self.route.route_id, "attempt_failed")

    def settle(self, outcome: str, reason: str = "", *, circuit: bool = False,
               retry_after_s: float | None = None) -> None:
        if self.settled:
            return
        self.settled = True
        route_id = self.route.route_id
        if outcome != "served":
            self.mark_attempt_failed()
        self.state.count(route_id, outcome)
        setattr(self.state, outcome, getattr(self.state, outcome) + 1)
        if outcome == "served":
            if not self.counting:
                self.state.routes.record_success(route_id, generation=self.permit.generation)
            self.state.observe_latency(route_id, "completion_ms",
                                       (time.monotonic() - self.started) * 1000)
            for name, value in (("first_content_ms", self.first_content_ms),
                                ("headers_ms", self.headers_ms)):
                if value is not None:
                    self.state.observe_latency(route_id, name, value)
        elif circuit:
            self.state.routes.record_failure(
                route_id, reason, now=time.monotonic(), cooldown_s=self.cfg.route_cooldown_s,
                retry_after_s=retry_after_s, generation=self.permit.generation)
        self.emit_terminal_receipt(outcome, reason)

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            # Starlette may cancel the entire stream task scope on disconnect.
            # Cleanup also runs when its generator has never been advanced.
            with anyio.move_on_after(UPSTREAM_CLEANUP_TIMEOUT_S, shield=True) as cleanup_scope:
                if self.upstream_response is not None:
                    await self.upstream_response.aclose()
            if cleanup_scope.cancel_called:
                self.state.count(self.route.route_id, "cleanup_failed")
                _log.warning("route %s close exceeded deadline", self.route.route_id)
        except Exception as exc:
            self.state.count(self.route.route_id, "cleanup_failed")
            _log.warning("route %s close failed: %s", self.route.route_id, type(exc).__name__)
        finally:
            if not self.settled:
                self.settle("cancelled")
            self.state.routes.release(self.permit)
            self.state.in_flight -= 1


class _ManagedStreamingResponse(StreamingResponse):
    def __init__(self, content, lifecycle: _RequestLifecycle, **kwargs):
        super().__init__(content, **kwargs)
        self.lifecycle = lifecycle

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self.lifecycle.close()


class _ResponsesRouteRefused(RuntimeError):
    def __init__(self, reason: str, *, retry_after_s: float | None = None,
                 circuit: bool = True):
        super().__init__(reason)
        self.reason, self.retry_after_s, self.circuit = reason, retry_after_s, circuit


class _PreSendUnavailable(RuntimeError):
    """A local admission or connection-phase failure with no possible inference effect."""
    def __init__(self, reason: str, *, circuit: bool = False,
                 retry_after_s: float | None = None):
        super().__init__(reason)
        self.reason, self.circuit, self.retry_after_s = reason, circuit, retry_after_s


def _error(reason: str, status: int, *, retry_after_s: float | None = None) -> Response:
    headers = {}
    if retry_after_s is not None:
        headers["retry-after"] = str(max(1, math.ceil(retry_after_s)))
    message = reason
    if reason == "FABRIC_ROUTE_CREDENTIAL":
        message = "fabric route unavailable: FABRIC_ROUTE_CREDENTIAL"
    elif status == 502 and reason.startswith("FABRIC_TRANSLATE_"):
        message = "translation failed: " + reason
    error_type = "invalid_request_error" if status == 400 else "fabric_route_error"
    return JSONResponse({"error": {"message": message, "type": error_type,
                                   "code": reason}}, status_code=status, headers=headers)


def _sse(event: str, data: str) -> bytes:
    return f"event: {event}\ndata: {data}\n\n".encode()


def _stream_error(reason: str) -> bytes:
    return _sse("error", json.dumps({"type": "error", "error": {
        "type": "fabric_route_error", "code": reason, "message": reason}}))


def create_app(cfg: Settings | None = None, *,
               transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings: Settings = app.state.settings
        limits = httpx.Limits(max_connections=settings.max_in_flight,
                              max_keepalive_connections=min(16, settings.max_in_flight))
        app.state.upstream = httpx.AsyncClient(
            transport=transport if transport is not None else httpx.AsyncHTTPTransport(
                retries=0, trust_env=False, limits=limits), trust_env=False,
            timeout=httpx.Timeout(connect=10, write=30,
                                  read=settings.upstream_timeout_s, pool=30),
            follow_redirects=False,
            limits=limits)
        try:
            yield
        finally:
            await app.state.upstream.aclose()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = cfg or settings_from_env()
    app.state.router_state = RouterState()
    app.state.router_state.route_ids = frozenset(r.route_id for r in app.state.settings.routes)

    def loopback_peer(request: Request) -> bool:
        if request.client is None:
            return False
        try:
            return ipaddress.ip_address(request.client.host).is_loopback
        except ValueError:
            return False

    def authorized(request: Request) -> bool:
        scheme, _, candidate = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() == "bearer" and hmac.compare_digest(
                candidate, app.state.settings.proxy_token):
            return True
        api_key = request.headers.get("x-api-key", "")
        return bool(api_key) and hmac.compare_digest(api_key, app.state.settings.proxy_token)

    @app.get("/healthz")
    async def healthz(request: Request) -> Response:
        if not loopback_peer(request):
            return _error("FABRIC_LOOPBACK_ONLY", 403)
        return JSONResponse({"ok": True})

    @app.get("/statusz")
    async def statusz(request: Request) -> Response:
        if not loopback_peer(request) or not authorized(request):
            return _error("FABRIC_UNAUTHORIZED", 401)
        cfg: Settings = app.state.settings
        state: RouterState = app.state.router_state
        now = time.monotonic()
        return JSONResponse({
            "ok": True, "policy": "model-priority-weighted-inflight-v2",
            "admission_scope": "single_process_local_bulkhead",
            "provider_quota_authority": False,
            "selection": {
                "scope": "historical_local_selection_only",
                "evaluations_total": state.selection_evaluations,
                "outcomes": state.selection_outcomes,
                "not_run": state.selection_not_run,
                "last": dict(state.last_selection,
                             age_s=round(max(0, now-state.last_selection_at), 3))
                    if state.last_selection is not None else None,
            },
            "in_flight": state.in_flight, "max_in_flight": cfg.max_in_flight,
            "request_timeout_s": cfg.request_timeout_s,
            "request_body_timeout_s": cfg.request_body_timeout_s,
            "max_attempts": cfg.max_attempts,
            "retry_scope": "pre_send_admission_or_connection_only",
            "attempts_total": state.attempts,
            "failovers_total": state.failovers,
            "exhausted_total": state.exhausted,
            "upstream_send_calls_total": state.upstream_send_calls,
            "routes": [
                {"route_id": r.route_id, "wire": r.wire, "models": list(r.models),
                 "weight": r.weight, "priority": r.priority,
                 "model_priority": r.model_priority, "model_weight": r.model_weight,
                 "model_params": {slug: sorted(params) for slug, params in r.model_params.items()},
                 "drained": r.weight == 0,
                 "cooling": not state.routes.available(r.route_id, now),
                 "circuit": state.routes.circuit(r.route_id, now),
                 "cooldown_remaining_s": round(max(0, state.routes.cooldown_until.get(
                     r.route_id, 0) - now), 3),
                 "consecutive_failures": state.routes.consecutive_failures.get(r.route_id, 0),
                 "in_flight": state.routes.in_flight.get(r.route_id, 0),
                 "max_in_flight": r.max_in_flight or None,
                 "concurrency_group": r.concurrency_group or None,
                 "group_in_flight": state.routes.group_in_flight.get(r.concurrency_group, 0)
                     if r.concurrency_group else None,
                 "group_max_in_flight": r.group_max_in_flight or None,
                 "last_failure_reason": state.routes.last_failure.get(r.route_id, (None, None))[1],
                 "latency_ewma_ms": {k: round(v, 3) for k, v in state.latency.get(
                     r.route_id, {}).items()},
                 "latency_histogram": {
                     "population": "successful_completions",
                     "clock_origin": "local_admission_reservation",
                     "bucket_upper_ms": [*LATENCY_BUCKET_UPPER_MS, None],
                     "counts": state.latency_histograms.get(r.route_id, {}),
                 },
                 **{key: state.per_route.get(r.route_id, {}).get(key, 0)
                    for key in ("selected", "served", "refused", "failed", "cancelled", "cleanup_failed",
                                "admission_refused", "attempt_failed")}}
                for r in cfg.routes],
            "aliases": {alias: list(targets) for alias, targets in cfg.aliases},
            "labels": dict(cfg.model_labels),
            "oauth_refresh_authority": "incumbent_auth_owner",
            "selected_total": state.selected, "served_total": state.served,
            "refused_total": state.refused, "failed_total": state.failed,
            "cancelled_total": state.cancelled,
        })

    @app.get("/v1/models")
    async def models(request: Request) -> Response:
        if not loopback_peer(request) or not authorized(request):
            return _error("FABRIC_UNAUTHORIZED", 401)
        cfg: Settings = app.state.settings
        slugs = list(dict.fromkeys(m for route in cfg.routes for m in route.models))
        slugs.extend(alias for alias, _ in cfg.aliases if alias not in slugs)
        labels = dict(cfg.model_labels)
        return JSONResponse({"object": "list", "data": [
            {"id": slug, "object": "model", "type": "model",
             "display_name": labels.get(slug.strip().lower(), slug), "owned_by": "capacity-fabric"}
            for slug in slugs]})

    async def send(ctx: _RequestLifecycle, url: str, headers: dict, payload: dict):
        if time.monotonic() >= ctx.deadline:
            raise TimeoutError()
        upstream: httpx.AsyncClient = app.state.upstream
        outgoing = upstream.build_request("POST", url, headers=headers,
                                          content=json.dumps(payload).encode())
        ctx.sent = True
        ctx.state.upstream_send_calls += 1
        try:
            # The service uses HTTPX's transport without retries, redirects or
            # environment proxies. Only its connection/pool establishment
            # exceptions prove that this HTTP request was never transmitted.
            ctx.upstream_response = await upstream.send(outgoing, stream=True)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
            # Arbitrary injected transports can send and then raise any error.
            # Their exception names are never evidence for another inference.
            if transport is not None:
                raise
            ctx.sent = False
            local_pool = isinstance(exc, httpx.PoolTimeout)
            raise _PreSendUnavailable(
                "FABRIC_ROUTE_LOCAL_POOL_TIMEOUT" if local_pool else "FABRIC_ROUTE_CONNECT",
                circuit=not local_pool) from None
        ctx.headers_ms = (time.monotonic() - ctx.started) * 1000
        return ctx.upstream_response

    def upstream_headers(route: Route, credential: str, payload: dict) -> dict:
        return {**_upstream_auth_headers(route, credential), **_session_headers(route, payload),
                "content-type": "application/json", "accept-encoding": "identity",
                "anthropic-version": "2023-06-01"}

    async def raw_response(response, cfg):
        data = await read_bounded(response, cfg.max_response_bytes)
        return Response(data, status_code=response.status_code,
                        headers={k: v for k, v in response.headers.items()
                                 if k.lower() in {"content-type", "x-request-id", "retry-after"}},
                        media_type="application/json")

    def json_event(data: str) -> dict:
        try:
            value = json.loads(data)
        except ValueError:
            raise WireTranslationError("FABRIC_STREAM_INVALID_JSON") from None
        if not isinstance(value, dict):
            raise WireTranslationError("FABRIC_STREAM_INVALID_JSON")
        if "error" in value or value.get("type") in {"error", "response.failed"}:
            raise WireTranslationError("FABRIC_UPSTREAM_STREAM_ERROR")
        return value

    async def forward_anthropic(ctx, payload, credential):
        suffix = "v1/messages/count_tokens" if ctx.counting else "v1/messages"
        response = await send(ctx, f"{_route_base_url(ctx.route).rstrip('/')}/{suffix}",
                              upstream_headers(ctx.route, credential, payload), payload)
        if response.status_code >= 300:
            return await raw_response(response, ctx.cfg)
        if ctx.counting or payload.get("stream") is not True:
            reply = await raw_response(response, ctx.cfg)
            try:
                value = json.loads(reply.body)
            except ValueError:
                raise WireTranslationError("FABRIC_RESPONSE_INVALID_JSON") from None
            if not isinstance(value, dict):
                raise WireTranslationError("FABRIC_RESPONSE_INVALID")
            if "error" in value or value.get("type") == "error":
                raise WireTranslationError("FABRIC_UPSTREAM_RESPONSE_ERROR")
            if ctx.counting:
                valid = type(value.get("input_tokens")) is int and value["input_tokens"] >= 0
            else:
                valid = (isinstance(value.get("id"), str) and bool(value["id"])
                         and isinstance(value.get("content"), list)
                         and value.get("type", "message") == "message")
            if not valid:
                raise WireTranslationError("FABRIC_RESPONSE_INVALID")
            if ctx.counting:
                ctx.input_token_estimate = _reported_count(value.get("input_tokens"))
            else:
                ctx.observe_message(value)
            return reply
        if "text/event-stream" not in response.headers.get("content-type", ""):
            raise WireTranslationError("FABRIC_STREAM_CONTENT_TYPE")

        async def stream():
            decoder = SSEDecoder(ctx.cfg.max_sse_event_bytes)
            received = 0
            async for part in response.aiter_bytes():
                received += len(part)
                if received > ctx.cfg.max_response_bytes:
                    raise WireTranslationError("FABRIC_RESPONSE_TOO_LARGE")
                terminal = False
                pending_identity = _ReceiptIdentity(
                    ctx.response_identity.sha256, ctx.response_identity.state)
                for event, data in decoder.feed(part):
                    value = json_event(data)
                    kind = value.get("type") or event
                    if kind == "message_start":
                        message = value.get("message")
                        ctx.observe_message(message, translated=True)
                        if isinstance(message, dict):
                            pending_identity.observe(message.get("id"))
                    elif kind == "message_delta":
                        ctx.observe_usage(value.get("usage"))
                    if kind == "content_block_delta":
                        ctx.content_observed()
                    if kind == "message_stop":
                        terminal = True
                # A later error in the same chunk prevents this entire part
                # from being forwarded. Only commit a downstream ID now.
                ctx.response_identity = pending_identity
                yield part
                if terminal:
                    return
            decoder.finish()
            raise WireTranslationError("FABRIC_STREAM_INCOMPLETE")

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"cache-control": "no-store"})

    async def forward_openai(ctx, payload, credential):
        translated = anthropic_to_openai(payload)
        translated.update(ctx.route.effective_params(ctx.model))
        response = await send(ctx, f"{_route_base_url(ctx.route).rstrip('/')}/chat/completions",
                              upstream_headers(ctx.route, credential, payload), translated)
        if response.status_code >= 300:
            return await raw_response(response, ctx.cfg)
        if payload.get("stream") is not True:
            data = await read_bounded(response, ctx.cfg.max_response_bytes)
            try:
                value = json.loads(data)
                reply = openai_to_anthropic(value, model=ctx.model,
                                           message_id=ctx.translated_message_id)
            except WireTranslationError:
                raise
            except (ValueError, TypeError, AttributeError):
                raise WireTranslationError("FABRIC_TRANSLATE_INVALID") from None
            ctx.observe_message(value, translated=True)
            outgoing = JSONResponse(reply)
            ctx.response_identity.observe(reply["id"])
            return outgoing
        if "text/event-stream" not in response.headers.get("content-type", ""):
            raise WireTranslationError("FABRIC_STREAM_CONTENT_TYPE")
        translator = OpenAIStreamTranslator(model=ctx.model, message_id=ctx.translated_message_id)

        async def stream():
            first = True
            async for _, data in events(response, max_event_bytes=ctx.cfg.max_sse_event_bytes,
                                        max_response_bytes=ctx.cfg.max_response_bytes):
                if data == "[DONE]":
                    for event in translator.finish():
                        yield _sse(*event)
                    return
                chunk = json_event(data)
                ctx.observe_message(chunk, translated=True)
                if first:
                    start_event = _sse(*translator.message_start())
                    ctx.response_identity.observe(translator.message_id)
                    yield start_event
                    first = False
                for event in translator.feed(chunk):
                    if event[0] == "content_block_delta":
                        ctx.content_observed()
                    yield _sse(*event)
            # A missing [DONE] is not an implicit successful completion.
            raise WireTranslationError("FABRIC_STREAM_INCOMPLETE")

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"cache-control": "no-store"})

    async def oauth_candidates(cfg, state, route):
        accounts = await _run_in_executor(codex_oauth.read_accounts, cfg.auth_store, route.pool)
        wall_now = time.time()
        unheld = [a for a in accounts if not a.owner_held]
        if not unheld:
            raise _ResponsesRouteRefused("FABRIC_OAUTH_OWNER_HELD", circuit=False)
        eligible, needs_refresh = [], False
        for account in unheld:
            if account.exhausted or state.oauth_bench.get((route.route_id, account.id), 0) > wall_now:
                continue
            expiry = codex_oauth.access_token_expiry(account.access_token)
            if expiry is not None and expiry <= wall_now + 30:
                needs_refresh = True
                continue
            eligible.append(account)
        if eligible:
            return eligible
        if needs_refresh:
            # Rotation belongs to the existing auth owner. No token endpoint
            # POST, invented recovery deadline or upstream-health penalty.
            raise _ResponsesRouteRefused("FABRIC_OAUTH_OWNER_REFRESH_REQUIRED", circuit=False)
        if any(a.exhausted_unknown for a in unheld):
            raise _ResponsesRouteRefused("FABRIC_OAUTH_QUOTA_UNKNOWN", circuit=False)
        deadlines = [max(a.exhausted_until, state.oauth_bench.get(
            (route.route_id, a.id), 0)) for a in unheld]
        remaining = min((d-wall_now for d in deadlines if d > wall_now), default=None)
        raise _ResponsesRouteRefused("FABRIC_OAUTH_ACCOUNTS_EXHAUSTED",
                                     retry_after_s=remaining, circuit=False)

    async def forward_responses(ctx, payload):
        translated = anthropic_to_responses(payload)
        translated["stream"] = True
        state, cfg, route = ctx.state, ctx.cfg, ctx.route
        eligible = await oauth_candidates(cfg, state, route)
        cursor = state.oauth_cursor.get(route.route_id, 0)
        account = eligible[cursor % len(eligible)]
        state.oauth_cursor[route.route_id] = cursor + 1
        headers = {"authorization": f"Bearer {account.access_token}",
                   "content-type": "application/json", "accept-encoding": "identity",
                   "originator": route.originator or "hermes-agent",
                   "user-agent": "HermesAgent/fabric-router",
                   **codex_oauth.account_id_header(account.access_token)}
        response = await send(ctx, f"{_route_base_url(route).rstrip('/')}/responses",
                              headers, translated)
        if response.status_code == 429:
            delay = retry_after_seconds(response.headers.get("retry-after", ""), wall_now=time.time())
            delay = max(cfg.route_cooldown_s, delay or 0)
            reset_at = max(time.time() + delay, state.oauth_bench.get((route.route_id, account.id), 0))
            state.oauth_bench[(route.route_id, account.id)] = reset_at
            # Existing auth-store owner, exact account, constant non-sensitive reason.
            persisted_reset = await _run_in_executor(
                codex_oauth.bench_row, cfg.auth_store, route.pool,
                account.id, reset_at=reset_at, reason="http_429")
            key = (route.route_id, account.id)
            state.oauth_bench[key] = max(state.oauth_bench.get(key, 0), reset_at, persisted_reset)
            # No replay: a later independent request may select another eligible row.
            raise _ResponsesRouteRefused("FABRIC_OAUTH_ACCOUNT_LIMIT",
                                         retry_after_s=delay, circuit=False)
        if response.status_code >= 300:
            # Includes 401/403/5xx: never refresh-and-resend or rotate after send.
            return await raw_response(response, cfg)
        if "text/event-stream" not in response.headers.get("content-type", ""):
            raise WireTranslationError("FABRIC_STREAM_CONTENT_TYPE")
        wants_stream = payload.get("stream") is True
        translator = ResponsesStreamTranslator(model=ctx.model, retain_text=not wants_stream,
                                               message_id=ctx.translated_message_id)

        async def translated_stream():
            first = True
            async for _, data in events(response, max_event_bytes=cfg.max_sse_event_bytes,
                                        max_response_bytes=cfg.max_response_bytes):
                if data == "[DONE]":
                    break
                chunk = json_event(data)
                if first:
                    if wants_stream:
                        start_event = _sse(*translator.message_start())
                        ctx.response_identity.observe(translator.message_id)
                        yield start_event
                    first = False
                produced = translator.feed(chunk)
                ctx.observe_usage(chunk.get("usage"))
                # Event IDs and output-item IDs are not response identities.
                if chunk.get("type") in {"response.created", "response.in_progress",
                                         "response.completed", "response.incomplete"}:
                    ctx.observe_message(chunk.get("response"), translated=True)
                for event in produced:
                    if event[0] == "content_block_delta":
                        ctx.content_observed()
                    if wants_stream:
                        yield _sse(*event)
                if translator.completed:
                    break
            if not translator.completed:
                raise WireTranslationError("FABRIC_STREAM_INCOMPLETE")
            if wants_stream:
                for event in translator.finish():
                    yield _sse(*event)

        if not wants_stream:
            async for _ in translated_stream():
                pass
            reply = translator.to_message()
            outgoing = JSONResponse(reply)
            ctx.response_identity.observe(reply["id"])
            return outgoing
        return StreamingResponse(translated_stream(), media_type="text/event-stream",
                                 headers={"cache-control": "no-store"})

    def settle_http(ctx: _RequestLifecycle, response: Response):
        if 200 <= response.status_code < 300:
            ctx.settle("served")
        elif response.status_code == 429 or response.status_code >= 500:
            delay = retry_after_seconds(response.headers.get("retry-after", ""), wall_now=time.time())
            ctx.settle("failed", f"http_{response.status_code}", circuit=True, retry_after_s=delay)
        else:
            # A caller/auth/config rejection is neither health success nor a server outage.
            ctx.settle("refused", f"http_{response.status_code}")

    async def managed_stream(ctx, iterator):
        try:
            async with asyncio.timeout_at(ctx.deadline):
                async for part in iterator:
                    if time.monotonic() >= ctx.deadline:
                        raise TimeoutError()
                    yield part
            ctx.settle("served")
        except (httpx.RequestError, TimeoutError):
            ctx.settle("failed", "FABRIC_UPSTREAM_EFFECT_UNKNOWN", circuit=True)
            yield _stream_error("FABRIC_UPSTREAM_EFFECT_UNKNOWN")
        except WireTranslationError as exc:
            reason = _public_reason(exc, "FABRIC_STREAM_INVALID")
            ctx.settle("failed", reason, circuit=True)
            yield _stream_error(reason)
        finally:
            await ctx.close()

    @app.post("/v1/messages")
    @app.post("/v1/messages/count_tokens")
    async def messages(request: Request) -> Response:
        if not loopback_peer(request):
            return _error("FABRIC_LOOPBACK_ONLY", 403)
        if not authorized(request):
            return _error("FABRIC_UNAUTHORIZED", 401)
        cfg: Settings = app.state.settings
        state: RouterState = app.state.router_state
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > cfg.max_body_bytes:
            state.preselection_refused("FABRIC_REQUEST_TOO_LARGE")
            return _error("FABRIC_REQUEST_TOO_LARGE", 413)
        if state.in_flight >= cfg.max_in_flight:
            state.refused += 1
            state.preselection_refused("FABRIC_ROUTER_BUSY")
            return _error("FABRIC_ROUTER_BUSY", 503, retry_after_s=1)
        # Reserve before the first body read as well as credential admission.
        # Partial uploads cannot retain unbounded buffers outside the bulkhead.
        state.in_flight += 1
        admission_started = time.monotonic()
        admission_reserved = True
        try:
            async with asyncio.timeout_at(admission_started + cfg.request_timeout_s):
                body = bytearray()
                try:
                    async with asyncio.timeout(cfg.request_body_timeout_s):
                        async for chunk in request.stream():
                            if len(body) + len(chunk) > cfg.max_body_bytes:
                                state.refused += 1
                                state.preselection_refused("FABRIC_REQUEST_TOO_LARGE")
                                return _error("FABRIC_REQUEST_TOO_LARGE", 413)
                            body.extend(chunk)
                except TimeoutError:
                    state.refused += 1
                    state.preselection_refused("FABRIC_REQUEST_BODY_TIMEOUT")
                    return _error("FABRIC_REQUEST_BODY_TIMEOUT", 408)
                try:
                    payload = json.loads(bytes(body))
                    if not isinstance(payload, dict):
                        raise ValueError()
                    candidates = _model_candidates(payload, cfg.aliases)
                except (ValueError, RecursionError, WireTranslationError) as exc:
                    state.refused += 1
                    reason = _public_reason(exc, "FABRIC_INVALID_REQUEST")
                    state.preselection_refused(reason)
                    return _error(reason, 400)
                counting = request.url.path.endswith("/count_tokens")
                eligible_routes = [r for r in cfg.routes if not counting or r.wire == WIRE_ANTHROPIC]
                if counting and not any(r.serves(model) for r in eligible_routes for model, _ in candidates):
                    state.refused += 1
                    state.preselection_refused("FABRIC_COUNT_TOKENS_WIRE")
                    return _error("FABRIC_COUNT_TOKENS_WIRE", 501)
                known_refusal = None
                available_routes = []
                owner_excluded_routes = []
                for route in eligible_routes:
                    if not any(route.serves(model) for model, _ in candidates):
                        continue
                    if route.kind == "oauth_pool":
                        try:
                            await oauth_candidates(cfg, state, route)
                        except _ResponsesRouteRefused as exc:
                            known_refusal = exc
                            owner_excluded_routes.append(route)
                            state.count(route.route_id, "admission_refused")
                            continue
                        except (OSError, ValueError, codex_oauth.OAuthPoolError):
                            known_refusal = _ResponsesRouteRefused(
                                "FABRIC_OAUTH_OWNER_UNAVAILABLE", circuit=False)
                            owner_excluded_routes.append(route)
                            state.count(route.route_id, "admission_refused")
                            continue
                    available_routes.append(route)
                attempted_routes: set[str] = set()

                def choose_route():
                    # Re-evaluate current eligibility after each proven pre-send
                    # failure. One route is attempted at most once, even when an
                    # alias lists several models it serves. No await separates
                    # selection, route/group/probe reservation and ownership.
                    selected, resolved, reason = None, "", "FABRIC_MODEL_UNKNOWN"
                    remaining = [r for r in available_routes if r.route_id not in attempted_routes]
                    for candidate_index, (model, alias) in enumerate(candidates, 1):
                        decision = decide_route(remaining, model, state=state.routes,
                                                now=time.monotonic(), affinity_key=_affinity(payload))
                        selected, reason = decision.route, decision.reason
                        evidence = state.record_selection(
                            decision, candidate_index=candidate_index, candidate_total=len(candidates),
                            configured_alias=bool(alias),
                            owner_excluded=sum(r.serves(model) for r in owner_excluded_routes))
                        evidence["previous_attempts_excluded"] = sum(
                            r.serves(model) and r.route_id in attempted_routes for r in available_routes)
                        if selected is not None:
                            resolved = next(m for m in selected.models if m.lower() == model.strip().lower())
                            permit = state.routes.acquire(selected, now=time.monotonic(), model=resolved)
                            evidence["local_permit_acquired"] = permit is not None
                            return selected, resolved, reason, evidence, permit
                    return None, resolved, reason, evidence, None

                selected, resolved, reason, evidence, permit = choose_route()
                if selected is None:
                    state.refused += 1
                    if not available_routes and known_refusal is not None:
                        evidence["preflight_refusal"] = (known_refusal.reason
                            if known_refusal.reason in PREFLIGHT_REASONS else "UNCLASSIFIED")
                        return _error(known_refusal.reason, 503,
                                      retry_after_s=known_refusal.retry_after_s)
                    return _error(reason, 503)
                if permit is None:
                    state.refused += 1
                    evidence["preflight_refusal"] = "FABRIC_ROUTES_BUSY"
                    return _error("FABRIC_ROUTES_BUSY", 503, retry_after_s=1)
                evidence["local_permit_acquired"] = True
                ctx = _RequestLifecycle(state, cfg, selected, permit, resolved, counting,
                                        started=admission_started)
                admission_reserved = False
                state.selected += 1
                state.count(selected.route_id, "selected")
                state.attempts += 1
                attempted_routes.add(selected.route_id)
        except TimeoutError:
            state.refused += 1
            state.preselection_refused("FABRIC_ADMISSION_DEADLINE")
            return _error("FABRIC_ADMISSION_DEADLINE", 503)
        except ClientDisconnect:
            state.cancelled += 1
            state.preselection_refused("FABRIC_REQUEST_DISCONNECTED")
            return _error("FABRIC_REQUEST_DISCONNECTED", 400)
        except asyncio.CancelledError:
            state.cancelled += 1
            state.preselection_refused("FABRIC_REQUEST_CANCELLED")
            raise
        finally:
            if admission_reserved:
                state.in_flight -= 1
        transferred = False
        try:
            async with asyncio.timeout_at(ctx.deadline):
                while True:
                    pre_send_refusal = None
                    forwarded = dict(payload, model=selected.wire_model(resolved))
                    try:
                        if selected.wire == WIRE_RESPONSES:
                            response = await forward_responses(ctx, forwarded)
                        else:
                            credential = await _run_in_executor(_route_authorization, selected, cfg)
                            if selected.wire == WIRE_ANTHROPIC:
                                response = await forward_anthropic(ctx, forwarded, credential)
                            else:
                                response = await forward_openai(ctx, forwarded, credential)
                    except _PreSendUnavailable as exc:
                        pre_send_refusal = exc
                    except _ResponsesRouteRefused as exc:
                        if not ctx.sent:
                            pre_send_refusal = _PreSendUnavailable(
                                exc.reason, circuit=exc.circuit, retry_after_s=exc.retry_after_s)
                        else:
                            ctx.settle("refused", exc.reason, circuit=exc.circuit,
                                       retry_after_s=exc.retry_after_s)
                            response = _error(exc.reason, 503, retry_after_s=exc.retry_after_s)
                    except WireTranslationError as exc:
                        reason = _public_reason(exc, "FABRIC_TRANSLATE_INVALID")
                        ctx.settle("failed" if ctx.sent else "refused", reason, circuit=ctx.sent)
                        response = _error(reason, 502 if ctx.sent else 400)
                    except (OSError, ValueError, codex_oauth.OAuthPoolError) as exc:
                        _log.warning("route %s unavailable: %s", selected.route_id, type(exc).__name__)
                        if not ctx.sent:
                            pre_send_refusal = _PreSendUnavailable("FABRIC_ROUTE_CREDENTIAL")
                        else:
                            ctx.settle("failed", "FABRIC_UPSTREAM_EFFECT_UNKNOWN", circuit=True)
                            response = _error("FABRIC_UPSTREAM_EFFECT_UNKNOWN", 502)
                    if pre_send_refusal is None:
                        break
                    # No HTTP response, write/read ambiguity or committed stream
                    # can enter this ladder. In particular 401/429/5xx never replay.
                    if ctx.sent or ctx.upstream_response is not None:
                        ctx.settle("failed", "FABRIC_UPSTREAM_EFFECT_UNKNOWN", circuit=True)
                        response = _error("FABRIC_UPSTREAM_EFFECT_UNKNOWN", 502)
                        break
                    ctx.mark_attempt_failed()
                    if pre_send_refusal.circuit:
                        state.routes.record_failure(
                            selected.route_id, pre_send_refusal.reason, now=time.monotonic(),
                            cooldown_s=cfg.route_cooldown_s,
                            retry_after_s=pre_send_refusal.retry_after_s,
                            generation=ctx.permit.generation)
                    # Release only this route/group/probe. The global reservation,
                    # request id and original absolute deadline stay with ctx.
                    state.routes.release(ctx.permit)
                    next_route = None
                    if len(attempted_routes) < cfg.max_attempts:
                        next_route, next_model, reason, evidence, next_permit = choose_route()
                    if next_route is None or next_permit is None:
                        state.exhausted += 1
                        ctx.settle("refused", pre_send_refusal.reason)
                        response = _error(pre_send_refusal.reason, 503,
                                          retry_after_s=pre_send_refusal.retry_after_s)
                        break
                    selected, resolved = next_route, next_model
                    ctx.route, ctx.model, ctx.permit = selected, resolved, next_permit
                    ctx.attempt_failed = False
                    attempted_routes.add(selected.route_id)
                    state.selected += 1
                    state.count(selected.route_id, "selected")
                    state.attempts += 1
                    state.failovers += 1
            if isinstance(response, StreamingResponse):
                response = _ManagedStreamingResponse(
                    managed_stream(ctx, response.body_iterator), ctx,
                    status_code=response.status_code, headers=dict(response.headers))
                transferred = True
            else:
                settle_http(ctx, response)
            response.headers.update({"x-fabric-route": selected.route_id,
                                     "x-fabric-model": resolved,
                                     "x-fabric-request-id": ctx.request_id,
                                     "x-fabric-policy": "model-priority-weighted-inflight-v2"})
            return response
        except (httpx.RequestError, TimeoutError) as exc:
            reason = ("FABRIC_UPSTREAM_EFFECT_UNKNOWN" if ctx.sent else
                      "FABRIC_ADMISSION_DEADLINE" if isinstance(exc, TimeoutError) else
                      "FABRIC_ROUTE_UNAVAILABLE")
            ctx.settle("failed" if ctx.sent else "refused", reason, circuit=ctx.sent)
            return _error(reason, 502 if ctx.sent else 503)
        finally:
            if not transferred:
                await ctx.close()

    return app
