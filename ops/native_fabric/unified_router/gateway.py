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
import uuid
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
    WIRE_RESPONSES,
    RateWindow,
    config_file_route_key,
    credential_pool_key,
    env_file_value,
    ordered_routes,
)
from ops.native_fabric.unified_router import codex_oauth
from ops.native_fabric.unified_router.provider_errors import classify as classify_provider_error
from ops.native_fabric.unified_router.model_policy import (ModelPolicyState, VERSION,
    AdmissionCapacityChanged, session_key, prefix_signature)
from ops.native_fabric.unified_router.config_refresh import ConfigRefresh, read_document
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

# Statuses that mean "this pool cannot serve the request" rather than "the
# request itself is wrong". They are safe to retry on the next route while no
# response byte has reached the client: upstream inference has no external
# side effect, and a caller-visible replay never happens after commit.
# Capacity/auth/server failures also bench the route for later requests;
# endpoint-shape failures (404 on an unsupported method, 408/409/425) ladder
# to the next route WITHOUT a cooldown, so one provider's missing endpoint
# cannot skew that provider's live distribution for everyone else.
COOLDOWN_STATUS = frozenset({401, 402, 403, 429, 500, 502, 503, 504, 529})
RETRYABLE_STATUS = COOLDOWN_STATUS | frozenset({404, 408, 409, 425})

DEFAULT_MAX_ATTEMPTS = 8



def _uncached_input(usage: dict) -> int:
    """Input tokens that actually consume a provider rate budget: total input
    minus cache reads (Anthropic: cache_read_input_tokens; OpenAI-wire:
    prompt_tokens_details.cached_tokens)."""
    if not isinstance(usage, dict):
        return 0
    total = usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0) or 0
    cached = usage.get("cache_read_input_tokens", 0) or 0
    details = usage.get("prompt_tokens_details") or {}
    if isinstance(details, dict):
        cached = max(cached, details.get("cached_tokens", 0) or 0)
    return max(0, int(total) - int(cached))


_QUOTA_WALL_RE = re.compile(
    r"reset(?:s)?\s+at\s+(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})")


def _quota_wall_s(detail, route=None, request_url=None) -> float | None:
    """Bench duration from a provider quota-exhaustion body.

    z.ai/zhipu quota bodies state a wall-clock reset ("Your limit will reset
    at 2026-11-14 14:25:24") with no timezone marker and no Retry-After; the
    provider clock is Beijing (+08). A flat 65s cooldown re-probed an
    exhausted key forever; park it until the stated reset instead (capped at
    6h so a mis-parsed timestamp cannot wedge a route for days).
    """
    if not detail:
        return None
    if route is not None or request_url is not None:
        from urllib.parse import urlsplit
        host = (urlsplit(request_url or route.base_url).hostname or "").lower()
        if not (host == "open.bigmodel.cn" or host.endswith(".bigmodel.cn")
                or host == "api.z.ai" or host.endswith(".z.ai")):
            return None
    text = detail.decode("utf-8", "replace") if isinstance(detail, bytes) else str(detail)
    m = _QUOTA_WALL_RE.search(text)
    if not m:
        return None
    try:
        import datetime as _dt
        ts = _dt.datetime.strptime(m.group(1) + " " + m.group(2), "%Y-%m-%d %H:%M:%S")
        ts = ts.replace(tzinfo=_dt.timezone(_dt.timedelta(hours=8)))
        wait = (ts - _dt.datetime.now(_dt.timezone.utc)).total_seconds()
    except ValueError:
        return None
    if wait <= 0:
        return None
    return max(1.0, wait) if wait <= 1e9 else None


# Provider-executed tools make an upstream turn non-idempotent: a replayed
# request could run web_search/code_execution twice. Only replay-safe payloads
# may fail over after a server-class upstream error.
_SIDE_EFFECT_TOOL_TYPES = frozenset({
    "web_search_20250305", "web_search_20250915", "code_execution_20250522",
})


def _replay_safe(payload: dict) -> bool:
    if payload.get("container") or payload.get("mcp_servers"):
        return False
    for tool in payload.get("tools") or []:
        if not isinstance(tool, dict) or tool.get("type") not in (None, "custom"):
            return False
    return True


def _retry_after_s(response) -> float | None:
    """Seconds from a Retry-After header (delta-seconds or HTTP-date), else None."""
    v = response.headers.get("retry-after")
    if not v:
        return None
    try:
        delay = float(v)
        return delay if math.isfinite(delay) and 0 <= delay <= 1e9 else None
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime
        import datetime as _dt
        when = parsedate_to_datetime(v)
        if when.tzinfo is None:
            when = when.replace(tzinfo=_dt.timezone.utc)
        delay = max(0.0, (when - _dt.datetime.now(_dt.timezone.utc)).total_seconds())
        return delay if math.isfinite(delay) and delay <= 1e9 else None
    except Exception:
        return None

class _Retryable(RuntimeError):
    """A pre-commit route refusal; the caller may try the next candidate.

    Logs and clients see constant FABRIC_* reasons, never upstream bodies.
    ``cooldown`` marks whether
    the rung failure should also bench the route for later requests.
    """

    def __init__(self, reason: str, detail: str = "", *, cooldown: bool = True,
                 cooldown_s: float | None = None, rejected: bool = False,
                 retryable: bool = False, category: str = "execution_unknown",
                 provider_code: str = "", owner_hold: bool = False, http_status: int = 502):
        super().__init__(reason)
        self.reason = reason
        self.cooldown = cooldown
        self.cooldown_s = cooldown_s
        self.rejected = rejected
        self.retryable = retryable
        self.category = category
        self.provider_code = provider_code
        self.owner_hold = owner_hold
        self.http_status = http_status
        _log.warning("fabric attempt refused: %s", reason)


async def _read_bounded(response: httpx.Response, limit: int) -> bytes:
    """Read at most ``limit`` bytes from a small error/health body."""
    data = bytearray()
    async for chunk in response.aiter_bytes():
        if len(data) + len(chunk) > limit:
            break
        data.extend(chunk)
    return bytes(data)


def _public_reason(exc: Exception, fallback: str) -> str:
    """Select a fixed public reason without propagating exception contents."""
    detail = str(exc)
    for public_code in _PUBLIC_REFUSAL_CODES:
        if detail == public_code:
            return public_code
    _log.warning("unified router withheld exception detail: %s", type(exc).__name__)
    return fallback

class _SyncHttpClient:
    """Short-lived synchronous client for OAuth refresh endpoints.

    Token refreshes are blocking file+HTTP transactions under the incumbent
    auth.json lock; they run in a worker thread (see ``_run_in_executor``)
    instead of blocking the router's event loop.
    """

    def __init__(self, timeout_s: float = 20.0):
        self._client = httpx.Client(timeout=timeout_s, follow_redirects=False)

    def post(self, *args, **kwargs):
        return self._client.post(*args, **kwargs)

    def close(self) -> None:
        self._client.close()


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
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    # Wait-for-capacity: when every rung is benched/exhausted, hold the request
    # up to this many seconds (polling for cooldown expiry) before failing with
    # 503, so a short-lived total outage does not kill client sessions. 0
    # disables. Never applies to count_tokens (cheap, never holds).
    capacity_wait_s: float = 45.0
    free_hold_s: float = 25.0
    model_labels: tuple[tuple[str, str], ...] = ()
    # Peak-window conservation: when the local wall clock (in peak_tz) is
    # inside [peak_start, peak_end), routes whose id starts with "glm_"
    # (the Z.ai subscription plans) are paced: sends are spaced at least
    # peak_min_interval_s apart fleet-wide, each send is additionally
    # delayed peak_delay_s (synthetic pacing so sessions keep working but
    # iterate slower), and the capacity hold is lifted to peak_wait_s so
    # paced requests are never failed with 503. Empty peak_tz disables.
    peak_tz: str = ""
    peak_start: str = "01:00"
    peak_end: str = "04:00"
    peak_min_interval_s: float = 0.0
    peak_delay_s: float = 0.0
    peak_wait_s: float = 0.0
    model_routing: dict = field(default_factory=dict)
    routes_path: Path | None = None
    routes_digest: str | None = None

    def __post_init__(self) -> None:
        if len(self.proxy_token) < 24:
            raise ValueError("FABRIC_ROUTER_TOKEN must contain at least 24 characters")
        if not self.routes:
            raise ValueError("the unified router needs at least one route")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
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
            model_priority={str(k): int(v) for k, v in entry.get("model_priority", {}).items()},
            model_weight={str(k): float(v) for k, v in entry.get("model_weight", {}).items()},
            model_params={str(k): dict(v) for k, v in entry.get("model_params", {}).items()},
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
            rate_limit=dict(entry.get("rate_limit") or {}),
            notes=entry.get("notes", "")))
    return tuple(routes)


