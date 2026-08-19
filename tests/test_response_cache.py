"""The read-response cache must stay bounded AND stay alive.

This cache exists because uncached dashboard reads on a constrained box peg the CPU and produce
gateway timeouts. The failure mode fixed here is that it could permanently disable ITSELF:

  * entries were admitted only while ``len(_CACHE) < _MAX_ENTRIES`` (512),
  * nothing was ever evicted, and expired entries kept occupying their slots,
  * so once 512 distinct keys existed no new key could be cached — and an EXISTING key could not
    be refreshed after expiry either, because the length check ran before the assignment.

From then on every request recomputed, forever, until ``clear()`` or a restart. The key was
path + the RAW query string, so 512 requests to one endpoint carrying junk query parameters were
enough to trip it.

The clock is injected so expiry is exercised exactly, without sleeping.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import response_cache


_TTL = 30.0


class _Clock:
    """Stand-in for the ``time`` module the cache imports (only ``monotonic`` is used)."""

    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def monotonic(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture()
def cache_app(monkeypatch):
    """A throwaway app behind the real cache middleware, with a driven clock and a call counter."""
    monkeypatch.setenv("MASTERMIND_RESP_CACHE_TTL", str(_TTL))
    clock = _Clock()
    monkeypatch.setattr(response_cache, "time", clock)
    response_cache.clear()

    calls = {"n": 0}
    app = FastAPI()
    response_cache.install(app)

    @app.get("/api/probe")
    def probe(n: int = 0, a: str = "", b: str = ""):
        calls["n"] += 1
        return {"n": n, "computed": calls["n"]}

    client = TestClient(app)
    try:
        yield client, clock, calls
    finally:
        response_cache.clear()


def _saturate(client, count: int = None, offset: int = 0) -> None:
    """Fill the cache with `count` distinct keys (defaults to exactly its capacity)."""
    count = response_cache._MAX_ENTRIES if count is None else count
    for i in range(offset, offset + count):
        client.get(f"/api/probe?n={i}")


# ---------------------------------------------------------------------------
# the bound itself
# ---------------------------------------------------------------------------

def test_cache_never_exceeds_its_bound(cache_app):
    client, _clock, _calls = cache_app
    _saturate(client, response_cache._MAX_ENTRIES * 3)
    assert len(response_cache._CACHE) <= response_cache._MAX_ENTRIES


def test_saturation_fills_exactly_to_capacity(cache_app):
    client, _clock, _calls = cache_app
    _saturate(client)
    assert len(response_cache._CACHE) == response_cache._MAX_ENTRIES


# ---------------------------------------------------------------------------
# the reported defect: caching must not switch off permanently
# ---------------------------------------------------------------------------

def test_a_new_key_is_still_cached_after_saturation_and_expiry(cache_app):
    client, clock, _calls = cache_app
    _saturate(client)
    clock.advance(_TTL + 1)          # every entry is now stale

    first = client.get("/api/probe?n=999999")
    assert first.headers.get("x-mm-cache") == "miss"
    second = client.get("/api/probe?n=999999")
    assert second.headers.get("x-mm-cache") == "hit", (
        "a full-but-expired cache must reclaim room instead of refusing new entries forever"
    )
    assert second.json() == first.json()


def test_an_expired_key_can_refresh_while_at_capacity(cache_app):
    client, clock, calls = cache_app
    _saturate(client)
    clock.advance(_TTL + 1)

    before = calls["n"]
    refreshed = client.get("/api/probe?n=0")          # a key that already exists, but stale
    assert refreshed.headers.get("x-mm-cache") == "miss"
    assert calls["n"] == before + 1, "an expired entry must be recomputed, not served"

    again = client.get("/api/probe?n=0")
    assert again.headers.get("x-mm-cache") == "hit", "the refreshed entry must be stored"
    assert calls["n"] == before + 1, "the second read must be served from cache"


def test_expired_entries_are_never_served(cache_app):
    client, clock, calls = cache_app
    client.get("/api/probe?n=1")
    assert client.get("/api/probe?n=1").headers.get("x-mm-cache") == "hit"

    clock.advance(_TTL + 1)
    stale = client.get("/api/probe?n=1")
    assert stale.headers.get("x-mm-cache") == "miss"


def test_junk_query_flooding_cannot_disable_caching(cache_app):
    """The abuse path that reached the stuck state: many distinct keys on ONE endpoint."""
    client, _clock, _calls = cache_app
    _saturate(client, response_cache._MAX_ENTRIES * 2, offset=10_000)
    assert len(response_cache._CACHE) <= response_cache._MAX_ENTRIES

    # A legitimate read must still be cacheable afterwards, with no expiry and no clear().
    assert client.get("/api/probe?n=7").headers.get("x-mm-cache") == "miss"
    assert client.get("/api/probe?n=7").headers.get("x-mm-cache") == "hit", (
        "flooding must cost evictions, never the cache's ability to serve"
    )


def test_lru_eviction_prefers_the_least_recently_used(cache_app):
    client, _clock, _calls = cache_app
    _saturate(client)

    keep = "/api/probe?n=0"
    client.get(keep)                                  # touch it -> most recently used
    assert client.get(keep).headers.get("x-mm-cache") == "hit"

    # Push in half a cache worth of new keys; the recently-touched entry should survive.
    _saturate(client, response_cache._MAX_ENTRIES // 2, offset=50_000)
    assert client.get(keep).headers.get("x-mm-cache") == "hit", (
        "a recently used entry must outlive colder ones under eviction pressure"
    )


# ---------------------------------------------------------------------------
# key canonicalisation — equivalent requests are ONE identity
# ---------------------------------------------------------------------------

def test_query_parameter_order_is_one_cache_identity(cache_app):
    client, _clock, calls = cache_app
    before = calls["n"]
    first = client.get("/api/probe?a=1&b=2")
    assert first.headers.get("x-mm-cache") == "miss"

    reordered = client.get("/api/probe?b=2&a=1")
    assert reordered.headers.get("x-mm-cache") == "hit", (
        "reordered parameters are the same request and must share one entry"
    )
    assert calls["n"] == before + 1
    assert len(response_cache._CACHE) == 1


def test_distinct_parameters_stay_distinct(cache_app):
    """Canonicalisation must collapse duplicates only — never merge different requests."""
    client, _clock, _calls = cache_app
    a = client.get("/api/probe?n=1")
    b = client.get("/api/probe?n=2")
    assert a.json()["n"] == 1
    assert b.json()["n"] == 2
    assert b.headers.get("x-mm-cache") == "miss"
    assert len(response_cache._CACHE) == 2


# ---------------------------------------------------------------------------
# the gate and the denylist are unchanged
# ---------------------------------------------------------------------------

def test_disabled_when_ttl_is_unset(monkeypatch):
    monkeypatch.delenv("MASTERMIND_RESP_CACHE_TTL", raising=False)
    response_cache.clear()
    app = FastAPI()
    response_cache.install(app)

    @app.get("/api/probe")
    def probe():
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/api/probe").headers.get("x-mm-cache") is None
    assert len(response_cache._CACHE) == 0


def test_denylisted_prefixes_are_never_cached(monkeypatch):
    monkeypatch.setenv("MASTERMIND_RESP_CACHE_TTL", str(_TTL))
    response_cache.clear()
    app = FastAPI()
    response_cache.install(app)

    @app.get("/api/pfolio/positions")
    def positions():
        return {"ok": True}

    client = TestClient(app)
    client.get("/api/pfolio/positions")
    client.get("/api/pfolio/positions")
    assert len(response_cache._CACHE) == 0, "the personal portfolio panel must never be cached"
    response_cache.clear()
