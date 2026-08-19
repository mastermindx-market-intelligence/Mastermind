"""App-level authorization for the Mastermind dashboard.

Mastermind manages paper portfolios and an LLM brain that spends tokens, so the
mutating/LLM-triggering routes must NOT be exposed unprotected. This installs a
middleware that enforces FOUR things — and nothing more:

  1. the serve-only POST guard (blocks operator mutations on a read mirror),
  2. the personal-pfolio guard (see PERSONAL PFOLIO PANEL below),
  3. the bearer-token OPERATOR tier (mutating/LLM POSTs require a bearer token),
  4. rate limiting on operator paths.

The browser PASSWORD-COOKIE LOGIN FLOW has been REMOVED (page-only scope):
there is no ``/login`` page, no ``/logout`` route, and no session cookie. Browsing
the dashboard (all GETs + read APIs + the SSE stream) requires NO login anywhere.
``MASTERMIND_PASSWORD``, ``MASTERMIND_SESSION_DAYS``, and ``MASTERMIND_COOKIE_SECURE``
are now NO-OPS (kept in the flag registry for backwards compatibility; the middleware
ignores them). ``MASTERMIND_REQUIRE_AUTH`` is likewise a no-op — with no password gate
there is nothing to refuse-to-start over.

DEPLOYMENT TOPOLOGY (current — read this before changing any gate)
------------------------------------------------------------------
The **public VPS is the one canonical scheduler/writer**. It runs with
``MASTERMIND_SERVE_ONLY=0`` and ``MASTERMIND_VPS_AUTHORITATIVE=1`` (see
``ops/mastermind-vps.service.d/authoritative.conf``). The retired topology — a
canonical Mac writer behind localhost plus a public serve-only mirror — is GONE.

That cutover matters for authorization: ``serve_only()`` is NO LONGER a proxy for
"is this box reachable from the internet". A gate keyed only on ``serve_only()``
is OPEN on the authoritative public VPS. Anything that used to be safe *because*
it was localhost-only must now gate on ``vps_authoritative()`` instead.

Environment (read from ``os.environ`` at request time; ``import bot`` via app.deps
loads ``.env`` first, so a value in ``.env`` is picked up automatically):

  - ``MASTERMIND_AUTH_TOKEN``   bearer token for the OPERATOR tier + programmatic
        clients (``Authorization: Bearer <token>``). This is the ONLY credential
        the app checks. Unset -> operator paths pass ONLY on a non-authoritative
        (local/dev) box; under ``MASTERMIND_VPS_AUTHORITATIVE=1`` an unset token
        FAILS CLOSED (see OPERATOR ROUTE TIER below).
  - ``MASTERMIND_SERVE_ONLY``   =1 -> serve-only read-mirror mode (see below).
  - ``MASTERMIND_VPS_AUTHORITATIVE`` =1 -> this process is the canonical,
        internet-reachable scheduler/writer. Tightens the pfolio + operator gates.

OPERATOR ROUTE TIER (MW6 docket #10 / ruling R4 second half)
-------------------------------------------------------------
``_OPERATOR_PATHS`` is the set of mutating/LLM-triggering routes that require the
BEARER token (MASTERMIND_AUTH_TOKEN). This prevents an anonymous client on the
open dashboard from spending LLM tokens or triggering book runs. Source:
data/census/CENSUS.md LLM-triggering tags.

Routes included:
  POST /daily              — gated flagship book (LLM)
  POST /reason             — reasoning pass (LLM)
  POST /research           — research session (LLM)
  POST /chat               — live advisor chat (LLM)
  POST /api/autonomous/run — autonomous Brain book (LLM)
  POST /api/heavyweight/run— heavyweight Brain book (LLM)
  POST /api/china/run      — China Brain book (LLM)
  POST /api/hk/run         — HK Brain book (LLM)
  POST /api/etf/run        — ETF Brain book (LLM)
  POST /api/self_directed/order   — order placement (non-LLM mutating POST)
  POST /api/self_directed/thesis  — thesis write (non-LLM mutating POST)
  POST /api/self_directed/cancel  — order cancel (non-LLM mutating POST)

Read-only dashboard GETs are open (no login).

FAIL-CLOSED ON THE AUTHORITATIVE BOX. When no bearer token is configured the old
behaviour was "operator paths pass (dev ergonomics)" — unconditionally. The
authoritative unit declares ``EnvironmentFile=-/etc/macro-api.env``; the leading
``-`` makes that file OPTIONAL, so a missing/unreadable secrets file would have
silently converted every LLM-spending and book-running route into an
unauthenticated one. Now:
  - ``MASTERMIND_VPS_AUTHORITATIVE=1`` + no token -> operator paths are REFUSED
    (503 ``operator_auth_misconfigured``), and ``assert_authoritative_auth_configured()``
    refuses process startup with a clear configuration error.
  - not authoritative (local dev) + no token -> operator paths pass, unchanged.

RATE LIMITS (MW6)
-----------------
In-memory SLIDING WINDOW per route group, keyed per group:
  - llm     : LLM-triggering operator paths — 8/hour AND 2/minute (both enforced)
  - operator: non-LLM mutating operator POSTs — 30/hour
Stdlib only (no slowapi).  429 with Retry-After.
Advisory run-event emitted on each 429.

The two LLM limits are INDEPENDENT quotas, enforced together — that is the written
contract. The previous implementation approximated them with one token bucket
(capacity 2, refill 8/3600s), which matched neither: after the initial two calls it
admitted only one request per 450s (far stricter than 2/min), while the full burst
plus refill could exceed 8 inside some rolling hours (looser than 8/hr). A bounded
timestamp deque expresses both exactly.

SERVE-ONLY MODE (MW6)
---------------------
``MASTERMIND_SERVE_ONLY=1`` converts the app to a read-only mirror:
  (a) scheduler is NEVER started (guarded in app.main startup)
  (b) first-run daemon threads are skipped
  (c) ALL operator paths return 403 JSON naming the mirror
  (d) /api/pfolio/* (personal Supabase portfolio CRUD) is BLOCKED entirely —
      ALL methods (GET/POST/PATCH/PUT/DELETE) return 403. See PFOLIO below.
  (e) /health gains "serve_only": true
Serve-only remains supported for a genuine read mirror; it is simply no longer
the public box's mode.

PERSONAL PFOLIO PANEL (PRD-R8, re-revised for the VPS cutover)
---------------------------------------------------------------
``/api/pfolio/*`` is the personal Supabase portfolio panel. The CALLER supplies no
user identity: ``app/pfolio.py`` resolves the operator's UUID itself and performs
every read/write with the Supabase SERVICE-ROLE key. So an unauthenticated request
that reaches those handlers reads or mutates the operator's real holdings.

It used to be gated solely by the browser PASSWORD COOKIE. That flow is gone. The
gate that replaced it keyed on ``serve_only()`` alone, which was only ever safe
while the canonical instance was localhost-bound. It is NOT safe now: the
canonical instance is the public VPS with ``MASTERMIND_SERVE_ONLY=0``.

Current model:
  - SERVE-ONLY mirror                -> BLOCKED, all methods, 403.
  - AUTHORITATIVE VPS                -> the OPERATOR BEARER TOKEN is required on
    EVERY method (GET included). With no token configured the surface is blocked
    outright (403) rather than left open — fail closed, never fail open. The
    service-role key stays server-side; it is never handed to a browser.
  - Local / non-authoritative dev box -> OPEN, unchanged (no bearer to send, not
    internet-reachable).

Note the consequence, which is intended: the browser panel has no bearer to send,
so on the authoritative VPS the personal panel is not reachable from a plain
browser session until a real per-user authentication mechanism exists. An
unauthenticated holdings read/write is the defect being closed; losing the
unauthenticated panel is the cost of closing it.

DO NOT treat the edge as the gate. As of 2026-08-19 an upstream entitlement layer
in front of bot.mastermind-x.com answers an anonymous GET /api/pfolio/positions with
``{"locked":true,"tier":"anon","required_tier":"pro"}``. That is a SUBSCRIPTION
paywall, not an operator-identity check: it stops anonymous callers, but anyone at
the required tier passes it and would have reached these handlers acting as the
OPERATOR's Supabase account. It is also external to this process, so any path that
reaches the origin directly (another hostname, the origin port, a worker
misconfiguration) never sees it. The gate below is the one that has to hold.
"""
from __future__ import annotations

