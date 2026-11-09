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

import hmac
import ipaddress
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from http import HTTPStatus
from pathlib import Path

import httpx
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from ops.native_fabric.unified_router.routes import (
    DEFAULT_AUTH_STORE,
    Route,
    RouteState,
    WIRE_ANTHROPIC,
    WIRE_OPENAI,
    config_file_route_key,
    credential_pool_key,
    env_file_value,
    select_route,
)
from ops.native_fabric.unified_router.wire import (
    OpenAIStreamTranslator,
    WireTranslationError,
    anthropic_to_openai,
    openai_to_anthropic,
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

    def __post_init__(self) -> None:
        if len(self.proxy_token) < 24:
            raise ValueError("FABRIC_ROUTER_TOKEN must contain at least 24 characters")
        if not self.routes:
            raise ValueError("the unified router needs at least one route")
        ids = [r.route_id for r in self.routes]
        if len(set(ids)) != len(ids):
            raise ValueError("route ids must be unique")
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
            upstream_model=tuple((slug, wire) for slug, wire
                                 in entry.get("upstream_model", {}).items()),
            auth_header=entry.get("auth_header", ""),
            session_header=entry.get("session_header", ""),
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
    )


@dataclass
class RouterState:
    routes: RouteState = field(default_factory=RouteState)
    started_at: float = field(default_factory=time.time)
    served: int = 0
    refused: int = 0
    per_route: dict[str, dict[str, int]] = field(default_factory=dict)

    def count(self, route_id: str, outcome: str) -> None:
        bucket = self.per_route.setdefault(route_id, {"served": 0, "refused": 0})
        bucket[outcome] = bucket.get(outcome, 0) + 1


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