def settings_from_env() -> Settings:
    routes_path = Path(os.environ.get("FABRIC_ROUTES_JSON", "")).expanduser()
    document, document_digest = read_document(routes_path)
    if document.get("model_routing", {}).get("version") != VERSION:
        raise ValueError("router requires its reviewed model-tier policy")
    aliases = tuple(
        (alias, tuple(targets))
        for alias, targets in document.get("aliases", {}).items())
    return Settings(
        proxy_token=os.environ.get("FABRIC_ROUTER_TOKEN", "").strip(),
        state_dir=Path(os.environ.get("FABRIC_GATEWAY_STATE_DIR", ".state")).expanduser(),
        routes=_routes_from_document(document),
        aliases=aliases,
        model_routing=document.get("model_routing") or {},
        peak_tz=os.environ.get("FABRIC_PEAK_TZ", "").strip(),
        peak_start=os.environ.get("FABRIC_PEAK_START", "01:00").strip(),
        peak_end=os.environ.get("FABRIC_PEAK_END", "04:00").strip(),
        peak_min_interval_s=float(os.environ.get("FABRIC_PEAK_MIN_INTERVAL_S", "0")),
        peak_delay_s=float(os.environ.get("FABRIC_PEAK_DELAY_S", "0")),
        peak_wait_s=float(os.environ.get("FABRIC_PEAK_WAIT_S", "0")),
        routes_path=routes_path, routes_digest=document_digest,
        auth_store=Path(os.environ.get("FABRIC_AUTH_STORE", str(DEFAULT_AUTH_STORE))).expanduser(),
        max_body_bytes=int(os.environ.get("FABRIC_MAX_BODY_BYTES", str(8 * 1024 * 1024))),
        upstream_timeout_s=float(os.environ.get("FABRIC_UPSTREAM_TIMEOUT_S", "900")),
        route_cooldown_s=float(os.environ.get("FABRIC_ROUTE_COOLDOWN_S", "30")),
        capacity_wait_s=float(os.environ.get("FABRIC_CAPACITY_WAIT_S", "45")),
        free_hold_s=float(os.environ.get("FABRIC_FREE_HOLD_S", "25")),
        max_attempts=int(os.environ.get("FABRIC_MAX_ATTEMPTS",
                                        str(DEFAULT_MAX_ATTEMPTS))),
        model_labels=tuple((str(k), str(v)) for k, v in
                           document.get("model_labels", {}).items()),
    )


def _peak_active(cfg: Settings) -> bool:
    """True when the local time in cfg.peak_tz is inside the peak window.
    The window may wrap midnight (start > end)."""
    if not cfg.peak_tz:
        return False
    try:
        import datetime as _dt
        from zoneinfo import ZoneInfo
        now = _dt.datetime.now(ZoneInfo(cfg.peak_tz))

        def _minutes(spec: str) -> int:
            hh, mm = spec.split(":")[:2]
            return int(hh) * 60 + int(mm)
        cur = now.hour * 60 + now.minute
        start = _minutes(cfg.peak_start)
        end = _minutes(cfg.peak_end)
    except Exception:
        return False
    if start == end:
        return False
    if start < end:
        return start <= cur < end
    return cur >= start or cur < end


# Fleet-wide send gate for peak-conservation routes (Z.ai GLM plans).
_PEAK_GATE_LOCK = asyncio.Lock()
_PEAK_GATE_NEXT = {"at": 0.0}


def _route_peak_gated(route: Route, cfg: Settings) -> bool:
    return cfg.peak_min_interval_s > 0 and route.route_id.startswith("glm_")


async def _peak_gate(route: Route, cfg: Settings) -> None:
    """Serialize paced sends: each caller waits for its slot, spaced at
    least peak_min_interval_s after the previous send, then absorbs the
    synthetic peak_delay_s before dispatch (outside the lock, so the next
    queued request can claim its slot meanwhile)."""
    if not _route_peak_gated(route, cfg):
        return
    async with _PEAK_GATE_LOCK:
        now = time.monotonic()
        wait_s = _PEAK_GATE_NEXT["at"] - now
        if wait_s > 0:
            await asyncio.sleep(wait_s)
        _PEAK_GATE_NEXT["at"] = time.monotonic() + cfg.peak_min_interval_s
    if cfg.peak_delay_s > 0:
        await asyncio.sleep(cfg.peak_delay_s)


@dataclass
class RouterState:
    routes: RouteState = field(default_factory=RouteState)
    started_at: float = field(default_factory=time.time)
    served: int = 0
    refused: int = 0
    attempts: int = 0
    failovers: int = 0
    exhausted: int = 0
    per_route: dict[str, dict[str, int]] = field(default_factory=dict)
    usage: dict[str, dict[str, int]] = field(default_factory=dict)
    rate_window: object = field(default=None)
    oauth_cursor: dict[str, int] = field(default_factory=dict)
    oauth_bench: dict[tuple[str, str], float] = field(default_factory=dict)
    oauth_bench_revision: dict[tuple[str, str], int] = field(default_factory=dict)
    oauth_bench_tasks: set = field(default_factory=set)

    def count_usage(self, route_id: str, inp: int, out: int) -> None:
        if inp <= 0 and out <= 0:
            return
        bucket = self.usage.setdefault(route_id, {"input": 0, "output": 0})
        bucket["input"] += max(0, int(inp))
        bucket["output"] += max(0, int(out))
        # Exact request settlement belongs to model_policy.finish, not aggregate telemetry.

    def count(self, route_id: str, outcome: str) -> None:
        bucket = self.per_route.setdefault(route_id, {"served": 0, "refused": 0})
        bucket[outcome] = bucket.get(outcome, 0) + 1


def _model_candidates(body: dict, aliases) -> list[tuple[str, str]]:
    """Ordered (model, alias) targets: an alias cascade, else the exact slug."""
    model = body.get("model")
    if not isinstance(model, str) or not model:
        raise WireTranslationError("FABRIC_EXACT_MODEL_REQUIRED")
    if model == "auto":
        metadata = body.get("metadata") or {}
        complexity = metadata.get("task_complexity") if isinstance(metadata, dict) else None
        if complexity == "C3_FRONTIER_JUDGMENT":
            raise WireTranslationError("FABRIC_EXPLICIT_FRONTIER_REQUIRED")
        if complexity == "C2_COMPLEX_BOUNDED":
            model = "fabric/balanced"
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