import hmac
import logging
import os
import time
from collections import deque
from typing import Callable, Sequence

from fastapi import Request   # module-level so FastAPI resolves the `request: Request`
                             # annotation under `from __future__ import annotations`

log = logging.getLogger("mastermind.auth")

#: Paths never gated by any check. The browser login flow is gone, so the only
#: always-open routes left are the uptime/health + readiness probes. (Kept as a
#: named set so scripts/system_census.py can introspect it via getattr.)
_OPEN_PATHS = {"/health", "/ready"}

# ---------------------------------------------------------------------------
# operator route tier — mutating/LLM-triggering POST paths that require the
# BEARER token (cookie is NOT sufficient).  Source: data/census/CENSUS.md.
# ---------------------------------------------------------------------------

#: LLM-triggering operator POSTs — sliding window: 8/hour AND 2/minute.
_LLM_OPERATOR_PATHS: frozenset[str] = frozenset({
    "/daily",
    "/reason",
    "/research",
    "/chat",
    "/api/autonomous/run",
    "/api/heavyweight/run",
    "/api/china/run",
    "/api/hk/run",
    "/api/etf/run",
})

#: Non-LLM mutating operator POSTs — sliding window: 30/hour.
_NON_LLM_OPERATOR_PATHS: frozenset[str] = frozenset({
    "/api/self_directed/order",
    "/api/self_directed/thesis",
    "/api/self_directed/cancel",
    # Mastermind AI admin section (W-AI) — settings/directives/manual cycle
    "/api/mastermind_ai/settings",
    "/api/mastermind_ai/directive",
    "/api/mastermind_ai/act_on_nudges",
    "/api/mastermind_ai/run",
})