def create_app(cfg: Settings | None = None, *,
               transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.upstream = httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(connect=10, write=30,
                                  read=app.state.settings.upstream_timeout_s, pool=30),
            follow_redirects=False,
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=16))
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
        return (scheme.lower() == "bearer"
                and hmac.compare_digest(candidate, app.state.settings.proxy_token))

    @app.get("/healthz")
    async def healthz(request: Request) -> Response:
        if not loopback_peer(request):
            return JSONResponse({"error": {"message": "loopback access only"}},
                                status_code=HTTPStatus.FORBIDDEN)
        return JSONResponse({"ok": True})

    @app.get("/statusz")
    async def statusz(request: Request) -> Response:
        if not loopback_peer(request) or not authorized(request):
            return JSONResponse({"error": {"message": "unauthorized",
                                           "type": "authentication_error"}},
                                status_code=401)
        cfg: Settings = app.state.settings
        state: RouterState = app.state.router_state
        now = time.time()
        return JSONResponse({
            "ok": True,
            "routes": [
                {"route_id": r.route_id, "wire": r.wire, "models": list(r.models),
                 "weight": r.weight, "priority": r.priority,
                 "cooling": not state.routes.available(r.route_id, now),
                 "consecutive_failures": state.routes.consecutive_failures.get(r.route_id, 0),
                 "served": state.per_route.get(r.route_id, {}).get("served", 0),
                 "refused": state.per_route.get(r.route_id, {}).get("refused", 0)}
                for r in cfg.routes],
            "aliases": {alias: list(targets) for alias, targets in cfg.aliases},
            "served_total": state.served, "refused_total": state.refused,
        })

    @app.get("/v1/models")
    async def models(request: Request) -> Response:
        if not loopback_peer(request) or not authorized(request):
            return JSONResponse({"error": {"message": "unauthorized",
                                           "type": "authentication_error"}},
                                status_code=401)
        cfg: Settings = app.state.settings
        slugs: list[str] = []
        for route in cfg.routes:
            for model in route.models:
                if model not in slugs:
                    slugs.append(model)
        for alias, _ in cfg.aliases:
            if alias not in slugs:
                slugs.append(alias)
        return JSONResponse({"object": "list", "data": [
            {"id": slug, "object": "model", "type": "model",
             "display_name": slug, "owned_by": "capacity-fabric"}
            for slug in slugs]})

    @app.post("/v1/messages")
    @app.post("/v1/messages/count_tokens")
    async def messages(request: Request) -> Response:
        if not loopback_peer(request):
            return JSONResponse({"error": {"message": "loopback access only"}},
                                status_code=HTTPStatus.FORBIDDEN)
        if not authorized(request):
            return JSONResponse({"error": {"message": "unauthorized",
                                           "type": "authentication_error"}},
                                status_code=401)
        cfg: Settings = app.state.settings
        state: RouterState = app.state.router_state
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > cfg.max_body_bytes:
            return JSONResponse({"error": {"message": "request body too large"}},
                                status_code=413)
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > cfg.max_body_bytes:
                return JSONResponse({"error": {"message": "request body too large"}},
                                    status_code=413)
            body.extend(chunk)
        try:
            payload = json.loads(bytes(body))
            if not isinstance(payload, dict):
                raise ValueError("not an object")
        except ValueError:
            return JSONResponse({"error": {"message": "invalid JSON body",
                                           "type": "invalid_request_error"}},
                                status_code=400)
        try:
            candidates = _model_candidates(payload, cfg.aliases)
        except WireTranslationError as exc:
            return JSONResponse({"error": {
                "message": _public_reason(exc, "FABRIC_TRANSLATE_INVALID"),
                "type": "invalid_request_error"}},
                status_code=400)
        alias = ""
        resolved = ""
        route = None
        reason = "FABRIC_MODEL_UNKNOWN"
        for candidate_model, candidate_alias in candidates:
            resolved, alias = candidate_model, candidate_alias
            route, reason = select_route(list(cfg.routes), resolved,
                                         state=state.routes, now=time.monotonic(),
                                         affinity_key=_affinity(payload))
            if route is not None:
                break
        if route is None:
            state.refused += 1
            return JSONResponse({"error": {"message": f"fabric routing refused: {reason}",
                                           "type": "fabric_route_error", "code": reason}},
                                status_code=HTTPStatus.SERVICE_UNAVAILABLE)
        counting = request.url.path.endswith("/count_tokens")
        if counting and route.wire != WIRE_ANTHROPIC:
            return JSONResponse({"error": {
                "message": "count_tokens is not available on OpenAI-wire routes",
                "type": "fabric_route_error", "route": route.route_id}},
                status_code=HTTPStatus.NOT_IMPLEMENTED)
        try:
            authorization = _route_authorization(route, cfg)
        except (OSError, ValueError) as exc:
            state.routes.record_failure(route.route_id, "credential_unavailable",
                                        now=time.monotonic(),
                                        cooldown_s=cfg.route_cooldown_s)
            state.refused += 1
            state.count(route.route_id, "refused")
            _log.warning("route %s credential unavailable: %s",
                         route.route_id, type(exc).__name__)
            return JSONResponse({"error": {
                "message": "fabric route unavailable: credential_unavailable",
                "type": "fabric_route_error",
                "code": "credential_unavailable"}},
                status_code=HTTPStatus.SERVICE_UNAVAILABLE)

        forwarded = dict(payload, model=route.wire_model(resolved))
        wants_stream = payload.get("stream") is True
        try:
            if counting:
                return await _forward_anthropic_count(app, route, authorization,
                                                      forwarded)
            if route.wire == WIRE_ANTHROPIC:
                return await _forward_anthropic(app, route, authorization,
                                                forwarded, wants_stream)
            return await _forward_openai(app, route, authorization,
                                         forwarded, wants_stream)
        except httpx.RequestError:
            state.routes.record_failure(route.route_id, "upstream_transport",
                                        now=time.monotonic(),
                                        cooldown_s=cfg.route_cooldown_s)
            return JSONResponse({"error": {
                "message": "upstream transport failure; result may be ambiguous",
                "type": "fabric_route_error", "route": route.route_id}},
                status_code=502)

    async def _forward_anthropic_count(app, route, authorization, payload) -> Response:
        upstream: httpx.AsyncClient = app.state.upstream
        upstream_request = upstream.build_request(
            "POST", f"{_route_base_url(route).rstrip('/')}/v1/messages/count_tokens",
            headers={**_upstream_auth_headers(route, authorization),
                     **_session_headers(route, payload),
                     "content-type": "application/json",
                     "accept-encoding": "identity"},
            content=json.dumps(payload).encode())
        response = await upstream.send(upstream_request)
        data = response.content
        return Response(content=data, status_code=response.status_code,
                        media_type="application/json")

    async def _forward_anthropic(app, route, authorization, payload,
                                 wants_stream) -> Response:
        cfg: Settings = app.state.settings
        state: RouterState = app.state.router_state
        upstream: httpx.AsyncClient = app.state.upstream
        upstream_request = upstream.build_request(
            "POST", f"{_route_base_url(route).rstrip('/')}/v1/messages",
            headers={**_upstream_auth_headers(route, authorization),
                     **_session_headers(route, payload),
                     "content-type": "application/json",
                     "accept-encoding": "identity"},
            content=json.dumps(payload).encode())
        response = await upstream.send(upstream_request, stream=True)
        if response.status_code >= 500 or response.status_code == 429:
            state.routes.record_failure(route.route_id, f"http_{response.status_code}",
                                        now=time.monotonic())
        else:
            state.routes.record_success(route.route_id)
        state.served += 1
        state.count(route.route_id, "served")
        headers = {k: v for k, v in response.headers.items()
                   if k.lower() in {"content-type", "x-request-id", "retry-after"}}
        if response.status_code >= 400:
            try:
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(data) + len(chunk) > cfg.max_body_bytes:
                        break
                    data.extend(chunk)
            finally:
                await response.aclose()
            return Response(content=bytes(data), status_code=response.status_code,
                            headers=headers, media_type="application/json")

        async def stream():
            async for part in response.aiter_raw():
                yield part
            await response.aclose()

        return StreamingResponse(stream(), status_code=response.status_code,
                                 headers=headers)

    async def _forward_openai(app, route, authorization, payload,
                              wants_stream) -> Response:
        state: RouterState = app.state.router_state
        cfg: Settings = app.state.settings
        upstream: httpx.AsyncClient = app.state.upstream
        try:
            openai_request = anthropic_to_openai(payload)
        except WireTranslationError as exc:
            return JSONResponse({"error": {
                "message": _public_reason(exc, "FABRIC_TRANSLATE_INVALID"),
                "type": "invalid_request_error"}},
                status_code=400)
        upstream_request = upstream.build_request(
            "POST", f"{_route_base_url(route).rstrip('/')}/chat/completions",
            headers={**_upstream_auth_headers(route, authorization),
                     **_session_headers(route, payload),
                     "content-type": "application/json",
                     "accept-encoding": "identity"},
            content=json.dumps(openai_request).encode())
        response = await upstream.send(upstream_request, stream=True)
        if response.status_code >= 500 or response.status_code == 429:
            state.routes.record_failure(route.route_id, f"http_{response.status_code}",
                                        now=time.monotonic())
        else:
            state.routes.record_success(route.route_id)
        if response.status_code >= 400:
            data = await response.aread()
            await response.aclose()
            return Response(content=data, status_code=response.status_code,
                            media_type="application/json")
        if not wants_stream:
            data = await response.aread()
            await response.aclose()
            try:
                translated = openai_to_anthropic(json.loads(data), model=payload["model"])
            except (ValueError, WireTranslationError) as exc:
                return JSONResponse({"error": {
                    "message": "translation failed: "
                               + _public_reason(exc, "FABRIC_TRANSLATE_INVALID"),
                    "type": "fabric_route_error"}},
                    status_code=502)
            return JSONResponse(translated)
        translator = OpenAIStreamTranslator(model=payload["model"])

        async def stream():
            first = True
            buffer = b""
            try:
                async for part in response.aiter_bytes():
                    buffer += part
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        text = line.decode("utf-8", "replace").strip()
                        if not text.startswith("data:"):
                            continue
                        data = text[5:].strip()
                        if data == "[DONE]":
                            for event in translator.finish():
                                yield _sse(*event)
                            return
                        try:
                            chunk = json.loads(data)
                        except ValueError:
                            continue
                        if first:
                            yield _sse(*translator.message_start())
                            first = False
                        for event in translator.feed(chunk):
                            yield _sse(*event)
                for event in translator.finish():
                    yield _sse(*event)
            finally:
                await response.aclose()

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"cache-control": "no-store"})

    def _sse(event: str, data: str) -> bytes:
        return f"event: {event}\ndata: {data}\n\n".encode()

    return app