def _sanitize_messages(payload: dict) -> None:
    """Drop non-schema keys from message objects before forwarding.

    Clients (notably T3's claudeAgent driver) can leak model options such as
    ``output_config`` into the messages array. The Messages API rejects the
    whole request with ``messages.N.output_config: Extra inputs are not
    permitted``, which surfaced as a hard 400 to every Claude model. The
    message object schema is fixed, so an allowlist is safe and lossless for
    every valid request.
    """
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return
    kept: list = []
    directives: list = []
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            kept.append(message)
            continue
        if message.get("role") == "system":
            # The Messages API only accepts a system-role entry that precedes an
            # assistant turn or ends the array; T3 emits one mid-conversation and
            # the whole request 400s. Fold it into the top-level system param,
            # which is always valid, instead of discarding the instructions.
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                directives.append({"type": "text", "text": content})
            elif isinstance(content, list):
                directives.extend(block for block in content
                                  if isinstance(block, dict) and block.get("type") == "text")
            _log.warning("fabric sanitized messages.%d folded role=system model=%s",
                         index, payload.get("model"))
            continue
        extra = [key for key in message if key not in ("role", "content")]
        if extra:
            for key in extra:
                del message[key]
            _log.warning("fabric sanitized messages.%d dropped=%s model=%s",
                         index, ",".join(sorted(extra)), payload.get("model"))
        kept.append(message)
    if directives:
        system = payload.get("system")
        if isinstance(system, str):
            system = [{"type": "text", "text": system}] if system else []
        if not isinstance(system, list):
            system = []
        # APPEND, never prepend: the prompt cache is prefix-exact, so putting
        # the folded directives in front of the system block changes the very
        # first token of every turn and cold-prefills the whole context. Appending
        # keeps the existing prefix intact so only the new tail is uncached.
        payload["system"] = system + directives
    if len(kept) != len(messages):
        payload["messages"] = kept


_ALLOWED_TOP_LEVEL = frozenset({
    "model", "messages", "system", "max_tokens", "stop_sequences", "stream",
    "temperature", "top_k", "top_p", "metadata", "tools", "tool_choice",
    "thinking", "service_tier", "container", "mcp_servers", "betas",
})


def _sanitize_payload(payload: dict) -> None:
    """Drop keys this Messages API does not accept, then fix message objects.

    Newer clients (T3's claudeAgent driver) send forward-looking fields the
    pinned ``anthropic-version`` rejects outright -- a single stray key fails
    the whole request with a hard 400 that the router can only pass through.
    Observed live: ``messages.N.output_config``, then top-level
    ``context_management``. Stripping is strictly better than a 400 because
    the upstream would refuse the field anyway; every drop is logged so the
    drifting client stays visible.
    """
    extra = [key for key in payload if key not in _ALLOWED_TOP_LEVEL]
    for key in extra:
        del payload[key]
    if extra:
        _log.warning("fabric sanitized payload dropped=%s model=%s",
                     ",".join(sorted(extra)), payload.get("model"))
    _sanitize_messages(payload)