#: Union — all operator-tier paths.
_OPERATOR_PATHS: frozenset[str] = _LLM_OPERATOR_PATHS | _NON_LLM_OPERATOR_PATHS

# ---------------------------------------------------------------------------
# PRD-R8 (re-revised): personal Supabase portfolio CRUD. Every handler behind this
# prefix acts as the operator using the SERVICE-ROLE key and takes no caller
# identity, so the prefix itself is the security boundary. See the module
# docstring (PERSONAL PFOLIO PANEL) for the per-instance rules enforced in `_gate`.
# ---------------------------------------------------------------------------
_PFOLIO_PATH_PREFIX = "/api/pfolio/"

_TRUTHY = {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# instance mode
# ---------------------------------------------------------------------------

def serve_only() -> bool:
    """True when MASTERMIND_SERVE_ONLY=1 — read-only mirror mode."""
    return os.environ.get("MASTERMIND_SERVE_ONLY", "").strip().lower() in _TRUTHY


def vps_authoritative() -> bool:
    """True when MASTERMIND_VPS_AUTHORITATIVE=1 — this process is the canonical,
    internet-reachable scheduler/writer (ops/mastermind-vps.service.d/authoritative.conf).

    Gates that exist to protect an operator-only surface must consult THIS, not
    ``serve_only()``: the authoritative box runs with MASTERMIND_SERVE_ONLY=0.
    """
    return os.environ.get("MASTERMIND_VPS_AUTHORITATIVE", "").strip().lower() in _TRUTHY


# ---------------------------------------------------------------------------
# in-memory sliding-window rate limiting for operator paths (stdlib only)
# ---------------------------------------------------------------------------

#: LLM operator quota — both limits enforced independently.
_LLM_RULES: tuple[tuple[int, float], ...] = ((2, 60.0), (8, 3600.0))
#: Non-LLM mutating operator quota.
_OPERATOR_RULES: tuple[tuple[int, float], ...] = ((30, 3600.0),)


class _SlidingWindowLimiter:
    """Enforce one or more independent ``(limit, window_seconds)`` quotas exactly.

    A request is admitted only when EVERY rule has room for it. Accepted-event
    timestamps are kept in a deque pruned to the longest window, so memory is
    bounded by the largest limit (8 entries for the LLM group) regardless of
    traffic. Thread-safe enough for CPython under the GIL, exactly as the token
    bucket it replaces was.

    ``clock`` is injectable so boundary behaviour is testable without sleeping.
    """
    __slots__ = ("_rules", "_clock", "_events", "_max_window")

    def __init__(self, rules: Sequence[tuple[int, float]],
                 clock: Callable[[], float] = time.monotonic) -> None:
        if not rules:
            raise ValueError("a limiter needs at least one (limit, window) rule")
        # shortest window first so the tightest burst rule is reported first
        self._rules: tuple[tuple[int, float], ...] = tuple(
            sorted(((int(n), float(w)) for n, w in rules), key=lambda r: r[1]))
        self._clock = clock
        self._events: deque[float] = deque()
        self._max_window = max(w for _, w in self._rules)

    @property
    def rules(self) -> tuple[tuple[int, float], ...]:
        return self._rules

    @property
    def burst_limit(self) -> int:
        """The tightest limit — how many calls a cold limiter admits back to back."""
        return min(n for n, _ in self._rules)

    def _prune(self, now: float) -> None:
        cutoff = now - self._max_window
        while self._events and self._events[0] <= cutoff:
            self._events.popleft()

    def consume(self) -> float | None:
        """Record one accepted event. Returns None on success, or seconds-to-wait
        on rejection. A rejected call records NOTHING (a caller cannot push its own
        retry deadline out by hammering)."""
        now = self._clock()
        self._prune(now)
        wait = 0.0
        for limit, window in self._rules:
            start = now - window
            inside = [t for t in self._events if t > start]
            if len(inside) >= limit:
                # the event that must age out of THIS window before we have room
                blocking = inside[-limit]
                wait = max(wait, blocking + window - now)
        if wait > 0:
            return wait
        self._events.append(now)
        return None

    def reset(self) -> None:
        """Forget every recorded event (TEST hook — module-global limiter state
        otherwise leaks across tests/orderings)."""
        self._events.clear()


# Module-global state: tests MUST reset via reset_rate_buckets() (autouse fixture)
# or ordering becomes load-bearing.
_llm_limiter = _SlidingWindowLimiter(_LLM_RULES)
_operator_limiter = _SlidingWindowLimiter(_OPERATOR_RULES)


def reset_rate_buckets() -> None:
    """Clear both operator rate limiters (TEST hook — see conftest autouse fixture)."""
    _llm_limiter.reset()
    _operator_limiter.reset()


# ---------------------------------------------------------------- config ----

def _bearer_token() -> str | None:
    return os.environ.get("MASTERMIND_AUTH_TOKEN") or None


class AuthorizationMisconfigured(RuntimeError):
    """The process is authoritative but has no operator credential configured."""


def assert_authoritative_auth_configured() -> None:
    """Refuse startup when the authoritative box has no operator bearer token.

    ``ops/mastermind-vps.service.d/authoritative.conf`` loads its secrets from
    ``EnvironmentFile=-/etc/macro-api.env`` — OPTIONAL at the service-manager level.
    A missing or unreadable secrets file must surface as a failed start with a clear
    message, not as a silently unauthenticated operator surface. Callers: the
    app.main startup hook. A no-op on a non-authoritative (local/dev) process.
    """
    if vps_authoritative() and not _bearer_token():
        raise AuthorizationMisconfigured(
            "MASTERMIND_VPS_AUTHORITATIVE=1 but MASTERMIND_AUTH_TOKEN is not set. "
            "The authoritative instance exposes operator/LLM routes and the personal "
            "portfolio panel; it must not start without an operator credential. "
            "Set MASTERMIND_AUTH_TOKEN (normally via /etc/macro-api.env) and restart."
        )


# ------------------------------------------------------------- authorize ----

def is_operator_authorized(request) -> bool:
    """True iff the request carries a valid BEARER token.

    Operator-tier paths (mutating / LLM-triggering POSTs) require the bearer
    token. An anonymous client on the open dashboard must NOT be able to fire
    LLM-triggering or mutating routes.

    When no token is configured this returns True on a LOCAL/dev process (the
    long-standing dev ergonomics) but False on an authoritative one — a missing
    credential on the internet-reachable canonical writer must fail CLOSED.
    """
    tok = _bearer_token()
    if not tok:
        return not vps_authoritative()
    auth = request.headers.get("authorization", "")
    return auth.lower().startswith("bearer ") and hmac.compare_digest(auth[7:].strip(), tok)


# --------------------------------------------------------------- install ----

def install(app) -> None:
    """Wire the operator-tier / serve-only / pfolio / rate-limit middleware onto a FastAPI app.

    Safe to call unconditionally. There is NO browser login: read-only browsing
    (every GET + the SSE stream) is always open. The middleware enforces only:
      1. the serve-only POST guard (MASTERMIND_SERVE_ONLY),
      2. the personal-pfolio guard (MASTERMIND_SERVE_ONLY / MASTERMIND_VPS_AUTHORITATIVE),
      3. the bearer-token OPERATOR tier (MASTERMIND_AUTH_TOKEN),
      4. rate limiting on operator paths.
    """
    from fastapi.responses import JSONResponse

    def _emit_rate_limit_event(path: str) -> None:
        """Emit an ADVISORY run-event on each 429. Never raises."""
        try:
            from control_plane import run_events
            run_events.append({
                "kind": "guardrail",
                "job": "rate_limit",
                "book": "",
                "step": "operator_rate_limit",
                "status": "warn",
                "severity": "ADVISORY_ONLY",
                "actor": "system",
                "extra": {"path": path},
            })
        except Exception:  # noqa: BLE001
            pass

    @app.middleware("http")
    async def _gate(request: Request, call_next):
        path = request.url.path
        method = request.method

        if method == "OPTIONS" or path in _OPEN_PATHS:
            return await call_next(request)

        # --- personal pfolio panel: never reachable unauthenticated ---
        # These handlers act as the operator with the Supabase SERVICE-ROLE key and
        # take NO caller identity, so the prefix is the security boundary. Blocked
        # outright on a read mirror; bearer-gated (all methods, GET included) on the
        # authoritative public VPS; open only on a local/non-authoritative box.
        if path.startswith(_PFOLIO_PATH_PREFIX):
            if serve_only():
                return JSONResponse(
                    {"error": "serve_only",
                     "detail": "portfolio panel disabled on the read mirror"},
                    status_code=403,
                )
            if vps_authoritative():
                if not _bearer_token():
                    # Fail CLOSED: no credential exists to authenticate against, and
                    # the surface reads/writes real holdings with a service-role key.
                    return JSONResponse(
                        {"error": "pfolio_unauthenticated_surface_disabled",
                         "detail": ("The personal portfolio panel is disabled on the "
                                    "authoritative instance because no operator credential "
                                    "is configured.")},
                        status_code=403,
                    )
                if not is_operator_authorized(request):
                    return JSONResponse(
                        {"error": "operator_bearer_required",
                         "detail": ("The personal portfolio panel requires a bearer token "
                                    "on the authoritative instance.")},
                        status_code=401,
                    )

        # --- serve-only mode: block all operator mutations ---
        if serve_only() and method in {"POST", "PATCH", "PUT", "DELETE"} and path in _OPERATOR_PATHS:
            return JSONResponse(
                {"error": "serve_only", "detail": (
                    "This instance is running in serve-only (read-only mirror) mode. "
                    "Operator mutations are disabled. Use the primary instance."
                )},
                status_code=403,
            )

        # --- read access is OPEN: no login. Every GET, the SSE stream and the
        #     read APIs fall straight through. Only the operator tier below gates. ---

        # --- operator-tier gate: bearer token required for mutating/LLM POSTs ---
        if method == "POST" and path in _OPERATOR_PATHS:
            if not is_operator_authorized(request):
                if vps_authoritative() and not _bearer_token():
                    # Distinguish "you sent no/incorrect credential" from "this box has
                    # no credential configured at all" — the latter is an operator-fixable
                    # deployment fault, not a client error.
                    log.error("operator path %s refused: MASTERMIND_AUTH_TOKEN unset on an "
                              "authoritative instance", path)
                    return JSONResponse(
                        {"error": "operator_auth_misconfigured",
                         "detail": ("This authoritative instance has no operator credential "
                                    "configured; operator paths are refused.")},
                        status_code=503,
                    )
                return JSONResponse(
                    {"error": "operator_bearer_required",
                     "detail": "Operator paths require a bearer token."},
                    status_code=401,
                )

            # --- rate limiting on operator paths ---
            if path in _LLM_OPERATOR_PATHS:
                wait = _llm_limiter.consume()
            else:
                wait = _operator_limiter.consume()

            if wait is not None:
                retry_after = max(1, int(wait) + 1)
                _emit_rate_limit_event(path)
                return JSONResponse(
                    {"error": "rate_limited",
                     "detail": f"Rate limit exceeded. Retry after {retry_after}s.",
                     "retry_after": retry_after},
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                )

        return await call_next(request)
