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
import functools
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
    select_route,
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

# The only exception text a client may ever see is a router-authored refusal
# reason of constant FABRIC_* shape (py/stack-trace-exposure): free-form
# detail from OSError/ValueError paths stays in the server-side log.
_FABRIC_REASON_RE = re.compile(r"^FABRIC_[A-Z0-9_]+$")


def _public_reason(exc: Exception, fallback: str) -> str:
    """Bound a caught exception to a publishable constant reason code."""
    text = str(exc)
    if _FABRIC_REASON_RE.match(text):
        return text
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
    max_response_bytes: int = 16 * 1024 * 1024
    max_sse_event_bytes: int = 1024 * 1024

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
        for value in (self.upstream_timeout_s, self.route_cooldown_s, self.request_timeout_s):
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
            weight=float(entry.get("weight", 1.0)),
            priority=int(entry.get("priority", 100)),
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
        max_response_bytes=int(os.environ.get("FABRIC_MAX_RESPONSE_BYTES", str(16 * 1024 * 1024))),
        max_sse_event_bytes=int(os.environ.get("FABRIC_MAX_SSE_EVENT_BYTES", str(1024 * 1024))),
    )


@dataclass
class RouterState:
    routes: RouteState = field(default_factory=RouteState)
    started_at: float = field(default_factory=time.time)
    served: int = 0
    refused: int = 0
    selected: int = 0
    failed: int = 0
    cancelled: int = 0
    in_flight: int = 0
    per_route: dict[str, dict[str, int]] = field(default_factory=dict)
    oauth_cursor: dict[str, int] = field(default_factory=dict)
    oauth_bench: dict[tuple[str, str], float] = field(default_factory=dict)
    latency: dict[str, dict[str, float]] = field(default_factory=dict)

    def count(self, route_id: str, outcome: str) -> None:
        bucket = self.per_route.setdefault(route_id, {"served": 0, "refused": 0})
        bucket[outcome] = bucket.get(outcome, 0) + 1

    def observe_latency(self, route_id: str, metric: str, value: float) -> None:
        bucket = self.latency.setdefault(route_id, {})
        old = bucket.get(metric)
        bucket[metric] = value if old is None else .2 * value + .8 * old


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

    @property
    def deadline(self) -> float:
        return self.started + self.cfg.request_timeout_s

    def content_observed(self) -> None:
        if self.first_content_ms is None:
            self.first_content_ms = (time.monotonic() - self.started) * 1000

    def settle(self, outcome: str, reason: str = "", *, circuit: bool = False,
               retry_after_s: float | None = None) -> None:
        if self.settled:
            return
        self.settled = True
        route_id = self.route.route_id
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

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            # Starlette may cancel the entire stream task scope on disconnect.
            # Cleanup also runs when its generator has never been advanced.
            with anyio.move_on_after(5, shield=True) as cleanup_scope:
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