def _session_headers(route: Route, payload: dict, admission=None) -> dict[str, str]:
    """A stable, header-safe session id for upstreams that route by session."""
    if not route.session_header:
        return {}
    raw = (admission.session if admission else None) or _affinity(payload)
    if not raw:
        # Upstreams that route by session reject a MISSING header outright
        # (OpenCode Go -> 400 MissingSessionID), so never omit a declared
        # session header. Anchor on system+tools+first user message: the
        # previous messages[:2] basis changed between turns 1 and 2, splitting
        # the upstream session (and its server-side cache) exactly once per
        # new conversation.
        from ops.native_fabric.unified_router.model_policy import conversation_key
        raw = conversation_key(payload)
    cleaned = "".join(ch for ch in (raw or uuid.uuid4().hex) if 33 <= ord(ch) <= 126)[:64]
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
            limits=httpx.Limits(max_connections=128, max_keepalive_connections=32))
        try:
            yield
        finally:
            if app.state.router_state.oauth_bench_tasks:
                await asyncio.shield(asyncio.gather(*app.state.router_state.oauth_bench_tasks))
            await app.state.model_policy.flush_checkpoint()
            writer = app.state.model_policy._checkpoint_task
            if writer is not None:
                await asyncio.shield(writer)
            await app.state.upstream.aclose()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = cfg or settings_from_env()
    app.state.router_state = RouterState()
    app.state.router_state.rate_window = RateWindow()
    app.state.model_policy = ModelPolicyState(app.state.settings.routes,
        app.state.settings.aliases, app.state.settings.model_routing,
        app.state.router_state.rate_window, app.state.router_state.routes)
    app.state.model_policy.usage_counters = app.state.router_state.usage
    app.state.model_policy.uncertainty_s = app.state.settings.upstream_timeout_s + 60
    if app.state.settings.model_routing.get("persist_admission_state") is True:
        app.state.model_policy.configure_persistence(
            app.state.settings.state_dir / "admission-window-v1.json",
            uncertainty_s=app.state.settings.upstream_timeout_s + 60)
        app.state.model_policy.async_checkpoints = True
    from ops.native_fabric.unified_router import overflow as _fabric_overflow  # overflow add-on
    _fabric_overflow.install(app, __import__("sys").modules[__name__])
    app.state.config_refresh = ConfigRefresh(app.state.settings.routes_path, app.state.settings.routes_digest)

    def refresh_config():
        return app.state.config_refresh.refresh(app, _routes_from_document)


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
        # The Anthropic Messages wire's native credential header; accepted
        # alongside Bearer exactly like the incumbent anthropic gateway.
        api_key = request.headers.get("x-api-key", "")
        return bool(api_key) and hmac.compare_digest(
            api_key, app.state.settings.proxy_token)

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
        refresh_config()
        cfg: Settings = app.state.settings
        state: RouterState = app.state.router_state
        # Cooldown bookkeeping lives on the monotonic clock (see RouteState);
        # reading it with wall time would always report "not cooling".
        now = time.monotonic()
        return JSONResponse({
            "ok": True,
            "routes": [
                {"route_id": r.route_id, "wire": r.wire, "models": list(r.models),
                 "usage": state.usage.get(r.route_id, {"input": 0, "output": 0}),
                 "weight": r.weight, "priority": r.priority,
                 "max_in_flight": r.max_in_flight,
                 "concurrency_group": r.concurrency_group,
                 "group_max_in_flight": r.group_max_in_flight,
                 "circuit_generation": state.routes.generations.get(r.route_id, 0),
                 "probe_required": bool(state.routes.consecutive_failures.get(r.route_id, 0)),
                 "owner_hold": state.routes.owner_holds.get(r.route_id),
                 "model_holds": state.routes.model_holds.get(r.route_id, {}),
                 "cooldown_remaining_s": round(max(0, state.routes.cooldown_until.get(r.route_id, 0) - now), 1),
                 "last_failure": state.routes.last_failure.get(r.route_id, (None, None))[1],
                 "model_priority": dict(r.model_priority),
                 "model_weight": dict(r.model_weight),
                 "model_params": {slug: sorted(params) for slug, params
                                  in r.model_params.items()},
                 "cooling": not state.routes.available(r.route_id, now),
                 "consecutive_failures": state.routes.consecutive_failures.get(r.route_id, 0),
                 "served": state.per_route.get(r.route_id, {}).get("served", 0),
                 "attempt_failed": state.per_route.get(r.route_id, {}).get("attempt_failed", 0),
                 "refused": state.per_route.get(r.route_id, {}).get("refused", 0)}
                for r in cfg.routes],
            "aliases": {alias: list(targets) for alias, targets in cfg.aliases},
            "labels": {slug: label for slug, label in cfg.model_labels},
            "max_attempts": cfg.max_attempts,
            "served_total": state.served, "refused_total": state.refused,
            "attempts_total": state.attempts, "failovers_total": state.failovers,
            "exhausted_total": state.exhausted,
            "peak": {
                "active": _peak_active(cfg),
                "tz": cfg.peak_tz, "start": cfg.peak_start, "end": cfg.peak_end,
                "min_interval_s": cfg.peak_min_interval_s,
                "delay_s": cfg.peak_delay_s, "wait_s": cfg.peak_wait_s,
                "next_send_in_s": max(0.0, _PEAK_GATE_NEXT["at"] - now),
            },
            "model_routing": app.state.model_policy.snapshot(),
            "configuration": app.state.config_refresh.snapshot(),
        })

    @app.get("/routingz")
    async def routing_status(request: Request) -> Response:
        if not loopback_peer(request) or not authorized(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        refresh_config()
        result = app.state.model_policy.snapshot()
        result["configuration"] = app.state.config_refresh.snapshot()
        result["runtime_generation"] = getattr(app.state, "runtime_generation", None)
        result["source_matches_manifest"] = getattr(app.state, "source_matches_manifest", None)
        result["pid"] = os.getpid()
        return JSONResponse(result)

    @app.get("/v1/models")
    async def models(request: Request) -> Response:
        if not loopback_peer(request) or not authorized(request):
            return JSONResponse({"error": {"message": "unauthorized",
                                           "type": "authentication_error"}},
                                status_code=401)
        cfg: Settings = app.state.settings
        refresh_config()
        cfg = app.state.settings
        slugs: list[str] = []
        for route in cfg.routes:
            for model in route.models:
                if model not in slugs:
                    slugs.append(model)
        for alias, _ in cfg.aliases:
            if alias not in slugs:
                slugs.append(alias)
        labels = {slug.strip().lower(): label for slug, label in cfg.model_labels}
        return JSONResponse({"object": "list", "data": [
            {"id": slug, "object": "model", "type": "model",
             "display_name": labels.get(slug.strip().lower(), slug),
             "owned_by": "capacity-fabric"}
            for slug in slugs]})

    @app.post("/v1/messages")
    @app.post("/v1/messages/count_tokens")
    async def messages(request: Request) -> Response:
        if not loopback_peer(request):
            return JSONResponse({"error": {"message": "loopback access only"}}, status_code=403)
        if not authorized(request):
            return JSONResponse({"error": {"message": "unauthorized", "type": "authentication_error"}}, status_code=401)
        cfg: Settings = app.state.settings
        state: RouterState = app.state.router_state
        routing = app.state.model_policy
        if not refresh_config():
            return JSONResponse({"error": {"code": "FABRIC_CONFIG_INVALID_OR_ACTIVE_BINDING"}}, status_code=503)
        cfg = app.state.settings
        if routing.draining:
            return JSONResponse({"error": {"type": "fabric_capacity_error", "code": "FABRIC_DRAINING"}},
                                status_code=503, headers={"retry-after": "2"})
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > cfg.max_body_bytes:
            return JSONResponse({"error": {"message": "request body too large"}}, status_code=413)
        body = bytearray()
        try:
            async with asyncio.timeout(20):
                async for chunk in request.stream():
                    if len(body) + len(chunk) > cfg.max_body_bytes:
                        return JSONResponse({"error": {"message": "request body too large"}}, status_code=413)
                    body.extend(chunk)
        except TimeoutError:
            return JSONResponse({"error": {"code": "FABRIC_BODY_DEADLINE"}}, status_code=408)
        try:
            payload = json.loads(bytes(body))
            if not isinstance(payload, dict):
                raise ValueError("not an object")
            if "max_tokens" in payload and (type(payload["max_tokens"]) is not int
                    or not 1 <= payload["max_tokens"] <= 1000000):
                raise ValueError("invalid maximum output tokens")
            if "tools" in payload and (not isinstance(payload["tools"], list)
                    or any(not isinstance(tool, dict) for tool in payload["tools"])):
                raise ValueError("invalid tools")
            _sanitize_payload(payload)
            candidates = _model_candidates(payload, cfg.aliases)
        except (ValueError, WireTranslationError):
            return JSONResponse({"error": {"message": "invalid request body or model", "type": "invalid_request_error"}}, status_code=400)
        counting = request.url.path.endswith("/count_tokens")
        wants_stream = payload.get("stream") is True
        session = session_key(request.headers, payload)
        fingerprint = prefix_signature(payload)
        nonce = uuid.uuid4().hex
        began = time.monotonic()
        peak_on = _peak_active(cfg)
        # The peak admission budget only applies while pacing is actually armed
        # for at least one route. With FABRIC_PEAK_MIN_INTERVAL_S=0 no route is
        # gated, and keeping peak_wait_s (60s) instead of the capacity budget
        # (120s) silently halved every client's wait inside the peak window.
        peak_armed = peak_on and cfg.peak_wait_s > 0 and any(
            _route_peak_gated(r, cfg) for r in cfg.routes)
        admission_deadline = began + (0 if counting else (
            max(0.0, cfg.peak_wait_s) if peak_armed
            else min(120.0, max(0.0, cfg.capacity_wait_s))))
        send_count = 0
        waiting = False
        reason = "FABRIC_ALL_ROUTES_UNAVAILABLE"
        preflight_excluded: set[str] = set()

        def note_failure(route, code, retry_after=None, admission=None, failure=None):
            state.count(route.route_id, "attempt_failed")
            if counting:
                # count_tokens is metering, not inference: a metering failure
                # must never open (and a metering success must never close) the
                # inference circuit breaker for real traffic.
                return
            quota = code.endswith("_429") or bool(failure and failure.category in ("quota_exhausted", "temporary_capacity"))
            if quota:
                routing.counters["quota_refusals"] += 1
            # Keep actual provider Retry-After, including long quota windows.
            # Permission refusals are terminal for this request, never a fallback trigger.
            delay = retry_after if retry_after is not None and retry_after > 0 else (65.0 if quota else cfg.route_cooldown_s)
            # Gateway-kind routes proxy a LOCAL pool gateway (8312/8311) that
            # already enforces per-account budgets and benches per account
            # upstream. Benching the whole pool route here strands every
            # account behind it -- observed live as claude_pool parked for an
            # hour by a single saturated instant's large Retry-After, and
            # re-benched by connect blips whenever the pool gateway restarts.
            # Cap pool benches short and never let them escalate.
            if getattr(route, "kind", "") == "gateway":
                delay = min(delay, 10.0 if code == "FABRIC_ROUTE_CONNECT" else 30.0)
            resource, _ = routing.resource(route)
            affected = [r for r in routing.routes.values() if routing.resource(r)[0] == resource] if quota else [route]
            for member in affected:
                state.routes.record_failure(member.route_id, code, now=time.monotonic(),
                    cooldown_s=delay, escalate=not quota and getattr(route, "kind", "") != "gateway",
                    generation=admission.circuit_generation if admission and member is route else None,
                    quota=quota)
                # A local pool gateway retains its own per-account hold owner.
                # Direct-route unknown exhaustion cannot be cleared by a timer.
                if failure and failure.owner_hold and retry_after is None and member.kind != "gateway":
                    state.routes.hold(member.route_id, failure.category,
                                      failure.provider_code or code, now=time.monotonic())
            routing.changed.set()
            routing.checkpoint()

        async def invoke(route, resolved, admission):
            forwarded = dict(payload, model=route.wire_model(resolved))
            # Caller routing/provenance hints are consumed locally, not unsupported provider fields.
            metadata = forwarded.get("metadata")
            if isinstance(metadata, dict):
                metadata = {k: v for k, v in metadata.items() if k not in ("fabric", "task_complexity")}
                if metadata:
                    forwarded["metadata"] = metadata
                else:
                    forwarded.pop("metadata", None)
            if route.wire == WIRE_ANTHROPIC:
                forwarded.pop("prompt_cache_key", None)
            if route.wire == WIRE_RESPONSES:
                return await _forward_responses(app, route, forwarded, wants_stream,
                                                admission=admission)
            try:
                authorization = _route_authorization(route, cfg)
            except PermissionError:
                return JSONResponse({"error": {"code": "FABRIC_CREDENTIAL_PERMISSION_REFUSED"}}, status_code=403)
            except (OSError, ValueError):
                raise _Retryable("FABRIC_ROUTE_CREDENTIAL", cooldown=True,
                                 rejected=True, retryable=True, category="local_preflight")
            if counting:
                return await _forward_anthropic_count(app, route, authorization, forwarded, admission=admission)
            if route.wire == WIRE_ANTHROPIC:
                return await _forward_anthropic(app, route, authorization, forwarded,
                                                wants_stream, admission=admission)
            return await _forward_openai(app, route, authorization, forwarded,
                                         wants_stream, resolved, admission=admission)

        try:
            while True:
                now = time.monotonic()
                if not refresh_config():
                    return JSONResponse({"error": {"code": "FABRIC_CONFIG_INVALID_OR_ACTIVE_BINDING"}}, status_code=503)
                cfg = app.state.settings
                if routing.draining:
                    return JSONResponse({"error": {"code": "FABRIC_DRAINING"}}, status_code=503, headers={"retry-after": "2"})
                candidates = _model_candidates(payload, cfg.aliases)
                if await request.is_disconnected():
                    return Response(status_code=499)
                ladder, eta, decision, profile = routing.plan(
                    candidates, payload, session, nonce, now, now - began, counting, fingerprint)
                if decision.startswith("FABRIC_"):
                    reason = decision
                if len(routing.active) >= 128:
                    ladder, eta, reason = [], 1.0, "FABRIC_GLOBAL_CAPACITY"
                for route, resolved in ladder:
                    if route.route_id in preflight_excluded:
                        continue
                    if send_count >= cfg.max_attempts:
                        break
                    # Availability and reservation are synchronous and adjacent.
                    capacity_eta = (routing.concurrency_eta(route, inference=False) if counting else
                        routing.eta(route, resolved, payload, session, time.monotonic(), fingerprint))
                    if capacity_eta > 0:
                        continue
                    if not counting and peak_on and _route_peak_gated(route, cfg):
                        # Peak conservation: pace this send for its fleet-wide slot
                        # BEFORE reserving capacity. Reserving first made every gate
                        # waiter hold an inflight slot, so eta() reported the GLM
                        # routes as saturated, the ladder skipped them, and new work
                        # was diverted to a different provider mid-conversation --
                        # losing that thread's warm prompt cache.
                        await _peak_gate(route, cfg)
                    # The peak gate awaited; another request may have reserved
                    # this resource while it slept. Recheck after the final await.
                    capacity_eta = (routing.concurrency_eta(route, inference=False) if counting else
                        routing.eta(route, resolved, payload, session, time.monotonic(), fingerprint))
                    if len(routing.active) >= 128 or capacity_eta > 0:
                        continue
                    selected_at = time.monotonic()
                    try:
                        admission = routing.begin(route, resolved, payload, session, profile,
                            time.monotonic(), fingerprint, operation="count_tokens" if counting else "inference")
                    except AdmissionCapacityChanged:
                        reason = "FABRIC_ADMISSION_CAPACITY_CHANGED"
                        continue
                    if admission:
                        admission.routing_reason = ("overflow_safe_rejection"
                            if admission.overflow_target and profile.startswith("model:")
                            and not decision.startswith("overflow_") else decision)
                    if admission and admission.effective_max_tokens is not None:
                        try:
                            durable = await routing.flush_checkpoint()
                            disconnected = durable and await request.is_disconnected()
                        except BaseException:
                            routing.finish(admission, no_send=True)
                            raise
                        if not durable:
                            routing.finish(admission, no_send=True)
                            # No send occurred. The latched state error removes
                            # strict seats; permitted non-strict fallback remains.
                            reason = "FABRIC_ADMISSION_STATE_UNAVAILABLE"
                            continue
                        if disconnected:
                            routing.finish(admission, no_send=True)
                            return JSONResponse({"error": {"code": "FABRIC_CLIENT_DISCONNECTED"}}, status_code=499)
                        if not refresh_config() or not routing.send_ready(admission, time.monotonic()):
                            routing.finish(admission, no_send=True)
                            reason = "FABRIC_ADMISSION_INVALIDATED"
                            continue
                    remaining = cfg.upstream_timeout_s if admission is None else (
                        cfg.upstream_timeout_s - (time.monotonic() - admission.started))
                    if remaining <= 0:
                        routing.finish(admission, no_send=True)
                        return JSONResponse({"error": {"code": "FABRIC_ADMISSION_DEADLINE"}}, status_code=503)
                    send_count += 1
                    state.attempts += 1
                    if send_count > 1:
                        state.failovers += 1
                    if waiting:
                        routing.waiters.pop(nonce, None); waiting = False
                    try:
                        async with asyncio.timeout(remaining):
                            response = await invoke(route, resolved, admission)
                    except _Retryable as exc:
                        code = exc.reason
                        note_failure(route, code, getattr(exc, "cooldown_s", None), admission, exc)
                        # Only proven local no-send or a classified admission
                        # rejection may continue through the bounded ladder.
                        permitted = exc.retryable and exc.rejected
                        routing.finish(admission, no_send=exc.rejected)
                        reason = code
                        if not permitted:
                            state.refused += 1
                            return JSONResponse({"error": {"type": "fabric_route_error", "code": code,
                                "category": exc.category,
                                "message": "upstream outcome was not replayed"}}, status_code=exc.http_status)
                        continue
                    except _ResponsesRouteRefused as exc:
                        safe = bool(admission and not admission.sent)
                        routing.finish(admission, no_send=safe)
                        reason = exc.reason
                        if safe:
                            # An owner hold or expired credential is not a sick
                            # provider. Try qualified alternatives before send,
                            # and reconsider this pool on the next request.
                            preflight_excluded.add(route.route_id)
                            continue
                        return JSONResponse({"error": {"code": exc.reason,
                            "message": "upstream outcome not replayed"}}, status_code=502)
                    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
                        # Only our own direct retry-free transport can prove connect/pool pre-send failure.
                        safe = transport is None
                        routing.finish(admission, no_send=safe)
                        note_failure(route, "FABRIC_ROUTE_CONNECT", admission=admission)
                        reason = "FABRIC_ROUTE_CONNECT"
                        if safe:
                            continue
                        return JSONResponse({"error": {"code": "FABRIC_UPSTREAM_EFFECT_UNKNOWN"}}, status_code=502)
                    except (httpx.RequestError, TimeoutError):
                        routing.finish(admission)
                        note_failure(route, "FABRIC_UPSTREAM_EFFECT_UNKNOWN", admission=admission)
                        state.refused += 1
                        return JSONResponse({"error": {"code": "FABRIC_UPSTREAM_EFFECT_UNKNOWN",
                            "message": "request may have reached upstream; not replayed"}}, status_code=502)
                    except BaseException:
                        routing.finish(admission, no_send=bool(admission and not admission.sent))
                        raise
                    response.headers["x-fabric-resolved-model"] = resolved
                    response.headers["x-fabric-route"] = route.route_id
                    response.headers["x-fabric-requested-model"] = str(payload.get("model", ""))
                    response.headers["x-fabric-routing-reason"] = admission.routing_reason if admission else decision
                    response.headers["x-fabric-model-substituted"] = str(resolved != payload.get("model")).lower()
                    response.headers["x-fabric-routing-policy"] = VERSION
                    response.headers["x-fabric-request-id"] = nonce
                    if getattr(app.state, "runtime_generation", None):
                        response.headers["x-fabric-generation"] = app.state.runtime_generation
                    response.headers["x-fabric-admission-wait-ms"] = str(int((selected_at - began) * 1000))
                    if admission and admission.effective_max_tokens is not None:
                        response.headers["x-fabric-requested-max-tokens"] = str(admission.requested_max_tokens)
                        response.headers["x-fabric-effective-max-tokens"] = str(admission.effective_max_tokens)
                    if admission and isinstance(response, StreamingResponse):
                        original_iterator = response.body_iterator
                        async def finish_stream(iterator=original_iterator, admitted=admission):
                            try:
                                remaining = max(0.001, cfg.upstream_timeout_s - (time.monotonic() - admitted.started))
                                async with asyncio.timeout(remaining):
                                    async for part in iterator:
                                        yield part
                            finally:
                                try:
                                    close = getattr(iterator, "aclose", None)
                                    if close is not None:
                                        await close()
                                finally:
                                    routing.finish(admitted, success=admitted.completed)
                                    if admitted.completed:
                                        state.served += 1
                                        state.count(admitted.route_id, "served")
                                        state.routes.record_success(admitted.route_id,
                                            generation=admitted.circuit_generation)
                                        routing.checkpoint()
                        response.body_iterator = finish_stream()
                    else:
                        success = 200 <= response.status_code < 300 and (counting or bool(admission and admission.completed))
                        routing.finish(admission, success=success,
                                       no_send=bool(admission and (not admission.sent or admission.rejected_before_acceptance)))
                        if success:
                            state.served += 1; state.count(route.route_id, "served")
                            if not counting:
                                state.routes.record_success(route.route_id, generation=admission.circuit_generation)
                                routing.checkpoint()
                        elif not counting and response.status_code in (401, 403):
                            # Provider refusal is already scoped by upstream_refusal.
                            # This remaining path is a local credential read denial.
                            if not admission.sent:
                                state.routes.hold(route.route_id, "permission", "FABRIC_CREDENTIAL_PERMISSION_REFUSED",
                                                  now=time.monotonic())
                            routing.checkpoint()
                    return response
                if counting or send_count >= cfg.max_attempts or time.monotonic() >= admission_deadline:
                    break
                if ladder and all(r.route_id in preflight_excluded for r, _ in ladder):
                    break
                if reason in ("FABRIC_MODEL_UNKNOWN", "FABRIC_TIER_CAPABILITY_UNAVAILABLE", "FABRIC_COUNT_TOKENS_WIRE", "FABRIC_REQUEST_EXCEEDS_CAPACITY"):
                    break
                if not waiting:
                    if not routing.join_wait(nonce, session):
                        reason = "FABRIC_QUEUE_FULL"; break
                    waiting = True
                # Event-driven completion wake, bounded polling only for clock/remote cooldown.
                timeout = min(max(0.05, eta if math.isfinite(eta) else 1.0),
                              1.0, max(0.001, admission_deadline - time.monotonic()))
                routing.changed.clear()
                try:
                    await asyncio.wait_for(routing.changed.wait(), timeout)
                except TimeoutError:
                    pass
            state.refused += 1
            state.exhausted += 1
            refusal_headers = {"x-fabric-request-id": nonce}
            if reason not in {"FABRIC_OAUTH_OWNER_HELD", "FABRIC_OAUTH_REFRESH_REQUIRED", "FABRIC_OAUTH_NO_ACCOUNT"}:
                refusal_headers["retry-after"] = str(max(1, math.ceil(eta))) if math.isfinite(eta) and eta > 0 else "5"
            return JSONResponse({"error": {"code": reason, "type": "fabric_capacity_error",
                "message": "no eligible capacity within the configured model/fallback policy"}},
                status_code=501 if reason == "FABRIC_COUNT_TOKENS_WIRE" else 503,
                headers=refusal_headers)
        finally:
            routing.waiters.pop(nonce, None)

    def upstream_refusal(route, payload, admission, status, detail, retry_after, request_url=None):
        failure = classify_provider_error(status, detail)
        if admission:
            admission.rejected_before_acceptance = failure.rejected
        code = f"FABRIC_ROUTE_HTTP_{status}"
        if failure.category in ("temporary_capacity", "quota_exhausted"):
            app.state.model_policy.learn_limit(route, detail)
            delay = _quota_wall_s(detail, route, request_url) or retry_after
            delay = delay if delay is not None and delay > 0 else None
            raise _Retryable(code, cooldown_s=delay, rejected=failure.rejected,
                retryable=failure.retryable and _replay_safe(payload), category=failure.category,
                provider_code=failure.code, owner_hold=failure.owner_hold, http_status=status)
        if failure.category == "execution_unknown":
            raise _Retryable(code, cooldown_s=retry_after, provider_code=failure.code,
                             http_status=502 if status == 500 else status)
        if failure.category == "permission" and failure.owner_hold:
            # Refusal ends this request. No alternate account/model/provider replay.
            state = app.state.router_state.routes
            state.hold(route.route_id, failure.category, failure.code, now=time.monotonic(),
                       model=admission.model if admission and failure.scope == "model" else None)
            app.state.model_policy.checkpoint()
        return JSONResponse({"error": {"type": "upstream_error", "code": code,
            "category": failure.category, "provider_code": failure.code,
            "message": "upstream refused; request was not replayed"}}, status_code=status)

    async def _forward_anthropic_count(app, route, authorization, payload, *, admission=None) -> Response:
        upstream: httpx.AsyncClient = app.state.upstream
        upstream_request = upstream.build_request(
            "POST", f"{_route_base_url(route).rstrip('/')}/v1/messages/count_tokens",
            headers={**_upstream_auth_headers(route, authorization),
                     **_session_headers(route, payload),
                     "content-type": "application/json",
                     "accept-encoding": "identity"},
            content=json.dumps(payload).encode())
        if admission:
            admission.sent = True
        response = await upstream.send(upstream_request)
        if response.status_code >= 400:
            # Metering shares transport capacity, not inference health/holds.
            return Response(content=response.content, status_code=response.status_code,
                            media_type="application/json")
        data = response.content
        return Response(content=data, status_code=response.status_code,
                        media_type="application/json")

    async def _forward_anthropic(app, route, authorization, payload,
                                 wants_stream, *, admission=None) -> Response:
        cfg: Settings = app.state.settings
        upstream: httpx.AsyncClient = app.state.upstream
        request_headers = {**_upstream_auth_headers(route, authorization),
                           **_session_headers(route, payload, admission),
                           "content-type": "application/json", "accept-encoding": "identity"}
        upstream_request = upstream.build_request("POST",
            f"{_route_base_url(route).rstrip('/')}/v1/messages", headers=request_headers,
            content=json.dumps(payload).encode())
        if admission:
            admission.sent = True
        response = await upstream.send(upstream_request, stream=True)
        if response.status_code >= 400:
            detail = await _read_bounded(response, 4096)
            retry_after = _retry_after_s(response)
            await response.aclose()
            return upstream_refusal(route, payload, admission, response.status_code, detail, retry_after, str(upstream_request.url))
        headers = {k: v for k, v in response.headers.items()
                   if k.lower() in {"content-type", "x-request-id", "retry-after"}}
        if not wants_stream:
            try:
                data = await _read_response_bounded(response, cfg.max_body_bytes)
                parsed = json.loads(data)
                app.state.model_policy.observe_usage(admission, parsed.get("usage"), "anthropic", parsed.get("model"))
                if admission:
                    admission.completed = parsed.get("type") == "message" and parsed.get("stop_reason") is not None
            except (ValueError, WireTranslationError):
                return JSONResponse({"error": {"code": "FABRIC_RESPONSE_INVALID"}}, status_code=502)
            finally:
                await response.aclose()
            return Response(content=data, status_code=response.status_code,
                            headers=headers, media_type="application/json")

        async def stream():
            buffer, usage = b"", {}
            try:
                async for part in response.aiter_bytes():
                    buffer += part
                    if len(buffer) > 2 * 1024 * 1024:
                        raise WireTranslationError("FABRIC_STREAM_EVENT_TOO_LARGE")
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        if not line.strip().startswith(b"data:"):
                            continue
                        try:
                            event = json.loads(line.strip()[5:])
                        except ValueError:
                            raise WireTranslationError("FABRIC_STREAM_INVALID_JSON")
                        if not isinstance(event, dict):
                            raise WireTranslationError("FABRIC_STREAM_INVALID")
                        message = event.get("message") or {}
                        if event.get("type") == "message_start" and isinstance(message, dict):
                            usage.update(message.get("usage") or {})
                            app.state.model_policy.observe_usage(admission, usage, "anthropic", message.get("model"))
                        elif event.get("type") == "message_delta":
                            usage.update(event.get("usage") or {})
                            app.state.model_policy.observe_usage(admission, usage, "anthropic")
                        elif event.get("type") == "message_stop" and admission:
                            admission.completed = True
                        elif event.get("type") == "error":
                            if admission:
                                admission.completed = False
                                admission.finish_reason = "stream_incomplete"
                    yield part  # Preserve the exact native Anthropic stream.
                if admission and not admission.completed:
                    admission.finish_reason = "stream_incomplete"
                    yield _sse("error", json.dumps({"type": "error", "error": {
                        "type": "api_error", "message": "FABRIC_STREAM_INCOMPLETE"}}))
            finally:
                await response.aclose()
        return StreamingResponse(stream(), status_code=response.status_code, headers=headers)

    async def _read_response_bounded(response, limit):
        data = bytearray()
        async for part in response.aiter_bytes():
            if len(data) + len(part) > limit:
                raise WireTranslationError("FABRIC_RESPONSE_TOO_LARGE")
            data.extend(part)
        return bytes(data)

    async def _forward_openai(app, route, authorization, payload,
                              wants_stream, slug="", *, admission=None) -> Response:
        cfg: Settings = app.state.settings
        upstream: httpx.AsyncClient = app.state.upstream
        try:
            openai_request = anthropic_to_openai(payload)
        except WireTranslationError as exc:
            return JSONResponse({"error": {"message": _public_reason(exc, "FABRIC_TRANSLATE_INVALID"),
                "type": "invalid_request_error"}}, status_code=400)
        if slug:
            openai_request.update(route.effective_params(slug))
        if admission and admission.effective_max_tokens is not None:
            # Apply last: a route override must not exceed its reserved output.
            openai_request["max_tokens"] = admission.effective_max_tokens
            if "max_completion_tokens" in openai_request:
                openai_request["max_completion_tokens"] = admission.effective_max_tokens
        if wants_stream:
            openai_request["stream_options"] = {"include_usage": True}
        upstream_request = upstream.build_request("POST",
            f"{_route_base_url(route).rstrip('/')}/chat/completions",
            headers={**_upstream_auth_headers(route, authorization),
                     **_session_headers(route, payload, admission),
                     "content-type": "application/json", "accept-encoding": "identity"},
            content=json.dumps(openai_request).encode())
        if admission:
            admission.sent = True
        response = await upstream.send(upstream_request, stream=True)
        app.state.model_policy.observe_headers(route, response.headers, admission)
        if response.status_code >= 400:
            detail = await _read_bounded(response, 4096)
            retry_after = _retry_after_s(response)
            await response.aclose()
            return upstream_refusal(route, payload, admission, response.status_code, detail, retry_after, str(upstream_request.url))
        if not wants_stream:
            try:
                data = await _read_response_bounded(response, cfg.max_body_bytes)
                parsed = json.loads(data)
                app.state.model_policy.observe_usage(admission, parsed.get("usage"), "openai", parsed.get("model"))
                translated = openai_to_anthropic(parsed, model=slug or payload["model"],
                    message_id=f"msg_{admission.token}" if admission else None)
                if admission:
                    admission.completed = bool(parsed.get("choices") and parsed["choices"][0].get("finish_reason"))
                    admission.finish_reason = parsed["choices"][0].get("finish_reason") if parsed.get("choices") else None
                return JSONResponse(translated)
            except (ValueError, WireTranslationError):
                return JSONResponse({"error": {"code": "FABRIC_RESPONSE_INVALID"}}, status_code=502)
            finally:
                await response.aclose()
        translator = OpenAIStreamTranslator(model=slug or payload["model"],
            message_id=f"msg_{admission.token}" if admission else f"msg_{uuid.uuid4().hex}")

        async def stream():
            first, buffer, terminal = True, b"", False
            try:
                async for part in response.aiter_bytes():
                    buffer += part
                    if len(buffer) > 2 * 1024 * 1024:
                        raise WireTranslationError("FABRIC_STREAM_EVENT_TOO_LARGE")
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        text = line.decode("utf-8", "strict").strip()
                        if not text.startswith("data:"):
                            continue
                        data = text[5:].strip()
                        if data == "[DONE]":
                            if not terminal:
                                raise WireTranslationError("FABRIC_STREAM_INCOMPLETE")
                            for event in translator.finish():
                                yield _sse(*event)
                            if admission:
                                admission.completed = True
                            return
                        chunk = json.loads(data)
                        if not isinstance(chunk, dict) or chunk.get("error"):
                            raise WireTranslationError("FABRIC_UPSTREAM_STREAM_ERROR")
                        app.state.model_policy.observe_usage(admission, chunk.get("usage"), "openai", chunk.get("model"))
                        if first:
                            yield _sse(*translator.message_start()); first = False
                        for event in translator.feed(chunk):
                            yield _sse(*event)
                        if any(isinstance(c, dict) and c.get("finish_reason") for c in (chunk.get("choices") or [])):
                            terminal = True
                            if admission:
                                admission.finish_reason = next(c["finish_reason"] for c in chunk["choices"]
                                    if isinstance(c, dict) and c.get("finish_reason"))
                raise WireTranslationError("FABRIC_STREAM_INCOMPLETE")
            except (ValueError, UnicodeError, WireTranslationError, httpx.RequestError):
                if admission:
                    admission.completed = False
                    admission.finish_reason = "stream_incomplete"
                yield _sse("error", json.dumps({"type": "error", "error": {
                    "type": "api_error", "message": "FABRIC_STREAM_INCOMPLETE; request was not replayed"}}))
            finally:
                await response.aclose()
        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"cache-control": "no-store"})


    class _ResponsesRouteRefused(RuntimeError):
        """Local account preflight refusal; inference has not been sent."""

        def __init__(self, reason: str):
            super().__init__(reason)
            self.reason = reason

    def _oauth_headers(account) -> dict[str, str]:
        headers = {"authorization": f"Bearer {account.access_token}",
                   "content-type": "application/json",
                   "accept-encoding": "identity",
                   "originator": "hermes-agent",
                   "user-agent": "HermesAgent/fabric-router"}
        headers.update(codex_oauth.account_id_header(account.access_token))
        return headers

    async def _oauth_accounts(route: Route):
        try:
            accounts = await asyncio.to_thread(codex_oauth.read_accounts,
                app.state.settings.auth_store, route.pool)
        except (OSError, ValueError, codex_oauth.OAuthPoolError):
            raise _ResponsesRouteRefused("FABRIC_OAUTH_NO_ACCOUNT") from None
        now = time.time()
        state: RouterState = app.state.router_state
        unheld = [a for a in accounts if not a.owner_held]
        if not unheld:
            raise _ResponsesRouteRefused("FABRIC_OAUTH_OWNER_HELD")
        unexpired = [a for a in unheld if (
            codex_oauth.access_token_expiry(a.access_token) is None
            or codex_oauth.access_token_expiry(a.access_token) > now + 30)]
        if not unexpired:
            raise _ResponsesRouteRefused("FABRIC_OAUTH_REFRESH_REQUIRED")
        eligible = [a for a in unexpired if not a.exhausted
                    and state.oauth_bench.get((route.route_id, a.id), 0.0) <= now]
        if not eligible:
            raise _ResponsesRouteRefused("FABRIC_OAUTH_ACCOUNTS_EXHAUSTED")
        return eligible

    async def _forward_responses(app_, route: Route, payload: dict,
                                 wants_stream: bool, *, admission=None) -> Response:
        state: RouterState = app.state.router_state
        cfg_: Settings = app.state.settings
        upstream: httpx.AsyncClient = app.state.upstream
        try:
            responses_request = anthropic_to_responses(payload)
        except WireTranslationError as exc:
            return JSONResponse({"error": {"message": _public_reason(exc, "FABRIC_TRANSLATE_INVALID"),
                                           "type": "invalid_request_error"}}, status_code=400)
        responses_request["stream"] = True
        eligible = await _oauth_accounts(route)
        cursor = state.oauth_cursor.get(route.route_id, 0)
        selected = eligible[cursor % len(eligible)]
        state.oauth_cursor[route.route_id] = (cursor + 1) % len(eligible)
        # Exactly one identity per inference. Rotation belongs to the incumbent
        # auth owner; a 401/429/5xx never causes refresh or account replay here.
        request = upstream.build_request("POST",
            f"{_route_base_url(route).rstrip('/')}/responses",
            headers=_oauth_headers(selected), content=json.dumps(responses_request).encode())
        if admission:
            admission.sent = True
        response = await upstream.send(request, stream=True)
        if response.status_code >= 400:
            status = response.status_code
            retry_after = _retry_after_s(response)
            await response.aclose()
            if status == 429:
                reset_at = time.time() + retry_after if retry_after is not None else None
                key = (route.route_id, selected.id)
                state.oauth_bench[key] = max(state.oauth_bench.get(key, 0.0), reset_at or float("inf"))
                revision = state.oauth_bench_revision.get(key, 0) + 1
                state.oauth_bench_revision[key] = revision
                combined = state.oauth_bench[key]

                async def persist_bench():
                    try:
                        await asyncio.to_thread(codex_oauth.bench_row, cfg_.auth_store,
                            route.pool, selected.id,
                            reset_at=combined if math.isfinite(combined) else None,
                            reason="http_429")
                        # Request cancellation cannot strand a completed write,
                        # nor can an older write clear a newer pending hold.
                        if state.oauth_bench_revision.get(key) == revision:
                            state.oauth_bench.pop(key, None)
                    except (OSError, ValueError, codex_oauth.OAuthPoolError):
                        _log.error("fabric OAuth account hold could not be persisted")

                writer = asyncio.create_task(persist_bench())
                state.oauth_bench_tasks.add(writer)
                writer.add_done_callback(state.oauth_bench_tasks.discard)
                await asyncio.shield(writer)
                state.count(route.route_id, "account_limited")
                headers = {"retry-after": str(max(1, math.ceil(retry_after)))} if retry_after is not None else {}
                return JSONResponse({"error": {"code": "FABRIC_OAUTH_ACCOUNT_LIMIT",
                    "message": "upstream limit; request was not replayed"}}, status_code=503, headers=headers)
            code = "FABRIC_OAUTH_AUTH_REFUSED" if status in (401, 403) else (
                "FABRIC_OAUTH_UPSTREAM_5XX" if status >= 500 else "FABRIC_OAUTH_UPSTREAM_REFUSED")
            if status >= 500:
                state.routes.record_failure(route.route_id, code, now=time.monotonic(),
                    cooldown_s=cfg_.route_cooldown_s,
                    generation=admission.circuit_generation if admission else None)
                app.state.model_policy.checkpoint()
            return JSONResponse({"error": {"code": code,
                "message": "upstream refusal; request was not replayed"}},
                status_code=502 if status >= 500 else status)

        translator = ResponsesStreamTranslator(model=payload["model"],
            retain_text=not wants_stream,
            message_id=f"msg_{admission.token}" if admission else f"msg_{uuid.uuid4().hex}")

        async def events():
            buffer, received = b"", 0
            async for part in response.aiter_bytes():
                received += len(part)
                if received > cfg_.max_body_bytes:
                    raise WireTranslationError("FABRIC_RESPONSE_TOO_LARGE")
                buffer += part
                if len(buffer) > 2 * 1024 * 1024:
                    raise WireTranslationError("FABRIC_STREAM_EVENT_TOO_LARGE")
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    text = line.decode("utf-8", "strict").strip()
                    if not text.startswith("data:"):
                        continue
                    data = text[5:].strip()
                    if data == "[DONE]":
                        if not translator.completed:
                            raise WireTranslationError("FABRIC_STREAM_INCOMPLETE")
                        return
                    event = json.loads(data)
                    translated = translator.feed(event)
                    if translator.completed:
                        completed = event.get("response") or {}
                        app.state.model_policy.observe_usage(admission, completed.get("usage"),
                            "responses", completed.get("model"))
                    for translated_event in translated:
                        yield translated_event
                    # Responses completion is itself the terminal event; [DONE]
                    # is optional. Tool JSON is validated by finish/to_message.
                    if translator.completed:
                        return
            if not translator.completed:
                raise WireTranslationError("FABRIC_STREAM_INCOMPLETE")

        def completed():
            if admission:
                admission.completed = True
                admission.finish_reason = translator._finish

        if not wants_stream:
            try:
                async for _ in events():
                    pass
                result = translator.to_message()
                completed()
                return JSONResponse(result)
            except (ValueError, UnicodeError, httpx.RequestError):
                return JSONResponse({"error": {"code": "FABRIC_RESPONSE_INVALID",
                    "message": "incomplete or invalid response; request was not replayed"}}, status_code=502)
            finally:
                await response.aclose()

        async def stream():
            try:
                yield _sse(*translator.message_start())
                async for event in events():
                    yield _sse(*event)
                final_events = translator.finish()
                for event in final_events:
                    yield _sse(*event)
                completed()
            except (ValueError, UnicodeError, httpx.RequestError):
                if admission:
                    admission.completed = False
                    admission.finish_reason = "stream_incomplete"
                yield _sse("error", json.dumps({"type": "error", "error": {
                    "type": "api_error", "message": "FABRIC_STREAM_INCOMPLETE; request was not replayed"}}))
            finally:
                await response.aclose()
        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"cache-control": "no-store"})

    def _sse(event: str, data: str) -> bytes:
        return f"event: {event}\ndata: {data}\n\n".encode()

    return app
