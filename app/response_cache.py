"""Short-TTL in-memory response cache for read-only GET /api/* endpoints.

On a 1-core box the dashboard fires ~20 /api/* calls on load, and several recompute heavy
artifacts per request (e.g. /api/outcomes rebuilds labels+track-record+calibration; the
/api/portfolios tab-list re-prices every book) — so repeat/concurrent reads peg the single core and
Cloudflare 524s. This caches each GET /api/* JSON response in memory for MASTERMIND_RESP_CACHE_TTL
seconds (keyed by path+query): the first request computes, the rest are instant.

GATED by ``MASTERMIND_RESP_CACHE_TTL`` (seconds; 0 or unset = DISABLED). Leave it unset on any
instance that mutates state on every build; set it where the served data changes on a slow cadence
and a few seconds of staleness is harmless.

Correctness:
  * Installed BEFORE the auth gate so auth stays OUTERMOST — an unauthenticated request never reaches
    the cache, so no cached data can leak to an unauthorized caller.
  * Only GET, only ``/api/*`` (minus a live-lookup denylist), only 200 ``application/json`` responses.
  * Keyed by path+query, NOT per user — the dashboard's read data is identical for every authorized
    viewer, and the auth gate already ran upstream.

BOUNDED — the cache must never be able to disable itself.
  The previous implementation admitted an entry only while ``len(_CACHE) < _MAX_ENTRIES`` and never
  removed anything, so once 512 distinct keys existed the cache was permanently stuck: expired
  entries still occupied their slots, no new key could be admitted, and an EXISTING key could not
  even be refreshed after expiry. Every subsequent request recomputed forever — the exact CPU
  pathology this module exists to prevent — until ``clear()`` or a process restart. Because the key
  included the raw query string, 512 requests to ONE endpoint carrying junk query parameters were
  enough to reach that state. Now: query parameters are canonicalised (order-insensitive) so
  equivalent requests share one identity, expired entries are purged on admission, and a full cache
  evicts least-recently-used entries. ``_CACHE`` never exceeds ``_MAX_ENTRIES``.
"""
from __future__ import annotations

import os
import time
from collections import OrderedDict
from urllib.parse import parse_qsl, urlencode

# key -> (expiry_monotonic, body, media_type). Ordered LRU: least-recently-used first.
_CACHE: OrderedDict[str, tuple[float, bytes, str]] = OrderedDict()
_MAX_ENTRIES = 512

# Never cache: live per-request lookups keyed off user-supplied query text, and the interactive
# Portfolio Desk (/api/pfolio/*) where a just-added position must show immediately (not after the TTL).
_DENY_PREFIXES = ("/api/self_directed/search", "/api/self_directed/quote", "/api/pfolio/",
                  "/api/account",        # per-user Supabase profile — never shared/public
                  "/api/live_marks",     # active-book intraday marks + session clock
                  "/api/mastermind_ai")  # W-AI admin surface — always fresh, never mirror-cached

# The origin already holds these read-only responses for ``MASTERMIND_RESP_CACHE_TTL`` seconds.
# Let the browser/edge reuse a response for five seconds too, then serve it for at most another
# five seconds while revalidating.
# This removes repeated global edge latency during one dashboard switch without changing the
# origin's freshness budget or caching any interactive/operator endpoint.
_CLIENT_CACHE_HEADERS = {
    "Cache-Control": "public, max-age=5, stale-while-revalidate=5",
}


def _ttl() -> float:
    try:
        return max(0.0, float(os.environ.get("MASTERMIND_RESP_CACHE_TTL", "0")))
    except (TypeError, ValueError):
        return 0.0


def _cacheable(path: str) -> bool:
    return path.startswith("/api/") and not any(path.startswith(p) for p in _DENY_PREFIXES)


def _cache_key(path: str, query: str) -> str:
    """Path + CANONICALISED query.

    Sorting the parameters makes ``?a=1&b=2`` and ``?b=2&a=1`` one cache identity instead of two.
    These handlers read parameters by name and never depend on their order, so this only collapses
    duplicates — it cannot merge two semantically different requests. Falls back to the raw query
    when it cannot be parsed, which is still a stable key for a given input.
    """
    if not query:
        return path + "?"
    try:
        return path + "?" + urlencode(sorted(parse_qsl(query, keep_blank_values=True)))
    except Exception:  # noqa: BLE001 — an unparseable query still deserves a stable key
        return path + "?" + query


def _purge_expired(now: float) -> int:
    """Drop every entry whose TTL has elapsed. Returns how many were removed."""
    stale = [k for k, (expiry, _, _) in _CACHE.items() if expiry <= now]
    for k in stale:
        _CACHE.pop(k, None)
    return len(stale)


def _admit(key: str, entry: tuple[float, bytes, str], now: float) -> None:
    """Store `entry` under `key`, keeping the cache within `_MAX_ENTRIES`.

    Order of preference when the cache is full: replace the key itself (a refresh is never blocked
    by capacity), then reclaim expired entries, then evict least-recently-used.
    """
    _CACHE.pop(key, None)           # a refresh replaces; it never competes for a free slot
    if len(_CACHE) >= _MAX_ENTRIES:
        _purge_expired(now)
    while len(_CACHE) >= _MAX_ENTRIES:
        _CACHE.popitem(last=False)  # evict the least-recently-used end
    _CACHE[key] = entry


def clear() -> None:
    """Drop the cache (tests / a forced refresh)."""
    _CACHE.clear()


def install(app) -> None:
    """Wire the response cache onto a FastAPI app. A no-op at request time when the TTL env is 0/unset,
    so it is always safe to install unconditionally."""
    from starlette.responses import Response

    @app.middleware("http")
    async def _resp_cache(request, call_next):
        ttl = _ttl()
        if ttl <= 0 or request.method != "GET" or not _cacheable(request.url.path):
            return await call_next(request)

        key = _cache_key(request.url.path, request.url.query or "")
        now = time.monotonic()
        hit = _CACHE.get(key)
        if hit is not None:
            if hit[0] > now:
                _CACHE.move_to_end(key)          # mark recently used
                return Response(content=hit[1], status_code=200, media_type=hit[2],
                                headers={"x-mm-cache": "hit", **_CLIENT_CACHE_HEADERS})
            _CACHE.pop(key, None)                # expired — never serve it, never keep its slot

        resp = await call_next(request)
        # Read the streamed body ONCE (the original iterator is then consumed), cache it, and hand back
        # a fresh Response carrying the same bytes. Only 200 application/json is cached.
        ctype = resp.headers.get("content-type", "")
        if resp.status_code == 200 and "application/json" in ctype:
            body = b""
            async for chunk in resp.body_iterator:
                body += chunk
            media = ctype.split(";")[0].strip() or "application/json"
            _admit(key, (now + ttl, body, media), now)
            return Response(content=body, status_code=200, media_type=media,
                            headers={"x-mm-cache": "miss", **_CLIENT_CACHE_HEADERS})
        return resp

    return None