def _error(reason: str, status: int, *, retry_after_s: float | None = None) -> Response:
    headers = {}
    if retry_after_s is not None:
        headers["retry-after"] = str(max(1, math.ceil(retry_after_s)))
    message = reason
    if reason == "credential_unavailable":
        message = "fabric route unavailable: credential_unavailable"
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
        app.state.upstream = httpx.AsyncClient(
            transport=transport, trust_env=False,
            timeout=httpx.Timeout(connect=10, write=30,
                                  read=settings.upstream_timeout_s, pool=30),
            follow_redirects=False,
            limits=httpx.Limits(max_connections=settings.max_in_flight,
                               max_keepalive_connections=min(16, settings.max_in_flight)))
        try:
            yield
        finally:
            await app.state.upstream.aclose()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = cfg or settings_from_env()
    app.state.router_state = RouterState()

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
            "ok": True, "policy": "priority-weighted-inflight-v1",
            "admission_scope": "single_process_local_bulkhead",
            "provider_quota_authority": False,
            "in_flight": state.in_flight, "max_in_flight": cfg.max_in_flight,
            "request_timeout_s": cfg.request_timeout_s,
            "routes": [
                {"route_id": r.route_id, "wire": r.wire, "models": list(r.models),
                 "weight": r.weight, "priority": r.priority,
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
                 **{key: state.per_route.get(r.route_id, {}).get(key, 0)
                    for key in ("selected", "served", "refused", "failed", "cancelled", "cleanup_failed", "admission_refused")}}
                for r in cfg.routes],
            "aliases": {alias: list(targets) for alias, targets in cfg.aliases},
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
        return JSONResponse({"object": "list", "data": [
            {"id": slug, "object": "model", "type": "model",
             "display_name": slug, "owned_by": "capacity-fabric"} for slug in slugs]})

    async def send(ctx: _RequestLifecycle, url: str, headers: dict, payload: dict):
        if time.monotonic() >= ctx.deadline:
            raise TimeoutError()
        upstream: httpx.AsyncClient = app.state.upstream
        outgoing = upstream.build_request("POST", url, headers=headers,
                                          content=json.dumps(payload).encode())
        ctx.sent = True
        # Exactly one inference send. HTTPX transport/SDK retries are not enabled.
        ctx.upstream_response = await upstream.send(outgoing, stream=True)
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
                for event, data in decoder.feed(part):
                    value = json_event(data)
                    kind = value.get("type") or event
                    if kind == "content_block_delta":
                        ctx.content_observed()
                    if kind == "message_stop":
                        terminal = True
                yield part
                if terminal:
                    return
            decoder.finish()
            raise WireTranslationError("FABRIC_STREAM_INCOMPLETE")

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"cache-control": "no-store"})

    async def forward_openai(ctx, payload, credential):
        translated = anthropic_to_openai(payload)
        response = await send(ctx, f"{_route_base_url(ctx.route).rstrip('/')}/chat/completions",
                              upstream_headers(ctx.route, credential, payload), translated)
        if response.status_code >= 300:
            return await raw_response(response, ctx.cfg)
        if payload.get("stream") is not True:
            data = await read_bounded(response, ctx.cfg.max_response_bytes)
            try:
                reply = openai_to_anthropic(json.loads(data), model=ctx.model)
            except WireTranslationError:
                raise
            except (ValueError, TypeError, AttributeError):
                raise WireTranslationError("FABRIC_TRANSLATE_INVALID") from None
            return JSONResponse(reply)
        if "text/event-stream" not in response.headers.get("content-type", ""):
            raise WireTranslationError("FABRIC_STREAM_CONTENT_TYPE")
        translator = OpenAIStreamTranslator(model=ctx.model)

        async def stream():
            first = True
            async for _, data in events(response, max_event_bytes=ctx.cfg.max_sse_event_bytes,
                                        max_response_bytes=ctx.cfg.max_response_bytes):
                if data == "[DONE]":
                    for event in translator.finish():
                        yield _sse(*event)
                    return
                chunk = json_event(data)
                if first:
                    yield _sse(*translator.message_start())
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
        translator = ResponsesStreamTranslator(model=ctx.model, retain_text=not wants_stream)

        async def translated_stream():
            first = True
            async for _, data in events(response, max_event_bytes=cfg.max_sse_event_bytes,
                                        max_response_bytes=cfg.max_response_bytes):
                if data == "[DONE]":
                    break
                chunk = json_event(data)
                if first:
                    if wants_stream:
                        yield _sse(*translator.message_start())
                    first = False
                produced = translator.feed(chunk)
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
            return JSONResponse(translator.to_message())
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
            ctx.settle("refused")

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
            return _error("FABRIC_REQUEST_TOO_LARGE", 413)
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > cfg.max_body_bytes:
                return _error("FABRIC_REQUEST_TOO_LARGE", 413)
            body.extend(chunk)
        try:
            payload = json.loads(bytes(body))
            if not isinstance(payload, dict):
                raise ValueError()
            candidates = _model_candidates(payload, cfg.aliases)
        except (ValueError, WireTranslationError) as exc:
            return _error(_public_reason(exc, "FABRIC_INVALID_REQUEST"), 400)
        counting = request.url.path.endswith("/count_tokens")
        eligible_routes = [r for r in cfg.routes if not counting or r.wire == WIRE_ANTHROPIC]
        if counting and not any(r.serves(model) for r in eligible_routes for model, _ in candidates):
            return _error("FABRIC_COUNT_TOKENS_UNSUPPORTED", 501)
        if state.in_flight >= cfg.max_in_flight:
            state.refused += 1
            return _error("FABRIC_ROUTER_BUSY", 503, retry_after_s=1)
        # Reserve the process bulkhead before any asynchronous credential read.
        # A burst cannot create unbounded admission/executor work ahead of it.
        state.in_flight += 1
        admission_started = time.monotonic()
        admission_reserved = True
        try:
            async with asyncio.timeout_at(admission_started + cfg.request_timeout_s):
                known_refusal = None
                available_routes = []
                for route in eligible_routes:
                    if not any(route.serves(model) for model, _ in candidates):
                        continue
                    if route.kind == "oauth_pool":
                        try:
                            await oauth_candidates(cfg, state, route)
                        except _ResponsesRouteRefused as exc:
                            known_refusal = exc
                            state.count(route.route_id, "admission_refused")
                            continue
                        except (OSError, ValueError, codex_oauth.OAuthPoolError):
                            known_refusal = _ResponsesRouteRefused(
                                "FABRIC_OAUTH_OWNER_UNAVAILABLE", circuit=False)
                            state.count(route.route_id, "admission_refused")
                            continue
                    available_routes.append(route)
                selected, resolved, reason = None, "", "FABRIC_MODEL_UNKNOWN"
                # No await between selection, route/group checks and acquisition.
                for model, _ in candidates:
                    selected, reason = select_route(available_routes, model, state=state.routes,
                                                    now=time.monotonic(), affinity_key=_affinity(payload))
                    if selected is not None:
                        resolved = next(m for m in selected.models if m.lower() == model.strip().lower())
                        break
                if selected is None:
                    state.refused += 1
                    if not available_routes and known_refusal is not None:
                        return _error(known_refusal.reason, 503,
                                      retry_after_s=known_refusal.retry_after_s)
                    return _error(reason, 503)
                permit = state.routes.acquire(selected, now=time.monotonic())
                if permit is None:
                    state.refused += 1
                    return _error("FABRIC_ROUTES_BUSY", 503, retry_after_s=1)
                ctx = _RequestLifecycle(state, cfg, selected, permit, resolved, counting,
                                        started=admission_started)
                admission_reserved = False
                state.selected += 1
                state.count(selected.route_id, "selected")
        except TimeoutError:
            state.refused += 1
            return _error("FABRIC_ADMISSION_DEADLINE", 503)
        except asyncio.CancelledError:
            state.cancelled += 1
            raise
        finally:
            if admission_reserved:
                state.in_flight -= 1
        transferred = False
        try:
            async with asyncio.timeout_at(ctx.deadline):
                forwarded = dict(payload, model=selected.wire_model(resolved))
                try:
                    if selected.wire == WIRE_RESPONSES:
                        response = await forward_responses(ctx, forwarded)
                    else:
                        credential = _route_authorization(selected, cfg)
                        if selected.wire == WIRE_ANTHROPIC:
                            response = await forward_anthropic(ctx, forwarded, credential)
                        else:
                            response = await forward_openai(ctx, forwarded, credential)
                except _ResponsesRouteRefused as exc:
                    ctx.settle("refused", exc.reason, circuit=exc.circuit,
                               retry_after_s=exc.retry_after_s)
                    response = _error(exc.reason, 503, retry_after_s=exc.retry_after_s)
                except WireTranslationError as exc:
                    reason = _public_reason(exc, "FABRIC_TRANSLATE_INVALID")
                    ctx.settle("failed" if ctx.sent else "refused", reason, circuit=ctx.sent)
                    response = _error(reason, 502 if ctx.sent else 400)
                except (OSError, ValueError, codex_oauth.OAuthPoolError) as exc:
                    _log.warning("route %s unavailable: %s", selected.route_id, type(exc).__name__)
                    reason = "FABRIC_UPSTREAM_EFFECT_UNKNOWN" if ctx.sent else "credential_unavailable"
                    ctx.settle("failed" if ctx.sent else "refused", reason, circuit=True)
                    response = _error(reason, 502 if ctx.sent else 503)
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
                                     "x-fabric-policy": "priority-weighted-inflight-v1"})
            return response
        except (httpx.RequestError, TimeoutError):
            ctx.settle("failed", "FABRIC_UPSTREAM_EFFECT_UNKNOWN", circuit=True)
            return _error("FABRIC_UPSTREAM_EFFECT_UNKNOWN", 502)
        finally:
            if not transferred:
                await ctx.close()

    return app
